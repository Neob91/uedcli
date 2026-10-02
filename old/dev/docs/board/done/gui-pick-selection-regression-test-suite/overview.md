+++
priority = "p1"
kind = "feature"
summary = "build synthetic-level test fixtures and deterministic click-selection tests covering every GUI pick/selection scenario from this campaign"
+++

# Synthetic-level regression tests for GUI pick/selection behavior

Done: all 8 scenarios have real, deterministic coverage. New file `web/src/scene/tapSelect.test.ts`
(17 tests) drives the REAL `resolveTapSelect` entry point (`tapSelect.ts`) with a real
`THREE.Raycaster`/orthographic camera against small synthetic scenes -- click-AT-vs-click-NEXT-TO,
asserting the resolved `TapAction` -- for scenarios 1, 2, 4, 5, 6, 8. Scenarios 3 and 7 already had
equivalent deterministic coverage in existing files (`markerRenderOrder.test.tsx`,
`BrushOutlines.test.tsx`) and needed no new test. Full frontend suite: 385 tests green (was 369), no
regressions; `tsc -b` shows the same 7 pre-existing, unrelated errors as before this change.

Per-scenario disposition:

1. **Click-to-deselect a sole selected poly** -- `selectionSet.test.ts` already unit-tests
   `toggleSelection`'s `deselectSole`. Added a round-trip test in `tapSelect.test.ts` chaining a real
   `resolveTapSelect` hit into `toggleSelection` exactly as `App.tsx`'s `onSelectSurface` does,
   proving the full click-to-deselect flow, not just the reducer in isolation.
2. **Masked-surface highlight + click reliability** -- highlight visibility (`alphaTest` scaling) was
   already covered by `SelectionHighlight.test.tsx`'s masked-geometry tests. The "flaky pick" half
   was confirmed NOT a bug (`flaky-masked-surface-and-sprite-picking-30pct`, closed with no code
   change) -- added a `tapSelect.test.ts` block asserting a masked decal in front of a wall resolves
   deterministically across repeated clicks and a grid of points, never the wall behind it.
3. **Highlight z-order vs. point-actor sprites** -- already fully covered by
   `markerRenderOrder.test.tsx`. No new test needed.
4. **Wireframe hit-tests lines only** -- new `tapSelect.test.ts` block: click on a brush's outline
   line selects it; click in the open interior (or well outside the shape) deselects instead of
   selecting by silhouette/AABB.
5. **Mover-vs-brush pick priority** -- `selection.test.ts`'s `pickHit` unit tests already cover the
   ranking algorithm in detail. Added one `tapSelect.test.ts` block exercising it end to end: a
   click on a Mover's outline (coincident with a wall poly) selects the Mover; a click on the wall
   away from the Mover selects the wall.
6. **Sprite alpha-aware picking** -- new `tapSelect.test.ts` block with a real `THREE.Sprite` +
   `SpriteMaterial` and a fake canvas (`getContext`/`getImageData` stand-in -- jsdom has no real
   `canvas` package installed) simulating an opaque icon disk on a transparent square billboard:
   click at the icon's center selects the actor; click in the billboard's transparent corner, or
   well outside the billboard, does not.
7. **Mover wireframe unoccluded** -- already fully covered by `BrushOutlines.test.tsx`'s
   `depthTest`/`renderOrder` assertions. No new test needed.
8. **Mover poly selection (Movers:on) and Mover selection via wireframe outline in non-wireframe
   mode** -- both board items (`mover-polys-unselectable-in-movers-on-mode`,
   `mover-not-selectable-via-wireframe-click`) are landed in `dev/docs/board/done/`. Added two
   `tapSelect.test.ts` blocks: one for the Movers:on solid mesh (a Mover's own face, positioned
   nearer the camera than a wall behind it, resolves to the Mover; a click outside the Mover's
   footprint still resolves to the wall), one for the always-visible outline being a click target
   in plain non-wireframe mode.

