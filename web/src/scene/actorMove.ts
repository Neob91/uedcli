// Pure math for Ctrl/Cmd-drag actor movement (spec "Interaction design") -- no three.js/React/DOM
// dependency, testable against known inputs (mirrors camera.ts's/orthoCamera.ts's own style).

import type { Vec3 } from './camera'
import { orthoBasis, type OrthoAxis } from './orthoCamera'

export type MoveAxis = 'x' | 'y' | 'z'

/** Perspective button-combo -> single move axis (spec.md "Resolved at plan time"): LMB=1 -> X,
 * RMB=2 -> Y, LMB+RMB=3 -> Z. Keyed by `PointerEvent.buttons`, matching `Viewport3D.tsx`'s existing
 * camera-gesture dispatch, which keys off the same bitmask. */
export const PERSPECTIVE_AXIS_BY_BUTTONS: Record<number, MoveAxis> = {
  1: 'x',
  2: 'y',
  3: 'z',
}

const AXIS_INDEX: Record<MoveAxis, number> = { x: 0, y: 1, z: 2 }

/** Perspective drag-move: ONE world axis per button combo, using only the drag's horizontal delta
 * (`dx`) -- the vertical delta is unused (owner ruling, spec.md "Interaction design"). Positive dx
 * moves the actor in the axis's positive direction, matching `camera.ts`'s `pan`'s own
 * dx*speed-scaled-along-a-basis-vector convention (screen-right drag = positive along the mapped
 * world direction). */
export function moveAlongAxis(dx: number, axis: MoveAxis, worldUnitsPerPixel: number): Vec3 {
  const delta: Vec3 = [0, 0, 0]
  delta[AXIS_INDEX[axis]] = dx * worldUnitsPerPixel
  return delta
}

/** Ortho drag-move: ONE combo, moves along BOTH of the pane's visible axes at once, using the real
 * `orthoBasis(axis)` vectors (never a hand-rolled 'x'|'y'|'z' pair -- see `orthoCamera.ts`'s own
 * `ORTHO_BASIS` table, the single source of truth for which world direction is "right"/"up" per
 * pane).
 *
 * Sign is DELIBERATELY the same numeric formula as `orthoPan` (`right*dx*wupp + up*-dy*wupp`) but
 * with the OPPOSITE real-world effect, because it is applied to a different quantity.
 * `orthoPan` adds this delta to the CAMERA's center: moving the camera's reference frame by +delta
 * makes a world-fixed point's on-screen position shift by -delta (its own doc comment: "a
 * world-fixed point already on screen therefore appears to slide OPPOSITE the drag" -- correct for
 * panning the view). `moveInPlane` instead adds this SAME delta directly to the ACTOR's own world
 * position, with the camera held fixed -- so the actor's on-screen position shifts by +delta, i.e.
 * WITH the drag (the actor visually follows the cursor, correct for "grab this actor and move it").
 * Pinned by `actorMove.test.ts`'s dot-product-positive assertions against `orthoBasis`'s own
 * vectors, verified in-app per the task's own Step 5 ground truth (dragging right moves the actor
 * right on screen). */
export function moveInPlane(dx: number, dy: number, axis: OrthoAxis, worldUnitsPerPixel: number): Vec3 {
  const { right, up } = orthoBasis(axis)
  const delta: Vec3 = [0, 0, 0]
  for (let i = 0; i < 3; i++) {
    delta[i] = right[i] * dx * worldUnitsPerPixel - up[i] * dy * worldUnitsPerPixel
  }
  return delta
}
