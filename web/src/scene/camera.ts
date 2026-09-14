// Faithful UnrealEd 1.x drag-fly perspective camera (spec, "Camera"). Pure transform math, no
// three.js/react-three-fiber dependency, so it's testable against known inputs without a
// renderer. World convention: Z-up, matching the backend's actor location tuples (x, y, z).
//
// LMB-drag = dolly forward/back (vertical drag) + turn/yaw (horizontal drag).
// RMB-drag = look in place (pitch + yaw), position fixed.
// LMB+RMB-drag = pan (strafe + vertical), no rotation.
// Scroll = zoom (dolly along the forward vector).
// Alt-drag = orbit around a pivot (the selection), re-aiming at it.

export type Vec3 = [number, number, number]

export interface CameraPose {
  position: Vec3
  pitch: number // degrees, clamped to [-MAX_PITCH, MAX_PITCH]
  yaw: number // degrees, wrapped to [0, 360)
}

export interface CameraSpeeds {
  yawPerPixel: number
  pitchPerPixel: number
  dollyPerPixel: number
  panPerPixel: number
  zoomPerWheelUnit: number
}

export const DEFAULT_SPEEDS: CameraSpeeds = {
  yawPerPixel: 0.25,
  pitchPerPixel: 0.25,
  dollyPerPixel: 1.0,
  panPerPixel: 1.0,
  zoomPerWheelUnit: 1.0,
}

const DEG2RAD = Math.PI / 180
const RAD2DEG = 180 / Math.PI
const MAX_PITCH = 89

function clampPitch(pitch: number): number {
  return Math.max(-MAX_PITCH, Math.min(MAX_PITCH, pitch))
}

function wrapYaw(yaw: number): number {
  return ((yaw % 360) + 360) % 360
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
}

function addScaled(v: Vec3, dir: Vec3, s: number): Vec3 {
  return [v[0] + dir[0] * s, v[1] + dir[1] * s, v[2] + dir[2] * s]
}

/** (forward, right, up) world basis for a (pitch, yaw) pose. Z-up: at pitch=0, yaw=0, forward is
 * +X, right is +Y, up is +Z. */
export function cameraBasis(pitch: number, yaw: number): { forward: Vec3; right: Vec3; up: Vec3 } {
  const p = pitch * DEG2RAD
  const y = yaw * DEG2RAD
  const forward: Vec3 = [Math.cos(p) * Math.cos(y), Math.cos(p) * Math.sin(y), Math.sin(p)]
  const right: Vec3 = [-Math.sin(y), Math.cos(y), 0]
  const up = cross(forward, right)
  return { forward, right, up }
}

/** LMB-drag: move forward/back in the HORIZONTAL plane (vertical drag) + turn/yaw (horizontal drag).
 * Movement is along the yaw direction projected onto XY (`[cos(yaw), sin(yaw), 0]`), NEVER Z, so a
 * pitched camera still "walks" level along the ground (classic UnrealEd; Z is LMB+RMB's job). */
export function dollyAndTurn(
  pose: CameraPose,
  dx: number,
  dy: number,
  speeds: CameraSpeeds = DEFAULT_SPEEDS,
): CameraPose {
  const yaw = wrapYaw(pose.yaw - dx * speeds.yawPerPixel)
  const y = yaw * DEG2RAD
  const horizForward: Vec3 = [Math.cos(y), Math.sin(y), 0]
  const position = addScaled(pose.position, horizForward, -dy * speeds.dollyPerPixel)
  return { position, pitch: pose.pitch, yaw }
}

/** RMB-drag: look in place -- pitch/yaw change, position fixed. */
export function look(
  pose: CameraPose,
  dx: number,
  dy: number,
  speeds: CameraSpeeds = DEFAULT_SPEEDS,
): CameraPose {
  const yaw = wrapYaw(pose.yaw - dx * speeds.yawPerPixel)
  const pitch = clampPitch(pose.pitch - dy * speeds.pitchPerPixel)
  return { position: pose.position, pitch, yaw }
}

/** LMB+RMB-drag: pan -- strafe in XY (horizontal drag) + move along world Z (vertical drag), no
 * rotation. Vertical is pure world-up so LMB+RMB is the ONE gesture that changes Z (`right` is always
 * horizontal, so strafe never leaks Z either). */
export function pan(
  pose: CameraPose,
  dx: number,
  dy: number,
  speeds: CameraSpeeds = DEFAULT_SPEEDS,
): CameraPose {
  const { right } = cameraBasis(pose.pitch, pose.yaw)
  const worldUp: Vec3 = [0, 0, 1]
  let position = addScaled(pose.position, right, dx * speeds.panPerPixel)
  position = addScaled(position, worldUp, -dy * speeds.panPerPixel)
  return { position, pitch: pose.pitch, yaw: pose.yaw }
}

/** Scroll-wheel zoom: dolly along the forward vector. */
export function zoom(
  pose: CameraPose,
  wheelDeltaY: number,
  speeds: CameraSpeeds = DEFAULT_SPEEDS,
): CameraPose {
  const { forward } = cameraBasis(pose.pitch, pose.yaw)
  const position = addScaled(pose.position, forward, -wheelDeltaY * speeds.zoomPerWheelUnit)
  return { position, pitch: pose.pitch, yaw: pose.yaw }
}

/** Alt-drag: orbit the camera around `pivot` (the selection), keeping its distance from the pivot
 * fixed and re-aiming pitch/yaw at the pivot after the rotation. A near-zero-radius pivot (camera
 * already at the pivot) is a no-op -- there is no orbit direction to rotate. */
export function orbit(
  pose: CameraPose,
  pivot: Vec3,
  dx: number,
  dy: number,
  speeds: CameraSpeeds = DEFAULT_SPEEDS,
): CameraPose {
  const offset: Vec3 = [
    pose.position[0] - pivot[0],
    pose.position[1] - pivot[1],
    pose.position[2] - pivot[2],
  ]
  const radius = Math.hypot(offset[0], offset[1], offset[2])
  if (radius < 1e-6) return pose

  let orbitYaw = Math.atan2(offset[1], offset[0]) * RAD2DEG
  let orbitPitch = Math.asin(Math.max(-1, Math.min(1, offset[2] / radius))) * RAD2DEG
  orbitYaw = wrapYaw(orbitYaw - dx * speeds.yawPerPixel)
  orbitPitch = clampPitch(orbitPitch - dy * speeds.pitchPerPixel)

  const { forward } = cameraBasis(orbitPitch, orbitYaw)
  const position: Vec3 = [
    pivot[0] + forward[0] * radius,
    pivot[1] + forward[1] * radius,
    pivot[2] + forward[2] * radius,
  ]
  // Face back toward the pivot: camera forward = -offsetDirection = forward(-orbitPitch, orbitYaw + 180).
  return { position, pitch: -orbitPitch, yaw: wrapYaw(orbitYaw + 180) }
}
