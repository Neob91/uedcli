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
import type { Vec3 } from './camera'
import { computeOwnerDeltas } from './dragStage'
import { buildEdgePickData, buildGeometryData } from './geometry'
import { actorsNeedingMarkers } from './markers'
import {
  useBuiltGeometry,
  useLightmapTexture,
  useMarkerTexture,
  usePatchedMeshPositions,
  useTextures,
} from './sceneResources'
import type { SceneResources } from './sceneResourcesReactContext'
import { SceneResourcesReactContext } from './sceneResourcesReactContext'

export function SceneResourcesProvider({
  scene,
  atlas,
  lightmap,
  stagedOffsets,
  children,
}: {
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload | null
  // Bug fix (reported live, post-merge): a Ctrl/Cmd-drag staged move only ever reached the
  // overlay layers (`applyStagedOffsets` over `scene.actors` -- marker, brush outline, vertex/pivot
  // dots, directional arrow, radii) -- a MESH actor's own rendered body (solid triangles in the
  // shared `bufferGeometry` below, plus its wireframe/pick geometry) kept showing the pre-move
  // position, since its polys live in `scene.polys` (a flat, owner-tagged array), never reachable
  // from an actor object the way a brush's own `brush.polys` are. Unlike a BRUSH's CSG-solved
  // surfaces (which genuinely can't cheaply re-transform -- see `dragStage.ts`'s own doc comment),
  // a mesh actor's triangles are a rigid, independently-addressable-by-owner asset with no CSG
  // involved, so this is a real, closeable gap, not the same accepted carve-out. Defaults to `{}`
  // (every non-Viewport/OrthoViewport test-only caller of this provider) so this stays additive.
  //
  // Perf fix (live report, "moving actors is super jittery and slow"): the FIRST version of this fix
  // applied the staged translation by producing a brand-new translated `ScenePoly[]` every frame and
  // feeding it back through `buildGeometryData` -- which rebuilds an ENTIRE level's solid geometry
  // (re-triangulating every poly, rebuilding every material, disposing+reallocating the GPU buffer),
  // not just the moved actor's own triangles, on every single pointer-move event. `usePatchedMeshPositions`
  // below replaces that: the SOLID/pick/edge-pick geometries are now built ONCE from the level's
  // real (unstaged) `scene.polys`, and a staged mesh actor's own vertices are patched directly into
  // the ALREADY-BUILT position buffer -- see that hook's own doc comment.
  stagedOffsets?: Readonly<Record<string, Vec3>>
  children: ReactNode
}) {
  const textures = useTextures(atlas)
  const lightmapTexture = useLightmapTexture(lightmap)
  const markerTexture = useMarkerTexture()

  // Mesh actors (GUI.md "Shading modes"): every non-brush actor (`SceneActor.brush === null`) --
  // covers a resolved DT_Mesh actor, and harmlessly a point actor that owns no polys at all. Used
  // twice below: to scope `meshStagedOffsets` (never a brush's CSG-solved polys -- see
  // `dragStage.ts`'s own doc comment on why translating one would produce WRONG, not just stale,
  // geometry) and as `usePatchedMeshPositions`' own `patchableNames` filter, so the MAIN buffer's
  // per-frame patch loop (below) never walks a brush's own range.
  const meshActorNames = useMemo(
    () => new Set(scene.actors.filter((a) => !a.brush).map((a) => a.name)),
    [scene.actors],
  )
  // Narrowed to just the staged names that are ALSO mesh actors -- a Mover is excluded too, since a
  // Mover's own `brush` field is set (it IS brush-derived), so `meshActorNames` never contains one --
  // unverified whether a staged Mover move has the same gap; flagged, not fixed here.
  const meshStagedOffsets = useMemo(() => {
    const out: Record<string, Vec3> = {}
    for (const name of meshActorNames) {
      const staged = stagedOffsets?.[name]
      if (staged) out[name] = staged
    }
    return out
  }, [meshActorNames, stagedOffsets])
  // Every staged mesh actor's own delta -- the single computation `usePatchedMeshPositions` (below,
  // 3 call sites) all read from, rather than each re-deriving it. Perf-critical that this stays
  // O(actor count), not O(level poly count): see this file's own "Perf fix" comment above.
  const meshOwnerDeltas = useMemo(
    () => computeOwnerDeltas(scene.actors, meshStagedOffsets),
    [scene.actors, meshStagedOffsets],
  )

  // Movers always render wireframe-outline-only by default (GUI.md "Movers"), so their solid polys
  // are split OUT of the default geometry into their own built resources -- `Viewport3D` draws
  // `moverGeometry` only when the "Movers: on" toggle is active. `moverNames` comes from the
  // server's authoritative `SceneActor.is_mover` (never re-derived from `cls` -- the client has no
  // class-schema access).
  const moverNames = useMemo(
    () => new Set(scene.actors.filter((a) => a.is_mover).map((a) => a.name)),
    [scene.actors],
  )
  // Built from the level's REAL (unstaged) `scene.polys` -- a staged mesh actor's move reaches this
  // geometry as a live position-buffer PATCH (`usePatchedMeshPositions` below), not by rebuilding it
  // from a translated poly array (this file's own "Perf fix" comment explains why that was the bug).
  // `scene.polys`/`scene.actors` are themselves stable across a drag (only `stagedOffsets` changes
  // per frame), so these two, `useBuiltGeometry`'s own memo, and `meshPolys`/`meshGeoData` below all
  // stay REFERENCE-STABLE for the whole gesture -- none of them re-run per frame any more.
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
  usePatchedMeshPositions(bufferGeometry, triangleOwners, 3, meshActorNames, meshOwnerDeltas)
  const {
    bufferGeometry: moverGeometry,
    materials: moverMaterials,
    unlitMaterials: moverUnlitMaterials,
    triangleOwners: moverTriangleOwners,
    trianglePolyIndex: moverTrianglePolyIndex,
  } = useBuiltGeometry(moverPolys, atlas, lightmap, textures, lightmapTexture)

  // Their solid polys stay in `bufferGeometry`/`materials` above (solid rendering shares the same
  // buffer as brush surfaces, live-patched for a staged mesh move too, per `usePatchedMeshPositions`
  // above); this only builds the WIREFRAME overlay, from the SAME triangle positions
  // `buildGeometryData` already extracts for solid rendering (no UVs/lightmap/materials needed for a
  // plain line overlay).
  const meshPolys = useMemo(
    () => scene.polys.filter((p) => p.owner != null && meshActorNames.has(p.owner)),
    [scene.polys, meshActorNames],
  )
  const meshGeoData = useMemo(() => buildGeometryData(meshPolys, atlas), [meshPolys, atlas])
  // Invisible, raycastable pick mesh for mesh actors in SOLID (non-wireframe) shading modes: a
  // DT_Mesh actor's solid triangles are the only thing that identifies it (it has no brush ring and
  // no marker sprite -- its polys stay in the main geometry). This is the same triangles as
  // `meshWireframeGeometry` below, kept as a real (material-invisible) mesh so the raycast resolves
  // a hit to its owning actor via `meshTriangleOwners` -- mirrors BrushOutlines' dedicated owner-
  // carrying pick geometry. Drawn nowhere visible; only ever raycast. NOT used in wireframe/ortho
  // modes any more -- see `meshEdgePickGeometry` below (GUI-PARITY.md "Mesh selection in 2D/3D
  // wireframe mode vs UED22": UED22 only hit-tests a mesh actor's drawn wireframe EDGES there, never
  // its filled interior, so a filled pick mesh let a click anywhere inside the silhouette wrongly
  // select it).
  //
  // Built once from `meshGeoData` (now stable across a drag); `usePatchedMeshPositions` below
  // live-patches its OWN position buffer for a staged move, same mechanism as the main buffer above,
  // one call site each. `SelectedMeshWireframe` (Viewport3D.tsx/OrthoViewport.tsx) reads this SAME
  // array directly (`meshPickGeometry.attributes.position.array`) to build its own small selected-
  // subset wireframe, so it automatically sees the patched values too -- as long as it re-runs at
  // all, which needs its OWN `stagedOffsets`-keyed trigger, since the array's REFERENCE never
  // changes from an in-place patch (see that component's own doc comment).
  const meshPickGeometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(meshGeoData.positions, 3))
    return g
  }, [meshGeoData])
  usePatchedMeshPositions(meshPickGeometry, meshGeoData.triangleOwners, 3, meshActorNames, meshOwnerDeltas)
  useEffect(() => {
    return () => meshPickGeometry.dispose()
  }, [meshPickGeometry])
  // The VISIBLE wireframe overlay (`MeshWireframe.tsx`) -- rebuilt (not live-patched) whenever
  // `meshOwnerDeltas` changes, unlike the two geometries above. `THREE.WireframeGeometry`'s own edge
  // extraction DEDUPES shared edges between adjacent triangles, discarding per-triangle owner
  // correspondence in the process (confirmed by `MeshWireframe.tsx`'s own `SelectedMeshWireframe`,
  // which already works around exactly this by building its own small geometry from filtered
  // triangles rather than patching the merged wireframe) -- so `usePatchedMeshPositions`' per-vertex
  // range patch can't apply here directly. Rebuilding is still bounded to this level's mesh-actor
  // triangle count alone (via `meshPickGeometry`'s own, already-patched position array, read AFTER
  // it -- source order matters here), never the whole level's geometry, so this keeps the dominant
  // cost this file's "Perf fix" comment describes fixed while accepting a smaller, wireframe-mode-
  // only rebuild cost for the baseline (unselected) mesh wireframe specifically.
  const meshWireframeGeometry = useMemo(() => {
    const trianglesGeo = new THREE.BufferGeometry()
    trianglesGeo.setAttribute(
      'position',
      new THREE.BufferAttribute((meshPickGeometry.attributes.position as THREE.BufferAttribute).array as Float32Array, 3),
    )
    const wire = new THREE.WireframeGeometry(trianglesGeo)
    trianglesGeo.dispose() // only fed WireframeGeometry's own edge extraction, not kept
    return wire
    // meshPickGeometry's own IDENTITY (deps below) doesn't change per staged-move frame (it's built
    // once from meshGeoData) -- reading its position ARRAY here still picks up this render's
    // already-patched values regardless (see the doc comment above on source order), but
    // meshOwnerDeltas is what must actually TRIGGER this memo to re-run on a staged move.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [meshPickGeometry, meshOwnerDeltas])
  useEffect(() => {
    return () => meshWireframeGeometry.dispose()
  }, [meshWireframeGeometry])
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
  // Edges (2 verts/primitive, not 3) -- same live-patch mechanism as the two triangle geometries
  // above, over `meshEdgePickData`'s own per-edge `edgeOwners` (not deduped, so unlike
  // `meshWireframeGeometry` this one CAN be patched directly).
  usePatchedMeshPositions(meshEdgePickGeometry, meshEdgePickData.edgeOwners, 2, meshActorNames, meshOwnerDeltas)
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
