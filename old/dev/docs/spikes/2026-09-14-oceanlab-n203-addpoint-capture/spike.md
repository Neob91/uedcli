# OceanLab N=203: live capture settles the FNV question; narrows the gap to a dead-node ghost point

Continues `dev/docs/board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/` and
`dev/docs/spikes/2026-09-13-oceanlab-n203-pbase-provenance/`. That session pinned the divergence to
one `bspAddPoint`/`FindNearestVertex` call and left one question open: does UED22's own
`FindNearestVertex` ALSO miss at that exact query (native would be faithfully reproducing an
upstream state), or does it HIT (native's descent genuinely differs)? This session ran the live
gdb capture the prior one could not (blocked by shared-disk exhaustion) and answers it: **UED22
also misses.** That rules out the FNV descent as the bug and moves the search one level down; a
follow-up static trace pins the new location precisely, though not all the way to a verified fix.

## The capture

`harness/capture_addpoint.py`: gdb attached inside the `dx-lum-uned-dbg` container (same recipe as
`2026-09-13-crossing-vertex-live-capture/`), breakpoint at Editor.dll (preferred base `0x10000000`)
`0x100354a1` — inside `bspAddPoint`, right after its call to `FindNearestVertex` — conditioned on
the query's x bits `0xc3800004` (native's divergent value,
`(-256.0001220703125, 600.000244140625, -1800.0)`, `Brush483` polygon 2's own transformed `Origin`).
At the breakpoint: `[ebp+0x0c]` = query `FVector*`, `[ebp+0x10]` = threshold, `[ebp+8]` = FNV return
distance (`-1.0` = MISS), `[ebp-0x14]` = returned vertex index. Drives the OceanLab N=203 subset
through `MAP IMPORT` + `MAP REBUILD` (no `LIGHT APPLY` needed — the divergence is in CSG).

Result (`logs/capture.log`, both queries hit twice each, fully consistent):

    ADDPOINT hit=46452 q=(-256.000122,600.000244,-1800) thr=0.002 dist=-1 vidx=268639582
    ADDPOINT hit=46469 q=(-256.000122,504.000244,-1704) thr=0.002 dist=-1 vidx=268639582
    ADDPOINT hit=46588 q=(-256.000122,600.000244,-1800) thr=0.002 dist=-1 vidx=268639582
    ADDPOINT hit=46593 q=(-256.000122,504.000244,-1704) thr=0.002 dist=-1 vidx=268639582

`dist=-1.0` is the FNV MISS sentinel (same convention as the original N=8 probe,
`2026-09-05-faithful-dedup-fix-attempt/stage2b/probe_editor_fnv.py`). **UED22's own
`FindNearestVertex` MISSES at this exact query, both times, for both of Brush483's two divergent
points** — identical to native's own trace (`UEDCLI_BSPCSG_POINT_TRACE`, prior session). Native's
FNV descent is faithful here; it is not the bug.

## What this rules out, and where it points instead

Given both sides push a NEW point at this call (miss => append), and finding 1 from the prior
session (`2026-09-13-oceanlab-n203-pbase-provenance/`) already proved this transform is the unique
f32 result under every operand grouping (`0xc3800004` both sides), **the literal add is identical on
both sides.** UED22's FINAL saved package nonetheless shows this surf's `pBase` pointing at a
DIFFERENT, pre-existing value (`0xc3800002`, 2 ULP off, matching a nearby wall crossing) — so
somewhere AFTER the add, UED22's build welds the two together and native's does not.

The only pass that welds near-duplicate points post-hoc is `bspoptgeom.rs::merge_near_points`
(faithful, disassembly-verified, radius 0.25 — no reachability gating). A temporary instrumented
trace (reverted, not committed — see below) walked `model.points` at four checkpoints in native's
own build (`pre-compact` / `post-compact` / `post-bsp_build` / `post-refresh-points`, the points-GC
call sites `bspcsg.rs` already names) and found the exact mechanism:

- **Right after Brush483's own CSG (`pre-compact`)**, the wall's crossing value
  (`-256.00006103515625, 600.000244140625, -1800.0`, i.e. `0xc3800002`) still exists in
  `model.points` (index 30820) and is referenced by exactly one surf — but that surf's owning NODE
  (5154) is **unreachable from root** (`reachable_nodes` reports `false`), a dead node
  `bsp_cleanup`'s FWTB-DEAD splice has already spliced out of the live tree. `compact_points_to_surf_bases`
  keeps the point anyway (it scans `model.surfs` unconditionally, live node or not — matching its own
  documented, live-verified rule), but that whole surf is discarded one line later (`model.surfs.clear()`).
- **After `bsp_build`'s repartition** (which reconstructs the soup by walking only LIVE, reachable
  nodes — `make_ed_polys`), nothing re-derives a surf at this exact coordinate: the dead node is never
  visited, so no fresh `alloc_surf`/`bsp_add_point` call ever queries `0xc3800002` again (confirmed
  directly: `UEDCLI_BSPCSG_POINT_TRACE` shows zero queries at this value during repartition, only at
  Brush483's own `0xc3800004`). The point is now a genuine, permanent orphan.
- **`bsp_refresh_points_vectors`** (the very next call, `bspcsg.rs:3408`) correctly drops it —
  zero live references, exactly its documented rule.
- **By the time `bsp_opt_geom`'s `merge_near_points` runs**, `0xc3800002` is simply gone from
  `model.points`. Nothing is left to weld Brush483's own `0xc3800004` onto, so it survives unchanged.

Checked for a decoy: `model.points` holds 12 distinct entries on this same wall plane with
`x = 0xc3800002` (different y/z). Two of them (`y=608`/`y=496`, ~8 units from the target — far
outside `merge_near_points`'s 0.25 radius) are still live. The two that are EXACTLY 6.1e-5 from
Brush483's adds (the only candidates within the merge radius) are both dead-node ghosts, same as
above (nodes 5154/5156, `i_actor=165` — two brushes before Brush483's own `i_actor=167`).

## The open question this narrows to

Every step measured above is individually a faithful, already-verified piece of the port
(`compact_points_to_surf_bases`, `bsp_refresh_points_vectors`, `make_ed_polys`'s live-only walk,
`merge_near_points` itself) — none of them looks locally wrong. The mechanism is airtight ON
NATIVE'S OWN TERMS. The real open question is upstream of all of it: **is node 5154 (the wall's
original face, here) actually dead at the equivalent point in UED22's REAL incremental tree, or does
UED22 keep it (or an equivalent live node at the same coordinate) alive through to its own
`bspOptGeom`?** If UED22's tree also has it dead, UED22's own surviving `0xc3800002` must come from a
DIFFERENT live mechanism this session did not find, and the true divergence is even further upstream
(exactly which earlier brush/CSG step frees vs. keeps this node). If UED22's tree keeps it alive,
native's `bsp_cleanup`/CSG classification kills this node too early relative to the real editor —
a genuine algorithm gap, but in node-liveness bookkeeping, not in point-dedup at all.

Settling this needs ANOTHER live capture — of the real editor's own `Model->Points`/`Model->Nodes`
state (size, and whether this specific coordinate is still referenced) at the `bspBuild`/`bspRefresh`
checkpoints equivalent to `bsp_refresh_points_vectors`'s call sites, or a direct read of node 5154's
UED22-equivalent liveness. That requires locating `bspOptGeom`'s own entry point's `Model*` argument
and `TArray` layout for `Points`/`Nodes` — non-trivial new RE, not attempted this session (a
materially different, larger investigation than the `bspAddPoint` capture above, per
`NATIVE-MATERIALIZE.md`'s prime directive: measure, don't guess a fix for an unconfirmed mechanism).

## What this does NOT do

- No fix applied. `bspcsg.rs`/`bspoptgeom.rs` are unmodified — the temporary diagnostic trace used to
  find the mechanism above (`trace_pts_tmp`, four checkpoint calls + a wall-plane point scan) was
  reverted after use; it was single-purpose (hardcoded to this investigation's exact coordinates), not
  a generically reusable diagnostic in the shape of the codebase's existing `UEDCLI_BSPCSG_POINT_TRACE`/
  `UEDCLI_LPI_TRACE_NEAR` hooks, so it was not committed.
- OceanLab's ceiling is unchanged: byte-exact N=1..202, still bails at N=203 on the same `model2`
  `points` divergence, re-confirmed unchanged this session
  (`ladder_run.py --dx 14_OceanLab_Lab.dx --from 203 --to 203 --force-ref --keep-native`).
- No mask, no exclusion proposed.

## Repro

    # the live capture:
    .venv/bin/python3 dev/docs/spikes/2026-09-14-oceanlab-n203-addpoint-capture/harness/capture_addpoint.py
    # the point-array mechanism (reproduce with the reverted trace re-applied, or by inspection):
    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
      --dx <…>/Maps/14_OceanLab_Lab.dx --from 203 --to 203 --force-ref --keep-native
