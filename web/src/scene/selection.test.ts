import { describe, expect, it } from 'vitest'

import type { BrushHighlight, SceneActor } from '../api'
import {
  canSelectBrushTap,
  isTap,
  pickActor,
  rayAabbIntersect,
  resolveHitActor,
  resolveHitSurface,
  resolveTapAction,
} from './selection'

const FAKE_BRUSH: BrushHighlight = { csg_class: 'add', color: [1, 1, 1], polys: [], local_origin: [0, 0, 0] }

function actor(
  name: string,
  lo: [number, number, number],
  hi: [number, number, number],
  overrides: Partial<SceneActor> = {},
): SceneActor {
  return {
    name,
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
    categories: [],
    brush: FAKE_BRUSH, // a brush actor by default -- most fixtures here exercise brush-select rules
    sprite: null,
    radii: null,
    is_mover: false,
    ...overrides,
  }
}

describe('rayAabbIntersect', () => {
  it('hits a box the ray passes through', () => {
    const t = rayAabbIntersect({ origin: [-10, 0, 0], direction: [1, 0, 0] }, [-1, -1, -1], [1, 1, 1])
    expect(t).toBeCloseTo(9)
  })

  it('misses a box the ray does not pass through', () => {
    const t = rayAabbIntersect({ origin: [-10, 5, 5], direction: [1, 0, 0] }, [-1, -1, -1], [1, 1, 1])
    expect(t).toBeNull()
  })

  it('misses a box entirely behind the ray origin', () => {
    const t = rayAabbIntersect({ origin: [10, 0, 0], direction: [1, 0, 0] }, [-1, -1, -1], [1, 1, 1])
    expect(t).toBeNull()
  })
})

describe('pickActor', () => {
  it('picks the nearest actor along the ray', () => {
    const near = actor('Near', [-1, -1, -1], [1, 1, 1])
    const far = actor('Far', [9, -1, -1], [11, 1, 1])
    const ray = { origin: [-10, 0, 0] as [number, number, number], direction: [1, 0, 0] as [number, number, number] }
    expect(pickActor(ray, [far, near])?.name).toBe('Near') // order-independent: nearest wins
  })

  it('returns null when the ray misses every actor', () => {
    const only = actor('Only', [-1, -1, -1], [1, 1, 1])
    const ray = { origin: [-10, 50, 50] as [number, number, number], direction: [1, 0, 0] as [number, number, number] }
    expect(pickActor(ray, [only])).toBeNull()
  })

  // Quad-layout Part 1, Task 6: an ortho pane's rays are all PARALLEL (the same axis-aligned
  // direction regardless of screen position), unlike a perspective ray fanning out from one camera
  // point. `pickActor`'s slab test and `resolveHitActor`'s triangle lookup are written against a
  // generic Ray (origin+direction) with no perspective-specific assumption, so this passes with ZERO
  // changes to selection.ts -- a confirming regression test, not invented busywork.
  it('finds the nearest AABB hit for a parallel (orthographic) ray too', () => {
    const near = actor('Near', [-1, -1, -1], [1, 1, 1])
    const far = actor('Far', [9, -1, -1], [11, 1, 1])
    // Two "screen positions" (different Y/Z origins), same parallel +X direction -- the ortho case.
    const rayThroughNear = { origin: [-10, 0, 0] as [number, number, number], direction: [1, 0, 0] as [number, number, number] }
    const rayThroughFar = { origin: [-10, -0.5, -0.5] as [number, number, number], direction: [1, 0, 0] as [number, number, number] }
    expect(pickActor(rayThroughNear, [far, near])?.name).toBe('Near')
    expect(pickActor(rayThroughFar, [far, near])?.name).toBe('Near') // still hits Near first, not Far
  })
})

