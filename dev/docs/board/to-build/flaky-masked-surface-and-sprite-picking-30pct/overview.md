+++
priority = "p0"
kind = "debug"
summary = "masked-surface and point-actor sprite click-picking now select the object behind ~30% of the time"
+++

# Flaky masked-surface / sprite picking (~30% miss)

Two symptoms reported live by the owner, both newly appearing after fixes landed earlier in this
same campaign session:

1. The 3 masked surfaces from `poly-highlight-not-visible-for-brush116-0`
   (`Brush100:0`/`Brush106:0`/`Brush111:0`) now select the wall BEHIND them roughly 30% of the time
   when clicked, instead of the surface itself.
2. Point-actor sprites (fixed in `point-actor-sprite-picking-ignores-sprite-alpha`) now also select
   whatever's behind them roughly 30% of the time, instead of the actor.

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

## Scope

Root-cause and fix ONLY this regression. A separate item
(`gui-pick-selection-regression-test-suite`) covers building durable synthetic-level test coverage
for this and every other click/selection scenario from this campaign -- don't build that suite here;
this item is scoped to the fix itself (with whatever minimal regression test proves the fix, same as
every other item in this campaign).
