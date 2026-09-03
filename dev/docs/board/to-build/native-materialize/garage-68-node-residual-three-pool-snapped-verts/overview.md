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

## Fix-round 2 (2026-09-03, branch `garage-pool-snap-fix-round2` @ `c442e4b` — coded, NOT MERGED)

Both undecoded pieces above are now decoded and address-cited in the commit (`Engine.dll 0x1adb60`
recursive body; `Editor.dll 0x35430`+`0x31ae0` miss tail — the miss path turns out to be TWO-stage,
tree search then a gated whole-pool per-axis box-scan fallback, NOT ported, flagged separately).
`find_nearest_vertex`/`find_nearest_vertex_at` ported into `bspcsg.rs`, wired into
`bsp_add_point_tol`'s Points-pool path only (`build.rs`/`zones.rs` deliberately untouched — each
has its own unexamined wrinkle). Two unit tests pin the real Brush21/Brush20 coords. `cargo test`
113/113 green, full `bin/test` clean of new failures.

**Coordinator-verified 18-level corpus A/B** (env var on/off, warm cache;
`dev/docs/native-materialize-findings.md` "Garage `find_nearest_vertex` fix" entry has the full
numbers): real wins on Garage (2→4/6, the fix's own target — `LENGTH MISMATCH` closes), NSFHQ04
(1→4/6), Area51 (1→3/6), Paris Underground (3→4/6). **Real regression**: `points_match` flips
true→false on `DX.dx` (previously 6/6, the campaign's simplest reference level) and `02_NYC_Bar.dx`,
plus on the already-non-exact ShipFan/FreeClinic. This is not acceptable per the standing
no-exact-level-regresses gate — **NOT merged**.

Separately, the commit gates the new logic behind `UEDCLI_BSPCSG_POINT_NEAREST` (default OFF)
while `materialize.py` calls `build_geometry_bspcsg` unconditionally — an "old way behind a flag"
regardless of the regression (the exact pattern `321f5dd` removed `UEDCLI_BSPCSG_ADD_RECOMPUTE_
NORMAL` for). The flag has to go either way once the logic is right.

**Next session starts here**: root-cause why the tree-restricted `find_nearest_vertex` diverges
from the whole-pool scan on DX/Bar's (much simpler) brush sets — likely the radius-shrink-as-you-
descend or the on-plane early-return band is too aggressive/wrong outside Garage's specific
geometry. Branch `garage-pool-snap-fix-round2` is sitting unpushed in worktree
`agent-a14189a804e86a9c4` — read its diff before restarting rather than re-deriving the decode.

## Fix-round 3 (2026-09-03, branch `garage-pool-snap-fix-round2-cont` @ `1916dc0`, worktree `agent-ad8c36bc0dc8e72a8` — coded, NOT MERGED, coordinator took over after a 2nd stall)

Correctly diagnosed and fixed a real gap: round 2's port only scanned a node's OWN ring, missing
the surf `pBase` candidate (`+0x8`) and the `i_plane` coplanar-sibling chain (`+0x28`) — both
disasm-confirmed, pinned by 2 new unit tests. Also fixed a resquare-vs-propagate radius precision
bug. Gates green (cargo 115/115, full pytest clean except the one pre-existing failure).

**This fix is REAL but DOES NOT close DX/Bar** — adds two NEW level wins beyond round 2's
(`06_HongKong_Helibase.dx`, `00_TrainingFinal.dx` both gain `nodes_match`), but DX.dx/`02_NYC_Bar.dx`
regress IDENTICALLY before and after (same `points_match: False`, same content notes) — the
pBase/chain gap was real but is not the DX/Bar mechanism. It's a third, separate bug.

**Precisely localized**: `parity_report.py` on DX.dx (flag on) → `points native=39 golden=32 d=+7`
— the OPPOSITE direction from Garage's own fix target. Garage's bug was native OVER-pooling
(welding points the editor kept distinct — tree-restriction correctly fixes this). DX's bug is
native UNDER-pooling / OVER-creating: the tree-restricted search fails to find an existing
near-duplicate point that the OLD whole-pool scan always found regardless of tree state. Either
the port is still missing a reachability path the real `Engine.dll UModel::FindNearestVertex` has,
or the call site/tree-state assumption is wrong for DX's construction order. NOT yet disassembled
further. Full detail + all 3 rounds' corpus numbers: `native-materialize-findings.md`, search
"Round 3 (`1916dc0`".

**Next session starts here**: DX.dx is TINY (39 vs 32 points) — get the 7 extra points' exact
coordinates and their would-be nearest golden neighbor (offline, via the cached golden + a native
rebuild), then trace which specific `bspAddPoint` call/tree-state produces the miss. Branch
`garage-pool-snap-fix-round2-cont` sits unpushed in worktree `agent-ad8c36bc0dc8e72a8` (commit
`1916dc0` on `70bf271`) — read its diff before restarting. `agent-a14189a804e86a9c4` (round 2's
original worktree) is now superseded/stale, safe to remove.
