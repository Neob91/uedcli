+++
priority = "p1"
kind = "debug"
summary = "LAST geometry-body byte gap = `bspcsg.rs` point-pool / CSG-transient accounting (detector is now FIXED) — 2026-07-18"
+++

# LAST geometry-body byte gap = `bspcsg.rs` point-pool / CSG-transient accounting (detector is now FIXED) — 2026-07-18

p1 **LAST geometry-body byte gap = `bspcsg.rs` point-pool / CSG-transient accounting (detector
is now FIXED) — 2026-07-18.** The `bspoptgeom.rs` detector had a REAL byte-parity bug: it read the
`0x3276a` `??TFVector` call as a plain edge divide and transcribed the ring scan as an *along-edge*
projection `E·(P-Pcur)/|E|`, so it rejected every deep-interior T-junction and welded ~22. That call
is `FVector::operator^` = the CROSS product — the real test projects onto `E×N` (edge × plane normal)
= the **perpendicular** distance from the edge line. Re-decoded & fixed (`tjunction_edge`, decode
§6b): castle now welds **1012**, matching **959/975** of the editor's inserter-oracle welds
(permutation-invariant on (node-plane, welded-P)); golden stays a fixpoint; `bin/test` green (1429).
**What's LEFT (this item):** native **1797 points / 10418 verts / NumSharedSides 2728 / Σnv 5533** vs
editor **2035 / 16163 / 2739 / 5496**. The live ring geometry MATCHES (1549/1555 distinct live coords
identical, 6 sub-0.05uu FP aliases, +37 over-weld). The whole residual is point-pool bookkeeping:
native's repartition **clears + rebuilds** the Points pool from the live soup (→1797, missing 485
editor orphan-CSG coords, +247 spurious z=−12/−80 coords that drive the +37 over-weld), while the
editor does NOT clear (keeps ~2091 pre-opt incl. transient orphans, merges 56 → 2035). Native's raw
*uncleared* CSG pool is ~6627 (3× editor) — `bspBrushCSG` leaks transient points from rolled-back
grazes, so neither clear (1797) nor no-clear (6627) matches 2091. **Fix = stop `bspcsg.rs`'s
incremental-CSG transient-point leak so the non-clearing repartition pool lands at 2091 pre-opt /
2035 post-opt, WITHOUT perturbing the byte-exact node/surf/vector tree** (every `surf.pBase`/
`vert.iVertex` is a pool index — high entanglement, hence deferred rather than forced). Do NOT loosen
the detector to force counts — it is validated correct. (decode §6a/§6b.)
