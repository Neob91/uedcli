+++
priority = "p1"
kind = "debug"
summary = "Garage -68 node residual: three pool-snapped verts stall the wall merge and flip the repartition root"
+++

# Garage -68 node residual: three pool-snapped verts stall the wall merge and flip the repartition root

`06_HongKong_WanChai_Garage` (198 world-CSG brushes), baseline at `1b8be83`: native vs cached lit
golden `d_nodes=-68 d_surfs=+0 d_leaves=-12`. Live prefix binary search
(`spikes/2026-09-03-built-parity-worst-tier/harness/wg_prefix_search.py`, log committed): first
diverging brush is **`Brush21` (world-CSG idx 39)** — n=39 exact, n=40 `+13/+0/+0`; deltas swing
along the prefix (n=99 `+100`, full `-68`), so everything past n=40 is cancellation on top of this.

## Measured chain (every stage dump- or live-verified)

`Brush21` is a plain 6-poly Yaw=16384 Subtract sharing a wall plane with `Brush20` (the 50-poly
Yaw=16384 staircase Subtract just before it; its only bbox-overlap partner). The 2-brush live case
[`Brush20`, `Brush21`] is EXACT (58/32/12 both, `wg_minimal_golden.py`) — the chain needs the
wider prefix:

1. Pass-1 fragment rings for `Brush21`'s south wall (ilink 240): pre-merge sets are 23 == 23,
   index/nv-identical (`fpolys_stage_verts.py` live capture vs `UEDCLI_BSPCSG_PREMERGE_DUMP`), but
   6 vert values differ, all on the z=0 seam: **native snapped 3 points onto `Brush20`'s
   coincident plane/pool — `(-288.000549,-896.001709,0)` → `(-288,-896.001953,0)`, likewise
   x=-312/-336 (Δ≈0.0005–0.0015, inside SAME=0.002)** — the editor keeps them on `Brush21`'s own
   plane (y=-896.0017).
2. Those 3 snapped points alone stall `bsp_merge_coplanars`: native fuses 23→13, editor 23→1
   (clean 4-vert quad, live-captured). The merge port is EXONERATED: the as-ported emulation
   (`wg_merge_emul.py`/`wg_rings_cmp.py`) on the editor's rings gives exactly 1 poly nv=4, on
   native's rings 13; no threshold/anchor variant moves it.
3. Soup: native 371 vs editor 359 (+12, all on that plane). Root `FindBestSplit` has a score TIE
   at 48 (`front=12 back=8 splits=0` both) between native's slot 108 (`Y=-416`) and the editor's
   slot 288 (`Y=-143.9999`); strict `score<best` keeps the earlier slot, so the differing
   soup/stride flips the ROOT pick (sync walk: 1 origin, at root). One flipped root → `+13` at
   n=40 → `-68/-12` full-level.

## Classification

KNOWN family — pass-1 ring-vert pooling/snap (the `RING_NEAR`/pool-reuse thread:
`points-residual-live-ring-near-threshold-drift`, the 2026-09-02 ring-threshold root-cause round).
NOT Active (both brushes Subtract), NOT Pass-D (0 degenerate rings either side), NOT the f32 scale
chain (both unscaled). First case measured end-to-end pooling → merge → soup → root pick. The fix
lever is the pooling stage: match WHICH pool point a landing ring vert reuses vs creates; the merge
and FBS stages are faithful given equal inputs.

Evidence: spike `2026-09-03-built-parity-worst-tier` §6, its `logs/wg-n40-premerge-native.log` +
`logs/fpolys-stage-order-wg-n40-verts.log`, `wg-prefix-search.log`.

## Fix-round progress (2026-09-03, branch `garage-pool-snap` @ `5215cf2` — investigation only, no code change yet)

Native predicate today: `bspcsg.rs::bsp_add_point_tol` = FIRST-within linear scan over the WHOLE
`model.points` pool (0.015 ring / 0.002 pBase); `zones.rs::fill_ring_verts` same shape at
`RING_POINT_TOL`. Editor predicate per the committed decodes (`fp-classification-sites.md` §7,
findings ledger "THE ONE REAL DIVERGENCE"): `bspAddPoint` (Editor `0x35430`) calls
`UModel::FindNearestVertex` (Engine `0x1adeb0`, recursive body `0x1adb60`), accepts if the real
(f64-sqrt) distance ≤ thresh, NEAREST not first — and the recursive body is a BSP-TREE walk
(descends by `PlaneDot` sign), i.e. it can only see verts REFERENCED BY NODE RINGS reachable from
the walk in the tree as built at that moment — never the whole Points pool. That tree restriction
is the missing piece that fits every measurement: Brush20's 0.0006-away pool point exists but the
tree walk at n=40 need not reach a ring referencing it (editor keeps Brush21's 3 seam verts
distinct; native's whole-pool scan welds), and the 2-brush case is EXACT because the walk context
differs — the snap needs the n≈39 tree.

Still UNDECODED (blocks the port; next session starts here):

1. Engine `0x1adb60` recursive body: the pruning band (`±MinRadius`), whether the on-plane case
   recurses front then checks only that node's `iPlane` chain and RETURNS (back subtree invisible),
   whether `Surf.pBase` is a candidate, and the radius-shrink order.
2. Editor `0x35430` MISS tail (after the `comiss` pair at `0x100354b4`): whether add-new
   linear-scans the pool (AddThing-style, and any `GFastRebuild` gating) or plain-appends.

Disassemble per `dev/docs/unrealed/extracting-from-dll.md` (`pefile`+`capstone`, harness
`_scratch/bspspike/`; DLLs under `Tools/uedcli/uned/UED22/` — do not `find /`, it hangs). Then:
one shared tree-walk `find_nearest_vertex` for every `bspAddPoint` site (`bspcsg.rs` ring+pBase,
`build.rs`, `zones.rs::fill_ring_verts`), exact miss fallback; regression test pinning the 3
Brush21 verts from the committed logs; guard FreeClinic points + Club/Chateau/NYC-Underground
nodes; then the corpus A/B gates from the task.
