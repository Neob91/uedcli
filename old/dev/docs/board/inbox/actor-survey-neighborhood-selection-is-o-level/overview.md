+++
priority = "p1"
kind = "debug"
summary = "Picking the neighborhood costs 855ms per survey on a real level; the CSG solve costs 8ms."
+++

# actor survey neighborhood selection is O(level) and dominates the csg tier

`build_context` spends nearly all of its time choosing WHICH brushes to solve, not solving them.
Measured on the shipped `wanchai` trunk (2288 actors), median over 10 randomly sampled brushes
(`_scratch/t13r6/build_breakdown.py`):

```
one `neighborhood` pass alone                     408.0 ms
neighborhood + near_brushes + nearby_point_actors 855.1 ms
solve_world_probe + csg_faces                       7.6 ms
```

The mechanism: `neighborhood`, `near_brushes` and `nearby_point_actors` each walk the WHOLE
`level.order` and call `region_of` on every actor, which calls `writes.actor_bounds` — a full
Decimal transform of every vertex of every brush in the level. Three whole-level passes per survey,
and `near_brushes` calls `neighborhood` again internally, so the level is walked four times in all.

This is the real budget problem for `actor survey`, not either csg relation. The spike's target is
6 ms median / 46 ms worst for the entire tier; `crosses` measures at 0.8 ms median and `touches`
(round 6) at 6.5 ms median on the same real content, while selection is three orders of magnitude
over.

Pre-existing and untouched by Task 12/13 — this is Task 7's `neighborhood`. Likely fixes, none
chosen here: memoize `region_of`/`actor_bounds` per actor for the life of a survey (the same actor's
box is recomputed four times), compute the candidate boxes in float once per level rather than in
Decimal per survey, and have `near_brushes` filter the list `neighborhood` already built instead of
rebuilding it.

**Note** (final whole-branch review of `actor-survey-and-relation`): `contains_facts_for`'s
`containment_winner` rebuilds a whole-level trunk-order dict (`{n: i for i, n in
enumerate(ctx.level.order)}`) per candidate target, compounding this item slightly on any survey
with multiple competing containers. Minor next to the four whole-level passes above; worth folding
into the same fix.
