+++
priority = "p2"
kind = "implement"
summary = "The surf/vector-ORDER half is done; the remaining half is the point-pool byte order."
+++

# Native point-pool byte-ORDER (follow-up to the pBase fix)

native point-pool byte-ORDER (follow-up to pBase fix, §82 §10.18/§10.19, 2026-07-18)` —
the surf/vector-ORDER half is **DONE** (§10.19): the editor KEEPS the incremental-CSG surf pool (95
brushes → 95 contiguous actor runs) while native cleared+rebuilt it in repartition order (322 runs);
a post-build canonical re-sort (`reorder_surfs_canonical`+`rebuild_vector_pool`, `bspcsg.rs`) landed
Surfs order + node.iSurf byte-exact + Vectors ORDER 26/26 (residual Vectors bytes = 1–3 ULP normal
FP, out of pool scope). What REMAINS is the POINT pool: (a) native carries **26 UNREFERENCED points**
(the +26 overshoot — its `bsp_refresh` skips point compaction; the editor's drops them → count/length
become byte-exact 2035/24422). Both landed in §10.20: `reorder_points_canonical` (`bspcsg.rs`) drops
the 26 orphans (Points 2061→2035, section length byte-exact) and re-lays the survivors bases-first
then rings (matching the editor's 484-base leading block) → whole-body positional match 29.6%→**43.6%**,
leading 132-base block byte-EXACT. REMAINING (⚠️ deeper follow-on, NOT forced): the editor's exact
intra-block sub-order (base #132+, ring order) is a `bspRefresh` reachability-DFS-compaction artifact
of the PRE-compaction pool indices — not reconstructable from the final model (native's own incremental
pool scored 1/2035; the clean bases-then-rings rule caps at the editor's own 384/2035). Plus an
~84-point sub-0.002 FP-value floor. To close it: reproduce the editor's incremental pre-compaction
point pool + its bspRefresh point-compaction DFS order (out of the current pool-numbering scope).
