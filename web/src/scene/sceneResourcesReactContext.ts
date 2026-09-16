// The raw React context object + its value type, split out of SceneResourcesContext.tsx /
// useSceneResourcesContext.ts so neither of THOSE files mixes a component/hook export with a plain
// value export -- Vite's react-refresh plugin can't Fast Refresh a file that does both ("X export is
// incompatible"), which silently wedges a pane (a stale module graph crashes on the next re-render,
// e.g. "useSceneResourcesContext() called outside a <SceneResourcesProvider>") until a full page
// reload. This file exports no component and no hook, so it's not a Fast Refresh boundary at all.
import { createContext } from 'react'
import * as THREE from 'three'

import type { SceneActor } from '../api'

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

export const SceneResourcesReactContext = createContext<SceneResources | null>(null)
