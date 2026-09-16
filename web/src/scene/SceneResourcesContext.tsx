// Shares ONE built scene (geometry/materials/textures/markers) across every pane -- Perspective and
// the three ortho panes (quad-layout Part 0, Task 2) -- instead of each pane rebuilding/re-uploading
// the same BufferGeometry to the GPU. `SceneResourcesProvider` calls sceneResources.ts's hooks
// exactly once per (scene, atlas, lightmap) triple; every pane reads the result via
// `useSceneResourcesContext()` (a separate file, along with the raw context object/type in
// `sceneResourcesReactContext.ts` -- this file exports ONLY the `SceneResourcesProvider` component,
// so Vite's react-refresh plugin can Fast Refresh it; mixing in a hook or a plain value export here
// broke that ("X export is incompatible") and silently wedged a pane on the next HMR update until a
// full page reload).
import { useEffect, useMemo } from 'react'
import type { ReactNode } from 'react'
import * as THREE from 'three'

import type { AtlasPayload, LightmapPayload, ScenePayload } from '../api'
import { buildGeometryData } from './geometry'
import { actorsNeedingMarkers } from './markers'
import { useBuiltGeometry, useLightmapTexture, useMarkerTexture, useTextures } from './sceneResources'
import type { SceneResources } from './sceneResourcesReactContext'
import { SceneResourcesReactContext } from './sceneResourcesReactContext'

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
