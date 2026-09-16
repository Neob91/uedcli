// Shares ONE built scene (geometry/materials/textures/markers) across every pane -- Perspective and
// the three ortho panes (quad-layout Part 0, Task 2) -- instead of each pane rebuilding/re-uploading
// the same BufferGeometry to the GPU. `SceneResourcesProvider` calls sceneResources.ts's hooks
// exactly once per (scene, atlas, lightmap) triple; every pane reads the result via
// `useSceneResourcesContext()`.
import { createContext, useContext, useEffect, useMemo } from 'react'
import type { ReactNode } from 'react'
import * as THREE from 'three'

import type { AtlasPayload, LightmapPayload, SceneActor, ScenePayload } from '../api'
import { buildGeometryData } from './geometry'
import { actorsNeedingMarkers } from './markers'
import { useBuiltGeometry, useLightmapTexture, useMarkerTexture, useTextures } from './sceneResources'

export interface SceneResources {
  bufferGeometry: THREE.BufferGeometry
  materials: THREE.Material[]
  // Same geometry/group indexing as `materials`, lightmap dropped -- a pane picks this array
  // instead when its OWN shading mode is 'unlit', so 'unlit' genuinely differs from 'lit' (review
  // finding: both modes rendered the identical mesh since materials were built once, shared, with
  // no per-mode variant).
  unlitMaterials: THREE.Material[]
  triangleOwners: (string | null)[]
  // Same per-triangle indexing as `triangleOwners`, into the original `scene.polys` array -- the
  // surface (single-polygon) click-to-select identity (`selection.ts`'s `resolveHitSurface`).
  trianglePolyIndex: (number | null)[]
  // A Mover's own solved geometry, split OUT of the fields above (GUI.md "Movers"): a Mover always
  // renders wireframe-outline-only by default, in every shading mode, so its solid triangles must
  // NOT ride the default `bufferGeometry`/`materials` a pane draws unconditionally -- they draw only
  // when the "Movers: on" toggle additionally requests them (`Viewport3D`'s `showMoverSolid`).
  // Same per-group shape as the fields above (`bufferGeometry`/`materials`/`unlitMaterials`/
  // `triangleOwners`), just scoped to Mover-owned polys alone.
  moverGeometry: THREE.BufferGeometry
  moverMaterials: THREE.Material[]
  moverUnlitMaterials: THREE.Material[]
  moverTriangleOwners: (string | null)[]
  moverTrianglePolyIndex: (number | null)[]
  // A mesh actor (any non-brush actor whose resolved geometry owns real triangles -- a DT_Mesh
  // actor, in practice) draws WIREFRAME in wireframe mode, matching a brush's own wireframe
  // convention there (GUI.md "Shading modes"; real UnrealEd renders a mesh as wireframe, never solid
  // or hidden, whenever the view is in wireframe mode). Unlike the Mover split above, this does NOT
  // pull mesh polys OUT of `bufferGeometry`/`materials` -- a mesh actor's SOLID rendering in
  // 'unlit'/'flat'/'lit' is unchanged, still riding the default array. This is purely the wireframe
  // OVERLAY: the real triangle-edge wireframe of those same polys (`THREE.WireframeGeometry` over
  // the built triangle positions -- the same triangle extraction `buildGeometryData` already does
  // for solid rendering, not a bounding-box/silhouette approximation), which a pane draws INSTEAD of
  // the solid mesh when its own mode is wireframe (every ortho pane; the perspective pane in
  // `'wireframe'` mode).
  meshWireframeGeometry: THREE.BufferGeometry
  textures: { map: Map<number, THREE.Texture>; sprite: Map<number, THREE.Texture> }
  markerTexture: THREE.Texture | null
  markerActors: SceneActor[]
  // The full actor list (Part 1, Task 6 addition, not in the plan's original interface list):
  // OrthoViewport's own props carry no `scene` (per the plan, just axis/selectedName/onSelectActor),
  // but click-to-select's AABB fallback (`pickActor`) and triangle-owner resolution
  // (`resolveHitActor`) both need the FULL actor set, not just `markerActors` -- so it rides the
  // context instead of a second prop every ortho pane would otherwise need threaded to it.
  actors: SceneActor[]
}

const SceneResourcesReactContext = createContext<SceneResources | null>(null)

