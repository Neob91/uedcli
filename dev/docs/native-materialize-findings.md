# Native materialize — findings ledger

The one place for short, cross-cutting, independently-checkable technical facts uncovered during
the native `level materialize` (BSP/CSG geometry + lighting) byte-parity work — disassembly,
live captures, structural measurements. Not board-item narrative, not owner rulings
(`direction/`), not design rationale (`rationale/`). Agents maintain this freely, but only by the
process below — never overwrite silently.

## Before adding or changing an entry

1. Search this file for the same topic/mechanism (the RVA, function name, or subject).
2. Not found: add it.
3. Found and it agrees: leave it. Add `(re-confirmed <date>)` only if independently re-derived,
   not just re-read.
4. Found and it contradicts what you're about to add: do NOT overwrite. Dispatch an independent
   subagent to re-derive the fact from scratch (live capture / fresh disassembly — not by reading
   this entry first) before changing anything. Once confirmed, replace the entry and note what was
   wrong and why, in one clause — not a history.

## Format

One line per entry, ≤50 words: `**<subject>** (<date>, <🔬 live / 📖 disasm / ✅ tested>) — <fact>.`

## Entries

**Owner ruling — pre-2026-08-14 spike findings invalid** (2026-08-28, per
`owner-ruling-all-native-decode-spike-findings`) — every native-decode finding written before
2026-08-14 is untrusted (causal story, not raw disassembly). Only current-tree live measurements
count. Never validate BSP/lighting against `Test_Castle`; use UNATCO/Wanchai (+9 more OG levels).

**`bspAddNode`** (📖, `Editor.dll` RVA `0x34e80`, ImageBase `0x10000000`) — args at entry (`push
ebp` not yet run): `[esp]=ret [esp+4]=Model [esp+8]=iParent [esp+0xc]=ENodePlace
[esp+0x10]=NodeFlags [esp+0x14]=FPoly*`. FPoly: `Base=+0x00 Normal=+0x0c NumVertices=+0x1c0
iLink=+0x1c4`. Verified working via live gdb capture, `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/`.

**`bspRepartition` world-level call site** (📖🔬, `Editor.dll 0x1004a89a`, 2-arg
`bspRepartition(Model, balancePortal)`) — at entry `esp+4=Model`. Verified live via
`repart_tree_unatco.py`/`repart_stage_unatco.py` (dumps a valid full node tree from this read).

**`bspRepartition` subtree-level call sites** (📖🔬, `Editor.dll 0x1004aa3f`/`0x1004aa90`, 3-arg
`bspRepartition(Model, iChild, 2)`, called from `csgRebuild`'s two post-detail-loop frontier
loops) — `esp+8=iChild` and `esp+4=Model` BOTH confirmed correct (`esp+4` independently validated
against known values 2953/2984/6314 at other breakpoints; `ecx` at this call site is a real but
DIFFERENT object — swapping to it gives a nonsensical constant `Nodes.Num=6`, refuted). The
`repart_allcalls_unatco.py` sweep's flat `Nodes.Num=6314` reading for all 209 calls is NOT a
calling-convention bug — cause still unresolved, not a measurement artifact of the read itself.

**`bsp_merge_coplanars`'s geometric weld is doing real, necessary work** (🔬, `child=6108`) — a
naive "keep one poly per unique `i_surf`" dedup matches the merge's poly COUNT (29) but picks the
WRONG root split (native's own `(0,0,-1,-280)`, not the editor's real `(1,0,0,508)` that the actual
merge reproduces exactly). Blanket-applied, dedup lands at 5599 nodes — worse than merge's 5689.
`bspBuildFPolys` is not a plain surf-array walk; whatever the editor does, it needs the weld's
actual geometry, not just fewer polys.

