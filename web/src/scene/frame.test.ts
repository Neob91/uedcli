import { describe, expect, it } from 'vitest'

import type { SceneActor } from '../api'
import { bboxCenter, bboxMaxExtent, unionBBox } from './frame'

function actor(lo: [number, number, number], hi: [number, number, number]): SceneActor {
  return {
    name: 'A',
    cls: 'Engine.Brush',
    bbox_lo: lo,
    bbox_hi: hi,
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
  }
}

describe('unionBBox', () => {
  it('is null for an empty set', () => {
    expect(unionBBox([])).toBeNull()
  })

  it('matches a single actor own bbox', () => {
    expect(unionBBox([actor([1, 2, 3], [4, 5, 6])])).toEqual({ lo: [1, 2, 3], hi: [4, 5, 6] })
  })

  it('unions two actors into the box enclosing both', () => {
    const a = actor([0, 0, 0], [1, 1, 1])
    const b = actor([-2, 5, 0], [3, 6, 10])
    expect(unionBBox([a, b])).toEqual({ lo: [-2, 0, 0], hi: [3, 6, 10] })
  })
})

describe('bboxCenter', () => {
  it('is the midpoint of lo/hi', () => {
    expect(bboxCenter({ lo: [0, 0, 0], hi: [4, 2, 10] })).toEqual([2, 1, 5])
  })
})

describe('bboxMaxExtent', () => {
  it('is the largest axis span', () => {
    expect(bboxMaxExtent({ lo: [0, 0, 0], hi: [4, 2, 10] })).toBe(10)
  })

  it('floors at 1 for a degenerate (point) box', () => {
    expect(bboxMaxExtent({ lo: [5, 5, 5], hi: [5, 5, 5] })).toBe(1)
  })
})
