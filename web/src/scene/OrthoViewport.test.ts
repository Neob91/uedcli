import { describe, expect, it } from 'vitest'
import * as THREE from 'three'

import { applyOrthoCameraPose } from './viewportRender'
import { orthoBasis, orthoPan } from './orthoCamera'
import type { OrthoAxis, OrthoPose } from './orthoCamera'

// Regression for the Front/Side blank-pane bug (owner report, live browser + headless repro):
// `OrthoCameraRig` used to build its rotation via `Matrix4.makeBasis(right, up, -forward)`, which
// is an IMPROPER matrix (determinant -1) for all three axes -- a consequence of this world being
// left-handed (see `Viewport3D.tsx`'s `applyCameraPose` doc comment, which already predicted this
// failure mode for this exact pattern). `THREE.Quaternion.setFromRotationMatrix` silently
// mis-decomposes an improper matrix; for `front`/`side` this pointed the camera along a completely
// wrong axis (nothing in the scene ever entered the frustum -- blank pane), while `top` happened to
// end up pointing the right way (just upside-down), which is why only front/side looked broken.
//
// The fix mirrors `Viewport3D.tsx`'s existing technique: build the rotation via `camera.up` +
// `lookAt` (always a proper, valid rotation), then mirror the projection matrix's NDC-x term to
// restore the intended screen-right (`lookAt` derives screen-right as `cross(up, forward)`, the
// exact negation of `orthoBasis.right` for all three axes here).
function projectRelative(pose: OrthoPose, axis: OrthoAxis, offset: [number, number, number]): THREE.Vector3 {
  const camera = new THREE.OrthographicCamera()
  applyOrthoCameraPose(camera, pose, axis, { width: 100, height: 100 })
  // Content is drawn inside a reflected `<group scale={[1,-1,1]}>` and the camera pose is reflected by
  // the same R = diag(1,-1,1), so a game-coord point appears at the projection of R*point (negate Y).
  const point = new THREE.Vector3(pose.center[0] + offset[0], -(pose.center[1] + offset[1]), pose.center[2] + offset[2])
  return point.project(camera)
}

const AXES: OrthoAxis[] = ['top', 'front', 'side']
const POSE: OrthoPose = { center: [10, -20, 30], worldUnitsPerPixel: 1 }

describe('applyOrthoCameraPose', () => {
  it('looks along orthoBasis(axis).forward for every axis (never a wrong axis entirely)', () => {
    for (const axis of AXES) {
      const camera = new THREE.OrthographicCamera()
      applyOrthoCameraPose(camera, POSE, axis, { width: 100, height: 100 })
      const { forward } = orthoBasis(axis)
      const lookDir = new THREE.Vector3(0, 0, -1).transformDirection(camera.matrixWorld)
      // Camera posed in reflected space: looks along R*forward = (fx, -fy, fz).
      expect(lookDir.x).toBeCloseTo(forward[0], 5)
      expect(lookDir.y).toBeCloseTo(-forward[1], 5)
      expect(lookDir.z).toBeCloseTo(forward[2], 5)
    }
  })

  it('renders a point offset toward orthoBasis(axis).right on the right of the screen (positive NDC.x)', () => {
    for (const axis of AXES) {
      const { right } = orthoBasis(axis)
      const ndc = projectRelative(POSE, axis, [right[0] * 10, right[1] * 10, right[2] * 10])
      expect(ndc.x).toBeGreaterThan(0)
    }
  })

  it('renders a point offset toward orthoBasis(axis).up higher on the screen (positive NDC.y)', () => {
    for (const axis of AXES) {
      const { up } = orthoBasis(axis)
      const ndc = projectRelative(POSE, axis, [up[0] * 10, up[1] * 10, up[2] * 10])
      expect(ndc.y).toBeGreaterThan(0)
    }
  })

  it('keeps the scene inside the frustum -- a point at pose.center always projects near NDC origin', () => {
    // The actual "blank pane" symptom: for front/side, the pre-fix camera pointed so far off-axis
    // that pose.center itself (dead-center of the intended view) could project way outside [-1, 1]
    // or behind the camera entirely.
    for (const axis of AXES) {
      const ndc = projectRelative(POSE, axis, [0, 0, 0])
      expect(Math.abs(ndc.x)).toBeLessThan(1e-6)
      expect(Math.abs(ndc.y)).toBeLessThan(1e-6)
    }
  })
})

// Regression for the owner-reported "ortho drag-pan is inverted" bug report: proves `orthoPan`'s
// "content follows the cursor" contract (its own doc comment, GUI.md's "Camera & projection") holds
// through the FULL render pipeline -- camera.lookAt + the NDC-x projection mirror above -- not just
// `orthoCamera.ts`'s pure math in isolation. A fixed world point's on-screen (canvas-pixel, y-down)
// position must move by exactly the same (dxPx, dyPx) the drag itself moved, for every axis, since a
// sign error in either `orthoPan` or the projection mirror they share would show up here even if
// `orthoCamera.test.ts`'s own `orthoPan` tests (which only check `pose.center`'s arithmetic, not the
// screen effect) still passed.
function screenPxOf(pose: OrthoPose, axis: OrthoAxis, worldPoint: [number, number, number], viewportPx: { width: number; height: number }) {
  const camera = new THREE.OrthographicCamera()
  applyOrthoCameraPose(camera, pose, axis, viewportPx)
  // Reflect the world point by R = diag(1,-1,1) (the content group's reflection) before projecting.
  const ndc = new THREE.Vector3(worldPoint[0], -worldPoint[1], worldPoint[2]).project(camera)
  return { x: ((ndc.x + 1) / 2) * viewportPx.width, y: ((1 - ndc.y) / 2) * viewportPx.height }
}

describe('orthoPan (rendered)', () => {
  it('a screen-space drag moves a fixed world point by the OPPOSITE screen delta (the view moves WITH the drag), for every axis', () => {
    const viewportPx = { width: 800, height: 600 }
    const worldPoint: [number, number, number] = [3, -4, 5]
    const dxPx = 10
    const dyPx = 6
    for (const axis of AXES) {
      const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 2 }
      const before = screenPxOf(pose, axis, worldPoint, viewportPx)
      const after = screenPxOf(orthoPan(pose, axis, dxPx, dyPx), axis, worldPoint, viewportPx)
      expect(after.x - before.x).toBeCloseTo(-dxPx, 5)
      expect(after.y - before.y).toBeCloseTo(-dyPx, 5)
    }
  })
})
