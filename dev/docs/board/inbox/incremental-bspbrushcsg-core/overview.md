+++
priority = "p1"
kind = "implement"
summary = "Incremental `bspBrushCSG` core (`build_geometry_bspcsg`, `uedcli-native/src/bspcsg.rs`) — §8.1 split-and-re-add + §8.2 Subtract-reverse LANDED; residual now at REPARTITION, not the filter"
+++

# Incremental `bspBrushCSG` core (`build_geometry_bspcsg`, `uedcli-native/src/bspcsg.rs`) — §8.1 split-and-re-add + §8.2 Subtract-reverse LANDED; residual now at REPARTITION, not the filter

p1. Default `build_geometry` untouched, full suite green (1242
passed / 1 skipped / 2 xfailed; 30 cargo tests). What changed this increment (decode
`sections/82-bspbrushcsg-port-decode.md §8`): (1) `filter_world_through_brush` replaced the old
clip-to-largest-fragment hack with the engine's SPLIT-AND-RE-ADD — the world face is filtered down
the brush's convex temp BSP (`build_brush_temp_bsp`), every bit31 outside cut-fragment is re-added
as a NODE_Plane node sharing the original surf, interior fragments delete the original; grazes roll
back; (2) §8.2 Subtract fix — dropped the LOOP-1 reverse, `leaf_func` now adds only on
{F_INSIDE,F_COPLANAR_INSIDE} and REVERSES at store time (descent keeps the outward normal); (3) the
repartition now rebuilds Points/Vectors (drops CSG-phase orphan points). Counts vs editor
(`harness/bspcsg_diff.py`, step 64): **nodes 1263 (ed 1156), surfs 437 (ed 485), points 1901 (ed
2035 — was 2509, now near-parity), verts 4945 (ed 16163), num_shared_sides 0 (ed 2739), bounds 0
(ed 484)**. The CSG SOUP is correctly fattened (pre-repartition verts 4914→**46058**, mechanism
verified: 1704 genuine cuts + 7696 correct rollbacks on the castle). Solidity vs oracle **98.43%
(step-64 on-grid)** — a DROP from the old clip's 99.35%. Investigation: ALL disagreements are
within 8u of a brush boundary face (zero interior/far leaks); they are grid-sensitive (offset grid
+13.37 → only 26 real >2u leaks vs 791 on-grid). BUT the editor's own golden model scores
**99.97%/100%** on the same harness, so the leaks are REAL, not a boundary-density artifact — the
residual is in the **MERGE/REPARTITION stage** (`bspMergeCoplanars`/`TryToMerge` §7c not
instruction-exact + `bspBuild`/`SplitPolyList` re-partition of the finer soup leaks at shared
boundaries; the pre-repart soup is 96.9%, repartition heals to 98.43% but not to the editor's 100%)
and the missing `bspOptGeom` (which gates the vert count to 16163 and is out of scope). **§8.3
coplanar IsCsg Outside-seed: RESOLVED & LANDED 2026-07-17.** The earlier blind attempt (measured
98.43→98.36, reverted) was wrong because the §7b pseudocode mis-assigned the FCoplanarInfo fields.
Full instruction-level disasm of `FilterEdPoly 0x32d91` + `FilterLeaf 0x33130` (see
`re-raw-zones/bspbrushcsg-filter-decode.md §7b`, now corrected) + a LIVE N=2 castle differential
(`subset_diff.py`) pinned it: `+0x20 FrontLeafOutside` is the OTHER-side descent seed (not a leaf
result), `+0x24 BackNodeOutside` is the classify `frontOutside`; each side gets the ordinary
SP_Front/SP_Back CSG adjust (`Out||csg` / `Out&&!csg`). Fix in `bspcsg.rs` (both `filter_*` and
`wtb_filter_*`): N=2 native 15→14 nodes = editor (surplus `(0,0,-1,0)` face now `FACING_IN`→dropped);
full-castle shared-plane multiset 867→971, node count 1028→1158 (editor 1156), solidity 98.96→98.99%.
