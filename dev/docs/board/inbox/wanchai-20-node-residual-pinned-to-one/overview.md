+++
priority = "p1"
kind = "debug"
summary = "Wanchai +20 node residual pinned to one repartition splitter-pick fed by a +2 root-soup delta"
+++

# Wanchai +20 node residual pinned to one repartition splitter-pick fed by a +2 root-soup delta

Pins the residual `wanchai-bsp-gap-localized-to-one-dropped` §9 left open after `b3609ea`
(`is_csg_filter` NumVertices>0). All offline, on the current tree (`b3609ea`), treatment = research
only, no code changed.

## Reproduce (current tree)

- Native: `build_geometry_bspcsg` over `_scratch/proj/maps/wanchai` (1304 world CSG brushes, trunk
  order; `brush_marshal._in_world_csg` + `spike_classindex`), serialize, `parse_model_body`.
  Committed tree: 21147 nodes / 5114 dead — index-for-index identical to the editor's committed log.
- Golden: `load_model_from_dx(_scratch/golden_wanchai_world.dx)` (world Model only).

Counts: native 11668/5284 vs editor 11648/5284 — **+20 nodes, surfs exact, 0 dead nodes in either
final tree**. Points native 16819 vs editor 16791 (+28; the known points family).

## Pin: the whole +20 lives under ONE repartition splitter-pick

Synchronized tree walk (forensic-dive method: pair by position from root, follow iFront/iBack and
the iPlane coplanar chains, record a divergence origin at the first plane mismatch):

- Final trees: **1 real origin** at position `F/F/F/F/B/0` (node 9843 both sides), plus 3 cosmetic
  precision-drift origins (normal dot ≥0.9999999999, |Δoff| 0.002–0.003) on unrelated branches.
  Subtree under the real origin: native 860 vs editor 840 — the entire +20. Surf-id sets inside
  that subtree identical (518=518); whole-tree surf ids 1:1 identical (5284, zero exclusive).
- Stage counts (`UEDCLI_BSPCSG_STAGE_COUNTS`): repartition native 11031 vs editor 11011 — **the +20
  exists already at repartition**. Downstream increments are identical on both sides: native zone
  pass +60, detail pass +577 (native 11668−11031=637; editor 11648−11011=637). So nothing after
  repartition contributes.
- Repartition trees (native `UEDCLI_BSPCSG_REPART_NODES` vs committed `wanchai-ed-repart-tree.log`):
  same single origin at node 9855 (same index both sides): plane `(0,+1,0)`, native
  `off=−631.99994` vs editor `off=−752.00000` — parallel Y splitters **120 units apart**. Path from
  root to the origin is **bit-identical in every on-path node's f32 plane and surf** in the final
  trees (native vs golden).

## Classification

- Type (a) splitter-pick difference, NOT precision drift (120-unit gap; upstream bit-identical), NOT
  the merge mechanism (`7f4a773`), NOT zone/detail (increments equal), NOT a scoring-bug (scores are
  engine-exact).
- Forensic candidate table (`UEDCLI_REPART_FBS_DUMP`, call `id=5763 i_node=9855 numpolys=631`, GOOD
  stride 31): `Y=−752` (slot 279) → front 13 / back 7, score 72; `Y=−631.99994` (slot 310) →
  front 8 / back 12, **score 48** = native's pick. Both planes present and eligible in native's own
  table, so with an identical poly list native's strict `score < best` would pick the same plane the
  editor picked. The editor's pick implies a different strided sample at this call.
- Cause of the different sample: the root repartition soup differs. Committed trees are identical,
  yet native's post-merge soup (`UEDCLI_BSPCSG_SOUP_ORDER`) is **8189 polys vs the editor's captured
  8187** (`logs/wanchai-ed-repart-numpolys.log`, `num=8187 nonzero_nv=8187`). This is the same
  "+2 of the old +3" the 2026-07-15 item flagged open ("the soup delta may be a SECOND, independent
  defect"): the fixed −1 node removed one poly, the +2 survived. No exact-duplicate twin polys in
  native's soup; the +2 is a bsp_build_fpolys/bsp_merge_coplanars generation difference, not a
  visible merge remnant. Scores are computed over a stride-`Inc` sample of the leaf list, so a
  2-poly content/order difference at the root propagates to the node-9855 strided counts and flips
  the pick; downstream, that one splitter choice re-partitions its slab into +20 nodes.

Measured chain: the root soup differs at repartition entry (+2, 8189 vs 8187) → GOOD-strided
FindBestSplit at node 9855 picks `Y=−631.99994` where the editor picks `Y=−752.00000` → subtree
re-partitions to 860 vs 840 = the +20. The measurements above are current-tree and hold. The
CAUSAL story linking the +2 soup delta to a "points/verts pass-1 residual" came from the
pre-2026-08-14 spike decode, which the 2026-08-28 owner ruling invalidates — do not treat that
link as known. The +2's own origin (which 2 polys; `bsp_build_fpolys` vs `bsp_merge_coplanars`)
is UNMEASURED — the editor's soup and per-ilink pre-merge fragments are not archived.

## Decisive experiment / lever

Name the 2 extra polys: run `harness/editor-tree-oracle/ed_soup.py` on the Wanchai golden (needs a
live editor; never run on any level per the 2026-07-15 item) and diff its `polys_order_diff.py`
format against native's `UEDCLI_BSPCSG_SOUP_ORDER`; then `UEDCLI_BSPCSG_PREMERGE_DUMP=<ilinks>` on
the differing faces to pin whether `bsp_build_fpolys` or `bsp_merge_coplanars` is the source. That
names the second defect precisely and is the highest-leverage lever: matching the +2 de-flips the
node-9855 splitter and should close the +20 (surf-exactness is already held). The switch is
independent of the `is_csg_filter` fix that landed at `b3609ea`.

## Evidence

Throwaway analysis (uncommitted, `/tmp`): sync-walk origins (final + repartition trees), path
bit-identity check, subtree sizing, `UEDCLI_REPART_FBS_DUMP` candidate table for call 5763, stage
counts, SOUP_ORDER scan. Re-generate the native side via `native_dumps.py _scratch/proj
_scratch/proj/maps/wanchai --stage-counts --repart-nodes --soup-order` plus the FBS env; editor side
via the committed `logs/wanchai-ed-repart-tree.log` / `wanchai-ed-repart-numpolys.log`.