import { describe, expect, it } from 'vitest'

import type { SceneActor } from '../api'
import { buildBrushRings } from './brushRings'

function brushActor(name: string, color: [number, number, number], isMover = false): SceneActor {
  return {
    name,
    cls: isMover ? 'Engine.Mover' : 'Engine.Brush',
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
    is_mover: isMover,
    directional_arrow: null,
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

  // Perf regression pin (click-to-highlight latency bug): BrushOutlines.tsx memoizes 'csg-all''s ring
  // SET on `[actors]` alone (an always-empty selection), never on `selectedNames`, so selecting a
  // brush in an ortho pane doesn't force `mergeThinRings` to rebuild the whole level's merged
  // wireframe buffer. That's only safe because a ring's own content (verts/color/actorName) never
  // depends on `selectedNames` in 'csg-all' mode -- only its `bold` flag does. If this ever stops
  // being true, the memoization in BrushOutlines.tsx silently goes stale.
  it("'csg-all' ring content (verts/color/actorName, in order) is identical regardless of selectedNames -- only `bold` differs", () => {
    const withNoSelection = buildBrushRings([a, b, c], new Set(), 'csg-all')
    const withSelection = buildBrushRings([a, b, c], new Set(['A', 'C']), 'csg-all')
    expect(withNoSelection.map((r) => ({ actorName: r.actorName, color: r.color, verts: r.verts }))).toEqual(
      withSelection.map((r) => ({ actorName: r.actorName, color: r.color, verts: r.verts })),
    )
    expect(withNoSelection.every((r) => r.bold === false)).toBe(true)
  })
})

// GUI.md "Movers": a Mover always renders wireframe-outline-only, in every shading mode -- so
// 'selected-only' (the mode non-wireframe panes use) can't gate a Mover's ring on selection the way
// it gates an ordinary brush's.
describe("buildBrushRings -- Movers always outline, even unselected, in 'selected-only' mode", () => {
  const mover = brushActor('Door1', [255, 0, 255], true)
  const brush = brushActor('Wall1', [0, 255, 0], false)

  it("'selected-only' includes an UNSELECTED Mover's ring, thin (not bold)", () => {
    const rings = buildBrushRings([mover, brush], new Set(), 'selected-only')
    expect(rings).toHaveLength(1)
    expect(rings[0].actorName).toBe('Door1')
    expect(rings[0].bold).toBe(false)
  })

  it("'selected-only' still omits an unselected ORDINARY brush's ring alongside an unselected Mover", () => {
    const rings = buildBrushRings([mover, brush], new Set(), 'selected-only')
    expect(rings.some((r) => r.actorName === 'Wall1')).toBe(false)
  })

  it("'selected-only' bolds a SELECTED Mover's ring, same as an ordinary selected brush", () => {
    const rings = buildBrushRings([mover, brush], new Set(['Door1']), 'selected-only')
    expect(rings).toHaveLength(1)
    expect(rings[0].actorName).toBe('Door1')
    expect(rings[0].bold).toBe(true)
  })

  it("'csg-all' is unaffected by is_mover -- already includes every brush actor", () => {
    const rings = buildBrushRings([mover, brush], new Set(), 'csg-all')
    expect(rings).toHaveLength(2)
    expect(rings.every((r) => r.bold === false)).toBe(true)
  })
})
