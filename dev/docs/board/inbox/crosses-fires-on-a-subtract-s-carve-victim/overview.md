+++
priority = "p1"
kind = "debug"
summary = "csg `crosses` claims a Subtract carved its own victim's matter, blocking that pair's `touches`"
+++

# crosses fires on a Subtract's carve victim

`actor_survey.penetration_depth` reports a `crosses` fact for the Add a Subtract carved. The spec
says that pair is `carves` + `touches` and never `crosses`: "legitimate carving never leaves a
violated *surviving* face for `crosses` to name (the boundary retreats to wherever the carve
stopped, and what remains of `X` sits flush against it — that is `touches`)"
(`actor-survey-and-actor-relation-csg-resolved/spec.md:443-445`).

Measured, on committed fixtures:

| fixture | reported | what it should be |
|---------------------------------------|---------------------------------|---|
| `blind_pocket_in_a_wall` | `Wall --crosses--> Pocket` (224uu) | `Pocket --carves--> Wall`, `Pocket --touches--> Wall` |
| `two_rooms_side_by_side` | `Rock --crosses--> RoomA` (462uu) | `RoomA --carves--> Rock`, `RoomA --touches--> Rock` |
| `a_doorway_through_a_wall_seam` | `WallA --crosses--> Doorway` (192uu) | `Doorway --carves--> WallA`, `Doorway --touches--> WallA` |

**The doorway row is the one that makes this urgent**, and it was found while reviewing Task 13
round 6. It is a wall built from two blocks with a door cut through the join — the single most
ordinary piece of geometry this feature will ever see, far commoner than the blind pocket already on
file. Measured on the committed `a_doorway_through_a_wall_seam` fixture:

```
pair_touches(WallA, Doorway) = True          # the contact predicate is right
crosses_facts_for(WallA)     = [('WallA', 'Doorway', 192.0)]
touches_facts_for(WallA)     = [('WallA', 'WallB')]      # WallA <-> Doorway suppressed
touches_facts_for(Doorway)   = []                        # the doorway touches nothing at all
```

So on an ordinary doorway the csg tier reports that the door opening CROSSES the wall it is cut
through, by 192uu, and reports no `touches` for it in either direction. Nothing about the walls
interpenetrates; the depth is the surviving thickness of the wall either side of the hole.

The mechanism: for a face the Subtract authored, `face_outward_sign` puts the solid on the side away
from the carve — which is the source Add's OWN remaining bulk. `penetration_depth` then measures how
far the Add reaches into that solid and calls it penetration, though the Add is the solid. The
`Rock`/`RoomA` row is the ordinary case (solid rock, a room carved into it), so this fires on
essentially every room in a real level.

Two consequences, both live:

- The depth number is the length of the source's surviving bulk, not a penetration.
- `touches` is suppressed for every such pair: `_is_flush` refuses any pair `crosses` claims, which
  is what the spec requires of it. `uedcli/tests/test_actor_survey.py
  ::test_touches_fires_for_a_blind_pockets_carve_victim` is a strict xfail pinning that; the contact
  probe itself names `{Wall, Pocket}` on all five of `Pocket`'s faces, so `touches` is right and
  only the gate is wrong.

`niche_carved_into_wall` escapes the same false positive only by accident: `csg_faces` dedupes
`Niche`'s x=64 plane to a fragment that happens to lie outside the wall, so the footprint test finds
no overlap. Keeping a different fragment would flip that pair's answer — the soundness violation the
spec's own truncation section forbids ("a redundant coplanar face appearing or vanishing must not
change a reported fact").

A second finding in the same gate: `touches_facts_for` excludes any pair `crosses` claims without
asking whether the source could produce a `crosses` fact at all. A Subtract is never a `crosses`
source, so for it there is nothing to be exclusive with, yet its penetration against another actor's
face still suppresses `touches`.

(The related question this item used to carry — whether a Subtract `touches` everything standing in
its void, or only what bounds it — was settled in Task 13 round 6: only what bounds it. A Subtract
is attributable to a contact only where the plane is its own carve boundary AND the carve really
removed something there, so an Add standing free in a room's void is not a contact at any distance.
The measurements that used to sit here are superseded by that.)

Owner's call: whether `crosses` should exclude a carve victim, and what its depth number means if it
should not.

**Raised to p1** (final whole-branch review of `actor-survey-and-relation`): reproduced live at HEAD
on ordinary shipped geometry, not just fixtures (`WallA --crosses(192uu)--> Doorway`,
`Rock --crosses(462uu)--> RoomA`), confirming this is not a fixture artifact. Also found an instance
this item's own rows do not cover: `Rock --crosses(1.47e+03uu)--> Crate`, an Add-to-Add pair where
the source's OWN matter was later reduced by an unrelated Subtract — `penetration_depth` sources from
`decompose_convex`'s AUTHORED cells, so a source whose matter a later Subtract removed still reports
`crosses` against a neighbor, independent of the carve-victim mechanism described above. Add this row
before this item is worked.
