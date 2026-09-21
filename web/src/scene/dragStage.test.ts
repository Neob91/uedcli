import { describe, expect, it } from 'vitest'

import type { BrushHighlight, DirectionalArrow, ScenePoly, SceneActor } from '../api'
import {
  addVec3,
  anySelectedIsBrush,
  applyDelta,
  applyStagedOffset,
  applyStagedOffsets,
  applyStagedOffsetsToPolys,
  resolveActorMoveAxis,
  snapVecToGrid,
  stagedLocationsFor,
} from './dragStage'

function actor(name: string, location: [number, number, number], overrides: Partial<SceneActor> = {}): SceneActor {
  return {
    name,
    cls: 'Engine.Actor',
    bbox_lo: location,
    bbox_hi: location,
    location,
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: '',
    csg_rank: 0,
    props: [],
    categories: [],
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
    ...overrides,
  }
}

function brush(csgClass = 'add'): BrushHighlight {
  return {
    csg_class: csgClass,
    color: [1, 1, 1],
    polys: [[0, 0, 0, 10, 0, 0, 10, 10, 0]], // one triangle
    local_origin: [5, 5, 0],
  }
}

function arrow(): DirectionalArrow {
  return {
    require_selection: true,
    lines: [0, 0, 0, 38, 0, 0, 38, 0, 0, 22, 12, 0], // shaft + one fin, flat triples
  }
}

describe('resolveActorMoveAxis', () => {
  it('resolves LMB(1)/RMB(2)/both(3) to x/y/z when additive with a non-empty selection', () => {
    const selection = new Set(['ActorA'])
    expect(resolveActorMoveAxis(true, 1, selection)).toBe('x')
    expect(resolveActorMoveAxis(true, 2, selection)).toBe('y')
    expect(resolveActorMoveAxis(true, 3, selection)).toBe('z')
  })

  it('returns null (fall through to camera dispatch) when not additive -- regression guard for an unmodified drag', () => {
    expect(resolveActorMoveAxis(false, 1, new Set(['ActorA']))).toBeNull()
  })

  it('returns null when additive but nothing is selected -- nothing to move', () => {
    expect(resolveActorMoveAxis(true, 1, new Set())).toBeNull()
  })

  it('returns null for an unmapped button combo (e.g. no buttons down, or a 4th/5th button)', () => {
    expect(resolveActorMoveAxis(true, 0, new Set(['ActorA']))).toBeNull()
    expect(resolveActorMoveAxis(true, 4, new Set(['ActorA']))).toBeNull()
  })
})

describe('anySelectedIsBrush', () => {
  const brush: BrushHighlight = { csg_class: 'add', color: [1, 1, 1], polys: [], local_origin: [0, 0, 0] }
  const brushActor = actor('BrushA', [0, 0, 0], { brush })
  const meshActor = actor('MeshA', [0, 0, 0])

  it('false when nothing selected is a brush', () => {
    expect(anySelectedIsBrush(new Set(['MeshA']), [brushActor, meshActor])).toBe(false)
  })

  it('true when the sole selected actor is a brush', () => {
    expect(anySelectedIsBrush(new Set(['BrushA']), [brushActor, meshActor])).toBe(true)
  })

  it('true when a MIXED selection has any brush in it (owner ruling: the whole selection snaps)', () => {
    expect(anySelectedIsBrush(new Set(['BrushA', 'MeshA']), [brushActor, meshActor])).toBe(true)
  })

  it('false for an empty selection', () => {
    expect(anySelectedIsBrush(new Set(), [brushActor, meshActor])).toBe(false)
  })
})

describe('addVec3', () => {
  it('adds component-wise', () => {
    expect(addVec3([1, 2, 3], [10, -5, 0])).toEqual([11, -3, 3])
  })
})

describe('snapVecToGrid', () => {
  it('rounds each component to the nearest multiple of gridSize', () => {
    expect(snapVecToGrid([17, -17, 8], 16)).toEqual([16, -16, 16])
  })

  it('rounds down when exactly halfway is not reached, per Math.round convention', () => {
    expect(snapVecToGrid([7.9, 8.1, -8.1], 16)).toEqual([0, 16, -16])
  })

  it('a zero delta stays zero', () => {
    expect(snapVecToGrid([0, 0, 0], 16)).toEqual([0, 0, 0])
  })

  it('returns delta unchanged for a non-positive gridSize (defensive)', () => {
    expect(snapVecToGrid([3, -4, 5], 0)).toEqual([3, -4, 5])
    expect(snapVecToGrid([3, -4, 5], -16)).toEqual([3, -4, 5])
  })
})

