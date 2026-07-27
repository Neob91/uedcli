+++
priority = "p2"
kind = "implement"
summary = "N-1 residual: `bspMergeCoplanars` (§7.1) coplanar-face union"
+++

# N-1 residual: `bspMergeCoplanars` (§7.1) coplanar-face union

p2. The off-grid
wedge golden (case b) fails Tier-S: native emits ~2× surfs (un-merged coplanar fragments where a
brush clips a wall into pieces the editor merges). `build.rs merge_coplanars` is currently a NO-OP
(identity) — it happens to match a/c/d/e (disjoint or seam-split faces stay separate), but case b
needs the real edge-adjacent coplanar polygon union + a `RemoveColinears` re-pass. Also the
split-minimizing `FindBestSplit` variant (documented in `build.rs`) substitutes for the later
merge/opt passes; a faithful merge would let `FindBestSplit` revert to the exact engine score.
Tracked by xfail `test_case_b_offgrid_wedge_residual`.
