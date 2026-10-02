// Fallback markers for pure point actors -- lights, triggers, patrol nodes, sounds, or a DT_Mesh
// actor whose mesh never resolved/rendered -- drawn when the actor's `DT_Sprite` billboard didn't
// resolve (`SceneActor.sprite` null; Viewport3D.tsx draws the real icon texture instead when it
// did). These have no brush and own no polys in `ScenePayload.polys`, so without a marker nothing
// draws them and nothing is there for a raycast to hit. Pure geometry/colour logic; Viewport3D.tsx
// wires the result into a second raycastable mesh alongside the main scene geometry.
import * as THREE from 'three'

import type { SceneActor } from '../api'

// Board `selected-surface-highlight-renders-above-point`: a selected surface's translucent overlay
// (`SelectionHighlight.tsx`'s `SurfaceSelectionHighlight`) rendered on top of a point-actor sprite
// genuinely closer to the camera. Both are `transparent` objects with the default `renderOrder` (0),
// and three.js's transparent-pass sort only falls back to distance-from-camera once `renderOrder`
// ties -- and that distance is each object's own `matrixWorld` origin, meaningless for the highlight
// mesh (it never sets a `.position`; its triangles live only in a shared-attribute index subset).
// Both `Viewport3D.tsx` and `OrthoViewport.tsx` pass this to every `PointActorMarker`/marker sprite
// so a marker always composites after a coincident-depth highlight, sidestepping that tiebreak
// entirely (checked before distance). `depthTest` is untouched -- this only fixes draw order among
// coincident-depth translucent overlays, not sprite-vs-wall occlusion.
export const MARKER_RENDER_ORDER = 10

/** World units per screen pixel at `point`, for either camera kind this app uses -- the constant-
 * screen-size scale factor a marker/gizmo sprite needs to stay a fixed size on screen regardless of
 * zoom (ortho) or camera distance (perspective, where a fixed WORLD-unit sprite shrinks with
 * distance via ordinary foreshortening). Ortho: the frustum height / zoom is already
 * screen-independent of `point`. Perspective: depends on distance to `point`, the standard
 * vFOV-based sprite-scale-compensation formula. Shared by `SelectionMarkers.tsx`'s pivot gizmo and
 * `PointActorMarker` below -- point-actor markers used a FIXED world-unit scale until now, which
 * shrinks to sub-pixel size at ordinary level-viewing distances (owner report: "point actors not
 * rendering"). */
export function worldUnitsPerPixelAt(camera: THREE.Camera, point: THREE.Vector3, viewportHeightPx: number): number {
  if (camera instanceof THREE.OrthographicCamera) {
    return (camera.top - camera.bottom) / camera.zoom / viewportHeightPx
  }
  if (camera instanceof THREE.PerspectiveCamera) {
    const distance = camera.position.distanceTo(point)
    const vFOV = THREE.MathUtils.degToRad(camera.fov)
    return (2 * Math.tan(vFOV / 2) * distance) / viewportHeightPx
  }
  return 1
}

/** Fallback marker colour when a point actor's `DT_Sprite` billboard doesn't resolve: a fixed
 * neutral grey, matching `uedcli/preview.py`'s `MARKER = (185, 185, 185)` -- deliberately NOT a
 * per-class hue (that was this module's own invented palette; the owner wants the actor's REAL
 * sprite icon, and a plain grey dot -- never a colour guess -- when there isn't one). 0..1 RGB,
 * this codebase's convention for a `THREE.Color` triple (e.g. the class palette this replaces). */
export const MARKER_COLOR: [number, number, number] = [185 / 255, 185 / 255, 185 / 255]

// Fallback marker world-space footprint (UU), used only when an actor has no resolved DT_Sprite (the
// grey dot). A resolved icon uses its own real `ActorSprite.width/height` (DrawScale x texel size)
// instead. 32 UU square mirrors UnrealEd's generic S_Actor icon (32x32 texels at DrawScale 1). Unlike
// the pivot GIZMO (`SelectionMarkers.tsx`, deliberately constant screen size), a point-actor marker
// is a real DT_Sprite billboard with a fixed WORLD footprint, so it foreshortens with distance/zoom
// like ordinary geometry -- UED22 parity.
export const DEFAULT_MARKER_FOOTPRINT_UU = 32

/** Actors needing a fallback marker: no brush (not a CSG actor -- brush picking/highlight is a
 * separate, already-working path) and no owned rendered poly (`ownedNames`, the distinct non-null
 * `ScenePoly.owner`s already present in the built scene geometry -- a mesh actor that resolved and
 * rendered is excluded, matching the spec's "real mesh, else a marker" priority). */
export function actorsNeedingMarkers(actors: SceneActor[], ownedNames: ReadonlySet<string>): SceneActor[] {
  return actors.filter((a) => !a.brush && !ownedNames.has(a.name))
}
