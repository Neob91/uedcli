+++
priority = "p3"
kind = "implement"
summary = "`actor find --overlapping-bbox X0,Y0,Z0,X1,Y1,Z1` — region-grab (AABB INTERSECTS a box)"
+++

# `actor find --overlapping-bbox X0,Y0,Z0,X1,Y1,Z1` — region-grab (AABB INTERSECTS a box)

Shipped: `writes.aabb_intersects` + `--overlapping-bbox` find filter, edge-inclusive, ANDs with the
other filters (no exclusion with `--within-bbox`).
