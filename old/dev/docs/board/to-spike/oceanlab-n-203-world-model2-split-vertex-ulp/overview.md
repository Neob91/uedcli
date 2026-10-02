+++
priority = "p2"
kind = "debug"
summary = "OceanLab byte-exact N=1..202, FAILS at N=203: one world Model2 point pair off by ~1-2 ULP near x=-256, same shape as the fixed N=13/WanChai-N40 MergeNearPoints bug but not the same cause."
+++

# OceanLab N=203 world Model2 split-vertex ULP divergence

Found 2026-09-07 chasing the N=203 bail (`ladder_run.py --dx 14_OceanLab_Lab.dx --from 203 --to 203
--force-ref --keep-native`). Gate residual: `BODY model model2` only (`Polys@Model2` soup also
differs downstream of the same points). `token_diff.py`/`body_token_diff.py` first show a raw token
COUNT mismatch (63317 vs 63319) that's a red herring — `model_dump.py` narrows it to exactly the
`points` array: same length both sides (3776), and as a MULTISET only 2 values differ.

## The divergence

    native only: (-256.0001220703125, 600.000244140625, -1800.0)  at points[617]
                 (-256.0001220703125, 504.000244140625, -1704.0)  at points[619]
    ued22  only: (-256.00006103515625, 600.000244140625, -1800.0) at points[612]
                 (-256.00006103515625, 504.000244140625, -1704.0) at points[614]

x differs by exactly 2 ULP at this magnitude (2 * 2^-15 = 6.103515625e-05); y/z are identical.
Neither side's value appears anywhere in the OTHER side's points array (not an index/order shift —
confirmed by full-array multiset diff). Everything else in `Model2` — vectors, nodes (2640/2640,
byte-identical apart from the expected iVertPool-index shift these two slots cause), surfs, verts,
lightmap, bounds, leaves, lights — is untouched; this is a pure 2-point value divergence.

## What's ruled out

- **Not the raw brush transform.** `brush483` (a "2D loft" builder shape: `2DLoftSIDE`/`2DLoftEND`/
  `2DLoftTOP` faces) is the last actor at N=203. Its own CSG-soup ring vertices near this region
  (`(-260.0001220703125, 600.000244140625, -1800.0)`, `soup_poly_dump.py --near`) are byte-IDENTICAL
  between native and UED22 — same raw authored/transformed float, confirmed via `soup_poly_dump.py`
  on both `native_N203.dx` and `ref_N203.dx`. So the divergence is a CSG-time computation, not a
  transform/GMath issue.
- **Not a single-hop `line_plane_intersection` crossing against the obvious candidate plane.**
  `brush1423`'s "OUTSIDE" face is a perfectly axis-aligned wall at `base=(-256.0,-252.0,0.0)`,
  `normal=(-1,0,0)` (both exact floats). Feeding `fpoly.rs::line_plane_intersection`'s exact formula
  (verified in numpy float32) with either edge-direction ordering of the brush483 ring edge
  `(-260.0001220703125, 600.000244140625, -1800.0) -> (-236.0001220703125, ...)` against this plane
  yields **exactly -256.0** — neither side's stored value (which are both ~1-2 ULP off `-256.0` in
  the OTHER direction from what a clean crossing gives). So this specific wall is not the (only)
  input to whatever produced the divergent point.
- **Live crossing-vertex instrumentation** (a temporary `eprintln!` in `fpoly.rs::split_with_plane`'s
  cut branch, gating on `|inter.x - (-256.0)| < 0.001`, reverted after use — not committed) logged
  every crossing near x=-256 during a native N=203 build. None of the ~5500 logged crossings produced
  `inter.x` bit-equal to native's stored `-256.0001220703125` (`0xc3800004`) or UED's
  `-256.00006103515625` (`0xc3800002`); the closest values were `0xc3800000` (exact -256.0),
  `0xc37fffff`/`0xc37ffffe`/`0xc37fffeb`, `0xc3800002`, `0xc3800008` — so the divergent point in the
  final `Model2.points` array is **not produced by a `split_with_plane` crossing directly**, at least
  not one whose `inter.x` value survives unmodified into the final array.
