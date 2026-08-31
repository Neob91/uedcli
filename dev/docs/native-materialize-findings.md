# Native materialize — findings ledger

The one place for short, cross-cutting, independently-checkable technical facts uncovered during
the native `level materialize` (BSP/CSG geometry + lighting) byte-parity work — disassembly,
live captures, structural measurements. Not board-item narrative, not owner rulings
(`direction/`), not design rationale (`rationale/`). Agents maintain this freely, but only by the
process below — never overwrite silently.

See board item `native-light-apply-bake-where-it-stands-and` for current status, the harness
catalog, and an index of every open sub-thread — this file stays the detailed findings record.

**Standing rule (owner, 2026-08-30):** native must follow the exact same PROCESS UnrealEd does, not
just converge on a matching byte count/percentage. A fix replicates the editor's real, live-verified
algorithm — never a rounding tweak, tolerance fudge, or alternate formula chosen because it happens
to measure better. If the real algorithm isn't confidently known, log the gap as unresolved rather
than shipping an approximation.

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

**Points residual (+16 on both UNATCO and Wanchai, post-`repartition_frontier` fix): the identical
size is a COINCIDENCE, not one shared mechanism — two different-shaped errors happen to land on the
same total.** (2026-08-30, offline live measurement — `regression_gate.py` + a new env-gated
`bspcsg.rs` stage/compaction probe, no docker/gdb this round) — `regression_gate.py` baseline
confirmed both levels EXACT on nodes/surfs/leaves, points `d=+16` both. Per-stage breakdown
(`UEDCLI_BSPCSG_STAGE_COUNTS`, editor reference = `repart-stage-unatco.log`/`wanchai-ed-repart-stage.log`,
both live-captured `bspRepartition`-entry gdb logs, dated 2026-08-26/27, i.e. post-2026-08-14 and not
covered by the pre-2026-08-14 spike invalidation):

| stage | UNATCO native | UNATCO editor | UNATCO Δ | Wanchai native | Wanchai editor | Wanchai Δ |
|---|---:|---:|---:|---:|---:|---:|
| post-repartition (world-level `bsp_build`) | 5249 | 5607 | −358 | 15785 | 18544 | −2759 |
| post-testvisibility (zone pass) | 5280 | 5638 | −358 | 15801 | n/a | — |
| post-pass2 (after detail loop) | 10810 | 11445 | −635 | 16859 | 19619 | −2760 |
| post-repartition-frontier (209/119 subtree calls) | 10820 | 12909 | −2089 | 16859 | 19626 | −2767 |
| post-optgeom (weld) | 10820 | (not separately captured) | — | 16859 | (not separately captured) | — |
| final (after `reorder_points_canonical`) | 10768 | 10752 | **+16** | 16807 | 16791 | **+16** |

Two new facts pin down WHERE the sign flips and why the same total conceals different causes:

1. **`repartition_frontier`'s OWN points growth is a big miss on UNATCO, negligible on Wanchai** — its
   209/119-call share: UNATCO native +10 vs editor +1464 (native undershoots by 1454, in ONE stage);
   Wanchai native +0 vs editor +7 (undershoot of 7, noise-level). This directly refutes the task's
   working hypothesis that repartition_frontier's own scratch mechanism is where the shared +16
   "enters" — it dominates UNATCO's error budget but is irrelevant to Wanchai's.
2. **The FINAL compaction (`reorder_points_canonical`) drops exactly 52 points on BOTH levels** — new
   `UEDCLI_REORDER_POINTS_DIAG` diagnostic (`bspcsg.rs`, env-gated, zero default-path effect) dumped
   every dropped point's own coordinates: 52 genuinely distinct, level-specific coordinates each side
   (not a fixed/constant set), so the equal count is itself coincidental, not a shared bug. Critically,
   a second diagnostic (`REORDER_POINTS_REACHABLE_ONLY`) recomputed what the PRE-fix policy (drop any
   point not reachable from a live node ring — i.e. before `repartition_frontier`'s orphan-vert-keep
   fix shipped) would have kept: UNATCO 10758 (vs golden 10752, **+6** — the gap PRE-EXISTS independent
   of the orphan-vert-retention feature), Wanchai 16807 (byte-identical to the CURRENT, orphan-aware
   result — the orphan-vert-retention fix changes NOTHING for Wanchai, since its `repartition_frontier`
   phase added zero new points to retain in the first place).

