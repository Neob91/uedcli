import { describe, expect, it } from 'vitest'

import type { SceneActor } from '../api'
import { actorsNeedingMarkers, MARKER_COLOR } from './markers'

function actor(overrides: Partial<SceneActor> = {}): SceneActor {
  return {
    name: 'Light0',
    cls: 'Engine.Light',
    bbox_lo: [0, 0, 0],
    bbox_hi: [0, 0, 0],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    categories: [],
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    ...overrides,
  }
}

describe('MARKER_COLOR', () => {
  it('is a fixed neutral grey, matching preview.py\'s MARKER=(185,185,185)', () => {
    expect(MARKER_COLOR).toEqual([185 / 255, 185 / 255, 185 / 255])
  })
})

describe('actorsNeedingMarkers', () => {
  it('excludes a brush actor even with no owned polys', () => {
    const brushActor = actor({
      name: 'Wall',
      brush: { csg_class: 'add', color: [0, 0, 0], polys: [], local_origin: [0, 0, 0] },
    })
    expect(actorsNeedingMarkers([brushActor], new Set())).toEqual([])
  })

  it('excludes an actor with an owned poly (a resolved, rendered mesh)', () => {
    const meshActor = actor({ name: 'Chair0', cls: 'DeusEx.OfficeChair' })
    expect(actorsNeedingMarkers([meshActor], new Set(['Chair0']))).toEqual([])
  })

  it('includes a bare point actor: no brush, no owned poly', () => {
    const light = actor({ name: 'Light0' })
    expect(actorsNeedingMarkers([light], new Set())).toEqual([light])
  })
})
