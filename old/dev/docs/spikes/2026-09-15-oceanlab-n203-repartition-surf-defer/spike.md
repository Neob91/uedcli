# OceanLab N=203: repartition must defer the dead-node surf/point GC to `bspOptGeom` — FIXED

Continues `dev/docs/board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/` and
`dev/docs/spikes/2026-09-15-oceanlab-n203-fwtb-classify/`. That session's exact next step (already
scoped, see the board overview): trace offline whether the wall's surf is still present in the
pre-clear `canon_surf_keys` snapshot at the world-level repartition checkpoint, to find which routine
drops it.

**Answer: it IS present in the pre-clear snapshot. The drop happens at repartition's own clear +
live-only rebuild, and that step is NOT a faithful port of what the real editor does there — fixed.**

## 1. The offline trace

Added a temporary env-gated diagnostic (`UEDCLI_BSPCSG_SURFTRACE_NODE`, reverted after use, not
committed) that, for OceanLab N=203, looked up node 5154's `i_surf` at three checkpoints: right before
the world-level repartition's clear (`canon_surf_keys`'s own snapshot point), right before
`bsp_opt_geom` runs, and in the final serialized model.

```
SURFTRACE pre-clear: node=5154 isurf=1053 surfs.len=1085 canon_surf_keys.len=1085
SURFTRACE pre-clear: node=5154 isurf=1053 key=(i_actor=165,i_brush_poly=0) in_canon=true
SURFTRACE pre-optgeom: key=(i_actor=165,i_brush_poly=0) present=false surfs.len=962
SURFTRACE final: key=(i_actor=165,i_brush_poly=0) present_in_final_surfs=false final_surfs.len=962
```

Present pre-clear, absent by the time `bsp_opt_geom` runs. Reading `bspcsg.rs`'s own code confirms
why: nothing removes a `model.surfs` entry during Pass 1 CSG (`cleanup_nodes` only unlinks the dead
NODE — it never touches `model.surfs`), so the wall's surf survives untouched right up to the
repartition clear. The clear (`model.surfs.clear()`) is immediately followed by a rebuild
(`bsp_build(&mut model, merged)`) whose input (`merged`, from `bsp_build_fpolys`/`make_ed_polys`) only
walks LIVE-reachable nodes from root — the wall's face, dead since `Brush482`, is never in `merged`, so
`bsp_build` never recreates its surf. `passes::bsp_refresh` (the very next call) then drops whatever
`bsp_build` didn't create — moot here, since it was already absent.

## 2. Why this is a REAL divergence, not a native-only permutation artifact

The world-level repartition's own comment (`bspcsg.rs`, already committed) states the editor does
**not** rebuild its `Surfs` pool at repartition at all — it keeps the incremental-CSG pool, compacting
only at `bspRefresh`. That's exactly what a fresh disassembly of the real `bspRefresh`
(`Editor.dll 0x36cd0`) confirms, and it pins the mechanism precisely:

`bspRefresh(Model, NoRemapSurfs)`, at `0x10036d62`: `cmp [ebp+0xc], 0; je 0x10036d7d` — skips a block
when `NoRemapSurfs == 0`. That skipped block (`0x10036d68`-`0x10036d7a`, taken when `NoRemapSurfs != 0`)
**zeroes the whole `SurfRemap` array** (`appMemzero(SurfRemap, Surfs.Num*4)`) right before the
compaction loop, which keeps a surf iff `SurfRemap[i] != 0xffffffff`. Zeroing (not `-1`-filling) makes
every slot read as kept — i.e. `NoRemapSurfs != 0` **suppresses the compaction entirely**, regardless of
tree reachability. `bspRepartition` calls this with `NoRemapSurfs=1` (confirmed independently in the
already-committed `sections/82-bspbrushcsg-port-decode.md`, `0x1004a049 push 1`) — so the real editor's
repartition drops NOTHING.

The real surf GC happens later, inside `bspOptGeom` itself: its prologue (`0x100368ef`-`0x100368f4`,
right after its own `ShrinkModel`-style point-merge at `0x33dc0`) calls `bspRefresh(Model, 0)` — literal
zero, a REAL compaction. So the true editor sequence is: repartition (keeps every surf) → [zone
split, semisolid pass] → `bspOptGeom`: point-merge (welds near-coincident points, INCLUDING a
dead-node's still-present, lower-index point) → **then** the real surf GC, which finally drops the
now-genuinely-unreferenced dead surf.

Native's old code ran the real GC (`passes::bsp_refresh`) immediately after repartition's rebuild —
structurally identical to the editor's `NoRemapSurfs=0` call, but at the WRONG point in the sequence
(before the point-merge, not after) — so a dead-node's point was gone before `merge_near_points` ever
got the chance to weld a later brush's near-coincident new point onto it.

Corrects a stale line in the older `42-bspoptgeom-decode.md` (§4): "(`NoRemapSurfs==0` keeps all
surfs)" has the polarity backwards — this session's fresh disassembly read (independently
re-confirmed by a subagent review, see below) shows `NoRemapSurfs != 0` is what keeps everything;
`== 0` is the real compaction. Not otherwise a load-bearing correction (nothing else in that doc
depended on the parenthetical), left as-is per this repo's dev-docs edit policy — flagged here, not
silently rewritten.