- One instrumented crossing used `base = (-256.00012, 600.00024, -1800.0)` — i.e. exactly native's
  divergent value — as a plane's `Base` parameter with `normal=(0,-1,0)`. That means this point
  (or one bit-identical to it) already exists as a real stored Points-array entry *before* this
  crossing runs, most likely a genuine (non-computed) vertex of `brush483` itself — consistent with
  it being the 2D-loft's own fan-center/axis point. Neither side's stored final value showed up as a
  raw soup vertex of `brush483` when searched directly (the point may already be consumed/replaced by
  fragments by the time the soup is dumped).

## Working hypothesis (unconfirmed)

This looks like the same BUG CLASS as the already-fixed OceanLab N=13 / WanChai N=40 issue
(`db857032`, `dev/docs/board/done/oceanlab-n13-csg-soup-split-vertex-1-ulp/`): a point that should be
WELDED onto (or already IS) a nearby existing pool point ends up with two builds picking different
final coordinates for what is conceptually the same location, 1-2 ULP apart. That fix was specifically
`MergeNearPoints` failing to remap `FBspSurf.pBase` alongside `FVert.iVertex` — confirmed NOT the gap
here (the current `bspoptgeom.rs::merge_near_points` already remaps both, per `db857032`/`d213832f`).
So this is either:

1. A different point-pooling/insertion-order divergence (native's incremental per-brush `AddPoint`
   dedup, `bspcsg.rs::find_nearest_vertex`, vs. the same-radius batch `merge_near_points` pass,
   picking different existing candidates at slightly different times), or
2. A genuinely new numeric-provenance divergence not yet isolated to a specific engine routine.

Neither could be pinned down at the level of static disassembly re-reading + numeric replay used for
the campaign's other same-shaped fixes today (`gather-box-verdict`, `oceanlab-n153-temp-brush-rsp`).
Closing it for real likely needs the same kind of live-editor-probe or fresh disassembly pass those
spikes used (e.g. instrument the editor's own `bspAddPoint`/`MergeNearPoints` call for this exact
brush/vertex under `winedbg`, the way `URender::BoundVisible` and `FLinePlaneIntersection` were
captured this session) — out of scope for a single diagnostic pass; parking here rather than forcing
an unconfirmed fix (`NATIVE-MATERIALIZE.md` prime directive: no masking, no guessing).

## Repro

    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
      --dx <…>/Maps/14_OceanLab_Lab.dx --from 203 --to 203 --force-ref --keep-native
    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/model_dump.py \
      <native_N203.dx> <ref_N203.dx> model2

No exclusion proposed — this is flagged as a reproducible algorithm difference per
`NATIVE-MATERIALIZE.md`'s prime directive, not a candidate for the closed exclusion set.

## 2026-09-13 update — provenance pinned, still not fixed

Re-checked with HEX bit patterns (the `2026-09-13-crossing-vertex-live-capture/` method) against the
current binary (post portal-graph-freeze fix); divergence unchanged. New findings, full detail in
`dev/docs/spikes/2026-09-13-oceanlab-n203-pbase-provenance/spike.md`:

- The divergent value is `Brush483` polygon 2's own transformed `Origin` (a `bsp_add_point(base)`
  call, never a `split_with_plane` crossing) — traced exactly via `bspcsg.rs`'s existing
  `UEDCLI_BSPCSG_POINT_TRACE`. Verified in f32 arithmetic that this transform's result is the SAME
  bit pattern under every operand grouping, ruling out a rounding-order explanation.
- A NEW committed diagnostic, `UEDCLI_LPI_TRACE_NEAR` (hex-precision trace on
  `fpoly.rs::line_plane_intersection`), confirms every crossing near x=-256 this brush's own clip
  produces lands on UED22's value (`0xc3800002`), not native's (`0xc3800004`) — ruling out a crossing
  formula difference too.
