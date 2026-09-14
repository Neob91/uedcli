import { describe, expect, it } from 'vitest'

import type { CameraPose, CameraSpeeds } from './camera'
import { cameraBasis, dollyAndTurn, look, orbit, pan, zoom } from './camera'

const UNIT_SPEEDS: CameraSpeeds = {
  yawPerPixel: 1,
  pitchPerPixel: 1,
  dollyPerPixel: 1,
  panPerPixel: 1,
  zoomPerWheelUnit: 1,
}

const IDENTITY: CameraPose = { position: [0, 0, 0], pitch: 0, yaw: 0 }

describe('cameraBasis', () => {
  it('is world +X forward / +Y right / +Z up at the identity pose', () => {
    const { forward, right, up } = cameraBasis(0, 0)
    expect(forward[0]).toBeCloseTo(1)
    expect(forward[1]).toBeCloseTo(0)
    expect(forward[2]).toBeCloseTo(0)
    expect(right[0]).toBeCloseTo(0)
    expect(right[1]).toBeCloseTo(1)
    expect(right[2]).toBeCloseTo(0)
    expect(up[0]).toBeCloseTo(0)
    expect(up[1]).toBeCloseTo(0)
    expect(up[2]).toBeCloseTo(1)
  })
})

describe('dollyAndTurn (LMB-drag)', () => {
  it('a horizontal drag yaws by the expected angle', () => {
    const got = dollyAndTurn(IDENTITY, 10, 0, UNIT_SPEEDS)
    expect(got.yaw).toBeCloseTo(350) // wrap(0 - 10*1)
    expect(got.pitch).toBe(0)
  })

  it('a vertical drag moves forward in the horizontal plane', () => {
    const got = dollyAndTurn(IDENTITY, 0, -5, UNIT_SPEEDS) // drag "up" (negative screen dy)
    expect(got.position[0]).toBeCloseTo(5) // horizontal forward is +X at yaw=0; moves forward by 5
    expect(got.position[1]).toBeCloseTo(0)
    expect(got.position[2]).toBeCloseTo(0)
  })

  it('NEVER changes Z even when pitched (the Z-leak fix)', () => {
    const pitched = { position: [0, 0, 0] as [number, number, number], pitch: 45, yaw: 0 }
    const got = dollyAndTurn(pitched, 0, -5, UNIT_SPEEDS)
    expect(got.position[2]).toBeCloseTo(0) // pitched-forward has a Z component; horizontal move ignores it
    expect(got.position[0]).toBeCloseTo(5) // still moves 5 along +X
  })
})

describe('look (RMB-drag)', () => {
  it('rotates pitch/yaw and leaves position untouched', () => {
    const got = look(IDENTITY, 20, 10, UNIT_SPEEDS)
    expect(got.yaw).toBeCloseTo(340) // wrap(0 - 20)
    expect(got.pitch).toBeCloseTo(-10) // 0 - 10
    expect(got.position).toEqual(IDENTITY.position)
  })

  it('clamps pitch to +/-89 degrees', () => {
    const got = look(IDENTITY, 0, -1000, UNIT_SPEEDS)
    expect(got.pitch).toBe(89)
  })
})

describe('pan (LMB+RMB-drag)', () => {
  it('when pitched, strafe stays in XY and vertical is pure Z', () => {
    const pitched = { position: [0, 0, 0] as [number, number, number], pitch: 45, yaw: 0 }
    const strafe = pan(pitched, 3, 0, UNIT_SPEEDS) // horizontal drag -> strafe along right (XY)
    expect(strafe.position[2]).toBeCloseTo(0) // right is horizontal, so no Z
    const vertical = pan(pitched, 0, -4, UNIT_SPEEDS) // vertical drag -> world Z only
    expect(vertical.position[0]).toBeCloseTo(0)
    expect(vertical.position[1]).toBeCloseTo(0)
    expect(vertical.position[2]).toBeCloseTo(4)
  })

  it('strafes along right and pans along up, with no rotation', () => {
    const got = pan(IDENTITY, 3, -4, UNIT_SPEEDS)
    // at yaw=0: right=(0,1,0), up=(0,0,1); dx=3 along right, -dy=4 along up
    expect(got.position[0]).toBeCloseTo(0)
    expect(got.position[1]).toBeCloseTo(3)
    expect(got.position[2]).toBeCloseTo(4)
    expect(got.pitch).toBe(0)
    expect(got.yaw).toBe(0)
  })
})

describe('zoom (scroll)', () => {
  it('dollies along forward proportional to the wheel delta', () => {
    const got = zoom(IDENTITY, -7, UNIT_SPEEDS)
    expect(got.position[0]).toBeCloseTo(7) // -(-7)*1 along +X forward
  })
})

describe('orbit (Alt-drag)', () => {
  it('rotates around the pivot at a fixed radius and re-aims at it', () => {
    const pose: CameraPose = { position: [10, 0, 0], pitch: 0, yaw: 0 }
    const got = orbit(pose, [0, 0, 0], 90, 0, UNIT_SPEEDS)

    expect(got.position[0]).toBeCloseTo(0, 5)
    expect(got.position[1]).toBeCloseTo(-10, 5)
    expect(got.position[2]).toBeCloseTo(0, 5)

    // The new position is still exactly `radius` from the pivot.
    const radius = Math.hypot(...got.position)
    expect(radius).toBeCloseTo(10, 5)

    // Camera now looks back at the pivot: forward(pitch, yaw) points from position to (0,0,0).
    const { forward } = cameraBasis(got.pitch, got.yaw)
    expect(forward[0]).toBeCloseTo(0, 5)
    expect(forward[1]).toBeCloseTo(1, 5)
    expect(forward[2]).toBeCloseTo(0, 5)
  })

  it('is a no-op when the camera is already at the pivot', () => {
    const pose: CameraPose = { position: [1, 2, 3], pitch: 5, yaw: 6 }
    const got = orbit(pose, [1, 2, 3], 30, 30, UNIT_SPEEDS)
    expect(got).toEqual(pose)
  })
})
