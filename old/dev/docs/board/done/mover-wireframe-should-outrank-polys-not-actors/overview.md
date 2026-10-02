+++
priority = "p0"
kind = "debug"
summary = "FIXED -- Mover outline beats a polygon within a 5px absolute hit box, not actors; preserves the Brush803 fix"
+++

# Mover wireframe outranks a polygon within a 5px hit box, not actors

Owner ruling: a Mover's always-visible outline should win a click over an obscuring polygon even
when not screen-nearest, but never over a real actor.

## The conflict with the Brush803 fix, and how it was resolved

This ruling looked like it was in direct tension with `pickHit`'s existing relative distance
tiebreak (`shift-modifier-convention-broken-for-poly-and`, `5cb974fc`), which was itself a fix for a
real bug: `DeusExMover4`'s outline stealing a click from an adjacent brush's poly (`Brush803`) merely
by being a raycast-threshold candidate nearby, not actually under the cursor.

Live measurement (headless Chromium, real synthetic clicks on `DeusExMover4`'s own obscured outline
in `showcase_bar`) proved the tension was real, not hypothetical: a polygon raycast hit is always
~0.0px from the click by construction (an exact ray-triangle intersection reprojects onto the
clicked pixel); a threshold-accepted line's reported point is the closest point on the segment to
the ray, which is almost never exactly 0px even when the click lands visually right on the rendered
line (measured ~0.1px dead-on, growing smoothly with lateral distance). So the OLD relative rule can
never let a line win once real geometry sits behind it -- implementing the ruling literally
(unconditional Mover-over-polygon) would have reintroduced Brush803's exact regression, since
Brush803's offending line was that SAME Mover's outline.

Reported the conflict with concrete pixel evidence; owner's resolution: add an **absolute ~5px
screen-distance cutoff** (UED22's own disassembly-confirmed fixed hit-test box, `GUI-PARITY.md`'s
"Click/hit-detection algorithm") scoped only to a Mover-outline-vs-polygon pairing, replacing the
relative rule for that pairing alone. A Mover's outline wins over a polygon hit if it's within 5px
of the click, regardless of the polygon's own distance; every other pairing (ordinary brush
wireframe, actor vs. Mover) keeps the pre-existing relative rule untouched.

## Fix

`web/src/scene/selection.ts`'s `HitCandidate<T>` gains optional `isMoverLine`/`isActor`; `pickHit`
gains a `moverBeatsPoly` branch (Mover line wins within `MOVER_LINE_HIT_BOX_PX = 5` when the
competing precise hit isn't an actor) ahead of the existing relative rule. `tapSelect.ts` computes
the two flags per candidate: `isMoverLine` from membership in `moverOutlineObjects` (already a
separate candidate group from ordinary `brushObjects`); `isActor` for a marker-sprite or mesh-actor
pick-mesh hit (a Mover's own solid poly, in Movers:on mode, is a POLYGON for this purpose --
selected exactly like any other brush poly, per the ruling's explicit scope).

## Verification

5 new `pickHit` unit tests (win within the box, Brush803-preserved outside the box, the exact `<=`
boundary, the actor carve-out, an ordinary-line scope check) plus the full frontend suite, 328/328
green.

Live-verified independently twice (this session, then a review subagent with its own separate
backend/ports and its own click coordinates), both on `showcase_bar`'s `DeusExMover4`:
- Obscured Mover outline now selects the Mover: 165/167 isolated sweep clicks (this session,
  deselecting between clicks) + 12/12 (review); the sweep's 2 "misses" were the actor carve-out
  correctly firing (`Light199`, a point actor, at those exact pixels).
- Determinism: 30/30 repeated clicks at the same obscured pixel.
- Brush803 preserved: 6/6 genuinely-interior clicks (this session) + a clean bounded-cutoff shape on
  a 4px-step sweep across the doorway (review) -- the Mover wins only in narrow ~8px bands right at
  its own edges, `Brush803` wins solidly in between.
- Actor beats Mover outline within the box: 20/20 (this session) + a contiguous 1px-grid band at the
  true boundary (review) -- both confirm the `!isActor` carve-out.
- Ordinary (non-Mover) brush wireframe selection, unrelated locations: unaffected in both passes.

## Pre-existing, unrelated finding from review (not fixed here, not blocking)

A **selected** brush's or Mover's own bold selection ring (`BrushOutlines.tsx`'s `BoldRing`) is only
wired into the perspective-pane raycast candidate set in wireframe mode (`groupRef`, gated
`mode === 'wireframe'` in `Viewport3D.tsx`/`OrthoViewport.tsx`) -- so in perspective mode, once a
brush or Mover is selected, its own highlighted ring becomes unclickable there (falls through to
whatever's behind it). Predates this change; not touched by it. Not filed as a separate board item
here -- worth a look if a future report describes "can't re-click a selected brush's own outline in
perspective mode."

`web/src/scene/selection.ts`, `web/src/scene/tapSelect.ts`, `web/src/scene/selection.test.ts`.
