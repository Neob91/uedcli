// Click-to-select picking: ray-vs-actor-AABB, nearest hit wins. Pure and framework-free (the
// screen-to-ray conversion, which needs the real camera projection, lives in Viewport3D.tsx via
// three.js's Raycaster; only the picking algorithm itself is here, so it's testable without a
// WebGL context). Slice 1 selects at actor-bbox granularity, not per-poly -- the scene payload's
// polys carry no owning-actor reference (they're anonymous CSG-solved fragments), so bbox
// hit-testing against `ScenePayload.actors` is what's available without a backend change.
import type { SceneActor } from '../api'
import type { Vec3 } from './camera'

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
