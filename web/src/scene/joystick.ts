// Pure joystick math (the mobile 3D move joystick, board item
// mobile-3d-move-joystick-visual-design-pending): a drag offset from the stick's center -> a
// clamped analog forward/right direction, fed straight into `camera.ts`'s `flyMove` -- the exact
// same movement WASD already drives (Viewport3D.tsx's FlyKeys), just continuous (-1..1) instead of
// the keyboard's discrete -1/0/1, so partial deflection gives partial speed like a real stick.
export interface JoystickVector {
  forward: number // -1..1, matches flyMove's `input.forward` (W/S)
  right: number // -1..1, matches flyMove's `input.right` (D/A)
}

const ZERO: JoystickVector = { forward: 0, right: 0 }

/** `dx`/`dy` are the drag offset from the stick's center, in the same pixel units as `maxRadius`
 * (the dot's visual travel limit). The raw offset is clamped to the disc of radius `maxRadius`
 * before normalizing, so a drag past the ring's edge still reads as full deflection rather than an
 * out-of-range value. Screen `y` grows downward; forward (matching `W`) is up the screen, so it's
 * the negated, normalized `dy`. */
export function joystickVector(dx: number, dy: number, maxRadius: number): JoystickVector {
  if (maxRadius <= 0) return ZERO
  const dist = Math.hypot(dx, dy)
  if (dist === 0) return ZERO
  const scale = (dist > maxRadius ? maxRadius : dist) / dist
  return { forward: -(dy * scale) / maxRadius, right: (dx * scale) / maxRadius }
}
