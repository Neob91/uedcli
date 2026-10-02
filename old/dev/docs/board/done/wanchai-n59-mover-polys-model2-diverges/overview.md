+++
priority = "p2"
kind = "debug"
summary = "FIXED 2026-09-14: collect_repartition_frontier (sub_49380 port) recursed i_back before i_front; the real editor checks iFront first (Editor.dll 0x10049380, disassembly + live capture). WanChai N=1..59 re-verified PASS; UNATCO/NYC_Bar/Island/OceanLab spot-checked unaffected."
+++

# WanChai N=59 — world Model2 Polys soup collapses to 1 poly (editor-side), not reproduced by native

Found while re-verifying the fix for `wanchai-n58-leaf-51-permeating-light-over-included`
(closed — see `NATIVE-MATERIALIZE.md`'s "portal-graph frozen before `bspOptGeom`" fix). WanChai
runs byte-exact N=1..58 and bails at N=59 on a DIFFERENT, unrelated mechanism. Investigated
2026-09-13; NOT fixed — see "Status" below.

## What actor 59 is

Trunk order actor 59 = `Brush904`:

    Begin Actor Class=Engine.Brush
        CsgOper=CSG_Add
        PolyFlags=32                    # PF_Semisolid
        Rotation=(Pitch=16384,Yaw=16384)
        Location=(X=-320,Y=-254,Z=736)
        MainScale=(SheerAxis=SHEER_ZX)
        PostScale=(Scale=(X=3,Z=0.5),SheerAxis=SHEER_ZX)
        Begin Brush Name=Model
           Begin PolyList
             Begin Polygon Texture=HK_BuildingExt.ClenWhteWall_F Flags=1048616
             ... one 128x128 quad, no extrusion (NOT a closed solid) ...
             End Polygon
           End PolyList
        End Brush
    End Actor

A single-poly, non-closed, `PF_Semisolid` `CSG_Add` brush (a decorative wall panel, not a mover).

## The real divergence (corrected — the original filing mis-measured this)

`gate()`'s printed `fails[0]` only shows a truncated repr, which reads as "a different
flags/base-point on the first poly." That is misleading. `parity_gate._polys_tail` emits exactly
6 tokens per poly (`PB`, `b`, `O`, `O`, `N`, plus a leading/merged `b`) plus one trailing `b` — so
token count, not poly count, is what a naive diff shows. Decoded properly:

- **N=58 (byte-exact, both sides): world `Model2.Polys` = 16 polys.**
- **N=59 ref (UED22): world `Model2.Polys` = 1 poly** — Brush904's own poly, verbatim
  (`Actor=Brush904`, `Texture=HK_BuildingExt.Concrete.ClenWhteWall_F`), UNCLIPPED.
- **N=59 native: world `Model2.Polys` = 16 polys** — composition ~unchanged from N=58 (still
  carries old brushes, e.g. `Brush323`'s poly is still first in the list); does not reproduce the
  collapse.

So: adding this one `PF_Semisolid` `CSG_Add` brush makes UED22 **discard all 15 pre-existing
world-soup polys**, keeping only the new brush's own. Native does not do this at all.

**Confirmed reproducible, not a one-off editor glitch**: forced TWO independent fresh rebuilds of
the editor reference (`ladder_run.py --force-ref`) — both gave exactly 1 poly. The N=1..58 history
being byte-exact rules out the 16-poly N=58 baseline being wrong.

## Root cause — NOT identified

Not a texture/import naming issue (see "side observation" below — that was a red herring from an
unrelated first run). The real mechanism is almost certainly that UED22's world `Model.Polys` is
not a simple "accumulate every CSG-surviving fragment across brush history" array — something
about a `PF_Semisolid` `CSG_Add` brush triggers a wholesale regeneration/prune of the soup (most
likely in `bspBrushCSG`'s semisolid-add path, or a `bspCleanup`/`bspOptGeom` step that rebuilds
`Model.Polys` from the current BSP node tree rather than brush history, and this subset's tree
happens to collapse to one node once semisolid handling is applied). Not RE'd — this needs either
disassembly of `bspBrushCSG`'s `PF_Semisolid` branch, or a live gdb capture at that call for this
exact repro (hex-precision, per `dev/docs/spikes/2026-09-13-crossing-vertex-live-capture/`'s
method), before a faithful fix can be written. Per the campaign's prime directive, this must not be
guessed at or patched to fit this one case.

## Side observation (separate, unconfirmed — do not conflate with the above)

The very first repro run of this investigation showed native producing 79 imports instead of the
correct 62 (17 duplicate `Package.Name`-flattened texture imports missing their `.Group.` segment,
e.g. `HK_BuildingExt.ClenWhteWall_F` instead of the correct `HK_BuildingExt.Concrete.ClenWhteWall_F`
already used elsewhere in the package). Three subsequent rebuilds (one force-ref re-verify + two
native-only rebuilds) all produced the correct 62 imports. Could not reproduce a second time —
likely an artifact of the scratch state from manual investigation (a stale/partial subset dir), not
a real bug, but flagging in case it recurs: if seen again, suspect `unbuilt.py`'s `tex_ref` closure
(`_assemble_once`, the `by_name`/`ref_pkgs`/`min(loaded, ...)` tie-break) for order-dependent
behavior over a `set()`.

## Repro

    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
        --dx dev/games/deusex/Maps/06_HongKong_WanChai_Market.dx --from 59 --to 59 --keep-native

Then decode `Model2`'s `Polys` export (`export_identity == "polys polys@model model2"`) with
`parity_gate.canon_body` on both `native_N59.dx` and `ref_N59.dx` — do NOT eyeball
`_polys_tail`'s raw token list as one-token-per-poly; group into 6-token runs (see above) or count
`("O", "brush ...")` owner tokens to get the true poly count.

## Status: FIXED 2026-09-14

Root-caused via live gdb capture (`dev/docs/spikes/2026-09-14-wanchai-n59-semisolid-repartition-order/`,
`repart_order_trace.py`) plus fresh disassembly of `Editor.dll 0x10049380` (`sub_49380`, the frontier
collector `bspRepartition`'s per-child loop reads). Not a `bspBrushCSG`/`bspOptGeom` semisolid-branch
issue as originally suspected — the world `Model.Polys` soup collapse is a side effect of an existing,
correct mechanism (`repartition_frontier`: the LAST frontier subtree repartitioned each pass wins
`Model.Polys`, since every call overwrites it) hitting a case it had never exercised before: TWO
frontier slots (the pre-existing `Brush323`/`Brush324` detail-brush pair, and the new `Brush904`)
both grow a subtree in the same pass. `collect_repartition_frontier` (`uedcli-native/src/bspcsg.rs`)
recursed a node's `i_back` child before its `i_front` child; the real `sub_49380` recurses `iFront`
first (`0x100493be`-`0x100493fd`, both statically disassembled and live-captured against the actual
WanChai N=59 `MAP REBUILD`). Swapping the recursion order fixes it — a one-function, 8-line diff, no
new mechanism needed.

Verified: `native_N59.dx`'s world `Model.Polys` now matches `ref_N59.dx` exactly (1 poly, `Brush904`'s
own, byte-identical); `parity_gate.py` PASSes N=59; `ladder_run.py --dx .../06_HongKong_WanChai_Market.dx
--from 1 --to 59` PASSes the whole ladder (no regression on N=1..58, previously the ceiling). This
touches native's shared CSG core, so also spot-checked (single-N, unaffected): UNATCO N=225, NYC_Bar
N=152, Island N=331, OceanLab N=202. Pinned by a new cargo unit test,
`bspcsg.rs::tests::frontier_collector_visits_ifront_branch_before_iback_branch`.