- `bsp_add_point_tol`'s FAITHFUL FNV descent (not the `bsp_build` repartition stopgap — this fires
  inside `bsp_brush_csg`) MISSES an existing pool point only `6.1e-5` away (well inside the `0.002`
  threshold) at the moment of this add; the miss target isn't currently wired to any reachable node.

Narrowed to a genuine `bspAddPoint`/`FindNearestVertex` HIT-vs-MISS divergence needing a live-editor
gdb capture to settle (same method as N=8/N=19 and the Island N=332 tie) — exact breakpoint condition
value and next steps are in the spike. Not attempted this session (scope/risk tradeoff, see spike's
final section); no fix, no mask.

## 2026-09-13 update (2) — live capture attempted, blocked by shared-disk exhaustion; miss re-confirmed exact

Reproduced N=203 fresh against the current binary (post the portal-graph-freeze fix, `f1bd02a4`):
unchanged, still `FAIL` at N=203 on `model2` only.

Re-read `point_wired`/`reachable_nodes` (`bspcsg.rs`): `sb=[] vp=[]` is a FULL DFS over every
currently-reachable node (root via `iFront`/`iBack`/`iPlane`), not a radius-pruned sample — so the
miss target (point 30820, `6.1e-5` from the query) is referenced by NO live node's `Surf.pBase` or
vert-pool at all right now, not merely outside some search radius. It is a genuinely orphaned
`Points` entry in native's current tree at this exact moment.

