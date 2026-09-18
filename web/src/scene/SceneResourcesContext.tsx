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
import { buildEdgePickData, buildGeometryData } from './geometry'
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
  const nonMoverPolys = useMemo(
    () => scene.polys.filter((p) => p.owner == null || !moverNames.has(p.owner)),
    [scene.polys, moverNames],
  )
  const moverPolys = useMemo(
    () => scene.polys.filter((p) => p.owner != null && moverNames.has(p.owner)),
    [scene.polys, moverNames],
  )
  const { bufferGeometry, materials, unlitMaterials, triangleOwners, trianglePolyIndex } =
    useBuiltGeometry(nonMoverPolys, atlas, lightmap, textures, lightmapTexture)
  const {
    bufferGeometry: moverGeometry,
    materials: moverMaterials,
    unlitMaterials: moverUnlitMaterials,
    triangleOwners: moverTriangleOwners,
    trianglePolyIndex: moverTrianglePolyIndex,
  } = useBuiltGeometry(moverPolys, atlas, lightmap, textures, lightmapTexture)

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
  const meshGeoData = useMemo(() => buildGeometryData(meshPolys, atlas), [meshPolys, atlas])
  const meshWireframeGeometry = useMemo(() => {
    const trianglesGeo = new THREE.BufferGeometry()
    trianglesGeo.setAttribute('position', new THREE.BufferAttribute(meshGeoData.positions, 3))
    const wire = new THREE.WireframeGeometry(trianglesGeo)
    trianglesGeo.dispose() // only fed WireframeGeometry's own edge extraction, not kept
    return wire
  }, [meshGeoData])
  useEffect(() => {
    return () => meshWireframeGeometry.dispose()
  }, [meshWireframeGeometry])
  // Invisible, raycastable pick mesh for mesh actors in SOLID (non-wireframe) shading modes: a
  // DT_Mesh actor's solid triangles are the only thing that identifies it (it has no brush ring and
  // no marker sprite -- its polys stay in the main geometry). This is the same triangles as
  // `meshWireframeGeometry`, kept as a real (material-invisible) mesh so the raycast resolves a hit
  // to its owning actor via `meshTriangleOwners` -- mirrors BrushOutlines' dedicated owner-carrying
  // pick geometry. Drawn nowhere visible; only ever raycast. NOT used in wireframe/ortho modes any
  // more -- see `meshEdgePickGeometry` below (GUI-PARITY.md "Mesh selection in 2D/3D wireframe mode
  // vs UED22": UED22 only hit-tests a mesh actor's drawn wireframe EDGES there, never its filled
  // interior, so a filled pick mesh let a click anywhere inside the silhouette wrongly select it).
  const meshPickGeometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(meshGeoData.positions, 3))
    return g
  }, [meshGeoData])
  useEffect(() => {
    return () => meshPickGeometry.dispose()
  }, [meshPickGeometry])
  // Invisible, raycastable EDGE-only pick geometry for mesh actors in WIREFRAME/ortho modes
  // (GUI-PARITY.md, same section as above): a `THREE.LineSegments` over the mesh's own triangle
  // edges (not deduped, so each edge keeps its source triangle's owner/polyIndex --
  // `geometry.ts`'s `buildEdgePickData`), raycast with the same line threshold a brush's own
  // outline uses. Only line hits within that threshold register, matching UED22's real click hit-
  // test (a pixel-proximity test against what's actually painted -- only the wireframe lines in
  // this render mode, never the open interior between them).
  const meshEdgePickData = useMemo(() => buildEdgePickData(meshGeoData), [meshGeoData])
  const meshEdgePickGeometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(meshEdgePickData.positions, 3))
    return g
  }, [meshEdgePickData])
  useEffect(() => {
    return () => meshEdgePickGeometry.dispose()
  }, [meshEdgePickGeometry])

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
      meshWireframeGeometry, meshPickGeometry, meshEdgePickGeometry,
      meshTriangleOwners: meshGeoData.triangleOwners, meshTrianglePolyIndex: meshGeoData.trianglePolyIndex,
      meshEdgeOwners: meshEdgePickData.edgeOwners, meshEdgePolyIndex: meshEdgePickData.edgePolyIndex,
      textures, markerTexture, markerActors, actors: scene.actors,
    }),
    [
      bufferGeometry, materials, unlitMaterials, triangleOwners, trianglePolyIndex,
      moverGeometry, moverMaterials, moverUnlitMaterials, moverTriangleOwners, moverTrianglePolyIndex,
      meshWireframeGeometry, meshPickGeometry, meshEdgePickGeometry, meshGeoData, meshEdgePickData,
      textures, markerTexture, markerActors, scene.actors,
    ],
  )

  return <SceneResourcesReactContext.Provider value={value}>{children}</SceneResourcesReactContext.Provider>
}
