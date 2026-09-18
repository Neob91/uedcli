+++
priority = "p1"
kind = "feature"
summary = "build synthetic-level test fixtures and deterministic click-selection tests covering every GUI pick/selection scenario from this campaign"
+++

# Synthetic-level regression tests for GUI pick/selection behavior

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
