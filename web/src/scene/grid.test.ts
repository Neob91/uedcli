import { describe, expect, it } from 'vitest'

import { gridLines, gridSpacingUU, orthoGridWindow } from './grid'

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

describe('orthoGridWindow', () => {
  // Regression: bounds must be anchored to the camera's world position, not a window centered on
  // 0 -- otherwise gridLines() always straddles the current pan position and the grid slides with
  // the camera instead of staying locked to world geometry (bug report: "grid is relative to the
  // viewport, not geometry").
  it('anchors bounds to the center point projected onto the axis basis, not to 0', () => {
    // up = [0,-1,0]: centerV = dot([500,-300,0], [0,-1,0]) = 300
    const { bounds } = orthoGridWindow([500, -300, 0], [1, 0, 0], [0, -1, 0], 100, 50)
    expect(bounds).toEqual({ uMin: 400, uMax: 600, vMin: 250, vMax: 350 })
  })

  it('panning the center shifts the window by exactly the pan delta', () => {
    const a = orthoGridWindow([0, 0, 0], [1, 0, 0], [0, -1, 0], 100, 50)
    const b = orthoGridWindow([64, 64, 0], [1, 0, 0], [0, -1, 0], 100, 50)
    expect(b.bounds.uMin - a.bounds.uMin).toBe(64)
    expect(b.bounds.vMin - a.bounds.vMin).toBe(-64) // up = [0,-1,0]: +world-Y is -screen-v
  })

  it("planeOrigin carries only center's component along the third (depth) axis", () => {
    // top view: right=+X, up=-Y, depth=Z -- planeOrigin must equal [0, 0, centerZ]
    const { planeOrigin } = orthoGridWindow([123, 456, 789], [1, 0, 0], [0, -1, 0], 10, 10)
    expect(planeOrigin).toEqual([0, 0, 789])
  })

  it('reconstructing a world point from bounds + planeOrigin recovers the original center', () => {
    const center: [number, number, number] = [500, -300, 42]
    const right: [number, number, number] = [1, 0, 0]
    const up: [number, number, number] = [0, -1, 0]
    const { bounds, planeOrigin } = orthoGridWindow(center, right, up, 100, 50)
    const centerU = (bounds.uMin + bounds.uMax) / 2
    const centerV = (bounds.vMin + bounds.vMax) / 2
    const rebuilt = [
      planeOrigin[0] + right[0] * centerU + up[0] * centerV,
      planeOrigin[1] + right[1] * centerU + up[1] * centerV,
      planeOrigin[2] + right[2] * centerU + up[2] * centerV,
    ]
    expect(rebuilt).toEqual(center)
  })
})
