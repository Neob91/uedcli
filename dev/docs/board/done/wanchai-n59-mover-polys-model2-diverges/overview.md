+++
priority = "p2"
kind = "debug"
summary = "WanChai N=59: adding a PF_Semisolid CSG_Add brush collapses UED22's world Model2.Polys soup from 16 polys to 1 (just the new brush's own); native keeps ~16 unchanged. Root mechanism not identified -- needs bspBrushCSG/bspOptGeom RE for Semisolid Add."
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

## Status: not fixed, ceiling unchanged

WanChai stays at byte-exact N=1..58, bails at N=59. No fix applied, no exclusion proposed. This
needs the RE step above before a faithful fix is possible. Left in `inbox/` with these findings for
the next session; do not move to `to-spike/`/`done/` until the mechanism is identified.
