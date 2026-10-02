import { describe, expect, it } from 'vitest'

import { computeTwoFingerDelta } from './touchGesture'

describe('computeTwoFingerDelta', () => {
  it('both fingers moving together the same amount is a pure pan, no zoom', () => {
    const before: [{ x: number; y: number }, { x: number; y: number }] = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
    ]
    const after: [{ x: number; y: number }, { x: number; y: number }] = [
      { x: 10, y: 5 },
      { x: 110, y: 5 },
    ]
    const got = computeTwoFingerDelta(before, after)
    expect(got.panDx).toBeCloseTo(10)
    expect(got.panDy).toBeCloseTo(5)
    expect(got.zoomDelta).toBeCloseTo(0)
  })

  it('fingers spreading apart with a fixed midpoint is a pure zoom-in (negative delta), no pan', () => {
    const before: [{ x: number; y: number }, { x: number; y: number }] = [
      { x: 40, y: 0 },
      { x: 60, y: 0 },
    ]
    const after: [{ x: number; y: number }, { x: number; y: number }] = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
    ]
    const got = computeTwoFingerDelta(before, after)
    expect(got.panDx).toBeCloseTo(0)
    expect(got.panDy).toBeCloseTo(0)
    expect(got.zoomDelta).toBeCloseTo(-80) // distance grew 20 -> 100, i.e. +80, negated for zoom-in
  })

  it('fingers pinching together is a positive zoom-out delta', () => {
    const before: [{ x: number; y: number }, { x: number; y: number }] = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
    ]
    const after: [{ x: number; y: number }, { x: number; y: number }] = [
      { x: 40, y: 0 },
      { x: 60, y: 0 },
    ]
    const got = computeTwoFingerDelta(before, after)
    expect(got.zoomDelta).toBeCloseTo(80) // distance shrank 100 -> 20, i.e. -80, negated for zoom-out
  })

  it('is a no-op for two stationary fingers', () => {
    const p: [{ x: number; y: number }, { x: number; y: number }] = [
      { x: 12, y: 34 },
      { x: 56, y: 78 },
    ]
    const got = computeTwoFingerDelta(p, p)
    expect(got.panDx).toBe(0)
    expect(got.panDy).toBe(0)
    expect(got.zoomDelta).toBeCloseTo(0) // -(distAfter - distBefore) is -0 here, not === 0
  })
})
