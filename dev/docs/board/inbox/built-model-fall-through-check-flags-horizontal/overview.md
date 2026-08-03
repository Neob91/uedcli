+++
priority = "p3"
kind = "owner-question"
summary = "Fall-through check flags any floor-facing PF_Portal surf; a horizontal zone portal is a false positive"
+++

# Built-model fall-through check flags horizontal zone portals as PF_Portal floors

The materialize built-model check (`done/bsp-issue-detector`, `bsp.builtmodel._fall_through_floors`)
reports a fall-through ERROR for a floor-facing surf carrying `PF_NotSolid`/`PF_SemiSolid`/`PF_Portal`
— the owner's 2026-08-03 definition, implemented as given.

Consequence worth an owner call: a legitimate HORIZONTAL zone portal (a water surface, a flat zone
divider) is a floor-facing `PF_Portal` surf, so it is reported as an ERROR fall-through though it is
intentional. Advisory-only (stderr, rc 0), so the cost is a noisy false positive, not a failed build.

If the owner wants it narrowed: drop `PF_Portal` from the floor check (keep NotSolid/SemiSolid), or
skip a portal already marked an intended zone boundary. No change made — current behavior matches the
stated design. Related: `_FLOOR_NORMAL_Z = 0.7` (the ~45° floor cutoff) is a judgment the design did
not specify, documented in a code comment only.
