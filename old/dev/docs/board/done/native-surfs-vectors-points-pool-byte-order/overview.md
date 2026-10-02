+++
priority = "p?"
kind = "unknown"
summary = "Native Surfs/Vectors/Points pool byte-ORDER"
+++

# Native Surfs/Vectors/Points pool byte-ORDER

— BUILT 2026-07-18 (§82 §10.19-§10.20).
RE'd the on-disk pool order to native's repartition CLEARING the incremental-CSG surf pool (editor
KEEPS it and only compacts): a post-build `reorder_surfs_canonical`+`rebuild_vector_pool`+
`reorder_points_canonical` (`bspcsg.rs`) restores editor order. Results: node `iSurf` byte-EXACT,
surf `iBrushPoly`/`polyFlags`/vector-refs byte-EXACT, Vectors ORDER 26/26, Points count/length
byte-EXACT (2035/24422, +26 orphans dropped), surf `pBase` mismatch 477→112, whole-body positional
match **29.2%→43.6%**; node isomorphism preserved (1156/1156). Guards intact; cargo 37 + offline
1701 green. **REMNANT (deferred, not pool-numbering lane):** Points intra-block sub-order (base
#132+, ring order) + orphan `iVertex` (Verts section) is a `bspRefresh` reachability-DFS point-
compaction artifact of PRE-compaction indices — not reconstructable from the final model — and is
further gated by the bspOptGeom vert-count weld divergence (16183 vs 16163, `bspoptgeom.rs` lane).
Residual Vectors bytes = 1-3 ULP normal-value FP (`fpoly` lane); surf `iActor`/`iLightMap` =
package-export / LightMap-array numbering (assembly / `light.rs` lanes).
