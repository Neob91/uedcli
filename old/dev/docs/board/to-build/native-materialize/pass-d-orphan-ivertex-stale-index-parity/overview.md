+++
priority = "p2"
kind = "implement"
summary = "Pass-D orphan `iVertex` stale-index parity"
+++

# Pass-D orphan `iVertex` stale-index parity

— the last Verts-section byte
residual. **The +9 orphan-slot COUNT half is DONE 2026-07-18 (`sections/70` §12): Verts 16172→16163
= editor.** The +9 was three spurious `[A,B,B]` orphan triangles native's `clip_poly` emitted that
the editor's `FPoly::Fix` drops — fixed by `zones.rs` `fix_ring` on Pass-D orphan rings. **What
REMAINS (RE'd infeasible in-lane, deferred):** the surviving orphan verts' `iVertex` still carry
native's snapped indices, not the editor's stale pre-compaction ones. Those stale indices run up to
**2642** (measured on `Test_Castle.dx`) — a transient CSG point numbering that peaked above 2643
during Pass-D and was compacted away. Reproducing it needs native to reconstruct the editor's whole
point-pool construction history, which conflicts with `bspcsg.rs`'s pool CLEAR at repartition
(§10.16) + `reorder_points_canonical`'s final renumber (§10.20) — both load-bearing for the
Points-section byte-parity guard, both outside the `zones.rs`/`passes.rs` lane. So a `passes.rs
bspRefresh` point-renumber sim cannot be byte-faithful without perturbing the Points guard.
Evidence: `sections/70 §12`, `42 §9`.
- **Points (native 1684 vs editor ~2088) = the repartition CLEAR.** Native clears Points + compacts
  Surfs 524→485 at repartition; the editor keeps them. **Fix is in `bspcsg.rs`** (no-clear repartition +
  deferred surf compaction into `bspOptGeom`) but entangled with `surf.pBase`/`vert.iVertex` pool indices
  → high tree-regression risk; needs care to preserve the byte-exact tree.
- **DONE this pass:** `UModel::Bound` prune type binary-verified — it is an **`FSphere`** (`BuildBound`
  = `Engine.dll 0x16fcf0`, not `0x100cee8c`; `FilterWorldThroughBrush 0x33250` arg5 = `&Bound.Sphere`,
  `DoFront=d>=−R / DoBack=d<=R`). Native's box prune (tighter) was replaced with the sphere in
  `bspcsg.rs` — output byte-invariant (uncleared verts now EXACTLY 17120 = editor). `bspoptgeom.rs`
  correct/frozen; `bspAddPoint` FIRST-vs-NEAREST is a red herring for pool SIZE.

## 2026-09-03: the orphan/points relationship is now editor-faithful in MECHANISM; stale-index
## BYTE parity remains open

Two shipped changes (spike `2026-09-03-verts-points-residual`) implement the editor's real orphan
semantics this item circled: `reorder_points_canonical` now uses the editor's GC rule (a point
lives iff a surf `p_base` or NODE-RANGE vert names it; orphan verts keep a point alive no longer,
and are never renumbered — golden evidence: every golden ships orphan verts with `iVertex` past
the pool end, min == `points.len()` on ShipFan), and Pass-D landings now go through the real
`bspAddNode` fill (`zones.rs::fill_ring_verts`: NEAR 0.015 pooling that CREATES pool points; a
killed landing's points end orphan-only and get GC'd — the snap-to-nearest orphan hack is gone).
Native orphan `iVertex` now dangle past the compacted pool exactly like the editor's, but their
VALUES are native's own pre-GC numbering, not the editor's transient numbering — the byte residual
this item tracks is unchanged in kind, smaller in surface.
