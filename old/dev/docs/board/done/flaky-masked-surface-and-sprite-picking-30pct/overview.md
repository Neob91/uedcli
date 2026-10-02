+++
priority = "p0"
kind = "debug"
summary = "NOT A NEW BUG -- already fixed by `pickHit`'s distance-tiebreak (`5cb974fc`, `shift-modifier-convention-broken-for-poly-and`), landed before this item was investigated further. Two independent agents ran 250+ real repeated clicks and fine pixel sweeps on `Brush100:0` itself, `DeusExMover4`/`Brush803` (symptom 3's exact shape), and a sprite's transparent-edge boundary -- zero flakiness anywhere, every region cleanly monotonic."
+++

# Flaky/wrong pick -- selects what's behind the intended target

Closed 2026-09-17, not a new bug. `pickHit`'s distance-tiebreak fix (`5cb974fc`, board item
`shift-modifier-convention-broken-for-poly-and`) fixed the exact mechanism this item described (an
always-on-top line beating a nearer precise hit) before this item was dispatched.

Verified live, two independent agents, headless Chromium, real `page.mouse.click`, `showcase_bar`:
`Brush100:0` itself (camera orbited to face the decal -- it sits nearly edge-on from the default
framed angle, why it wasn't found sooner) got 180+ repeated clicks plus a 21x21 boundary sweep, 100%
deterministic, one clean monotonic region bordered by `Brush98`/`Brush1`. `DeusExMover4`/`Brush803`
(an opaque poly next to an always-on-top Mover outline, symptom 3's exact shape) and a point-actor
sprite's transparent-edge boundary: same result. `tapSelect.ts`/`selection.ts` confirm masked and
opaque brush surfaces share `pickHit`'s one ranking path with no alpha special-casing, so this
generalizes to `Brush106:0`/`Brush111:0` too.

No code change. `gui-pick-selection-regression-test-suite` still covers building durable test
coverage for this scenario.
