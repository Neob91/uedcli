// Ctrl/Cmd-drag actor-move: tap-vs-drag threshold gating (final-review fix wave, Critical 1).
//
// `dragGesture.ts`'s own tap-vs-drag threshold (`isTap`/`TAP_DRAG_THRESHOLD_PX`) only gates
// `onTap` -- `onDrag` fires on every pointer-move from the very first pixel, unconditionally.
// Viewport3D.tsx/OrthoViewport.tsx wired their Ctrl/Cmd-drag actor-move branch straight off
// `onDrag`, so a Ctrl+click with a few pixels of ordinary jitter (the same gesture this project's
// own Ctrl+click multi-select relies on) both correctly fired the multi-select tap (onTap's own
// threshold check) AND wrongly displaced the actor by that jitter and staged it on release, since
// the move branch never checked the threshold at all.
//
// Fix: accumulate one gesture's own raw pixel delta locally and apply no move until the SAME
// threshold `isTap` already uses is exceeded -- applying the WHOLE pending delta on the exact frame
// that crosses it (not just the remainder past the threshold), so a real drag's first few pixels
// aren't silently dropped once it does cross.
import { isTap } from './selection'

export interface MoveDragAccumulator {
  totalDx: number
  totalDy: number
  started: boolean
}

/** A fresh accumulator for a NEW gesture. Callers must replace (not reuse) their held accumulator
 * with this at the start of every pointerdown -- the tap-vs-drag threshold is per-gesture, not
 * cumulative across separate drags. */
export function freshMoveDragAccumulator(): MoveDragAccumulator {
  return { totalDx: 0, totalDy: 0, started: false }
}

/** Feeds one `onDrag` frame's raw `(dx, dy)` into `acc` (mutated in place, held across frames of
 * one gesture in a ref). Returns `null` while the gesture's cumulative movement is still within the
 * tap threshold -- the caller must apply NO move for this frame (and must not fall through to a
 * camera-move branch either: Ctrl/Cmd is still held, so this is still potentially a multi-select
 * click in progress, per spec.md's "a Ctrl-held pointer-down that stays within the tap threshold is
 * still a multi-select click"). Otherwise returns the delta to actually apply: the gesture's WHOLE
 * accumulated total on the exact frame that crosses the threshold, and just this frame's own
 * `(dx, dy)` on every frame after that (the total up to the crossing point is already reflected in
 * the staged position by then). */
export function accumulateMoveDragFrame(
  acc: MoveDragAccumulator,
  dx: number,
  dy: number,
): { dx: number; dy: number } | null {
  if (acc.started) return { dx, dy }
  acc.totalDx += dx
  acc.totalDy += dy
  if (isTap(0, 0, acc.totalDx, acc.totalDy)) return null
  acc.started = true
  return { dx: acc.totalDx, dy: acc.totalDy }
}