export function SceneResourcesProvider({
  scene,
  atlas,
  lightmap,
  children,
}: {
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload | null
  children: ReactNode
}) {
  const textures = useTextures(atlas)
  const lightmapTexture = useLightmapTexture(lightmap)
  const markerTexture = useMarkerTexture()

  // Movers always render wireframe-outline-only by default (GUI.md "Movers"), so their solid polys
  // are split OUT of the default geometry into their own built resources -- `Viewport3D` draws
  // `moverGeometry` only when the "Movers: on" toggle is active. `moverNames` comes from the
  // server's authoritative `SceneActor.is_mover` (never re-derived from `cls` -- the client has no
  // class-schema access).
  const moverNames = useMemo(
    () => new Set(scene.actors.filter((a) => a.is_mover).map((a) => a.name)),
    [scene.actors],
  )
  // Each subset carries its own polys' index into the ORIGINAL `scene.polys` array alongside the
  // filtered poly itself -- `useBuiltGeometry`'s `sourceIndices` needs this to build a surface
  // (single-polygon) selection identity that survives the non-Mover/Mover split (geometry.ts's
  // `trianglePolyIndex` doc comment: a plain local index would collide across the two subsets).
  const { polys: nonMoverPolys, indices: nonMoverIndices } = useMemo(() => {
    const polys: typeof scene.polys = []
    const indices: number[] = []
    scene.polys.forEach((p, i) => {
      if (p.owner == null || !moverNames.has(p.owner)) {
        polys.push(p)
        indices.push(i)
      }
    })
    return { polys, indices }
  }, [scene.polys, moverNames])
  const { polys: moverPolys, indices: moverIndices } = useMemo(() => {
    const polys: typeof scene.polys = []
    const indices: number[] = []
    scene.polys.forEach((p, i) => {
      if (p.owner != null && moverNames.has(p.owner)) {
        polys.push(p)
        indices.push(i)
      }
    })
    return { polys, indices }
  }, [scene.polys, moverNames])
  const { bufferGeometry, materials, unlitMaterials, triangleOwners, trianglePolyIndex } =
    useBuiltGeometry(nonMoverPolys, atlas, lightmap, textures, lightmapTexture, nonMoverIndices)
  const {
    bufferGeometry: moverGeometry,
    materials: moverMaterials,
    unlitMaterials: moverUnlitMaterials,
    triangleOwners: moverTriangleOwners,
    trianglePolyIndex: moverTrianglePolyIndex,
  } = useBuiltGeometry(moverPolys, atlas, lightmap, textures, lightmapTexture, moverIndices)

  // Mesh actors (GUI.md "Shading modes"): every non-brush actor (`SceneActor.brush === null`) --
  // covers a resolved DT_Mesh actor, and harmlessly a point actor that owns no polys at all. Their
  // solid polys stay in `bufferGeometry`/`materials` above (solid rendering is unchanged); this only
  // builds the WIREFRAME overlay, from the SAME triangle positions `buildGeometryData` already
  // extracts for solid rendering (no UVs/lightmap/materials needed for a plain line overlay).
  const meshActorNames = useMemo(
    () => new Set(scene.actors.filter((a) => !a.brush).map((a) => a.name)),
    [scene.actors],
  )
  const meshPolys = useMemo(
    () => scene.polys.filter((p) => p.owner != null && meshActorNames.has(p.owner)),
    [scene.polys, meshActorNames],
  )
  const meshWireframeGeometry = useMemo(() => {
    const { positions } = buildGeometryData(meshPolys, atlas)
    const trianglesGeo = new THREE.BufferGeometry()
    trianglesGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const wire = new THREE.WireframeGeometry(trianglesGeo)
    trianglesGeo.dispose() // only fed WireframeGeometry's own edge extraction, not kept
    return wire
  }, [meshPolys, atlas])
  useEffect(() => {
    return () => meshWireframeGeometry.dispose()
  }, [meshWireframeGeometry])

  // Point actors with no owned rendered poly (lights, triggers, patrol nodes, sounds, an unresolved
  // DT_Mesh) -- markers.ts's own filter, computed once here rather than per-pane. Unions BOTH
  // triangle-owner arrays: a Mover's own polys moved to `moverTriangleOwners` above, but it still
  // owns rendered geometry (just not in the default array), so it must not read as marker-needing.
  const markerActors = useMemo(() => {
    const ownedNames = new Set(
      [...triangleOwners, ...moverTriangleOwners].filter((n): n is string => n != null),
    )
    return actorsNeedingMarkers(scene.actors, ownedNames)
  }, [scene, triangleOwners, moverTriangleOwners])

  const value = useMemo<SceneResources>(
    () => ({
      bufferGeometry, materials, unlitMaterials, triangleOwners, trianglePolyIndex,
      moverGeometry, moverMaterials, moverUnlitMaterials, moverTriangleOwners, moverTrianglePolyIndex,
      meshWireframeGeometry,
      textures, markerTexture, markerActors, actors: scene.actors,
    }),
    [
      bufferGeometry, materials, unlitMaterials, triangleOwners, trianglePolyIndex,
      moverGeometry, moverMaterials, moverUnlitMaterials, moverTriangleOwners, moverTrianglePolyIndex,
      meshWireframeGeometry,
      textures, markerTexture, markerActors, scene.actors,
    ],
  )

  return <SceneResourcesReactContext.Provider value={value}>{children}</SceneResourcesReactContext.Provider>
}

/** Reads the shared built-scene resources. Throws (naming the missing provider) when called outside
 * a `SceneResourcesProvider` -- a programmer error, not a recoverable render state. */
export function useSceneResourcesContext(): SceneResources {
  const ctx = useContext(SceneResourcesReactContext)
  if (ctx === null) {
    throw new Error('useSceneResourcesContext() called outside a <SceneResourcesProvider>')
  }
  return ctx
}
