+++
priority = "p0"
kind = "debug"
summary = "FIXED -- the 5px mover-wireframe hit-box cutoff now also gates the no-competing-poly fallthrough, not just moverBeatsPoly"
+++

# 5px mover-wireframe cutoff doesn't apply when there's no competing poly

Owner report, live: "When I click many pixels away from wireframe, it still gets selected. I need to
move far away, like 40px or sth sometimes." Confirmed as a real, specific bug, not a units mistake.

## Root cause (confirmed by code read, not guessed)

`web/src/scene/selection.ts`'s `pickHit` (from `mover-wireframe-should-outrank-polys-not-actors`,
`5552eab3`) applies `MOVER_LINE_HIT_BOX_PX = 5` (a genuine screen-pixel cutoff -- `screenX`/`screenY`
are real CSS-pixel coordinates computed in `tapSelect.ts` via NDC projection scaled by
`rect.width`/`rect.height`, confirmed correct, NOT a uu/world-space mixup) -- but ONLY inside the
`moverBeatsPoly` branch, which only runs `if (preciseHits.length > 0)` (there's a competing polygon
raycast hit at that exact pixel). When there's NO competing polygon hit at the click point (open
space, an angle/gap where nothing else registers), the function falls straight through to
`if (bestLine) return bestLine.value` with NO distance check applied at all.

Whether the Mover's line is even a raycast CANDIDATE in that fallback path is governed by a
completely different threshold: `tapSelect.ts`'s `raycaster.params.Line = { threshold: lineThreshold
}` -- a WORLD-SPACE (uu) admission threshold along the ray, unrelated to the 5px screen-space rule.
Converted to screen pixels, this threshold's effective size varies with camera distance/zoom, easily
reaching 40px+ or more at typical viewing distances -- exactly the reported symptom.

## Fix

The 5px screen cutoff needs to gate ANY Mover-line win, not just the one branch where it's racing a
polygon hit. When `bestLine.isMoverLine` and there's no competing precise hit close enough to force
the comparison, the code still needs to check `bestLineDistSq <= MOVER_LINE_HIT_BOX_PX ** 2` before
returning `bestLine.value` in the `if (bestLine) return bestLine.value` fallback path too -- not just
in `moverBeatsPoly`. If that check fails (click is genuinely far from the line in screen space), the
function should return `null` for that candidate rather than blindly accepting a stale-distance line,
though double check whether an ordinary (non-Mover) line should still be exempt from this specific gate
(this cutoff is scoped to `isMoverLine` per the original ruling, ordinary brush wireframes rely on
different, already-correct threshold-based logic per `wireframe-brush-selection-should-hit-test-lines`
-- don't change that path).

## Where to look

`web/src/scene/selection.ts`'s `pickHit` (the `if (bestLine) return bestLine.value` line at the very
end, and the `moverBeatsPoly` block above it) -- read both together, this is likely a small, precise
fix. `selection.test.ts` already has unit tests for `pickHit`'s Mover-line cases from the original fix
-- add a new one covering "Mover line is the only candidate, no competing poly, click is far (>5px)
from the line" and confirm it currently (wrongly) returns the Mover before the fix, correctly returns
null/nothing after.

## Repro

1. Frame a Mover whose outline is drawn over/through other geometry (any distance from camera where
   its raycast line-threshold in screen-pixel terms exceeds ~5px -- likely most normal viewing
   distances).
2. Click a point on screen that's NOT near the Mover's line at all, but where nothing else (no
   polygon) registers a hit either (open space/gap/angle).
3. Expected: nothing selected (or whatever's genuinely closest, if anything). Actual: the Mover gets
   selected anyway, sometimes from 40px+ away.

## Fix (implemented)

`pickHit` (`web/src/scene/selection.ts`) gains an `else if` right after the `preciseHits.length > 0`
block: when there's no competing precise hit at all and the winning line is a Mover line farther than
`MOVER_LINE_HIT_BOX_PX` (5px) from the click, return `null` instead of falling through to
`if (bestLine) return bestLine.value`. `moverBeatsPoly` (competing-poly case), ordinary (non-Mover)
lines, and the actor carve-out are all untouched -- the new branch only fires when
`preciseHits.length === 0` and `bestLine.isMoverLine`.

5 new unit tests in `selection.test.ts`: no-competing-hit far miss, exact 5px boundary win, 6px miss,
close win, and an ordinary-line scope check (unaffected). Full vitest suite: 333/333 (was 328).

## Live verification

Headless Chromium, real synthetic clicks, `showcase_bar`'s `DeusExMover4` (wireframe mode, camera
zoomed in close on the door so the raycaster's fixed world-unit line threshold subtends a large
screen-pixel radius -- the actual mechanism behind the reported "40px" symptom). Found a real
no-competing-poly gap directly above the mover's own outline (the door lintel has a gap before
`Brush803`'s wall starts further up) and mapped the exact before/after boundary there, 5 repeated
clicks per offset:

- **Before (bug, old code)**: offsets 1-10px from the line all wrongly select `DeusExMover4`, with NO
  competing polygon underneath (confirmed by pixel color: nothing rendered there); only at 15px does
  `Brush803`'s wall become a real competing hit and correctly win.
- **After (fixed)**: offsets 1-4px still select `DeusExMover4` (intended case preserved); 5px onward
  returns nothing (a hair under the nominal 5px cutoff due to the line's own sub-pixel rendering
  center, not a bug -- a separate boundary test in the TOP ortho view, with an exactly-placed line,
  confirmed the precise `<=5 wins, 6 doesn't` cutoff with no sub-pixel fuzz); 15px+ correctly selects
  `Brush803`, unchanged from before.
- **Regression checks**: clicking directly on the mover's outline where it's adjacent to the door
  lintel (`moverBeatsPoly` path) and clicking an ordinary (non-Mover) brush wireframe line both gave
  IDENTICAL results before and after the fix (`Brush803` and `Brush820` respectively, both cases governed by
  code this change doesn't touch).

Independently re-verified by a review subagent with its own backend/vite instance: confirmed the code
change, all 58 `pickHit` tests, the full 333-test frontend suite, and the `moverBeatsPoly`/ordinary-line
paths unaffected across ~500 clicks on several camera framings. It could not reproduce the exact
"40px" no-competing-poly gap live in its own chosen camera angles (this mover's door is flush with
walls in most directions/angles; the specific lintel gap above the door was needed) but confirmed the
distance-math unit tests exercise the same code path directly and pass. No bugs found in the fix; no
changes made in review.

`web/src/scene/selection.ts`, `web/src/scene/selection.test.ts`.
