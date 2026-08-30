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
before/after all of this round's diagnostics).

**CORRECTED same day: nodes are NOT held in a separate scratch `UModel` — they're added directly to
the persistent Model, past its own `Nodes.Num`, then discarded by a real `FArray::Remove` every
single call. The earlier "scratch model accumulates nodes" entry (below, kept for the record) is
REFUTED by direct live evidence — do not rely on it.** (2026-08-30, 🔬, supersedes the disasm-only
entry immediately below) — `repart_addnode_model_trace.py`: live-captured `bspAddNode`'s
(`Editor.dll 0x10034e80`) own `Model` argument (`esp+4`) for all 29 node-adds under `child=6108`'s
`bspRepartition` call and diffed each against that SAME call's own `Model` arg — **0/29 mismatches**:
every add targets the persistent Model directly, never a separate object. `nodesnum_watch.py`: a
hardware watchpoint on the persistent Model's `Nodes.Num` (`+0x5c`) across a full `MAP REBUILD` shows
real `+1` writes at each `bspAddNode` call (PC `0x19bb062`, called from `Editor.dll 0x10031cc4` /
`0x10035188`), growing the counted array — so the EARLIER static-disassembly reading of `bspBuild`'s
`esi` (Flag=2, `SplitPolyList` target) as "a separate scratch object" was a mis-tracked register: it
is, in fact, the SAME persistent Model, just referenced past its own `Num` boundary as temporary
scratch slots within the SAME allocation. At the end of every subtree call, `bspRefresh`
(`Editor.dll 0x10036e86`) calls `Core.dll!Remove@FArray@@QAEXHHH@Z` (IAT `0x100ce7f4`, confirmed by
symbol, not inference) with `(StartIndex=kept_count, Count=current_Num-kept_count,
ElementSize=0x40)` — a genuine array-shrink, not a reset-to-constant. For every subtree call sampled
so far (callidx 2–44 of 209, live-verified via the watchpoint's Old/New value pairs, including
`child=6108` itself, independently known to have a `+1` node delta by isolated-subtree comparison)
`kept_count` lands at EXACTLY the pre-call baseline (6314) — net zero growth, even for a subtree
whose isolated reconstruction differs by one node. Checked whether the ROOT node's own fixed slot is
where the real content lands: `node_content_before_after.py` read `Nodes[6108]`'s full 64 raw bytes
(`FBspNode` stride, matching the `Remove` call's own `ElementSize=0x40`) at `child=6108`'s
`bspRepartition` entry and again at its `bspRefresh` return — **byte-for-byte IDENTICAL**. So the
subtree's root slot is not rewritten in place either; whatever growth+shrink happens during the call
must be pure working scratch for computing content that lands somewhere else (an existing descendant
slot, not yet checked) or the call is a genuine no-op for the majority of subtrees (matching "only
3–9 of 209 calls have any delta" from the earlier per-call board-item findings) with real writes
concentrated in the FEW calls that DO have a delta — not yet distinguished live. Separately, the CTX
object from the entry below (`bspbuild_ctx_dump.py`'s `ebx≠esi` finding) is real and still stands —
`bspMergeCoplanars` genuinely operates on a distinct object's `Polys` sub-array — but it holds the
FPoly/poly-list WORKING SET for `bspBuildFPolys`/`bspMergeCoplanars` only, not the node tree; node
writes always target the persistent Model, confirmed above.

**Next step, precisely scoped:** live-check whether `child=6108`'s DESCENDANT node slots (its
original `iFront`/`iBack` and their own children) change content across this same call — the check
above only covered the subtree's root/parent slot, which turned out unchanged. If descendants also
come back byte-identical for a call independently known to have a `+1` delta, the delta must be
represented some OTHER way (a distinct `iFront`/`iBack` value pointing at a fixed slot within
`[0,6314)` that legitimately holds different content than before world-level building, not caught by
a single before/after diff at fixed indices) — worth a broader per-subtree scan, not single-node
spot checks, in a future round.

**REFUTED 2026-08-30 (see correction above, kept for the record) —
`bspRepartition`'s per-subtree call builds into a SEPARATE, persistently-reused SCRATCH `UModel`,
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
sub-array (`[[CTX+0x54]+0x2c]`, `FPoly` stride `0x1d8`), never touching the persistent Model — THIS
PART STILL STANDS, see correction above. The REST of this entry (scratch holds/accumulates Nodes,
`bspBuild`'s Flag=2 skips `EmptyModel` to append into the scratch's node array) is WRONG — live
evidence above shows node writes go straight to the persistent Model past its own `Num`, not to a
separate scratch object.

**Breadth geometry check, 10 new OG levels (Endgame4/NYC-Bar/NYC-Underground04/Paris-Club/
NYC-ShipFan/Vandenberg-Gas/Wanchai-Garage/Paris-Underground/NYC-747/OceanLab-Lab)** (2026-08-30, 🔬,
`dev/docs/board/inbox/breadth-geometry-check-on-10-new-og-levels-1-10/`) — 1/10 exact: Endgame4
(6-brush cutscene map, exact on every count incl. verts/points/vectors — same trivial-map pattern as
`DX.dx`, not `Wanchai`-class evidence). Wanchai Garage/Paris Underground/NYC 747/OceanLab Lab are a
SEVERE under-build family (-13% to -22% nodes AND double-digit-percent surfs together, up to -19.7%
surfs on OceanLab — the largest level tested, 1886 brushes), matching the already root-caused
`native-under-builds-area51-entrance-geometry` over-carve mechanism — not re-investigated, just
re-observed at 4x new instances, including at the largest scale tested so far. Updated corpus: 3/21
levels exact (14.3%), or 1/19 excluding the two trivial cutscene maps (~5.3%) — sample breadth (21 of
~20-30 total OG levels) is no longer the limiting factor, the parity RATE is.

**Descendant-slot check on Wanchai's 9 known-delta `repartition_frontier` calls: ZERO content
change anywhere, root or descendants — the "editor's own subtree call is a no-op" reading now
generalizes cleanly** (2026-08-30, 🔬) — `node_content_before_after.py` (same day, earlier) found
UNATCO `child=6108`'s own ROOT node slot byte-identical before/after its `bspRepartition` call. That
checked only one node; `wanchai_descendant_slots.py` extends it to the WHOLE subtree: for each of
Wanchai's 9 known-delta calls (`11633/11295/11291/11287/11283/11206/11211/11216/11201`, from
`wanchai-verts-points-residual-independently`), BFS-walks `iFront`/`iBack` (`FBspNode` offsets
`+0x20`/`+0x24`, per `bspcsg.rs`'s own "ENGINE convention" comment) from the root AT CALL ENTRY,
captures every reached node's full 64 raw bytes (`FBspNode` stride `0x40`), then re-reads the SAME
indices at the call's own `bspRefresh`-return marker. **43 total slots across all 9 subtrees (4 of
the 9 are single-leaf, `nslots=1`, no descendants at all) — 0 changed.** Combined with
`nodesnum_watch.py`'s finding that `Nodes.Num` always nets to the pre-call baseline, this rules out
BOTH candidate commit sites (net array growth, in-place content rewrite) for the calibration set
available. Reframes the open question: since the editor's own `repartition_frontier`-equivalent call
appears to be a genuine no-op for these specific subtrees (nothing observably changes, at the node
level, anywhere reachable from the call's own target), the "+1/+delta" mismatch these subtrees show
under isolated NATIVE-vs-editor comparison may not be about an undiscovered editor commit mechanism
at all — it may mean the CORRECT content was already established by an EARLIER pass (world-level or
zone/detail-loop, before `repartition_frontier` ever runs), and NATIVE's own reconstruction for these
specific subtrees is diverging from something that was already right, rather than from something the
editor is about to change. Not yet tested: whether that earlier-pass content matches native's
"already merged" expectation directly (would need a world-level-only capture, no subtree loop). Tool
files: `wanchai_descendant_slots.py`, `node_content_before_after.py`,
`repart_addnode_model_trace.py`, `nodesnum_watch.py` (all in
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`). No `bspcsg.rs` changes; read-only
live capture only. `bin/test -k bspcsg` (84/84) and `regression_gate.py`'s default path unchanged
(UNATCO nodes 6321 vs golden 6314, Wanchai exact at 11648) before/after.

**CORRECTION, same day: the per-call "editor real Δverts" methodology (`repart_child_trace.py`'s
live `bspAddNode`-during-the-call capture) measures TRANSIENT, DISCARDED scratch construction, not
the real persistent tree — invalidating the "9 known-bad calls" delta table in
`wanchai-verts-points-residual-independently`. Once measured against the true persistent content,
all 9 of those calls show ZERO delta, not the tabulated +4/+8s.** (2026-08-30, 🔬, corrects the
`repart_child_trace.py`-derived "editor real Δverts" column used throughout both
`wanchai-verts-points-residual-independently` and, by the same methodology,
`unatco-verts-points-residual-after-the-zone`'s `child=6108`/`4077`/`3086` figures — NOT
independently re-checked for UNATCO this round, flagged as a re-examination risk) — Extended
`wanchai_descendant_slots.py`'s BFS to also follow `iPlane` (the coplanar-duplicate chain,
`FBspNode` `+0x28`) after finding the original version silently missed 12 of 43 nodes for the 4
coplanar-leaf targets (`11206/11211/11216/11201`, each `iFront=iBack=-1` but a live 4-node `iPlane`
chain). Rerun: **55 total slots across all 9 subtrees — still 0 changed**, now covering every node
reachable by any of the three link fields. Separately, cross-referenced `prepart_tree_wanchai.py`'s
existing "state right before `repartition_frontier`'s subtree loop begins" dump (`callidx==2`,
already committed, no new capture needed): for EVERY ONE of the 9 targets, the pre-existing subtree
size (BFS over `iFront`/`iBack`/`iPlane`) exactly equals `orig_polys` from the per-call table (9/9
exact: 15/5/6/6/7/4/4/4/4) — the editor's real, persistent tree already represents each original
poly as one separate, unmerged node BEFORE `repartition_frontier` ever touches these subtrees. Cross
-checked UNATCO's OWN existing `prepart_tree_unatco.py` dump (same `callidx==2` checkpoint, no new
capture) for `child=6108`: pre-existing subtree size = 40 nodes, exactly matching that call's own
"40 polys" description — same pattern, second level, no new live capture needed to see it. **Given
the call is a proven no-op (55/55 unchanged) and the persistent structure is confirmed unmerged and
matches `orig_polys`, the true persistent vertex count per subtree is `orig_polys × verts-per-poly`
— and for all 9 Wanchai targets, that number is EXACTLY equal to native's own current (default,
unmerged) `Δverts`, not the tabulated "editor real Δverts" figure** (e.g. `child=11201`: table said
editor-real=4, persistent-content computation says 12 — matching native's own 12 exactly; same
exact-match pattern for all 9). So `repart_child_trace.py`'s "editor's REAL subtree is exactly 1
`bspAddNode` call, nv=4" framing (used to justify the whole "9 known-bad calls" table) was a
misnomer: that call is real (confirmed live, `bspAddNode`'s own `Model` arg matches the persistent
model, per `repart_addnode_model_trace.py`) but its RESULT never survives — `bspRefresh`'s
`FArray::Remove` discards it every time (`nodesnum_watch.py`), and the pre-existing, un-merged,
never-modified content is what actually ships. **Implication, not yet independently verified: the
Wanchai "+64 verts, attributed to `repartition_frontier`'s 119 calls" stage-count finding
(`UEDCLI_BSPCSG_STAGE_COUNTS` vs the live editor stage log) may itself be comparing against the same
flawed "transient bspAddNode capture" reference for at least these 9 calls — if so, the true source
of Wanchai's real +138-vert residual is NOT localized to these 9 calls and needs re-attribution from
scratch, not a fix aimed at `repartition_frontier`'s merge logic.** Not yet checked: whether the
`UEDCLI_BSPCSG_STAGE_COUNTS` aggregate measurement uses `prepart_tree_wanchai.py`-style persistent
snapshots (unaffected by this correction) or `repart_child_trace.py`-style per-call capture
(affected) as its editor-side reference — that's the concrete next step before touching any
`bspcsg.rs` code. No `bspcsg.rs` changes this round; read-only live capture and re-analysis of
already-committed logs only. `bin/test -k bspcsg` (84/84) and `regression_gate.py`'s default path
unchanged (UNATCO 6321/6314, Wanchai exact 11648) before/after.

**Bounded re-check on UNATCO's `child=6108` using the corrected methodology: NEITHER of the two
hypotheses this was meant to distinguish — a third story. The persistent editor content genuinely
matches native's OWN read of it (40 unmerged nodes both ways), but native's OWN reconstruction
OUTPUT still overcounts by 1 — a real bug, independent of any merge/no-merge question.**
(2026-08-30, 🔬, no new capture — cross-referenced two already-committed, methodologically distinct
sources) — `prepart_tree_unatco.py`'s existing dump (same `callidx==2` pre-`repartition_frontier`
checkpoint used for Wanchai, BFS over `iFront`/`iBack`/`iPlane`): `child=6108`'s persistent subtree
= exactly 40 nodes, 157 total verts — confirms the earlier "40 pre-existing nodes, matching '40
polys'" read. Compared against the `UEDCLI_REPART_CALL_DIAG` table in
`unatco-verts-points-residual-after-the-zone` (`orig polys=40, appended nodes=41, delta=+1` for this
same call) — critically, that table is a NATIVE-INTERNAL comparison (native's own `make_ed_polys`
read of the pre-existing subtree vs native's own `split_poly_list` output for the same subtree), NOT
an editor-side live capture, so it is NOT subject to the `repart_child_trace.py`
transient-capture flaw found above. Native's own "orig polys=40" independently confirms the
persistent content (both readings land on 40, from two unrelated sources). But native's own
"appended nodes=41" is real and unexplained by the methodology correction — from the SAME
faithfully-read 40-poly input, native's `split_poly_list`/`bsp_add_node` chain produces 41 nodes,
one too many. **This rules out hypothesis (a) — native's unmerged reconstruction is NOT already
right for this call, contra Wanchai's 9 calls, where it was.** It also does not cleanly match
hypothesis (b) — there's no sign of a merge happening upstream (the persistent target is 40
distinct, unmerged nodes, and native's own input reading already correctly counts 40, not 41 or
39). **The real bug is upstream of any merge/no-merge question: something in native's own
split/add-node logic manufactures a spurious extra node when converting an already-correctly-read
40-poly list into a node tree.** Wanchai's 9-calls-all-zero-delta finding and UNATCO's single
`child=6108` case are therefore NOT the same phenomenon — Wanchai's residual was a measurement
artifact (no real editor/native gap), UNATCO's `child=6108` (and by extension the other 2 of the
"3 calls, summing to +7" — `4096`/`3086` — not re-checked this round) is a real, unexplained
node-count overcount internal to native's split logic. Concrete next step (named, not chased this
round): trace `split_poly_list`/`bsp_add_node`'s own behavior on `child=6108`'s specific 40-poly
input to find where the 41st node comes from — a native-code debugging task, not another live-gdb
editor capture. No `bspcsg.rs` changes; this check used only already-committed logs. `bin/test -k
bspcsg` (84/84) and `regression_gate.py`'s default path unchanged (UNATCO 6321/6314, Wanchai exact
11648).

**`child=6108`'s 41st node located exactly: a real split at `depth=0` (the ROOT), on a poly the
coarse `Opt::Good` scoring heuristic never sampled — but that heuristic is itself disassembly-
verified faithful to the real editor, so the divergence is upstream (poly-list ORDER), not in
`find_best_split_exact`. No fix identified or attempted this round.** (2026-08-30, native-code
trace, no live-gdb capture) — Added two TEMPORARY env-gated diagnostics to `bspcsg.rs`
(`UEDCLI_REPART_FBS_INPUT`, dumps each input poly's `i_link`/`nv`/`actor`/`i_brush_poly`;
`UEDCLI_REPART_TRACE_LINK=<i_link>`, logs every `Split::Split` classification for polys with that
`i_link`, with the splitter's own plane and depth) — both off by default, zero effect on the
regression gate. Diffing the 40-poly INPUT multiset against the 41-node OUTPUT multiset (by
`(i_link, nv)`) pinpointed the exact discrepancy: the input has a genuine DUPLICATE poly (`actor=686,
i_brush_poly=2, i_link=3513, nv=4`, appearing twice at list positions `k=5` and `k=39`); the output
has one surviving whole (`nv=4`) and the other split into two triangles (`nv=3` each) — the missing
`(3513,4)` and the extra `2×(3513,3)`. `UEDCLI_REPART_TRACE_LINK=3513` traced this to `depth=0`: the
ROOT split's own winning candidate (`i_link=3542`, `find_best_split_exact`'s own table scored it
`splits=0`) genuinely produces `Split::Split(front_nv=3, back_nv=3)` when applied to the `i_link=3513`
poly — a real, direct contradiction between the SCORING pass and the ACTUAL split.

**Root-caused the scoring/actual mismatch, then ruled out `find_best_split_exact` itself as the
bug.** `find_best_split_exact`'s inner counting loop scores each candidate by sampling only
`j=0,inc,2·inc,…` (`inc=2` here, `Opt::Good`, `(40 poly count *0x66666667)>>35`) — BOTH duplicate
`i_link=3513` polys sit at ODD list indices (`5`, `39`), so NEITHER is ever sampled by ANY
candidate's scoring pass, for the entire `find_best_split_exact` call — a real, exploitable blind
spot. But `dev/docs/spikes/2026-07-15-native-materialize/re-raw-zones/findbestsplit-params-decode.md`
(🔬 disassembly-verified, pre-existing) states explicitly: "Both the candidate loop and the inner
counting loop stride by `Inc`" — this coarse-scoring blindness is a FAITHFUL, disassembly-confirmed
property of the real editor's own `FindBestSplit`, not a native deviation. So the mechanism that
produces the 41st node (an under-scored candidate that turns out to really split something) is
INHERENT to the real editor's own heuristic too — for native's output to diverge from the editor's
(0 splits, 40 nodes) on this SAME subtree, the poly-list ORDER itself must differ: if the editor's
real reconstruction places the `i_link=3513` duplicates at indices whose parity IS sampled (or if a
different candidate ends up winning due to order differences elsewhere in the list), the editor's
scoring would catch the split and the heuristic would pick a genuinely split-free plane instead. Not
yet checked (would need a new live capture — a `bspBuildFPolys`-stage poly-order dump for this exact
subtree, not yet built): whether native's `make_ed_polys`/`bsp_merge_coplanars` tree-walk order for
`child=6108`'s 40 polys matches the editor's real order index-for-index, particularly around
positions 5 and 39. **No fix attempted or proposed this round — `find_best_split_exact`'s scoring
loop is confirmed correct as-is; changing it would be an unverified, wide-blast-radius edit to code
that governs every BSP split in the codebase, and the actual root cause (ordering) is still
unconfirmed.** `bin/test -k bspcsg` (84/84) and `regression_gate.py`'s default path unchanged (UNATCO
6321/6314, Wanchai exact 11648) — both new diagnostics are env-gated, no default-path effect.

**The "ordering" hypothesis was wrong too — the real editor's `FindBestSplit` input for
`child=6108` is the MERGED 29-poly list, not the unmerged 40, and native's own merge function
already reproduces it exactly. This reconciles with, rather than contradicts, the Wanchai no-op
finding above: the editor's real per-call reconstruction (merged, root-plane-correct) is genuine
work — that then gets discarded by `bspRefresh`'s `FArray::Remove` just like every other call,
leaving the OLD unmerged subtree as the real, persisted output.** (2026-08-30, 🔬 live +
cross-checked against an existing native function, no code changes) — Live capture
(`fbs_root_poly_order.py`, new; reuses `repart_child_trace.py`'s proven breakpoint scaffolding) at
`FindBestSplit`'s real entry (`Editor.dll 0x100338EE`), gated to the FIRST hit after `child=6108`'s
`bspRepartition` entry (the root-level call): **`numpolys=29`, not 40** — several entries have
`nv=5`/`nv=6`, larger than any single original poly, confirming these are merged shapes. Validated
via the coordinator's own cross-check: `k=21` has `i_link=3633, normal=(1,0,0), dist=508.0` — an
EXACT match for the previously-known editor root-split plane `(1,0,0,508)`. Then, a cheap, no-capture
check: native's OWN `reduce_repartition_polys` (`UEDCLI_REPART_ISOLATED_TREE`), applied to the SAME
40-poly input, produces **`merged_count=29`** — an exact count match — and its own root node
(`ISONODE i=0`) has the SAME plane, `(1,0,0,508)`. **Native's merge implementation is correct and
already reproduces the editor's real per-call input exactly; it simply isn't invoked by
`repartition_frontier`'s default path** (`blanket_merge` is off by default; see
`unatco-verts-points-residual-after-the-zone`'s "correct per-call, wrong in aggregate" history for
why it was reverted after a blanket-apply regression).

This closes the loop with the Wanchai finding (`wanchai-verts-points-residual-independently`, same
day): the editor's real `bspRepartition` call does genuine work — reconstruct via `bspBuildFPolys`,
merge via `bspMergeCoplanars` (confirmed here, live, for `child=6108`), build a real new subtree via
real `bspAddNode` calls (confirmed earlier, `nodesnum_watch.py`'s real `+1` growth) — and then
`bspRefresh`'s `FArray::Remove` DISCARDS that entire freshly-built (merged) subtree, because it lives
past the pre-call `Nodes.Num` boundary, landing back at the exact pre-call baseline. The OLD,
UNMERGED subtree from before the call — untouched, confirmed via `node_content_before_after.py`
finding node `6108`'s own bytes unchanged — is what survives as the real, persisted output. **So the
real editor's per-call reconstruction is genuinely correct AND genuinely irrelevant to the final
tree** — it computes the right (merged) answer and then throws it away, for this call and for all 9
of Wanchai's known-delta calls alike.

**This reframes the whole bug, one more level up from anything tried or fixed this round.** Native's
`repartition_frontier` treats its own reconstruction as the FINAL result, writing it directly into
the persistent tree (no merge, by default) — producing 41 nodes instead of 40 for `child=6108`. The
real editor treats its OWN reconstruction (which DOES merge) as scratch work that gets discarded,
leaving the pre-existing subtree in place. Neither "add the merge step" (that would still commit a
different, though correctly-merged, subtree — not what the editor actually persists) nor "match the
poly order" (refuted directly — merge state was the real difference, not order) is the right fix.
The evidence now points at something more fundamental: `repartition_frontier` may need to NOT commit
its reconstruction into the persistent tree for calls the real editor also discards — which, from
the evidence gathered across this whole chain (Wanchai's 9/9, UNATCO's 1/1 checked), might be EVERY
call, not a subset. **Not established: whether ANY call ever survives being written back — the
current architecture (`compact_unreachable_nodes` running once at the very end, after ALL 209/119
calls) implies something must eventually differ from the pre-loop baseline for the tree to reach its
correct final shape, but no call checked so far (10 total: 9 Wanchai + 1 UNATCO) has shown ANY
persisted change.** That is the real open question for a future round — not scoring, not ordering,
not the presence or absence of a merge step alone, but WHERE and WHY the tree's real final shape
ever differs from what existed before `repartition_frontier`'s subtree loop began. No `bspcsg.rs`
changes this entry; `bin/test -k bspcsg` (84/84) and `regression_gate.py`'s default path unchanged
(UNATCO 6321/6314, Wanchai exact 11648).

**Candidate reconciliation (b) — "the 10 no-op calls checked are an unrepresentative,
pre-selected-as-interesting sample" — tested directly and REFUTED. 16 more UNATCO calls, chosen
from opposite ends of the 209-call sequence without any reference to native's own diagnostics, are
ALSO all no-ops.** (2026-08-30, 🔬) — `unatco_boring_calls_noop_check.py` (new; same
`iFront`/`iBack`/`iPlane` BFS + before/after byte-diff method as `wanchai_descendant_slots.py`,
triggered by `callidx` range instead of a pre-known target-child list, so the calls checked are NOT
selected by anything native's own reconstruction says about them). Two batches: `callidx` 10–17 (90
total slots across 8 calls) and `callidx` 190–197 (134 total slots across 8 calls) — chosen simply as
"early" and "late" in the sequence, not by any interestingness criterion. **Both batches: 0/0
changed.** Combined with the original 10 (9 Wanchai known-delta + UNATCO `child=6108`), that is 26
individually-checked `bspRepartition` calls, spanning two different levels and both ends of UNATCO's
own 209-call sequence, chosen by three different selection criteria (known-delta, sequential-early,
sequential-late) — ALL no-ops. This makes candidate (b) from the open-contradiction write-up
(`unatco-verts-points-residual-after-the-zone`) very unlikely: the real `+10462`-vert aggregate
growth is not plausibly hiding in "boring" calls that simply hadn't been checked yet, unless it is
concentrated in a small minority of the remaining ~183 UNATCO calls not yet sampled (not
exhaustively ruled out — 26/209 is not "every call" — but the two-batch, opposite-ends sampling
makes broad diffuse growth across "most boring calls" implausible). Candidates (a) checkpoint
misattribution and (c) a final one-time commit step after all calls finish are now the more likely
reconciliations; neither tested this round. No `bspcsg.rs` changes; `bin/test -k bspcsg` (84/84)
unaffected (no source edits this entry).

**Candidate (a) tested — checkpoint misattribution — REFUTED on its literal terms, but the SAME
analysis fully resolves the contradiction: node CONTENT/COUNT is a genuine no-op (confirmed twice
over), VERTS ARE NOT — every single one of the 209 subtree calls shows real, persistent vertex
growth, exhaustively, no sampling needed. This was hiding in an already-committed, already-cited log
the whole time; my own "no-op" framing was correct for nodes and OVERSTATED when generalized to "the
call is a no-op."** (2026-08-30, pure log re-analysis, no new live capture — exactly as directed) —
Parsed `dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/logs/repart-stage-
unatco.log` (pre-existing, cited since early in this item) directly, checking three specific claims:

1. **"210 `bspRepartition` groups" — CONFIRMED**, counted directly from raw `STAGEEND` markers: 210,
   not trusted from the prior paraphrase.
2. **"54776" is the 210th (last) group's own `E_bsprefresh` verts value — CONFIRMED** by direct
   extraction (`groups[-1]['E_bsprefresh']['verts'] == 54776`), not a different group, breakpoint, or
   post-processing artifact.
3. **`0x1004a05f` cannot fire from anywhere else — CONFIRMED by disassembly, not inference.** Static
   read (`rdis.py dis Editor 0x1004a020 0x60`) shows `0x1004a059: call dword ptr[edx+0x200]` (the
   4th internal call inside `bspRepartition`, matching vtbl+0x200 = `bspRefresh`, established earlier
   this session) with `0x1004a05f` as the LITERAL NEXT INSTRUCTION — the return address, inside
   `bspRepartition`'s own SEH-cleanup epilogue (`mov [ebp-4],-1; ...; ret 0xc`). This is a specific
   program-counter position reachable ONLY by returning from `bspRepartition`'s own 4th call — no
   other caller of `bspRefresh` (e.g. `bspOptGeom`, if it calls `bspRefresh` too) can land on this
   exact address; a different call site returns to a different PC by construction. Not a generic
   function-entry breakpoint — genuinely call-site-scoped.

All three hold up — candidate (a), literally posed ("the checkpoint isn't measuring what it claims"),
is REFUTED. **But re-parsing the SAME log's per-group deltas (not part of the coordinator's literal
checklist, but the natural next step once the log was open) resolves the whole open contradiction
directly:** of the 209 subtree-call groups (excluding group 0, the world-level call), **209/209 show
ZERO net node growth** (`E_bsprefresh.nodes == A_entry.nodes` every time — exhaustively matches the
live-verified "26/26 no-op" finding above, now confirmed for ALL 209 calls, not a sample) — but
**0/209 show zero vert growth** (`E_bsprefresh.verts != A_entry.verts`, EVERY single call, no
exceptions). Summing each call's own `(E_bsprefresh.verts − A_entry.verts)` across all 209 gives
exactly **10462** — telescoping precisely onto the established `44314→54776` aggregate figure, with
no gap and no need for any separate "final commit step" (candidate (c), now unnecessary as an
explanation — the growth is already fully, individually accounted for, call by call).

**The reconciliation:** `bspRefresh`'s compaction (`Core.dll!FArray::Remove`, confirmed via IAT
symbol) targets the `Nodes` array specifically and reverts it to baseline every call — genuinely
true, confirmed both by this log (209/209) and by live captures (`node_content_before_after.py`,
`wanchai_descendant_slots.py`, `unatco_boring_calls_noop_check.py`, 26/26 calls, byte-for-byte). But
`bspRefresh` does NOT correspondingly compact `Verts`/`Points` back down — those pools keep every
vertex allocated during each call's real (and, per `child=6108`'s finding, correctly MERGED)
reconstruction, even though the NODE structure that would reference those new vertices gets thrown
away by the same call's own `bspRefresh`. This matches the item's own pre-existing "surfs 3703→6059
(a later `bspRefresh` compacts them back to the shipped 3616)" note (surfs DO eventually get
compacted, later — verts/points never do, all the way to the final serialized map, where native's
own verts/points gap is the entire remaining residual).

**So my own "no-op" claim from earlier this session (`unatco-verts-points-residual-after-the-zone`,
"10/10", then "26/26", "the call is a proven no-op") was TRUE for node content/count specifically,
and OVERSTATED where it implied the whole call has zero persistent effect — it does not. Logging this
correction explicitly per this repo's own re-check process, since it directly contradicts the
stronger framing used in that item's most recent entries.** This closes the open contradiction from
the prior entry cleanly, with no candidate left unresolved: (a) refuted, (b) refuted, (c) unnecessary
— replaced by a precise, exhaustively-confirmed mechanism (asymmetric node/verts compaction). The
actionable direction for a future fix (not attempted this round): native's `repartition_frontier`
needs to perform the REAL per-call reconstruction (merge included, matching `child=6108`'s confirmed
`40→29` merge) so its own vertex-pool additions accumulate the same way, while still discarding the
resulting NODE structure the way the real editor does — growing verts/points without committing
nodes. No `bspcsg.rs` changes this entry (pure log analysis + one static disassembly check, no
container spin-up); `bin/test -k bspcsg` (84/84) and `regression_gate.py`'s default path unaffected.

**SHIPPED — the actionable fix from the entry above: `repartition_frontier` now reproduces the
editor's real per-call "reconstruct, discard the node tree, keep the Verts/Points" behavior exactly.
UNATCO's node/surf/leaf counts are now byte-exact for the first time in this whole investigation;
verts residual dropped from +2443 to +5. Caught and fixed a second, real latent bug along the way —
a `-1` vertex-index crash in the lighting bake that this fix's own orphan verts exposed.**
(2026-08-30, TDD + live UNATCO/Wanchai verification) — `repartition_frontier` (`bspcsg.rs`)
rewritten: for each frontier call, still runs the real reconstruction (`make_ed_polys` → always-on
`reduce_repartition_polys` merge → `split_poly_list`), but now into a throwaway `scratch =
model.clone()` instead of `model` directly. Only `scratch`'s `Verts`/`Points` growth
(`scratch.{verts,points}[before..]`) gets copied into `model`; `scratch`'s new node tree and its own
copy of the parent's rewritten child pointer are discarded — `model.nodes`/`model.surfs` are never
touched, so the parent keeps pointing at the pre-existing child exactly as before. No new surf is
ever allocated in `scratch` either: `FPoly::split_with_plane`'s fragments always preserve `i_link`
(`empty_copy`), so `bsp_add_node`'s `alloc_surf` path is never reached. Removed the now-structurally-
impossible diagnostics (`UEDCLI_REPART_COMPACT_PER_CALL`, `UEDCLI_REPART_CALL_DIAG`,
`UEDCLI_REPART_BLANKET_MERGE`, `UEDCLI_REPART_REAL_TREE`, `UEDCLI_REPART_ISOLATED_TREE`,
`UEDCLI_REPART_FBS_INPUT`) — each measured something (appended node counts, an optional/gated merge,
a grafted subtree) that no longer exists under the new architecture; kept
`UEDCLI_REPART_PERCALL_VERTS` (still meaningful, now the primary way to inspect the fix's own
behavior per call).

TDD: added `bspcsg::tests::repartition_frontier_is_a_node_noop_but_grows_verts` (needed
`PartialEq` added to `BspNode`/`Plane` in `model.rs`, a plain additive derive) — builds a real small
box model, picks any node with a real child, asserts after `repartition_frontier`: `model.nodes`
byte-identical (both length AND content, via `assert_eq!` on the whole `Vec<BspNode>`), `model.surfs`
same length, `model.verts` strictly grew. Confirmed RED against the pre-fix code (11 nodes vs 6,
the old graft appending 5) before the fix, GREEN after (85/85 total, up from 84).

Live verification, in order (per the coordinator's own sequencing — verts growth first, before
anything else): (1) `UEDCLI_BSPCSG_STAGE_COUNTS=1` on a real UNATCO build: `post-pass2` (="after the
detail loop") verts=44325, `post-repartition-frontier` (="after the ~209 sub-BSP repartitions")
verts=54781 — a **+10456** delta against the target **+10462** (`repart-stage-unatco.log`), off by
only 6 (0.06%), and `nodes` exactly 6314 at both checkpoints (matching the target precisely, since
nodes are structurally untouched by this pass now). (2) `regression_gate.py`: UNATCO
`nodes/surfs/leaves` all `d=+0` for the first time this whole investigation (was `d=+7` nodes before
this fix); `verts d=+5` (was `+2443`); `points d=+16`. Wanchai stays exact throughout (`verts d=+74`,
was `+138` — also improved, though Wanchai was never the item's primary subject). Full `bin/test`
(not just `-k bspcsg`): 12329 passed, 0 failed, both before and after this fix (no regression
anywhere else in the codebase).

**Second, real bug found and fixed along the way, not anticipated going in:** the lighting spot-check
(`light_spotcheck_unatco.py`, new — mirrors `apply.py`'s `_materialize_native` logic directly with
the same UNATCO trunk `regression_gate.py` uses, since this project doesn't use the CLI's
`level/NAME` tree convention) crashed: `lightmap bake: vert iVertex index -1 out of range [0,10758)`.
Root-caused via `light.rs`'s `validate_indices`, which scans ALL of `model.verts` unconditionally
(not just node-reachable ones) — to `reorder_points_canonical` (`bspcsg.rs`), a pre-existing points-
compaction pass whose own "surviving points" walk covered only `surf.p_base` and node-reachable
`vert.i_vertex` ranges. Its own doc comment had predicted this exact failure mode almost verbatim:
"if a future `bsp_opt_geom` ever removed/repacked verts, an orphan could name a dropped point and hit
the `-1` sentinel here — re-audit this loop then." `repartition_frontier`'s new orphan verts are
exactly that future case: unlike `bsp_opt_geom::insert_point`'s orphans (which always duplicate a
point some live ring already uses), these can name a BRAND NEW point no live node ring uses at all —
so the old compaction walk dropped it, and the -1 sentinel followed. Fix: added a third walk pass
covering every vert's own point directly (not just node-reachable ones), matching the function's
OWN already-stated intent ("a point is referenced iff some `surf.pBase` or `vert.iVertex` names it").
Verified: lighting bake now completes cleanly for UNATCO for the first time in this investigation
(previously blocked/STALE per `native-light-apply-bake-where-it-stands-and`) — `surfs`/`nodes`/
`leaves`/`vectors`/LightMap-record-COUNT all exact (3616/6314/762/599/3345 both sides), 2692/3345
records fully byte-identical, 99.23% shadow-bit agreement on grid+run-matched records. Remaining
lighting gaps (Lights entries 10646 vs 16263, some run/bits diffs) match ALREADY-TRACKED, unrelated
issues in that other item (light-run matching, `Model.Lights` count) — not new regressions from this
fix, and re-measuring that item's own UNATCO table in full is out of scope here (named as its own
follow-up, not chased).

Files: `light_spotcheck_unatco.py` (new,
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`), reused the existing lit golden
(`_scratch/native-visgate-2026-08-29/golden_unatco_lit.dx`, built 2026-08-29, unaffected by this
native-side change). `bin/test -k bspcsg` (85/85, was 84/84) and full `bin/test` (12329/0, both
before and after) both clean. `regression_gate.py`: UNATCO/Wanchai both `EXACT` (nodes/surfs/leaves),
`GATE: PASS`.
