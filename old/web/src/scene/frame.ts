// The union world-space AABB of a set of actors (quad-layout Part 3, Task 15) -- the shared framing
// mechanism `F` (Perspective/ortho camera framing) and the org panel's folder-node selection (Part
// 6) both reuse, rather than each inventing its own.
import type { SceneActor } from '../api'
import type { Vec3 } from './camera'

export interface BBox {
  lo: Vec3
  hi: Vec3
}

/** One `F`-triggered framing request (QuadLayout's own state, Task 15): `seq` is a monotonic counter
 * so a pane's `useEffect` can tell "frame again" apart from "no new request" even when the bbox
 * itself is byte-identical to the last one (e.g. pressing `F` twice on the same selection). */
export interface FrameRequest {
  bbox: BBox
  seq: number
}

/** The union AABB of every actor's own `bbox_lo`/`bbox_hi` -- `null` for an empty set (nothing to
 * frame). */
export function unionBBox(actors: SceneActor[]): BBox | null {
  if (actors.length === 0) return null
  const lo: Vec3 = [...actors[0].bbox_lo]
  const hi: Vec3 = [...actors[0].bbox_hi]
  for (const actor of actors.slice(1)) {
    for (let i = 0; i < 3; i++) {
      lo[i] = Math.min(lo[i], actor.bbox_lo[i])
      hi[i] = Math.max(hi[i], actor.bbox_hi[i])
    }
  }
  return { lo, hi }
}

/** The bbox's world-space center. */
export function bboxCenter(box: BBox): Vec3 {
  return [(box.lo[0] + box.hi[0]) / 2, (box.lo[1] + box.hi[1]) / 2, (box.lo[2] + box.hi[2]) / 2]
}

/** The bbox's largest axis extent (its "size" for a camera-distance/zoom-to-fit calculation),
 * floored at 1 UU so a degenerate (point-actor-only) selection still gets a sane, non-zero frame. */
export function bboxMaxExtent(box: BBox): number {
  return Math.max(box.hi[0] - box.lo[0], box.hi[1] - box.lo[1], box.hi[2] - box.lo[2], 1)
}
