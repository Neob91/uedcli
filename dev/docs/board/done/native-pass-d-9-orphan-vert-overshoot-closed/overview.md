+++
priority = "p?"
kind = "unknown"
summary = "Native Pass-D +9 orphan-vert overshoot CLOSED"
+++

# Native Pass-D +9 orphan-vert overshoot CLOSED

(`zones.rs` `fix_ring`, 2026-07-18, §70 §12).
Native entered `bspOptGeom` with +9 vert slots (10527 vs editor 10518), carried to Verts 16172 vs
16163. Localized (`preopt_runs2.py`) to two orphan runs (+3 @5596, +6 @7591), then pinned via a new
`bspaddnode_ring_oracle.py` (breakpoints editor `bspAddNode`, logs per-ring `(ivp, nv)`) to
**exactly 3 spurious `[A,B,B]` orphan triangles** native's `clip_poly` emits that the editor's
`FPoly::Fix` (drop consecutive verts `< 0.002`) collapses below 3 and drops. Fix applies `FPoly::Fix`
to Pass-D orphan rings only (no node created ⇒ node-order/`tail_order` untouched). RAW
(`ground_truth_bytediff.py`): PRE-optgeom **10527→10518 = editor**; **Verts 16172→16163 = editor**;
Verts posmatch **24.8%→27.3%**; Nodes **91.6%→92.6%**; whole-body **42.4%→43.0%**. Guards intact
(soup 853/853, surfs 485, vectors 26, Points 2035/24422 first-diff @1586, NumSharedSides 2739
byte-identical, Bounds 484, LeafHulls 308/3866/1710, LightMap 484, nodes 1156/1156); `cargo test` 38,
offline **1744 passed**. **REMNANT (deferred, RE'd infeasible in-lane, §70 §12):** the surviving
orphan verts' `iVertex` still carry native's snapped indices, not the editor's stale pre-compaction
ones (which run up to 2642 — a transient CSG point numbering native never builds; reproducing it
conflicts with the `bspcsg.rs` pool clear + `reorder_points_canonical` Points-parity guard). Verts
section length-close (53860 vs 53866, −6 = compact-int width of smaller indices) but not
byte-identical.
