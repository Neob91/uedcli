// Move-mode toggle (viewport-control-redesign-icon-cluster-replaces spec, "Move-mode toggle"): a
// single 2-state toggle shared by desktop and touch, deliberately NOT per-platform (unlike
// inputMode.ts's per-device persistence) -- a hybrid touchscreen+mouse user gets one consistent
// remembered choice, not two. What each state means differs by platform; see camera.ts's
// `resolveDrag` (desktop) / `resolveTwoFingerDrag` (touch).
export type MoveMode = 'fly' | 'pan'

export function cycleMoveMode(current: MoveMode): MoveMode {
  return current === 'fly' ? 'pan' : 'fly'
}