describe('resolveHitActor', () => {
  const inner = actor('Inner', [-1, -1, -1], [1, 1, 1])
  const room = actor('Room', [-100, -100, -100], [100, 100, 100])

  it('resolves a hit face to its owning actor, even one nested in a bigger actor\'s AABB', () => {
    // The bug this fixes: `Inner`'s tiny AABB sits fully inside `Room`'s huge one, so an
    // AABB-only test could never tell a click on `Inner`'s own geometry apart from `Room`'s.
    const owners = ['Room', 'Room', 'Inner', 'Inner']
    expect(resolveHitActor(2, owners, [room, inner])?.name).toBe('Inner')
    expect(resolveHitActor(0, owners, [room, inner])?.name).toBe('Room')
  })

  it('returns null when there is no hit', () => {
    expect(resolveHitActor(null, ['Room'], [room])).toBeNull()
    expect(resolveHitActor(undefined, ['Room'], [room])).toBeNull()
  })

  it('returns null for a hit triangle with no resolved owner', () => {
    expect(resolveHitActor(0, [null], [room])).toBeNull()
  })

  it('returns null when the owner name matches no actor in the current payload', () => {
    expect(resolveHitActor(0, ['Ghost'], [room])).toBeNull()
  })
})

describe('resolveHitSurface', () => {
  const room = actor('Room', [-100, -100, -100], [100, 100, 100])

  it('resolves a hit face to its owning actor AND poly index', () => {
    const owners = ['Room', 'Room']
    const polyIndex = [4, 4]
    expect(resolveHitSurface(0, owners, polyIndex, [room])).toEqual({ actor: room, polyIndex: 4 })
    expect(resolveHitSurface(1, owners, polyIndex, [room])).toEqual({ actor: room, polyIndex: 4 })
  })

  it('returns null when there is no hit', () => {
    expect(resolveHitSurface(null, ['Room'], [0], [room])).toBeNull()
    expect(resolveHitSurface(undefined, ['Room'], [0], [room])).toBeNull()
  })

  it('returns null when the owner is unresolved', () => {
    expect(resolveHitSurface(0, [null], [0], [room])).toBeNull()
  })

  it('still resolves the actor when the poly index is unresolved (a mesh-actor hit, no brush.polys to index into)', () => {
    expect(resolveHitSurface(0, ['Room'], [null], [room])).toEqual({ actor: room, polyIndex: null })
  })
})

