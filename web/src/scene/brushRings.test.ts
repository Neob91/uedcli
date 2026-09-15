import { describe, expect, it } from 'vitest'

import type { SceneActor } from '../api'
import { buildBrushRings } from './brushRings'

function brushActor(name: string, color: [number, number, number]): SceneActor {
  return {
    name,
    cls: 'Engine.Brush',
    bbox_lo: [0, 0, 0],
    bbox_hi: [1, 1, 1],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    categories: [],
    brush: { csg_class: 'add', color, polys: [[0, 0, 0, 1, 0, 0, 1, 1, 0]], local_origin: [0, 0, 0] },
    sprite: null,
    radii: null,
  }
}

function nonBrushActor(name: string): SceneActor {
  return { ...brushActor(name, [0, 0, 0]), brush: null }
}

describe('buildBrushRings', () => {
  const a = brushActor('A', [255, 0, 0])
  const b = brushActor('B', [0, 255, 0])
  const c = brushActor('C', [0, 0, 255])
  const nonBrush = nonBrushActor('Light1')

  it("'csg-all' returns one ring per brush actor, correct colors, only the selected one bold", () => {
    const rings = buildBrushRings([a, b, c, nonBrush], new Set(['B']), 'csg-all')
    expect(rings).toHaveLength(3)
    const byName = new Map(rings.map((r) => [r.actorName, r]))
    expect(byName.get('A')?.color).toEqual([255, 0, 0])
    expect(byName.get('A')?.bold).toBe(false)
    expect(byName.get('B')?.color).toEqual([0, 255, 0])
    expect(byName.get('B')?.bold).toBe(true)
    expect(byName.get('C')?.bold).toBe(false)
  })

  it("'selected-only' returns exactly one ring, for the selected actor only, bold (regression pin: single-select shape unchanged)", () => {
    const rings = buildBrushRings([a, b, c, nonBrush], new Set(['B']), 'selected-only')
    expect(rings).toHaveLength(1)
    expect(rings[0].actorName).toBe('B')
    expect(rings[0].bold).toBe(true)
  })

  it("'selected-only' returns zero rings when nothing is selected (regression pin)", () => {
    expect(buildBrushRings([a, b, c], new Set(), 'selected-only')).toHaveLength(0)
  })

  it('never emits a ring for a non-brush actor, in either mode', () => {
    expect(buildBrushRings([nonBrush], new Set(['Light1']), 'csg-all')).toHaveLength(0)
    expect(buildBrushRings([nonBrush], new Set(['Light1']), 'selected-only')).toHaveLength(0)
  })

  // Quad-layout Part 3, Task 14: multi-select cross-pane highlight -- 2 of 3 brush actors selected.
  it("'selected-only' with 2 selected brush actors returns 2 bold rings, correctly colored", () => {
    const rings = buildBrushRings([a, b, c], new Set(['A', 'C']), 'selected-only')
    expect(rings).toHaveLength(2)
    const byName = new Map(rings.map((r) => [r.actorName, r]))
    expect(byName.get('A')?.color).toEqual([255, 0, 0])
    expect(byName.get('A')?.bold).toBe(true)
    expect(byName.get('C')?.color).toEqual([0, 0, 255])
    expect(byName.get('C')?.bold).toBe(true)
    expect(byName.has('B')).toBe(false)
  })

  it("'csg-all' with 2 selected brush actors marks both bold, the third not", () => {
    const rings = buildBrushRings([a, b, c], new Set(['A', 'C']), 'csg-all')
    expect(rings).toHaveLength(3)
    const byName = new Map(rings.map((r) => [r.actorName, r]))
    expect(byName.get('A')?.bold).toBe(true)
    expect(byName.get('B')?.bold).toBe(false)
    expect(byName.get('C')?.bold).toBe(true)
  })
})