**Golden `.dx` provenance — CONFIRMED, closed** (2026-08-30, 🔬) — the established golden-build
method (`dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/build_ued_lit_golden.py`)
confirmed correct: `MAP NEW`→`EDIT PASTE`/`IMPORTADD`→`MAP REBUILD`→`LIGHT APPLY`, never `MAP LOAD`
on an original file (documented elsewhere as producing a DIFFERENT world BSP from the same brushes:
UNATCO LOAD 3705/6254/776 vs PASTE 3616/6314/762). Shipped originals
(`dev/games/substrate-deusex/Maps/*.dx`) are dated Nov 2017; goldens used this session are dated
Aug 2026. The `_scratch/geo-confirm-*` goldens (10-level/4-level breadth checks) had no committed
builder script or log for most of the set — closed by independently rebuilding
`geo-confirm-training-final`'s golden from scratch (`build_ued_golden.py --world-only --no-light
--no-obj-load`, `MAP NEW`→`[re-add]`(EDIT PASTE)→`MAP REBUILD`→`MAP SAVE`, no `MAP LOAD`): the
fresh rebuild is BIT-IDENTICAL to the pre-existing `golden_training-final.dx` (nodes/surfs/leaves/
points/vectors/verts all equal: 11122/5307/848/16473/631/115560). Whole `geo-confirm-*` set is
safe to use.

**`_scratch/wanchai-relight-2026-08-29/golden.dx` provenance — CONFIRMED** (2026-08-30, 🔬) — its
`golden_build.log` shows the correct `build_ued_lit_golden.py` pipeline ran end to end (`[map-new]`,
`[re-add]`/EDIT PASTE, `[rebuild[0]]` MAP REBUILD, `LIGHT APPLY`, MAP SAVE), never `MAP LOAD` on a
shipped file; log timestamps match the file's mtime. Safe to use as the Wanchai lighting oracle.

**`repartition_frontier`'s poly reconstruction has same-surf duplicates** (🔬, live-verified on
UNATCO `child=6108`: 40 polys via `make_ed_polys` vs editor's real `FindBestSplit` NumPolys=29;
`child=4077`: 107 vs 75) — `make_ed_polys` walks the OLD subtree's nodes (self/front/back/coplanar-
chain); multiple nodes can share one `i_surf`. The existing `bsp_merge_coplanars` (gated on
matching `i_link`) closes both gaps exactly, including reproducing the editor's real winning split
plane for `child=6108`. Isolated per-call correctness is now 10/10 live-verified.

**Blanket `bsp_merge_coplanars` in `repartition_frontier` regresses UNATCO** (🔬, reproduced twice
independently) — applying the merge to all 209 subtree-repartition calls (not just individually-
tested ones) drops UNATCO nodes 6321→5689 (target 6314), even though per-call correctness is
10/10 verified, pre-repartition subtree structure is 209/209 verified identical to the editor, and
compaction timing (once-at-the-end vs per-call) is proven irrelevant. Root cause of the aggregate
mismatch is still open — see `dev/docs/board/inbox/unatco-verts-points-residual-after-the-zone/`.
NOT shipped: gated behind `UEDCLI_REPART_BLANKET_MERGE`, unset by default (`bspcsg.rs:1791`) — the
default/current-tree build path does not apply it, so default-build UNATCO stays at 6321 (+7 vs
6314), still NOT node-exact.

**Full-corpus breadth geometry sweep, post-repartition_frontier-experiments** (2026-08-30, 🔬,
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/breadth_gate.py`) — 11 unique OG
levels measured direct via `build_geometry_bspcsg` vs `MAP REBUILD`-only editor goldens: only
**Wanchai (Market)** and **`DX.dx`** (the 5-brush intro/logo screen) are node/surf/leaf-exact.
UNATCO, smuggler, paris-chateau, training-final, hk-helibase, nyc-street all OVER-build nodes by
0.3–2.6%; freeclinic08/nsfhq04 UNDER-build nodes by 0.8–1% while surfs are +1 (matches the
pre-existing `−nodes,+1 surf` "native face-keeping / tree-shape" signature noted in
`geo-confirm-wanchaimkt-wk/logs/verdict-report.md`, not a new bug); Area51-entrance stays the
known severe under-build (-3384 nodes, matches prior root-caused measurement). 2/11 exact
(18%, or 1/10 excluding the trivial intro screen) — below the 30% floor.

