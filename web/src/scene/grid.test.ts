import { describe, expect, it } from 'vitest'

import { gridLines, gridSpacingUU } from './grid'

describe('gridSpacingUU', () => {
  it('snaps to the 1-2-5-10 sequence at each order of magnitude (known-input table)', () => {
    expect(gridSpacingUU(0.1)).toBe(5) // ideal=5 -> 5
    expect(gridSpacingUU(0.5)).toBe(50) // ideal=25 -> 50
    expect(gridSpacingUU(1)).toBe(50) // ideal=50 -> 50
    expect(gridSpacingUU(3)).toBe(200) // ideal=150 -> 200
    expect(gridSpacingUU(10)).toBe(500) // ideal=500 -> 500
  })

  it('is coarser as worldUnitsPerPixel grows, finer as it shrinks (monotonic)', () => {
    const wupps = [0.01, 0.1, 1, 10, 100, 1000]
    const spacings = wupps.map(gridSpacingUU)
    for (let i = 1; i < spacings.length; i++) {
      expect(spacings[i]).toBeGreaterThan(spacings[i - 1])
    }
  })

  it('every returned spacing is 1, 2, 5, or 10 times a power of 10', () => {
    for (const wupp of [0.001, 0.03, 0.7, 4, 60, 900, 12345]) {
      const spacing = gridSpacingUU(wupp)
      const magnitude = Math.pow(10, Math.floor(Math.log10(spacing) + 1e-9))
      const normalized = Math.round((spacing / magnitude) * 1e6) / 1e6
      expect([1, 2, 5, 10]).toContain(normalized)
    }
  })
})

describe('gridLines', () => {
  it('produces lines exactly covering the bounds at the given spacing, none outside them', () => {
    const bounds = { uMin: -5, uMax: 12, vMin: 0, vMax: 22 }
    const lines = gridLines(10, bounds)

    const uLines = lines.filter((l) => l.axis === 'u').map((l) => l.at)
    const vLines = lines.filter((l) => l.axis === 'v').map((l) => l.at)

    expect(uLines).toEqual([0, 10])
    expect(vLines).toEqual([0, 10, 20])
    for (const l of lines) {
      const lo = l.axis === 'u' ? bounds.uMin : bounds.vMin
      const hi = l.axis === 'u' ? bounds.uMax : bounds.vMax
      expect(l.at).toBeGreaterThanOrEqual(lo)
      expect(l.at).toBeLessThanOrEqual(hi)
    }
  })

  it('returns no lines when no multiple of the spacing falls inside the bounds', () => {
    expect(gridLines(1000, { uMin: 1, uMax: 5, vMin: 1, vMax: 5 })).toEqual([])
  })
})