**So the +16/+16 match is two different compositions landing on the same number:** UNATCO = a
pre-existing +6 "reachable-only" gap PLUS +10 from the orphan-vert-retention fix (shipped for the
lighting `-1 iVertex` crash, `unatco-verts-points-residual-after-the-zone`); Wanchai = a +16
"reachable-only" gap entirely unrelated to that fix. Neither of the task's two named candidate
mechanisms (repartition_frontier's own scratch clone; the orphan-vert-retention side effect) explains
Wanchai's share at all, and both only partially explain UNATCO's.

**The dominant SHARED mechanism across both levels is the world-level clear, not repartition_frontier**
— `build_geometry_bspcsg` (`bspcsg.rs`) does `model.{nodes,surfs,verts,points,vectors}.clear()`
immediately before the WORLD-level `bsp_build` call, and this is where the biggest single-stage gap
opens on both levels (UNATCO −358, Wanchai −2759, at the very FIRST checkpoint, before repartition or
testvisibility). This independently reproduces, in shape and cause, a **pre-2026-08-14** (thus
owner-flagged, not trusted at face value) disassembly claim in
`spikes/2026-07-15-native-materialize/sections/82-bspbrushcsg-port-decode.md` ("`EmptyModel(0,0)` +
`bspRefresh` keep-set — decoded"): `Engine.dll UModel::EmptyModel(EmptySurfInfo, EmptyGeometry)`
unconditionally clears Nodes/Verts but gates the Points/Vectors/Surfs frees on its args, so
`EmptyModel(0,0)` **keeps** Points/Vectors/Surfs; `bspRepartition` calls `bspRefresh` with
`NoRemapSurfs=1`, so the CSG-phase Points/Surfs pools survive into the repartition, unlike native's
unconditional clear. That same old write-up already flagged porting this as **high tree-regression
risk** ("entangled with `surf.pBase`/`vert.iVertex` pool indices") and explicitly did not attempt it
on its own (smaller, pre-node-exactness) test case — this round's fresh measurement on the NOW
node-exact UNATCO/Wanchai trees is consistent with, but does not itself re-derive, that old claim.

**Not a clean, isolatable fix for either level.** The initial world-level gap does NOT propagate
additively — both levels show a much larger swing during `repartition_frontier` + the final weld/
compaction (UNATCO −358→−2089 then flips to +16, a swing of +2105; Wanchai −2759→−2767 then flips to
+16, a swing of +2783) that native's own compaction (`reorder_points_canonical`, dropping only 52
points on each side) does not reproduce at anywhere near that scale — the small final residual is a
near-cancellation of much larger, only partly-understood errors, not a sign that the pipeline is
"almost right" at any single stage. **No fix shipped** — both candidate levers are either entangled
with a previously-flagged high-risk area (the world-level clear) or don't touch one of the two levels
at all (the orphan-vert-retention scope). Recommended next step for a future round: a live gdb
capture of the CURRENT (node-exact) UNATCO's `EmptyModel`/`bspRefresh` args and points pool at the
world-level `bspRepartition` boundary, to re-confirm the pre-2026-08-14 claim from scratch before
attempting a no-clear world-level repartition.

Shipped this round: two read-only, env-gated diagnostics only (`bspcsg.rs`) —
`UEDCLI_BSPCSG_STAGE_COUNTS` gained one more line (`STAGE post-optgeom`, between the existing
post-finalize and the surf/vector/point canonicalization), and `UEDCLI_REORDER_POINTS_DIAG`
(dropped-point dump + the reachable-only comparison count) is new. Both zero-effect on the default
path: `regression_gate.py` byte-identical before/after (UNATCO points `d=+16`, Wanchai points `d=+16`,
both still node/surf/leaf-EXACT), `bin/test -k bspcsg` 85/85, full `bin/test` unaffected (containerized
Rust goldens + host pytest both green — see the board item for the exact run).

**`EmptyModel(0,0)` world-level semantics — CONFIRMED live from scratch, independent of the
pre-2026-08-14 disassembly; the mechanism is real but a naive port makes Points markedly WORSE, not
better — measured and rejected.** (2026-08-30, 🔬 live gdb, UNATCO + Wanchai, new harness
`emptymodel_worldlevel_trace.py`) — Re-derived `UModel::EmptyModel`'s RVA two ways independent of the
old doc: Engine.dll's own export table (`?EmptyModel@UModel@@QAEXHH@Z`, RVA `0x16ff10`) and Editor.dll's
IMPORT table (IAT slot `0x100cee24`, holding the resolved runtime address — read directly from both PE
files, not copied from any prior write-up). Fresh disassembly of the function body (`0x16ff10`-
`0x170121`) confirms: Nodes(+0x58)/Verts(+0x68) cleared unconditionally; Vectors(+0x78)/Points(+0x88)/
Surfs(+0x98) gated as ONE block on arg1 (`EmptySurfInfo`) — `EmptyModel(0,0)` skips that block, i.e.
keeps them. Reproduces the old claim's shape from a fresh read of the binary.

**New fact the old doc never checked, live-verified on both levels:** at the WORLD-level
`bspRepartition(Model, 0)` call specifically, `bspBuild` calls `EmptyModel` with `ecx` (its "this")
EQUAL to the persistent world Model pointer captured independently from `bspRepartition`'s own stack
arg (`this_eq_m=1`, both UNATCO and Wanchai) — NOT a separate scratch/CTX object as a prior
(already-superseded) finding in this same investigation implied for `bspBuild` calls in general (that
finding's own "ebx" register read was captured at a DIFFERENT program point and does not correspond to
this breakpoint's `ebx`, which is unrelated leftover register content here, not the persistent Model).
Before/after EmptyModel itself, on the real persistent Model (UNATCO / Wanchai): Nodes 5218→0 /
16341→0 (cleared), Verts 45943→0 / 224697→0 (cleared), Points 1510→1510 / 4757→4757 (UNCHANGED),
Vectors 348→348 / 452→452 (UNCHANGED), Surfs 1720→1720 / 5322→5322 (UNCHANGED) — exact, clean
confirmation on the real object, cross-validated against already-established editor stage-log numbers
(the calls' own `STAGEEND` readings — nodes/verts/points 2953/11794/5607 (UNATCO) and 11011/43759/18544
(Wanchai) — match the pre-existing `repart-stage-unatco.log`/`wanchai-ed-repart-stage.log` "editor"
column exactly).

**Ported as `UEDCLI_BSPCSG_WORLD_KEEP_POINTS` (env-gated, OFF by default) — measured, REJECTED.**
`bsp_add_point`/`bsp_add_vector` already tolerance-dedupe (safe against a non-empty pool);
`bsp_add_node` already reuses an existing surf via `edpoly.i_link` when valid. But `bsp_build` itself
re-seeds EVERY surf fresh via `alloc_surf` regardless of `model.surfs`' prior content (`bsp_build`'s own
"one fresh surf per distinct source-surf id" contract), so Surfs must stay cleared (unrelated to
`EmptyModel`'s own semantics — this is `bsp_build`'s OWN internal indexing contract, not an
EmptyModel-clear question) — and IS already effectively parity-correct via a DIFFERENT, working
mechanism (`canon_surf_keys` + `reorder_surfs_canonical`, pre-existing). Vectors gets UNCONDITIONALLY
rebuilt later regardless (`rebuild_vector_pool`, walking the final canonical Surfs' own refs) — kept
cleared for symmetry only, confirmed to make no difference either way (`regression_gate.py`: vectors
`d=-8` both with and without the flag on Wanchai). Only Points was toggled. Result:
`regression_gate.py` WITH the flag stays node/surf/leaf-EXACT on both levels (no structural regression)
but Points goes from `d=+16`→`d=+912` (UNATCO) and `d=+16`→`d=+2673` (Wanchai) — a large, clear
regression on the exact metric this was meant to improve. `bsp_add_point`'s tolerance-dedup and
`reorder_points_canonical`'s reachability filter are not, alone, enough to bound the kept CSG-phase
Points pool back down to what the real editor's own later passes reconcile it to — the editor's real
downstream mechanism that keeps Points bounded through this same "keep" behavior is not yet identified.
**Do not re-attempt a bare "stop clearing Points" without finding that mechanism first.**

TDD: `bspcsg::tests::world_keep_points_env_var_retains_points_the_default_clear_would_lose` (new,
86th `bspcsg` test) — two overlapping ADD boxes, asserts nodes/surfs identical and points
non-decreasing between the flag on/off. Incidentally found (not investigated) a pre-existing panic on
a DIFFERENT two-box overlap scenario (`box(256,256,256@0,0,0)+box(256,256,256@200,0,0)`, both Add) —
`bsp_cleanup`'s "dead root with no iPlane successor" `debug_assert` — filed separately, see board item
`two-overlapping-add-boxes-panic-dead-root-no`.

**Not shipped to the default path.** `UEDCLI_BSPCSG_WORLD_KEEP_POINTS` stays unset by default; the
`model.points.clear()` call is now conditional on it but unconditionally clears when unset (byte-
identical to before). `regression_gate.py` with no env vars set: UNATCO/Wanchai both unchanged (node/
surf/leaf-EXACT, points `d=+16` both, verts `d=+5`/`d=+74`, vectors `d=+0`/`d=-8` — all identical to
pre-round). `bin/test -k bspcsg` 86/86 (was 85), full `bin/test` green (host pytest + containerized
`cargo test`, both before and after). New harness:
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/emptymodel_worldlevel_trace.py`.

**Round 3 — the missing downstream mechanism FOUND: the real `bspRefresh` ALSO compacts Points AND
Vectors on every call (fresh disassembly), not just Nodes. Wiring it into
`UEDCLI_BSPCSG_WORLD_KEEP_POINTS` closes nearly the whole regression (+912→+16 UNATCO, +2673→+19
Wanchai) — the flag is now a verified-working mechanism, just not better than the current shipped
default. Not switched to default.** (2026-08-30, 📖 fresh disassembly + offline measurement, no
docker/gdb needed this round) — Two offline (no live editor) diagnostics localized the entry point
BEFORE any disassembly: `UEDCLI_BSPCSG_STAGE_COUNTS` + `UEDCLI_BSPCSG_WORLD_KEEP_POINTS` together (new
harness `keep_points_stage_diag.py`) show UNATCO's points ALREADY at 21652 right after the world-level
`bsp_build`+`bspRefresh` (editor's real value at the same checkpoint: 5607) — the blowup is not
downstream of `repartition_frontier`/the weld at all, it is present at the very first post-world-clear
checkpoint. `UEDCLI_BSPCSG_POOLDUMP` traced it one step earlier: PASS 1's own incremental per-brush
`bsp_brush_csg` loop (before the world clear even runs) already holds 21362 raw Points on UNATCO, of
which only 6400 are reachable from its own tree at that point (Wanchai: 54670 raw / 19054 reachable) —
`bsp_cleanup` (Editor.dll `0x36160` port) only ever splices dead NODES, confirmed by reading its Rust
port (`cleanup_nodes`, `bspcsg.rs`): it never touches Points, so PASS 1's Points pool is pure
monotonic accumulation, unlike the real editor's (1510/4757 at the same checkpoint, per
`emptymodel_worldlevel_trace.py` above).

Fresh disassembly of `bspRefresh` (`Editor.dll`) PAST the range already decoded for the Nodes-array
`FArray::Remove` call (the existing `0x10036e86` finding) — `0x10036fb0`-`0x10037166`, read directly
off `uned/UED22/Editor.dll` via `rdis.py`, no prior write-up cited — shows it allocates TWO more remap
tables sized to `Model+0x7c` (Vectors.Num) and `Model+0x8c` (Points.Num), marks a Point used iff some
surf's `p_base` (`+0x8`) OR some (already-compacted) node's own vert-pool range (`iVertPool`/
`NumVertices@+0x36`) names it via `Vert.iVertex`, marks a Vector used iff some surf's `v_normal`/
`v_texture_u`/`v_texture_v` (`+0xc`/`+0x10`/`+0x14`) names it, physically compacts BOTH arrays in place
(dense repack + a `0x10034310` shrink call, same pattern as the Nodes `Remove` call, plus an
`appFailAssert` sanity check on the new count), then walks Surfs and Nodes AGAIN to rewrite every
surviving cross-reference to the new indices — a real, complete GC, not just marking. **This directly
refutes the "SHIPPED" entry above's own "`bspRefresh` does NOT correspondingly compact Verts/Points
back down" claim, but only for POINTS/VECTORS — that claim is CONFIRMED correct for VERTS (no verts
remap exists anywhere in this disassembled range).** The reachability RULE itself (surf.pBase / node
vert-pool `iVertex`) is exactly what native's own `reorder_points_canonical` already implements (its
doc comment even anticipated this: "native's `bsp_refresh` skips point compaction, leaving the +26
CSG-phase orphans the editor's `bspRefresh` GCs") — the new fact is that the real editor runs this
reachability GC on **every** `bspRefresh` call (world-level AND all ~209/119 subtree calls), not once
at the very end the way native's `reorder_points_canonical` does.

**Ported as `passes::bsp_refresh_points_vectors` (`passes.rs`), wired ONLY at the world-level
checkpoint (`bspcsg.rs`, right after the existing `passes::bsp_refresh(&mut model)` call) and ONLY
under the SAME `UEDCLI_BSPCSG_WORLD_KEEP_POINTS` flag — not wired into `repartition_frontier`'s own
per-call scratch-clone architecture (out of scope this round, higher regression risk).** Result,
offline, both goldens: UNATCO points `d=+912`→`+16` (now BYTE-EQUAL to the current default path's own
`+16`), Wanchai points `d=+2673`→`+19` (default path is `+16`, so 3 worse) — nodes/surfs/leaves stay
EXACT on both, verts and vectors stay byte-identical to the default path's own `+5`/`+74` and `+0`/
`-8`. **The mechanism is now fully verified: finding it and porting it makes the "keep points" world-
level semantics viable (no longer a severe regression) — but it converges to essentially the SAME
final result the current shipped default (clear + fresh rebuild) already reaches, not a better one.**
So this round closes the OPEN QUESTION (mechanism identified, confirmed, quantified) without unlocking
new forward progress on the standing byte-parity goal — the current default stays the better (simpler,
already-shipped) path to the same result.

TDD: new `bspcsg::tests::world_keep_points_with_compaction_leaves_no_orphan_points` (87th whole-crate
test, was 86 — the ledger's "`bspcsg` N/N" shorthand tracks the FULL `cargo test --lib` count, not a
`bspcsg`-only filter; `bin/test -k bspcsg` only filters the pytest phase, cargo test always runs
unfiltered) — two overlapping ADD boxes; pins that with the compaction, `WORLD_KEEP_POINTS`'s final
`points.len()` is EXACT-equal to the default clearing path's (not just bounded/smaller-than-before),
and that nodes/surfs stay identical either way. `cargo test --lib` 87/87 (was 86).

**Not shipped to the default path** — `UEDCLI_BSPCSG_WORLD_KEEP_POINTS` stays unset by default, so
`bsp_refresh_points_vectors` never runs unless explicitly opted in; `regression_gate.py` with no env
vars: UNATCO/Wanchai both unchanged (node/surf/leaf-EXACT, points `d=+16` both, verts `d=+5`/`d=+74`,
vectors `d=+0`/`d=-8` — byte-identical to pre-round). Full `bin/test` (pytest + `cargo test --lib`
87/87) green, both before and after this round's change; `breadth_gate.py` (13 cases) unaffected —
4/13 exact, same shape as the established baseline (see the board item for the exact numbers).
New/changed files: `passes.rs` (`bsp_refresh_points_vectors`), `bspcsg.rs` (wiring + new test),
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/keep_points_stage_diag.py` (new).

**Round 4, 2026-08-30 — live-confirmed the real editor's Points GC runs INSIDE `bspOptGeom`, BEFORE
the T-junction weld, and lands EXACTLY on the final golden Points count on both levels — but porting
just the ORDERING (running native's existing compaction at the equivalent earlier point) makes ZERO
measurable difference. Mechanism real, lever exhausted.** (🔬 live gdb, UNATCO + Wanchai, new harness
`bspoptgeom_pool_trace.py`) — Task: check whether the editor's real final points-compaction happens
somewhere AFTER `bspOptGeom`'s weld that native currently misses. Independently re-derived
`bspOptGeom`'s RVA two ways before trusting it (both post-2026-08-14, on UNATCO): the vtable slot
`+0x218` captured live by the pre-existing `vtable_dump.py` (`slot218=0x10036870`) plus a fresh static
disassembly of `Editor.dll 0x10036870`-`0x10036c32` this round (not copied from the pre-08-14 doc),
which also independently re-confirmed the `0x33dc0` `ShrinkModel`-style merge call's identity and
signature (`(Model, radius=0.25)`, matching `bspoptgeom.rs::merge_near_points`'s own doc comment) and
found a SECOND call immediately after it, `0x100368f4: call [eax+0x200]` (a virtual dispatch through
`bspOptGeom`'s own "this", args `(Model, 0)`) — not yet identified as any specific named function, but
live-measured directly regardless of its identity.

Bracketed all 4 points (`ENTRY`/`POST_SHRINK`/`POST_VTCALL200`/`EXIT`) with a live Points/Verts/Nodes
read of the SAME model pointer (saved once at entry, read via that pointer at every checkpoint — safe
even where a register gets reused) on the REAL UNATCO and Wanchai goldens (never `Test_Castle`):

| level | ENTRY points | POST_SHRINK points | POST_VTCALL200 points | EXIT points | golden final points |
|---|---:|---:|---:|---:|---:|
| UNATCO | 12909 | 12909 (unchanged) | **10752** | 10752 | **10752** |
| Wanchai | 19626 | 19626 (unchanged) | **16791** | 16791 | **16791** |

Two solid facts, both live-verified on both levels, neither trusted from any pre-08-14 doc:
1. The `0x33dc0` merge call does NOT physically shrink the Points array (points unchanged
   ENTRY→POST_SHRINK) — it only remaps `vert.iVertex` in place, exactly matching
   `merge_near_points`'s own doc comment ("The Points array is left intact"). That native-side claim
   is now independently reconfirmed live, not just asserted.
2. The VERY NEXT call (`[eax+0x200]`) drops Points straight from its raw accumulated count to the
   EXACT final on-disk value, on BOTH levels, before `eliminate_tjunctions`'s weld runs — and Points
   never changes again after that (flat through EXIT, confirming the weld — which grows Verts
   54776→76488 UNATCO / 112985→169313 Wanchai in the same window — never touches Points, consistent
   with the "weld is essentially exact, all the residual is upstream of it" conclusion already on
   record).

**Ported the ORDERING (not a new mechanism — reused native's own existing `reorder_points_canonical`,
called a second time between `merge_near_points` and `eliminate_tjunctions` instead of only at the
very end), gated behind `UEDCLI_BSPCSG_EARLY_POINTS_COMPACT` (off by default) — measured, NO EFFECT.**
`regression_gate.py` with the flag on: byte-identical to the flag off on every metric, both levels
(points `d=+16` both, unchanged). `UEDCLI_REORDER_POINTS_DIAG` traced why: the early call drops the
same 52 points on each level as the current default's single late call (`kept=10768`/`16807`, matching
exactly), and the subsequent late call then finds nothing left to drop (`dropped=0`) — so native's own
reachable-point SET is invariant to whether the compaction runs before or after the weld. This directly
refutes this round's working hypothesis (that the late-only call over-counts points kept alive only by
the weld's orphaned pre-splice ring copies, per `insert_ring_vertex`'s "old ring slots are never
removed" note) — timing is not the mechanism.

**Why the gap survives anyway:** editor's own RAW (pre-compaction) pool is much bigger relative to what
it drops than native's (UNATCO: editor 12909→10752, a 16.7% drop; native 10820→10768, a 0.5% drop) —
native's pool is already tight by construction (continuous tolerance-dedup via `bsp_add_point`, plus
`repartition_frontier`'s scratch-clone architecture never allocates the editor's equivalent scratch
churn in the first place), so there's little left for ANY reachability-based GC to find, regardless of
where in the pipeline it runs. The two engines are not tracking directly-comparable raw pools, so
matching the editor's GC RULE (which this round confirms native already effectively does — same 52
either way) does not converge the totals; the gap is upstream, in how the raw pool accumulates, not in
when or how it gets swept.

**Not shipped — reverted cleanly, zero footprint.** `bspcsg.rs`/`bspoptgeom.rs` are back to their exact
pre-round committed state (`git diff` empty on both files) since the experiment measured no benefit;
kept only the new live-capture harness (`bspoptgeom_pool_trace.py` — reusable if a future round wants
to inspect the RAW-pool-accumulation question directly, e.g. instrumenting the unidentified
`[eax+0x200]` call's own internals) and its two logs. `bin/test -k bspcsg` 87/87 (unchanged from the
pre-round baseline), `regression_gate.py` byte-identical before/after (both levels EXACT, points
`d=+16` both).

**Round 4 conclusion — this residual is now genuinely exhausted across 4 rounds** (not-one-shared-
mechanism; a naive "keep points" port that regresses; the same port with the just-found real
compaction mechanism wired in, converging to par-not-better; this round's compaction-ORDERING lever,
zero effect). The mechanism the task asked about (a later editor-side compaction opportunity) is REAL
and now precisely located (`Editor.dll 0x100368f4`, inside `bspOptGeom`, pre-weld) but reordering
native's own equivalent pass to match doesn't help, because native's own pool never grows large enough
for the ordering to matter. Recommend NOT picking this up again without first answering a different
question: why does the editor's raw (pre-`bspOptGeom`) Points pool run ~2000+ points hotter than
native's at the equivalent stage (12909 vs 10820 UNATCO), given nodes/surfs/leaves already match
exactly at that point — that's a raw-accumulation-mechanism gap, not a GC-timing one, and is a new,
open, differently-shaped question from anything tried in rounds 1-4. Absent someone picking that up,
better ROI elsewhere: Wanchai's still-open LIGHTING gaps (light-run matching needs `MergeWith` decoded;
a shadow-ray precision issue) — Wanchai is ALREADY node/surf/leaf-exact, so unlike freeclinic08/
nsfhq04 (blocked on their own separate geometry gap) lighting comparison there is not blocked by
anything this residual touches. New file:
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/bspoptgeom_pool_trace.py`.

**Wanchai lighting re-measured on the current (post-`repartition_frontier`) tree: 3297/4530 (72.8%)
byte-identical, unchanged from the pre-fix number — the geometry improvement (verts `+138`→`+74`)
didn't move the lighting bucket shape** (2026-08-30, offline, new harness `light_spotcheck_wanchai.py`
+ `lightparity_buckets.py`) — re-measured because the last full Wanchai lighting run predates
`repartition_frontier`'s rewrite. Fresh bucket breakdown (first-match priority grid→run→bits→pan/scale,
1233 bad records total): grid 6 (0.5%), run 261 (21.2%), bits 255 (20.7%), pan/scale 711 (57.7%) —
same shape as the prior (now-superseded) 1302-bad-record table in
`native-light-apply-bake-where-it-stands-and`, pan/scale still dominant.

**Gap 2 (per-lumel shadow-ray precision) hypothesis REFUTED — `lumel_axes`'s determinant term-grouping
is bit-IDENTICAL to the editor's `FCoords::Inverse`, both by closed-form proof and live capture; the
real bake divergence is elsewhere, not yet identified.** (2026-08-30, 📖 fresh disassembly + 🔬 live
gdb, both this session, no prior doc trusted) — `native-light-apply-bake-where-it-stands-and` names
`lumel_axes` (`light.rs`) computing `det = tu·(tv×normal)` in a "different term grouping" than
`FCoords::Inverse` (`core.dll 0x509c0`) as the likely cause of ~254 bad Wanchai records where run/grid/
pan/scale all match but shadow bits don't. Fresh disassembly (`rdis.py dis Core 0x509c0 0x1b0`+more,
not copied from any prior doc) of the full routine shows every cofactor is a single
product-minus-product (e.g. `N.z*TV.y − N.y*TV.z`) — by IEEE754 float-multiplication commutativity
(`a*b == b*a` bit-exact always) this is the SAME value as `light.rs`'s direct cross-product term
(`tv.y*n.z − tv.z*n.y`), and the determinant's 3-term sum, though accumulated as
`(A·TU.y + B·TU.x) + C·TU.z` vs Rust's `(TU.x·B + TU.y·A) + TU.z·C`, is ALSO bit-identical because
IEEE754 addition is commutative (`a+b == b+a` exactly) — the two differently-ordered PAIRS evaluate to
the same intermediate before the third add. A closed-form proof, not an approximation — confirmed
`light.rs::Vec3::dot`/`cross` compile without FMA contraction (Rust doesn't fuse mul+add by default)
so the source-level left-to-right order is what actually executes.

Also traced the calling convention (not in any prior doc): `FCoords(0,TU,TV,N)`'s ctor pushes 6 dwords
total, the LAST 4 being its own args (confirming `TextureU=ebp-0xa0`, `TextureV=ebp-0x94`,
`Normal=ebp-0x88`) and the FIRST 2 being pre-staged hidden-return-pointers for the chained
`.Inverse()`/`.Transpose()` calls — `Transpose`'s result (the `u_dir`/`v_dir` finally read off) lands
at `ebp-0x108`, still addressable right after the `Transpose` call returns (`Editor.dll 0x100a5570`).

Empirically confirmed LIVE, not just by proof: `lumel_axes_live_check.py` (new) breaks at
`0x100a5570` during a real `MAP LOAD`+`LIGHT APPLY` of the Wanchai lit golden, captures
TextureU/TextureV/Normal + the editor's REAL `u_dir`/`v_dir` for 80 real surfaces, and diffs against
`light.rs::lumel_axes`'s own formula (re-implemented in Python with per-op f32 rounding, no shortcuts)
run on the SAME captured inputs: **80/80 match, 0 mismatches** (`<1e-6` abs tolerance, well under any
plausible ulp). Separately, an offline cross-check on 30 of Wanchai's real "bits-only-divergent"
`LightMap` records (`bits_only_input_check.py`, new) found 29/30 already have BIT-IDENTICAL
Base/TextureU/TextureV/Normal between native.dx and golden.dx — meaning their `u_dir`/`v_dir` (and
thus ray origin/step) must already be bit-identical too, yet shadow bits still diverge for those
records, independently corroborating that `lumel_axes` is not the cause.

**Conclusion: no fix to `lumel_axes` — there is nothing wrong with it, live-verified. The real source
of the "bits differ, run/grid/pan/scale all agree" bucket (255 Wanchai records) is downstream of the
axis basis — most likely the shadow ray's actual `LineCheck`/BSP line-of-sight test (`linecheck::
line_clear`) — not yet investigated.** Per the owner's standing rule (replicate the editor's real
mechanism, never a fudge that merely converges): since the real cause isn't identified, no speculative
change was made to `line_clear` or anywhere else — this is exactly the "log clearly and stop" case, not
a "tune until it matches" one. New files:
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/light_spotcheck_wanchai.py`,
`lightparity_buckets.py`, `lumel_axes_live_check.py`, `bits_only_input_check.py`. No source changes;
`regression_gate.py`
byte-identical before/after (both levels still EXACT), `bin/test` unaffected (no `.rs`/`.py`
production-code edits this round).

**`line_clear`'s per-node state-threading formula INDEPENDENTLY re-derived by a from-scratch static
hand-decode of the already-committed disassembly — confirms the prior round's Finding D
transcription exactly, and finds a NEW, likely-relevant divergence in the crossing-point (`mid`)
formula. Live single-step confirmation attempted, but the breakpoint (at the shared per-ray call
site) fires for essentially every shadow ray in the whole bake — hung for 25 min with zero hits
logged, killed. NOT live-verified — static decode only, no production change.** (2026-08-30, 📖
static, no live capture succeeded) — Line-by-line SSE decode of `linecheck-target-disasm.log`'s
already-committed disassembly of the recursive walker (`target+0x5b0`, offsets `+0x92`-`+0xd5`),
cross-referenced against a fresh static disasm of the CALLER (`rdis.py dis Editor 0x100a5900 0x160`,
the `illuminateSurf` call site at `0x100a59f3`-`0x100a5a04`) to pin the argument-passing convention:
the outer call pushes `extra_flags` (4 or 0x14, matching `VIS_EXTRA_FLAGS`/`VIS_BRIGHT_CORNERS`
exactly), then two `FVector`s built from `[ebp-0x7c/-0x78/-0x74]` (the lumel position) and
`[esi+0xd0/+0xd4/+0xd8]` (`esi`=light actor, `Location`), confirming the call is
`Model->vtbl[0x58](extra_flags, lumel_pos, light_loc, 0, &out)` with `ecx`=Model — matches the
existing `linecheck.rs` doc comment's "ecx = Level->Model" claim, independently re-derived.

**Bit formula — reproduces Finding D exactly, from scratch.** Tracing `setae %cl`/`setae %al` at
`+0x81`/`+0x8c` (`front_end=de>=0`, `front_start=ds>=0`) through to the XOR/AND chain at
`+0xa3`-`+0xac`: `new_state = (((incoming_state XOR front_start) AND NodeFlags_byte) AND 1) XOR
front_start` — algebraically tests only bit 0 (`NF_NOT_CSG`) of `NodeFlags`, same conclusion as the
prior round's Finding D. Independently confirms it was read correctly the first time.

**NEW finding: the crossing-point `mid` is computed via a DIFFERENT, non-bit-identical formula.**
Native (`linecheck.rs`): `t = ds/(ds-de)`, `mid = lerp(start,end,t) = start+(end-start)*t`. The
disassembly at `+0xae`-`+0xd4` shows the editor instead computes `t' = de/(de-ds)` (a SEPARATE
division, `divss` at inner-offset `+0xae`) then `mid = end + t'*(start-end)` (`subps`/`mulps`/`addps`
at `+0xb6`-`+0xcb`) — algebraically `t'≡1-t` (verified: both formulas agree exactly at `ds=0` and
`de=0` endpoints), but NOT bit-identical, since `t` and `t'` are two INDEPENDENTLY-rounded divisions,
not related by a computed `1-t`. This matters most exactly in the traced exemplar's regime: `ds`
tiny (≈-0.0002) and `de` large (≈112.39) makes `t=ds/(ds-de)` a division dominated by the SMALL,
noise-sensitive numerator (`t≈1.78e-6`, amplifying any ULP-level imprecision in `ds` itself), while
`t'=de/(de-ds)` is dominated by the LARGE, well-conditioned `de` (`t'≈0.9999982`, comparatively
insensitive to `ds`'s exact tiny value) — a real, structural reason the two engines could reach
different `mid` points, and therefore different recursion outcomes, from the SAME bit-identical
`ds`/`de` pair, precisely in the near-zero-plane-crossing case the original manual trace flagged.
**Not live-confirmed this round** — see below.

**Live single-step attempt: hung, killed, no data captured.** New harness
`linecheck_singlestep_rec14.py` (committed, `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/
harness/`) targets the exact known-mismatching ray (`rec=14 Light42 v=3 u=0`,
`p=(1760.0,1148.125,191.87503051757812)`, `light_loc=(1570.3885...,1147.6254...,283.4671...)`, this
session's fresh `line_clear_algorithm_check.py` run against the CURRENT `native.dx`/`golden.dx` —
now 40/40 golden-tree disagreements sampled, up from the prior round's 20/40, same direction split).
Design: one gdb session, a conditional breakpoint at the fixed outer call site (`0x100a5a04`) gated
on the pushed lumel-position matching the target within a tight float band, which on match resolves
the recursive walker's live (relocatable) address and arms two further breakpoints at `+0x92`
(logs `ds`,`de`,front-flags,`NodeFlags` per node) and `+0xd5` (logs the computed `mid` before each
recursive call) — scoped to just that one ray's call tree via an `$active` flag cleared at return.
**Problem found via live diagnosis, not assumed:** the container ran 25 minutes with the gdb log
still stuck at `ORACLE_ATTACHED` (0 breakpoint hits logged); `ps` inside the container showed `gdb`
at 99.6% CPU with 24:45 accumulated CPU-time and `unrealed.exe` actively running at 53.6% CPU — i.e.
`LIGHT APPLY` genuinely ran and the outer breakpoint genuinely fired, just never (yet) on a match,
because that call site is hit once per shadow-ray bit computed across the WHOLE level (on the order
of 10^5-10^6 for a level this size, per the existing "shadow bits on grid+run-matched records"
counts elsewhere in this file) — each hit costs a full ptrace stop/evaluate/resume round-trip
through Docker, so reaching record 14 of ~4530 records this way was not going to finish in bounded
time. Killed (`docker kill`/`docker rm`) rather than let it run indefinitely, per the standing
background-work rule.

**Concrete next step for a future round (not attempted, per the "don't grind" guidance once a
technique is shown to be too unwieldy):** gate the fine-grained breakpoints behind a much
LESS-frequent checkpoint than the per-ray call site — e.g. a breakpoint at `illuminateSurf`'s own
per-surface entry (hit ~4530 times total, not per-bit), conditioned on the target surf's
`iLightMap`/index, arming the per-ray/per-node breakpoints only for the duration of that ONE
surface's processing. That cuts the hit volume by orders of magnitude and should make a bounded live
trace of the `mid`-formula finding above tractable. No production code changed this round
(`linecheck.rs` untouched); no regression-gate re-run needed (nothing that could regress changed).

**Round 3 (surf-gated live trace, worked): the per-node walker examined in rounds 1-2
(`target+0x5b0`, `0x17cea70`) is the WRONG function — real zero-extent shadow rays for the traced
surface never reach it. Found and live-confirmed the ACTUAL recursive walker (`0x17ce190`), captured
its real crossing-fraction formula for the target ray's root-level call, but the full sign/role
mapping is not yet resolved -- genuinely open, not a completed pin.** (2026-08-30, 🔬 live gdb,
`linecheck_singlestep_rec14_v2.py`/`_v3.py`, new) — Implemented the coordinator's proposed fix for
round 1's volume problem: gate the ray-level breakpoint behind `illuminateSurf`'s own per-surface
entry (`Editor.dll 0x100a5010`, located fresh via a backward int3-padding scan, confirmed live to
take `iSurf` at `[ebp+0xc]`), armed only once `iSurf==4556` (the surf for record 14, computed
offline). This cut the run from a 25-minute hang with zero hits to under a minute, completing
reliably across five reruns.

**Surprise result: our exact target ray (`rec=14 Light42 v=3 u=0`, matched by exact float
comparison) reached neither the "empty model" short path NOR `target+0x5b0` before returning.** A
follow-up 20-ray survey of the SAME surface (no per-ray filter, just logging every ray's outcome)
showed ALL 20 sampled rays -- both `result=0` and `result=1` cases, i.e. both directions of the bug
-- take the SAME branch: `early_exit_0x17ce867`, reached via `call 0x17ce190` returning non-zero,
which the dispatcher then returns directly without ever touching `target+0x5b0`. So `target+0x5b0`
(the function rounds 1-2 spent a whole round hand-decoding) is real, reachable code (round 1's
un-gated first-3-hits capture did land inside it and dump a coherent disassembly) but is NOT the
path real per-lumel shadow rays for this surface take -- it must be some OTHER LineCheck variant
(box-extent collision, an actor-movement trace, or similar). **This means round 2's whole
`mid`-formula analysis (`t'=de/(de-ds)` vs native's `t=ds/(ds-de)`) was performed on a function that,
while real, is not demonstrated to be the one that actually produces this bug — an important
correction, not a refutation of that analysis' correctness on its own terms.**

**Disassembled `0x17ce190` live** (`x/500i`, no static file lookup needed since it's read straight
from live process memory) and confirmed it IS genuinely recursive: a self-call at `0x17ce3b4`
(`call 0x17ce190`), gated behind the same near/far crossing-detection shape as `line_clear`/`seg_clear`
(early returns for both-same-side cases at `0x17ce249`-`0x17ce2a9`, a crossing branch at `0x17ce2ae`
computing a fraction and a sub-segment before recursing). Captured LIVE, for the target ray's
ROOT-level call: `A=-39.1334839` (plane-dot of `point1`), `B=26.8858643` (plane-dot of `point2`),
`point1=(1570.38855,1147.62537,283.467133)` = **`light_loc` exactly**, `point2=(1760,1148.125,
191.875031)` = **the lumel position exactly** (bit-for-bit match to the known target ray, confirming
the capture is genuinely on-target) — so this build passes `(light_loc, lumel_pos)` in that ORDER,
opposite the assumed `(start=lumel, end=light)` labeling used in round 2's analysis of the other
function. Crossing fraction: `t = A/(B-A)`, live-verified exactly (`-39.1334839/(26.8858643-
(-39.1334839)) = -0.592757821`, matching the captured `CROSS_T` to 9 significant figures).

**Open, not resolved this round:** mapping this `t` onto native's `t_native=ds/(ds-de)` convention
(with `ds`=plane-dot of the segment's OWN start, `de`=of its end) requires knowing which of
`point1`/`point2` is being treated as the "current segment start" at each recursive level, which
alternates as the walk descends near/far sides (matching `line_clear`'s own `side`/`parent_csg`
alternation) — only the ROOT call was captured, so this isn't pinned generally. A naive `ds=B` (point2
=lumel=segment start), `de=A` mapping gives `t_native=B/(B-A)=0.407242`, and empirically
`editor_t = t_native - 1` for this one data point — a real, reproducible relationship, but a
`t-1` shift (not a simple `1-t` complement) implies EITHER a different base point for the lerp
(`mid = point1 + t*(point2-point1)` with `t` allowed outside `[0,1]`, still landing on the correct
line but via a different, not-yet-verified algebraic path) or a mislabeled A/B role — not
disambiguated with the data captured so far. Confirmed via disassembly that `mid = point1 +
t*(point2-point1)` (the delta computed as `point2-point1` at `0x17ce2b2`-`0x17ce2da`, scaled by `t`,
then combined with `point1` via a virtual call at `0x17ce300`) but did NOT capture the resulting mid
point's own coordinates live to check whether it lands strictly between the two endpoints, which
would resolve the open question directly — the natural next step for a future round, not attempted
here (budget/scope).

**Not shipped.** No change to `linecheck.rs` or any other production code; this round is read-only
live capture + static disassembly. `bin/test`/`regression_gate.py` not re-run (nothing that could
regress changed). New harness files (all in `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/
harness/`): `linecheck_singlestep_rec14_v2.py` (the surf-gated single-ray trace, iterated several
times in place to add the dispatcher disasm, the `0x17ce190` disasm, and the final `A`/`B`/`t`
capture — each iteration's gdb log is the source for the facts above), `linecheck_singlestep_rec14_v3.py`
(the 20-ray outcome survey that found the `target+0x5b0` misidentification). Logs:
`linecheck-singlestep-rec14-v2.log`, `linecheck-singlestep-rec14-v3.log`.

**Round 4: captured the real `mid` coordinates and traced one level deeper — CLEANLY PINS the
crossing formula (`t'=de/(de-ds)`, algebraic complement of native's `t=ds/(ds-de)`, exactly as
originally hypothesized in round 2, now proven on the RIGHT function). Implemented, TDD'd, full
`bin/test` green, geometry gate green — but the live lighting re-measurement shows a SEVERE
REGRESSION on both Wanchai and UNATCO, not an improvement. REVERTED. The formula, though
live-verified correct for the one traced crossing, does not generalize safely across the whole
population when blanket-applied — an open question for a future round, not the same thing as
"formula unknown."** (2026-08-30, 🔬 live gdb + TDD implementation + measured revert) —

**Part 1: pinned the formula with real numbers, not algebra.** Extended the surf-gated harness
(`linecheck_singlestep_rec14_v2.py`) with a breakpoint at the function's own entry (`0x17ce1b4`,
reads incoming `point1`/`point2` for EVERY call including recursive ones) and one right where the
computed `mid` local (`-0x1c/-0x18/-0x14(%ebp)`) is read for the recursive call's own argument setup
(`0x17ce387`). Captured, for the target ray's root-level crossing: `mid=(1647.60632,1147.82886,
246.166962)` — verified offline (`python3 -c`, exact f32 arithmetic) to match `lerp(start=lumel_pos,
end=light_loc, t')` to full float32 precision, where `t'=de/(de-ds)` (native's own `ds`/`de`/`start`/
`end` convention: `ds=plane_dot(start)`, `de=plane_dot(end)`) — NOT `lerp(..., t=ds/(ds-de))`, and NOT
the round-3 entry's tentative `mid=point1+t*(point2-point1)`/`editor_t=t_native-1` guess (that guess
used a wrong pairing of which local variable played which algebraic role; the real relationship is
the clean `t'=1-t` complement, confirmed to 7 decimal places: `t_native+t'=1.0000000`). This directly
confirms round 2's ORIGINAL static-only hypothesis (`t'=de/(de-ds)`, algebraically `1-t` but not
bit-identical) — derived that round from hand-reading the WRONG function, but the formula itself
turns out to be exactly right for the RIGHT one. Depth-2 trace: 15/15 further breakpoint hits were
`EARLY_RETURN_A` (both-same-side, no more crossings needed for this ray) — consistent, no
contradiction, but means only ONE genuine crossing was observed end-to-end this round.

**Part 2: implemented via TDD, following the standing rule to the letter.** Refactored `linecheck.rs`
`seg_clear`'s inline `let t = ds / (ds - de);` into a named `fn crossing_fraction(ds, de) -> f32 { de
/ (de - ds) }`, called from the same site. New test
`crossing_fraction_matches_the_editors_live_captured_formula` pins the exact live-captured numbers
(`ds=26.8858643`, `de=-39.1334839`) against both the new formula AND the resulting `mid` (within
1e-2 of the observed coordinates). Confirmed genuinely RED before the fix (temporarily reverted just
`crossing_fraction`'s body, not the test — `assert_eq!` failure `left: 0.4072422 right: 0.5927578`,
exactly the two formulas' values) and GREEN after, cleanly (a first RED attempt used an overly broad
`sed` that also clobbered the test's own local variable, giving a misleading identical-looking
failure — caught and redone correctly with a scoped `Edit`, not `sed`, before trusting the result).
`bin/test -k linecheck`: 88/88 (was 87). Full `bin/test`: exit 0 (pytest + `cargo test`, both host and
containerized phases). `regression_gate.py`: UNATCO/Wanchai both still node/surf/leaf-EXACT, points/
verts/vectors deltas byte-identical to the pre-change baseline (a lighting-only change cannot and did
not touch geometry).

**Part 3: the lighting re-measurement (the actual gate) shows regression, not improvement — reverted.**
`light_spotcheck_wanchai.py` + `lightparity_buckets.py`, before/after, same golden, same trunk:

| level | before (baseline) | with the fix | verdict |
|---|---:|---:|---|
| Wanchai byte-identical | 3297/4530 (72.8%) | 1355/4530 (29.9%) | REGRESSION |
| Wanchai `run` differs | 261 (21.2% of bad) | 1714 (54.0% of bad) | REGRESSION |
| UNATCO byte-identical | 2692/3345 (80.5%) | 1414/3345 (42.3%) | REGRESSION |
| UNATCO `run` differs | 193 (29.6% of bad) | 992 (51.4% of bad) | REGRESSION |

The dominant damage is in the `run` bucket (which light-run SET/ORDER a surface gets) — a metric
`crossing_fraction` should have NO business touching, since that's a per-lumel shadow-ray OCCLUSION
formula, not light-relevance gating. This is the concrete, measured signal that blanket-substituting
`de/(de-ds)` for `ds/(ds-de)` everywhere `line_clear`/`seg_clear` is called is NOT the same thing as
"replicate the editor's real algorithm" — the live capture only verified the formula for ONE genuine
crossing, at the ROOT level, of ONE ray, and the depth-2 trace found no second crossing to
cross-check against. `0x17ce190`'s own recursion structure (captured this round: the recursive call
always keeps `point2` fixed and only ever replaces `point1` with `mid`) does not obviously match
Rust's `seg_clear`/`descend` structure (which alternates which of `start`/`end` gets replaced,
depending on near-vs-far side) closely enough to be confident `de/(de-ds)` is universally the right
substitution regardless of recursion depth or which side is being visited — this round did not
verify that, and the population-level regression is direct evidence it is NOT simply that. Reverted
cleanly (`git checkout -- uedcli-native/src/linecheck.rs`): `bin/test -k linecheck` back to 87/87,
`light_spotcheck_wanchai.py`/`_unatco.py` both reproduce the exact baseline numbers above, confirming
the revert is complete and the regression was real (not a measurement artifact).

**Open for a future round, precisely scoped:** the crossing FRACTION formula for the one traced
exemplar is solid and live-verified; what's missing is understanding `0x17ce190`'s full recursion
structure (does it ever replace `point2` instead of `point1`? does the near/far visiting order match
native's? is there a SEPARATE code path or argument convention for the "other side" of a crossing
that this round never triggered?) well enough to port the WHOLE algorithm, not just one formula in
isolation. No `linecheck.rs` change shipped; `git diff` on that file is empty. New harness edits
retained in `linecheck_singlestep_rec14_v2.py` (now includes the `CALL_ENTRY`/`MID`/
`EARLY_RETURN_A`/`EARLY_RETURN_B` breakpoints from this round, reusable for a deeper trace).

**Round 5: `point2` staying fixed across the whole recursion is a GENUINE, robust structural
invariant — confirmed across 4 successive genuine crossings, on each of 12 different rays, not an
artifact of round 4's single-crossing sample. This means `0x17ce190`'s recursion shape is
fundamentally NOT the alternating near/far structure `linecheck.rs`'s `seg_clear`/`descend` uses —
which is the real, now well-evidenced reason round 4's formula-only substitution regressed: the
formula was correct, but grafting it onto a differently-shaped recursion was never going to work. A
full, faithful port needs a recursion-structure rewrite, not a one-line formula swap — scoped for a
future round, not attempted here.** (2026-08-30, 🔬 live gdb, no code change) —

New harness `linecheck_multicrossing_survey.py`: drops the single-ray `px`/`py`/`pz` filter from the
round 3-4 harness (whose breakpoint offsets from `0x17ce190` were confirmed STABLE across several
separate editor restarts already, so no live re-resolution was needed) and instead arms on
`illuminateSurf`'s FIRST call (whichever surface that is — turned out to be `iSurf=1`), logging full
per-ray recursion structure for the first 12 rays. Completed in under a minute, same as rounds 3-4's
technique.

**Result, ray 1 (representative — all 12 rays show the identical structural pattern, just different
coordinates):** 4 genuine crossings occur before the ray resolves (`RAY_RETURN result=0`). Grepping
just the `CALL_ENTRY` lines for this ray:

    CALL_ENTRY depth=1 point1=(1574.90796,-705.968018,179.389343) point2=(1462.90857,-1500.60205,4)
    CALL_ENTRY depth=1 point1=(1552.3092,-866.30603,144)          point2=(1462.90857,-1500.60205,4)
    CALL_ENTRY depth=1 point1=(1542.09204,-938.796997,128)        point2=(1462.90857,-1500.60205,4)
    CALL_ENTRY depth=1 point1=(1514.29736,-1136,84.4739227)       point2=(1462.90857,-1500.60205,4)

`point2` is **bit-identical** across all four physical recursive calls; `point1` starts at `light_loc`
and gets replaced by each successive `mid`, converging toward `point2` (the lumel position, i.e.
native's own `start` argument for this call). This is not a coincidence of one ray — the same exact
shape (point2 frozen, point1 shrinking) repeats identically across all 12 sampled rays this round
(different surfaces/records, different coordinates, same structural invariant).

**Methodology caveat, logged so a future reader of the raw log isn't misled:** the harness's own
`$depth` bookkeeping (incremented at `CALL_ENTRY`, decremented at `EARLY_RETURN_A`/`_B`) is WRONG as
a call-stack-depth indicator — `EARLY_RETURN_A`/`_B` do not unwind a call frame, they mark the
function's internal per-node LOOP continuing to the next node within the SAME physical stack frame
(the same tail-loop optimization already established for `target+0x5b0`/`0x17cea70` in round 1 and
described for `illuminateSurf`'s dispatcher's own loop pattern) — so several `EARLY_RETURN_A`/
`CROSS_ENTRY` pairs can appear at what the log labels as decreasing "depth" while still inside ONE
`CALL_ENTRY` frame. The `CALL_ENTRY` count itself (a fresh `call 0x17ce190`) is the reliable measure
of genuine recursion depth, and that count is what the "4 crossings" claim above is based on, not the
buggy `$depth` field.

**What this explains, concretely:** round 4's `crossing_fraction` fix computed `t'=de/(de-ds)`
correctly (live-verified to full f32 precision against the observed `mid`) but plugged it into
`seg_clear`'s EXISTING recursion, which alternates — for a crossing, it visits `[start,mid]` as the
near half and `[mid,end]` as the far half, swapping which of the ORIGINAL two endpoints survives into
each recursive call. The real editor algorithm, per this round's evidence, does no such alternation:
it always keeps the ORIGINAL query's `start`-equivalent point (`point2`/lumel_pos) fixed through the
ENTIRE walk and only ever shrinks the other end. Grafting the right formula onto the wrong recursion
shape produces a function that computes a numerically-plausible `mid` at each step but recurses on
the WRONG set of sub-segments overall — consistent with, and now a mechanistic explanation for, the
measured population-level regression (round 4's before/after table).

**Not attempted this round:** a full recursion-structure port. Understanding the loop/child-selection
mechanics well enough to safely rewrite `seg_clear`'s shape (not just its formula) — specifically
what determines the NEXT node to test within one physical frame (the `ecx`-selected child from the
`EARLY_RETURN_A`/`_B` branches) and whether the single-recursive-call structure ever needs a genuine
SECOND branch (matching native's `&&`-combined near+far) or is provably equivalent to a single-
direction walk for this specific zero-extent case — is scoped as a distinct, larger task for a future
round, not blindly attempted here per the standing rule (no fix without full live-verified
confidence). No `linecheck.rs` change this round; `git diff` on that file is empty; `bin/test`/
`regression_gate.py` not re-run (nothing that could regress changed). New file:
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_multicrossing_survey.py`; log:
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-multicrossing-survey.log`.

**`line_clear` CONFIRMED as the real cause (not a geometry residual): disagrees with the editor's real
bit even fed the editor's own real tree/inputs. Live-disassembled the real editor function on the
current build; REFUTES the old ±0.001 epsilon-tolerance hypothesis; full per-node state formula NOT
decoded — no fix.** (2026-08-30, offline decisive test + 🔬 live gdb) — New
`line_clear_algorithm_check.py`: ported `line_clear` verbatim to Python (f32-exact), self-consistency-
verified against native's OWN real output on native's OWN tree (40/40 match — the port is faithful),
then ran it against the GOLDEN's own real tree/inputs (already serialized in the lit `.dx` — `LIGHT
APPLY` never rebuilds BSP, so no live capture needed for this part) for "bits-only" bucket mismatches:
**20/40 sampled disagree with the editor's real bit**, 16/20 in the direction "line_clear says
blocked, editor says clear". This rules out the geometry-residual explanation and confirms a genuine
`line_clear` algorithm gap.

Manually traced one mismatch (`rec=14 Light42 v=3 u=0`) to a ray origin sitting ~0.0002uu off an
axis-aligned BSP plane, where `line_clear`'s strict `ds>=0.0` test takes a spurious near-zero
"crossing" split. The pre-08-14 (owner-flagged untrusted) `linecheck-oracle.md` claims a ±0.001
epsilon band would avoid exactly this. **Live-checked directly on the current build**
(`linecheck_target_disasm.py`, new): fresh disasm confirms the real call site (`Editor.dll` `illuminateSurf`,
`call dword ptr [eax+0x58]` off `Level->Model`'s vtable — independently re-derives the pre-08-14
"vtable +0x58" claim), live-resolved the real call target, and disassembled the actual recursive
per-node walker. **REFUTED**: the real classification (`comiss`+`setae`) is a strict `>=0.0` test, no
epsilon — same as native's own test. **Ruled out for the traced exemplar** (not eliminated generally):
the plane-dot is an SSE pairwise-sum dot product, different ASSOCIATION than native's left-to-right
scalar sum; provably bit-identical for the traced exemplar's axis-aligned plane (b=c=0 collapses both
orders to the same two operands), unchecked on oblique planes. **Cross-validated** existing
`model.rs`/`bspcsg.rs` node-layout assumptions live: `FBspNode` stride 0x40, children at `+0x20`/
`+0x24`, `NodeFlags` at `+0x37` — all confirmed exactly. **Not decoded**: the per-node state-threading
bit formula (XOR/AND of front-flags, incoming state, `NodeFlags`) appears, as read, to test only bit0
(`NF_NOT_CSG`) of `NodeFlags` — leaving open whether/where `NF_NotVisBlocking`/`NF_IsNew` gating
happens elsewhere, or whether the static read has an error (dense SSE register reuse, not verified by
single-stepping). Stopped here per the "log clearly, don't grind" guidance — next step named: a
live single-step trace of the same known-mismatching ray through this exact function. No production
code changed (`linecheck.rs` untouched); full findings + reusable harnesses:
`dev/docs/board/inbox/line-clear-shadow-ray-algorithm-gap-found-real/overview.md`.

**`FSpanBuffer::MergeWith` (`render.dll` file RVA `0x1001e3b0`) fully decoded — `visible_surfs.rs`'s
`merge_into` already reproduces it exactly; NOT the cause of Wanchai's zone-crossing missed-pair
share.** (2026-08-30, 📖+🔬, `mergewith-fully-decoded-confirms-merge-into`) — Full
instruction-by-instruction static disasm (`rdis.py dis Render 0x1001e3b0 0x400`, no gaps, `ret 4` to
`ret`): grows `this->Index`'s `[StartY,EndY)` row-pointer array only if `Other`'s range isn't already
contained (irrelevant to native's fixed `[0,RES)` `SpanBuf`), then for each row in `Other`'s range
does a standard two-sorted-disjoint-list merge of 12-byte `{X0,X1,Next}` nodes into `this`'s row,
`FMemStack`-allocating new nodes for anything not already `this`'s own, touching intervals (`OtherX1
== ThisX0`, `jge` not `jg`) merging same as a true overlap. `this+8` (`ValidLines` per the existing
`FSpanBuffer` struct-layout note) turns out to be a total INTERVAL-NODE count (±1 per node
alloc/absorb), not a per-ROW count as `SpanBuf::valid_lines` assumes — but every consumer
(`any_visible`, the real `ValidLines<=0` reachability test) only tests `>0`/`<=0`, which both
countings agree on, so this has no functional effect.

**Live-verified**, `mergewith_live_check.py`
(`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`): first confirmed render.dll does NOT
load at its preferred `0x10000000` base in this wine process (it loads at `0x015b0000`; only
Editor.dll keeps its preferred slot — every PRIOR live capture in this codebase happened to target
Editor.dll, so this addressing gap was latent and unnoticed) — computed the real breakpoint VA as
`render_base + (static_va - 0x10000000)`, resolved fresh from `/proc/PID/maps` each run. 10 real
`MergeWith` calls captured during a genuine Wanchai `LIGHT APPLY`: 7 pure-append (this row empty) +
3 genuine merges including two touching-boundary cases. All 10 match, node for node, what
`merge_into` independently computes from the same captured inputs. `merge_into` needed no fix; ported
the finding into its own doc comment + a new regression test (`merge_into_matches_the_real_editors_output`)
pinning the 3 live-captured merge cases. No functional code change — `regression_gate.py`: UNATCO
6314/6314 exact, Wanchai 11648/11648 exact, before and after (this change cannot affect the compiled
extension's behavior — doc comment + a `#[cfg(test)]`-gated test only). `bin/test -k visible_surfs`
88/88 green. Leaves the ~20% zone-crossing share of Wanchai's missed pairs unexplained by anything
found this round — `MergeWith` is ruled out as the cause, not identified as fixed; the real cause is
still open.

**Wanchai's zone-crossing `GetVisibleSurfs` gap root-caused and SHIPPED — `PF_Invisible` was wrongly
gating portal zone-crossing, not just emission.** (2026-08-30, 📖+🔬, live trace +
disassembly-address-ordering, TDD) — `zone_crossing_pairs.py` (new,
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`, extends `pair_geometry.py`) listed
concrete editor-only (surf,light) pairs whose light/surf BSP zones differ. Picked Light482/surf881
(Wanchai, zone 4→1 in the editor's own numbering) and traced it live with a new env-gated probe
(`UEDCLI_VISGATE_TRACE_PORTALS`, `visible_surfs.rs`, kept as a reusable diagnostic like the existing
`_TRACE_SURF`/`_LOC` pair): the ONLY portal connecting the light's zone to the target's zone (surf
998, `PolyFlags=0x4000109` = `PF_Portal|PF_NotSolid|PF_TwoSided|PF_Invisible`, IDENTICAL on native and
the editor's own golden build) was rejected before rasterization purely because `invisible=true` —
native's gate `if reachable && front_ok && !portal_needs_zones && !invisible` blocked rasterization,
the span test AND the zone-crossing merge together for any invisible surface.

Cross-checked against the board item's own disassembly (`port-urender-getvisiblesurfs-so-each-light-
gets`'s "per-node/per-surface filters, in traversal order"): step 10 (zone reachability) and step 5's
portal-crossing code (`ActiveZoneMask` OR + `MergeWith`, address `0x1001a257`) both execute BEFORE
step 11's `PF_Invisible` emission-exclusion check (`0x1001a30d`) — address ORDER, not just adjacency,
since `0x1001a257 < 0x1001a30d`. So the real editor rasterizes/tests/crosses a `PF_Portal` node
regardless of `PF_Invisible`; the flag only suppresses the surf's own appearance in the light's final
run (`iSurfs`/`Draw[]`), never the zone-crossing it performs. A `PF_Portal` surface is near-universally
ALSO `PF_Invisible` (a zone portal is not meant to render), so this bug silently blocked most/all
invisible-portal zone-crossings — a strong, disassembly-grounded candidate for a real fraction of the
~20% zone-crossing missed-pair share (`getvisiblesurfs-wanchai-run-gap-root-cause`).

**Fix** (`visible_surfs.rs::traverse`): moved the `!invisible` condition out of the shared
raster/test/portal-cross gate and into ONLY the `out.insert(n.i_surf)` step (emission) — rasterization,
`test_and_maybe_subtract` and the portal `merge_into`/`active_mask` update now run unconditionally on
`invisible` (still gated on `reachable && front_ok && !portal_needs_zones`, as before). No change to
non-portal invisible surfaces' visible-listing behavior (still never emitted); they now also get
rasterized/tested (matching the real editor's `CopyFromRaster` call for every non-occluding surface),
a functionally-harmless extra computation since `PF_Invisible ⊂ PF_NONOCCLUDING` already keeps
`opaque=false` for them (no span-buffer mutation either way).

TDD: `an_invisible_portal_still_propagates_visibility_into_its_far_zone` — a hand-built two-zone Model
(no CSG; a single portal node dividing one open volume, mirroring the real editor's "ADD portal brush
into open space" pattern) with a `PF_Portal|PF_Invisible` boundary; asserts the far wall IS reached
(RED before the fix — the portal never crossed, wall unreachable) and the portal surf itself is still
never emitted (guards against a naive "just drop `!invisible` everywhere" overcorrection). `cargo test`
89/89 (was 88; the new test is the only addition) both in isolation and full-suite.

**Measured, live, both directions of the standing regression gate:**
`regression_gate.py`/`breadth_gate.py` UNCHANGED (UNATCO 6314/6314, Wanchai 11648/11648, both exact,
before and after — this is a pure lighting-bake change, cannot touch geometry). Lighting improved on
both levels (`light_spotcheck_wanchai.py`/`light_spotcheck_unatco.py`, fresh native rebuild each side):
Wanchai `LightMap` records byte-identical 3297/4530 (72.8%) → 3319/4530 (73.3%), run differs 266→240,
shadow-bit agreement flat (99.00%→99.01%); UNATCO (geometry-matched, its tree isn't node-exact so this
is `light_spotcheck_unatco.py`'s own methodology, not the older stale table) byte-identical
2692/3345 (80.5%) → 2739/3345 (81.9%), shadow-bit agreement 99.23%→99.25%. Both real, modest,
same-direction improvements — consistent with fixing a subset (not all) of the zone-crossing share,
since only ~20% of Wanchai's missed pairs cross a zone at all and not every crossing goes through a
purely-invisible portal. `bin/test -k "visible_surfs or light"` and full `cargo test` green.

**Still open:** the remaining zone-crossing misses (this fix did not close 100% of the ~20% share),
and the much larger `Pan`/`UScale`/`VScale` bucket (the `Points`/geometry residual, unrelated,
`unatco-verts-points-residual-after-the-zone`) and the `bits`-only bucket (`line_clear`,
`line-clear-shadow-ray-algorithm-gap-found-real`) — neither touched by this change.

**Remaining Wanchai zone-crossing misses traced to two ALREADY-tracked issues, not a second
gating bug** (2026-08-30, 🔬 live, no code change) — fresh `zone_crossing_pairs.py` run against the
post-invisible-portal-fix build found new editor-only zone-crossing pairs; traced 3 live
(`UEDCLI_VISGATE_TRACE_PORTALS`). (1) Light100/48/50→surf3141 (zone2→1): `get_visible_surfs` now
ACCEPTS it (confirms the fix generalizes) but it's still absent from the final run — all 3 lights are
within radius (`worldRadius=225`, distances 127–209uu), so the residual is the already-confirmed-broken
`linecheck::line_clear` per-lumel gate (`line-clear-shadow-ray-algorithm-gap-found-real`), not
GetVisibleSurfs. (2) Light45/69→surf4846/4740 (zone1→2): the connecting portal (surf998, same one the
invisible-portal fix unblocked) shows `reachable=false` — zone1's span buffer is GLOBALLY exhausted
(`valid_lines<=0`) by DFS order before reaching it, even though OTHER portals fed by the same buffer
succeed earlier in the same traversal (rules out "portals always fail"). Light45 is the exact light
`getvisiblesurfs-wanchai-run-gap-root-cause`'s original trace used to diagnose the same-zone
clutter-over-occlusion bucket — same mechanism, now also blocking a crossing as a side effect, not a
new bug. Checked for a second "gate too much" sibling per the coordinator's named candidates:
`zones.rs::build_zone_mask` (pure OR over children's `i_zone`, no `poly_flags` test) and
`collect_zone_barriers` (oracle-validated leaf-pair-exact, `PF_PORTAL`-gated only) don't discriminate
on `PF_Invisible`/`PF_Semisolid`; `visible_surfs.rs` has no `PF_Semisolid` handling at all. None found.
No `bspcsg.rs`/`visible_surfs.rs` changes this round (pure live-trace investigation); full writeup in
`zone-crossing-getvisiblesurfs-gap-invisible`.

**`GetVisibleSurfs`'s DFS order had `far_child` interleaved BEFORE the rest of the coplanar chain —
fixed and shipped; real, positive lighting improvement on both levels, geometry unaffected.**
(2026-08-30, 🔬 disasm cross-check + TDD + live) — Investigated whether native's BSP traversal order
for `get_visible_surfs` matches the real editor's (the `zone-crossing-...` item's open tail: "zone1's
span buffer is GLOBALLY exhausted by DFS order before traversal reaches it, even though other portals
fed by the same buffer succeed earlier in the same run"). `port-urender-getvisiblesurfs-so-each-
light-gets` already documents the real per-node order from disassembly ("AddUniqueItem ... front-to-
back DFS order (near child -> own surface -> iPlane chain -> far child)") — near child, THEN own
surface, THEN the REST of the `i_plane` coplanar chain, and ONLY THEN `far_child`. `visible_surfs.rs`'s
`traverse` instead recursed into `far_child` immediately after the HEAD's own surface, before walking
the rest of the chain (the chain walk happened via the `while cur = n.i_plane` loop, but each
iteration re-triggered `far_child` = a no-op past the head since chain members carry
`i_front=i_back=-1` — except the HEAD's own iteration, where `far_child` fired with a REAL subtree,
one loop turn too early). Net effect: `far_child`'s subtree — potentially large — got to consume
shared span-buffer area BEFORE a later chain member (or a portal reached only through one) was ever
tested, an order-dependent exhaustion bug distinct from occlusion correctness.

Fixed: `traverse` now computes `near_child`/`far_child` once at the chain head, recurses `near_child`,
walks the ENTIRE `i_plane` chain testing every member's surface (a member's own zone_mask can still
early-`break` the REMAINING chain, matching the prior optimization, but no longer skips `far_child`),
and only then recurses `far_child` — matching the documented order exactly.

TDD: `coplanar_chain_is_walked_before_far_child_not_interleaved_with_it` — a hand-built model (no CSG,
`use_zones=false`) with a head node (no surface of its own), a coplanar-chain member holding a small
"target" quad, and a `far_child` holding a bigger, angularly-larger opaque quad whose screen footprint
fully covers the target's. RED before the fix (`far_child` consumed the shared buffer first, target
rejected — confirmed live: `visible={1}`, target surf 0 missing); GREEN after. `cargo test` 90/90 (was
89), full-suite and in isolation.

**Measured, live, both directions:** `regression_gate.py` UNCHANGED (UNATCO 6314/6314, Wanchai
11648/11648, both node/surf/leaf-exact, before and after — pure lighting-bake change, cannot touch
geometry). Lighting improved on both levels (`light_spotcheck_unatco.py`/`light_spotcheck_wanchai.py`,
fresh native rebuild each side, `run_diff.py` for the pair-level breakdown):

| | UNATCO (geometry-matched) | Wanchai (positional, tree node-exact) |
|---|---|---|
| records byte-identical | 2739/3345 (81.9%) → **2769/3345 (82.8%)** | 3319/4530 (73.3%) → **3408/4530 (75.2%)** |
| run identical (same set+order) | 3219/3345 → 3256/3345 | 4290/4530 → 4414/4530 |
| records where the SET differs | 126 → 89 | 240 → 116 |
| extra (surf,light) pairs native adds | 88 → 73 | 77 → **31** |
| (surf,light) pairs native misses | 111 → **149** | 268 → 209 |
| shadow-bit agreement (grid+run-matched) | 99.25% → 99.26% | 99.01% → 98.79% |

Real, positive improvement on the primary metrics (byte-identical and run-identical record counts,
extra pairs) on BOTH levels — Wanchai's gain is larger, consistent with it being the denser/more
zone-crossing-heavy level this mechanism was diagnosed against. Two metrics moved the "wrong" way and
are flagged rather than hidden: UNATCO's missed-pair count rose (111→149, even as byte-identical rows
rose) — the 89 residual set-differing records apparently miss more pairs each on average than the 126
before, i.e. fewer-but-larger residual failures, not a regression in the improved majority. Wanchai's
shadow-bit-agreement rate dipped slightly (99.01%→98.79%) — the matched-record population grew
substantially (more, and apparently larger, records now qualify as grid+run-matched), pulling in more
lumels governed by the SEPARATE, already-tracked `line_clear` bug
(`line-clear-shadow-ray-algorithm-gap-found-real`); not evidence this fix made per-lumel accuracy
worse, just that more surfaces are now exposed to that pre-existing, unrelated gap. `bin/test`
(12487 pytest passed, 90/90 cargo, full suite) and `regression_gate.py` green before and after.

**Still open:** neither level reaches 100% — the remaining gap splits across the already-tracked
`Pan`/`UScale`/`VScale` `Points`-residual bucket (`unatco-verts-points-residual-after-the-zone`) and
the `line_clear` bits-only bucket, plus whatever residual DFS-order or span-buffer subtlety remains
unexamined (not chased further this round — the specific "zone1 exhausted" symptom that motivated
this investigation is now addressed at its root, not just measured around).

**Real shadow-ray walker (`Editor.dll 0x17ce190`) recursion shape — fully resolved via full live
disassembly, not the function rounds 1-2 examined** (2026-08-30, 🔬 live `x/400i` capture +
20-breakpoint state trace, `line-clear-shadow-ray-algorithm-gap-found-real` round 6) — the real
walker is a LOOP over whole-segment (no-crossing) nodes with exactly ONE genuine recursive call
per crossing: the near call always replaces `point1` with `mid` (keeps `point2` unchanged) and
descends via `point1`'s OWN plane-dot sign (not `point2`'s); once it returns clear, the SAME frame
tail-loops (not a second call) into the other child with `point2` replaced by `mid` and `point1`
unchanged. Argument-slot layout (not sign-dependent, most reliable part of the trace) confirms this
directly. Explains round 5's "`point2` stays fixed across 4 crossings" as a structural consequence,
not a coincidence: `point2` only changes at the far-continuation tail-loop step, never during a
chain of near-recursions.

**Real shadow-ray classification uses a genuine ±0.001 epsilon band, live-read from process memory —
not 0.0, and DIFFERENT from the epsilon rounds 1-2 refuted (that was for the wrong function,
`target+0x5b0`)** (2026-08-30, 🔬 live memory read, same round) — the two float constants gating
FRONT/BACK/crossing classification (`Editor.dll` addrs `0x183761c`/`0x182293c` in this build)
read live as **exactly ±0.001** (f32-encoded). FRONT-whole requires `D1>-0.001 AND D2>-0.001`;
BACK-whole requires `D1<0.001 AND D2<0.001`; else crossing. This is the exact mechanism round 1's
original traced exemplar needed (a ray origin ~0.0002uu off a splitting plane spuriously classified
as a crossing under native's strict `>=0.0`) — the real function absorbs that into the epsilon band
instead. Crossing formula re-confirmed with corrected point roles: `t=D1/(D2-D1)`,
`mid=point2+t*(point2-point1)` — matches round 3's raw captured `t` and round 4's live `mid`
coordinates exactly (algebraically `t=-t'` of round 4's formula, an exact float negation, not an
approximation).

**Not yet resolved, no port shipped:** the `edi`/state-thread's full semantics and terminal-handling
polarity (traced live for 6 rays, all-blocked outcome only — never exercised the clear-return path),
plus a found-but-unreconciled CSG-mask asymmetry between whole-segment and far-continuation branches
(far-continuation doesn't strip `NF_BrightCorners` before testing, unlike every other site and the
existing `is_csg` helper). `linecheck.rs` untouched this round (`git diff` empty); no regression-gate
re-run needed (nothing that could regress changed). Full detail:
`dev/docs/board/inbox/line-clear-shadow-ray-algorithm-gap-found-real/overview.md`.

**Round 7 — the state machine (near-call incoming state, far-continuation state, terminal polarity)
was fully pinned and passed EVERY targeted live check, then a broad offline sweep against real
golden bits (not cherry-picked) revealed a severe, previously-invisible large-scale regression.
Root cause not found; a FRONT/BACK swap hypothesis was tested and ruled out as not a clean fix; most
likely cause is an entirely un-modeled zone-transform branch. Reverted cleanly, nothing shipped.**
(2026-08-30, 🔬 live + offline, `line-clear-shadow-ray-algorithm-gap-found-real` round 7) — Found a
live-verified transcription error in round 6's own D1/D2 register labels (`[ebp-0x8]` tracks the
query/lumel point, `[ebp-0xc]` the light — the reverse of round 6's original reading), fixed the
crossing formula and near-side test accordingly, and separately found the near-recursive call's own
incoming state is NOT the caller's `edi` passed through (a real gap round 6 missed) but a distinct
computation at `0x17ce306`-`0x17ce35e` — algebraically identical in shape to the far-continuation
formula, unifying into one `combine_state(side, state, csg)` helper. Verified via 122 live-captured
state transitions (0 mismatches) and 4/4 real rays replayed end-to-end with exact node-path
matching for 3/4. **Then**, a full offline sweep of 2,000,000 real shadow bits each on Wanchai/UNATCO
(`line_clear_v2_algorithm_check.py`, no live capture needed — golden's own tree is ground truth)
showed only 92.36%/88.81% agreement — well below the ~99% baseline the CURRENT, un-fixed code
already achieves — with every mismatch one-directional (`golden=blocked, algorithm=clear`, never
the reverse). A FRONT/BACK state-polarity swap experiment (a concrete, principled hypothesis, not a
parameter search) helped one problem light (81%→97%) but regressed another working one — ruled out
as the fix. Leading hypothesis tested same round and REFUTED: `0x17ce1d3`-`0x17ce213` gates every dot-product
computation on a constant-across-the-whole-call pointer (`edx`, loaded from `[ebp+0x10]`, built by
the top-level dispatcher via a virtual call on the LineCheck's own "this") — every port this round
always takes the "null" plain-dot path. New harness `linecheck_edx_zone_check.py`, surf-gated on a
small single-light UNATCO surface (`Light24`, `isurf=2810`, chosen offline to reach fast): live
capture shows **`edx=0x0` for all 4 sampled rays** (2 blocked, 2 clear) — identical to a working
light, ruling out a missing zone-transform as the cause for this specific broken case. Root cause
remains open; the recommended next step (not this round) is a live single-step of the SAME broken
ray (not more offline hand-tracing, which is what led this round away from the working live-capture
discipline that found round 7's two earlier real gaps). Reverted (`git checkout --
uedcli-native/src/linecheck.rs`, diff empty); `bin/test -k linecheck` 90/90; no regression-gate
re-run needed (nothing shipped). Full detail + concrete next steps:
`dev/docs/board/inbox/line-clear-shadow-ray-algorithm-gap-found-real/overview.md`.

**`rot_is_pure_rotation` missed pure mirrors, root-causing the severe-under-build family** (🔬,
`c7b8b0b`, SHIPPED) — a mirror (e.g. `MainScale=(-1,1,1)`) has orthonormal rows just like a real
rotation; only `det<0` distinguishes it. The length-only check let a mirrored Subtract brush's
§48 normal-recompute fire on already-correct, already-winding-reversed normals, inverting them —
`build_brush_temp_bsp` built that brush's own tree inside-out, so `filter_world_through_brush`
discarded unrelated world faces as "interior." Live-traced on Wanchai Garage's `Brush24`. Fixed with
a determinant check. Closes the severe under-build (-13% to -27% node deficits) on Area51-entrance,
Wanchai Garage, Paris Underground, NYC 747, OceanLab Lab — deltas now match the corpus's ordinary
over-build noise range. UNATCO/Wanchai Market unaffected, stay exact. Full detail:
`dev/docs/board/inbox/mirrored-brush-determinant-fix-closes-the/overview.md`.

**smuggler's `+4` surf residual (nodes/leaves EXACT) isolated to 4 `PF_Semisolid CSG_Add` brushes;
PASS-A (structural) tree confirmed BYTE-EXACT — a NEW, cleaner shape than freeclinic08/nsfhq04's,
mechanism NOT found (no fix shipped)** (2026-08-30, 🔬 offline + one attempted live descent trace,
inconclusive) — `breadth_gate.py` baseline: smuggler nodes 7007/7007 EXACT, surfs `d=+4`, leaves
`d=+0` (verts `-70`/points `+135`/vectors `+13`, not gated). Per-brush surf-count attribution
(`smuggler_surf_diff.py`, same method as `fc08_surf_diff.py`) finds **exactly 4 brushes**, each
`d=+1`: `Brush547`/`Brush550`/`Brush273`/`Brush457` (world-CSG idx 119/120/124/266) — all
`CsgOper=CSG_Add PolyFlags=32` (`PF_Semisolid`), all 128-poly composite props (texture
`CoreTexMetal.Heli_LiftMetl_A`, a "Heli Lift"-style stacked-panel object placed 4 times).

**Decisive new test, borrowing freeclinic08's own methodology (`smuggler_filter_trunk.py` +
`geo_golden_resume_structural.py`, both committed): smuggler's PASS-A (all 79 `PF_Semisolid`
brushes dropped, 660 of 739 actors kept) is nodes/surfs/leaves BYTE-EXACT against a freshly built
editor golden of the SAME filtered trunk** (native `2526/1378/614`, editor `2526/1378/614`, verts/
points/vectors within noise: `+65/+1/-1`). This is the opposite of freeclinic08 (PASS-A already
`-38 nodes/-23 leaves` before its own semisolid brush ran) — smuggler's `+4` surf delta is **entirely
a PASS-2 (semisolid) effect on an otherwise-exact tree**, not inherited from an already-wrong PASS-A
repartition gap. A cleaner, more tractable shape than freeclinic08/nsfhq04's diffuse residual, and a
DIFFERENT mechanism from UNATCO's fixed `repartition_frontier` gap (which was never about PASS-2).

**Per-brush poly attribution (`smuggler_brush_surf_detail.py`, matches native/editor surfs by
`i_brush_poly`):** 3 of 4 (`Brush547`/`Brush550`/`Brush273`) are a CLEAN single addition — native
keeps local poly index **124** (same index all three times) as an extra surf with NO editor
counterpart at all (not a swap); `Brush457` is a different shape — native keeps poly **99**, editor
instead keeps poly **16** (a genuine one-for-one SWAP between two non-coplanar, non-duplicate faces,
net `+1`). Poly 124 (all three matching brushes) is the BOTTOM-most stacked panel of the prop
(`Z` spans the brush's own `PrePivot.Z`, e.g. `Brush547`'s `PrePivot=(12,-40,-52)` and poly124 spans
`Z=[-52,-40]`) — suggestive of a coincident/boundary-adjacent face at the very bottom of a placed
prop (the classic `F_COSPATIAL_FACING_OUT` case `leaf_func`'s `LeafFunc::Add` arm gates OFF for
`PF_SEMISOLID` faces specifically, `bspcsg.rs:604-613`), but this is a HYPOTHESIS, not confirmed.

**Attempted to confirm via the existing `UEDCLI_BSPCSG_DESCENT=<i_link>` tracer — inconclusive, ruled
out as unreliable for this purpose.** `i_link` is a per-brush-CSG-call-LOCAL temp index (assigned
fresh inside `bsp_brush_csg` per brush, `bspcsg.rs` ~2382-2460), not a global/stable identifier, so
`UEDCLI_BSPCSG_DESCENT=124` fired 37 times across the WHOLE build (every brush with ≥125 polys hits
local index 124 once), none distinguishable as "the" `Brush547` call without brush-scoped
instrumentation this tracer doesn't have. None of the 37 captured lines showed the expected
near-zero-distance coincident-plane signature the hypothesis predicts, but this is NOT strong
evidence against it — the specific `Brush547` line was never confirmed to be among the 37. **Per
the standing rule (a fix must replicate the real, live-verified mechanism), no fix was attempted.**

**Not shipped, no source changes.** Only new committed harness scripts (`dev/docs/spikes/
2026-08-29-unatco-repart-live-diff/harness/`): `smuggler_surf_diff.py`, `smuggler_brush_surf_detail.py`,
`smuggler_filter_trunk.py`, `smuggler_native_structural.py`, `smuggler_structural_compare.py`,
`geo_golden_resume_structural.py` (+ its dependency `geo_golden_driver.py`, previously
`_scratch`-only). `bin/test`/`regression_gate.py` unaffected (no `.rs` edits this round). Full
write-up: `dev/docs/board/inbox/smuggler-4-surf-delta-traced-to-4-pf-semisolid/overview.md`.
**Concrete next step for a future round:** scope the descent tracer by enclosing brush actor name
(or isolate a single-brush repro: rebuild with ONLY `Brush547` as the sole `PF_Semisolid` addition
onto the already-exact PASS-A tree) before attempting another live/native differential on poly 124's
actual classification.

**Descent tracer fixed to scope by brush+poly (not `i_link`); `F_COSPATIAL_FACING_OUT`/`PF_SEMISOLID`
hypothesis for smuggler's `Brush547` REFUTED with unambiguous live evidence — the real terminal
classification is `F_COPLANAR_OUTSIDE`, unconditionally added, not the cospatial/semisolid-gated
path at all.** (2026-08-30, native-code trace) — `bspcsg.rs`'s `filter_ed_poly`/`leaf_func` DESCENT
tracer took `UEDCLI_BSPCSG_DESCENT=<i_link>` only; `i_link` at that point is a per-brush-call
speculative surf-slot number (`model.surfs.len()` at first-seen time, never incremented unless the
candidate actually commits via `bsp_add_node`), so it collides across unrelated brushes whenever an
earlier candidate got dropped — not a stable identity, confirmed the prior round's "37 lines, none
attributable" dead end. Fix: added `UEDCLI_BSPCSG_DESCENT_ACTOR=<world-csg actor idx>` and
`UEDCLI_BSPCSG_DESCENT_POLY=<i_brush_poly>`, both keying off `FPoly` fields that were ALREADY
present and already `empty_copy`-preserved across every split fragment (`fpoly.rs`) but never used
by the tracer: `actor` (set once per `bsp_brush_csg` call to the world-CSG brush index) and
`i_brush_poly` (the authored local poly index within that brush). Refactored the scope-matching
logic into a shared `descent_scope_matches(edpoly)` helper (any SET filter must match; at least one
must be set) used by both the existing descent-path trace and a new `LEAF` trace added inside
`leaf_func`'s `Add` arm (prints `filter`/`semisolid`/`add`, the actual leaf-classify verdict the old
tracer never exposed at all).

Ran the whole smuggler build with `UEDCLI_BSPCSG_DESCENT_ACTOR=119 UEDCLI_BSPCSG_DESCENT_POLY=124`
(`Brush547`'s world-csg index / local poly index, from the prior round's own attribution table):
**every captured line carries `actor=119 i_brush_poly=124`** — fully unambiguous, unlike the old
`i_link`-keyed attempt. Result: 3 `LEAF` lines, all `filter=2 semisolid=true add=true` — `filter=2`
is `F_COPLANAR_OUTSIDE`, not either cospatial value (`F_COSPATIAL_FACING_OUT=5`/
`F_COSPATIAL_FACING_IN=4` in this file's own constants). `leaf_func`'s `Add` arm adds `F_OUTSIDE`/
`F_COPLANAR_OUTSIDE` UNCONDITIONALLY (no semisolid gate) — and the disassembly-decoded real editor
`AddFunc` (`Editor.dll 0x31770`, `sections/10-bsp-csg-build.md` §4.3, 📖 byte-verified) does the
identical thing: `if Filter == F_OUTSIDE(0) or F_COPLANAR_OUTSIDE(2): bspAddNode(...)` unconditional,
no semisolid test — the semisolid gate in the real editor applies only to the OTHER cospatial branch
(`elif Filter == <cospatial, raw value 5> and not semisolid`). **So the originally-suspected
mechanism does not apply here at all: this poly never reaches the semisolid-gated branch on either
side, native and the confirmed real editor treat `F_COPLANAR_OUTSIDE` identically, and the gate
itself is not the bug.**

Note in passing, not acted on: this file's own `F_COSPATIAL_FACING_OUT=5`/`F_COSPATIAL_FACING_IN=4`
are the reverse of `sections/10-bsp-csg-build.md`'s disassembly-derived `F_COSPATIAL_FACING_OUT=4`/
`F_COSPATIAL_FACING_IN=5`. Not a functional bug — the semisolid gate in `leaf_func` keys off
whichever constant equals raw value 5, matching the real `AddFunc`'s own gate on raw value 5 — but a
naming mismatch worth resolving before anyone reasons about "in vs out" here again; left alone since
renaming risks touching unrelated call sites for zero behavior change and was out of this round's
scope.

**New characterization, not previously known:** the full (unscoped-by-poly) descent trace for this
poly shows it reaching a genuine `COPLANAR dot=-1.00000` hit partway down (native node 2706, `csg=0`
— i.e. NOT a node from the already-confirmed-exact PASS-A structural tree, but one of `Brush547`'s
OWN earlier-added faces from earlier in this SAME `bsp_brush_csg` call). This contradicts the
original hypothesis's framing ("resting on structural floor geometry") — the coincidence is INTERNAL
to the brush's own reconstructed geometry (two touching faces of the same stacked-panel composite
prop, exactly opposite-facing), not against the world. Whether native's classification of this
self-coincidence genuinely diverges from the real editor's (a bug in the coplanar-facing test or in
reaching a different node than the real editor does), or whether real semisolid/PASS-2 CSG uses some
mechanism beyond the shared `AddFunc`/`leaf_func` that native's Pass 2 (which calls the same
`bsp_brush_csg` as Pass 1, `bspcsg.rs` ~2953-2960) doesn't model, is **not determined this round** —
would need either a live editor-side capture of this exact poly's real classification or a
single-brush isolated repro, neither attempted (per the standing rule: no fix without a confirmed
real mechanism, and per spike judgment: this reframes rather than closes the question, logged rather
than chased further).

**No `bspcsg.rs` semantic changes** — both new/changed blocks are env-gated diagnostics only
(`descent_scope_matches`, the new `LEAF` trace), zero effect on any default-path build. Verified:
full `bin/test` 12517 passed/0 failed (pytest) + 90/90 (cargo test), both before and after;
`regression_gate.py` UNATCO/Wanchai both EXACT, `GATE: PASS`; `breadth_gate.py` unaffected (numbers
unchanged from the pre-existing corpus measurement — read-only tracer addition, no build-path code
touched).

**Why the `repartition_frontier` fix (`bcc3693`) didn't touch freeclinic08/nsfhq04: DIFFERENT call
site, not the same bug — disproves the board item's "same class as UNATCO" framing.** (2026-08-30,
offline `UEDCLI_BSPCSG_STAGE_COUNTS` measurement, no docker/gdb — no source changes) — freeclinic08's
structural-only set (141 non-semisolid brushes, `_scratch/fc08-structural-only/`, pre-existing golden)
re-measured post-fix: nodes/leaves still `-38/-23` (surfs `+0`), byte-identical to the board item's
own pre-fix number. Stage-by-stage (`UEDCLI_BSPCSG_STAGE_COUNTS`): node count is **already** 1141 (vs
golden 1179) at `post-repartition` — the ONE-TIME world-level `bsp_build_fpolys`→
`bsp_merge_coplanars`→`bsp_build` reconstruction — and stays byte-frozen at 1141 through
`post-testvisibility`/`post-pass2`(empty here)/`post-repartition-frontier`/`post-finalize`/
`post-optgeom`. `repartition_frontier` is directly confirmed a no-op (1141→1141, and separately on the
FULL freeclinic08 build with real Pass-2 growth: `post-pass2` 2492 → `post-repartition-frontier` 2492
unchanged; nsfhq04 same, 7564→7564) — exactly as `bcc3693` designed it, but that means the fix had
**nothing to touch** for these two levels: their deficit is entirely upstream, at the WORLD-LEVEL
`bsp_build` call, a different code path UNATCO's own residual never implicated (UNATCO's world-level
stage is independently confirmed EXACT: native 2953 nodes == the live-gdb-captured editor STAGEEND
value, `emptymodel_worldlevel_trace.py`, already on record). Per-brush node-plane-owner attribution on
the isolated world-level result (`fc08_node_owner_diff.py`-style) shows the same diffuse,
heavy-cancellation shape as the original (now-superseded) full-build finding: 37/141 structural
brushes (26%) differ, summing to 102 absolute vs a net −38 — consistent with a `FindBestSplit`
tie-break/poly-order sensitivity, but firing at the world-level one-shot reconstruction (whole-level
merged soup, one call) rather than `repartition_frontier`'s 209/119 per-subtree calls. nsfhq04 only
gets the weaker half of this check (repartition_frontier confirmed no-op there too, but its
`zone_pass` DOES move node count, 4933→4975, so world-level-vs-zone-pass isn't isolated the way
freeclinic08's zero-semisolid test isolates it). **No fix — root cause of the world-level `bsp_build`
divergence itself (why `FindBestSplit` lands on a different tree for these specific brush sets) is
unresolved**; closing it needs a live gdb capture of the editor's real world-level poly order for a
~141-poly merged soup (`fbs_root_poly_order.py`-style, scaled up from UNATCO's single-subtree
capture), not attempted this round. `regression_gate.py`: UNATCO/Wanchai unchanged, `GATE: PASS` (no
source edits). See `freeclinic08-nsfhq04-1-surf-under-build-root` for the full per-stage numbers.

**The world-level `bsp_build` divergence, ROOT-CAUSED: a genuine poly-list ORDER mismatch between
native's and the real editor's `bspBuildFPolys`/merge reconstruction — NOT a scoring/tie-break bug.
`find_best_split_exact`'s stride formula is exonerated a second time (world-level call, not just the
earlier subtree case).** (2026-08-30, 🔬 live, new harness `fbs_world_poly_order.py`) — Did the live
capture flagged as the concrete next step above, scaled to the WORLD-level call instead of a subtree
(`fbs_root_poly_order.py`'s own mechanism: breakpoint `FindBestSplit` entry `0x100338EE`, gated to the
first hit after the FIRST `bspRepartition` entry `0x10049fc0` — `callidx==1`, the same world-level
gate `emptymodel_worldlevel_trace.py` already live-verified). Target: freeclinic08's structural-only
141-brush golden (`_scratch/fc08-structural-only/golden_structural.dx`, the pre-existing isolate with
0 surf delta / −38 node delta).

Captured **1019** `FBSPOLY` entries — exactly matching native's own `UEDCLI_REPART_FBS_DUMP`/
`UEDCLI_BSPCSG_SOUP_ORDER` count for the identical brush set (`numpolys=1019` at native's own
world-level `split_poly_list` call, confirmed via a fresh offline run of those pre-existing
diagnostics) — so the MERGED POLY SET is the same size both sides; the divergence is not a
missing/extra poly. `Opt::Good`'s stride for 1019 polys is `inc=1019/20=50`, so both sides' search
only ever SAMPLES the poly at each 50-wide window's first eligible index (0,50,100,…,1000 — the
window-start when all local flags are plain, which holds here: none of the checked entries carry the
`0x28` semisolid/notsolid mask, this being the structural-only set by construction). The real editor's
`node[0]` (read straight from the golden `.dx`, no live capture needed for this half) is
`plane=(0,−1,0,896)`. In the LIVE-CAPTURED real editor order, the poly bearing that EXACT plane sits
at **k=700** — itself one of the 21 sampled window-start indices (`700 = 14×50`) — an exact,
bit-identical plane match at a genuinely-sampled slot, which is definitive: the real `FindBestSplit`
can only return a plane it actually evaluated, and this is the only `k=700`-adjacent candidate whose
plane matches the built model's real answer. In NATIVE's own reconstruction (`UEDCLI_BSPCSG_SOUP_ORDER`
on the same brush set), the SAME identifiable poly (matched by exact plane AND `i_link`, which numbers
consistently across both captures — confirmed on multiple polys, not just this one) sits at **k=672**
— inside window `[650,700)`, NEVER sampled (native's own candidate for that window is index 650
itself, a wholly different, unrelated poly/plane, matching `UEDCLI_REPART_FBS_DUMP`'s own
`REPART_CAND id=0 slot=650` row). Native's own world-level winner (`best_i=600`, `score=24.0`, plane
`(1,0,0,576)`) is real and lowest-scoring **among the 21 candidates its own order exposes it to** —
the algorithm is not malfunctioning, it is scoring the wrong candidate SET because the input order
differs. A second poly (`i_link=57`, the other end of the same corridor) shows the same shape at
different magnitude: editor real order `k=468`, native order `k=124` — a 344-position shift, vs the
first poly's 28-position shift, ruling out a simple constant/linear reindex (e.g. a reversed list or
an off-by-N rotation) — this is a genuine STRUCTURAL reordering, consistent with a different recursive
tree-walk order, not a uniform permutation.

**This exonerates `find_best_split_exact`'s windowed-stride candidate selection a second time** (the
first was UNATCO's `child=6108`, disassembly-verified faithful to the real editor's own coarse
sampling) — for THIS call site too, the formula is correct; feeding it the editor's own real order
would very likely reproduce the editor's real choice (the winning plane match at a genuinely-sampled
index is about as strong a proof as available without also capturing full per-poly vertex arrays to
re-run the exact score). This is also a DIFFERENT finding than "the ordering hypothesis was wrong"
for UNATCO's `repartition_frontier` subtree calls (`child=6108`, earlier entry) — that refutation
was about a call whose entire reconstruction gets DISCARDED by `bspRefresh`'s node-array `Remove`
(the pre-existing subtree survives instead), which does NOT apply here: the world-level call is
confirmed to commit directly to the persistent Model (`emptymodel_worldlevel_trace.py`,
`this_eq_m=1`), so there is no discard-and-keep-the-old-tree escape hatch available at this call site
— the poly-list order genuinely is what determines the real, final, persisted tree shape here.

**NOT further root-caused, and NO FIX SHIPPED, per the standing rule.** WHY native's poly-list order
diverges from the editor's real order — whether it traces to a difference already present in Pass 1's
incrementally-built world tree (before this call even runs), to `bsp_merge_coplanars`'s own grouping/
walk order, or to something else — is not determined this round; establishing it would need at least
one more live capture (the editor's real PRE-world-level-repartition incremental tree order, the
`prepart_tree_unatco.py`/`prepart_tree_wanchai.py` technique already proven for subtree calls, not yet
applied at world level) and is comparable in scope to the rest of this investigation. Per the standing
rule ("if the real algorithm isn't confidently known, log the gap as unresolved rather than shipping
an approximation"), no reordering fix was attempted — a plausible-looking reorder (e.g. sort by some
proxy key) would be exactly the forbidden tolerance-fudge, chosen because it might measure better, not
because the real mechanism is known. Diminishing-returns judgment call per the task's own budget
guidance: this round's goal (confirm or refute the poly-order hypothesis for the world-level call) is
now answered with high confidence; the deeper "why" is named as the concrete next step, not chased
further here. No `bspcsg.rs` changes — read-only live capture (new harness script, committed) plus
reuse of pre-existing env-gated diagnostics (`UEDCLI_REPART_FBS_DUMP`, `UEDCLI_BSPCSG_SOUP_ORDER`,
already committed). `regression_gate.py` not re-run (no source edits to re-verify against); the
committed harness addition is inert on the default build path. New file:
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/fbs_world_poly_order.py`, log at
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/fbs-world-poly-order-fc08struct.log`.

**Poly-list order divergence localized one stage further: it is already present coming OUT of
Pass 1, before `bspBuildFPolys`/`bspMergeCoplanars`/`bspBuild` ever run — both later steps are now
exonerated for freeclinic08's world-level call.** (2026-08-30, 🔬 live, no fix shipped) — New live
capture (`fpolys_stage_order.py`) breaks at the two return addresses inside `bspRepartition`
(`Editor.dll 0x1004a00d` post-`bspBuildFPolys`, `0x1004a027` post-`bspMergeCoplanars`) and dumps the
CTX object's `Polys` array (`UPolys*` at `CTX+0x54`) at each. **Corrects an earlier, never-live-
tested ledger entry's `[[CTX+0x54]+0x2c]`=Data guess, which was off by 4 bytes** — live dword-probe
(`ctx_polys_struct_probe.py`/`_probe2.py`) found `+0x2c`/`+0x30` hold a valid `(Count,Max)` pair
(`1333,1449`), not a pointer; the real layout is `Data=+0x28, Count=+0x2c, Max=+0x30` (confirmed:
dereferencing `+0x28` as `FPoly*` gives a sane unit normal `(0,0,1)`, `nv=4`). Validated in-band
too: the POSTMERGE dump's order is index-for-index IDENTICAL to the already-committed
`fbs_world_poly_order.py` FindBestSplit-entry capture for the same golden (`i_link=57` at `k=468`
both ways, 3/3 spot-checked positions match) — proof `bspBuild` does not reorder between merge
output and `FindBestSplit`'s own input, and that the corrected offsets are right.

Compared against native's own equivalent stage dumps (`UEDCLI_BSPCSG_PREMERGE_DUMP=ALL` — extended
this round from a name-filtered subset to a full-list dump — and the pre-existing
`UEDCLI_BSPCSG_SOUP_ORDER`) on the identical freeclinic08 structural-only golden:

| stage | editor (live) | native | order match |
|---|---|---|---|
| PREMERGE (post-`bspBuildFPolys`) | 1333 polys | 1263 polys | first divergence at k=2; COUNTS differ |
| POSTMERGE (post-`bspMergeCoplanars`) | 1019 polys | 1019 polys | same i_link multiset, same k=2 divergence pattern |

The PREMERGE stage already shows a real COUNT mismatch (1333 vs 1263, not just reordering) — the
real editor's Pass-1 incremental tree carries ~70 more raw poly-fragments for this brush set than
native's own Pass-1 tree, even though both converge to the identical 1019-face POSTMERGE set (and,
per this item's earlier structural-only measurement, the identical final 680-surf set). Since
`bspMergeCoplanars`'s grouping/walk order is confirmed elsewhere in this ledger to correctly and
faithfully reduce whatever fragment soup it's given (child=6108's 40→29 merge, exact plane match),
and `bspBuildFPolys`/`make_ed_polys` is a simple, uncontroversial DFS tree-walk on both sides, the
POSTMERGE-stage divergence is not something either of those two steps INTRODUCES — it is inherited
from a genuine tree-SHAPE difference already present in Pass 1's own incrementally-built world tree,
before `bspBuildFPolys` ever runs. This is new localization, one stage further upstream than any
prior entry in this chain reached.

**`line_clear` round 7's "regression" was a measurement artifact, not a real v2 bug — the threaded-
state port is 262/262 (100%) correct on every real Wanchai native-vs-golden mismatch vs v1's 20/262
(7.6%), shipped** (2026-08-31, 🔬 live + offline oracle) — Round 7's v2 checker calls `line_clear`
directly with no light-radius cull, over ALL lumels, then compared against a 99% baseline from a real
compiled run that DOES cull by radius first. Confirmed: round 7's own first-listed mismatch
(`rec=3 Light391 v=34 u=20`) is 677uu from a light with 425uu world radius — genuinely out of range,
unrelated to `line_clear`. Restricted to the real (native.dx≠golden.dx) mismatch bucket, in-range
only, whole Wanchai level (198 records, 262 lumels, not cherry-picked): v1 20/262 correct, v2 262/262
— zero regressions. `uedcli-native/src/linecheck.rs` now ships the threaded `combine_state`/
`terminal`/`seg_clear` port. Wanchai byte-identical 3408/4530→3418/4530; `regression_gate.py` exact
before/after. Full round-by-round detail: `line-clear-shadow-ray-algorithm-gap-found-real`.

**`a_not_vis_blocking_node_does_not_occlude` conflicted with the verified-correct `line_clear`
threaded-state port — resolved per owner ruling (2026-08-31): rewrite the test, ship the fix.**
The old construction flagged EVERY node `NF_NotVisBlocking` (unrealistic: no real level does this)
and expected CLEAR. The real algorithm's `state` starts `false`/unproven and only a genuine
CSG-solid FRONT crossing sets it `true`; an all-non-CSG tree never earns that, so the terminal
reports BLOCKED. Rewrote the test to a realistic partial-flagging construction matching the real
UNATCO ratio (a solid ancestor node the ray crosses first, establishing `state=true`, then the
flagged node under test) — both the baseline-solid and flagged cases now pass under v2, and the
test still pins the same real-measurement motivation (54157→3902 dark lumels). `cargo test`: 91/91.
Full `bin/test`: independently re-verified clean. `line_clear` v2 SHIPPED.

**Not further root-caused.** WHY editor's real Pass-1 tree ends up with ~70 more fragments for the
same face set — a different CSG split/classification order across the 141 structural brushes, or a
genuine algorithmic gap in native's `bsp_brush_csg`/`filter_ed_poly` not caught by the existing
33/33 disassembly-verified check-set — is not determined this round; would need a live per-brush
Pass-1 tree-shape trace (the `prepart_tree_*` technique, not yet run at world level for
freeclinic08) to attribute the +70 delta to specific brushes/split decisions. Per the standing rule,
no reordering/fudge fix attempted. Diminishing-returns judgment call: this is the 3rd consecutive
round on this thread; the specific question posed (which of the three steps introduces the
divergence) is now answered with high confidence (none of the three — it's upstream of all of them)
and logged as the next round's starting point rather than chased further here. `bspcsg.rs` change:
one additive `ALL` mode on the pre-existing `UEDCLI_BSPCSG_PREMERGE_DUMP` env-gated diagnostic (was
name-filtered only); zero effect on the default path (`bin/test -k bspcsg` 90/90,
`regression_gate.py` UNATCO/Wanchai both EXACT, `GATE: PASS`, before and after). New files:
`fpolys_stage_order.py`, `ctx_polys_struct_probe.py`, `ctx_polys_struct_probe2.py` (all
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`); log at
`.../logs/fpolys-stage-order-fc08struct.log`.

**`line_clear` round 8's fix re-measured on UNATCO (round 9): real, positive improvement, no
source changes.** (2026-08-31, offline measurement, `light_spotcheck_unatco.py` against the
existing self-built `_scratch/native-visgate-2026-08-29/golden_unatco_lit.dx`) — round 8 shipped
the threaded-state `line_clear` port (commit `9827f07`) verified on Wanchai only; UNATCO was never
re-measured. `LightMap` records byte-identical: **2692/3345 (80.5%, pre-round-8 baseline) →
2797/3345 (83.6%)**, +105 records. Shadow-bit agreement (grid+run-matched): 99.27%. Consistent with
Wanchai's own improvement (3408/4530→3418/4530), no regression signal. No `uedcli-native/` source
changes this round — pure re-measurement.

**Completed round 8's other named next step (full-level radius-aware shadow-bit sweep on Wanchai)
— net improvement confirmed, but NOT a strict win: 203 genuine regression candidates found.**
(2026-08-31, offline, `broad_shadow_sweep.py`, whole level exhausted — 922,706 in-range bits, not
truncated) — v1 (old) vs golden: 922426/922706 (99.9697%); v2 (round 8's port) vs golden:
922503/922706 (99.9780%) — a real net gain (+77 bits), consistent with round 8's narrower
262-lumel sample and the record-level improvement. BUT: of the 922,706 bits, 280 are
`v1-wrong/v2-correct` (the expected fix) while **203 are `v1-correct/v2-wrong`** — genuine cases
where the OLD code happened to match the real editor and the new threaded-state port does not.
Round 8's "zero regressions" claim was based on the narrower real-mismatch bucket (262 lumels) and
did not generalize to the full level. A partial sample of the 203 (4 of 20 printed disagreement
examples) clusters at one location — record 977, `Light189`, adjacent lumels `v∈{0,1} u∈{10,11}` —
suggesting a localized geometric feature, not scattered noise, but NOT characterized further this
round. Per the standing rule, this is logged as an open residual on an already-shipped fix, not
silently patched — `line_clear` v2 stays shipped (net positive, matches or beats v1 on every
already-measured aggregate), but is not the final word. Needs a dedicated round: dump the full
203-case list (the harness only prints first 20), live-trace the record-977 cluster specifically.

**CORRECTION to the paragraph immediately above (2026-08-31, same day, independent parallel run of
the identical `broad_shadow_sweep.py`, 735,272-bit prefix of the same sweep — numbers agree exactly
where they overlap: 203 regressions both runs).** The `record 977, Light189` cluster named above as
"4 of the 203" is misattributed — those 4 lumels are `golden=BLOCKED(0), v1=CLEAR(1)=wrong,
v2=BLOCKED(0)=correct`, i.e. **v2 fixes them** (part of the 280-fixed bucket), not regressions. The
real `record=977` regression pair (v1-correct/v2-wrong) is `Light92` at `v=0 u=0` and `v=0 u=1`
(`golden=BLOCKED(0), v1=BLOCKED(0)=correct, v2=CLEAR(1)=wrong`) — only 2 of the 203, not 4, and a
different light. A future round chasing this cluster should live-trace `record=977`/`Light92`, not
`Light189`.

**Round 10: the whole 203-case population traced to ONE mechanism, then shown to be a
`broad_shadow_sweep.py` measurement artifact, not a real `line_clear` v2 regression — v2 stays
shipped, no source change.** (2026-08-31, offline + 🔬 live, `--dump-v1-only` extension to
`broad_shadow_sweep.py` + `linecheck_nearstate_recheck.py`) — Dumped the full 203-case list (not
just the 20 printed): **all 203 are ONE light (`Light92`), all 11 distinct surfaces are
`PF_BrightCorners`-flagged, and every single case diverges at the SAME BSP node, 5394** (a
crossing where near-side resolves via a nested recursion to `state=1`, then the far side hits a
bare terminal, `i_front=-1`). Node 5394's `node_flags=0x10` (`NF_BrightCorners` only) in
`golden.dx`'s saved model makes `is_csg`'s unstripped (near/far) mask read it as non-CSG, letting
the already-proven-open `state` leak through a terminal that should be genuinely solid.

**Live-verified this is not what the real editor's shadow-ray walker actually sees.**
`linecheck_nearstate_recheck.py` (new, surf-gated on `isurf=1979`, the cheapest of the 11 targets —
record 2296, `Light92`, `v=0 u=0`, ray 25) captured node 5394's REAL `NodeFlags` byte live, at the
exact moment the real walker classifies it during `LIGHT APPLY`: **`0x00`, not `0x10`** — matching
9/9 other path nodes exactly (only node 5394 differs from the golden-saved snapshot). `NF_BrightCorners`
on this node is evidently set LATER in the same `LIGHT APPLY` run (its own owning surface, processed
after record 2296's, presumably stamps it) — golden.dx's saved model reflects END-OF-BAKE state, not
the state the walker saw at THIS ray's cast time. (Also caught and discarded a real bug in the
pre-existing `linecheck_walker_state_trace.py`'s own `RECURSE_CALL state_out` field — its
`$esp+0xc` offset does not land on the pushed state value once the mid-vector struct setup between
`0x17ce364` and `0x17ce3b4` is hand-counted; a new direct-register breakpoint at `0x17ce35e`
supersedes it for state reads. `NEARSTATE_EAX` there confirmed `eax=1`, matching the ALREADY-SHIPPED
near-state formula exactly — that formula was never wrong.)

**The decisive check: native's OWN model never sets `NF_BrightCorners` on ANY node — `derive_nf`
(`build.rs`/`bspcsg.rs`) has no case for `PF_BrightCorners`, so every node's flags in native's real
pipeline lack bit `0x10` unconditionally, matching the real editor's AT-CAST-TIME state for exactly
this population.** Re-ran v1 and v2 against a fresh native-built Wanchai tree's OWN node flags
(`light-spotcheck-wanchai-native.dx`, current tree, no source changes) for all 203 cases (positions
recomputed via native's own `row_origins`, not copied from golden): **203/203 agree (both blocked,
matching golden)** — v2 does NOT reproduce the golden-tree regression when run against what native
actually builds. `broad_shadow_sweep.py` (and, by extension, round 7-9's whole "test the port
against golden.dx's saved tree" methodology) is valid for static node properties but wrong for
`NF_BrightCorners` specifically, since golden.dx's copy reflects a value the flag only reaches AFTER
the tested ray's own cast time.

**No fix shipped — none is needed for this population, and none is safe to attempt speculatively.**
Adding a `PF_BrightCorners → NF_BrightCorners` case to `derive_nf` (which WOULD close native's
node_flags gap against golden.dx byte-for-byte) is explicitly NOT done here: native builds its whole
model before lighting runs, so a naive static set would apply the flag to EVERY node from the start
of the bake, not incrementally per-surface like the real editor evidently does — which is exactly the
mechanism that would turn this dormant 203-case population into a REAL regression. The real
per-surface timing/ordering rule that governs when the editor sets this bit during `LIGHT APPLY` is
undecoded; per the standing rule, logged as an open, separate question rather than guessed at.
`git diff -- uedcli-native/src/` is empty this round. New spike files:
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_nearstate_recheck.py`,
`.../logs/linecheck-nearstate-recheck.log`; `broad_shadow_sweep.py` gained a `--dump-v1-only PATH`
flag (unlimited dump, not capped at 20).

**New infrastructure, not a finding: canonical single-entry-point parity report tool, shipped**
(2026-08-31) — `dev/docs/spikes/2026-08-31-native-parity-report/harness/parity_report.py
<path/to/OG-level.dx> [--json]`: one script, geometry (nodes/surfs/leaves/verts/points/vectors,
exact counts) AND lighting (`LightMap` byte-identical record count/percentage + grid+run-matched
shadow-bit agreement) together, top-line `FULL PARITY: YES/NO` (YES only if EVERY geometry count
and EVERY `LightMap` record is byte-identical — stricter than `breadth_gate.py`'s node/surf/leaf-only
"EXACT"). Content-hashes the input `.dx`, caches the self-built golden under
`/tmp/uedcli-parity-cache/<hash>/` (golden+meta only; the extracted trunk lives under
`_scratch/uedcli-parity-cache/<hash>/trunk/` instead — `/tmp` breaks the ephemeral build
container's ini bind-mount under a sandboxed shell, see `dev/docs/parallel-editors.md`). Never
`MAP LOAD`s the original — reuses `ingest_dx_trunk.py` (extraction) + `build_ued_lit_golden.py`
(`MAP NEW`→`EDIT PASTE`→`MAP REBUILD`→`LIGHT APPLY`→`MAP SAVE`) as subprocesses, plus one new
post-extraction step (`classindex.ClassIndex.qualify_and_validate`, the same mechanism
`uedcli/cli/ingest.py`'s real ingest gate uses) since `ingest_dx_trunk.py`'s own output can leave a
class BARE (e.g. `LevelInfo`), which `gather_lights`/`ClassDefaults` reject. Live-verified: `DX.dx`
(trivial, FULL PARITY: YES, 26/26 LightMap records + 1536/1536 shadow bits), a fresh cache-miss run
vs a cache-hit re-run (1.5s), and both UNATCO and Wanchai reproduce this ledger's own most recent
figures exactly (below) — independently re-confirmed by the coordinating session too (cache-hit
re-run 34s, byte-identical numbers). 28 offline unit tests (pure cache/compare/verdict logic, no
docker) under the same `harness/` dir; not part of `bin/test` (lives under `dev/docs/`, not
`uedcli/`).

**Found while live-testing the new tool: the "UNATCO" baseline this whole ledger cites is actually
`03_NYC_UNATCOHQ.dx`, not `01_NYC_UNATCOHQ.dx`** (2026-08-31, 🔬 confirmed by raw byte search) — DX
ships UNATCO HQ as several per-mission `.dx` snapshots (`01_`/`03_`/`04_`/`05_NYC_UNATCOHQ.dx`).
`01_NYC_UNATCOHQ.dx` contains `AlexJacobson`, lacks `AllianceTrigger`; `03_NYC_UNATCOHQ.dx` contains
`AllianceTrigger`, lacks `AlexJacobson` — matching the historical `_scratch/bsp-parity-proj/maps/unatco`
trunk's own actor names exactly (has `AllianceTrigger0/1/2`, lacks `AlexJacobson0`). Running the new
tool against `03_NYC_UNATCOHQ.dx` reproduces every figure this ledger has reported for "UNATCO" bit
for bit: nodes/surfs/leaves EXACT (6314/3616/762), verts d=+5, points d=+16, vectors d=+0, lighting
2797/3345 (83.6%) byte-identical, shadow bits 3729140/3756584 (99.27%). Against the LITERAL
`01_NYC_UNATCOHQ.dx` (a real, different actor/geometry snapshot: 1470 actors vs 1437, 721 raw
`Class=Brush` actors vs 734) geometry is NOT node-exact (d_nodes=+350, d_surfs=+3, d_leaves=+39).
Owner ruling 2026-08-31: rename references to `03_NYC_UNATCOHQ.dx` (done, this ledger's own
mentions were already bare "UNATCO" and needed no change; 9 board/spike/direction docs corrected —
see `unatco-baseline-trunk-is-actually-03-nyc`), keep it as the real target, no re-verification
needed.

**Also found: `build_ued_lit_golden.py`'s Wanchai self-build (`06_HongKong_WanChai_Market.dx`,
1303-brush trunk) crashed UnrealEd 3/3 tries in this session's environment**, always at the level's
first `EDIT PASTE` right after `MAP NEW` (`error: UnrealEd has crashed — a 'Critical Error' dialog is
open`), before any `MAP REBUILD`/`LIGHT APPLY` step. Host resources were not the cause (18G free,
load 1.3-1.6/14 cores, no orphaned containers). NOT a regression in the harness itself — the same
trunk previously built successfully (`_scratch/wanchai-relight-2026-08-29/golden.dx`, provenance
already confirmed above, still the basis for this ledger's `line_clear` Wanchai figures) — cause
undetermined (possibly environment/load-specific to this session's ~11 concurrent worktrees). Worked
around (not root-caused) by seeding that pre-existing confirmed golden into the new tool's cache
while using the tool's own fresh trunk extraction: geometry/lighting matched the ledger exactly
(nodes/surfs/leaves EXACT 11648/5284/3371, verts +74, points +16, vectors −8, lighting 3418/4530
(75.5%), shadow bits 98.79%). Filed as `board/inbox/wanchai-self-build-edit-paste-crash`.