// GUI.md "Selection & the Inspector" -- the redesigned click-target resolution: surface (texture)
// vs. whole-actor vs. deselect vs. absorbed, with/without Shift/Ctrl, per shading mode.
describe('resolveTapAction', () => {
  const brush = actor('Brush1', [-1, -1, -1], [1, 1, 1])
  const point = actor('Light1', [-1, -1, -1], [1, 1, 1], { brush: null })

  // Point actors are always plain-tap-selectable everywhere, unaffected by Shift or shading mode.
  it('a point-actor hit always selects the actor, Shift/mode irrelevant', () => {
    for (const mode of ['wireframe', 'unlit', 'flat', 'lit'] as const) {
      for (const shiftKey of [false, true]) {
        expect(resolveTapAction({ actor: point, polyIndex: null }, mode, shiftKey, false)).toEqual({
          kind: 'select-actor', name: 'Light1', additive: false,
        })
      }
    }
  })

  it('a point-actor hit threads the Ctrl-driven additive flag through unchanged', () => {
    expect(resolveTapAction({ actor: point, polyIndex: null }, 'lit', false, true)).toEqual({
      kind: 'select-actor', name: 'Light1', additive: true,
    })
  })

  // The core of the new model: a genuine surface hit (polyIndex set) in a non-wireframe mode.
  describe('a surface hit on a brush, non-wireframe mode', () => {
    it('unmodified -> selects the TEXTURE, non-additive', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: 4 }, 'lit', false, false)).toEqual({
        kind: 'select-surface', actor: 'Brush1', polyIndex: 4, additive: false,
      })
    })

    it('Ctrl -> selects the TEXTURE, additively (multi-selects textures)', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: 4 }, 'unlit', false, true)).toEqual({
        kind: 'select-surface', actor: 'Brush1', polyIndex: 4, additive: true,
      })
    })

    it('Shift -> forks the SAME click to the whole BRUSH actor instead, always additive', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: 4 }, 'lit', true, false)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: true,
      })
    })

    it('Shift+Ctrl -> still the whole-actor fork, additive (Ctrl adds nothing new here)', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: 4 }, 'flat', true, true)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: true,
      })
    })
  })

  // A wireframe outline-LINE hit (polyIndex null, mode 'wireframe') -- the EXISTING, unchanged rule:
  // no modifier needed, Ctrl still multi-selects, Shift plays no special role.
  describe('a line hit on a brush, wireframe mode', () => {
    it('unmodified -> selects the actor, non-additive', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null }, 'wireframe', false, false)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: false,
      })
    })

    it('Ctrl -> selects the actor, additive (existing multi-select convention)', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null }, 'wireframe', false, true)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: true,
      })
    })

    it('Shift has no effect on the resulting additive flag (unlike the non-wireframe surface fork)', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null }, 'wireframe', true, false)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: false,
      })
    })
  })

  // A non-wireframe AABB-fallback hit on a brush (missed all real geometry, so polyIndex is null) --
  // no surface to fall back to a texture-select on, so this is still gated like brush selection
  // always has been: Shift required, a rejected hit absorbed rather than deselecting.
  describe('a non-wireframe fallback hit on a brush with no resolved surface', () => {
    it('unmodified -> absorbed (hit something, but not selectable without Shift)', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null }, 'lit', false, false)).toEqual({ kind: 'none' })
    })

    it('Shift -> selects the whole actor, additive', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null }, 'unlit', true, false)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: true,
      })
    })
  })

  // Owner ruling 2026-09-15, reversing spec §9's earlier "Esc is the only deselect path": a tap that
  // hits NOTHING at all deselects everything, in every pane/mode, regardless of Shift/Ctrl.
  it('a tap that hits nothing at all deselects, regardless of modifiers or mode', () => {
    for (const mode of ['wireframe', 'unlit', 'flat', 'lit'] as const) {
      for (const shiftKey of [false, true]) {
        for (const additive of [false, true]) {
          expect(resolveTapAction(null, mode, shiftKey, additive)).toEqual({ kind: 'deselect' })
        }
      }
    }
  })
})

describe('canSelectBrushTap', () => {
  // Corrected owner ruling 2026-09-15: shading-mode-gated (wireframe vs. non-wireframe), not
  // viewport-gated (an earlier pass had this backwards as 3D-vs-2D). Wireframe never needs Shift --
  // ortho panes are always wireframe, and the 3D perspective pane is too when in that mode.
  it('never requires Shift in wireframe mode', () => {
    expect(canSelectBrushTap('wireframe', false)).toBe(true)
    expect(canSelectBrushTap('wireframe', true)).toBe(true)
  })

  it('requires Shift for a brush hit in a non-wireframe mode (only possible in 3D perspective)', () => {
    for (const mode of ['unlit', 'flat', 'lit'] as const) {
      expect(canSelectBrushTap(mode, false)).toBe(false)
      expect(canSelectBrushTap(mode, true)).toBe(true)
    }
  })
})

describe('isTap', () => {
  it('is a tap when total travel stays within the threshold', () => {
    expect(isTap(100, 100, 102, 101)).toBe(true) // ~2.24px, under the 4px default
  })

  it('is a drag once travel exceeds the threshold', () => {
    expect(isTap(100, 100, 110, 100)).toBe(false) // 10px, over the 4px default
  })

  it('is exactly at the threshold boundary (inclusive)', () => {
    expect(isTap(0, 0, 4, 0, 4)).toBe(true)
    expect(isTap(0, 0, 4.01, 0, 4)).toBe(false)
  })
})
