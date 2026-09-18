+++
priority = "p0"
kind = "debug"
summary = "the 5px mover-wireframe hit-box cutoff only gates a win against a competing poly hit -- it's unbounded when nothing else is behind the click"
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
