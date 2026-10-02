import { describe, expect, it } from 'vitest'

import { accumulateMoveDragFrame, freshMoveDragAccumulator } from './moveDragThreshold'
import { TAP_DRAG_THRESHOLD_PX, isTap } from './selection'

describe('accumulateMoveDragFrame', () => {
  it('applies no move while the CUMULATIVE delta stays within the tap threshold', () => {
    const acc = freshMoveDragAccumulator()
    // Four 1px frames: cumulative (4, 0), hypot 4 == TAP_DRAG_THRESHOLD_PX -- isTap's own `<=` still
    // calls this a tap, so no move must apply yet.
    for (let i = 0; i < 4; i++) {
      expect(accumulateMoveDragFrame(acc, 1, 0)).toBeNull()
    }
    expect(acc.started).toBe(false)
    expect(acc.totalDx).toBe(4)
  })

  it('on the frame that CROSSES the threshold, applies the WHOLE accumulated delta, not just the remainder', () => {
    const acc = freshMoveDragAccumulator()
    accumulateMoveDragFrame(acc, 1, 0) // total (1, 0) -- still a tap
    accumulateMoveDragFrame(acc, 1, 0) // total (2, 0) -- still a tap
    // This 1px frame alone is not what should be applied -- the actor must not "skip" the first 2px.
    const frame = accumulateMoveDragFrame(acc, 10, 0) // total (12, 0) -- crosses
    expect(isTap(0, 0, 12, 0, TAP_DRAG_THRESHOLD_PX)).toBe(false)
    expect(frame).toEqual({ dx: 12, dy: 0 })
    expect(acc.started).toBe(true)
  })

  it('applies each frame\'s own per-frame delta once the gesture has already started (no re-accumulation)', () => {
    const acc = freshMoveDragAccumulator()
    accumulateMoveDragFrame(acc, 100, 0) // crosses immediately -- started = true, applies (100, 0)
    expect(accumulateMoveDragFrame(acc, 3, -2)).toEqual({ dx: 3, dy: -2 })
    expect(accumulateMoveDragFrame(acc, -1, 1)).toEqual({ dx: -1, dy: 1 })
    // totalDx/totalDy are no longer consulted once started -- confirm nothing but the per-frame
    // delta is returned, however large the (unused) running total would have grown.
    expect(acc.totalDx).toBe(100)
  })

  it('a diagonal cumulative delta crossing the threshold is measured by hypot, not by axis alone', () => {
    const acc = freshMoveDragAccumulator()
    // (3, 3) has hypot ~4.24, over the 4px threshold, even though neither axis alone reaches 4.
    expect(accumulateMoveDragFrame(acc, 3, 3)).toEqual({ dx: 3, dy: 3 })
  })

  it('freshMoveDragAccumulator resets state for a NEW gesture -- no leakage from a prior one', () => {
    const first = freshMoveDragAccumulator()
    accumulateMoveDragFrame(first, 100, 0) // crosses, started = true

    const second = freshMoveDragAccumulator()
    expect(second.started).toBe(false)
    expect(second.totalDx).toBe(0)
    expect(second.totalDy).toBe(0)
    // A fresh under-threshold sequence on the NEW accumulator must not be treated as already-started.
    expect(accumulateMoveDragFrame(second, 1, 0)).toBeNull()
  })
})
