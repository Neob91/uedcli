+++
priority = "p2"
kind = "debug"
summary = "After the 2026-09-03 points-GC + Pass-D fill fixes, the last verts surplus on the structure-EXACT levels (UNATCO +6, Underground +24, ShipFan +1, FreeClinic +1, Wanchai +84) sits in Pass-D/repartition orphan-slot gaps; golden orphan iVertex are stale, so closing it needs per-emission live editor capture, not offline diffing."
spikes = ["dev/docs/spikes/2026-09-03-verts-points-residual/"]
+++

# Verts residual on the structure-EXACT levels: orphan-slot gaps, live capture needed

Post the 2026-09-03 fixes (points GC editor rule, `merge_near_points` ring fix-up, Pass-D
`fill_ring_verts`), the structure-EXACT levels' verts deltas are UNATCO +6, Underground +24,
ShipFan +1, FreeClinic +1, Wanchai +84 — all localized by
`dev/docs/spikes/2026-09-03-verts-points-residual/harness/vp_gap_walk.py` to a handful of
orphan-slot gaps between ring blocks (Pass-D re-emit / `repartition_frontier` regions), always
native-over, e.g. ShipFan's whole +1 in one 1009-vs-1008 gap, Underground +24 in one
2065-vs-2041 gap.

Why offline is exhausted: the goldens' orphan verts carry STALE `iVertex` (pre-GC transient
indices, many past the pool end), so orphan CONTENT cannot be compared against native
(`vp_orphan_multiset.py` shows the resolved-coordinate comparison is meaningless). Slot COUNTS
are the only offline signal, and they don't identify which emission differs.

Next step: a live gdb capture of `AssignAllZones`' per-landing `bspAddNode` calls (ring length
after fill, pool slot count) on Underground or ShipFan, joined against native's
`UEDCLI_PASSD_DUMP` emission log per landing. The remaining points extras (+6/+3/+1 on
UNATCO/Underground/ShipFan) are a separate, smaller thread: live-ring value drift creating a
point just outside the 0.015 ring pool threshold (e.g. UNATCO's `(1071.98, -1023.999, 240)`
quad) — same family as the gated `UEDCLI_BSPCSG_ADD_RECOMPUTE_NORMAL` drift work.