describe('applyDelta', () => {
  const actors = [actor('ActorA', [10, 20, 30]), actor('ActorB', [0, 0, 0])]

  it('bases the first move of a selected actor on its scene.actors location', () => {
    const next = applyDelta({}, new Set(['ActorA']), [5, 0, 0], actors)
    expect(next.ActorA).toEqual([15, 20, 30])
  })

  it('accumulates a second delta onto the PREVIOUS staged position, not the original trunk location', () => {
    const first = applyDelta({}, new Set(['ActorA']), [5, 0, 0], actors)
    const second = applyDelta(first, new Set(['ActorA']), [5, 0, 0], actors)
    expect(second.ActorA).toEqual([20, 20, 30])
  })

  it('moves the WHOLE selection, not just one actor', () => {
    const next = applyDelta({}, new Set(['ActorA', 'ActorB']), [1, 2, 3], actors)
    expect(next.ActorA).toEqual([11, 22, 33])
    expect(next.ActorB).toEqual([1, 2, 3])
  })

  it('leaves an unrelated staged actor untouched', () => {
    const prev = { ActorB: [100, 100, 100] as [number, number, number] }
    const next = applyDelta(prev, new Set(['ActorA']), [1, 0, 0], actors)
    expect(next.ActorB).toEqual([100, 100, 100])
    expect(next.ActorA).toEqual([11, 20, 30])
  })

  it('skips a selected name absent from the scene rather than crashing', () => {
    const next = applyDelta({}, new Set(['Ghost']), [1, 0, 0], actors)
    expect(next.Ghost).toBeUndefined()
  })

  it('returns a NEW object, never mutates prev', () => {
    const prev = {}
    const next = applyDelta(prev, new Set(['ActorA']), [1, 0, 0], actors)
    expect(next).not.toBe(prev)
    expect(prev).toEqual({})
  })
})

describe('stagedLocationsFor', () => {
  it('returns only the staged locations for names in the current selection', () => {
    const offsets = { ActorA: [1, 2, 3] as [number, number, number], ActorB: [4, 5, 6] as [number, number, number] }
    expect(stagedLocationsFor(offsets, new Set(['ActorA']))).toEqual({ ActorA: [1, 2, 3] })
  })

  it('omits a selected name that was never actually moved (no staged offset)', () => {
    const offsets = { ActorA: [1, 2, 3] as [number, number, number] }
    expect(stagedLocationsFor(offsets, new Set(['ActorA', 'ActorC']))).toEqual({ ActorA: [1, 2, 3] })
  })

  it('returns an empty object when nothing in the selection was moved', () => {
    expect(stagedLocationsFor({}, new Set(['ActorA']))).toEqual({})
  })
})

describe('applyStagedOffset', () => {
  it('returns the SAME actor reference, unchanged, when it has no staged offset', () => {
    const a = actor('ActorA', [1, 2, 3])
    expect(applyStagedOffset(a, {})).toBe(a)
  })

  it('moves location and translates bbox_lo/bbox_hi by the same delta, preserving box size', () => {
    const a = actor('ActorA', [10, 20, 30], { bbox_lo: [5, 15, 25], bbox_hi: [15, 25, 35] })
    const next = applyStagedOffset(a, { ActorA: [20, 20, 30] }) // delta = [10, 0, 0]
    expect(next.location).toEqual([20, 20, 30])
    expect(next.bbox_lo).toEqual([15, 15, 25])
    expect(next.bbox_hi).toEqual([25, 25, 35])
  })

  it("translates a brush's own polys and local_origin by the same delta -- BrushOutlines' ring / SelectionMarkers' vertex+pivot dots", () => {
    const a = actor('BrushA', [0, 0, 0], { brush: brush() })
    const next = applyStagedOffset(a, { BrushA: [0, 10, 0] }) // delta = [0, 10, 0]
    expect(next.brush!.polys).toEqual([[0, 10, 0, 10, 10, 0, 10, 20, 0]])
    expect(next.brush!.local_origin).toEqual([5, 15, 0])
    // Non-spatial brush fields are untouched.
    expect(next.brush!.csg_class).toBe('add')
    expect(next.brush!.color).toEqual([1, 1, 1])
  })

  it("translates a directional_arrow's lines by the same delta -- DirectionalArrows' gizmo", () => {
    const a = actor('ActorA', [0, 0, 0], { directional_arrow: arrow() })
    const next = applyStagedOffset(a, { ActorA: [0, 0, 5] }) // delta = [0, 0, 5]
    expect(next.directional_arrow!.lines).toEqual([0, 0, 5, 38, 0, 5, 38, 0, 5, 22, 12, 5])
    expect(next.directional_arrow!.require_selection).toBe(true)
  })

  it('translates a brush AND a directional_arrow together (e.g. a DeusExMover)', () => {
    const a = actor('MoverA', [0, 0, 0], { brush: brush('mover'), directional_arrow: arrow() })
    const next = applyStagedOffset(a, { MoverA: [1, 0, 0] })
    expect(next.brush!.polys[0][0]).toBe(1) // first vertex's x shifted by 1
    expect(next.directional_arrow!.lines[0]).toBe(1) // first line point's x shifted by 1
  })

  it('leaves radii/sprite untouched (no vector fields of their own)', () => {
    const a = actor('ActorA', [0, 0, 0], {
      radii: { collision_radius: 10, collision_height: 5, light_radius: null, sound_radius: null },
      sprite: { tex_index: 3, width: 32, height: 32 },
    })
    const next = applyStagedOffset(a, { ActorA: [1, 1, 1] })
    expect(next.radii).toEqual(a.radii)
    expect(next.sprite).toEqual(a.sprite)
  })
})

