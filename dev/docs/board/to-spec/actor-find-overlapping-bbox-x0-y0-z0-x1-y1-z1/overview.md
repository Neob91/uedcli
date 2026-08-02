+++
priority = "p3"
kind = "implement"
summary = "`actor find --overlapping-bbox X0,Y0,Z0,X1,Y1,Z1` — region-grab (AABB INTERSECTS a box)"
+++

# `actor find --overlapping-bbox X0,Y0,Z0,X1,Y1,Z1` — region-grab (AABB INTERSECTS a box)

The looser companion to the built `--within-bbox` (full containment, `rationale/reported-coordinates.md`, 2026-07-24
21:44 UTC): match actors whose world AABB **intersects** the box, so a room shell / floor / wall that
straddles the box edge IS grabbed — better for "show me everything in this area" (feeding
`actor preview -`) than strict containment, which drops straddling brushes. Same machinery as
`--within-bbox`: a Decimal AABB predicate (`writes.aabb_intersects`, edge-inclusive) over
`writes.actor_bounds` in the dispatch find handler; reuse `parse_bbox`. Spec: the flag name/semantics,
whether it and `--within-bbox` can co-exist (they're distinct predicates, both single-valued), and the
L-brush AABB false-positive caveat (documented, not fixed — that's the `--precise`/`--within-brush`
follow-up in the parked board item `find-relational-predicates`). Deferred from the `--within-bbox` build per
Andrzej. (2026-07-24.)