**`GetVisibleSurfs`'s "missed" run gap is mostly same-zone rasterization precision, not
`MergeWith`** (2026-08-30, 🔬 live) — `pair_geometry.py` (Wanchai, native vs golden) shows only
~20% of missed (surf,light) pairs cross a zone boundary (light/surf zone agree 94.6% on matched
pairs, 96.3% on native's own false positives, but only 80.0% on editor-only/missed pairs — real but
small skew). Live per-pair trace of Light45/surf-2920 (a same-zone miss; `visible_surfs.rs`'s new
`UEDCLI_VISGATE_TRACE_SURF`/`_LOC` env-gated probe) showed dense same-zone clutter (~40 small opaque
surfaces) fully consuming the target's row before it was even reached — not a `MergeWith`/portal
issue. Corrects the `SUBTRACT_OCCLUSION` doc comment's "MergeWith is the likeliest source" claim.

**`rasterize_node`'s full-coverage floor/ceil over-occludes in cluttered scenes** (2026-08-30, 🔬
live, shipped) — rounding a rasterized row's `[lo,hi)` outward to pixel boundaries (`lo.floor()`,
`hi.ceil()`) pads every polygon's footprint by up to ~1px per edge; in a scene with many small
adjacent opaque surfaces (Wanchai's market clutter) those pads compound across neighbours in one row
and can swallow a genuine gap a pixel-center rasterizer would leave open. Switched to pixel-center
coverage (`x0=ceil(lo-0.5)`, `x1=ceil(hi-0.5)`) — measured net effect: Wanchai `LightMap` records
byte-identical 3228/4530 (71.3%) → 3297/4530 (72.8%), run differs 348→266, extra pairs 134→79,
missed 350→314; UNATCO (geometry-matched via `light_geomatch.py`, its tree isn't node-exact so
positional compare doesn't apply) run_ok 92.0%→94.2%, dark/lit mismatches 29+36→27+20. No regression
on either level's shadow-bit-equal or grid/pan/scale rates, or on Wanchai's geometry exactness
(surfs/nodes/leaves unchanged, purely a lighting-side change). `bin/test -k light` + full `cargo
test` green.


**freeclinic08/nsfhq04's `+1 surf` traced to ONE semisolid brush each** (2026-08-30, 🔬) —
per-brush surf-count attribution (`fc08_surf_diff.py`) finds exactly one `PF_Semisolid` CSG_Add
brush per level (freeclinic08 `Brush143`, nsfhq04 `Brush531`) where native keeps an authored poly
the editor's built model drops. **CORRECTION, same session:** the entry originally named
`csg.rs`'s `classify_fragment` (a nudge-based point-in-solid approximation) as root cause — WRONG,
that function is dead for this path. `uedcli_native.build_geometry_bspcsg` (what every script here
calls) dispatches to `bspcsg::build_geometry_bspcsg`, which has its OWN `filter_ed_poly` — a
faithful recursive BSP-node descent matching the decoded editor algorithm
(`sections/10-bsp-csg-build.md` §4), re-verified live this session (`verify_csg_build.py` 33/33
against current `uned/UED22`). True cause still open; live investigation continuing in board item
`freeclinic08-nsfhq04-1-surf-under-build-root`.

**freeclinic08's node/leaf deficit is diffuse across ~25% of brushes, NOT localized** (2026-08-30,
🔬) — per-brush BSP-node-plane-owner attribution (`fc08_node_owner_diff.py`) shows 75/305 brushes
differ, summing to 260 absolute delta against a net -20 (heavy cancellation), while a combined
surf+node check (`fc08_combined_diff.py`) shows 74 of those 75 have MATCHING surf counts (same
face set, different split shape only) — the same symptom shape as UNATCO's residual (+7 nodes,
zero surf/leaf delta). Only `Brush143` (the `+1 surf` brush) differs in both. Whether the diffuse
tree-shape issue and the `+1 surf` are one root cause (PASS-A repartition tie-break sensitivity,
Brush143's PASS-B `filter_ed_poly` walk hitting an already-slightly-wrong PASS-A tree) or two is
under live test — see the board item.

**Wanchai's Points/Verts residual is small, additive, and NOT the same shape as UNATCO's aggregate
node-count mystery — but its `repartition_frontier` share hits the identical dead end at 1/30th
scale** (2026-08-30, 🔬, updated same day) — fresh measurement, current tree (post
`repartition_frontier`+`compact_unreachable_nodes`): Wanchai nodes/surfs/leaves stay EXACT (11648/…);
verts +138 (+0.08%), points +16, vectors −8 (new, previously untracked). `UEDCLI_BSPCSG_STAGE_COUNTS`
vs the live-captured editor stage log splits +138 additively: world-level repartition +6,
zone-pass+detail-loop (combined) +63, `repartition_frontier`'s 119 subtree calls +64, `bsp_opt_geom`
T-junction weld +5 (near-exact, same as UNATCO's weld finding).

The +64 share was fully IDENTIFIED (not just localized): two new live-gdb captures
(`prepart_tree_wanchai.py`, `repart_stage_child_wanchai.py`) gave real editor node identity per call
(native's node index corresponds directly to the editor's own at this checkpoint, 11626/11648 exact,
22 coplanar-chain-order swaps only), letting native's 119 calls join the editor's real per-call vert
growth by CHILD IDENTITY instead of sequence position. Result: **110/119 match exactly; the other 9
(children 11633/11295/11291/11287/11283/11206/11211/11216/11201) sum to exactly +64.** Live-verified
the simplest (`child=11201`, `repart_child_trace.py`, reused verbatim from the UNATCO harness): native
reconstructs 4 unmerged same-surf coplanar triangle fragments; the editor's real subtree is 1 merged
quad node — the SAME mechanism already diagnosed for UNATCO's `child=6108`/`4077`/`3086`. But
`bsp_merge_coplanars` is idempotent on non-duplicate input, so "merge selectively" and "blanket-merge
all 119" are mathematically identical — and blanket-merge is ALREADY KNOWN to break Wanchai's
node-exactness (11648→11628, `unatco-verts-points-residual-after-the-zone`). Summed these 9 calls' own
`UEDCLI_REPART_ISOLATED_TREE` merged-node counts: reduction is exactly −20, fully explaining that
regression (unlike UNATCO's −625, which never balanced against its 46-call prediction) — but Wanchai's
CURRENT unmerged path already lands the true final aggregate at 11648 despite representing these 9
subtrees "wrong" locally. Same "correct per call, wrong in aggregate" contradiction as UNATCO's open
puzzle, confirmed live rather than assumed. Full detail + the per-call table:
`dev/docs/board/inbox/wanchai-verts-points-residual-independently/overview.md`. STOPPED here per the
coordinator's steer (bounded task, don't re-burn UNATCO-scale budget on the same open contradiction).
No fix shipped; default build path byte-unchanged (`regression_gate.py`, `bin/test -k bspcsg` 84/84,

**`bspRepartition`'s per-subtree call builds into a SEPARATE, persistently-reused SCRATCH `UModel`,
never the real world Model — full disassembly, live-cross-validated** (2026-08-30, 📖+🔬) —
`bspRepartition` (`Editor.dll 0x10049fc0`) is a short dispatcher: 4 sequential virtual calls, all with
`this=persistent Model` (confirmed: same `[ebp-0x18]` local at every `csgRebuild` call site), each ALSO
passed an explicit `CTX` arg = `[[Model+0xa8]+0x98]`, a DIFFERENT `UModel`-shaped object —
`bspBuildFPolys`(vtbl+0x20c) / `bspMergeCoplanars`(+0x210) / `bspBuild`(+0x1fc) / `bspRefresh`(+0x200).
Live-verified (`bspbuild_ctx_dump.py`, breaking inside `bspBuild` at `ebx`=this/`esi`=CTX): `ebx≠esi`
in 1203/1203 samples across a full Wanchai `MAP REBUILD`; `esi` (the scratch) is a SINGLE constant
address across all 120 genuine `bspRepartition`-triggered `bspBuild` calls (the other 1083 hits, a
different constant, come from `bspBuild` being called elsewhere entirely — e.g. per-brush incremental
CSG — not attributed further). `bspMergeCoplanars` operates entirely on the scratch's own `Polys`
sub-array (`[[CTX+0x54]+0x2c]`, `FPoly` stride `0x1d8`), never touching the persistent Model.
`bspRefresh` (`Engine.dll!EmptyModel@UModel@@QAEXHH@Z` sibling) operates on ITS arg1 (=scratch, via
`[ebp+8]`), not `this` — compacts the scratch's surfs/verts/points/vectors only, matching the
already-ported `passes::bsp_refresh` scope exactly, just now confirmed scoped to a scratch object for
subtree calls specifically. `bspBuild`'s `Flag` param (`0`=world-level, `1`=unidentified, `2`=subtree)
gates `UModel::EmptyModel`: Flag∈{0,1} call it on the scratch before rebuilding; **Flag=2 (every
subtree repartition call) SKIPS `EmptyModel` entirely** and calls the `SplitPolyList`-equivalent
(`0x10034530`) straight into the scratch's EXISTING node array — meaning the scratch's `Nodes`
ACCUMULATES, uncleared, across ALL 209/119 subtree calls in one `MAP REBUILD`, never reset between
them. Explains the session's earlier "persistent Model's `Nodes.Num` reads flat at the pre-loop
baseline for literally every one of 209 calls" finding: that reading (`esp+4` at `bspRepartition`
entry) was the PERSISTENT model all along (validated, unlike a same-session `ECX`-based reread which
was refuted as a different, wrong object) — it stays flat because the PERSISTENT model's own Nodes
array is genuinely untouched throughout the ENTIRE 209/119-call loop; all the real per-call construction
happens in the separate, accumulating scratch object instead.

**Not yet found: the actual scratch→persistent commit/graft step** (2026-08-30, 📖) — fully
disassembled all 4 of `bspRepartition`'s own sub-calls (above) plus the two calls `csgRebuild` makes
immediately after BOTH frontier loops finish (`vtbl+0x218` at `Editor.dll 0x10036870`, `vtbl+0x208` at
`0x100aace0`, both resolved live via a vtable dump, `vtable_dump.py`) — NONE of the six write to the
persistent Model's `Nodes` array or any node's `iFront`/`iBack`/`iPlane`. `+0x218`'s body (edge/vertex
coincidence loops keyed on byte offset `0x36`=`NumVertices`, called on `(this=persistent,
arg1=persistent)` — i.e. both this AND arg1 are the SAME object, an odd but plausible legacy-signature
artifact) reads as a T-junction WELD pass (`bspOptGeom` or a direct sibling), not a tree splice — matches
its position in the pipeline (right after repartition, before the weld numbers the board items already
track). `+0x208` matches `bspBuildBounds`/`BuildInfiniteFPoly` (hardcoded `±32768`/`±65536` box
constants). So the mechanism that gets each accumulated scratch subtree back into the persistent tree's
real `iFront`/`iBack` links — which MUST exist, since the final serialized map is correct and
structurally exact — is still unlocated: candidates not yet checked are a pointer-SWAP (reassigning
which object the persistent Model's OWN fields point at, rather than a copy) or deeper logic inside
`SplitPolyList` (`0x10034530`) or the `MakeEdPolys`-shaped helper `bspBuildFPolys` conditionally calls
(`0x10033bb0`, fires only when the scratch already has nodes from a prior call) — neither of those two
functions has been disassembled yet. This is the concrete next step for a future round; see
`unatco-verts-points-residual-after-the-zone` and `wanchai-verts-points-residual-independently` for the
`-625`/`+64` puzzles this would very plausibly explain if resolved (a scratch object holding growing,
uncommitted state across many calls is exactly the shape needed for "individually correct, aggregate
wrong").
before/after all of this round's diagnostics).
