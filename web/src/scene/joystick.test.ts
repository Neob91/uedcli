import { describe, expect, it } from 'vitest'

import { joystickVector } from './joystick'

describe('joystickVector', () => {
  it('is zero at the center', () => {
    expect(joystickVector(0, 0, 32)).toEqual({ forward: 0, right: 0 })
  })

  it('straight up (negative dy) is full forward, no strafe', () => {
    const v = joystickVector(0, -32, 32)
    expect(v.forward).toBeCloseTo(1)
    expect(v.right).toBeCloseTo(0)
  })

  it('straight down (positive dy) is full backward', () => {
    const v = joystickVector(0, 32, 32)
    expect(v.forward).toBeCloseTo(-1)
  })

  it('straight right is full right strafe, no forward', () => {
    const v = joystickVector(32, 0, 32)
    expect(v.right).toBeCloseTo(1)
    expect(v.forward).toBeCloseTo(0)
  })

  it('straight left is full left strafe', () => {
    const v = joystickVector(-32, 0, 32)
    expect(v.right).toBeCloseTo(-1)
  })

  it('a partial deflection gives a proportionally partial value (analog, not just -1/0/1)', () => {
    const v = joystickVector(0, -16, 32)
    expect(v.forward).toBeCloseTo(0.5)
  })

  it('clamps a drag past the ring edge to full deflection, never beyond 1', () => {
    const v = joystickVector(0, -1000, 32)
    expect(v.forward).toBeCloseTo(1)
  })

  it('a diagonal drag combines forward and strafe, magnitude clamped to the unit circle', () => {
    const v = joystickVector(32, -32, 32)
    expect(Math.hypot(v.forward, v.right)).toBeCloseTo(1)
    expect(v.forward).toBeGreaterThan(0)
    expect(v.right).toBeGreaterThan(0)
  })

  it('a non-positive radius is always zero (no divide-by-zero)', () => {
    expect(joystickVector(10, 10, 0)).toEqual({ forward: 0, right: 0 })
    expect(joystickVector(10, 10, -5)).toEqual({ forward: 0, right: 0 })
  })
})
