+++
priority = "p?"
kind = "unknown"
summary = "bspcsg FindBestSplit param fix + `bspOptGeom` wire-in"
+++

# bspcsg FindBestSplit param fix + `bspOptGeom` wire-in

— BUILT 2026-07-17 (spec
`specs/2026-07-17-findbestsplit-params-fix.md`). Repartition path now uses Balance=12/PortalBias=0/
Opt=GOOD (stride `max(NumPolys/10,1)`), threaded through `split_poly_list` so the temp-brush convex
partition keeps its invariant OPTIMAL/50/70; `bspOptGeom` runs at the build tail after `bspRefresh`.
MEASURED effect (full castle vs editor 1156/485/2035/16163/2739): over-fragmentation FIXED, nodes
1263→**1028**, surfs 454, points 1579, `NumSharedSides` 0→**940**, verts 3604→4040, solidity 98.96%.
Gates green (cargo 33, `bin/test` 1269). **Remnants (still open, see inbox):** node-for-node prefix
still 0 — first-divergence is the §8.3 cospatial-facing-in surplus face (needs a live differential
trace); and pass-1 T-junction insertion under-fires (verts 4040 vs 16163).
