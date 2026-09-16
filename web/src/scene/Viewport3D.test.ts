import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import { cameraBasis } from './camera'
import type { CameraPose } from './camera'
import { applyCameraPose, WIREFRAME_LINE_HIT_WORLD_UNITS } from './Viewport3D'

// Widened hit-test tolerance (owner report, live testing: brush-outline selection in wireframe mode
// needed near-pixel-exact clicks) -- pins the value so a future edit can't silently narrow it back.
describe('WIREFRAME_LINE_HIT_WORLD_UNITS', () => {
  it('is wider than the original 4-world-unit threshold', () => {
    expect(WIREFRAME_LINE_HIT_WORLD_UNITS).toBe(8)
  })
})

// Pins the mirror fix (owner bug report: "meshes render reverted (mirror image)") against real
// three.js math -- no WebGL context needed, `Vector3.project` is pure matrix arithmetic. The world
// is left-handed (X forward, Y right, Z up) fed verbatim into three.js's right-handed renderer, so
// a correct camera must render a point offset toward `cameraBasis.right` on the RIGHT of the screen
// (positive NDC.x) and a point offset toward `up` toward the TOP (positive NDC.y) -- verified
// against a fresh `level photo --native` (render.rs) of the same poses during this fix.
// `depthAlongForward` keeps the projected point safely in front of the camera (real screen content
// always has forward depth; an offset purely perpendicular to `forward` sits exactly at the camera,
// an degenerate zero-depth case `Vector3.project` can't handle) -- only `right`/`up` decide which
// half of the screen it lands in.
function projectRelative(pose: CameraPose, sideOffset: [number, number, number]): THREE.Vector3 {
  const camera = new THREE.PerspectiveCamera(75, 1, 1, 131072)
  applyCameraPose(camera, pose)
  const { forward } = cameraBasis(pose.pitch, pose.yaw)
  const depthAlongForward = 500
  const point = new THREE.Vector3(
    pose.position[0] + forward[0] * depthAlongForward + sideOffset[0],
    pose.position[1] + forward[1] * depthAlongForward + sideOffset[1],
    pose.position[2] + forward[2] * depthAlongForward + sideOffset[2],
  )
  return point.project(camera)
}

describe('applyCameraPose', () => {
  it('renders a point offset toward cameraBasis.right on the right of the screen (positive NDC.x)', () => {
    const poses: CameraPose[] = [
      { position: [0, 0, 0], pitch: 0, yaw: 0 },
      { position: [0, -500, 200], pitch: -10, yaw: 90 },
      { position: [-300, 50, 700], pitch: -75, yaw: 0 }, // the near-top-down pose the bug/fix was pinned against
    ]
    for (const pose of poses) {
      const { right } = cameraBasis(pose.pitch, pose.yaw)
      const ndc = projectRelative(pose, [right[0] * 350, right[1] * 350, right[2] * 350])
      expect(ndc.x).toBeGreaterThan(0)
    }
  })

  it('renders a point offset toward cameraBasis.up higher on the screen (positive NDC.y)', () => {
    const poses: CameraPose[] = [
      { position: [0, 0, 0], pitch: 0, yaw: 0 },
      { position: [0, -500, 200], pitch: -10, yaw: 90 },
    ]
    for (const pose of poses) {
      const { up } = cameraBasis(pose.pitch, pose.yaw)
      const ndc = projectRelative(pose, [up[0] * 350, up[1] * 350, up[2] * 350])
      expect(ndc.y).toBeGreaterThan(0)
    }
  })

  it('looks along cameraBasis.forward (never flips the view direction itself)', () => {
    const pose: CameraPose = { position: [-300, 50, 700], pitch: -75, yaw: 0 }
    const camera = new THREE.PerspectiveCamera(75, 1, 1, 131072)
    applyCameraPose(camera, pose)
    const { forward } = cameraBasis(pose.pitch, pose.yaw)
    const lookDir = new THREE.Vector3(0, 0, -1).transformDirection(camera.matrixWorld)
    expect(lookDir.x).toBeCloseTo(forward[0], 5)
    expect(lookDir.y).toBeCloseTo(forward[1], 5)
    expect(lookDir.z).toBeCloseTo(forward[2], 5)
  })
})
