// Whether this session can receive touch input at all -- gates touch-only UI (the mobile 3D move
// joystick + up/down buttons, board item mobile-3d-move-joystick-visual-design-pending). Unlike
// `useCollapsiblePanel.ts`'s viewport-width breakpoint (a RESPONSIVE default for narrow windows),
// this is a CAPABILITY check: a touch-capable laptop with a keyboard still gets the touch control
// (the board item's own constraint), so window width is the wrong signal. Feature-detected, never
// UA-sniffed -- the two standard capability signals a real touch device exposes, checked here since
// there's no per-event `pointerType` (the convention Viewport3D.tsx/OrthoViewport.tsx already use
// for handling touch) available before anything has been drawn yet.
//
// Mirrors `useCollapsiblePanel.ts`'s split: a pure, unit-testable resolver plus a thin impure
// wrapper that reads the real globals -- the resolver is what's tested (`resolveTouchCapable`), same
// as that file's `resolveCollapsed`.
export function resolveTouchCapable(hasOntouchstart: boolean, maxTouchPoints: number): boolean {
  return hasOntouchstart || maxTouchPoints > 0
}

export function isTouchCapableDevice(): boolean {
  if (typeof window === 'undefined') return false
  return resolveTouchCapable('ontouchstart' in window, navigator.maxTouchPoints ?? 0)
}
