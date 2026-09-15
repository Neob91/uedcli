import { describe, expect, it } from 'vitest'

import type { SceneActor } from '../api'
import {
  canSelectBrushTap,
  isTap,
  pickActor,
  rayAabbIntersect,
  resolveHitActor,
  resolveTapSelection,
} from './selection'

function actor(name: string, lo: [number, number, number], hi: [number, number, number]): SceneActor {
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
    brush: null,
    sprite: null,
    radii: null,
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

describe('resolveTapSelection', () => {
  const hit = actor('Hit', [-1, -1, -1], [1, 1, 1])

  // Quad-layout Part 3, Task 13: a plain tap on a hit actor selects it non-additively; a Ctrl-tap
  // selects it additively; a tap that hits NOTHING is a true no-op (the deliberate behavior change
  // from Slice 1's click-away-to-deselect -- Esc, not a miss, is now the only deselect path).
  it('a plain tap on a hit actor resolves to (name, additive=false)', () => {
    expect(resolveTapSelection(hit, false)).toEqual({ name: 'Hit', additive: false })
  })

  it('a Ctrl-tap on a hit actor resolves to (name, additive=true)', () => {
    expect(resolveTapSelection(hit, true)).toEqual({ name: 'Hit', additive: true })
  })

  it('a tap that hits nothing resolves to null, regardless of additive', () => {
    expect(resolveTapSelection(null, false)).toBeNull()
    expect(resolveTapSelection(null, true)).toBeNull()
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