describe('applyStagedOffsets', () => {
  it('maps applyStagedOffset over the whole actor list, moving only the staged ones', () => {
    const a = actor('ActorA', [0, 0, 0])
    const b = actor('ActorB', [100, 100, 100])
    const [nextA, nextB] = applyStagedOffsets([a, b], { ActorA: [5, 0, 0] })
    expect(nextA.location).toEqual([5, 0, 0])
    expect(nextB).toBe(b) // untouched, same reference
  })
})

function poly(owner: string | null, overrides: Partial<ScenePoly> = {}): ScenePoly {
  return {
    verts: [0, 0, 0, 10, 0, 0, 10, 10, 0],
    base: [0, 0, 0],
    tu: [1, 0, 0],
    tv: [0, 1, 0],
    pan: [0, 0],
    tex_index: -1,
    masked: false,
    two_sided: false,
    blend: 'opaque',
    flags: 0,
    lightmap: null,
    owner,
    i_brush_poly: null,
    ...overrides,
  }
}

describe('applyStagedOffsetsToPolys', () => {
  it('returns the SAME array reference, unchanged, when nothing is staged', () => {
    const polys = [poly('MeshA')]
    expect(applyStagedOffsetsToPolys(polys, [actor('MeshA', [0, 0, 0])], {})).toBe(polys)
  })

  it('leaves each poly the SAME reference when the staged actor owns no polys here', () => {
    const p = poly('MeshA')
    const actors = [actor('MeshA', [0, 0, 0]), actor('Other', [0, 0, 0])]
    const [next] = applyStagedOffsetsToPolys([p], actors, { Other: [5, 0, 0] })
    expect(next).toBe(p)
  })

  it("translates a staged mesh actor's own polys' verts and base by its delta, leaving tu/tv untouched", () => {
    const polys = [poly('MeshA', { verts: [0, 0, 0, 10, 0, 0, 10, 10, 0], base: [1, 2, 3] })]
    const actors = [actor('MeshA', [0, 0, 0])]
    const [next] = applyStagedOffsetsToPolys(polys, actors, { MeshA: [5, 0, 0] }) // delta = [5, 0, 0]
    expect(next.verts).toEqual([5, 0, 0, 15, 0, 0, 15, 10, 0])
    expect(next.base).toEqual([6, 2, 3])
    expect(next.tu).toEqual([1, 0, 0])
    expect(next.tv).toEqual([0, 1, 0])
  })

  it('leaves an unstaged poly (owned by a different actor) untouched, same reference', () => {
    const staged = poly('MeshA')
    const untouched = poly('MeshB')
    const actors = [actor('MeshA', [0, 0, 0]), actor('MeshB', [0, 0, 0])]
    const result = applyStagedOffsetsToPolys([staged, untouched], actors, { MeshA: [1, 0, 0] })
    expect(result[1]).toBe(untouched)
    expect(result[0]).not.toBe(staged)
  })

  it('leaves an ownerless poly (a CSG join with no source actor) untouched', () => {
    const orphan = poly(null)
    const actors = [actor('MeshA', [0, 0, 0])]
    const result = applyStagedOffsetsToPolys([orphan], actors, { MeshA: [1, 0, 0] })
    expect(result[0]).toBe(orphan)
  })
})
