# Verts/Points pool residual on the four structure-EXACT levels (2026-09-03)

Target: `03_NYC_UNATCOHQ`, `09_NYC_ShipFan`, `04_NYC_Underground`, `08_NYC_FreeClinic` — all
nodes/surfs/leaves-EXACT, verts/points counts off. Offline throughout: cached goldens
(`/tmp/uedcli-parity-cache/`), shared trunk cache, `parity_compare.build_native_model`. Baseline
(RING_NEAR default): verts/points d = +11/+16, +1/+21, +41/+18, +1/+20.

## Finding 1 — the editor's points GC ignores orphan verts (FIXED, `bspcsg.rs`)

`vp_structure.py` decomposed every level's points surplus into native-only coordinates with NO
golden value-match; `vp_orphan_evidence.py` showed they are (almost all) referenced ONLY by orphan
verts, and — the decisive golden-byte evidence — every golden ships orphan verts whose `iVertex`
is OUT OF RANGE of its own Points pool (ShipFan 252, min exactly `== points.len()`; FreeClinic
762; Underground 2406; UNATCO 1278). So the editor's GC (the `bspRefresh` points compaction,
fresh-disassembled 2026-08-30: used iff a surf `p_base` or a NODE-RANGE vert names it) drops
points only orphan verts reference and never renumbers the orphans — they dangle. Native's
`reorder_points_canonical` had a third walk keeping every orphan-named point alive.

Fix: drop the third walk; renumber only node-range verts; orphan `iVertex` left numerically
untouched. Bake index validation narrowed to node-range verts (the only verts it reads — the
goldens themselves would fail the old whole-array check). Points d: +16/+21/+18/+20 →
**+6/+1/+3/0**; structure stays EXACT; DX/NYC-Bar stay all-zero; Wanchai unchanged (+17 is the
RING_NEAR baseline, orphan retention adds 0 there).

## Finding 2 — the 0.25 point-merge ends with a ring fix-up (FIXED, `bspoptgeom.rs`)

Underground had 3 nodes with `num_vertices` diffs: native nv=3/3/4 vs golden nv=0/0/3, same slot
widths both sides (3/3/4 — `vp_node_detail.py`, `_scratch/slotwidth.py`). Fresh disassembly of
`Editor.dll 0x33dc0` (the ShrinkModel-style 0.25 merge `merge_near_points` ports): after
remapping verts' `iVertex` (and surfs' `pBase`, a deliberate native deviation kept), the function
walks EVERY node (`0x10033f29-0x10033f9b`) dropping cyclic index-equal ring verts COUNT-only —
survivors' `(iVertex, iSide)` pairs compact down within the ring's own slots, slots stay
allocated, `NumVertices = survivors if >= 3 else 0`. Ported verbatim; the three nodes now match
the golden exactly. Counts unchanged corpus-wide (a count-only trim), node CONTENT improves.

## Finding 3 — Pass-D landings must use `bspAddNode`'s real ring fill (FIXED, `zones.rs`)

`vp_gap_walk.py` localized every remaining verts surplus to orphan-slot gaps between ring blocks
(Pass-D re-emit / repartition regions), always native-over. `zones.rs::append_ring_verts` pooled
at 0.002 with a snap-to-nearest orphan hack (predating finding 1's GC, which is what made a
faithful append unshippable before). Editor path (already decoded: `passD-assignzones-7400.md`
§4/§5 — every landing goes through `bspAddNode`; the fill decompile 2026-09-02; ring `bspAddPoint`
NEAR=0.015 per `0x352fd push 0`): pool into the REAL pool at 0.015 creating points (killed
landings' points end orphan-only → GC'd, reproducing the goldens' dangling stale indices),
consecutive-index collapse (no slot), wrap trim (slot kept, count−1), <3 → nv=0. Replaced with
`fill_ring_verts` (single path, no live/orphan split); `fix_ring` (the `FPoly::Fix`-equivalent
0.002 coordinate collapse, castle-calibrated) now runs before it for every landing. Verts d:
UNATCO +11→**+6**, Underground +41→**+24**, Wanchai +99→**+84**; ShipFan/FreeClinic stay +1;
structure stays EXACT everywhere measured; DX/NYC-Bar all-zero.

## Left open

- The remaining verts surplus (+6/+1/+24/+1) still sits in Pass-D/repartition orphan-slot gaps
  (`vp_gap_walk.py` brackets each) — needs per-emission editor-side data (live capture) to close;
  golden orphan `iVertex` are stale so orphan CONTENT cannot be compared offline
  (`vp_orphan_multiset.py` demonstrates why).
- The remaining points extras (+6/+3/+1) are live-ring near-threshold drift (native creates a
  point ~0.016 from the editor's pooled one — e.g. UNATCO's `(1071.98, -1023.999, 240)` quad);
  same family as the gated `UEDCLI_BSPCSG_ADD_RECOMPUTE_NORMAL` value-drift thread.

Harness: `vp_diff.py`, `vp_structure.py`, `vp_orphan_evidence.py`, `vp_orphan_multiset.py`,
`vp_vert_locus.py`, `vp_insertion_point.py`, `vp_context_dump.py`, `vp_node_detail.py`,
`vp_gap_walk.py`, `vp_counts_ab.py` (all offline, cached-golden based).
