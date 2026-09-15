// Click-to-select picking. The PRIMARY path (`resolveHitActor`) raycasts the actual rendered
// geometry (the merged bufferGeometry Viewport3D.tsx builds from `scene.polys`) and maps the hit
// triangle back to its owning actor via `ScenePoly.owner` -- real per-poly ownership, so a small
// brush fully enclosed in a bigger brush's bounding box is still selectable by its OWN geometry.
// `pickActor` (ray-vs-actor-AABB) is the FALLBACK for a tap that doesn't land on any drawn
// triangle -- the only way to select a non-brush point actor (no geometry of its own, out of scope
// here) today, so it must keep working exactly as before. Pure and framework-free (the
// screen-to-ray conversion, which needs the real camera projection, lives in Viewport3D.tsx via
// three.js's Raycaster; only the picking algorithm itself is here, so it's testable without a
// WebGL context).
import type { SceneActor } from '../api'
import type { Vec3 } from './camera'
import type { ShadingMode } from './shadingMode'

/** Resolves a raycast hit on the merged scene geometry to its owning actor: `faceIndex` is
 * `THREE.Intersection.faceIndex` (a triangle index into the non-indexed geometry, so it indexes
 * `triangleOwners` directly -- `geometry.ts`'s `buildGeometryData` emits one owner entry per
 * triangle in the SAME order). Returns null when there was no hit, the hit triangle has no
 * resolved owner (an out-of-range CSG join), or the name doesn't match any actor in the current
 * payload (a live-reload race). */
export function resolveHitActor(
  faceIndex: number | null | undefined,
  triangleOwners: (string | null)[],
  actors: SceneActor[],
): SceneActor | null {
  if (faceIndex == null) return null
  const name = triangleOwners[faceIndex]
  if (name == null) return null
  return actors.find((a) => a.name === name) ?? null
}

/** Resolves a raycast hit on `BrushOutlines`' merged thin-wireframe `LineSegments` (bug report item
 * 4/6) to its owning actor: `index` is `THREE.Intersection.index` -- for a `LineSegments` hit,
 * three.js's own `Line.raycast` sets it to the segment's FIRST vertex index, so `index / 2` is the
 * segment number, indexing `segmentOwners` directly (`brushRings.ts`'s `mergeThinRings`, one owner
 * per 2-vertex segment, same per-index-array shape as `resolveHitActor`'s `triangleOwners`). */
export function resolveSegmentHitActor(
  index: number | null | undefined,
  segmentOwners: (string | null)[],
  actors: SceneActor[],
): SceneActor | null {
  if (index == null) return null
  const name = segmentOwners[Math.floor(index / 2)]
  if (name == null) return null
  return actors.find((a) => a.name === name) ?? null
}

/** The tap-resolution decision Viewport3D/OrthoViewport's `performTapSelect` both make once they've
 * found (or not found) a hit actor (quad-layout Part 3, Task 13): a real hit calls `onSelectActor`
 * with the actor's name and the `additive` flag threaded through from the drag gesture's Ctrl/Cmd
 * state; a MISS is a true no-op (spec §9's deliberate behavior change -- a tap that hits nothing no
 * longer clears the selection, `Esc` is the only deselect path). Pulled out as a pure, tiny function
 * so this exact decision is testable without a WebGL raycast. */
export function resolveTapSelection(
  hitActor: SceneActor | null,
  additive: boolean,
): { name: string; additive: boolean } | null {
  return hitActor ? { name: hitActor.name, additive } : null
}

export interface Ray {
  origin: Vec3
  direction: Vec3
}

/** Ray-vs-AABB slab test. Returns the entry distance (clamped to >= 0 for a ray starting inside
 * the box), or null if the ray misses. */
export function rayAabbIntersect(ray: Ray, lo: Vec3, hi: Vec3): number | null {
  let tmin = -Infinity
  let tmax = Infinity
  for (let i = 0; i < 3; i++) {
    const o = ray.origin[i]
    const d = ray.direction[i]
    if (Math.abs(d) < 1e-12) {
      if (o < lo[i] || o > hi[i]) return null
      continue
    }
    let t1 = (lo[i] - o) / d
    let t2 = (hi[i] - o) / d
    if (t1 > t2) [t1, t2] = [t2, t1]
    tmin = Math.max(tmin, t1)
    tmax = Math.min(tmax, t2)
    if (tmin > tmax) return null
  }
  if (tmax < 0) return null
  return Math.max(tmin, 0)
}

/** The actor whose bbox the ray hits first (closest positive-t AABB hit), or null if the ray
 * misses every actor. */
export function pickActor(ray: Ray, actors: SceneActor[]): SceneActor | null {
  let best: SceneActor | null = null
  let bestT = Infinity
  for (const actor of actors) {
    const t = rayAabbIntersect(ray, actor.bbox_lo, actor.bbox_hi)
    if (t !== null && t < bestT) {
      bestT = t
      best = actor
    }
  }
  return best
}

/** This is SHADING-MODE-gated (wireframe vs. non-wireframe), not viewport-gated -- corrected owner
 * ruling 2026-09-15 (an earlier pass had this backwards as 3D-vs-2D). In wireframe mode -- the 2D
 * ortho panes are always wireframe, and the 3D perspective pane can be too -- a plain LMB tap
 * selects a brush directly, matching how a point actor is always plain-tap-selectable. In a
 * NON-wireframe shading mode (only possible in the 3D perspective pane: `unlit`/`flat`/`lit`), a
 * plain LMB-drag is camera-fly (dolly+turn), so a tap landing on a brush is ambiguous with an
 * incidental camera nudge -- Shift+LMB is the disambiguator there. */
export function canSelectBrushTap(mode: ShadingMode, shiftKey: boolean): boolean {
  return mode === 'wireframe' || shiftKey
}

export const TAP_DRAG_THRESHOLD_PX = 4

/** Was a pointer-down/up pair a TAP (click-to-select) or a DRAG (camera fly)? A tap is one whose
 * total on-screen travel stayed within `thresholdPx` -- the gate between LMB's two dual-purpose
 * behaviors (spec, "Selection & inspector": "LMB tap ... below the camera-fly drag threshold"). */
export function isTap(
  startX: number,
  startY: number,
  endX: number,
  endY: number,
  thresholdPx: number = TAP_DRAG_THRESHOLD_PX,
): boolean {
  return Math.hypot(endX - startX, endY - startY) <= thresholdPx
}
