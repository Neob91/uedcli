// Pure two-finger touch-gesture math: turns two touch points' before/after screen positions into
// the screen-space deltas `camera.ts`'s `pan`/`zoom` already expect, so Viewport3D.tsx can feed a
// touch drag straight into those unchanged functions. No DOM/three.js dependency, same testability
// as camera.ts.
export interface TouchPoint {
  x: number
  y: number
}

export interface TwoFingerDelta {
  panDx: number
  panDy: number
  // Wheel-delta-shaped, ready for `zoom()`: fingers spreading apart (distance increasing) is
  // negative, matching a scroll-up wheel delta (zoom in); pinching together is positive (zoom out).
  zoomDelta: number
}

/** Midpoint movement between `before` and `after` (pan) + separation-distance change (pinch-zoom). */
export function computeTwoFingerDelta(
  before: [TouchPoint, TouchPoint],
  after: [TouchPoint, TouchPoint],
): TwoFingerDelta {
  const midBefore = { x: (before[0].x + before[1].x) / 2, y: (before[0].y + before[1].y) / 2 }
  const midAfter = { x: (after[0].x + after[1].x) / 2, y: (after[0].y + after[1].y) / 2 }
  const distBefore = Math.hypot(before[0].x - before[1].x, before[0].y - before[1].y)
  const distAfter = Math.hypot(after[0].x - after[1].x, after[0].y - after[1].y)
  return {
    panDx: midAfter.x - midBefore.x,
    panDy: midAfter.y - midBefore.y,
    zoomDelta: -(distAfter - distBefore),
  }
}
