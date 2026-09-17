+++
priority = "p0"
kind = "debug"
summary = "click-picking selects the object behind the intended target -- masked surfaces, sprites, and now confirmed on a plain opaque poly clicked well inside its bounds"
+++

# Flaky/wrong pick -- selects what's behind the intended target

Symptoms reported live by the owner, all newly appearing after fixes landed earlier in this same
campaign session:

1. The 3 masked surfaces from `poly-highlight-not-visible-for-brush116-0`
   (`Brush100:0`/`Brush106:0`/`Brush111:0`) now select the wall BEHIND them roughly 30% of the time
   when clicked, instead of the surface itself.
2. Point-actor sprites (fixed in `point-actor-sprite-picking-ignores-sprite-alpha`) now also select
   whatever's behind them roughly 30% of the time, instead of the actor.
3. **A plain, non-masked, opaque shelf poly** clicked ~4px from its edge but genuinely INSIDE its
   visible bounds (owner confirmed explicitly: "I actually CLICKED INSIDE THE SHELF POLY" / "It was
   like 4px away from the edge, INSIDE the shelf poly. And it selected what's behind") also selects
   the object behind it.

**Symptom 3 changes the diagnosis.** It's NOT alpha/masking-specific (the shelf poly is plain opaque
geometry, no alphaTest/masked-texture path involved at all), and a click 4px inside a poly's visible
bounds is not an edge-grazing/sub-pixel raycast-miss case either -- a plain single-ray geometric
intersection test against real mesh geometry should hit solidly there. This points away from the
alpha-sampling suspects below and toward a general HIT-RANKING bug: the raycast likely DOES hit the
correct (front) poly, but something ranks a different (behind) candidate ahead of it. Prime new
suspect: `nearestScreenHit` (added in `wireframe-brush-selection-should-hit-test-lines` /
`mover-near-brush803-unclickable-in-wireframe-2d`) -- if its screen-space ranking logic isn't scoped
tightly enough to lines/wireframe candidates, it could be misranking ordinary opaque poly hits too.
Verify whether this fix's ranking is applied more broadly than intended before assuming the
alpha-sampling paths are involved at all.

**Not yet established whether this is random (non-deterministic) or deterministic-but-positional**
(owner's own caveat: "could be deterministic, not confirmed to be random") -- e.g. it might be that
clicks landing on certain sub-pixels/regions of the target ALWAYS fail (a systematic UV/coordinate
offset or off-by-one in the alpha sampling, or a boundary condition in the masked-surface pick
rejection) while others always succeed, which would look like an aggregate "~30% miss rate" across
varied real clicks without any single click itself being flaky. Do NOT assume timing/jitter/
non-determinism going in. First investigation step: fire synthetic clicks at the EXACT SAME screen
coordinates many times in a row (does the result ever vary for one fixed point?) AND at a grid of
nearby coordinates across the target (does failure correlate with position?) to tell the two
hypotheses apart before theorizing about a mechanism.

Primary code suspects:
- `tapSelect.ts`'s `isTransparentPixel` (added in `point-actor-sprite-picking-ignores-sprite-alpha`)
  -- alpha-sampling machinery for sprite picking, prime suspect for the sprite symptom.
- Whatever handles masked-surface pick rejection -- check for any alpha-based logic that may have
  been added or changed near the masked-surface path.
- `nearestScreenHit` (added in `wireframe-brush-selection-should-hit-test-lines` /
  `mover-near-brush803-unclickable-in-wireframe-2d`) -- screen-space hit ranking; check for
  interaction with masked/thin-decal geometry specifically, since a decal poly and the wall behind it
  are exactly the kind of close-in-screen-space overlapping candidates that fix's ranking logic
  touches.

## Repro

1. `showcase_bar` level. Click `Brush100:0` (or `Brush106:0`/`Brush111:0`) repeatedly -- expect it to
   sometimes select the wall behind instead.
2. Click a point-actor sprite repeatedly -- expect it to sometimes select whatever's behind it.
3. Click a plain opaque shelf poly a few pixels in from its edge (still clearly inside its visible
   footprint) -- expect it to sometimes select the object behind it instead of the shelf poly itself.

## Related fix landed (2026-09-17, not yet verified against THIS item's own repro)

`mover-not-selectable-via-wireframe-click` (`done/`) fixed exactly the over-broad-`nearestScreenHit`
mechanism symptom 3 points at: the old ranking always used screen-distance across EVERY hit once
`hits.length > 1`, including two PRECISE (mesh) hits along the same ray -- which can't be
disambiguated by screen distance at all (two points on one ray reproject to the same pixel), so the
"winner" was effectively picked by sub-pixel floating-point noise. `selection.ts`'s new `pickHit`
(unit-tested) now takes the depth-nearest precise hit outright unless a genuine always-on-top line
wins the ranking. This class of bug plausibly explains symptom 3 (plain opaque poly) directly, and
possibly symptoms 1-2 too if the masked-surface/sprite alpha-rejection paths were hitting the same
precise-vs-precise coincidence rather than (or in addition to) an alpha-sampling bug. NOT verified
against this item's own repro (`Brush100:0` etc., a real sprite, the reported shelf poly) -- re-test
with `pickHit` before assuming this is closed; the alpha-sampling suspects below may still be real,
separate issues even if the hit-ranking fix helps.

## Scope

Root-cause and fix ONLY this regression. A separate item
(`gui-pick-selection-regression-test-suite`) covers building durable synthetic-level test coverage
for this and every other click/selection scenario from this campaign -- don't build that suite here;
this item is scoped to the fix itself (with whatever minimal regression test proves the fix, same as
every other item in this campaign).
