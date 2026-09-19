import { describe, expect, it } from 'vitest'

import type { BrushHighlight, SceneActor } from '../api'
import {
  canSelectBrushTap,
  isTap,
  isTransparentPixel,
  nearestScreenHit,
  pickActor,
  pickHit,
  rayAabbIntersect,
  resolveEdgeHitSurface,
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

// GUI-PARITY.md "Mesh selection in 2D/3D wireframe mode vs UED22" -- a mesh actor's own wireframe
// EDGES are their own raycast candidate in wireframe mode (`meshEdgePickGeometry`, a `LineSegments`,
// not the filled `meshPickGeometry`), resolved by segment (`index / 2`) like a brush's own outline.
describe('resolveEdgeHitSurface', () => {
  const crate = actor('Crate0', [-50, -50, -50], [50, 50, 50], { brush: null })

  it('resolves a hit segment to its owning actor AND poly index, by index/2', () => {
    const owners = ['Crate0', 'Crate0']
    const polyIndex = [2, 2]
    expect(resolveEdgeHitSurface(0, owners, polyIndex, [crate])).toEqual({ actor: crate, polyIndex: 2 })
    expect(resolveEdgeHitSurface(1, owners, polyIndex, [crate])).toEqual({ actor: crate, polyIndex: 2 })
    expect(resolveEdgeHitSurface(2, owners, polyIndex, [crate])).toEqual({ actor: crate, polyIndex: 2 })
  })

  it('returns null when there is no hit', () => {
    expect(resolveEdgeHitSurface(null, ['Crate0'], [0], [crate])).toBeNull()
    expect(resolveEdgeHitSurface(undefined, ['Crate0'], [0], [crate])).toBeNull()
  })

  it('returns null when the edge has no resolved owner', () => {
    expect(resolveEdgeHitSurface(0, [null], [0], [crate])).toBeNull()
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
        expect(resolveTapAction({ actor: point, polyIndex: null, isLineHit: false }, mode, shiftKey, false)).toEqual({
          kind: 'select-actor', name: 'Light1', additive: false,
        })
      }
    }
  })

  it('a point-actor hit threads the Ctrl-driven additive flag through unchanged', () => {
    expect(resolveTapAction({ actor: point, polyIndex: null, isLineHit: false }, 'lit', false, true)).toEqual({
      kind: 'select-actor', name: 'Light1', additive: true,
    })
  })

  // The core of the new model: a genuine surface hit (polyIndex set) in a non-wireframe mode.
  describe('a surface hit on a brush, non-wireframe mode', () => {
    it('unmodified -> selects the TEXTURE, non-additive', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: 4, isLineHit: false }, 'lit', false, false)).toEqual({
        kind: 'select-surface', actor: 'Brush1', polyIndex: 4, additive: false,
      })
    })

    it('Ctrl -> selects the TEXTURE, additively (multi-selects textures)', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: 4, isLineHit: false }, 'unlit', false, true)).toEqual({
        kind: 'select-surface', actor: 'Brush1', polyIndex: 4, additive: true,
      })
    })

    it('Shift -> forks the SAME click to the whole BRUSH actor instead, always additive', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: 4, isLineHit: false }, 'lit', true, false)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: true,
      })
    })

    it('Shift+Ctrl -> still the whole-actor fork, additive (Ctrl adds nothing new here)', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: 4, isLineHit: false }, 'flat', true, true)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: true,
      })
    })
  })

  // A wireframe outline-LINE hit (polyIndex null, mode 'wireframe') -- the EXISTING, unchanged rule:
  // no modifier needed, Ctrl still multi-selects, Shift plays no special role.
  describe('a line hit on a brush, wireframe mode', () => {
    it('unmodified -> selects the actor, non-additive', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null, isLineHit: false }, 'wireframe', false, false)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: false,
      })
    })

    it('Ctrl -> selects the actor, additive (existing multi-select convention)', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null, isLineHit: false }, 'wireframe', false, true)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: true,
      })
    })

    it('Shift has no effect on the resulting additive flag (unlike the non-wireframe surface fork)', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null, isLineHit: false }, 'wireframe', true, false)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: false,
      })
    })
  })

  // A non-wireframe AABB-fallback hit on a brush (missed all real geometry, so polyIndex is null) --
  // no surface to fall back to a texture-select on, so this is still gated like brush selection
  // always has been: Shift required, a rejected hit absorbed rather than deselecting.
  describe('a non-wireframe fallback hit on a brush with no resolved surface', () => {
    it('unmodified -> absorbed (hit something, but not selectable without Shift)', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null, isLineHit: false }, 'lit', false, false)).toEqual({ kind: 'none' })
    })

    it('Shift -> selects the whole actor, additive', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null, isLineHit: false }, 'unlit', true, false)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: true,
      })
    })
  })

  // A genuine LINE hit (a Mover's always-visible outline, `isLineHit: true`) in a NON-wireframe
  // mode -- owner ruling 2026-09-17 (`shift-modifier-convention-broken-for-poly-and`, Bug B): this
  // must behave exactly like wireframe mode's own line-hit rule (no modifier needed), NOT like the
  // AABB-fallback case right above, even though both carry `polyIndex: null`. A line click has no
  // competing poly/texture-select interpretation to disambiguate from a camera-fly drag, unlike an
  // AABB-fallback hit (which GUI.md's rationale still gates behind Shift).
  describe('a genuine line hit on a brush, NON-wireframe mode (e.g. a Mover outline)', () => {
    it('unmodified -> selects the actor, non-additive -- no Shift needed', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null, isLineHit: true }, 'lit', false, false)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: false,
      })
    })

    it('Ctrl -> selects the actor, additive', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null, isLineHit: true }, 'unlit', false, true)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: true,
      })
    })

    it('Shift is not required (unlike the AABB-fallback case) and changes nothing', () => {
      expect(resolveTapAction({ actor: brush, polyIndex: null, isLineHit: true }, 'flat', true, false)).toEqual({
        kind: 'select-actor', name: 'Brush1', additive: false,
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

describe('nearestScreenHit', () => {
  it('returns null for an empty candidate list', () => {
    expect(nearestScreenHit([], 100, 100)).toBeNull()
  })

  it('picks the candidate closest to the click on screen, not array order', () => {
    const hits = [
      { value: 'far', screenX: 0, screenY: 0 },
      { value: 'near', screenX: 101, screenY: 100 },
      { value: 'farther', screenX: 500, screenY: 500 },
    ]
    expect(nearestScreenHit(hits, 100, 100)).toBe('near')
  })

  it('reproduces the real bug: a depth-nearer but screen-farther hit must NOT win', () => {
    // This is the exact failure mode found live (wireframe-brush-selection-should-hit-test-lines /
    // mover-near-brush803-unclickable-in-wireframe-2d): three.js's own Raycaster sorts by ray
    // DEPTH, so a hit far from the click on screen but physically nearer the camera used to be
    // `hits[0]` and win. Simulating that array order here: the depth-nearest candidate is listed
    // FIRST, but it is screen-farther from the click than the second candidate.
    const depthOrderedHits = [
      { value: 'depth-nearest-but-off-screen', screenX: 400, screenY: 400 },
      { value: 'the-actual-clicked-line', screenX: 100, screenY: 100 },
    ]
    expect(nearestScreenHit(depthOrderedHits, 100, 100)).toBe('the-actual-clicked-line')
  })
})

describe('pickHit', () => {
  it('returns null for an empty candidate list', () => {
    expect(pickHit([], 100, 100)).toBeNull()
  })

  it('a single precise hit wins with no lines present', () => {
    const hits = [{ value: 'mesh', isLine: false, alwaysOnTop: false, screenX: 100, screenY: 100 }]
    expect(pickHit(hits, 100, 100)).toBe('mesh')
  })

  it('among several PRECISE hits, the first (real ray-depth order) wins outright, not screen distance', () => {
    // Two points on the same ray reproject to (as good as) the same screen pixel regardless of
    // depth, so screen-distance can't disambiguate two precise hits -- `hits[0]`'s real depth order
    // must decide, even if a LATER entry happens to report a marginally closer screen position.
    const hits = [
      { value: 'depth-nearest', isLine: false, alwaysOnTop: false, screenX: 100.4, screenY: 100 },
      { value: 'depth-farther', isLine: false, alwaysOnTop: false, screenX: 100.1, screenY: 100 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('depth-nearest')
  })

  it('an ORDINARY (not always-on-top) line never overrides a precise hit, even when screen-nearer', () => {
    // board `flaky-masked-surface-and-sprite-picking-30pct`-shaped case: a genuine precise hit under
    // the cursor must not lose to an unrelated ordinary line merely because it threshold-accepted.
    const hits = [
      { value: 'precise-under-cursor', isLine: false, alwaysOnTop: false, screenX: 100, screenY: 100 },
      { value: 'ordinary-line', isLine: true, alwaysOnTop: false, screenX: 100, screenY: 100 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('precise-under-cursor')
  })

  it('an always-on-top line beats a precise hit at the same pixel', () => {
    // board `mover-not-selectable-via-wireframe-click`: a Mover's outline (depthTest:false) is drawn
    // over whatever real geometry sits behind it, so a click there must resolve to the line.
    const hits = [
      { value: 'wall-behind', isLine: false, alwaysOnTop: false, screenX: 100, screenY: 100 },
      { value: 'mover-outline', isLine: true, alwaysOnTop: true, screenX: 100, screenY: 100 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('mover-outline')
  })

  it('only the winning line\'s always-on-top-ness matters, not a losing candidate\'s', () => {
    // Review finding: an ordinary line that is screen-NEAREST must still win over a precise hit
    // check -- a farther, always-on-top line merely being present elsewhere must not force the
    // precise hit to be discarded.
    const hits = [
      { value: 'precise-under-cursor', isLine: false, alwaysOnTop: false, screenX: 100, screenY: 100 },
      { value: 'ordinary-line-close', isLine: true, alwaysOnTop: false, screenX: 101, screenY: 100 },
      { value: 'always-on-top-line-far', isLine: true, alwaysOnTop: true, screenX: 400, screenY: 400 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('precise-under-cursor')
  })

  it('among several LINE hits with no precise hit, screen-nearest wins (matches nearestScreenHit)', () => {
    const hits = [
      { value: 'depth-nearest-but-off-screen', isLine: true, alwaysOnTop: false, screenX: 400, screenY: 400 },
      { value: 'the-actual-clicked-line', isLine: true, alwaysOnTop: false, screenX: 100, screenY: 100 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('the-actual-clicked-line')
  })

  it('an always-on-top line FARTHER from the click than a precise hit does NOT win (the bug)', () => {
    // Real bug found live 2026-09-17 (`shift-modifier-convention-broken-for-poly-and`, Bug A):
    // `DeusExMover4`'s outline is threshold-accepted (world-unit `Raycaster.params.Line.threshold`
    // can span several screen pixels), so it was a candidate even when a click was actually centered
    // on `Brush803`'s own poly right next to it -- and the old code let ANY always-on-top line beat
    // ANY precise hit outright, with no distance comparison at all. The always-on-top line must only
    // win when it's genuinely at least as close to the click as the precise hit.
    const hits = [
      { value: 'brush-poly-under-cursor', isLine: false, alwaysOnTop: false, screenX: 100, screenY: 100 },
      { value: 'mover-outline-off-to-the-side', isLine: true, alwaysOnTop: true, screenX: 150, screenY: 100 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('brush-poly-under-cursor')
  })

  it('a Mover outline wins over an obscuring polygon when within the ~5px absolute hit box', () => {
    // Board `mover-wireframe-should-outrank-polys-not-actors` (owner ruling 2026-09-18): a Mover's
    // wireframe must win over a polygon even when it's not screen-nearest, as long as the click is
    // genuinely on/near the rendered line. Live-measured: clicking dead-on an obscured Mover outline
    // puts the line ~0.1px from the click while the occluding polygon sits at ~0px -- the OLD
    // relative rule (line must be <= the polygon's own distance) can never fire here, which is why
    // this needed a new absolute cutoff instead of a tighter relative one.
    const hits = [
      { value: 'occluding-wall-poly', isLine: false, alwaysOnTop: false, isActor: false, screenX: 100, screenY: 100 },
      { value: 'mover-outline', isLine: true, alwaysOnTop: true, isMoverLine: true, screenX: 103, screenY: 100 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('mover-outline')
  })

  it('a Mover outline does NOT win over a polygon once outside the absolute hit box (preserves Brush803)', () => {
    // Same mechanism as `DeusExMover4`'s real Brush803 regression above, re-expressed with the new
    // Mover-specific flags: the offending line there was measurably OFF to the side (well past a 5px
    // box), so the new absolute rule must not fire for it either -- it falls through to the ordinary
    // relative rule, which (correctly) rejects it.
    const hits = [
      { value: 'brush803-poly', isLine: false, alwaysOnTop: false, isActor: false, screenX: 100, screenY: 100 },
      { value: 'deusexmover4-outline', isLine: true, alwaysOnTop: true, isMoverLine: true, screenX: 150, screenY: 100 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('brush803-poly')
  })

  it('exactly at the ~5px boundary, the Mover outline still wins (<=, not <)', () => {
    const hits = [
      { value: 'poly', isLine: false, alwaysOnTop: false, isActor: false, screenX: 100, screenY: 100 },
      { value: 'mover-outline', isLine: true, alwaysOnTop: true, isMoverLine: true, screenX: 105, screenY: 100 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('mover-outline')
  })

  it('an actor hit still wins over a Mover outline within the absolute hit box (the "not actors" carve-out)', () => {
    // Owner ruling's explicit carve-out: the Mover-wireframe priority is over POLYGONS, never over
    // another actor (a point actor, another Mover, a mesh actor). An actor precise hit is exempted
    // from the new absolute rule and falls through to the ordinary relative rule, which -- since a
    // real precise hit is always ~0px from the click by construction -- lets the actor win by default.
    const hits = [
      { value: 'nearby-actor', isLine: false, alwaysOnTop: false, isActor: true, screenX: 100, screenY: 100 },
      { value: 'mover-outline', isLine: true, alwaysOnTop: true, isMoverLine: true, screenX: 101, screenY: 100 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('nearby-actor')
  })

  it('an ORDINARY (non-Mover) line within the absolute hit box still loses to a closer polygon', () => {
    // Scope check: the new absolute cutoff is Mover-specific (`isMoverLine`). Same geometry as the
    // "wins within the box" test above, but WITHOUT `isMoverLine` -- if the absolute rule leaked to
    // ordinary lines, this would wrongly pick the line; it must fall through to the pre-existing
    // relative rule instead, which rejects a line farther than the polygon.
    const hits = [
      { value: 'poly-under-cursor', isLine: false, alwaysOnTop: false, isActor: false, screenX: 100, screenY: 100 },
      { value: 'ordinary-brush-outline', isLine: true, alwaysOnTop: true, screenX: 103, screenY: 100 },
    ]
    expect(pickHit(hits, 100, 100)).toBe('poly-under-cursor')
  })

  it('a Mover outline with NO competing precise hit at all does NOT win once outside the hit box', () => {
    // Board `mover-wireframe-5px-cutoff-only-applies-vs-poly`: `moverBeatsPoly` above only runs when
    // `preciseHits.length > 0`, so a Mover line with nothing competing at the click point used to
    // fall straight through to `if (bestLine) return bestLine.value` with no distance check at all --
    // live-reported as needing a 40px+ click to miss. 20px stands in for "far"; the raycaster's own
    // world-space line threshold (`tapSelect.ts`) is what actually admits a line this far as a
    // candidate in the first place.
    const hits = [{ value: 'mover-outline', isLine: true, alwaysOnTop: true, isMoverLine: true, screenX: 120, screenY: 100 }]
    expect(pickHit(hits, 100, 100)).toBeNull()
  })

  it('a Mover outline with no competing precise hit still wins at the exact 5px boundary (<=, not <)', () => {
    const hits = [{ value: 'mover-outline', isLine: true, alwaysOnTop: true, isMoverLine: true, screenX: 105, screenY: 100 }]
    expect(pickHit(hits, 100, 100)).toBe('mover-outline')
  })

  it('a Mover outline with no competing precise hit does NOT win just past the boundary', () => {
    const hits = [{ value: 'mover-outline', isLine: true, alwaysOnTop: true, isMoverLine: true, screenX: 106, screenY: 100 }]
    expect(pickHit(hits, 100, 100)).toBeNull()
  })

  it('a Mover outline with no competing precise hit still wins when genuinely close', () => {
    const hits = [{ value: 'mover-outline', isLine: true, alwaysOnTop: true, isMoverLine: true, screenX: 102, screenY: 100 }]
    expect(pickHit(hits, 100, 100)).toBe('mover-outline')
  })

  it('an ORDINARY (non-Mover) line with no competing precise hit is unaffected by the new gate', () => {
    // Scope check: the new "no competing precise hit" gate is Mover-specific (`isMoverLine`). An
    // ordinary brush wireframe line relies on `wireframe-brush-selection-should-hit-test-lines`'s own
    // threshold-based admission, not this cutoff -- it must keep winning from any distance here.
    const hits = [{ value: 'ordinary-brush-outline', isLine: true, alwaysOnTop: false, screenX: 140, screenY: 100 }]
    expect(pickHit(hits, 100, 100)).toBe('ordinary-brush-outline')
  })
})

describe('isTransparentPixel', () => {
  it('is transparent at alpha 0 (the sprite icon padding)', () => {
    expect(isTransparentPixel(0)).toBe(true)
  })

  it('is not transparent at full opacity', () => {
    expect(isTransparentPixel(1)).toBe(false)
  })

  it('uses the same 0.5 cutoff as the masked-material alphaTest', () => {
    expect(isTransparentPixel(0.49)).toBe(true)
    expect(isTransparentPixel(0.5)).toBe(false)
  })
})
