// Fallback markers for pure point actors -- lights, triggers, patrol nodes, sounds, or a DT_Mesh
// actor whose mesh never resolved/rendered -- drawn when the actor's `DT_Sprite` billboard didn't
// resolve (`SceneActor.sprite` null; Viewport3D.tsx draws the real icon texture instead when it
// did). These have no brush and own no polys in `ScenePayload.polys`, so without a marker nothing
// draws them and nothing is there for a raycast to hit. Pure geometry/colour logic; Viewport3D.tsx
// wires the result into a second raycastable mesh alongside the main scene geometry.
import type { SceneActor } from '../api'

/** Fallback marker colour when a point actor's `DT_Sprite` billboard doesn't resolve: a fixed
 * neutral grey, matching `uedcli/preview.py`'s `MARKER = (185, 185, 185)` -- deliberately NOT a
 * per-class hue (that was this module's own invented palette; the owner wants the actor's REAL
 * sprite icon, and a plain grey dot -- never a colour guess -- when there isn't one). 0..1 RGB,
 * this codebase's convention for a `THREE.Color` triple (e.g. the class palette this replaces). */
export const MARKER_COLOR: [number, number, number] = [185 / 255, 185 / 255, 185 / 255]

/** Actors needing a fallback marker: no brush (not a CSG actor -- brush picking/highlight is a
 * separate, already-working path) and no owned rendered poly (`ownedNames`, the distinct non-null
 * `ScenePoly.owner`s already present in the built scene geometry -- a mesh actor that resolved and
 * rendered is excluded, matching the spec's "real mesh, else a marker" priority). */
export function actorsNeedingMarkers(actors: SceneActor[], ownedNames: ReadonlySet<string>): SceneActor[] {
  return actors.filter((a) => !a.brush && !ownedNames.has(a.name))
}
