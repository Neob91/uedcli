# Confirm two spec changes the collision-tolerance spike introduced from measurement

## Context

The owner ruled "include cylinder for crosses" and asked for a real measured tolerance.
`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/` measured every collidable actor in 24
shipped level trunks and found **no tolerance exists**: not one of 1936 real Deus Ex actors
penetrates resolved solid by less than 0.01 uu, the smallest real penetration is 0.043 uu, and from
there the distribution is continuous to 64 uu. There is no float-noise band to absorb, and a
tolerance large enough to suppress the by-design cases (p90 = 11 uu) would suppress mistakes too.

Two changes went into the spec in place of a tolerance. Both are the spike's own proposals, not
things the owner asked for — flagged here rather than folded in silently.

1. **Source gate tightened from `bCollideActors` to `bCollideActors && bBlockActors`.** The spec's
   original gate admits trigger volumes — `DataLinkTrigger` at `CollisionRadius` 520, `FlagTrigger`
   at 630, `LaserTrigger`, `Teleporter` — which set `bCollideActors` so they can be touched, block
   nothing, and are deliberately sized to span rooms including their walls. They are 598 of the 1936
   and carry the whole deep tail; excluding them drops the worst by-design overlap from 436 uu to
   64 uu and p90 from 52 uu to 11 uu. `bCollideWorld` was considered and rejected: it drops 279
   genuinely physical wall- and ceiling-mounted props (`HKHangingLantern2`, `SecurityCamera`,
   `Keypad1`, `AlarmUnit`, `ClothesRack`) whose `bCollideWorld` is false only because they are
   mounted and never fall.

2. **A `crosses(<depth>uu)` annotation** when the source is a collision extent. Under the tightened
   gate ~11% of blocking actors are still genuinely inside solid by ~6 uu at the median, by design.
   Those lines are true and stay; the depth is what lets a reader tell 8 uu of flush mounting from
   60 uu of misplacement. It is the only annotation any `csg`-tier line carries.

Both are reversible in one edit if the answer is no. Option 1's fallback is the original
`bCollideActors`-only gate (with the measured noise); option 2's is a bare `crosses` line.

## Answer

<!-- Empty = open. -->