## 3. The fix

Three files, `uedcli-native/src/`:

- `bspcsg.rs`: right where `canon_surf_keys` is already snapshotted (pre-clear), also snapshot the
  full surf rows (`pre_clear_surfs`). After the post-clear rebuild + `passes::bsp_refresh`, call a new
  `carry_forward_dead_surfs(&mut model, &pre_clear_surfs)` — re-appends any pre-clear surf whose
  `(i_actor, i_brush_poly)` key isn't already present, with no owning node (an orphan row, exactly
  matching the real editor's `NoRemapSurfs=1` outcome). `canon_surf_keys` already covers its canonical
  rank, so `reorder_surfs_canonical` (run once at the very end) needs no change. `pre_clear_surfs`'
  `p_base` indices are stale after `compact_points_to_surf_bases` shrinks `model.points` a few lines
  later, so that function's signature grew a return value (`Vec<i32>`, the old→new point remap) and
  the call site applies it to `pre_clear_surfs` too.
- `passes.rs`: extracted the surf-compaction half of `bsp_refresh` into a new
  `pub fn compact_unreferenced_surfs` (pure refactor at that call site, same behavior).
- `bspoptgeom.rs`: `bsp_opt_geom` now calls `compact_unreferenced_surfs` right after
  `merge_near_points`, before the existing points/vectors GC (`bsp_refresh_points_vectors_stale_orphans`)
  — reproducing the real editor's bspOptGeom-front `bspRefresh(Model, 0)`, previously entirely
  unported. Surfs-before-points matches the real function's own internal instruction order.

This is a no-op for any brush sequence where no dead-node surf/point survives long enough to matter
(the overwhelming majority of builds): `carry_forward_dead_surfs` finds nothing to append, and the new
`compact_unreferenced_surfs` call in `bsp_opt_geom` has nothing extra to drop.

## 4. Result

`Model2.points` is now byte-identical to a fresh UED22 build (was: one 2-ULP-divergent pair). Every
one of 2640 live BSP node rings is coordinate-identical (`ring_diff.py`), live vert count matches
exactly (11991 both sides). `lightmap`/`lightbits`/`bounds`/`leafhulls`/`leaves` all match. Verified
reproducibly: `harness/verify_points_and_rings.py` (needs a kept `ref_N203.dx` from a prior
`ladder_run.py --keep-native` run).

**Not fully closed — one narrow residual, gate-side, not algorithmic.** `parity_gate.py` still reports
FAIL: native's raw `Verts` array has 35264 entries, the fresh ref has 35265 — one extra ORPHAN
(unreferenced by any live node ring on either side). This desyncs `parity_gate.py`'s positional token
walk and cascades into spurious differences in every later field. Whether this is itself a faithful,
explainable byproduct of the same mechanism (not yet traced) or `parity_gate.py`'s existing
orphan-vert exclusion machinery simply never anticipated a raw COUNT mismatch (only content) is an
open question filed as `dev/docs/board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/
questions/orphan-vert-count-mismatch-gate-widening.md` — a candidate gate-exclusion widening needs the
owner's yes per `NATIVE-MATERIALIZE.md`'s own rule, so `parity_gate.py` was NOT touched this session.

An independent subagent review re-disassembled `bspRefresh`/`bspOptGeom` from scratch (not deferring to
either doc above) and re-ran the point/ring/i_link checks against the kept N=203 builds itself; it
confirmed the mechanism, found no regression risk in the three changed files, and found no
duplicate-surf-key or `i_link`-consistency issue.

## Regression coverage (committed)

- `passes::tests::compact_unreferenced_surfs_drops_only_the_unreferenced_ones`
- `bspcsg::tests::carry_forward_dead_surfs_reappends_only_the_missing_key`

Both are pure unit tests of the two new/refactored functions (no CSG brush geometry needed — the
mechanism is tested directly, not re-derived from a synthetic brush scene that could itself be subtly
wrong). `cargo test`: 246 passed, 0 failed (was 244; +2 new).

## Repro

```
# offline re-check (no docker), needs a previously kept ref_N203.dx:
dev/docs/spikes/2026-09-15-oceanlab-n203-repartition-surf-defer/harness/verify_points_and_rings.py

# full gate (still FAILs on the orphan-vert-count residual above):
dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
  --dx <...>/Maps/14_OceanLab_Lab.dx --from 203 --to 203 --force-ref --keep-native
```
