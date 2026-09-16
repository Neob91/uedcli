import { describe, expect, it } from 'vitest'

import {
  GRID_TARGET,
  gridEscalation,
  gridIndices,
  gridLineColor,
  orthoGridWindow,
  worldGridLines,
} from './grid'

// Known-input/output pairs lifted from `uedcli/tests/test_preview_grid.py` (the ground truth for
// `preview.py`'s own `_grid_escalation`/`_grid_line_color`/`_grid_indices`) -- this suite asserts
// the TS port reproduces them exactly, not new values invented for the port.

const GRID_MINOR: [number, number, number] = [80, 80, 80] // round(64 + (96-64)*0.5), exact

describe('gridEscalation', () => {
  it.each([
    [100, 1.0, 50, { shift: 0, drawn: 50, fade: 1.0 }], // 2*count(4) < limit(25): gate never opens
    [100, 1.0, 5, { shift: 0, drawn: 5, fade: 0.4 }], // gate opens but no escalation needed
    [130, 1.0, 1, { shift: 3, drawn: 8, fade: 0.984375 }], // gate opens AND escalates; non-trivial fade
    [1000, 1.0, 1, { shift: 3, drawn: 8, fade: 1.0 }], // gate opens AND escalates; fade lands on 1.0
  ])('matches the ported arithmetic for (%d, %d, %d)', (widthPx, worldUnitsPerPixel, step, expected) => {
    const got = gridEscalation(widthPx, worldUnitsPerPixel, step)
    expect(got.shift).toBe(expected.shift)
    expect(got.drawn).toBe(expected.drawn)
    expect(got.fade).toBeCloseTo(expected.fade, 9)
  })

  it('guards a pane narrower than the 4px threshold', () => {
    // `limit = widthPx // 4` would be 0 below 4px, and the loop's own exit condition
    // (`(count >> shift) >= limit`) could then never fire (0 >= 0 forever) -- guarded, not escalated.
    expect(gridEscalation(3, 1.0, 1)).toEqual({ shift: 0, drawn: 1, fade: 1.0 })
  })
})

describe('gridLineColor', () => {
  it('fades only odd lines', () => {
    const { shift, fade } = gridEscalation(100, 1.0, 5) // (0, 5, 0.4)
    expect(fade).not.toBe(1.0)
    for (let i = -4; i < 20; i++) {
      const tier = ((i << shift) & 7) !== 0 ? 0.5 : 1.0
      const unfaded: [number, number, number] = [64 + (96 - 64) * tier, 64 + (96 - 64) * tier, 64 + (96 - 64) * tier]
      const got = gridLineColor(i, shift, fade)
      if (i % 2 === 0) {
        expect(got).toEqual(unfaded)
      } else {
        const faded = unfaded.map((c) => Math.round(64 + (c - 64) * fade))
        expect(got).toEqual(faded)
        expect(got).not.toEqual(unfaded)
      }
    }
  })

  it('fade is exactly 1 when the density gate is not crossed', () => {
    const { shift, fade } = gridEscalation(100, 1.0, 50) // gate never opens
    expect(fade).toBe(1.0)
    for (const i of [1, 3, 5]) {
      const tier = ((i << shift) & 7) !== 0 ? 0.5 : 1.0
      const unfaded: [number, number, number] = [64 + (96 - 64) * tier, 64 + (96 - 64) * tier, 64 + (96 - 64) * tier]
      expect(gridLineColor(i, shift, fade)).toEqual(unfaded)
    }
  })

  it('tier selects the lerp endpoint -- every 8th (unescalated) line is major', () => {
    for (const i of [0, 8, -8, 16]) {
      expect(gridLineColor(i, 0, 1.0)).toEqual(GRID_TARGET)
    }
    for (const i of [1, 2, 3, 4, 5, 6, 7]) {
      expect(gridLineColor(i, 0, 1.0)).toEqual(GRID_MINOR)
    }
  })

  it('majors are pinned to multiples of 8x drawn across two zooms', () => {
    // The property the `<< shift` in the ported formula exists to preserve: independent of which
    // (unescalated) zoom `drawn` came from.
    for (const step of [4, 64]) {
      const { shift, drawn } = gridEscalation(2000, 0.1, step) // small enough that neither escalates
      expect(shift).toBe(0)
      expect(drawn).toBe(step)
      for (let i = -20; i < 20; i++) {
        const world = (i << shift) * step
        const isMajor = ((i << shift) & 7) === 0
        expect(isMajor).toBe(world % (8 * drawn) === 0)
      }
    }
  })
})

describe('gridIndices', () => {
  it('the world clamp bounds the index range regardless of the visible span', () => {
    const r = gridIndices(1, 0, -1_000_000, 1_000_000)
    expect(r.lo).toBe(-32768)
    expect(r.hi).toBe(32768)
  })

  it('the world clamp scales down by shift', () => {
    const step = 4
    const { shift, drawn } = gridEscalation(4000, 1.0, step) // forces real escalation
    const r = gridIndices(step, shift, -1_000_000, 1_000_000)
    for (const i of [r.lo, r.hi - 1]) {
      const world = (i << shift) * step
      expect(world).toBeGreaterThanOrEqual(-32768)
      expect(world).toBeLessThan(32768 + drawn)
    }
  })
})

describe('orthoGridWindow', () => {
  // Regression: bounds must be anchored to the camera's world position, not a window centered on
  // 0 -- otherwise lines always straddle the current pan position and the grid slides with the
  // camera instead of staying locked to world geometry (bug report: "grid is relative to the
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

describe('worldGridLines', () => {
  it('produces lines at every multiple of the base step touching the bounds', () => {
    const bounds = { uMin: -5, uMax: 12, vMin: 0, vMax: 22 }
    // step=10, widthPx large + worldUnitsPerPixel small -> no escalation, drawnStep === baseStep
    const { lines, drawnStep } = worldGridLines(10, 2000, 0.01, bounds)
    expect(drawnStep).toBe(10)

    const uLines = lines.filter((l) => l.axis === 'u').map((l) => l.at)
    const vLines = lines.filter((l) => l.axis === 'v').map((l) => l.at)
    // `gridIndices`' own floor/ceil widening (ported from `preview.py`'s `_grid_indices`, whose
    // docstring explains why: a line just outside the visible span still needs its endpoints
    // computed so a renderer with pixel-level clipping can draw its clipped remainder) means the
    // first/last line here can land one step OUTSIDE `bounds` -- -10 is left of uMin=-5.
    expect(uLines).toEqual([-10, 0, 10])
    expect(vLines).toEqual([0, 10, 20])
  })

  it('a too-coarse step is not escalated (only a fine one ever doubles)', () => {
    // Mirrors `preview.py`'s `test_too_coarse_step_is_reported_unescalated_in_the_caption`: an
    // over-coarse step never escalates, so `drawnStep === baseStep` even though the resulting
    // line(s) land far outside any reasonable viewport.
    const { drawnStep } = worldGridLines(65536, 2000, 0.1, { uMin: -256, uMax: 256, vMin: -256, vMax: 256 })
    expect(drawnStep).toBe(65536)
  })

  it('every 8th drawn line is colored as major, matching gridLineColor', () => {
    const bounds = { uMin: -80, uMax: 80, vMin: 0, vMax: 0 }
    const { lines } = worldGridLines(8, 2000, 0.01, bounds) // no escalation: shift=0
    const majorLines = lines.filter((l) => l.axis === 'u' && l.at % 64 === 0)
    expect(majorLines.length).toBeGreaterThan(0)
    for (const l of majorLines) expect(l.color).toEqual(GRID_TARGET)
  })
})