No production code was changed -- this was pure test infrastructure. No bug was found while writing
these tests.

Reviewed (one subagent, adversarial): found two tests that passed for the wrong reason -- scenario 4's
"interior click deselects" used an actor bbox unreachably far away, so the wireframe-mode AABB
exclusion it claimed to test was never actually exercised; scenario 5's first Mover-vs-poly test
never wired in a competing poly hit at all. Both fixed (a reachable bbox + a companion test proving
it, and a real `meshObject` wired into the coincident-hit test) and confirmed by mutation -- reverting
the real fix in `selection.ts`/`tapSelect.ts` now fails the corresponding test. 17 tests total.

---

Owner's direct request: "We should have some synthetic levels, and some tests that verify the
behavior by clicking AT a sprite and NEXT TO a sprite, and asserting what gets selected. ... We need
these kinds of tests for at least all the scenarios we discussed today."

Build durable, deterministic regression coverage (not manual headless-Chromium spot-checks) for every
click/selection/highlight scenario fixed in this campaign so far:

1. Click-to-deselect a sole selected poly (`click-on-a-selected-poly-does-not-deselect-it`).
2. Masked-surface highlight visibility on select (`poly-highlight-not-visible-for-brush116-0`) --
   AND click-to-select reliability (see `flaky-masked-surface-and-sprite-picking-30pct`, a separate
   item -- write this suite against whatever that item lands as the fixed/correct behavior).
3. Selected-surface highlight z-order vs. point-actor sprites
   (`selected-surface-highlight-renders-above-point`).
4. Wireframe-mode hit-testing lines only, not invisible poly faces
   (`wireframe-brush-selection-should-hit-test-lines`).
5. Mover-vs-Subtract-brush pick priority (`mover-near-brush803-unclickable-in-wireframe-2d`).
6. Point-actor sprite alpha-aware picking -- click AT the visible icon shape selects it, click NEXT TO
   it (in the transparent margin) does not (`point-actor-sprite-picking-ignores-sprite-alpha`; see
   also `flaky-masked-surface-and-sprite-picking-30pct`).
7. Mover wireframe always rendering unoccluded (`mover-wireframe-occluded-by-geometry`) -- a visual/
   render-order assertion, not a click test, but should get equivalent deterministic coverage.
8. Mover poly selection in "Movers:on" mode, and Mover actor selection via wireframe click in plain
   non-wireframe mode (`mover-polys-unselectable-in-movers-on-mode` /
   `mover-not-selectable-via-wireframe-click`) -- check `dev/docs/board/done/` for these before
   starting; if they've landed, write real tests against them; if not yet, note as a follow-up rather
   than blocking on them.

"Synthetic levels" = small, purpose-built test fixtures (hardcoded scene/actor data, not full real
T3D map content) isolating one scenario each -- e.g. a masked decal poly directly in front of a wall,
a point actor with a known sprite texture, a Mover overlapping a Subtract brush. Follow this
campaign's existing test patterns already in the codebase for the shape to use (e.g.
`SelectionHighlight.test.tsx`'s `buildMaskedGeometry()` helper, `markerRenderOrder.test.tsx`,
`selection.test.ts`) -- prefer fast, deterministic vitest/jsdom-level tests over full headless-browser
E2E where the existing patterns show it's sufficient (most of this campaign's raycast/selection logic
is plain three.js math, testable without a live renderer or backend). Use judgment on where a true
click test needs to go through the real `tapSelect.ts` entry point with a constructed `Raycaster`
against synthetic geometry (click AT vs. click NEXT TO a target, asserting the resolved
actor/poly/nothing) vs. where a narrower unit test on the underlying helper suffices.

## Scope note

This is a separate item and a separate subagent from `flaky-masked-surface-and-sprite-picking-30pct`
-- the owner asked for these as distinct pieces of work (one code-fix subagent, one test-infra
subagent), not combined. Sequence after the flakiness fix lands so the suite is written against
correct, settled behavior rather than a moving target.