Attempted the live-editor gdb capture (same recipe as `stage2b/probe_editor_fnv.py`: break inside
`bspAddPoint` right after its `FindNearestVertex` call, `Editor.dll` preferred-base offset
`0x100354a1`, condition on the query's x bits `0xc3800004`, threshold `0.002`) — aborted before
running any container. This worktree shares a Docker daemon and host disk with concurrent sessions
(the parent session's UNATCO `ladder_run.py` sweep, at minimum). During setup, `docker images` showed
`ued-x86-runtime:latest` (needed as the base for the debug image) present, then **absent**, in two
checks minutes apart, and `df -h /` swung from 7.1G free to **159M free** and back to 5.9G within the
same ~15-minute window with no build of my own running yet. Rebuilding the ~4.2GB `ued-x86-runtime`
image on top of that would risk driving the shared host to true zero disk during a concurrent peak —
this session's brief explicitly says abort toward ~1.5GB. Stopped before any docker build; no image
was built, no disk was consumed beyond the failed (zero-cost) `docker build` attempts that errored on
`FROM ued-x86-runtime:latest: pull access denied` once the image had been evicted.

**Not resolved.** The open question is unchanged: does UED22's own `FindNearestVertex` ALSO miss at
the equivalent call (native would then be faithfully reproducing an earlier, not-yet-byte-visible
tree divergence from some prior actor/N), or does it HIT onto the nearby point (native's descent
genuinely differs here, same shape as N8 but reversed)? Settling this needs the live capture above,
run when the shared host's disk is not mid-swing. Exact recipe, breakpoint address, and query bits are
unchanged from the prior update and ready to run as-is. No fix, no mask, no exclusion proposed.

## 2026-09-14 update — live capture ran: UED22 ALSO misses; narrowed to a dead-node ghost point

Disk was calm this session (`df -h /` steady at 12-16G free throughout); the debug image build
(`dx-lum-uned-dbg`, gdb added on top of the already-present `ued-x86-runtime` base) cost under a
minute. Ran the exact recipe the prior update left ready. Full writeup + committed harness:
`dev/docs/spikes/2026-09-14-oceanlab-n203-addpoint-capture/`.

**The open question is answered: UED22's own `FindNearestVertex` MISSES too** (`dist=-1.0`, the same
sentinel the N=8 probe used), both times, for both of Brush483's two divergent points. Native's FNV
descent is faithful at this call — it is not the bug. A follow-up static trace (reverted after use,
not committed — see the spike for why) walked native's own `model.points` at each points-GC
checkpoint and found the exact downstream mechanism: the pre-existing wall-crossing point
(`0xc3800002`) survives the add only as a "ghost" reference from a surf whose owning NODE is already
DEAD (spliced out of the live tree by `bsp_cleanup`'s FWTB-DEAD splice) by the time Brush483's own
add runs. `compact_points_to_surf_bases` keeps the point alive anyway (its rule doesn't check node
liveness), but that ghost surf itself is discarded one line later, and repartition's soup-rebuild
(`make_ed_polys`) only walks LIVE reachable nodes — so nothing ever re-derives a surf at that exact
coordinate again. `bsp_refresh_points_vectors` correctly drops the now-truly-orphaned point right
after, and by the time `bsp_opt_geom`'s `merge_near_points` runs, there is nothing left to weld
Brush483's new point onto.

Every individual step in this chain is already a faithful, independently live-verified piece of the
port — none of them is locally wrong. The remaining question is upstream of all of it: is this
wall-face node ALSO dead at the equivalent point in UED22's real incremental tree, or does UED22 keep
it (or an equivalent live node at the same spot) alive through to its own `bspOptGeom`? Settling that
needs a DIFFERENT live capture — of the real editor's own `Model->Points`/`Model->Nodes` state at the
`bspBuild`/`bspRefresh` checkpoints, which needs locating `bspOptGeom`'s own `Model*` argument and
`TArray` layout, not yet done. A materially new, larger RE task, out of scope for this pass — not
attempted (`NATIVE-MATERIALIZE.md` prime directive: measure, don't guess a fix for an unconfirmed
mechanism). Still not resolved; no fix, no mask. OceanLab's ceiling is unchanged (byte-exact N=1..202,
re-confirmed unchanged this session).

## 2026-09-15 update — the open question is ANSWERED: UED22 keeps the wall face alive; narrowed to one exact CSG classification call

Full writeup: `dev/docs/spikes/2026-09-15-oceanlab-n203-bspoptgeom-points/spike.md`. Located
`bspOptGeom`'s `Model*` argument and `UModel`'s in-memory `TArray` layout (`Points`/`Nodes`/`Surfs`/
`Vectors` offsets — reused, not re-derived, from an already-committed but previously uncredited
oracle, `2026-07-15-native-materialize/harness/editor-tree-oracle/bspopt_pool_oracle.py`, cross-verified
against `zones.rs`'s own disassembly comment). A live gdb capture at `bspOptGeom` entry
(Editor.dll `0x10036870`) for OceanLab N=203 dumped the real editor's live `Points` (4189 entries) and
`Surfs` (1085 entries) arrays directly:

**Answer: UED22 keeps it alive.** Both the wall's pre-existing point (x-bits `0xc3800002`, at Points
index 947/950) and `Brush483`'s own new point (`0xc3800004`, index 968/970) are present, at DIFFERENT
indices — not merged, not orphaned. A `Surfs`-array cross-check (needs no node-reachability walk:
`pBase` offset `+0x08` within `FBspSurf`, scanned across all live surfs) confirms this is not a
dead-node ghost either — the wall's original surf (index 1053/1055) is a fully live, independent `Surfs`
entry, structurally identical in kind to `Brush483`'s own brand-new surf (1074/1076). This refutes the
prior session's "ghost from a dead node, kept alive only pending GC" framing: native's points-GC
(`bsp_refresh_points_vectors`/`compact_points_to_surf_bases`) is fully innocent — the true divergence
is one step further upstream.

Pinpointed the exact CSG step offline (no gdb, using the already-committed
`UEDCLI_BSPCSG_BRUSH_STATE=FULL:lo-hi` per-brush node trace): the wall face is native node 5154
(plane `x = -256.00006103515625`, exactly the wall plane; surf 1053), created by `Brush480`
(`CSG_Subtract`, world-CSG index `bi=164`), alive (`nv=3`) through `Brush481` (`bi=165`, `CSG_Subtract`),
then killed (`nv=0`, its own children spliced away) immediately after `Brush482` (`bi=166`,
**`CSG_Add`**) runs — one brush before `Brush483` (`bi=167`) itself. Native's `filter_world_through_brush`
(`bspcsg.rs`, port of Editor.dll `FilterWorldThroughBrush` `0x33250`) decides this ADD volume genuinely
consumes the wall face (`GDiscarded != 0`); the live capture proves UED22's real equivalent must decide
the opposite (a graze, keeps the face). Same bug SHAPE as the campaign's other found-and-fixed
near-tie boundary classifications (Island N=332, WanChai N=45/58, UNATCO N=226 — all a sub-ULP
`FLinePlaneIntersection`/crossing tie), but in a DIFFERENT function never live-captured before
(`FilterWorldThroughBrush`'s own consume-vs-graze classify, not a permeating-light beam clip).

**Not fixed.** The next step is a live gdb capture of the real editor's `FilterWorldThroughBrush`
(or its inner classify) during `Brush482`'s own `bspBrushCSG`, scoped to this exact face's plane bits,
to read the real `GDiscarded` verdict — same method class as `2026-09-13-crossing-vertex-live-capture/`.
No mask, no exclusion proposed. `docker cp` on this rootless daemon is separately confirmed BROKEN
(deterministic overlay `remount-ro .../stubs` error, not transient) — future captures should pull files
via `docker exec ... cat` instead, as this session's harness now does.

## 2026-09-15 update (2) — the capture ran: UED22 ALSO decides CONSUME; hypothesis REFUTED

Full writeup: `dev/docs/spikes/2026-09-15-oceanlab-n203-fwtb-classify/spike.md`. Ran the exact capture
scoped above (breakpoint at `FilterWorldThroughBrush`'s reconciliation, `0x1003348b`, confirmed by a
fresh `objdump` disassembly of `uned/UED22/Editor.dll` this session; staged the OceanLab N=203 subset
truncated to N=202 so `Brush482` is unambiguously the last CSG-participating brush).

**Result: UED22's own `GDiscarded` is nonzero (CONSUME) at every reconciliation hit on the wall's
exact plane** — node 5154 and its whole coplanar-chain successors (5156/5158/5160/5163/5165), all six
hits. This directly REFUTES the prior session's framing ("UED22's real answer must be a graze") —
UED22 kills this face during `Brush482` exactly like native does. `FilterWorldThroughBrush` is now
doubly confirmed faithful (live capture, on top of the existing disassembly-level port) and is not the
bug.

This also corrects the prior session's `bspOptGeom`-entry Points/Surfs read: the wall's surf
(1053/1055) being present in UED22's live `Surfs` array does NOT mean it's "a fully live, undamaged
surf" — its owning node is dead in UED22's tree too (per this capture), so it's a dead-node surf on
BOTH sides, not a coexisting-live-surf-vs-dead-node-ghost asymmetry. A fresh offline cross-check of
the FINAL (fully built) `native_N203.dx`/`ref_N203.dx` this session confirms only ONE point/surf
survives per side at this location, not two — native keeps `Brush483`'s own new point
(`0xc3800004`), UED22 keeps the wall's ORIGINAL point (`0xc3800002`) — consistent with the two
coexisting only transiently (at `bspOptGeom` entry, before its own `merge_near_points` runs) and then
UED22's `merge_near_points` welding them onto the wall's earlier point, while native's own
`merge_near_points` never gets the chance because the wall's point is already gone from native's pool
by the time `Brush483` runs.

**Re-scoped, not closed.** The true divergence is upstream of the classify decision: what happens to
a dead node's surf/point reference AFTERWARD, before `bspOptGeom`'s `merge_near_points` runs. A first
draft of this update blamed native's repartition-time `Surfs` clear+rebuild — WRONG, caught by review:
`bspcsg.rs`'s own comment there (`bspcsg.rs:3398-3406`) says the real editor does NOT rebuild Surfs at
repartition at all (it keeps the incremental-CSG pool, only compacting at `bspRefresh`); native's
clear+rebuild is a reordering device reconciled back to the editor's true order via
`canon_surf_keys`/`reorder_surfs_canonical`, not a port of an editor-side rebuild. Only
`bsp_refresh_points_vectors`'s point-compaction is independently evidenced-faithful so far; exactly
which step drops the wall's SURF entry (not just its point) is not yet pinned. Next step, in order:
(1) offline — trace natively whether the wall's surf is still present in the pre-clear
`canon_surf_keys` snapshot at the `Brush482`→`Brush483` boundary, to find which routine actually drops
it; (2) only then a live capture bracketing that exact step in UED22's real build. Full detail:
`dev/docs/spikes/2026-09-15-oceanlab-n203-fwtb-classify/spike.md` §3-4. No fix, no mask, no exclusion
proposed.

## 2026-09-15 update (3) — the surf's real drop point pinned and FIXED; one narrow residual left, not algorithmic

Step (1) above ran, offline, no live capture needed: the wall's surf IS present in the pre-clear
`canon_surf_keys` snapshot — confirmed by a temporary node-keyed trace (reverted after use). It is
dropped by the world-level repartition's clear + rebuild itself: the rebuild's input soup
(`bsp_build_fpolys`/`make_ed_polys`) only walks LIVE-reachable nodes, so a dead node's face is simply
never re-created; the very next call, `passes::bsp_refresh`, then can't drop what was never there, but
also has nothing to preserve it. A fresh disassembly of the real `bspRefresh` (`Editor.dll 0x36cd0`)
pins why this is a genuine divergence, not a reordering-device artifact: `bspRepartition`'s own call
passes `NoRemapSurfs=1`, which (traced at the instruction level) zeroes the function's internal
`SurfRemap` array before its compaction loop — i.e. it suppresses compaction entirely, keeping every
surf. The real surf GC happens later, inside `bspOptGeom`'s own prologue (`bspRefresh(Model, 0)`,
literal zero — a REAL compaction), which runs AFTER `bspOptGeom`'s own point-merge
(`merge_near_points`) — so a dead node's point survives long enough for a later brush's near-coincident
new point to weld onto it. Native was running the real compaction eagerly, right after repartition,
well before `merge_near_points` ever got the chance.

**FIXED**: `bspcsg.rs`'s world-level repartition now carries a dead node's surf forward across the
clear+rebuild (`carry_forward_dead_surfs`, using the same pre-clear snapshot `canon_surf_keys` already
took); `bspoptgeom::bsp_opt_geom` gained the previously-unported real compaction
(`passes::compact_unreferenced_surfs`, right after its point-merge). `Model2.points` is now
byte-identical to a fresh UED22 build (was: one 2-ULP-divergent pair); every one of 2640 live node
rings is coordinate-identical; live vert count matches exactly. Full detail, disassembly addresses,
and an independent subagent re-verification: `dev/docs/spikes/2026-09-15-oceanlab-n203-repartition-surf-defer/spike.md`.

**Not fully closed.** `parity_gate.py` still FAILs at N=203 — but the ONLY remaining divergence is one
extra ORPHAN (dead, unreferenced) `Verts` entry on the UED22 side (35265 vs native's 35264), which
desyncs the gate's positional token walk and cascades into spurious downstream "differences" that are
not real. This is a narrow residual in `parity_gate.py`'s existing orphan-vert exclusion (built and
validated only for same-COUNT, different-content orphan slots, never a genuine count mismatch), not a
newly-found algorithm bug. Whether native can be made to also produce this one orphan slot faithfully
(closing the item with no gate change) was not traced this session. Either way this needs the owner's
call before anything in `parity_gate.py` changes — filed as
`questions/orphan-vert-count-mismatch-gate-widening.md`. Staying in `to-spike/` until that's answered
(or the orphan-count mechanism is traced and fixed natively, whichever comes first). N=1..202
re-verified with `ladder_run.py` alongside this change — see the spike for the exact range covered
this session.
