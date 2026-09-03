+++
priority = "p3"
kind = "debug"
summary = "Counts of stored NumVertices==0 nodes differ native vs golden on 7 levels, both directions; the 747 case is proven not Pass-D (no nv=0 emission) — likely 0.25-merge trim / incremental-CSG divergence downstream of other open mechanisms."
+++

# nv0-node count imbalance native vs golden is not Pass-D-born

Census 2026-09-03 (post `fill_ring_verts` + the Pass-D kill/retarget, both landed; harness:
`degen_census.py` extended with an nv==0 column — `_scratch/degen_census2.py` in the fix worktree,
re-derivable from the spike's census): native-vs-golden counts of stored `NumVertices==0` nodes
differ on 7 levels, in BOTH directions — native +1 on `03_nyc_747`, `06_hongkong_wanchai_garage`,
`15_area51_entrance`; golden +1 on `00_trainingfinal`, `04_nyc_nsfhq`, `12_vandenberg_gas`,
`14_oceanlab_lab`. `04_nyc_underground` and `06_hongkong_helibase` match exactly (their nv0 nodes
are the legit `merge_near_points` ring-trim ones, finding 2 of
`spikes/2026-09-03-verts-points-residual`).

Not the Pass-D mechanism: on 747 a `UEDCLI_PASSD_DUMP` build AT `c228e60` (before the kill guards,
when a ringless landing still printed `len=0`) showed ZERO `len=0` emissions, and the lone native
nv0 node (1177, `isurf=104`, early index) sits outside the Pass-D fragment region — so
it comes from the incremental-CSG fill guard or the 0.25-merge trim diverging, downstream of the
still-open node-count mechanisms on those levels (Active-CsgOper outcome, f32 ship). Worth
re-checking after those close rather than chasing directly.
