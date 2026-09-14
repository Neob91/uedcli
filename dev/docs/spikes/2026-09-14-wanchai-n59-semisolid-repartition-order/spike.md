# WanChai N=59 — the frontier-repartition collector recurses the wrong child first

Closes `dev/docs/board/inbox/wanchai-n59-mover-polys-model2-diverges/`: adding `Brush904` (a
`PF_Semisolid` `CSG_Add` brush, one unclosed quad) collapsed UED22's world `Model.Polys` soup from 16
polys to 1 (Brush904's own); native kept all 16 unchanged.

## Root cause

`collect_repartition_frontier` (`uedcli-native/src/bspcsg.rs`, the port of `sub_49380`) walks the
tree once, checking BOTH of a node's empty child slots and pushing to `list_a` (`i_back`-empty) or
`list_b` (`i_front`-empty). It checked/recursed `i_back` before `i_front`. Fresh disassembly of
`Editor.dll 0x10049380` (`dev-container`'s build image extracted `Editor.dll` from
`ued-x86-runtime:latest`, `/opt/UED22/Editor.dll`) shows the real order is the opposite: `iFront`
(`+0x24`, into `List1`) is checked/recursed BEFORE `iBack` (`+0x20`, into `List2`)
(`0x100493be`-`0x100493fd`).

This only shows once TWO OR MORE frontier slots each grow a subtree in the same
`repartition_frontier` pass — each call overwrites `model.polys` with its own subtree's soup, so the
LAST call wins, and intra-list order decides which one that is. WanChai N=59 has two: `Brush323`/
`Brush324` (an existing detail brush pair, already present at N=58) and the new `Brush904`. Both
attach to leaf slots discovered on `list_b` (`i_front`-empty); native's `i_back`-first recursion
visited `Brush904`'s slot before `Brush323`/`324`'s, so the OLD, unrelated subtree's soup won.

## Live verification

`harness/repart_order_trace.py` breaks on the WHOLE `MAP REBUILD` of the WanChai N=59 subset (the
same 59-actor trunk `ladder_run.py`/`actor_parity.py` build, MAP IMPORT + dummy builder) at:
`bspBrushCSG` entry (`0x100355e0`), `bspRepartition(Model, iChild, 2)` entry (`0x10049fc0`), its
`bspRefresh` exit marker (`0x1004a05f`), and `bspAddNode` (`0x10034e80`, dumping the first call's
`iLink`/`Base`).

`logs/repart-order-n59.log` (raw capture): 42 structural `bspBrushCSG` calls, then ONE
`bspRepartition` call (`child=0`, the whole-tree structural repartition, matching native's own
pre-Pass-2 step) — then 3 more `bspBrushCSG` calls (the detail/Pass-2 loop: `Brush323`, `Brush324`,
`Brush904`) — then exactly two more `bspRepartition` calls:

    CALL idx=2 child=449  ADD ilink=295 base=-489.3726,-512.0,3200.0   (Brush323's own face)
    CALL idx=3 child=467  ADD ilink=311 base=-128.0,-254.0,704.0       (Brush904's own face)

`child=449` (the Brush323/324 subtree) runs BEFORE `child=467` (Brush904's) — the real editor's
`Model.Polys` ends up as `child=467`'s soup (Brush904's single poly), matching UED22's golden
exactly. This is also the SAME node indices native's own tree uses for these two subtrees — both
builds' post-repartition trees are otherwise structurally identical, which is what let a
single-line reorder fix it and what lets this capture's node numbers be read directly against
native's own diagnostic dump.

## Why no `iFront`/`iBack` swap applies here

`bspcsg.rs` documents, in several OTHER places (`repartition_frontier`'s own doc,
`find_nearest_vertex`), that native's incrementally-CSG-built tree (`bsp_brush_csg`'s own node
placement, Pass 1) has `i_front`/`i_back` SWAPPED relative to the engine's real `iFront`/`iBack` —
an independently-established fact for THAT tree. `collect_repartition_frontier` does not walk that
tree: it runs after the whole-tree structural repartition (`bsp_build`) has already replaced
`model.nodes` from scratch via `split_poly_list`. `split_poly_list` (`Editor.dll 0x34530`) is a
literal, unswapped port — its own recursion order (`NODE_FRONT` before `NODE_BACK`, `bspcsg.rs`
~line 2155) follows `FPoly::split_with_plane`'s real `Front`/`Back` classification, matching the
editor's own `FrontList`/`BackList` directly (see that function's doc comment; not modified by this
change). So on the tree `collect_repartition_frontier` actually sees, native's `i_front`/`i_back`
already coincide with the editor's real `iFront`/`iBack` — no translation needed, and the fix
(check `i_front` first) is a direct, unswapped port of `sub_49380`'s disassembled order. The doc
comment on `collect_repartition_frontier` spells this distinction out explicitly, since a reader
who only knows the OTHER (correctly swapped) convention would otherwise read this fix as backwards.

## Fix

`uedcli-native/src/bspcsg.rs`: swap the two branches in `collect_repartition_frontier` so `i_front`
is checked/recursed before `i_back`. Verified: `native_N59.dx`'s world `Model.Polys` now matches
`ref_N59.dx` exactly (1 poly, `Brush904`'s own, byte-identical base/actor/texture);
`parity_gate.py` PASSes N=59; `ladder_run.py --from 1 --to 59` PASSes the whole WanChai ladder (no
regression on 1..58); spot-checked UNATCO N=225, NYC_Bar N=152, Island N=331, OceanLab N=202 (all
PASS — this is a shared CSG-core change).

## Pinned

`bspcsg.rs::tests::frontier_collector_visits_ifront_branch_before_iback_branch` — a 3-node synthetic
tree where the real order (`i_front` before `i_back`) and the old, buggy order (`i_back` before
`i_front`) produce different `list_b` contents; asserts the real one.
