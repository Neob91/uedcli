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

**Re-emphasised (owner, 2026-09-01):** every fix must be confirmed against UnrealEd's real behavior
before shipping — the algorithm must be functionally identical, not just numerically closer. Model
instance: the OceanLab Lab `bsp_validate_brush_links` fix (search "OceanLab Lab +27 surf
over-build") was live-verified against a real UED22 build (an isolated context golden) before
shipping — native's predicted surf-group count matched the live editor's exactly, not just measured
to reduce the delta.

**Standing directives (owner, 2026-09-01):**
- Work fully autonomously — do not stop to ask; investigate and act (fix + ship when confidently
  live-verified, per the rule above). Escalate only a genuinely irreversible action or a reversal of
  an explicit prior owner ruling.
- Report parity status every time it changes — not just on request.
- Sweep the worst-parity levels one at a time: after each fix lands, re-rank the corpus and
  investigate whichever level is worst next. Current worst-first queue and results:
  `native-light-apply-bake-where-it-stands-and`.
- Faithfully reproduce a real, live-verified editor effect even when the level authoring that
  triggers it looks like a mistake (e.g. `vandenberg-gas-csg-active-csgoper-brush-causes`'s
  `CsgOper`-absent brush) — never silently "correct" the data to what was presumably intended.
  Comment the code and file a board note flagging it as likely-unintentional authoring, so the
  behavior can be revisited later, but the shipped behavior still matches what UnrealEd actually
  does with it.

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

**Round 11 (auditing round 8's 262/262 evidence for the same golden-tree-timing artifact round 10
found): INCONCLUSIVE, concluded without a finding after repeated stalls.** (2026-08-31) — the task
was to check whether round 8's decisive "262/262 real Wanchai mismatches fixed by v2" ship evidence
has the same `NF_BrightCorners` golden-tree-timing artifact round 10 found in the 203-case
regression bucket (round 10 found the artifact only in one direction; round 11's job was to check
the other). The dispatched agent built real, well-designed tooling —
`round11_fixbucket_brightcorners_audit.py` (an OFFLINE check, no live capture needed: re-walks each
candidate fix through golden's tree with `NF_BrightCorners` force-cleared on every node, round 10's
own live-confirmed proxy for "what the real editor's walker saw at cast time") and
`round11_decisive_node_order.py` (a record-index-order heuristic for the same question) — but never
actually ran either past the fixbucket-generation step. It ran two live gdb captures instead
(`round11_node_flags_at_cast.py`): the first completed cleanly (`TARGET_DONE hits=0`, a negative
result for that specific probe) but the agent stalled ~1hr afterward without analyzing it; after a
nudge, a second capture (`--rays 20000`) hung/terminated without producing output at all
(log ends at `ORACLE_ATTACHED`, no `SURF_ENTER`/`TARGET_DONE`). No `FIXBUCKET.jsonl` was ever
generated by any run. Concluded by the coordinating session after two nudges and ~30min final
idle with no active process, per the standing no-third-nudge discipline.

**This does NOT mean round 8's 262/262 evidence is wrong** — it means that evidence was never
re-verified against the timing-artifact-free methodology round 10 established. It is a real,
still-open question, not a refutation. The fastest path for a future round: the offline
`round11_fixbucket_brightcorners_audit.py` script is ready and does not need docker/gdb at all —
it only needs round 8's original 262-case fix list regenerated as a `FIXBUCKET.jsonl` (the exact
input the script's own usage line documents) and pointed at Wanchai's confirmed golden. New harness
files (uncommitted work, not lost — round 11's coordinating-session cleanup committed them):
`round11_node_flags_at_cast.py`, `round11_fixbucket_brightcorners_audit.py`,
`round11_decisive_node_order.py` (all `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`).

## Breadth golden-caching pass across the 21-level corpus (2026-08-31)

Owner ask: pre-build and cache a self-built golden for every one of the 21 OG-retail breadth-corpus
levels, so a future `parity_report.py` run against any of them is a cache hit, not a fresh editor
build. Ran from an isolated worktree (own `.venv` + freshly-built `uedcli_native`).

**Docker mount-permission blocker, root-caused, worked around, not fixed** — filed as
`board/inbox/docker-mount-source-permission-fails-from-main`. From the main checkout, every
editor-driving command fails with `mkdir /workspace/umodel_win32: permission denied`.
`tool_assets.umodel_dir()` is package-relative (`tool_root().parent / "umodel_win32"`), deliberately
a SIBLING of the tool dir. From the main checkout this resolves to `/workspace/umodel_win32` — a
symlink to `dev/games/.cache/umodel-src` — and the rootless docker daemon (a different OS user than
`agent`) fails to `mkdir` a bind-mount source there (`/workspace` is `agent`-owned, mode 0755, no
group/other write; the daemon doesn't accept the existing symlink as satisfying its
mount-source-exists check). From a worktree, `tool_root()` is the worktree dir, so `umodel_dir()`
resolves instead to `.claude/worktrees/umodel_win32` — a real, already-populated directory an earlier
worktree session created — so the daemon never needs to `mkdir` anything and the bug never fires.
Confirmed live: 2/2 reproductions from the main checkout, 0 failures across 15 fresh builds run from
a worktree. Incidental, not a fix — every worktree on this box shares that one directory.

**18/21 levels now have a cached self-built golden** under `/tmp/uedcli-parity-cache/` (3
pre-existing: UNATCO/`03_NYC_UNATCOHQ.dx`, Wanchai Market, `DX.dx`; 15 newly built this session). 3
failed, no cached golden: **Endgame4** (offline UCC `batchexport` can't resolve
`Engine.CameraPoint` — an extraction-mechanism gap, does not contradict the earlier geometry-exact
finding via a different, live-editor ingest path); **smuggler** and **nyc-street** (both crash at
`EDIT PASTE` right after `MAP NEW` — same signature as this session's Wanchai self-build crash,
`wanchai-self-build-edit-paste-crash`).

**Full per-level table, corrected against each level's raw log** (the golden-generation subagent's
own summary table understated two levels' real deltas — UNATCO's node count was reported as a stale
`+7` when the live re-verified number is `+0`, and Wanchai Market was called "EXACT" despite real
verts/points/vectors deltas already on record all session; both corrected here from the raw
`_scratch/parity_runs/*.log` output). Per the owner's standing format: tree structure = nodes/surfs/
leaves all zero-delta; verts/points/vectors = all three zero-delta; geometry % = categories exact
out of 6.

| level | tree structure | verts/pts/vectors | geometry | lighting (records) |
|---|:---:|:---:|---:|---:|
| DX.dx (intro) | ✅ | ✅ | 6/6 (100%) | 26/26 (100.0%) |
| NYC Bar | ✅ | ✅ | 6/6 (100%) | 821/936 (87.7%) |
| UNATCO (`03_NYC_UNATCOHQ`) | ✅ | ❌ (+5/+16/+0) | 4/6 (66.7%) | 2797/3345 (83.6%) |
| NYC ShipFan | ✅ | ❌ (+1/+21/+0) | 4/6 (66.7%) | 638/916 (69.7%) |
| NYC Underground (04) | ✅ | ❌ (+26/+17/+0) | 4/6 (66.7%) | 448/803 (55.8%) |
| Wanchai Market | ✅ | ❌ (+74/+16/−8) | 3/6 (50.0%) | 3418/4530 (75.5%) |
| Paris Club | ❌ (+2 nodes) | ❌ (+36/+9/+0) | 3/6 (50.0%) | 1045/1361 (76.8%) |
| HK Helibase | ❌ (+9 nodes) | ❌ (+122/+292/+0) | 3/6 (50.0%) | 4023/6002 (67.0%) |
| Wanchai Garage | ❌ (−68 nodes/−12 leaves) | ❌ (−1224/−27/+0) | 2/6 (33.3%) | 1/941 (0.1%) |
| Paris Underground | ❌ (−108 nodes/−4 leaves) | ❌ (−1306/−143/+0) | 2/6 (33.3%) | 0/1293 (0.0%) |
| Paris Chateau | ❌ (+4 nodes) | ❌ (+16/+43/+2) | 2/6 (33.3%) | 3800/4646 (81.8%) |
| Area51 Entrance | ❌ (+85/+51) | ❌ (+1055/+99/−9) | 1/6 (16.7%) | 3/5746 (0.1%) |
| Training Final | ❌ (+105/+13) | ❌ (+1464/+286/+11) | 1/6 (16.7%) | 2/4875 (0.0%) |
| FreeClinic08 | ❌ (−30/+1/−23) | ❌ (−729/−23/+0) | 1/6 (16.7%) | 1/1510 (0.1%) |
| NYC 747 | ❌ (all 3 off) | ❌ (all 3 off) | 0/6 (0%) | 5/1918 (0.3%) |
| Vandenberg Gas | ❌ (all 3 off) | ❌ (all 3 off) | 0/6 (0%) | 8/4325 (0.2%) |
| OceanLab Lab | ❌ (all 3 off) | ❌ (all 3 off) | 0/6 (0%) | 9/10630 (0.1%) |
| NSFHQ04 | ❌ (all 3 off) | ❌ (all 3 off) | 0/6 (0%) | 2/3321 (0.1%) |
| Endgame4 | — | — | FAILED (extraction) | — |
| smuggler | — | — | FAILED (crash) | — |
| nyc-street | — | — | FAILED (crash) | — |

**Zero levels at FULL PARITY** except the trivial `DX.dx` intro map — no real, non-trivial level has
both tree structure AND verts/points/vectors AND every lighting record byte-identical. Geometry-6/6
count: 2/21 (`DX.dx`, NYC Bar — both genuinely all-six-exact, not the looser node/surf/leaf "EXACT").
Confirms the standing "lighting is gated on geometry parity" pattern: every level with a large
geometry delta (any of Area51/NYC747/TrainingFinal/VandenbergGas/OceanLab over-build,
FreeClinic08/NSFHQ04/WanchaiGarage/ParisUnderground under-build) collapses to <1% lighting; levels
with only small verts/points deltas still land 55-90%. No new root-causing done this pass — breadth
over depth, per the task.

**Smuggler round 3: self-coincidence LIVE-CONFIRMED as a real native/editor divergence via an
isolated single-brush editor rebuild; exact root cause still not pinned, no fix shipped.** Round 2
left it undetermined whether native's classification of `Brush547`'s poly124 (which the trace shows
landing `COPLANAR dot=-1.00000` against the SAME brush's own poly5, both faces of the "Heli Lift"
prop touching at Y≈32 with opposite normals) genuinely diverges from the real editor, or reflects
some PASS-2 mechanism native doesn't model. Built `_scratch/smuggler-b547-isolated`: the confirmed-
exact PASS-A structural trunk (429 non-semisolid brushes) + `Brush547` alone appended last (matching
`10-bsp-csg-build.md`'s documented PASS B — a full, unrepartitioned second pass strictly after PASS
A, in trunk order — so this ordering is a faithful reduction, not a guess), driven through a real
`MAP NEW`→`EDIT PASTE`(chunked)→`MAP REBUILD`→`MAP SAVE` via a new
`smuggler_b547_isolated_golden.py` (copy of `geo_golden_resume_structural.py` retargeted). Native's
own offline build of the identical isolated trunk reproduces the full-level result exactly (65 surfs
for `Brush547`, same extra `i_brush_poly=124` key) — proving the effect has zero dependency on the
other 78 semisolid brushes. **The live editor golden for this same isolated trunk: 64 surfs for
`Brush547`, `i_brush_poly=124` absent** — the identical delta, reproduced with a real editor in
complete isolation. This upgrades round 2's "not determined" to a confirmed fact: native's handling
of this self-coincidence is a genuine algorithmic divergence from the real editor, not an artifact of
cross-brush interaction or of the unscoped tracer.

Two more candidate mechanisms ruled out this round: (1) `splitwithplane-degenerate-fragment-fallback`
(the catalogued `FPoly::SplitWithPlane` degenerate-sliver fallback) — checked directly, both `SPLIT`s
poly124 passes through en route to node 2706 produce `f_nv=4 b_nv=4`, no degenerate fragment, so that
gap does not apply here. (2) A surf-reuse/dedup difference in `bsp_add_node`'s `i_link` handling —
checked the code (`bspcsg.rs` `brush_loop1`'s pre-pass groups same-brush polys sharing an identical
plane+orientation via `links[i]`, seeding a shared speculative surf slot): poly5 (normal `(0,1,0)`)
and poly124 (normal `(0.00208,-1,0)`, opposite-facing) are NOT in the same orientation-equivalence
class, so each gets its own surf slot on both sides regardless — not the mechanism either. The
node-2706 `Coplanar` classification itself is also not a threshold-borderline call: vertex distances
to the plane are `0.0`–`0.0166`, comfortably inside `THRESH_SPLIT_POLY_WITH_PLANE`'s `±0.25` band, not
a near-miss at that specific test.

Best remaining candidate, NOT confirmed: a small (sub-0.001, ULP-level) floating-point difference
between native's and the real editor's vertex/normal transform for this Yaw=`-16384`-rotated brush —
visible as small plane-key mismatches (e.g. normal `(0.0,-1.0,-0.002)` vs `(-0.0,-1.0,-0.002)`, dist
`-60.6` vs `-60.7`) across MOST of `Brush547`'s other surviving faces too (harmless there, since
neither side's classification flips) — could tip the ~20-node-deep descent path leading to node 2706
just enough to change poly124's final classification, without touching the coplanar test's own
threshold. Pinning this needs bit-level comparison of the two transform code paths, the same class of
work as the still-open `wanchai-verts-points-residual-independently` Points residual — out of this
round's scope. Per the standing rule, no fix shipped without a confirmed mechanism. Harness added:
`smuggler_b547_isolated_golden.py` (committed alongside this entry), trunk under
`_scratch/smuggler-b547-isolated/` (not committed, scratch). Full write-up:
`dev/docs/board/inbox/smuggler-4-surf-delta-traced-to-4-pf-semisolid/overview.md` (Round 3).

**MAJOR CORRECTION: "tree structure EXACT" claims for DX.dx, NYC Bar, UNATCO, Wanchai Market, NYC
ShipFan, and NYC Underground were all count-coincidence, not content identity — zero levels in the
corpus have genuine structural tree parity.** (2026-08-31) — `parity_report.py`'s geometry check
only ever compared aggregate array LENGTHS (`len(model.nodes)` etc.), never the actual per-index
content. Added real index-for-index field comparison (`ContentComparison`, bit-exact, no epsilon,
generic over `dataclasses.fields` so it can't drift from the real struct layout) covering
nodes/surfs/leaves — the same "tree structure" triple this ledger's own reporting format is built
on. Ran against every level previously reported as node/surf/leaf-exact:

- **`DX.dx`** (previously the session's one clean `FULL PARITY: YES`): NOT content-exact. 8/26
  nodes differ (`node_flags`, `i_leaf`); every one of 26 surfs differs (`texture_ref`, `i_actor`,
  `p_base`); all 5 leaves differ in `i_permeating` (native always `-1`, golden has real per-leaf
  light-list indices — this specific divergence is EXPECTED and matches the already-known,
  not-yet-wired-in `port-the-per-leaf-permeating-light-lists-model` gap, not a new finding).
- **NYC Bar** (previously the only non-trivial 6/6-geometry-exact level): NOT content-exact. 2700+
  individual field divergences across nodes/surfs, dominated by `i_actor`/`texture_ref`/`p_base`.
- UNATCO, Wanchai Market, NYC ShipFan, NYC Underground: all already `geometry NOT EXACT` (counts
  themselves don't match), so content divergence there is expected, not new information — confirmed
  for completeness.

The scale and pattern of the `i_actor`/`texture_ref` divergence (large, systematic, not small
plane-key noise) is consistent with a package import/export table ORDERING difference between
native's and the golden's object-ref numbering, not necessarily a BSP topology bug — a hypothesis,
not confirmed. `p_base`'s divergence looks more structurally relevant (a Points-array base-index
per surf) and may connect to the still-open `wanchai-verts-points-residual-independently` thread.
Root-causing either is a genuine, separate investigation for a future round — not attempted here,
this was a measurement-tooling fix, not a BSP-algorithm fix. `git diff -- uedcli-native/src/` is
empty; no source changes.

Implementation note: an independent review pass (dispatched specifically because this tool is now
the source of truth for parity claims) caught two things before merge — a build-stage mismatch
(comparing native's bare `build_geometry_bspcsg` output, which never populates
`texture_ref`/`i_actor`/`i_light_map`, against golden's fully-assembled surfs; fixed by parsing
native's own fully-assembled `.dx` bytes on both sides) and a non-bit-exact float comparison (`!=`
on Python floats: `-0.0 != 0.0` is `False`, `NaN != NaN` is `True`; fixed via on-disk f32 byte
comparison). The review then caught a third gap (leaves missing from the comparison entirely,
fixed the same way). 43 unit tests, `bin/test` unaffected (12721 passed/0 failed + 91/91 cargo,
this only touches `dev/docs/` harness code).

**Follow-up: the `texture_ref`/`i_actor` ordering hypothesis above is REFUTED. Root cause found: a
golden-build actor-set mismatch, not a native table-ordering bug.** (2026-08-31) — parsed both
`DX.dx` packages' full import/export tables (`uedcli/native/pkg_write.parse_package`). Native: 23
imports/52 exports/115 names. Golden: 14 imports/33 exports/87 names — not the same content
reordered, a genuinely smaller POPULATION: golden is missing 19 real trunk actors native includes
(`DXLogo3`, `DXText0/1`, `DeusExLevelInfo0`, `EidosLogo0`, `ElectricityEmitter0`, all 16
`InterpolationPoint*`, `IonStormLogo0`, `PlayerStart1` — every decorative/non-brush/non-light actor),
and instead carries 6 `Camera6`-`Camera11` exports that came from neither the trunk nor golden's own
paste filter — live confirmation of the already-suspected "`SpawnViewActor` reuses a free `Camera`"
mechanism (this file's lighting section, "Two smaller leads"): `GetVisibleSurfs`'s six 90°-apart temp
visibility cameras leak into the saved package uncleaned. Cause: `build_ued_lit_golden.py` (which
every `parity_report.py` golden is built with) deliberately pastes only `{Brush, LevelInfo} ∪
light-classes` into the editor — correct for its original geometry/lighting-only purpose, but
`compare_content` (added this same round) diffs native's FULL-actor-set package against this
narrowed golden field-by-field. `texture_ref`/`i_actor` are absolute object-ref integers into each
package's OWN table, so comparing them across two differently-populated packages is apples-to-oranges
regardless of whether native's resolver is correct — and where checked, both sides resolve to the
SAME semantic identity (leaf names match: every surf's texture is `BlackMaskTex` on both sides, the
referenced brush names match too). Likely explains a large share of the corpus-wide
`texture_ref`/`i_actor` diff counts, not just `DX.dx` — unconfirmed beyond `DX.dx` this round.
**No fix shipped** — the real options (widen the golden's actor set past the brush-safety line, or
compare object-refs by resolved identity instead of raw index) are a tooling design call, not a
native-code fix; logged for a decision rather than picked unilaterally.
`board/inbox/texture-ref-i-actor-divergence-traced-to-golden` has the full write-up.

`p_base` (a Points-array index, unrelated to object-ref tables) is a SEPARATE, real divergence: on
`DX.dx`, verts/points/vectors counts are already zero-delta, yet `p_base` differs across most surfs
by small amounts — e.g. `Brush3`'s surfs walk the same 5-point set `{0..4}` on both sides but the
last three surfs read them as `2,3,4` (native) vs `3,4,2` (golden), a cyclic rotation, not noise.
Likely the same FAMILY as `wanchai-verts-points-residual-independently` (a Points-array
construction-order divergence) but not confirmed identical — that thread's cases carry a real count
residual (Wanchai +16, UNATCO +16) while `DX.dx` shows pure reordering with no count delta, a
cleaner, smaller isolated repro if that thread is picked up again. Not chased further this round.

**Round 2: golden actor-set widened (movers excluded, schema-checked) and shipped SAFE — but the
texture_ref/i_actor fix does NOT deliver; hypothesis REFUTED a second, stronger time.** (2026-08-31,
owner-directed follow-up) — `build_ued_lit_golden.py`'s default `keep` widened from
`{Brush,LevelInfo}∪lights` to every trunk class EXCEPT `Engine.Mover` descendants, resolved via
`classindex.ClassIndex`+`movers.is_mover` (schema-based, not name-matching — catches
`DeusEx.BreakableGlass` on Wanchai, which doesn't end in "Mover"). A class whose mover-ness can't be
resolved is excluded conservatively. New `--keep-classes ALL` + `--allow-brush-bearing` force the
true full set (movers included) for measurement; the refuse-on-brush-bearing check still gates the
default path.

*Safety (the owner's bar): PASSED.* Geometry COUNTS (nodes/surfs/leaves/verts/points/vectors)
unchanged after widening on `DX.dx` (26/26/5/250/32/6), UNATCO (6314/3616/762/76488/10752/599) and
NYC Bar (1620/953/283/20878/2762/138) — byte-identical to the existing narrow goldens. Content-level
check on `DX.dx` confirms it's genuinely inert, not count-coincidence: nodes/leaves identical
field-for-field, only surfs' `i_actor`/`texture_ref` shift (expected index-table renumbering from the
larger population).

*Owner follow-up: also tried the TRUE full set on UNATCO, movers included
(`--keep-classes ALL --allow-brush-bearing`, 28 `DeusExMover` actors).* Counts still unchanged,
byte-identical — movers pasted via `EDIT PASTE` do NOT merge into the world model (764 vs 736 `Model`
exports, +28 = exactly the mover count, each keeping its own private Model, matching real production
`MAP LOAD` behavior). But content-level check found `node_flags` differs on 862/6314 world nodes
(13.7%) — confirmed REAL, not noise (two independent builds of the identical movers-excluded set are
100% byte-identical, zero diffs — the pipeline is deterministic). Every other node field
(`plane`/`i_leaf`/`i_zone`/etc.) is unaffected; surfs differ only in the expected object-ref shift;
leaves 100% identical. A smaller same-direction effect (20/6314 nodes) already exists between the
ORIGINAL narrow golden and the movers-EXCLUDED widened one, so `node_flags` (occlusion/lighting-bake
metadata — see `unrealed/quirks.md` "`0x08 NF_PolyOccluded` + `0x10 NF_BoxOccluded`... render-only
occlusion bits") has some sensitivity to actor population generally, far more so with movers. Node
topology (the owner's literal safety bar) is unaffected either way. **Not shipped as the default** —
counts-unchanged was the stated "ship it" criterion, but the node_flags finding is new information
outside that criterion, and movers-excluded also matches native's OWN world-model build
(`parity_compare.build_native_model` filters non-world-CSG brushes — i.e. movers — from its own
input), so it's the internally-consistent choice pending a decision this round doesn't make
unilaterally.

*The motivating hypothesis is REFUTED, more strongly than the first round.* Re-ran `compare_content`
(native's full build vs the WIDENED golden) on `DX.dx`, NYC Bar and UNATCO: field-diff counts are
statistically unchanged from the narrow-golden baseline on all three (`DX.dx`: identical — same
8/26 nodes, 26/26 surfs, 5/5 leaves, same fields; NYC Bar: nodes 2066→2091, surfs 2739→2830, leaves
WORSE 354→637 with a new `i_volumetric` divergence; UNATCO: 22202→22199, 10940→10941, 1496→1496,
noise-level). Direct export-table diff on `DX.dx` explains why: the golden's table still doesn't
match native's even with matching actor POPULATIONS, because (a) the leaked `Camera6`-`Camera11`
`GetVisibleSurfs` temp-viewport exports persist regardless of which actors were pasted (a separate,
unfixed bug), and (b) native's serializer names per-brush auxiliary objects differently from the real
editor (`Model_Brush3Polys` vs `Polys6`, etc.) — a structural difference between the two build
mechanisms no actor-set widening can close. `texture_ref`/`i_actor` are raw indices into these
tables, so they were never going to converge via population-matching alone. Of the two options the
first round logged, only "widen the actor set" was tried and it does not deliver; "compare object-refs
by resolved semantic identity instead of raw index" (in `compare_content`) is the one worth trying
next.

*New blocker found, not chased:* `06_HongKong_WanChai_Market`'s widened build CRASHES the editor
reproducibly at the first `EDIT PASTE` (2 attempts, identical failure point); its narrow golden is
untouched and still valid. Root cause not investigated (budget; retry-once-then-file-a-finding).

Not committed (spike harness change, left for the coordinating session per task instruction).
Reproduction: `build_ued_lit_golden.py --trunk <trunk> --out <out> --keep-classes ALL
--allow-brush-bearing` for the true full set; drop both flags for the new (movers-excluded) default.
This round's widened goldens are at `/tmp/uedcli-widen-test/`, NOT installed over the live
`/tmp/uedcli-parity-cache/` entries — that cache is shared across sessions, and this round's own
numbers argue against silently treating "widened" as an improvement to adopt; installing over the
live cache is the coordinating session's call. Full write-up:
`board/inbox/texture-ref-i-actor-divergence-traced-to-golden` (Round 2).

**Round 3: `Polys` naming — the CONVENTION is confirmed, the exact per-object VALUE is not
reproducible, and a naming-only fix would not move `texture_ref`/`i_actor` anyway. No fix shipped.**
(2026-08-31.) Follow-up on the `Model_Brush3Polys` vs `Polys6` lead from round 2.

*The editor's naming rule, confirmed with high confidence across 3 goldens (`DX.dx`, NYC Bar,
UNATCO — 1400+ Model/Polys exports inspected via `pkg_write.parse_package`):* a brush's inner
`Model` keeps whatever name its T3D `Brush=Model'Pkg.Model_Brush3'` line gives it explicitly
(matches native's own `Model_{actorname}` scheme byte-for-byte — no divergence there). Its `Polys`
sub-object does NOT — `t3d.md`'s own `Begin PolyList … End PolyList` grammar (line 43) carries no
`Name=` field, so the T3D importer (the golden is built by `EDIT PASTE`, a T3D-parse path) is forced
to auto-create it, landing on the class's own global auto-name: `Polys<N>`, N a package-wide counter
for the `Polys` class, unrelated to the owning brush. Every golden inspected: strictly `Polys<N>`,
`N` stepping by exactly +2 per successive brush in export order (`Polys4,6,8,…`; UNATCO: 720
consecutive +2 steps over 723 Polys/Model pairs) — never once `<brush-derived-string>Polys`.

*Why the exact value is not reproducible:* the per-brush +2 step (not +1) means TWO `Polys` objects are allocated
per brush and only the even one survives to be saved — a temp/working copy the editor discards
before `MAP SAVE`, consistent with `quirks.md`'s already-documented extra `Engine.Polys` block per
level (the world `Model`'s own aggregate post-CSG surface set, "position among the per-brush blocks
is not stable"). This starting offset (base N before the first per-brush entry) is NOT constant
across levels — 6 on `DX.dx` and NYC Bar, but 4 on UNATCO — and the world-model's own aggregate
`Polys` export lands OUT of the per-brush numeric run and at an arbitrary export-table position (on
UNATCO: `Polys1447`, appearing near the world `Model` export, well before the per-brush run that
tops out at `Polys1444`). None of this is derivable from the T3D trunk; it is a byproduct of
`build_ued_lit_golden.py`'s own internal `EDIT PASTE`/CSG/temp-object churn inside that specific
editor session, which native does not run and has no way to replicate short of literally emulating
the editor's per-brush CSG-temp-object allocation order — a materially bigger reverse-engineering
task than "a naming convention," out of scope for this round's budget.

*Renaming alone would not close the `texture_ref`/`i_actor` gap regardless:* both fields are raw
POSITIONAL object-refs into the combined import/export index space (`umodel.py` `BspSurf.texture_ref`
= "obj-ref of the texture", `i_actor` = "owning brush actor ref" — positive = export index+1,
negative = -(import index+1); see `umodel.py:61,67`), not name-string lookups. Changing only the
STRING attached to an already-reserved export would not move its table position/count, so a
naming-only fix cannot by construction change these fields. What actually determines them is export
table population (count) and order — a separate axis from the naming-string question this round was
scoped to.

*One separate, concrete, structural finding surfaced along the way (not this round's mandate, not
fixed):* `unbuilt.py`'s world-model reservation (`lm = "Model_Level"`, `unbuilt.py:323-336`) never
reserves a companion `Polys` export for the world model — native's assembled package has NO
counterpart to the golden's extra world-aggregate `Engine.Polys` block that `quirks.md` already
documents the real editor always emits. This is a genuine export-table COUNT gap (not a naming
artifact), independently visible in the DX.dx export-table diff (widened golden: 57 exports vs
native's 52). Flagged, not fixed — inserting it requires knowing where in the table it belongs and
whether omitting it has any consequence beyond this comparison harness (the `unbuilt.py` comment at
line 342 asserts export order is "reshuffled harmlessly" by the editor, which this round did not
re-verify against a COUNT mismatch specifically). A candidate for a future round, not this one.

**No fix shipped.** The naming CONVENTION is pinned; the reproducible VALUE and its actual relevance
to `texture_ref`/`i_actor` are not. Full write-up: `board/inbox/texture-ref-i-actor-divergence-traced-to-golden` (Round 3).

**`node_flags` 862/6314 divergence (movers-excluded vs movers-included): reproduced; splits cleanly
into a known render bit and a new, unexplained one.** (2026-08-31, 🔬 disassembly + offline
analysis, no live capture) — Follow-up to Round 2's finding above. Bit-level XOR of the 862 diffs:
`0x08` (337 nodes) + `0x10` (34) = the ALREADY-confirmed render-viewport occlusion leftover
(`node-flags-8-is-nf-polyoccluded-a-render-only`, done/) — expected, since movers are visible
occluding geometry the editor's last-viewport-render pass reasons about. `0x40` (346) + `0x80` (218)
are NEW: absent from every movers-excluded build tried (never appear without movers), union 564
nodes — the majority of the diff. Isolating the general (non-mover) actor-population effect
(cached pre-widening narrow golden vs movers-excluded-widened, 20/6314 diffs) shows it's 100% bit
`0x10` — confirms `0x40`/`0x80` are mover-specific, not a generic actor-count effect.

Repeated the exact disassembly method the original `0x08` finding used (`capstone`+`pefile`,
`FBspNode.NodeFlags` at struct offset `+0x37`), widened to any mnemonic/addressing form, across
`Editor.dll`/`render.dll`/`core.dll`/`Engine.dll`/`unrealed.exe`: **no instruction anywhere sets
`0x40` or `0x80`.** `Editor.dll` touches offset `+0x37` NOT AT ALL (extends "Editor.dll sets neither
0x08 nor 0x10" to every bit — the whole deterministic build path never patches `NodeFlags` after
`bspAddNode`'s own argument sets it once). `render.dll` has only the already-known 4 occlusion-walk
instructions (plus one previously-unlogged clear, `and [.+0x37],0xf7`, the walk's own reset step) —
none touch `0x40`/`0x80`. Two `Engine.dll` near-hits are `TLazyArray<BYTE>` ctor/assign, unrelated to
`FBspNode`, a coincidental offset collision.

Structural correlation (28 UNATCO movers' own root-to-leaf BSP descent paths, from their trunk
`Location`s): real but far too small to be the mechanism — 24 total nodes touched across all 28
movers (paths are 9-10 deep), vs 564 flipped by `0x40`/`0x80`. Real 4x enrichment (a mover's own path
hits diff nodes at 33-55% vs the 13.7% base rate) explains only 9/564 by direct overlap. No
zone-clustering either — scattered proportionally to the level's overall zone population, matching
the ORIGINAL `0x08` finding's own "scattered, uncorrelated with zone" note.

**Leading hypothesis, NOT live-confirmed: `0x40`/`0x80` are uninitialized-memory noise, not a real
algorithm.** Movers are brush-bearing (own private Models, real per-actor CSG/paste work during
`EDIT PASTE`) — categorically different allocation activity than plain actors, which is exactly the
class this divergence gates on. Combined with the pre-existing live-verified fact that the Nodes
array grows past its own `Num` into un-zeroed scratch slots every `bspRepartition` call
(`nodesnum_watch.py`, 2026-08-30), a node's `NodeFlags` byte reading stale/reused memory content is a
better fit than a deliberate scene-aware computation (no setter found; scattered, not clustered).
Not live-verified — no heap-history/watchpoint capture done this round.

**Implication:** does not support switching the default golden to movers-included. If `0x40`/`0x80`
is noise, there's no algorithm to port, the opposite of the round's motivating question. Recommend
(not decided) extending the existing `node_flags` exclusion (`82b-ground-truth-byte-diff.md`,
"masking BOTH bits makes the editor's build-time flags EQUAL native's exactly") to cover `0x40`/
`0x80` too. No `bspcsg.rs`/`uedcli-native` changes; pure analysis + static disassembly, no container
spin-up. Full write-up: `board/inbox/node-flags-0x40-0x80-divergence-from-movers-no`.

**Round 4: CORRECTION to Round 3's "genuine export-table COUNT gap" — refuted. `Polys` export COUNTS
already match (6=6); the real 57-vs-52 gap is the already-known Camera leak (+6) plus one new,
unrelated `LevelSummary` gap (+1) plus an unrelated actor-drop wash (-1/-1). The one real remaining
divergence is a FIELD, not a missing export — and its content is confirmed NOT derivable from final
Model/Surf data. No fix shipped; index-shift risk confirmed non-existent (moot).** (2026-08-31, 🔬
live re-parse, `pkg_write.parse_package` + a hand-rolled `FPoly`/`UPolys` body parser matching
`actor_write.write_fpoly`/`write_upolys_body`'s exact layout, cross-checked byte-for-byte via each
`Model`'s own reach-EOF self-check.) Independently re-derived from raw bytes, not from reading the
Round 3 entry as a premise.

Re-verified current-tree numbers directly (not trusted from Round 3): golden (`dx_widened.dx`,
unchanged since Round 2/3) parses to 26 imports/57 exports/143 names. Native's own fresh build
(worktree `world-polys-export-check`, needed only because `umodel_win32`'s docker mount fails from
the main checkout — `docker-mount-source-permission-fails-from-main`; extracted DX's trunk via
`parity_pipeline.ensure_golden`, built via `parity_compare.build_native_lit_dx`) parses to 23
imports/52 exports/115 names — exact match to Round 1/3's cited number, now re-confirmed live on the
current tree, not carried over.

**Per-class export diff (the check Round 3 didn't do) refutes its own framing:** `Counter` over
`class_of_export` for every export, native vs golden — only 4 classes differ: `Camera` (0→6, the
already-known `GetVisibleSurfs` leak), `LevelSummary` (0→1, new, see below), `Brush` (8→7) and
`Model` (7→6). **`Polys`: 6 native, 6 golden — EQUAL.** Round 3's "genuine export-table COUNT gap
(not a naming artifact)" for `Polys` is wrong; there is no `Polys`-count deficit to fix. The
`Brush`/`Model` -1/-1 is a pre-existing, unrelated wash: native's own build emits two `Brush1`/`Brush2`
actors with a live warning ("`refers to MyLevel.Model2, which this level does not contain --
dropped`") that this specific DX.dx trunk already carries, orthogonal to this task.

**What IS real: native's world `Model` (`Model_Level`) never sets its own `field_0x54`
(`UModel.Polys=`, `assemble.py`'s own comment on the identical per-brush field), so it serializes as
0/None; the golden's world `Model` (`Model2`) has it set to a real, non-empty `Polys` export.**
Confirmed via `umodel.parse_model_body`'s own reach-EOF self-check (would raise on any layout
misread) on `Model2`'s full body. This is a genuine field-content divergence, not a table-count one —
`unbuilt.py`'s `_world_model_body` (lines 331-336) has no counterpart to `assemble.py`'s
`_empty_model_body`'s `m.field_0x54 = asm.eref(polys_name)` for every OTHER `Model` it writes.

**What that field actually points to, checked on 3 levels — NOT a stable "aggregate of every
surviving surf" as `quirks.md`'s `OBJ DEPENDENCIES`-based note (a different, text-dump mechanism)
suggested, and not derivable from `Model.Surfs`/`Nodes` by any formula tried:**
- `DX.dx` (26 nodes = 26 surfs, no BSP splitting): world `Model2.field_0x54` → `Polys15`, 26 `FPoly`
  entries, `i_link` sequential 0-25 (matches surf index), `actor_ref` spanning ALL 5 real brushes
  (2,3,4,6,7 mixed) — degenerate/inconclusive on its own (surf count IS 26 here).
- NYC Bar (widened golden, 1620 nodes / 953 surfs): world `Model2.field_0x54` → `Polys411`, only **9**
  `FPoly` entries, **every one the SAME single `actor_ref` (59)** — an octagonal-prism shape (8 side
  quads + 1 cap), `i_link` sequential 1500-1508, `i_brush_poly` 0-7 then 9. Not remotely an aggregate
  of 953 surfs — this is one brush's own authored poly set.
- UNATCO (widened golden, 6314 nodes / 3616 surfs): same pattern, worse — `Polys1473`, only **6**
  `FPoly` entries, **all one single `actor_ref` (187)**.

**Circumstantial mechanism, not confirmed live:** `DX.dx`'s world `Polys15` is numbered immediately
adjacent to `Brush4`'s own dedicated `Polys14` (the LAST per-brush `Polys` in the global `Polys<N>`
counter run, per Round 3's own "+2 per brush" finding) — consistent with the world `Model`'s
`Polys=` field simply being left pointing at whatever SCRATCH `Polys` object the editor's internal
per-brush CSG loop most recently touched when the loop ended, not a deliberate semantic aggregate.
This would explain both the DX.dx and NYC-Bar/UNATCO shapes (a trivial level's "last touched" scratch
state happens to look aggregate-like; a large level's does not) without needing two different
mechanisms. **Not live-verified — would need a `bspBrushCSG`/`csgRebuild` capture of `Model->Polys`
across the per-brush loop to confirm**, out of this round's scope.

**Risk (the round's other mandate): CONFIRMED SAFE, though now moot since no fix ships.**
`assemble.py`'s `_Assembler._reserve`/`eref` is fully name-resolved: every export is looked up via
`asm.index_of[name]` (a dict), body closures run only after ALL exports are reserved (`build()`,
"Body fns run AFTER all exports are reserved, so eref() resolves any forward ref"), and a grep of
every `.exports[` site in `unbuilt.py`/`assemble.py`/`pkg_write.py` confirms none indexes by a raw
hardcoded position — always through `index_of`/`eref`. Adding one more `_reserve()` call anywhere
would not shift or break any other reference. The Round 3 "does reshuffling break a hardcoded index"
worry does not apply to this codebase.

**No fix shipped.** Per the standing "no guessing at content" rule: the export-count gap this was
meant to close does not exist (`Polys` counts already match); the one real divergence (the world
Model's own `Polys=` field) has content that is level-dependent, editor-build-order-dependent, and
not reconstructible from `Model.Surfs`/`Nodes`/`Verts` by any formula this round tried on 3 different
levels — confirmed wrong on 2 of 3, not merely "unverified." Shipping "point at a synthesized
aggregate of all surfs" (the natural guess) would be a known-wrong value, not an approximation.
Closing this needs a live capture of the editor's internal per-brush CSG/`Polys`-scratch-reuse
timing, not a native-code change.

**New, unrelated, unflagged finding surfaced, not chased:** the golden carries one `LevelSummary`
export (14 bytes: `b'1]\n\tUntitled\x00\x00'`) that native never emits — looks like a `MAP
SAVE`-time editor bookkeeping object (map-browser title/thumbnail metadata), not investigated
further. Separate from both the Camera leak and this entry's `Polys` field question; worth a board
item if a future round wants full export-table parity.

No `unbuilt.py`/`assemble.py`/any production code changes this round — read-only live re-parsing in a
disposable worktree (removed after, no commits). `bin/test` not re-run (no source changed).

## `parity_report.py` content comparison now masks proven-noisy `node_flags` bits — result: no level's nodes array is node-exact even so

Measurement-tool change, not a native-code change. `compare_array_content` (`parity_lib.py`) compared
`BspNode.node_flags` bit-exact, unmasked, same as every other field — but two already-closed findings
prove 4 of its 8 bits are not part of the editor's deterministic build at all: `0x08`/`0x10`
(`NF_PolyOccluded`/`NF_BoxOccluded`, render-viewport occlusion leftover from whatever camera position
the LAST `LIGHT APPLY` session happened to leave, set only by `render.dll`, confirmed absent from
`Editor.dll`'s entire build path — `board/done/node-flags-8-is-nf-polyoccluded-a-render-only`) and
`0x40`/`0x80` (no disassembly-confirmed setter ANYWHERE in the editor, all 5 relevant DLLs/EXE
scanned; best-supported hypothesis is uninitialized-memory noise from mover-triggered allocation, not
a real algorithm — `board/inbox/node-flags-0x40-0x80-divergence-from-movers-no`). Comparing these
bit-exact was measuring noise, not a real divergence.

Added `NODE_FLAGS_NOISE_MASK = 0x08|0x10|0x40|0x80`; `compare_array_content` now masks only this one
field (`(native & ~MASK) != (golden & ~MASK)`) before comparing — every other `BspNode` field and all
of `BspSurf` stay bit-exact, zero tolerance, unchanged. Report text/JSON headers now name the mask and
cite both board items so a future reader can't mistake this for an unmasked comparison. TDD:
`test_parity_lib.py` gained 3 tests — masked-bits-only diff now reports exact, a real (non-masked) bit
flip still reports a diff, and a real diff in a DIFFERENT field (`i_leaf`) on a node whose
`node_flags` also differs is still caught (the mask must not swallow anything beyond its own field).

**Re-measured all 6 tracked levels (self-built goldens, cached; native's own freshly-built lit `.dx`
each time) — before (unmasked) vs after (masked) node-content diff INDEX count:**

| level | before (idx differ) | after (idx differ) | swallowed (node_flags-only) | nodes now exact? |
|---|---:|---:|---:|---|
| `DX.dx` | 8 | 4 | 4 | NO — 4 `i_leaf` diffs remain |
| NYC Bar | 1351 | 942 | 409 | NO — `i_leaf`/`i_vert_pool`/`i_zone`/`plane` remain |
| UNATCO (`03_NYC_UNATCOHQ.dx`) | 6201 | 6002 | 199 | NO — `i_back`/`i_collision_bound`/`i_leaf`/`i_plane`/`i_render_bound`/`i_vert_pool`/`i_zone`/`plane`/`zone_mask` remain |
| Wanchai Market | 11168 | 9659 | 1509 | NO — `i_leaf`/`i_plane`/`i_vert_pool`/`i_zone`/`num_vertices`/`plane`/`zone_mask` remain |
| NYC ShipFan | 1731 | 1700 | 31 | NO — `i_leaf`/`i_plane`/`i_vert_pool`/`i_zone`/`plane`/`zone_mask` remain |
| NYC Underground | 1804 | 1775 | 29 | NO — `i_back`/`i_collision_bound`/`i_front`/`i_leaf`/`i_plane`/`i_render_bound`/`i_vert_pool`/`i_zone`/`num_vertices`/`plane`/`zone_mask` remain |

**Verdict: masking is correct and does remove real noise (409-1509 indices per level stop being
misreported as diverging on the bigger levels), but it does not reveal any level's nodes array as
genuinely content-exact.** Every level still has real, non-masked field divergence after
masking — dominated by `plane`/`i_zone`/`i_vert_pool`/`i_plane` on the larger levels (an open,
already-tracked structural issue, not this task's scope) and, on `DX.dx` specifically, a small
isolated `i_leaf` residual (4/26 nodes) with no `node_flags` involvement at all. `surfs`/`leaves`
still diverge on every level too (`texture_ref`/`i_actor`/`p_base`/`i_permeating` — all pre-existing,
separately tracked threads, untouched by this change; `BspSurf`'s comparison was not touched, per
scope).

Reproduction: cached goldens under `/tmp/uedcli-parity-cache/`; native's lit `.dx` built via
`parity_compare.build_native_lit_dx`; run from a worktree (main-checkout docker mount-source bug,
`board/inbox/docker-mount-source-permission-fails-from-main`), `.venv`/`dev/games` symlinked in from
the main checkout, no commits made there, worktree removed after. Before/after table via a throwaway
script toggling `parity_lib.NODE_FLAGS_NOISE_MASK` between 0 and its real value around two
`compare_content` calls on the same built native/golden pair (not committed).

## `DX.dx`'s last node-level residual, the 4/26 `i_leaf` diffs, was a real `zones.rs::assign_leaves` traversal-order bug — FIXED, `DX.dx` nodes now content-exact

**Confirmed live 2026-08-31, fix shipped (uncommitted, worktree `dx-ileaf-investigation`).** Re-ran
`parity_report.py` on `DX.dx` — same 4 diffs as the prior round, unchanged: nodes `[6]`, `[11]`,
`[21]`, `[25]` each disagree only on `i_leaf`, and only on the FRONT slot (`native=(-1,X)
golden=(-1,Y)`), never structurally (every other node field, and `i_front`/`i_back`/`i_plane` on
every node including these 4, already matched). Dumping both trees' `leaves` array content
(`i_zone`/`i_volumetric`/`i_exclusive`, ignoring the separately-tracked, not-yet-wired
`i_permeating`) showed all 5 leaves IDENTICAL in content on both sides (`i_zone=1`,
`i_volumetric=-1`, `i_exclusive=all-1s` — `DX.dx` is degenerate: one zone, no volumetrics). Native's
4 leaf-index values were exactly the reverse of golden's (`0↔4`, `1↔3`, `2` fixed) — the signature of
a traversal-ORDER difference, not a structural one.

**Root cause, confirmed by simulation against native's own tree topology (not guessed):** replaying
`zones.rs::assign_leaves`'s Pass A DFS over `DX.dx`'s 26-node tree with each of the two possible
child-visit orders and diffing the resulting `iLeaf` numbering against golden's real on-disk values —
the current code's order (`i_back` then `i_front`) reproduces the exact 4 known mismatches (sanity
check); the opposite order (`i_front` then `i_back`) matches golden's numbering on **all 26 nodes,
0 mismatches**. This also matches what the project's own spec already said: `70-zones-portalization.md`
§2, "DFS over `iChild[0]`(back) then `iChild[1]`(front)" — and `iChild[0]` = this struct's `i_front`
field (`iChild[1]` = `i_back`, per this file's own FRONT/BACK-swap note directly above
`assign_leaves`) — so the code had transcribed the spec's own already-decoded order backwards. Not a
comparison-methodology artifact (leaves are NOT interchangeable/order-independent on disk — the
on-disk `iLeaf` field is a literal index into the `Leaves` array, so a wrong visit order really does
serialize different bytes) and not a structural/topological divergence (leaf content and the
front/back tree shape already matched).

**Fix:** swap the iteration order in `assign_leaves` (`uedcli-native/src/zones.rs`) from
`[(1usize, i_back), (0usize, i_front)]` to `[(0usize, i_front), (1usize, i_back)]` — side labels
(which side is FRONT vs BACK) are unchanged, only which is visited first. TDD: new test
`assign_leaves_visits_i_front_before_i_back` (red under the old order, green under the new) added
alongside the existing `zones.rs` unit tests.

**Before/after, `i_leaf` field diffs (node content comparison, `NODE_FLAGS_NOISE_MASK` still
applied):**

| level | i_leaf diffs before | i_leaf diffs after | other node fields (untouched) |
|---|---:|---:|---|
| `DX.dx` | 4/26 | **0/26 — nodes array now fully content-exact** | none (was the only remaining node diff) |
| `02_NYC_Bar.dx` | 874 | **0** | `i_zone` 11, `i_vert_pool` 67, `plane` 200 (pre-existing, untouched) |
| `03_NYC_UNATCOHQ` (`bsp-parity-proj` golden) | present (untabulated count) | **0** (absent from the field breakdown entirely) | `i_vert_pool` 4576, `plane` 668, `i_zone` 57, `i_plane` 23, `i_back` 3, `i_collision_bound` 2, `i_render_bound` 2, `zone_mask` 9 |
| Wanchai Market (`golden_wanchai_world.dx`) | present (untabulated count) | **0** (absent from the field breakdown entirely) | `i_vert_pool` 7803, `plane` 676, `i_zone` 205, `num_vertices` 10, `i_plane` 15, `zone_mask` 9 |

`regression_gate.py` (UNATCO/Wanchai): `GATE: PASS`, both still node/surf/leaf-COUNT-exact, same
pre-existing verts/points/vectors deltas as before this change (UNATCO +5/+16/+0, Wanchai
+74/+16/−8) — no regression. `DX.dx`'s remaining gap is now only `surfs`
(`texture_ref`/`i_actor`/`p_base`, pre-existing, out of scope) and `leaves.i_permeating`
(pre-existing stub, `port-the-per-leaf-permeating-light-lists-model`, out of scope) — the node-level
gap this round targeted is fully closed. `bin/test` and `cargo test` (92/92) run clean.

Not yet done: this fix was verified on 4 of the 6 tracked levels (not NYC ShipFan/NYC Underground);
those two were not re-measured this round.

## `DX.dx`'s `p_base` reordering: confirmed the SAME pre-existing §10.20 residual, not the Wanchai/UNATCO Points-count thread; existing `bsp_refresh_points_vectors`/`UEDCLI_BSPCSG_WORLD_KEEP_POINTS` measured with ZERO effect; no fix shipped

**Re-verified via `parity_report.py` (worktree `dx-pbase-investigation`, cache hit, no rebuild
needed):** 13/26 `DX.dx` surfs still diverge on `p_base` (indices 3,4,5 / 9,10,11 / 15,16,17 / 19,20 /
23,24). Every diff is a pure reorder within an already-correct point set — e.g. golden surfs 3,4,5
read `{3,4,2}`, native reads `{2,3,4}` (a cyclic rotation of the same 3-point subset), and this
pattern repeats per-brush. `verts`/`points`/`vectors` counts stay 0-delta (32/32 points both sides) —
confirms the round-2 characterization in `texture-ref-i-actor-divergence-traced-to-golden` still
holds, unstale.

**This is the SAME family as the Wanchai/UNATCO Points thread only in the loose sense of "Points-array
construction order" — but it is specifically the OTHER, older, already-pinned residual from that same
lineage, not the +16-count bug those 4 rounds chased.** `reorder_points_canonical`'s own doc comment
(`bspcsg.rs` ~L3290) already documents this exact defect, dated 2026-07-18 (spike §10.20, Test_Castle):
"this matches the editor's LAYOUT (bases-first block)... but NOT its exact intra-block order — the
editor's base/ring sub-order is a deeper `bspRefresh` reachability-DFS-compaction artifact of the
PRE-compaction pool indices, not reconstructable from the final model." `DX.dx` reproduces this
byte-for-byte in miniature: bases-first layout is right (0 count delta, structurally correct
26-surf/32-point pool), only the intra-block sub-order is wrong — the exact shape §10.20 already named
and left as a "deeper follow-on lever, not forced." Wanchai/UNATCO's own +16 residual (the 4-round
thread) is a different bug (raw pool-SIZE overshoot upstream of any compaction, not order) — the two
threads share a code area (`reorder_points_canonical`/`bsp_refresh_points_vectors`) but are not the
same defect.

**Tested whether the existing (Wanchai-thread-built, currently unwired) `bsp_refresh_points_vectors`
mechanism, via its `UEDCLI_BSPCSG_WORLD_KEEP_POINTS` gate, closes `DX.dx`'s gap anyway — measured, ZERO
effect.** Built native's model for `DX.dx` twice (env var unset / set to `1`) via
`parity_compare.build_native_model` against the cached trunk+golden: geometry counts and the full
`p_base` diff list are byte-identical between the two runs, all 13 diffs unchanged. Expected, once you
read what the flag actually does: `bsp_refresh_points_vectors` is a reachability GC (drop points no
surf/vert references) that preserves the SURVIVORS' existing relative pool order — it never reorders
anything, and its own code comment (`bspcsg.rs` ~L2869) already says the default path "already starts
this stage from an empty pool, so this call is a no-op there by construction" when there's nothing to
keep. `DX.dx` has zero count residual (nothing for the GC to drop), so the flag is a no-op on this
level by the same logic that makes it a partial win on Wanchai/UNATCO (which DO have a count gap) —
confirms this mechanism addresses pool SIZE, not ORDER, and structurally cannot touch this residual on
any level.

**No fix shipped, no code changed.** Closing this needs what §10.20 already said it needs: a live
capture of the real editor's Points pool CONTENT (not just counts) during the internal `bspRefresh`
reachability-DFS compaction, mid-build — existing live-gdb harnesses in the Wanchai thread
(`bspoptgeom_pool_trace.py` etc.) only capture pool COUNTS at checkpoints, not per-entry order/identity,
so a new capture would be required. Per the standing no-guessing rule, not attempted this round (real
new instrumentation, not a re-run of an already-built lever) — logged as open. `DX.dx`'s `surfs` residual
after today's `i_leaf` fix is `texture_ref`/`i_actor` (golden-actor-set artifact, `texture-ref-i-actor-
divergence-traced-to-golden`) + `p_base` (this entry) — nodes/leaves (mod `i_permeating`) stay exact.

## The `Camera6`-`Camera11` leak: REFUTED as a `LIGHT APPLY`/`GetVisibleSurfs` mechanism — a live no-light control build carries the identical 6 exports

Follow-up on the standing "leaked `GetVisibleSurfs` temp visibility camera" hypothesis
(`texture-ref-i-actor-divergence-traced-to-golden`, `native-light-apply-bake-where-it-stands-and` "Two
smaller leads"): every self-built golden carries 6 `Camera6`-`Camera11` exports, previously attributed
to `URender::GetVisibleSurfs`'s six 90°-apart cube-map faces spawning/reusing temp viewport `Camera`
actors during `LIGHT APPLY` and never being cleaned up before `MAP SAVE`. That attribution was never
live-verified — this round settles it.

**Count/naming is invariant across radically different actor populations — first sign the mechanism
isn't light- or paste-content-dependent.** Parsed every cached/widened `DX.dx`/NYC Bar/UNATCO golden
export table (`pkg_write.parse_package`): 9 builds spanning 5-195 real `Light`-class exports and
33-2974 total exports, across three different actor-set filters (narrow brush+light-only, widened
all-non-mover, `ALL` incl. movers) and two independent re-builds of the same UNATCO config — **every
one carries exactly 6 `Camera` exports, named exactly `Camera6`-`Camera11`, byte-identical strings, no
exceptions.** If this were "one temp camera leaks per light" or scaled with actor-paste population,
the count and/or the numeric suffix would move across a 5-to-195-light, 33-to-2974-export span. It
never does.

**Decisive test: a live `--no-light` control build (`build_ued_lit_golden.py` already ships this flag
for exactly this purpose) on `DX.dx`'s trunk — `MAP NEW` → `EDIT PASTE` (all 37 actors) → `MAP REBUILD`
→ `MAP SAVE`, `LIGHT APPLY` never called.** Built live this round (worktree
`camera-leak-investigation`, trunk `_scratch/geo-confirm-dx/maps/dx` — this trunk predates
class-name qualification and needed a throwaway in-memory `ClassIndex.qualify_and_validate` patch
before `gather_lights` would run on it, unrelated to this finding). Result, parsed the same way:
**57 exports, `Camera` count = 6, names `Camera6`-`Camera11` — identical to every LIGHT-APPLY'd
golden.** `LIGHT APPLY` never ran in this build. The leak is not downstream of it.

**Conclusion: the hypothesis is REFUTED.** The 6 stray `Camera` exports are not a `GetVisibleSurfs`
artifact and do not belong to `LIGHT APPLY` at all — they are already present after nothing more than
`MAP NEW`/`EDIT PASTE`/`MAP REBUILD`, i.e. an editor-session/viewport artifact of driving UnrealEd at
all, independent of lighting. This matches two pieces of evidence that were already on record but not
previously cross-referenced against the `GetVisibleSurfs` theory:
- `sections/31-package-wrapper-parity.md` (spike 2026-07-15/07-18, `Test_Castle.dx` — a golden built
  the OLDER unlit way, no `LIGHT APPLY` anywhere in that spike's pipeline either) already documented
  "6 `Camera` viewport actors... serialized from UnrealEd's viewport/browser session" as
  editor-session-global state with **no theory attached to `GetVisibleSurfs`** — filed alongside the
  session-global FName pool order and the session-global UObject numbering as fundamentally
  unreproducible-from-the-trunk state, not as an algorithm output.
- `dev/docs/unrealed/package-format.md` ("The `Actors` array is the authority...", 2026-07-27, 88
  retail Deus Ex maps measured against UnrealEd's own `UCC batchexport`): **every single retail map
  carries exactly 4 viewport `Camera` actors on its roster**, universally, that the exporter omits —
  an independent, much larger-sample confirmation that UnrealEd always saves some fixed small number
  of its own UI viewport cameras into any map it saves, unrelated to that map's content, lighting, or
  how it was built.

**Why our self-built goldens show 6 and retail shows 4: not resolved this round, and not this round's
question.** The most likely explanation is that this pipeline's headless `wine_ctl`/Xvfb/fluxbox
automation session ends up with a different number of live viewport windows open at `MAP SAVE` time
than a real interactive 4-pane artist session — a headless-automation/session-setup detail, not a
lighting or geometry algorithm. Not chased further (out of this round's scope: the question asked was
specifically whether this is a `LIGHT APPLY` mechanism, and it is not).

**Answer to the round's mandate: native's lighting bake should NOT replicate this.** `visible_surfs.rs`
(`uedcli-native/src/`) already has zero concept of spawning actors or viewports — it is a purely
geometric/mathematical port (a `Face` struct, in-memory span buffers) with no architectural hook for
"emit N stray exports," and confirmed above, there is no real editor `LIGHT APPLY` algorithm fact to
port here regardless. Adding 6 fake `Camera` exports to native's output would not be replicating a
`LIGHT APPLY` quirk (there is none to replicate) — it would be inventing content to chase a
superficial byte count, exactly the "guess and fudge" move the standing rule forbids. This is the same
category of gap `materialize-verify-qualify-level-textures` already flagged for the verify path
("Retail maps DO normally ship viewport cameras... the verify should treat them as an editor artifact
... not a mismatch") — a package-wrapper/session-state gap to be EXCLUDED from comparison at the
tooling layer (same treatment as timestamps/GUIDs/name-table order, `sections/31`), not something for
`level materialize`'s content to reproduce.

**No fix shipped, none should be.** No production code changed (`uedcli-native/src/*`, `unbuilt.py`,
`assemble.py` all untouched). The `--no-light` build lives at
`/tmp/camera-leak-investigation/dx_nolight.dx`; the qualify-patched driver script at
`/tmp/camera-leak-investigation/build_ued_lit_golden_qualify.py` (throwaway, not committed — its only
change from `build_ued_lit_golden.py` is the in-memory `ClassIndex.qualify_and_validate` call needed
because `_scratch/geo-confirm-dx`'s trunk predates class qualification). Worktree
`camera-leak-investigation` left in place uncommitted for the coordinating session to inspect; no
docker containers left running (`stop_editor`'s `finally` ran cleanly).

## Round 7 (2026-08-31): Camera-artifact export exclusion implemented and shipped in `parity_report.py` -- correct, TDD'd, but MEASURED ZERO effect on `texture_ref`/`i_actor` across all 3 tracked levels

Mandate: round 6 confirmed the golden's 6 `Camera6`-`Camera11` exports are a pure editor-session
artifact, not `LIGHT APPLY` content. Following the `sections/31-package-wrapper-parity.md` precedent
(GUIDs/timestamps/name-table order are excluded from comparison the same way), implement the
exclusion in `parity_report.py`'s content comparison and measure whether it closes any of the
`texture_ref`/`i_actor` divergence chased across rounds 1-6.

**Where the 6 Camera exports land, confirmed live on all 3 tracked goldens (`pkg_write.parse_package`
export-table dump) -- NOT a fixed position, contrary to the initial assumption.** `DX.dx` (33
exports): contiguous, indices 18-23 (0-based), sandwiched between the world model's own `Polys` and a
tail run of per-brush `Model`s -- but this is because `DX.dx` is small enough that every other export
lands before them. NYC Bar (683 exports) and UNATCO (2409 exports): scattered/interspersed among
per-brush `Model`/`Polys` pairs -- NYC Bar `[263, 264, 268, 271, 272, 275]`, UNATCO
`[911, 912, 913, 915, 916, 917]`. So the exclusion cannot assume contiguity or a fixed offset; it has
to walk the whole export-class table and renumber generically.

**Implementation (`dev/docs/spikes/2026-08-31-native-parity-report/harness/`).** `parity_lib.py` gained
`CAMERA_ARTIFACT_EXPORT_CLASS`, `export_renumber_map(export_classes)` (0-based golden export index ->
its index in an artifact-stripped table, `None` for a stripped artifact), `renumber_actor_ref(ref,
mapping)` (renumbers a positive 1-based export ref, raises `ValueError` if it targets a stripped
artifact, passes `ref <= 0` through untouched -- `texture_ref` is always a negative IMPORT ref per its
own field comment and is never in this mapping's domain), and `renumber_surf_actor_refs(surfs,
mapping)`. `parity_compare.py` gained `golden_export_classes(golden_path)` (a cheap header/table-only
reparse) and wires the three into `compare_content`: the golden's surfs have `i_actor` renumbered
through the artifact-stripped mapping before the index-for-index `compare_array_content` call.
`texture_ref` is untouched by design. TDD: `test_parity_lib.py` gained 7 tests, including the exact
scenario the mandate asked for -- a synthetic export table with 6 Camera artifacts interspersed (not
contiguous) among real `Brush` exports, asserting the OLD raw-index comparison false-positives on the
two surfaces whose owning brush sits after an artifact, and the NEW renumbered comparison finds zero
diffs.

**Measured before/after on all 3 tracked levels (self-built cached goldens, native's own fresh lit
build each time, worktree `camera-export-exclusion` to avoid the main-checkout docker-mount bug) --
ZERO change on every metric:**

| level | surfs fields_differ (before/after) | `i_actor` diffs (before/after) | `texture_ref` diffs (before/after) | geometry/lighting |
|---|---:|---:|---:|---|
| `DX.dx` | 65 / 65 | 26 / 26 | 26 / 26 | unchanged |
| `02_NYC_Bar` | 2739 / 2739 | 953 / 953 | 862 / 862 | unchanged |
| `03_NYC_UNATCOHQ` | 10940 / 10940 | 3616 / 3616 | 3615 / 3615 | unchanged |

Every individual diff's reported golden VALUE is also byte-identical before/after (checked, not just
the count) -- the renumbering genuinely runs (unit-tested and confirmed active), it just never changes
anything on these 3 levels' real data.

**Root cause of the zero effect, confirmed by direct inspection: on all 3 levels, the maximum golden
`i_actor` value referenced by ANY surf never exceeds the position immediately before the first Camera
artifact.** UNATCO: max real `i_actor` across all 3616 surfs is 911 (export index 910); the first
Camera sits at export index 911 -- one past the last real reference, zero overlap. NYC Bar: same
shape (max real ref 264; first Camera at 263). `DX.dx`: Cameras sit at the very tail (18-23), after
all 12 real content exports. In other words, the artifact is inserted at a session checkpoint that
consistently comes AFTER the last world-CSG brush actor any surf could reference, on every level tried
-- so even though the Cameras are numerically interspersed among the FULL export table (contrary to
the initial "always contiguous at the end" guess), they never fall between the golden's own real
surf-owning-brush positions where a shift would actually change anything.

**Conclusion: the exclusion is real, correctly implemented, precedent-following, and shipped -- but
it is not, and structurally cannot be, the fix for the `texture_ref`/`i_actor` divergence this thread
has chased across 6 rounds.** This confirms and sharpens round 2's finding ("the leaked Camera exports
persist regardless of actor population... a structural mismatch no actor-set widening fixes"): the
real cause is what rounds 2-4 already isolated -- native's own export serializer places/names
per-brush `Model`/`Polys` objects in a fundamentally different order than the golden's editor-session
build (`Model_<brush>Polys` vs `Polys<N>`, `sections/31`'s already-documented "Object numbering...
fundamentally unreproducible" residual), which dominates the whole comparison and is untouched by
stripping 6 known-artifact exports from one end of a table whose ordering diverges throughout. This is
not "more architecturally invasive than expected" in the sense of the renumbering itself being hard --
the renumbering mechanism is simple and works exactly as designed -- it is that the artifact this round
targeted was never the actual source of the measured divergence on these levels.

**Residual, unaffected by this round, as expected (task's own item 6):** no level reaches geometry
content-exactness -- `DX.dx` nodes stay exact (prior fix), leaves carry the pre-existing
`i_permeating` stub gap (5/5), surfs carry `texture_ref`/`i_actor` (both an IMPORT/EXPORT-order
mismatch, not this round's target) and `p_base` (13/26, the separately-tracked §10.20 Points-reorder
residual). NYC Bar/UNATCO add their own pre-existing `p_base`/points-count residuals plus (newly
visible in this round's per-field breakdown, not previously called out by name) small
`v_normal`/`v_texture_u`/`v_texture_v` diff counts -- not chased, out of scope. No level reaches FULL
PARITY. `regression_gate.py`: `GATE: PASS`, UNATCO/Wanchai unchanged (+5/+16/+0 and +74/+16/-8, same
as every prior round). Scoped check only this round (owner said not to run the full suite this
session): `test_parity_lib.py`'s 46 tests (7 new) pass in the worktree's own isolated venv, unaffected
by an unrelated shared-venv `PIL`/DXT-codec flake hit mid-round from a concurrent session's
`bin/test` sharing the main checkout's live `.venv` -- confirmed not caused by this change (same
`test_utexture_blocks.py` passes clean both via the main checkout's venv directly and via the
worktree's own fresh, isolated venv). Full `bin/test` (pytest + `cargo test`) NOT run this round --
left for the coordinating session before it commits. Only
`dev/docs/spikes/2026-08-31-native-parity-report/harness/*` changed, no `uedcli-native/src/` or
`uedcli/` production code touched.

**Shipped (uncommitted, worktree `camera-export-exclusion`).** The fix stays in even though it didn't
move these 3 levels' numbers: it removes a real, confirmed confound from the comparison methodology
(a golden built on a level where a real brush DOES land after the Camera-artifact position -- plausible
on some larger, differently-shaped level in the 21-level corpus not tested this round -- would have
silently false-positived without it), it is zero-risk (comparison-only, no production code, TDD'd), and
per the standing rule the mechanism itself is grounded in round 6's live verification, not a guess.

## Round 8 (2026-08-31): permeating light lists (`Model.Lights` region 1) -- `SplitWithPlaneFast` decoded live, closes most of the per-leaf content gap; still NOT wired into `light::bake`, still not byte-exact

Worktree `permeating-lights-fix`, task: `port-the-per-leaf-permeating-light-lists-model`'s two open
verify-before-porting items.

**(a) `FPortal.iFrontLeaf`/`iBackLeaf` orientation -- resolved by measurement, not a fresh gdb
capture.** No live `MakePortals` capture was done this round. Instead: `zones.rs`'s own DFS
visit-order fix (`a999b30`, already live-verified against `DX.dx`'s real on-disk `iLeaf` values)
turned out to ALSO be the dominant fix for the permeating port's content bug -- rebuilding
`permeating_lights.rs` unchanged against the now-current `zones.rs` moved UNATCO's per-leaf exact-run
match from the board item's stale 4/762 to 675/762 (88.6%), including the leaf-0 reference run
`[44,43,42,39,19,13,12]` matching exactly. A backward `iFrontLeaf`/`iBackLeaf` orientation would
invert the flood's `d<0` gate globally and collapse the flood to near-nothing, not produce an
88%-correct result with a narrow, structured residual -- so the existing `a`=front/`b`=back
convention is trusted on this evidence. Flagged as weaker than a live capture would be; not attempted
further this round.

**(b) `FPoly::SplitWithPlaneFast` -- decoded by static disassembly, RESOLVED.** Found in `Engine.dll`
(not `Editor.dll` -- it's an import) via its mangled export
`?SplitWithPlaneFast@FPoly@@QBEHVFPlane@@PAV1@1@Z` at RVA `0x151f90` (image base `0x10000000` ->
`0x10151f90`); disassembled with `pefile`+`capstone` per `unrealed/extracting-from-dll.md`'s method.
It is NOT a plain per-vertex clip: every vertex's signed plane distance is classified by sign
(`>= 0.0` exactly, ties go to "front"), but the function only calls the split decisive if some vertex
exceeds `+THRESH_SPLIT_POLY_WITH_PLANE` (a `.rdata` float constant, extracted directly from the
binary, RVA `0x206780` = `0.25`) AND some vertex is below `-0.25` (RVA `0x20b580`). Short of both,
it returns the WHOLE polygon unclipped (`SP_Front`) or rejects it WHOLESALE (`SP_Back`) --  never a
naive per-edge sliver. `permeating_lights.rs`'s `clip_beam` was doing exactly that naive sliver clip;
replaced with `split_with_plane_fast`, a faithful port of the decoded algorithm (see its doc comment
for the disassembly addresses). One branch (`SP_Coplanar`, neither flag set) has no known caller
behavior from this round's disassembly -- defaulted to "kept whole" (empirically no worse than
"reject" on this measurement: 35 vs 30 mismatches, but "reject" traded 0 missing for 3 new missing
entries, a different failure mode) and flagged as the one still-open item.

**Effect, measured on UNATCO (`03_NYC_UNATCOHQ.dx`) via
`spikes/2026-08-29-permeating-lights/harness/check_permeating.py`** (per-leaf light-name run,
resolved content, order+content compared against the self-built golden cached at
`_scratch/permeating-check-2026-08-29/golden.dx`):

| | leaves w/ exact run | mismatching leaves | mismatch shape |
|---|---:|---:|---|
| before (old `clip_beam`, wired) | 675/762 (88.6%) | 87 | 82 over-reach (extra lights only) + 5 under-reach (`Light127` missing everywhere) |
| after (`split_with_plane_fast`) | 727/762 (95.4%) | 35 | 35 over-reach (extra lights only); the 5-leaf under-reach case fully fixed as a side effect |

Remaining 35 mismatches are still 100% one-directional (native has extra lights, never missing,
never reordered) -- consistent with a residual clip/qualification imprecision, not an orientation
bug. Not further isolated this round.

**`parity_report.py`, before (old `clip_beam`, wired) / after (fixed), all figures unchanged unless
noted -- geometry and Lighting (`LightMap`/shadow-bit) are UNCHANGED by this fix on all 3 levels (it
only writes `Model.Lights` region 1 + leaf `i_permeating`, which neither section reads):**

- **DX.dx** -- geometry ✅ EXACT (26/26/5/250/32/6, d=+0 all), content ❌ NOT EXACT (pre-existing
  `texture_ref`/`i_actor` export-order residual, `p_base`/points untouched by this round; leaves
  content identical both before/after -- level has no permeating lights to speak of), lighting ✅
  FULL 100% (26/26 records, 1536/1536 shadow bits) both before/after. `FULL PARITY: NO` (content),
  unchanged.
- **UNATCO (`03_NYC_UNATCOHQ.dx`)** -- geometry ❌ NOT EXACT (verts d=+5, points d=+16, pre-existing,
  unchanged), content ❌ NOT EXACT: leaves' raw `i_permeating` POINTER differs at 734/762 indices
  BOTH before and after -- unchanged at the byte level, because the fix leaves 35 (down from 87)
  leaves with wrong CONTENT, and even one wrong leaf ahead of the tail cascades a pointer-offset
  mismatch onto every later leaf's `i_permeating` value; the byte-exact metric only moves once ALL
  upstream leaves are exact. Lighting 83.6% (2797/3345 records), 99.27% shadow bits, unchanged.
  `FULL PARITY: NO`, unchanged at the byte-comparison level despite the real semantic-content
  improvement above.
- **NYC Bar (`02_NYC_Bar.dx`)** -- geometry ✅ EXACT (1620/953/283/20878/2762/138, d=+0 all), content
  ❌ NOT EXACT: leaves' raw `i_permeating` differs at 230/283 before, 206/283 after (same cascade
  caveat as UNATCO, but this level's residual leaf-content mismatches happen to shift the count
  slightly). Lighting 87.7% (821/936 records), 99.76% shadow bits, unchanged. `FULL PARITY: NO`,
  unchanged.

**No level moved to FULL PARITY this round.** The fix is real and substantially closes the semantic
per-leaf-content gap (measured directly), but the BYTE-level `i_permeating` index comparison --
which is what full parity actually requires -- stays gated on reaching ZERO wrong-content leaves,
not "mostly right"; a single remaining wrong leaf anywhere before the tail cascades to the whole rest
of the array. `regression_gate.py` not re-run this round (scope: `cargo test --quiet` in
`uedcli-native/`, 95/95 pass, no regression vs the 89 pre-existing; full `bin/test` intentionally
NOT run per this session's standing instruction -- left for the coordinating session).

**Shipped: `uedcli-native/src/permeating_lights.rs` only** (new `split_with_plane_fast`, 3 new unit
tests pinning the decoded epsilon behavior against a naive clip). The dispatched agent also wired
`write_permeating_region` into `light::bake` (`uedcli-native/src/light.rs`); the coordinating session
reverted that part before committing. The owner's original call to leave it unwired (commit `8d7fe30`,
"shipping wrong-but-plausible light lists is worse than the current honest `iPermeating = -1` gap")
still holds -- 95.4% is real progress but still wrong-but-plausible, and this round's own measurement
shows wiring it moves ZERO levels' byte-level parity. Flipping that call needs the owner's explicit
yes (asked separately, not assumed). Scoped `bin/test -k permeating` (740 pytest + 95 cargo tests)
re-verified clean after the revert.

## `texture_ref`/`i_actor` round 8 (2026-08-31): the editor's `Polys<N>` counter IS deterministic — and irrelevant. `i_actor` divergence was 100% a measurement artifact; semantic-identity comparison shipped

Mandate: decide, on live evidence, whether the editor's `Polys<N>` auto-name counter is derivable
from the trunk (fix it in native) or session state (exclude it from comparison), and re-measure
`texture_ref`/`i_actor` on `DX.dx`/`02_NYC_Bar`/`03_NYC_UNATCOHQ`.

### 1. Two independent builds of the same trunk produce BYTE-IDENTICAL name/import/export tables

`build_ued_lit_golden.py` starts a fresh `uuid7()`-named editor container per run, so two runs are
two separate editor processes. Round 2 left exactly that pair on disk for UNATCO
(`/tmp/uedcli-widen-test/unatco_widened.dx`, 15:46, and `unatco_widened_run2.dx`, 15:54 — same trunk,
same actor filter, distinct GUIDs, so genuinely two saves). Reparsed both with
`pkg_write.parse_package`:

| | run 1 | run 2 | equal? |
|---|---:|---:|---|
| names (count and ORDER) | 3357 | 3357 | ✅ identical |
| imports (all fields) | 289 | 289 | ✅ identical |
| exports (all fields, incl. `soff`) | 2890 | 2890 | ✅ identical |
| `Polys<N>` names, in order | 736 | 736 | ✅ identical |
| GUID | — | — | ❌ differs (expected) |

Every one of the 736 `Polys` numbers is the same in both builds, as is every export row's serial
offset.

The two files are not byte-identical, though — 1603 of 2533794 bytes differ, and they fall in exactly
three places, none of them a table:

- 16 bytes at offset 36: the package GUID (already excluded).
- 4 bytes at body offset 10-13 of **933 of the 1416 `RF_HasStack` exports** (every actor), and of only
  1 of the 1474 non-`RF_HasStack` exports. Each actor body opens `90 90 ff ff ff ff ff ff ff ff` then
  4 bytes that look like a heap pointer and change every run (`14 00 01 00` vs `e0 79 46 0d`). Read
  against UE1's `FStateFrame::Serialize` layout (`Node`, `StateNode`, `ProbeMask` as a QWORD,
  `LatentAction` as an INT) that is `LatentAction`, serialized uninitialized. Layout-inferred, NOT
  disassembly-confirmed. The 483 `RF_HasStack` exports that happen to match are consistent with
  garbage that sometimes collides.
- 2 bytes inside `MyLevel`: a float32 `102.62` vs `102.57`, an elapsed-time field.

The world BSP `Model2` (1.65 MB) is byte-identical, which is what round 2's "two independent builds
are 100% byte-identical across nodes/surfs/leaves" actually measured.

**This is a hard ceiling on the full-byte-parity goal and is new** — the real editor cannot reproduce
its own output byte-for-byte, so neither can native. Filed as
`board/inbox/actor-state-frame-latentaction-is-serialized/`.

**So `sections/31-package-wrapper-parity.md`'s categorization is right but its stated reason is
wrong.** Object numbering and name-table order are NOT run-to-run unstable "session-global state" —
they are perfectly reproducible for a fixed pipeline. What they are is **not derivable from the
trunk**: they are a function of the editor process's own object-allocation history across
`OBJ LOAD` → `MAP NEW` → `EDIT PASTE` → `MAP REBUILD` → `LIGHT APPLY`. Native would have to emulate
UnrealEd's `UObject` allocator to reproduce them. The practical verdict (exclude, don't chase) is
unchanged; the doc's justification should be, if the owner wants it corrected.

### 2. The counting rule, as far as it goes

Same three goldens, `Polys` exports in numeric order:

| level | world brushes | per-brush run | extras |
|---|---:|---|---|
| `DX.dx` | 5 | `Polys6,8,10,12,14` | `Polys15` (the world `Model2`'s own `Polys`) |
| `02_NYC_Bar` | 202 | `Polys6 … Polys408` (+2) | `Polys4`, `Polys410`, `Polys411` |
| `03_NYC_UNATCOHQ` (movers excluded) | 733 | `Polys6 … Polys1470` (+2) | `Polys4`, `Polys1472`, `Polys1473` |
| `03_NYC_UNATCOHQ` (`--keep-classes ALL`) | 733 + 28 movers | `Polys6 … Polys1526` (+2) | `Polys4`, `Polys1528`, `Polys1529` |

`Polys4` (9 bytes, empty) is the builder brush's shape polys, paired with the `Model` export named
plainly `Brush`; the world BSP `Model` is auto-named `Model2` on every level. Movers get per-brush
`Polys` in the same +2 run as world brushes. The run is contiguous in NUMBER but not in export
POSITION — on `DX.dx` the 5th brush's `Polys14` and the world's `Polys15` sit at export indices 16
and 21, in the middle of the pasted actors, while the other four sit in a tail block. That is
because the export table is written in `UObject` allocation-slot order (freed slots reused), not in
paste order: the `DX.dx` golden's actor export order (`Brush8, Brush3, Brush9, Light5, Brush5,
Brush4, Light3, Light2, Light1, Light0, …`) matches neither the trunk order nor
`levelinfo_first_order`'s paste order.

### 3. Renaming was never the lever — `i_actor` is positional, and it was already semantically correct

Round 3 predicted this and it is now measured. `BspSurf.texture_ref`/`i_actor` are raw POSITIONS in
each package's own import/export table. Resolving each side's refs to the referenced object's full
dotted path (each through its OWN table) and comparing THOSE:

| level | `i_actor` raw-index diffs | `i_actor` resolved-identity diffs | `texture_ref` raw | `texture_ref` resolved |
|---|---:|---:|---:|---:|
| `DX.dx` (26 surfs) | 26 | **0** | 26 | 26 |
| `02_NYC_Bar` (953) | 953 | **0** | 862 | **139** |
| `03_NYC_UNATCOHQ` (3616) | 3616 | **0** | 3615 | **0** |

Native's surf→owning-brush assignment is 100% correct on all three levels, and its surf→texture
assignment is 100% correct on UNATCO. The entire `i_actor` "divergence" tracked since the 2026-08-31
"MAJOR CORRECTION" was the export-table ordering difference, i.e. a measurement artifact. No native
change would have improved it, and a `Polys` rename would have changed nothing at all.

These are the CACHED goldens `parity_report.py` uses — `DX.dx`'s is still the narrow 13-actor one
from round 1. Resolved identity is 0 anyway, which retroactively settles round 1's and round 2's
question too: the golden's actor POPULATION never mattered to `i_actor` either. Only the raw index
was ever sensitive to it.

### 4. The two surviving `texture_ref` residuals are BOTH about texture resolution, and only one is native's fault

- **`DX.dx`, 26/26 surfs — a real native bug.** Native emits the import `DeusExItems.BlackMaskTex`;
  the editor (and the original shipped `DX.dx`) emit `DeusExItems.Skins.BlackMaskTex`. Confirmed
  cause: `BlackMaskTex` is an `Engine.Texture` export inside `DeusExItems.u` under group `Skins`, and
  `pkgref.build_texture_group_index` globs `*.utx` only — it never scans code packages (`*.u`), so
  `object_ref` cannot re-attach the group the trunk's 2-part `Texture=DeusExItems.BlackMaskTex`
  dropped. This ships a wrong import path in real `level materialize` output, the exact failure
  `build_texture_group_index`'s own docstring warns about ("Can't find Texture in file"). Not fixed
  this round (out of mandate, and widening the glob to `*.u` needs its own perf/regression check) —
  filed as `board/inbox/texture-group-index-misses-textures-inside-u/`.
- **`02_NYC_Bar`, 139/953 surfs — a GOLDEN-side artifact; native is the correct side.** e.g. native
  `NewYorkCity.Metal.trough1` vs golden `NYCBar.Metal.trough1`. The trunk says
  `Texture=NewYorkCity.trough1` and the ORIGINAL shipped `02_NYC_Bar.dx` imports
  `NewYorkCity.Metal.trough1` — native is faithful. `trough1` exists in BOTH `NewYorkCity.utx` and
  `NYCBar.utx` (both in group `Metal`), both packages were `OBJ LOAD`ed, and the editor's T3D-paste
  texture lookup picked the other one. One further surf has golden `texture_ref = 0` for native's
  `effects.water.drtywater_a` — `effects` is not in that build's `OBJ LOAD` set, so the editor left
  the surface untextured. Filed as
  `board/inbox/golden-edit-paste-resolves-ambiguous-texture-names/`.

### 5. Shipped (comparison tooling only; no production code touched)

`parity_lib.object_paths` / `resolve_object_ref` / `resolve_surf_refs` / `OBJECT_REF_NONE` /
`SURF_OBJECT_REF_FIELDS` (pure, TDD'd — 6 new tests in `test_parity_lib.py`, including a synthetic
"same content, different export order" case and a "genuinely different texture" case that must still
report), plus `parity_compare.object_paths`, wired into `compare_content` so both sides' surf
object-refs are resolved to identity before comparison.

Round 7's Camera-artifact renumbering (`export_renumber_map`/`renumber_actor_ref`/
`renumber_surf_actor_refs`/`CAMERA_ARTIFACT_EXPORT_CLASS`/`parity_compare.golden_export_classes`) is
strictly superseded — resolved identity is immune to ANY export-table difference, cameras included —
and was removed along with its 7 tests.

`parity_report.py`, before → after (`surfs` field-diff totals; nodes/leaves and all geometry/lighting
numbers unchanged):

| level | geometry | surfs fields_differ | `i_actor` | `texture_ref` | lighting |
|---|---|---|---|---|---|
| `DX.dx` | ✅ EXACT (all 6 counts d=+0) | 65 → **39** | 26 → **0** | 26 → 26 | ✅ 100% (26/26 records, 1536/1536 bits) |
| `02_NYC_Bar` | ✅ EXACT (all 6 counts d=+0) | 2739 → **1063** | 953 → **0** | 862 → **139** | ❌ 87.7% (821/936), 99.76% bits |
| `03_NYC_UNATCOHQ` | ❌ verts d=+5, points d=+16 | 10940 → **3709** | 3616 → **0** | 3615 → **0** | ❌ 83.6% (2797/3345), 99.27% bits |

**No level newly reaches content-exactness or FULL PARITY.** After removing the artifact, the surf
residual is entirely `p_base` (13 / 924 / 3709 diffs) — the §10.20 Points-order thread, unchanged —
and, on NYC Bar, the 139 texture-resolution diffs above. Leaves still differ on `i_permeating`
(native writes `-1`) and nodes on `i_vert_pool`/`plane`/`i_zone`, all pre-existing threads.

### 6. `texture-group-index-misses-textures-inside-u` — FIXED, DX.dx's `texture_ref` residual now 0

`pkgref.build_texture_group_index` scanned `*.utx` only. Widened to also scan `*.u` (code packages),
via a new `_scan_group_index(index, pkg_dirs, pattern, kinds)` helper called twice — `.utx` first
(unchanged loop), `.u` second, both `index.setdefault`-ing — so the `.u` pass can only fill NAMES
the `.utx` pass left unresolved, never displace one it already answered. This mirrors the item's own
"safest option" instruction: purely additive, no change to any name `.utx` already covered.

**Cost.** Real corpus (`dev/games/substrate-deusex/System/`, 38 `.u` files, 293 MB): full
read+parse via `pkg_write.parse_package` is 1.33 s. `build_texture_group_index` runs once per
`assemble_unbuilt` call (no memoization, unlike `build_class_package_index`'s `_CLASS_PKG_CACHE`),
so this is a one-time ~1.3 s addition per `level materialize` invocation — on top of the ~1.3 s
`build_class_package_index` already pays scanning the SAME `.u` files for the class→package index
(uncached across the two functions; not unified in this change — that would touch both functions'
call sites for a second-order win and was left out as beyond this item's scope). Not sharing the
parse means the total added cost is a full second scan, not zero, but it is small next to a
`MAP REBUILD`+`LIGHT APPLY` round-trip and was judged acceptable without further work.

**Collision safety.** `index.setdefault` plus the two-pass (`.utx` before `.u`) order guarantees a
`.utx` name is never overridden by a same-named `.u` export, regardless of `pkg_dirs` order — proven
by a fixture test (`test_pkgref.py::test_a_utx_group_wins_over_a_same_stem_name_in_a_u_file`) and by
`parity_report.py` returning byte-identical `texture_ref` diff LISTS (not just counts) on
`02_NYC_Bar` and `03_NYC_UNATCOHQ` before/after — zero resolutions changed anywhere except the
26 `DeusExItems.u`-sourced surfs on `DX.dx`. `.u`-vs-`.utx` scan ORDER within the widened function
was not otherwise pinned against the real editor (no ambiguous case existed in the corpus to test
against), consistent with the item's no-guessing instruction.

**Fixture note.** `pkgfixture.texture_package(group=...)` encodes a texture's group as an IMPORT;
real content (verified by parsing the shipped `DeusExItems.u`) encodes it as an EXPORT in the same
file, which is the only shape `build_texture_group_index`'s outer-chain walk follows (`while
outer > 0`). The import-shaped fixture is fine for `utexture.group_of_export`/`TextureResolver`
(`name_of_ref` handles both ref signs) but silently resolves to the EMPTY group through pkgref's
walk — so `test_pkgref.py` hand-builds packages with `pkg_write` primitives instead of reusing
`pkgfixture`, matching the real export-based shape. `pkgfixture.py` itself is untouched (shared by
several other test files; not this item's concern).

`parity_report.py`, before → after (unaffected numbers omitted; `02_NYC_Bar`/`03_NYC_UNATCOHQ`
`texture_ref` diff LISTS are byte-identical before/after, not just their counts):

| level | geometry | lighting | surfs `texture_ref` | surfs other fields | leaves | nodes |
|---|---|---|---|---|---|---|
| `DX.dx` | ✅ EXACT (all 6 counts d=+0) | ✅ 100% (26/26, 1536/1536 bits) | 26 → **0** | `p_base` 13 (unchanged) | `i_permeating` 5 (unchanged, pre-existing) | ✅ EXACT (unchanged) |
| `02_NYC_Bar` | ✅ EXACT (all 6 counts d=+0) | ❌ 87.7% (unchanged) | 139 (unchanged — the separate golden-side ambiguity, `golden-edit-paste-resolves-ambiguous-texture-names`) | unchanged | unchanged | unchanged |
| `03_NYC_UNATCOHQ` | ❌ verts d=+5, points d=+16 (unchanged) | ❌ 83.6% (unchanged) | 0 (unchanged) | unchanged | unchanged | unchanged |

`DX.dx`'s surfs residual is now `p_base` only (13/26, the §10.20 Points-order thread — untouched,
out of this item's scope) and leaves' pre-existing `i_permeating` (5/5, native writes `-1`, unrelated
to textures). Geometry and lighting were already exact/100% on `DX.dx` before this fix; `DX.dx` does
NOT reach FULL PARITY from this fix alone (the `p_base` residual remains), but its `texture_ref`
category is fully closed.

Verification used cached goldens/trunks (`/tmp/uedcli-parity-cache`, `_scratch/uedcli-parity-cache`)
already built by other sessions this run — no live editor was driven for this item. `uedcli_native`
in the verification venv was copied from the shared main checkout's already-built `.so` rather than
rebuilt in-worktree (containerized `cargo`/`maturin` builds were failing on `docker: ... resource
temporarily unavailable`, a host-level contention issue from concurrent sessions, not this change);
since the fix is Python-only (`pkgref.py`), the native extension's exact build provenance does not
bear on these numbers, but the coordinating session should re-verify with a clean native build before
relying on the geometry/lighting percentages as final.

## `node_flags` 0x40/0x80: live gdb capture blocked (docker/runc dead in this sandbox); static re-scan finds the block-copy site the prior round flagged as unconfirmed, and disproves its own "zero setter" claim

Follow-up to `node-flags-0x40-0x80-divergence-from-movers-no` (2026-08-31 Round, above), tasked to do
the live gdb verification its own "Left undone" section named. **Live capture was not achievable this
session — no container can start at all in this sandbox (📖 static findings only below, no 🔬).**

**Docker is dead here, confirmed thoroughly, not a Dockerfile issue.** `docker info` and `docker ps`
work (daemon reachable, `DOCKER_HOST=tcp://dind:2375`, rootless backend), but every `docker run`
fails at container-create: `docker run --rm debian:bookworm-slim true` and the OFFICIAL
`docker run --rm hello-world` (a zero-dependency sanity image) both fail identically —
`OCI runtime create failed ... runc did not terminate successfully: exit status 2` /
`failed to create shim task: ttrpc: closed`. `/sys/fs/cgroup` is mounted `ro`, no systemd
(`docker info`: "Running in rootless-mode without cgroups. Systemd is required..."). Reproduced
building `ued-x86-runtime` fresh (apt-get layer fails the same way) and via 3 separate retries with
pauses. This is an infra fault in the `dind` sidecar for this sandbox instance, not something fixable
from an agent session (no access to restart the daemon or its backend VM); the coordinating session
should retry in a fresh sandbox. Nothing below used the editor, gdb, or Wine.

**Corrects the prior round's static-scan claim: `bspAddNode` DOES write `NodeFlags` — the original
scan was scoped to Editor.dll's EXPORT TABLE and silently skipped this function because it isn't
exported.** `bspAddNode` (VA `0x10034e80`) is called ONLY indirectly: a raw byte scan for `E8 <rel32>`
resolving to `0x10034e80` anywhere in Editor.dll's `.text` (alignment-independent, catches every
direct call regardless of linear-disasm desync) found **zero** hits; a data-scan found exactly one
`.rdata` reference, at `0x100cf7f8`, which is slot `+0x224` of a ~172-entry function-pointer table at
`0x100cf5d4` (the same vtable `bspRepartition`/`bspBuild`/`bspRefresh` sit in — `[+0x1fc]` through
`[+0x210]` match the prior round's own offsets). Because it's reached only through this vtable slot,
the "disassemble every exported function" method the prior round (and the original `0x08` finding)
both used never looked inside it. Full disassembly (capstone, all ~1300 instructions of the function)
finds exactly one instruction touching struct offset `+0x37`: `mov byte ptr [esi+0x37], al` at VA
`0x100351c2`, where `al` is loaded 3 instructions earlier from `[ebp+0x14]` — the function's OWN 4th
argument (`NodeFlags`, matching the known call signature `Model, iParent, ENodePlace, NodeFlags,
EdPoly*` this project's other harnesses already use, e.g. `editor_tree_oracle.py`'s
`_GDB_SCRIPT`). It is a plain `mov` (full overwrite), not `or`/`and` — it cannot "preserve" whatever
was in that byte before the call.

**Traced the argument's real source: the only 2 external call sites into `bspAddNode` anywhere in
Editor.dll both push a HARDCODED CONSTANT, `0x20` — never a variable, never 0x40/0x80.** Scanned all
66,562 linearly-disassembled `.text` instructions for `call [reg + 0x224]` (the confirmed vtable
slot): exactly 2 external hits, `0x100317d9` and `0x10031bf6`. At both, the `NodeFlags` push
(2nd-from-top of the 5-arg block, matching the known stack layout) is a literal `push 0x20`, not a
register/memory read. `bspAddNode`'s own internal recursive self-calls (through the same vtable slot,
for the front/back-split continuation and the coplanar-chain append — both branches disassembled)
forward this SAME argument unchanged (`push dword ptr [ebp+0x14]`), never recomputing it. `0x20`
matches UE1's likely `NF_IsNew` (a transient "just built this pass" marker) — consistent with a
direct check: **bit `0x20` never appears in EITHER `unatco_widened.dx`'s or `unatco_all.dx`'s SAVED
`node_flags`** (checked all 6314 nodes both sides, `parity_compare.parse_dx_model` +
`uedcli_native`), i.e. something clears it before the map is saved. That clearing site was not
located this round (candidate: a `bspCleanup`/`bspOptimize`-style finalize pass, not yet found).

**Re-verified the prior round's diff numbers independently (own parse, not reused) and confirmed
index correspondence is exact — zero non-flags field differs anywhere in the 6314-node tree.**
Re-parsed both cached `/tmp/uedcli-widen-test/unatco_{widened,all}.dx` (still present, unchanged):
862/6314 `node_flags` diffs reproduced exactly (346×`0x40` + 218×`0x80` + 337×`0x08` + 34×`0x10`).
Checked every one of `i_front`/`i_back`/`i_plane`/`i_leaf`/`i_surf`/`i_vert_pool`/`i_zone`/
`i_collision_bound`/`i_render_bound`/`num_vertices`/`plane`/`zone_mask` at all 6314 positional
indices between the two builds: **0 differ**, anywhere — the divergence really is `node_flags`-only,
not a comparison-methodology artifact. Node index 0 (the tree ROOT) is itself one of the 564
`0x40`/`0x80` nodes (`0x00` movers-excluded → `0x40` movers-included) — the most structurally central
node in the whole tree carries this divergence, which argues against it being some obscure edge case.

**Headline finding: located the exact block-copy mechanism the prior round's own "Left undone"
section flagged as unconfirmed and unable-to-rule-out from single-instruction scanning.**
`bspRefresh` (VA `0x10036cd0`, vtbl `+0x200`, also unexported — same blind spot) contains an in-place
Nodes-array COMPACTION loop (VA `0x10036dff`–`0x10036e59`): for `esi = 0 .. Nodes.Num` (`Model+0x5c`,
the same field `nodesnum_watch.py` already confirmed), a parallel remap array marks removed nodes
with `-1` (skip, don't advance the kept-count `ecx`); every SURVIVING node is copied WHOLE — the
entire 0x40-byte `FBspNode` stride, as four 16-byte `movups` (SSE) copies covering byte ranges
`[0x00,0x10)`, `[0x10,0x20)`, `[0x20,0x30)`, `[0x30,0x40)` — from its OLD slot
(`Nodes.Data + esi*0x40`) to a NEW, compacted slot (`Nodes.Data + ecx*0x40`). The last of the four
copies, `movups xmmword ptr [ecx+0x30], xmm0` at VA `0x10036e44`, spans bytes `0x30`–`0x3F`,
covering `NodeFlags` at `+0x37` as a side effect of a 16-byte vector copy — exactly the class of
instruction a "+0x37 operand string" scan cannot see (its own operand is `+0x30`, not `+0x37`). This
loop runs once per `bspRefresh` call, i.e. up to ~209 times per `MAP REBUILD`
(`unatco-verts-points-residual-after-the-zone`'s per-call count).

**Reconciles cleanly with every prior LIVE finding that seemed to rule out any content change.**
`nodesnum_watch.py`/`node_content_before_after.py`/`wanchai_descendant_slots.py` (2026-08-30, all
🔬) sampled calls where `Nodes.Num` nets back to the EXACT pre-call baseline — i.e. calls where
nothing was ever marked `-1`, so this SAME compaction loop still runs but copies every node onto
ITSELF (`esi == ecx` throughout), byte-identical, indistinguishable from a no-op in a before/after
diff. Those findings were correct for the specific calls they sampled; they just never happened to
land on a call with a real hole to compact. The mechanism was never contradicted, only unexercised in
the sampled set.

**What this does and does not settle, against the 3 hypotheses this round was asked to distinguish.**
Confirms hypothesis 2's PREMISE — a real whole-struct block-copy mechanism exists in the editor's
build path, reachable from an unexported function two levels of static-scan blind spot deep (an
un-exported callee, then a copy whose own operand offset isn't the target byte's offset). It does
NOT confirm that this copy's SOURCE content is itself "real" engine state (a legitimate `0x40`/`0x80`
computed somewhere and then relocated down through 1+ compaction hops) versus stale/leftover content
from a now-defunct node's slot that a compaction copy propagated forward without anyone having
written it deliberately — both remain open. Two things this round could NOT locate, and both need
live tracing (blocked) or substantially more static call-graph work to close: (a) what clears
`NF_IsNew` (`0x20`) before save, and whether that same code touches `0x40`/`0x80`; (b) what marks the
remap array `-1` (the removal decision), and what the ORIGINAL source node (the one whose content
ends up relocated into a surviving `0x40`/`0x80` slot) had for `NodeFlags` before ITS OWN creation —
tracing that requires either a live watchpoint across a real movers-included build (the originally
planned method, blocked) or building a full call-graph/data-flow model of `bspBuild`'s recursive
split logic offline, not attempted this round (budget).

**Recommendation on `NODE_FLAGS_NOISE_MASK`: leave it as-is.** This round neither confirms a decoded
algorithm native could replicate nor closes off the noise hypothesis — it narrows WHERE the
remaining uncertainty lives (a real copy mechanism plus two still-unlocated writers) without
resolving it. Not confident enough to touch `parity_lib.py`; flagging for the coordinating session
per the task's own ground rules.

Static-analysis scripts (capstone+pefile, no editor/docker) committed at
`dev/docs/spikes/2026-08-31-node-flags-live-verify/harness/`: `disasm_bspaddnode.py` (full
`bspAddNode` disasm + `+0x37`-coverage scan), `find_calls_raw.py` (alignment-independent `E8` scan),
`find_vtbl224_sites.py` (whole-`.text` scan for the vtable-slot call), `disasm_bspbuild.py` (ruled out
`bspBuild` as a direct caller), `full_text_flags_scan.py` (whole-`.text` `+0x37`-coverage scan, noisy
— useful only restricted to BSP-related code ranges, not run that way this round). Work done in
worktree `.claude/worktrees/node-flags-live-verify` (branch `node-flags-live-verify`), left uncommitted
per this round's instructions; the offline diff/index-correspondence check used the main checkout's
already-built `uedcli_native` venv (`/workspace/uedcli/.venv`) against the still-cached
`/tmp/uedcli-widen-test/unatco_{widened,all}.dx` — no rebuild, no editor.

## Lighting record divergence: failure-mode breakdown (2026-08-31, no docker/live editor)

Sandbox docker/runc was still down this round (confirmed once, not retried further —
`sandbox-docker-runc-cannot-start-any-container`), so this is entirely offline against cached goldens
(`/tmp/uedcli-parity-cache/`, `_scratch/uedcli-parity-cache/<hash>/trunk`, both re-used read-only via
`parity_report.py`/`parity_compare.py` — a real cache hit, no re-extraction, no re-build). Task: NYC
Bar (87.7%, 821/936) and UNATCO (83.6%, 2797/3345) lighting-record divergence had never been broken
down past the aggregate percentage this session. Full writeup, board item
`lighting-bits-only-divergence-localizes-to`; summary here.

Confirmed the current numbers first (`parity_report.py --json`, matches the standing item exactly):
NYC Bar geometry is COUNT-exact (all 6 deltas `d=+0`); UNATCO carries the known verts+5/points+16.

**Split the aggregate into 3 mutually-exclusive buckets** (previously only union'd field counts
existed): `bits`-only (grid+run agree, shadow bits differ), `grid`-only (`Pan`/`UScale`/`VScale`
differ, bits+run agree), `run` differs. Both levels: `bits`-only and `grid`-only are each ~40-45% of
bad records, `run` a steady ~13%.

**`grid`-only bucket root cause, confirmed with new evidence: real Points/Vectors VALUE drift, even
where Points COUNT is exact.** The standing "Points residual" thread only ever tracked COUNT deltas
(UNATCO +16, Wanchai +16/+19) — NYC Bar's 0-delta geometry was assumed clean on this axis. A multiset
compare of `Model.Points` (native vs golden, both 2762 entries on NYC Bar) finds 54 native points (2%)
whose VALUE matches no golden point at all — e.g. native `(0.0, -311.9998779296875,
-255.99993896484375)` vs golden's `(0.0, -312.0, -256.0)`, tens of ULPs apart, not a rounding-mode
artifact. `Model.Vectors`: 47/138 (34%) similarly value-mismatched. UNATCO: 393/10768 points (3.6%),
on top of its already-known +16 count residual. Correlating each `grid`-only record's owning surf
(via `i_light_map` → node vert-pool ∪ `p_base`) against this divergent-point set: NYC Bar 32/49
(65.3%) touch a divergent point vs a 4.8% baseline on identical records (13.6x enrichment); UNATCO
148/196 (75.5%) vs 5.4% baseline (14x). This is a real causal link, not aggregate coincidence — the
bake's own grid math (`axis_grid` in `light.rs`) is unaffected; it faithfully reproduces whatever
`vmin`/`vmax` it's handed. No lighting-side fix is possible here. This is a NEW, narrower angle on the
already-4x-exhausted `wanchai-verts-points-residual-independently` thread (that thread tracked COUNT
only; this shows a genuine VALUE-level drift persists even at zero count delta) — not a reason to
reopen it without a fresh live-capture angle on the intermediate CSG split arithmetic.

**`bits`-only bucket (the largest, ~45% both levels): NOT diffuse precision noise.** Divergent-point
correlation here is weak (NYC Bar 16.0%, UNATCO 8.4%, barely above baseline) — a different mechanism.
Splitting each bad record's `LightBits` back into its per-light sub-planes (stored consecutively per
run) and XORing independently: 72% of NYC Bar's bad records (36/50) and 53% of UNATCO's (132/250) have
EXACTLY ONE light with any wrong bits — every OTHER light sharing that same surface/grid is
bit-perfect. Where more than one light is bad, it's still typically 1-2 of 4-9, not all slightly off.
This rules out diffuse per-lumel rounding noise (which would scatter evenly across every light on a
record) and explains the earlier "bits-only records average 2-3x more lights per surface" observation
as pure exposure (more lights = more chances one is the bad one), not noise scaling with ray count.
**The bad light is not random per-surface noise: specific light ACTORS recur as the bad one across
many different surfaces** — NYC Bar's `Light30` on 7 of only 50 bad records; UNATCO's `Light227` on
12 of 250. Checked the trunk T3D for a static distinguisher (class, `LightRadius`, cone/effect fields)
between recurring-bad and always-good co-located lights on NYC Bar — none found; all are plain
`Engine.Light`, ordinary radii. Whatever makes these lights special isn't in their declared
properties — likely a Location/geometry relationship only a live trace surfaces.

**Bottom line, no fix shipped, both leads need live capture:**
1. `grid`-only — why 54-393 Points/Vectors values drift by tens of ULPs even when total counts match
   (geometry-side CSG float accumulation, not the bake).
2. `bits`-only — why specific recurring lights (`Light30`, `Light227`, …) produce a wrong shadow trace
   on multiple surfaces while co-located lights on the same surfaces are correct. Needs a live gdb
   trace of `line_clear` for one of these now-concrete (surf, light) repros (e.g. `Light30` against
   any of its 7 bad NYC Bar surfaces), the same mechanism `line_clear_algorithm_check.py`/
   `linecheck_*.py` already use, pointed at a real repro instead of a generic sweep.

Neither of the two previously-"chased" leads (shadow-ray precision / `lumel_axes`'s determinant,
`MergeWith`'s span-buffer merge) is reopened by this — both are independently confirmed correct
elsewhere in the pipeline and are not the computation this finding implicates (the ray WALK itself,
not the determinant or the merge). `9827f07` (round-8 `line_clear` port) stands; 99.27%/99.76%
shadow-bit agreement is unchanged — this narrows what's left of that residual to specific,
reproducible pairs instead of "diffuse, chased+refuted".

No source changed (`uedcli-native/src/` untouched); this was pure characterization. Worktree
`.claude/worktrees/lighting-divergence-breakdown` (branch of the same name), left uncommitted per this
round's instructions. Board item: `lighting-bits-only-divergence-localizes-to`.

## `bits`-only bucket: real root cause found and FIXED -- not `line_clear`, a `row_padding` state-carry bug. NYC Bar shadow bits 99.76%->100.00%, UNATCO 99.27%->99.998% (2026-09-01, offline + live docker)

Traced the recurring-bad-light finding above (`Light30` on 7 NYC Bar surfaces) to ground. Docker was
back this round (confirmed via `docker run --rm hello-world`), so a live gdb trace was prepared
(`editor_tree_oracle.start_dbg_editor`/the `linecheck_*.py` breakpoint pattern), but turned out
unnecessary: an OFFLINE check settled it first, since `LIGHT APPLY` never rebuilds BSP so golden's own
saved tree/bits are ground truth for a replay, and the replay alone pinned an exact mechanism -- no
live capture needed to close this one.

**Step 1 -- ruled out `line_clear` itself.** New `light30_offline_check.py` (reuses
`line_clear_v2_algorithm_check.py`'s exact port of the shipped `linecheck.rs` v2 algorithm) replayed
every lumel of `Light30`'s participation against golden's own real BSP tree. First pass (no radius
gate) showed only 74% agreement -- alarming, but a repeat of round 7's own already-documented mistake
(`--radius-aware` was defined but never wired into that script): most of the "disagreement" was
`line_clear` being asked about lumels the real bake never queries at all (outside
`(LightRadius+1)*25` world radius). Re-run WITH the same `d.dot(&d) < wr2` gate `light.rs::bake_surf`
applies before ever calling `line_clear`: **4728/4728 in-range bits, 100.00% agreement.** `line_clear`
is bit-perfect for every real query this light makes. The `9827f07` port is not implicated.

**Step 2 -- confirmed the mismatch is real but lives entirely in PADDING bits.** `find_bad_light_records.py`
(new) rebuilds native's own lit `.dx` (`parity_compare.build_native_lit_dx`) and diffs each light's own
sub-plane against golden's, reproducing the standing finding exactly (`Light30` bad on records
23/26/28/38/40/91/867). `light30_geom_compare.py` (new) then compared native's vs golden's own
`p_base`/`v_normal`/`v_texture_u`/`v_texture_v` for those 7 records: 5/7 byte-identical on every input
(ruling out the separate, already-known Points/Vectors ULP-drift mechanism for those); the other 2
(records 38/40) DO carry real ULP-level vector drift, a second, independent, already-tracked
mechanism (the "`grid`-only" bucket's root cause from the entry above) -- not investigated further
here since it's the same open geometry-side question. Direct hex dump of the mismatching bytes on all
7 shows the SAME shape every time: native's tail byte(s) hold a repeating non-zero pattern where
golden's are `0x00` -- e.g. record 23 `native=f9f9f8` vs `golden=f9f900`, record 867 (33-row) native's
last several bytes repeat `e0` where golden is all `00`. The REAL lumel bits (index < `USize`) match
exactly on both sides in every case; only the bits beyond `USize` (the packer's own padding, per
`row_padding`, `a_row_is_packed_to_its_last_whole_byte`) differ.

**Step 3 -- decisive replay pinned the exact wrong state-carry.** `light.rs::bake_surf` declares `let
mut last_clear = false;` ONCE, before the whole `for v in 0..v_size` row loop, so the value
`row_padding` repeats into a byte's padding bits can carry forward from an earlier lumel query
arbitrarily far back -- across an intervening run of radius-culled (real, in-range-tested-false)
lumels, across a byte boundary, even across a ROW boundary -- as long as no ray runs in between to
refresh it. Reimplemented `bake_surf`'s row-packing loop three ways in Python against golden's own
stored geometry/tree (persist-for-the-whole-record = current code; reset-once-per-ROW;
reset-once-per-output-BYTE) and replayed each against the real recorded bytes for all 7 `Light30`
records: persist matches 0/7, reset-per-row matches 6/7 (fails record 91, whose row spans 2 bytes),
**reset-per-BYTE matches 7/7 exactly, byte for byte.** The real editor evidently keeps no state longer
than the one packed output byte it is currently filling.

**Fix shipped:** moved `let mut last_clear = false;` from before the `v` loop to the top of the `for
byte in 0..row_bytes` loop (`uedcli-native/src/light.rs`) -- one line moved, `row_padding` itself
untouched. New regression test `row_padding_carry_does_not_survive_a_byte_boundary`: an EMPTY model
(`line_clear` trivially returns CLEAR for any query -- isolates the packing bug from any occlusion
concern) with one 12-lumel-wide (`USize=12`, 2 bytes) surf and a light positioned so byte 0 (lumels
0-7) is fully in range and CLEAR, byte 1's real bits (8-11) are out of range, and 12-15 are true
padding; asserts the padding stays `0x00` rather than inheriting byte 0's stale CLEAR. Verified RED
against the pre-fix code (`0xf0`) and GREEN after. `cargo test --lib`: 96/96 (was 95/95 -- the one new
test), `cargo test --lib light::`: 13/13.

**Measured before/after** (`parity_report.py`, self-built goldens, cache-hit, no re-extraction):

| level | shadow bits (before -> after) | `LightMap` records byte-identical (before -> after) |
|---|---|---|
| NYC Bar (`02_NYC_Bar.dx`) | 420064/421088 (99.76%) -> **421088/421088 (100.00%)** | 821/936 (87.71%) -> **871/936 (93.06%)**, +50 |
| UNATCO (`03_NYC_UNATCOHQ.dx`) | 3729140/3756584 (99.27%) -> **3756504/3756584 (99.998%)**, 80 bits left | 2797/3345 (83.6%) -> **3042/3345 (90.94%)**, +245 |
| `DX.dx` | 1536/1536 (100%, unchanged) | 26/26 (100%, unchanged) -- no regression |

NYC Bar's shadow-bit gap is now fully closed. UNATCO has 80 wrong bits left (of 3.76M) -- not chased
further this round; likely a residual instance of the same ULP-drift geometry mechanism noted for
records 38/40 above, or a genuinely new tail worth a fresh offline sweep before assuming so. The
remaining NOT-byte-identical records on both levels are dominated by the `grid`-only bucket (real
Points/Vectors value drift, already tracked, exhausted 4+ rounds) and the small `run`-differs bucket
(the known `GetVisibleSurfs` gap) -- neither touched this round.

Work done in worktree `.claude/worktrees/lighting-light30-bits-trace` (branch of the same name), left
uncommitted per this round's instructions. New spike:
`dev/docs/spikes/2026-09-01-light30-bits-trace/harness/` (`light30_offline_check.py`,
`find_bad_light_records.py`, `light30_geom_compare.py`). Board items:
`lighting-bits-only-divergence-localizes-to`, `native-light-apply-bake-where-it-stands-and`.
## 2026-09-01: `grid`-only bucket's Points/Vectors VALUE drift — root mechanism found (numeric proof, not live gdb) and quantified: CSG_Add faces wrongly keep the AUTHORED (6-decimal-text) normal where the real editor recomputes it, contradicting the existing §92 §48 "Add keeps authored" rule

Task: live-trace the CSG split arithmetic behind the `grid`-only bucket's Points/Vectors value drift
(`lighting-bits-only-divergence-localizes-to`, "grid-only bucket" section) — 54-393 points/47-136
vectors per level whose VALUE matches no golden point/vector even though the total COUNT is exact.
Read first: `lighting-bits-only-divergence-localizes-to`, `wanchai-verts-points-residual-independently`
(all 4 rounds), `native-materialize-findings.md` §92 (`p_base`/`ShrinkModel`/`bspRefresh` sections).
Docker/live editor was up this round (confirmed via `docker run --rm hello-world`).

**Reproduced the starting point** (worktree `.claude/worktrees/lighting-points-value-drift`, fresh
`.venv`+`uedcli_native` build): NYC Bar, current tree — geometry COUNT-exact (all 6 metrics `d=+0`,
2758/2758 points), 58/2758 (2.1%) points and 47/142 (33%) vectors multiset-value-mismatched (new
harness `find_drifted_points.py`, committed alongside this round). Close to the board item's cited
54/2762 — small drift from a day of unrelated commits, not a different phenomenon.

**Traced ONE concrete point to its owning brush and reproduced native's exact drifted value by hand.**
`trace_drifted_point.py` (new, committed): native `points[204] = (0.0, -311.9998779296875,
-255.99993896484375)` is the `p_base` (only) of surf 251, owned by `Brush69` (`CsgOper=CSG_Add`, plain
integer `Location=(-384,-440,0)`/`PrePivot=(256,40,-8)`, no `Rotation`, no real `MainScale`/`PostScale`
sheer) — a sloped (1:2 ramp, authored `Normal=(0,0.894427,0.447214)`) face whose `p_base` is the
polygon's `Origin=(640,168,-264)` (local), NOT one of its 4 ring vertices. Hand-computed the exact
`bspcsg.rs` base-snap formula (`d = Normal·(Vertex[0]-Base); if |d|>1e-4: Base += Normal*d`, all f32,
`Vec3::dot`'s left-to-right reduction) using ONLY the T3D-authored integers/normal-text: **reproduces
native's stored value bit-for-bit** (`(0.0, -311.9998779296875, -255.99993896484375)`), no editor
needed — `d = 0.00012969970703125`, just 30% over the `1e-4` threshold, purely from the AUTHORED
normal text's rounding (`0.894427`/`0.447214`, 6 decimal places) being ~2e-7 off the true `2/√5`/`1/√5`.
Mathematically the Origin lies EXACTLY on the polygon plane (integer geometry, `d=0` with the true
normal) — the snap is spurious, triggered only by text-precision noise amplified by the ~130uu lever
arm between `Base` and `Vertex[0]`.

**Decisive: golden's stored normal for this exact surf is NEITHER the authored text NOR the
mathematically-true unit normal — it's a RECOMPUTED value, close (1-2 ULP) to `CalcNormal`-over-local-
winding.** `golden.vectors[44] = (0.0, 0.8944272994995117, 0.44721364974975586)`; `f32(0.894427) =
0.8944270014762878` (native's stored value, the authored text — exact match to native, confirming
native trusts the text); `f32(2/√5) = 0.8944271802902222` (the true value) — golden matches NEITHER.
Hand-reconstructing `CalcNormal` (triangle-fan cross-product accumulation, pivoted at `V0`, f32
throughout, `NormalizeSlow`'s f64-widened magnitude — the exact algorithm `fpoly.rs::calc_normal`
already implements, per §92 §16/§17) over the polygon's 4 local integer vertices gives `(0.0,
0.8944271802902222, 0.4472135901451111)` — within 1-2 ULP of golden's stored value, and nowhere near
the authored text. **This directly contradicts `bspcsg.rs`'s current CSG_Add branch** (`else` arm,
~line 2426: "UNSCALED CSG_Add... keeps its authored normal", gated by
`subtract_recomputes_slant_normal_while_add_keeps_authored`'s pinned test, built on §92 §48's
castle-bastion evidence that Add keeps authored and only Subtract recomputes).

**Not a one-off: checked all 47 NYC Bar + 136 UNATCO mismatched vectors' owning-surf `CsgOper`.** NYC
Bar: the large majority trace to `CSG_Add` faces whose native value is bit-exact to the authored T3D
text (`f32(0.707107)`, `f32(0.866026)`, `f32(0.894427)`, etc. — literal 6-decimal-text values).
**UNATCO (node-exact fixture, `_scratch/bsp-parity-proj/`): 265/265 (100%) of (vector,surf) pairs
touching a mismatched vector are `CSG_Add` — ZERO `CSG_Subtract`.** Exactly the pattern predicted if
native's Subtract-recompute is already correct (matching golden) but its Add-keeps-authored branch is
not — cross-level, 100%-consistent, not a single-brush coincidence.

**Measured a gated experiment: extend the existing §92 §48 winding-recompute to CSG_Add too.**
`UEDCLI_BSPCSG_ADD_RECOMPUTE_NORMAL` (new, off by default, `bspcsg.rs`) widens the recompute branch's
condition from `oper == Subtract` to `oper == Subtract || <flag>`, unchanged otherwise (same
`!is_unit_axis`/`rot_is_pure_rotation` guards, same code path Subtract already uses — no new
arithmetic, reuses the already-`§92`-decoded/tested `calc_normal`). Result, both node-exact levels,
counts vs golden unchanged (no structural regression):

| level | metric | default | `ADD_RECOMPUTE_NORMAL=1` |
|---|---|---:|---:|
| NYC Bar | nodes/surfs/leaves | EXACT (unchanged) | EXACT (unchanged) |
| NYC Bar | points value-mismatched | 58/2758 | **25/2758 (-57%)** |
| NYC Bar | vectors value-mismatched | 47/142 | **10/142 (-79%)** |
| UNATCO | nodes/surfs/leaves | 6314/3616/762 EXACT | 6314/3616/762 EXACT (unchanged) |
| UNATCO | verts delta | +5 | **+4** (slightly better) |
| UNATCO | points delta (count) | +16 | +16 (unchanged) |
| UNATCO | points value-mismatched | 393/10768 | **179/10768 (-54%)** |
| UNATCO | vectors value-mismatched | 136/599 | **21/599 (-85%)** |

`cargo test bspcsg` (scoped): 24/24 pass unchanged, env var unset by default — the pinned
`subtract_recomputes_slant_normal_while_add_keeps_authored` test is untouched (it never sets the flag).
The 25/179 (NYC Bar/UNATCO) points still mismatched WITH the flag on are now sub-ULP-to-few-ULP (0.000004
to 0.0014 nearest-golden distance, vs 1e-4-to-0.03 before) — a much smaller, separate residual matching
the already-documented §92 §52 "second `SafeNormalSlow` in `FPoly::Transform`" precision gap, not a new
open thread.

**Why NOT shipped to default.** This numerically falsifies §92 §48's "CSG_Add keeps authored normal"
premise on real, unmodified retail content (not synthetic) — but that premise is backed by a committed,
passing test built from CASTLE evidence (not live-reconfirmed this round), and my own evidence here is
exact-arithmetic reconstruction + golden-value matching, NOT a live capture of the real editor's
`FPoly::Finalize`/`CalcNormal` call for a CSG_Add brush. Per the standing no-guessing rule this is
strong enough to report and gate, not strong enough to flip a tested default without a live capture
(or the owner accepting this evidence in lieu of one) — a live gdb breakpoint on `CalcNormal`
(`Engine.dll 0x150510`) during `EDIT PASTE` of a CSG_Add brush (e.g. NYC Bar's `Brush69`) would settle
it directly and either fix `subtract_recomputes_slant_normal_while_add_keeps_authored`'s premise
(remove the `Subtract`-only gate) or explain what's actually different about the castle-bastion case
this evidence doesn't reproduce. Not attempted live this round — the numeric route above was
independently decisive and cheaper; live tracing is the natural next step if this is picked up again.

**Lighting-bucket impact not re-measured this round** (would need a fresh `lightparity_buckets.py` run
against a native build with the flag on — not done; the geometry-side improvement above is the
consolidated, load-bearing result). Given the earlier finding's own 13-14x enrichment of `grid`-only
records touching a divergent point, halving-to-quartering the divergent-point count is expected to
shrink the `grid`-only bucket materially, but this is a prediction, not a measurement.

New harnesses (committed, `dev/docs/spikes/2026-08-31-native-parity-report/harness/`):
`find_drifted_points.py` (multiset points/vectors value-mismatch dump for any trunk+golden pair),
`trace_drifted_point.py` (resolve a native Points[] index to its owning surf/brush actor). Code change:
`uedcli-native/src/bspcsg.rs` — `add_recompute_normal_enabled()` + the widened recompute-branch
condition (gated, off by default, zero effect on the default path — `cargo test bspcsg` 24/24 unchanged,
regression gate unrun full this round but the scoped counts above show no node/surf/leaf regression on
either node-exact level). Also tried and reverted (zero measured effect, see harness for the diagnostic):
`UEDCLI_BSPCSG_POINT_NEAREST` (`bsp_add_point`/`bsp_add_vector` FIRST-vs-NEAREST dedup, per spec.md §3.10
— confirmed byte-identical output on/off for NYC Bar, extending `pass-d-orphan-ivertex-stale-index-
parity`'s "red herring for pool SIZE" finding to VALUES too).

Worktree: `.claude/worktrees/lighting-points-value-drift` (branch of the same name), left uncommitted
per this round's instructions. Board items updated: `lighting-bits-only-divergence-localizes-to`,
`wanchai-verts-points-residual-independently`.

## `DX.dx`'s `p_base` residual: §10.20 hypothesis REFUTED for the simple case -- live gdb pins the exact rule (`Origin` then REVERSED ring vertices, per polygon, in authored order); NOT shipped (generalization to split polygons unverified)

Task: live-verify whether §10.20's "pre-compaction pool indices, not reconstructable from the final
model" hypothesis holds for `DX.dx`'s 13/26 `p_base` diffs (`texture-ref-i-actor-divergence-traced-to-
golden`, `native-materialize-findings.md` "`DX.dx`'s `p_base` reordering"). Worktree
`.claude/worktrees/dx-pbase-live-gdb`. Docker/live editor up throughout.

**Offline localization first (no editor).** `parity_report.py` on `DX.dx` (cache hit): still 13/26
`p_base` diffs, geometry EXACT, lighting 100%. Parsed the cached golden's `Model` directly
(`parity_compare.parse_dx_model`): all 13 diffs trace to `Brush3`/`Brush8`/`Brush9`/`Brush4` (plain
unsplit 6-face `CSG_Subtract` unit cubes), each contributing a 3-point rotation within its own 5-point
base sub-block (e.g. `Brush3`'s surfs 3-5: golden `p_base` = `{3,4,2}`, native = `{2,3,4}` — same set,
rotated). Reconstructing the golden's base-block order from the FINAL model alone (surf order, node
order, ring order, every combination tried) never reproduced this rotation — consistent with §10.20,
but not yet a live confirmation.

**Live capture 1 (`points_pool_refresh_trace.py`, new): every `bspRefresh` call's full `Model.Points`
array content, before and after, across a real `MAP REBUILD` of `DX.dx`'s trunk.** `bspRefresh` entry
VA (`0x10036cd0`) was already known from prior rounds; this round freshly disassembled its single true
exit (`0x1003718f`, `ret 8` — the OTHER `ret` in the same disassembly window, `0x10037251`, belongs to
a different function whose prologue starts immediately after `0x1003718f`, confirmed by inspecting the
bytes around it). Only **5 `bspRefresh` calls** fire for the whole `DX.dx` build (it is tiny). Decisive
finding: **every compaction call preserves the RELATIVE ORDER of surviving points — it never reorders,
only drops unreferenced ones and closes the gap.** Call 5's AFTER array (32 points) is BYTE-IDENTICAL,
index for index, to golden's real saved `Points` array. Call 5's BEFORE array (42 points) already has
`Brush3`'s 5 base points in the exact golden order `[A,E,H,G,F]` at raw positions `[0,1,2,3,4]`
(A/E/H/G/F = the 5 distinct authored polygon Origins of `Brush3`'s 6 faces). Tracing back further:
call 1's (the world-level, FIRST `bspRefresh`) BEFORE array (44 points) already has these same 5
values at raw positions `[0,4,5,6,7]`, and call 1's AFTER (19 points) already matches golden's real
`Points[0..18]` exactly. **So the reordering is not a `bspRefresh` artifact at all — it is baked in
before the world's very first `bspRefresh` call**, refuting the specific "it's a `bspRefresh`
reachability-DFS-compaction artifact" half of §10.20 (the DROP/close-gap behavior IS a `bspRefresh`
reachability GC, exactly as documented — but ORDER survives from earlier untouched).

**Live capture 2 (`bspaddpoint_call_trace.py`, new): every `bspAddPoint` call during the same
`MAP REBUILD`.** Resolved `bspAddPoint`'s VA (`0x10035430`) from the `UModel` vtable at
`0x100cf5d4+0x1f4` (the same vtable `bspRefresh`/`bspBuild`/`bspRepartition`/`bspAddNode` already sit
in — cross-checked by independently re-deriving `bspRefresh`'s own already-known VA from `+0x200` and
getting `0x10036cd0` back exactly). Signature confirmed live: `__thiscall bspAddPoint(Model* ecx,
FVector* [ebp+0xc], INT Exact [ebp+0x10])` — `[ebp+8]` is a REUSED scratch stack slot the function
later overwrites with a float, not the point argument (an early, wrong read of `[ebp+8]` as the
FVector produced all-zero coordinates for all 600 calls; `[ebp+0xc]` is the real argument. `ecx`, not
`[ebp+8]`, is the `Model` this-pointer, moved to `esi`). Captured the input `FVector` and `Exact` flag
at entry (`0x1003545d`, post-prologue) and the returned pool index (`eax`) at the function's `ret 0xc`
epilogue (`0x100354ce`; a second candidate `ret 0xc` at `0x100355a7` fired inconsistently — 168 times
against 600 real calls — and was excluded as unreliable/misidentified, not used).

**The exact per-polygon call sequence, decoded directly from the trace: `Origin` first (`Exact=1`),
then its 4 `Vertex` entries in REVERSE authored order (`Exact=0`), repeated per polygon in AUTHORED
polygon order.** `Brush3`'s poly0 (`Vertex` order A,B,C,D in the T3D): captured calls are
`Origin=A(exact=1) -> A,D,C,B(exact=0 each)` — vertices D,C,B,A, i.e. the T3D list REVERSED. Poly1
(`Vertex` order E,F,G,H): captured calls `Origin=E(exact=1) -> H,G,F,E(exact=0)` — again the exact
reverse of the authored E,F,G,H list. This is not guesswork — 600 calls across the whole build were
captured and this pattern holds at every polygon boundary (every 5th call has `Exact=1`, matching one
polygon's `Origin`).

**Decisive check: does the LAST `bspAddPoint` return value for each of `Brush3`'s 5 base points equal
its true FINAL saved `Points[]` index?** Grepped all hits for A/E/H/G/F's coordinates across the full
600-call trace (each value gets re-queried many times by later brushes/passes, since the pool is
global and every `Exact`/tolerance dedup call against an existing point returns its CURRENT index,
which can shift across a `bspRefresh` drop-and-later-readd cycle). Last hit per value: A -> idx 0
(golden real: 0), E -> idx 1 (real: 1), H -> idx 2 (real: 2), G -> idx 3 (real: 3), F -> idx 4 (real:
4). **5/5 exact matches.**

**Why the base-block LAYOUT (bases lead, rings trail) still holds despite `Origin`+reversed-`Vertex`
calls happening interleaved, same as §10.19/10.20 already established:** ring-only points (never any
polygon's `Origin` anywhere in the level) get inserted into the pool early too (as non-`Exact`
`Vertex` calls) but are NOT YET referenced by any node's vert-pool at the time of the FIRST
`bspRefresh` (node/vert-pool construction happens later, during `bspRepartition`'s subtree recursion)
— so the reachability GC drops them as orphans at that checkpoint, and they get freshly RE-ADDED to
the pool later once real BSP nodes reference them as ring vertices, landing far down in the final
array (confirmed directly: `Brush3`'s poly0 vertices D/C/B raw-pool-positioned at 1/2/3 in call 1's
BEFORE array are ABSENT from call 1's AFTER array, and reappear at golden's real indices 22-24 in the
final saved model). Base points (referenced by `surf.pBase` immediately, as soon as the surf exists)
survive every GC and keep their relative insertion order — which is why the base block's INTERNAL
order reflects the raw `Origin`+reversed-`Vertex` insertion sequence, including contributions from
vertex-only calls of an EARLIER polygon that happen to be a LATER polygon's `Origin` (exactly `Brush3`
poly1's reversed vertices H,G,F landing ahead of poly3/poly4's own `Origin` calls for G/F, which just
dedup back to the same indices).

**Cross-check against a second brush, `Brush8` (same cube shape, `Location=(1280,0,0)`, offline only —
T3D read, no new gdb needed): the SAME rule predicts golden's real surf 9/10/11 `p_base` = `{8,9,7}`
exactly, while the naive "origin-only, first-appearance" rule (what native's `reorder_points_canonical`
currently implements) predicts the WRONG rotation `{7,8,9}` — matching the actual native/golden diff on
those surfs precisely.** Not a `Brush3`-specific fluke.

**Conclusion: §10.20's hypothesis is REFUTED as stated for this class of case.** The order is not
"lost information reconstructable only from a live capture" — it is a fully mechanical, deterministic
function of (a) brush CSG-processing order (native already tracks this — `canon_surf_keys`), (b) each
polygon's AUTHORED `Vertex` list read `Origin`-first-then-REVERSED (native has this in the T3D), and
(c) a periodic (per-`bspRefresh`-call) reachability GC that can drop and later re-add a point,
which native's current single END-of-build `reorder_points_canonical` pass does not model (it walks
the FINAL surf/node structure once, which cannot reproduce a mid-build drop-then-readd's effect on
relative order).

**No fix shipped.** Full confidence in the mechanism above is confined to `DX.dx`'s specific case:
plain, UNSPLIT, whole-brush `CSG_Subtract` boxes, each polygon's authored `Vertex` list untouched by
CSG splitting. `UNATCO`/Wanchai's own residual `p_base` diffs (924/3709, still tracked, node/surf/leaf
EXACT) involve real polygon SPLITTING against existing world geometry during CSG — a split-generated
sub-polygon's own vertex order is NOT the T3D `Vertex` list (it's computed by `FPoly::SplitWithPlane`
at CSG time), so this exact reconstruction rule does not obviously extend there without further live
verification (not attempted this round — budget). Implementing "Origin-then-reversed-vertex insertion
order, replayed through the SAME periodic drop/readd choreography the real `bspRefresh` GC performs at
every one of its ~209/119 subtree calls on the bigger levels" is a real architectural change to
`reorder_points_canonical` (replacing one final canonical resort with an incremental, mid-build-aware
model), not a small patch — and shipping it blind on UNATCO/Wanchai risks the hard-won node/surf/leaf
EXACT status those two levels currently hold. Per the standing no-guessing rule, logged as a confirmed
mechanism + an open generalization question rather than shipped code.

New harnesses (committed, `dev/docs/spikes/2026-09-01-dx-pbase-points-trace/harness/`):
`points_pool_refresh_trace.py` (per-`bspRefresh`-call full `Points` array before/after dump — reusable
on any level small enough to dump the whole pool cheaply), `bspaddpoint_call_trace.py` (every
`bspAddPoint` call's input point + `Exact` flag + returned pool index — the new, decoded VA
`0x10035430` and its `[ebp+0xc]`/`[ebp+0x10]`/`ecx` argument layout are reusable for any future
CSG-insertion-order investigation). `DX.dx` remains at geometry EXACT / lighting 100% / `p_base` 13/26
unresolved — does NOT reach FULL PARITY this round. Worktree `.claude/worktrees/dx-pbase-live-gdb`,
left uncommitted per this round's instructions.

## Round 10: tried the gated, post-hoc version of the §10.20-REFUTED insertion-order rule — MEASURED, and it makes `p_base` WORSE on all 3 tracked levels; node/surf/leaf-EXACT survives unchanged; not shipped

Task: the prior round found the exact mechanism (`Origin` then reversed `Vertex` list, per polygon)
but explicitly punted on shipping it, since `reorder_points_canonical` (`bspcsg.rs`) is a single
post-hoc resort over the FINAL model, not an incremental replay, and the rule was only confirmed for
`DX.dx`'s unsplit boxes. Mandate: find a way to apply the rule SCOPED to provably-unsplit surfs only,
without risking `UNATCO`/Wanchai's split-polygon path — implement + measure if it looks safe, else
characterize the entanglement precisely.

**`PF_SPLIT_MARKER` (the one bit that looked like a reusable "was this split" signal) is a dead end —
confirmed by reading the code, not assumed.** `FPoly::empty_copy` (`fpoly.rs`) ORs it into every
fragment `split_with_plane`/`split_in_half` produce, but `bsp_brush_csg` (`bspcsg.rs` ~line 2546)
unconditionally clears it (`poly_flags &= 0x7fff_ffff`) on every poly entering LOOP 2's world filter,
for LOOP 2's own unrelated purpose (the WTB re-add gate, §1247). So by the time a poly reaches
`bsp_add_node`, the bit answers "was this fragment cut during THIS filter descent", not "was this
polygon ever split, anywhere in the pipeline" — using it for the latter would need a NEW, separate,
cross-cutting flag correctly OR-combined at every split/merge site (`split_with_plane`,
`split_in_half`, `bsp_merge_coplanars::union_group`, `bspRepartition`'s own `split_poly_list`, …),
which is real new architecture, not a small patch.

**Found a cheaper, data-only gate instead — no new flag threaded through the pipeline.** `canon_surf_keys`
(§10.19) already sorts `model.surfs` into `(i_actor, i_brush_poly)` CSG-processing order before
`reorder_points_canonical` runs, and `build_geometry_bspcsg`'s own `brushes: &[BrushInput]` parameter
(already in scope at the call site) holds every brush's original, AUTHORED, per-poly `Vertex` list.
So per surf, `unsplit_reversed_ring` (new, `bspcsg.rs`) can PROVE — from data already available, no
tracking added anywhere else — whether that surf's own final ring is its brush's untouched authored
polygon: exactly one owning node (no `iLink` sharing), the node's vertex COUNT matches the authored
polygon's count, and the ring's actual WORLD points match the authored polygon (transformed by the
same `rot`/`prepivot`/`location` `brush_loop1` applies) as a value set, within tolerance. Only when all
three hold does `reorder_points_canonical`'s bases-first loop push that surf's own ring (reversed)
right after its `p_base`, interleaved per-surf in canonical order — replicating the live-decoded call
shape. Every other surf falls through unchanged to the existing base-only push. Landed behind
`UEDCLI_BSPCSG_POINTS_ORIGIN_REVERSED` (off by default), TDD'd: two new `bspcsg.rs` unit tests pin the
gate firing on a hand-built unsplit ring (`Origin` then reversed ring, matching the live trace exactly)
and NOT firing when the ring's vertex count doesn't match the authored polygon (the split-fragment
proxy). `cargo test --lib bspcsg` 26/26, full crate `cargo test --quiet` 98/98, both pass with the
flag unset (default path byte-unchanged, confirmed — this alone required no live editor: pure
Rust + the cached goldens).

**Measured on all 3 tracked levels via `parity_report.py` against the existing `/tmp/uedcli-parity-cache/`
goldens (no live editor spin-up needed — all 3 cache-hit).** Node/surf/leaf topology is IDENTICAL
flag-on vs flag-off on every level (the safety argument holds by construction: the gate only permutes
`model.points`' internal order and remaps `p_base`/`i_vertex` consistently — it never touches
`model.nodes`/`model.surfs`/`model.verts` structurally) — geometry counts, verts/points/vectors
deltas, and lighting (records + shadow bits) are byte-identical on/off for `UNATCO` and Wanchai. But
the `p_base`-order metric the fix targets got WORSE everywhere, not better:

| level     | surf `p_base` diffs, flag OFF (baseline) | flag ON            |
|-----------|------------------------------------------:|--------------------:|
| `DX.dx`   | 13/26                                      | **20/26**            |
| `UNATCO`  | 3592/3709                                  | **3612/3729**        |
| Wanchai   | 5249/8696 (incl. unrelated texture-ref case diffs) | **5252/8699** |

`DX.dx` does NOT reach FULL PARITY with the flag on — it regresses (13 -> 20). This is a clean,
three-for-three negative result, not a partial win: even restricted to the single safest possible
case (a surf whose ring is PROVEN, by direct value comparison, to be its brush's untouched authored
polygon — no lineage-flag guesswork), replaying "Origin then reversed ring" as a POST-HOC pass over
the final model does not reproduce the golden's true order. This confirms, experimentally rather than
just architecturally, the prior round's own concern: the real order is a function of the INCREMENTAL
insertion sequence interleaved with periodic (per-`bspRefresh`-call) drop-then-readd compaction, which
a single end-of-build resort — however precisely gated — structurally cannot replay, because the
final model retains no memory of which points were inserted, dropped, and re-inserted at which point
during the build. Gating correctly identifies WHICH surfs are safe to touch without risking structure,
but "safe to touch" and "produces the right answer" turned out to be independent questions here.

**Not shipped; nothing changes on the default path.** `UEDCLI_BSPCSG_POINTS_ORIGIN_REVERSED` stays
off by default (zero effect unless explicitly set) — kept in the tree as a negative-result experiment
with its own regression tests (pins the exact gated behavior so a future attempt at the real
incremental-replay architecture has a known-bad post-hoc baseline to beat, and so nobody re-discovers
"just resort the final surfs" as a shortcut without re-deriving this result). A real fix needs
`reorder_points_canonical` replaced by an incremental point-pool model that replays insertion AND the
periodic reachability-GC compaction in build order — the architecture change both this round and the
prior one identified, still unbuilt. Code: `uedcli-native/src/bspcsg.rs` (`unsplit_ring` module,
`points_origin_reversed_enabled`, the two new `bspcsg::tests` cases). Worktree
`.claude/worktrees/bsp-insertion-order`, left uncommitted per this round's instructions.

## Round 11 (2026-09-01): live-captured a genuine mid-CSG-split `bspAddPoint` sequence on a synthetic 2-brush case — decoded, but the split turned out fully TRANSIENT (`bspMergeCoplanars`-equivalent erases it before the final model), so the rule for a PERSISTING split fragment (the UNATCO/Wanchai case) is still unconfirmed. No fix attempted.

Task: round 9 pinned "`Origin` then reversed `Vertex` ring" for `DX.dx`'s UNSPLIT boxes; round 10
showed a post-hoc replay of that rule can't work regardless of gating. This round's mandate: capture
the real `bspAddPoint` sequence for a genuine CSG-SPLIT polygon fragment (UNATCO/Wanchai's actual
`p_base` residual shape), live, to see whether the same rule extends or a different one applies.

**DX.dx has no real split** — round 9 already noted its 5 brushes are plain unsplit boxes; confirmed
again this round (26 nodes = 26 surfs, no shared `iLink`). Built a synthetic 2/3-brush trunk instead
(`_scratch/split-trace/maps/split2` in the round's own worktree, not committed — throwaway):
`Room` (`CSG_Subtract`, a 2048³ hollow box) + `PillarB`/`PillarC` (`CSG_Add`, two 512-cube "pillars"
overlapping by 256uu along X, same Y/Z extents) — the minimal shape that forces `bspBrushCSG` to
actually split a polygon against another brush's existing planes, built via
`dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py` (`--world-only --no-light
--no-obj-load`) then re-traced with the existing `bspaddpoint_call_trace.py` harness
(`dev/docs/spikes/2026-09-01-dx-pbase-points-trace/harness/`) — reused as-is, no new VAs needed.
(First attempt used two bare `CSG_Add` boxes only, no `Subtract` — got a genuinely EMPTY built model,
0 nodes: confirms the world starts SOLID, not empty, so a pure-`Add` brush with nothing subtracted
first adds nothing new. Documented here so a future round doesn't repeat the same dead end.)

**Live capture: 383 `bspAddPoint` calls total across the `MAP REBUILD`.** Chunking by the `Exact=1`
Origin marker (round 9's own signature) gives 35 groups; every UNSPLIT face's group is 5 calls
(Origin + 4 Vertex, one of the 4 landing back on Origin's own point via the tolerance dedup) — but
four groups (one per straddling face of `PillarC`) are **9 calls**, not 5: `Origin` once (`Exact=1`),
then **8** `Vertex` calls. Decoded (per-face, e.g. `PillarC`'s +Z face, authored corners A(256,-256,256)
→B(768,-256,256)→C(768,256,256)→D(256,256,256)): `[Origin=A] [new-mid1(512,-256,256)] [B] [C]
[new-mid2(512,256,256)] [A(dedup)] [new-mid1(dedup)] [new-mid2(dedup)] [D]`. Read as two 4-vertex
rings sharing the cut edge at X=512: **ring 1 = [mid1, B, C, mid2]** (the outer, X:512–768 half) and
**ring 2 = [A, mid1, mid2, D]** (the inner, X:256–512 half, sharing `PillarB`'s already-added volume)
— both walked in the polygon's OWN forward winding direction (not reversed), and **only the FIRST
ring's start gets an `Exact=1` Origin call; the second ring's start point is inserted as an ordinary
tolerance-dedup Vertex call**, i.e. `alloc_surf` (which sets `p_base`) fires once, and the second
fragment reuses it via `iLink` — exactly the branch native's own `bsp_add_node` already implements
(`bspcsg.rs` ~313: `if edpoly.i_link < 0 { alloc_surf(...) } else { edpoly.i_link }`), not a missing
mechanism.

**But the split is TRANSIENT: none of the 4 fragments persists in the final built model.** Parsed the
separately-built golden (`parity_compare.parse_dx_model`, no gdb needed for this check) — every one
of `PillarC`'s 4 straddling surfs (`ibrushpoly` 0/1/2/3) is a single 4-vertex node spanning the FULL
authored range (256–768), byte-identical to the UNSPLIT authored polygon, not either half. So
whatever split the live trace shows mid-build gets fused back into one whole polygon before the final
`p_base`/points array is written — consistent with `bspMergeCoplanars` (`bspcsg.rs` line 1952,
`bsp_merge_coplanars`, already ported from the real `Editor.dll 0x36200`/`0x36480`): two `iLink`-
sharing, coplanar, same-texture, adjacent fragments are a canonical merge candidate, and this
synthetic case's fragments are maximally mergeable (same plane, same texture, sharing one full edge,
no third neighbor interrupting). `PillarB`'s own faces (the OTHER side of the same overlap) DO show a
real, PERSISTING trim in the final model (their authored 0–512 range is cut down to 0–256, the
portion outside `PillarC`) — but that trim comes from a full-polygon "already solid, drop" classification
against `PillarC`'s volume (round 9's non-split "whole polygon in/out" case), not from a surviving
split fragment; it offered no new information over round 9.

**Net result: a real, live, decoded mid-CSG-split `bspAddPoint` sequence was captured end-to-end, but
this specific synthetic geometry was the wrong shape to answer the actual open question** — it
exercises a split that always gets merged back away, not the UNATCO/Wanchai case (924/3709 residual
`p_base` diffs) where a split fragment survives as its OWN final surf. The two rings' insertion order
(forward, unreversed, per-fragment; second fragment skips `alloc_surf`) is confirmed for a
**transient** split; whether the SAME rule holds for a fragment that is never remerged (differing
neighbor geometry/texture on the two sides of the cut, so `merge_group_pred` never fires) is still
open. A future round needs a synthetic case built specifically to defeat the merge — e.g. two
overlapping brushes with DIFFERENT Y/Z extents (a true T-junction, not a flush full-height/width
overlap) or a third brush interrupting one side of the cut only.

**No fix attempted, none should be** — the incremental point-pool architecture rounds 9/10 already
scoped is not worth prototyping against a rule not yet confirmed for the case it needs to cover; per
the standing no-guessing rule. `DX.dx`/UNATCO/Wanchai `p_base` counts unchanged (no production code
touched — `uedcli-native/src/*` untouched this round). Harness reused unmodified
(`bspaddpoint_call_trace.py`, `points_pool_refresh_trace.py`); the synthetic trunk + golden + gdb log
are throwaway, left in the round's own worktree (`.claude/worktrees/bspcsg-split-fragment-trace`,
`_scratch/split-trace/`), not committed, not needed by a future round (the T3D recipe above is enough
to regenerate).

## Round 12 (2026-09-01): a corner-bite variant DEFEATS the coplanar merge -- live-captured a genuine PERSISTING split; the fragment-insertion rule is confirmed as a natural extension of round 11's, not a different rule; no fix shipped

Task: round 11 captured a real mid-CSG-split `bspAddPoint` sequence but the split was fully
TRANSIENT (merged back before save) -- its own conclusion named two variants to try to defeat the
merge: differing Y/Z extents between the two overlapping brushes (a true T-junction), or a third
brush interrupting one side of the cut only. This round built the second variant.

**Design, new committed harness (`dev/docs/spikes/2026-09-01-dx-pbase-points-trace/harness/
build_tjunction_trunk.py`):** `Room` (`CSG_Subtract`, 2048³) + `PillarB`/`PillarC` (`CSG_Add`,
512-cubes overlapping 256uu along X -- IDENTICAL to round 11's own geometry, kept as an in-build
reproducibility control) + `PillarD` (`CSG_Add`, a 64×128×128 corner-bite box at `(432,224,224)`,
X:[400,464] -- well inside PillarC's outer split half [256,512], 144uu clear of the X=256 split
boundary and entirely clear of `PillarB`). `PillarD` pokes past PillarC's +Y (Y=256) and +Z (Z=256)
face planes only, carving a notch into the OUTER fragment of those two faces alone; -Y/-Z are
untouched.

**Verified BEFORE any live trace that the split genuinely persists (direct model inspection of the
built golden, no gdb needed for this check).** `dev/docs/spikes/2026-09-01-dx-pbase-points-trace/
harness` companion inspection (throwaway `_scratch/tjunction/inspect_golden.py`, not committed --
trivial to regenerate from `parity_compare.parse_dx_model` + the pkg export table) parses the built
`.dx` and groups `model.nodes` by shared `i_surf`. Result: surf 12 (`i_actor=PillarC`,
`i_brush_poly=2`, the +Y face) and surf 14 (`i_brush_poly=4`, +Z) each resolve to **3 separate final
BSP nodes** sharing one surf index -- a genuinely disjoint, non-reunited set of fragments (X ranges
`[464,512]` / `[0,400]` / `[400,464]`, the last cut short in Z where PillarD's notch removed
material). The CONTROL faces, untouched by PillarD -- surf 13 (-Y, `i_brush_poly=3`) and surf 15
(-Z, `i_brush_poly=5`) -- each resolve to exactly **1 final node**, reproducing round 11's "all
straddling surfs end up as ONE whole node" finding exactly, on independent geometry. One addendum to
round 11's characterization: the re-merged whole face is a 6-vertex ring, not the clean 4-vertex
rectangle round 11 reported -- it retains the two historical split-boundary points as extra
COLLINEAR vertices rather than being cleanly re-derived from scratch.

**Live gdb capture (reusing `bspaddpoint_call_trace.py` unmodified, same VAs as rounds 9/11): 607
calls, log committed at `dev/docs/spikes/2026-09-01-dx-pbase-points-trace/logs/
bspaddpoint-call-trace.log`.** Decoded (throwaway `_scratch/tjunction/decode_trace.py` /
`compare_final_order.py`, not committed -- trivial to regenerate):

1. **PillarC's own LOOP1-vs-PillarB split (calls 121-161) reproduces round 11's transient-split rule
   EXACTLY, on independent geometry:** two 4-vertex rings sharing the cut edge, both walked FORWARD
   (no reversal), only the outer ring's start gets `Exact=1`/`alloc_surf`, the inner ring's start is
   an ordinary tolerance-dedup `Vertex` call. Confirms round 11's rule is not a one-geometry fluke.
2. **That split is re-merged by LOOP2 (calls 162-207) BEFORE `PillarD` is even processed** -- new
   fact not in round 11 (whose synthetic case had only 2 brushes, so this couldn't be observed):
   `bspMergeCoplanars` (or an equivalent per-brush fusion) runs PER-BRUSH, incrementally, not once
   globally at the very end of `csgRebuild`. The remerged polygon keeps the two split points as extra
   collinear ring vertices (the 6-vertex addendum above).
3. **`PillarD`'s own CSG pass (calls 208-275) never emits a fresh `Exact=1`/`alloc_surf` call for
   surf 12/14.** Grepped the full 607-call trace for every `Exact=1` marker (48 total, all ≤ call
   275) -- the notch cut reuses the ALREADY-ALLOCATED surf (and its `p_base`, fixed back at call 172
   when PillarC's own re-merged +Y polygon was added to the world) via ordinary dedup `Vertex` calls
   only, splitting it into the 3 final disjoint nodes without ever re-allocating the surf. **This is
   the answer to the round's central question: persistence does NOT change the insertion rule.** A
   fragment set that persists gets exactly the same treatment as one that's about to be merged away --
   one `Exact=1`/`alloc_surf` at whichever CSG step FIRST creates the polygon (which may itself be a
   later, already-remerged whole, not the original raw split), and every subsequent split by ANY later
   brush reuses that one surf/`p_base` via plain dedup `Vertex` calls, forever -- confirmed here across
   TWO further splitting events (PillarB's cut, then PillarD's notch) on the one canonical surf.
4. **Every final node's vertex ring (9/10/11 on surf 12, 17/18/19 on surf 14) walks FORWARD winding,
   never reversed** -- the same rule holds for the actual persisting, final geometry, not just the
   transient intermediate rings round 11 captured.
5. **Base-block relative order is UNCHANGED from round 9's rule.** Golden's real `Points[12..15]` are
   PillarC's 4 side-face Origins in AUTHORED polygon order (`poly2,3,4,5` = `+Y,-Y,+Z,-Z`, `cube()`'s
   own face order) -- exactly round 9's "Origin first, per polygon, in authored CSG order" rule,
   holding even though poly2/poly4's own ring later undergoes a persisting split. The live trace's
   LAST-HIT `ret_idx` for these 4 points (10,11,12,13) preserves the identical relative order (a
   uniform −2 compaction offset versus their real final index), consistent with round 9's "`bspRefresh`
   preserves relative order, only drops-and-closes-gap" mechanism extending unchanged to a surf whose
   ring is a persisting split.
6. **But a literal absolute-index last-hit reconstruction still fails broadly** (only 1/60 golden
   points match their trace `ret_idx` at the raw-index level; the rest hold a per-brush-group offset
   that is internally uniform but differs unpredictably block to block: −8 for Room's cap points,
   roughly −3 for PillarB's, +2 for PillarC's own side-face Origins, +8..+16 for PillarD's).
   Confirms round 10's finding generalizes to the persisting-split case too: recovering the true final
   index needs the exact incremental drop/readd depth per point (how many further `bspRefresh`/
   `bspRepartition` cycles happen to touch it), which is not a function of the final model alone --
   the SAME reason round 10's post-hoc single resort failed on `DX.dx`'s much simpler unsplit case.

**Net verdict.** The corner-bite variant DOES defeat the coplanar merge (confirmed via direct
model inspection, with a same-build reproducibility control). The persisting-fragment insertion rule
is now found, precisely, and it's a clean, forced extension of round 11's transient rule rather than a
new one: forward winding always, one `alloc_surf` per canonical surf ever, every later split (by the
original interrupting brush or a completely different, later one) reuses it via plain dedup calls.
New fact for a future incremental-model implementation: the merge pass that can erase a split
fragment runs PER-BRUSH, not once at the end -- an incremental point-pool architecture must replay
merge-then-resplit cycles at every brush boundary, not just track one final merge. Base-block relative
order is untouched by any of this (round 9's rule already covers it). What's still missing is
UNCHANGED from round 10: a real architecture replacing `reorder_points_canonical`'s single end-of-build
resort with an incremental model that replays insertion AND the periodic per-point drop/readd
choreography in build order -- round 10 already proved a post-hoc pass can't fake this, and this round
confirms the same limit holds for a persisting multi-brush split, not just DX.dx's unsplit boxes.

**No fix attempted, none should be** -- per the standing no-guessing rule, the rule is now fully
characterized for both transient and persisting cases, but implementing the incremental replay is the
same real architecture change rounds 9/10 already scoped, still unbuilt; prototyping it blind without
budget for a full non-regression pass on UNATCO/Wanchai would repeat round 10's mistake in a much
larger, more complex form. `uedcli-native/src/*` untouched this round. `DX.dx`/UNATCO/Wanchai `p_base`
counts unchanged (no production code touched). New harness committed:
`dev/docs/spikes/2026-09-01-dx-pbase-points-trace/harness/build_tjunction_trunk.py` (builds the
T-junction/corner-bite trunk) and `dev/docs/spikes/2026-09-01-dx-pbase-points-trace/logs/
bspaddpoint-call-trace.log` (this round's 607-call capture, kept for future comparison alongside
round 9/11's methodology). Worktree `.claude/worktrees/pbase-round12-tjunction`, left uncommitted per
this round's instructions.

## Breadth table refreshed (2026-09-01): re-measured all 18 cached corpus levels post `light30` fix

The 2026-08-31 breadth table (search "Breadth golden-caching pass") predates today's `light30`
row-padding-carry fix (`1ef4fe4`). Re-ran `parity_report.py` against all 18 cached goldens (no new
editor builds -- cache hits throughout) to get current numbers.

Geometry is unchanged on every level (today's work didn't touch default geometry code paths --
the `bspcsg.rs` experiments from rounds today are gated off by default). Lighting improved on
every level whose geometry is close enough for records to positionally line up:

| level | lighting before | lighting after |
|---|---:|---:|
| NYC Bar | 87.7% | 93.1% |
| UNATCO | 83.6% | 90.9% |
| NYC ShipFan | 69.7% | 75.0% |
| NYC Underground (04) | 55.8% | 66.6% |
| Wanchai Market | 75.5% | 80.0% |
| Paris Club | 76.8% | 87.4% |
| HK Helibase | 67.0% | 69.7% |
| Paris Chateau | 81.8% | 87.6% |
| Wanchai Garage / Paris Underground / Area51 Entrance / Training Final / FreeClinic08 / NYC 747 / Vandenberg Gas / OceanLab Lab / NSFHQ04 | (severe geometry break) | unchanged -- almost no record can positionally line up when node/leaf counts themselves diverge |

Still **zero levels at full byte parity**; geometry-6/6 count-exact stays 2/21 (DX.dx, NYC Bar).
Full per-level table shown to the owner as an artifact this round; not reproduced in full here to
avoid duplicating `parity_report.py`'s own output -- rerun it directly for exact current numbers.

## Round 13: first real IMPLEMENTATION attempt at the incremental point-pool architecture rounds 9-12 scoped -- MEASURED NEGATIVE on all 3 tracked levels; not shipped, root cause narrowed but not found

Task: rounds 9-12 fully pinned the real editor's per-polygon `bspAddPoint` insertion rule (`Origin`
then reversed ring for an unsplit whole polygon; forward winding + first-fragment-only `alloc_surf`
for a split) but explicitly stopped short of implementing it, since round 10 proved a POST-HOC
resort over the final model cannot replay it. This round's mandate: build the real incremental
architecture -- per-brush insertion in CSG order, replaying `bspRefresh`'s periodic drop/readd
compaction -- and measure it for real, non-regression-gated, on `DX.dx`/UNATCO/Wanchai.

**Root architectural fact found first (not previously documented): `model.points` is UNCONDITIONALLY
CLEARED before `bspRepartition`'s own rebuild** (`build_geometry_bspcsg`, the `model.points.clear()`
call gated only by the pre-existing `UEDCLI_BSPCSG_WORLD_KEEP_POINTS`, off by default). Since
`bspRepartition` throws away `model.nodes`/`model.surfs`/`model.verts`/`model.points`/`model.vectors`
and rebuilds ALL of them from the post-merge fragment soup via a fresh `bsp_build`, native's Pass-1
incremental insertion order (the thing rounds 9-12 characterized) is discarded by construction before
it can ever reach the final model -- `reorder_points_canonical`'s end-of-build reconstruction exists
`BECAUSE` of this discard, not despite it. This means any fix has to (a) keep the Points/Vectors pools
alive across that clear, not just insert them correctly during Pass 1.

**Implementation (`uedcli-native/src/bspcsg.rs`, gated behind NEW flag
`UEDCLI_BSPCSG_INCREMENTAL_POINTS`, off by default -- 0 effect unless set):**
1. `bsp_add_node`: for a poly whose surf is a first-allocation (`i_link < 0`, i.e. `alloc_surf` runs)
   AND the flag is set, resolve each ring vertex's point-pool index by walking `edpoly.verts`
   BACKWARDS (round 9's "Origin then reversed ring" rule) while still writing the results into
   `model.verts` in the polygon's own FORWARD order (the node's real rendering ring must stay
   forward -- only which pool index a point receives changes, never which point a vert names). A
   split fragment (`i_link >= 0`, reusing an EXISTING surf) is untouched -- round 11/12's "forward,
   never reversed" rule for a fragment already falls out of the existing default code path.
2. `bsp_brush_csg`'s tail: after the existing per-brush `bsp_cleanup`, call the ALREADY-existing
   (but previously unwired) `passes::bsp_refresh_points_vectors` once per brush -- an order-preserving
   reachability GC (drops orphans, never reorders survivors) matching round 9's own measured cadence
   (`DX.dx`: exactly 5 `bspRefresh` calls for exactly 5 brushes).
3. `build_geometry_bspcsg`'s repartition-clear boundary: extend `UEDCLI_BSPCSG_WORLD_KEEP_POINTS`'s
   existing points-survival condition to also fire under the new flag.
4. The end-of-build canonicalization: when the new flag is set, replace the
   `reorder_points_canonical` call (bases-then-rings RECONSTRUCTION from the final structure) with a
   bare `passes::bsp_refresh_points_vectors` call (order-preserving orphan-drop only) -- added after
   discovering (1)-(3) alone had ZERO measured effect (see below), because `reorder_points_canonical`
   unconditionally overwrites whatever order preceded it.

**Measured on `DX.dx` via `parity_report.py` (cached golden, no live editor) -- THREE separate,
isolated configurations, each rebuilt and independently verified:**

| configuration | surf `p_base` diffs | geometry (6 counts) |
|---|---:|---|
| default (flag off) -- baseline | 13/26 | EXACT (26/26/5/250/32/6) |
| (1)+(2)+(3), but `reorder_points_canonical` still runs at the end | 13/26 (byte-identical to baseline) | EXACT |
| (1)+(2)+(3)+(4) -- the incremental order actually reaches the final model | 25/26 | still EXACT |
| (2)+(3)+(4) only, insertion-order reversal (1) DISABLED via a temporary debug gate | 25/26 (identical numeric result to the row above) | still EXACT |

The middle row's zero effect is a clean, mechanical confirmation, not a surprise in hindsight:
`reorder_points_canonical` derives order purely from the FINAL surf/node structure (bases in
canonical-surf order, then ring verts in node-array order), so it overwrites ANY preceding order
unconditionally -- keeping Points alive through repartition changes nothing until something ALSO
stops re-deriving order from scratch at the end. The bottom two rows isolate the real question --
does the raw incrementally-preserved order (once it's actually allowed to reach the final model) beat
the default's post-hoc heuristic? -- and answer NO, decisively: 25/26 is worse than 13/26, and this
holds REGARDLESS of whether the Origin+reversed-ring insertion rule is applied, meaning the damage is
not primarily an insertion-order-rule bug -- it is in the keep-alive + per-brush-GC mechanism itself.

**On UNATCO the flag is worse than a parity regression -- the native build fails outright:**
`parity_report.py --json` against `03_NYC_UNATCOHQ.dx` with the flag set exits 2, `native CSG build
failed: lightmap bake: vert iVertex index -1 out of range [0,10758)` -- a dangling point reference a
later stage can't resolve. Root cause not chased down this round (budget), but the shape is
suggestive: UNATCO has real WTB-path cross-brush re-splits (rounds 11/12's whole subject), where a
LATER brush's `FilterWorldThroughBrush` re-visits an EXISTING surf's points; a per-brush GC that only
runs in `bsp_brush_csg`'s OWN tail (i.e. once that BRUSH is done) has no visibility into a point a
FUTURE brush's WTB pass will still need, and can drop it as an orphan too early. **Wanchai, by
contrast, does NOT crash** with the flag on: node/surf/leaf counts stay EXACT (11648/5284/3371, d=+0
each, byte-identical to the flag-off baseline) and verts/points deltas actually IMPROVE slightly
(verts d=+74->+49, points d=+16->+14; vectors unchanged at d=-8) -- a genuinely mixed, unresolved
result this round did not have budget to reconcile with UNATCO's outright crash on ostensibly the
same mechanism.

**Non-regression: CONFIRMED on all 3 tracked levels, by construction and by live measurement.** Every
change is gated behind `UEDCLI_BSPCSG_INCREMENTAL_POINTS`, off by default, so the default path is
provably untouched (every new branch has an unmodified `else` arm running the pre-existing code
verbatim). Live-measured anyway (not just argued): `parity_report.py` with the flag OFF reproduces
the exact pre-existing historical baseline on all 3 levels -- `DX.dx` 13/26 `p_base` / geometry EXACT
/ lighting 100%; UNATCO nodes/surfs/leaves 6314/3616/762 d=+0 each, verts d=+5, points d=+16, vectors
d=+0; Wanchai nodes/surfs/leaves 11648/5284/3371 d=+0 each, verts d=+74, points d=+16, vectors d=-8.
Full crate `cargo test --quiet`: 99/99 (98 pre-existing + 1 new structural-safety test pinning this
round's flag on the simplest unsplit case, since it cannot be corrupted the way UNATCO's crash shows
for cross-brush-split geometry).

**Not shipped; `DX.dx` does NOT reach FULL PARITY this round.** `UEDCLI_BSPCSG_INCREMENTAL_POINTS`
stays off by default, kept as a real (not post-hoc) incremental-architecture attempt with its own
regression test, for the same reason round 10's post-hoc experiment was kept: so a future round has a
known-bad incremental baseline to beat rather than re-deriving this result. **What's still open,
precisely:** the real editor's `bspRefresh` cadence is evidently FINER-GRAINED than "once per
completed brush" -- round 9's "5 calls for 5 brushes" count for `DX.dx` is consistent with a
per-brush cadence ONLY because `DX.dx` has zero real cross-brush splits (round 9: "26 nodes = 26
surfs, no shared `iLink`"); it does not by itself prove the cadence IS per-brush, and this round's
UNATCO crash is direct evidence it is NOT -- some finer unit within a brush's own `bspBrushCSG`
processing (plausibly per-`FilterWorldThroughBrush` call, or per some subtree unit inside the LOOP2
descent) must be the real trigger, catching points inserted-but-not-yet-node-referenced at a grain
this round's per-brush cadence is too coarse to see. Finding that finer unit needs a live gdb capture
counting `bspRefresh` call TIMING against finer pipeline checkpoints than round 9's own trace covered
(it counted calls, not what triggered each one) -- not attempted this round, budget. Code:
`uedcli-native/src/bspcsg.rs` (`incremental_points_enabled`, the `bsp_add_node` reversed-insertion
branch, the per-brush `bsp_refresh_points_vectors` call in `bsp_brush_csg`, the repartition-clear
`keep_points` extension, the end-of-build branch replacing `reorder_points_canonical`, and
`incremental_points_keeps_the_simplest_subtract_case_structurally_safe_but_not_parity_exact`).
Worktree `.claude/worktrees/bspcsg-incremental-points`, left uncommitted per this round's
instructions.

## Round 14 (2026-09-01): `bspRefresh`'s real cadence found -- ZERO calls during brush CSG, all of them tied to a SEPARATE post-CSG rebuild phase; round 13's per-brush placement is the bug, not a too-coarse cadence

Task: round 13's incremental-point-pool attempt called the (pre-existing)
`passes::bsp_refresh_points_vectors` GC once per brush, in `bsp_brush_csg`'s tail -- matching round 9's
"5 `bspRefresh` calls for `DX.dx`'s 5 brushes" correlation -- and that measured worse on `DX.dx` and
crashed UNATCO. Round 13 guessed the real cadence must be FINER than once-per-brush (some sub-brush
checkpoint). This round's mandate: find the real trigger, live, on a case with genuine cross-brush
persisting splits (not `DX.dx`'s trivial unsplit boxes), per round 13's own item 3 -- check for a
mundane bug in round 13's call-site placement before assuming the cadence theory.

**Verdict: round 13's cadence theory had the direction backwards. The real cadence is COARSER than
once-per-brush, not finer -- `bspRefresh` fires ZERO times during brush CSG (any brush, including ones
with real cross-brush WTB resplits) and only fires within a SEPARATE rebuild phase that runs AFTER all
brushes' CSG completes.** Round 13's bug is a phase-placement bug: it wired the GC into the CSG phase,
a phase the real editor never GCs during, at all.

**Method: a new combined trace, one gdb session, one global sequence counter, breaking on all four VAs
at once** (`bspAddPoint` entry `0x1003545d`/exits `0x100354ce`+`0x100355a7`, `bspRefresh` entry
`0x10036cd0`/exit `0x1003718f` -- all four VAs reused unmodified from round 9). Prior rounds traced
`bspAddPoint` and `bspRefresh` in SEPARATE gdb runs and could only correlate by call-index heuristics
across two different logs; interleaving both in one session with one counter gives the true relative
order directly. New harness: `dev/docs/spikes/2026-09-01-dx-pbase-points-trace/harness/
combined_refresh_addpoint_trace.py`. Target: round 12's own T-junction trunk
(`build_tjunction_trunk.py`, unmodified) -- `Room` (`CSG_Subtract`) + `PillarB`/`PillarC` (`CSG_Add`,
overlapping) + `PillarD` (`CSG_Add`, corner-bite) -- the case round 12 already proved has a real,
PERSISTING cross-brush split (surf 12/14, 3 final nodes each from one canonical surf reused across
PillarB's cut and PillarD's notch). Rebuilt the golden fresh this round (`build_ued_golden.py
--world-only --no-light --no-obj-load`); log committed at `dev/docs/spikes/2026-09-01-dx-pbase-points-
trace/logs/combined-tjunction.log`.

**Result: 607 `bspAddPoint` calls (identical count to round 12's separately-traced run on the same
trunk -- confirms determinism/reproducibility) and exactly 5 `bspRefresh` calls, matching round 9's
`DX.dx` count coincidentally -- but their POSITION in the call sequence refutes per-brush cadence
outright:**

| `bspRefresh` call | fires between `bspAddPoint` calls | nodes/points/vectors before -> after |
|---|---|---|
| rfidx=1 | apidx 303 / apidx 304 | 40/65/23 -> 34/23/23 |
| rfidx=2 | apidx 415 / apidx 416 | 28/61/23 -> 28/61/23 (no-op) |
| rfidx=3 | immediately after rfidx=2, same boundary | 28/61/23 -> 28/61/23 (no-op) |
| rfidx=4 | apidx 607 (the LAST call of the whole build) / after it | 76/99/23 -> 28/61/23 |
| rfidx=5 | immediately after rfidx=4, same boundary | 28/61/23 -> 28/60/22 |

**Decisive coordinate evidence for what's actually happening at these boundaries.** Calls 208-303 are
`PillarD`'s own CSG pass against `PillarC`/`PillarB` (coordinates in the 160-512 range, matching that
geometry -- confirms round 12's "PillarD reuses the already-allocated surf via dedup calls only, no
fresh `alloc_surf`" finding held for the ENTIRE tail of PillarD's processing, not just the window round
12 sampled). Call 304, immediately after rfidx=1, jumps straight to `(1024,-1024,1024)`,
`(1024,1024,1024)`, ... -- `Room`'s own 2048-cube corner points (half-extent 1024), i.e. a dead restart
from the FIRST brush's own geometry, in a totally different order than brush-CSG order. The same thing
happens again at call 416, immediately after the rfidx=2/3 no-op pair: `(-1024,-1024,-1024)`,
`(1024,-1024,-1024)`, ... -- `Room`'s corners AGAIN, a second full pass. **This can only be a separate,
subsequent tree-rebuild pass that re-walks the model's final merged polygon soup from scratch
(revisiting `Room`'s geometry multiple times, in `bsp_build`-recursion order, not brush-CSG order) --
not a continuation of brush processing.** Grepping the full log confirms **zero** `RF_ENTRY`/`RF_EXIT`
lines anywhere in the first 790 log lines (`bspAddPoint` calls 1-303, spanning ALL FOUR brushes' full
CSG -- `Room`+`PillarB`+`PillarC`'s split-vs-`PillarB` (round 11/12's own subject) +`PillarD`'s
cross-brush WTB notch-resplit against `PillarC`'s existing surf, round 13's own named suspect for a
finer-grained trigger).

**This matches a mechanism already on record, predating round 9: `points_pool_refresh_trace.py`'s own
docstring (written by round 9 itself) already states "`bspRefresh` ... is called once at world-level
and once per `bspRepartition` subtree (up to ~209/119 times on larger levels)" -- citing prior "Round
3". Round 9 itself labeled `DX.dx`'s call 1 "the world-level, FIRST `bspRefresh`"** (§`DX.dx`'s
`p_base` residual" section above), already distinguishing it from a "per-brush" call, a distinction
round 13 overlooked when it generalized "5 calls, 5 brushes" into per-brush causality. This round's
5-call breakdown reads cleanly against that pre-existing mechanism: **rfidx=1 sits exactly at the
CSG-phase/rebuild-phase seam (plausibly the "world-level" call, fired once as the finished CSG model is
handed to the rebuild/repartition step) and rfidx=2-5 are "per-subtree" checkpoints WITHIN that
rebuild's own recursion** (2 no-op mid-rebuild, 2 more -- one doing the real, large final compaction --
right after the rebuild's own last `bspAddPoint` call). The subtree count (4, for this tiny synthetic
level) scales with the rebuild's own recursion depth/structure, not with brush count -- consistent with
the doc's already-recorded "up to ~209/119 on larger levels" scaling note.

**This directly explains round 13's regression AND crash as one mechanism, not two separate bugs --
answering item 3 of this round's mandate: it is a call-site bug, not a too-coarse cadence.** Round 13
wired `passes::bsp_refresh_points_vectors` into `bsp_brush_csg`'s own tail -- i.e. DURING the CSG
phase, once per brush. This trace shows the real editor runs this GC ZERO times during CSG, for ANY
brush, including the one (`PillarD`) round 13 itself flagged as the likely culprit ("a LATER brush's
`FilterWorldThroughBrush` re-visits an EXISTING surf's points"). Round 9 already established why a
mid-CSG GC is unsafe on its own terms: "ring-only points ... are NOT YET referenced by any node's
vert-pool at the time of the FIRST `bspRefresh` -- node/vert-pool construction happens later, DURING
`bspRepartition`'s subtree recursion" (§`DX.dx`'s `p_base` residual" section). Running a reachability
GC before that linkage exists (as round 13's per-brush call does) will misclassify still-needed points
as unreachable and drop them -- exactly UNATCO's crash symptom (`vert iVertex index -1 out of range`,
a point a later stage needed was already gone) and, on `DX.dx`, a corruption of index alignment
relative to a golden that never GCs until the rebuild phase (the measured 13->25 `p_base` regression).

**Connects to round 13's own "root architectural fact" (`model.points` unconditionally cleared before
`bspRepartition`'s own rebuild in `build_geometry_bspcsg`) -- native already has the right SEAM for
this, it's just not where the GC call was wired.** The real editor's own rebuild/repartition-equivalent
phase is exactly the phase native's `build_geometry_bspcsg` already treats specially (the
`model.points.clear()` call). This round did not attempt to move the GC call there or otherwise change
`uedcli-native/src/*` -- per this round's mandate, characterization only, no implementation. A future
round can now target the GC call site with confidence: NOT `bsp_brush_csg`'s per-brush tail, but
somewhere in/around the rebuild/repartition-equivalent phase, with a trigger tied to that phase's own
recursion structure (subtree checkpoints), not to brush completion. What is still NOT characterized:
the exact recursion unit that maps 1:1 to a real subtree checkpoint (this round pinned WHERE the calls
land in the `bspAddPoint` sequence, not the precise C++ call site inside the rebuild), and how the
count scales on a real level's much deeper rebuild recursion (UNATCO/Wanchai) -- both open for a future
implementation round.

**No production code touched this round** (`uedcli-native/src/*` untouched; `DX.dx`/UNATCO/Wanchai
`p_base` counts unchanged). New committed-worthy harness (left uncommitted per this round's
instructions): `dev/docs/spikes/2026-09-01-dx-pbase-points-trace/harness/
combined_refresh_addpoint_trace.py` (interleaved `bspAddPoint`+`bspRefresh` trace, one gdb session, one
global sequence counter -- reusable for any future cadence question needing true call-order evidence)
and `dev/docs/spikes/2026-09-01-dx-pbase-points-trace/logs/combined-tjunction.log` (this round's 1408-
line capture). Worktree `.claude/worktrees/pbase-round14-refresh-cadence`, left uncommitted per this
round's instructions.

## OceanLab Lab +27 surf over-build — root-caused and FIXED: `bsp_validate_brush_links` coplanarity gate used `verts[0]`, must use the authored `Base` (2026-09-01)

Owner directed a shift to the worst-parity levels, starting with OceanLab Lab (`14_OceanLab_Lab.dx`,
1886 brushes, the largest level in the corpus). It was previously the worst instance of the
severe-under-build family (`breadth-geometry-check-on-10-new-og-levels-1-10`: nodes -22.0%, surfs
-19.7%) attributed to the same root cause as Area51 Entrance (mirrored-brush determinant bug, fixed
`c7b8b0b`). A fresh breadth pass (2026-09-01, cached golden) showed the shape had FLIPPED to a much
smaller OVER-build (nodes +465, surfs +27, leaves +86, verts +3958, points +1003, vectors -66) — the
mirrored-brush fix evidently touched OceanLab too, but left (or revealed) a second, smaller, unrelated
issue. This item root-causes and fixes the SURF half of that residual.

**Per-brush surf attribution** (method from `freeclinic08-nsfhq04-1-surf-under-build-root`: native
`BspSurf.i_actor` vs golden's resolved via `epkg.name_of_ref`, script
`dev/docs/spikes/2026-09-01-oceanlab-overbuild/harness/` — see below) found **exactly 9 brushes**
differ, **each by exactly +3** (native 18 vs golden 15, or native 21 vs golden 18), summing to the
full net +27 with zero cancellation — an unusually clean signal. All 9 are `Brush784`/`844`/`858`/
`872`/`886`/`904`/`918`/`1852`/`1868`: identical-shape 26-poly `CSG_Add PolyFlags=32` (PF_Semisolid)
"2D Loft" BrushBuilder decorative details (a small beveled octagonal-ring shape, `Item=2DLoftTOP/SIDE/
END`), each authored with a few thousandths of a unit of construction noise between its own vertices
(e.g. `PrePivot=(X=-0.001648,Y=0.001342,Z=-0.002441)`) — NOT mirrored, NOT scaled (`MainScale`/
`PostScale` both identity, no `Rotation`), so unrelated to the `c7b8b0b` determinant fix's code path
(that fix's `rot_is_pure_rotation` gate only matters for `CSG_Subtract` or the off-by-default
`ADD_RECOMPUTE_NORMAL` experiment; these are plain `CSG_Add`). Of 110 total 26-poly "loft" brushes in
the level, only these 9 are affected — a shape-family issue, not universal.

**Root cause: `bsp_validate_brush_links`'s coplanarity gate (`bspcsg.rs`, the §92-§9 "dome-cap fix")
used each poly's `verts[0]` as its on-plane reference point instead of the poly's own authored `Base`
field (T3D `Origin=`).** This function assigns each brush poly a surf-link `iLink` so coplanar
same-facing same-texture faces of ONE brush share a single `FBspSurf` (`Editor.dll 0x37290`, the gate
that already fixed the UNATCO dome-cap N=9-facets-should-be-1 case). The coplanarity test is `-0.001 <
Normal·(Base_j − Base_i) < 0.001`; the existing code computed `Base` as each poly's first vertex, on
the (undocumented, never live-checked) assumption that `FPoly::Finalize`'s "base snap" meant `Base :=
verts[0]`. For OceanLab's loft brushes this is wrong: their own vertices carry construction noise
large enough (~0.0015–0.0042, 1.5×–4× the ±0.001 band) to push some genuinely-coplanar pairs of an
otherwise-flat cap/ring outside the band, while each face's AUTHORED `Origin` sits exactly on its
intended plane (0 delta) — because `Origin`/`Base` is the texture-plane anchor point, mathematically
required to lie exactly on the polygon's plane by construction, unlike an arbitrary vertex which only
approximates it once BrushBuilder-generated coordinates carry rounding.

A pure-Python reimplementation of the documented link algorithm (`_scratch/oceanlab_link_sim.py`,
throwaway — see harness note below) against Brush784's raw T3D polys confirmed: `verts[0]`-based
linking gives 21 groups (matches native's actual isolated build exactly), `Base`(Origin)-based linking
gives 18 groups. Ran this comparison across all 110 26-poly loft brushes in the level
(`/tmp/link_sim2.py`): **exactly the same 9 brushes flip 21→18 under the Origin-based reference point;
the other 101 are byte-identical either way** — a maximally clean signal with no collateral risk
visible even before touching Rust.

**Live-verified before shipping** (per the standing no-guessing rule), isolating the leading-Add-brush
quirk out of the picture: pasting `Brush784` ALONE into a fresh `MAP NEW` gives a genuinely EMPTY
golden (0 nodes/surfs — "Unreal's world is solid by default... additive brushes only matter where
something was subtracted", `unrealed/quirks.md` "CSG model"; this is the ALREADY-documented "leading
CSG_Add into an empty world" divergence, irrelevant to this finding and NOT what's being tested here).
Fixed by pasting a synthetic ADD shell (16000³) + SUBTRACT room (4000³) around Brush784's own location
first, giving it real carved space to sit in (`oceanlab_isolate_golden.py`) — a real UED22 build (`MAP
NEW`→`EDIT PASTE`→`MAP REBUILD`→`MAP SAVE`, no lighting needed) then attributed per-actor
(`oceanlab_isolate_check.py`): **native (pre-fix) = 21 surfs for Brush784, the live editor = 18** —
exactly reproducing the isolated-brush prediction and the full-level +3 delta, confirming the
mechanism is INTRINSIC to this brush's own geometry (not contextual/interaction with the other 1885
brushes).

**Fix** (`uedcli-native/src/bspcsg.rs`, `bsp_validate_brush_links`): `base.push(p.verts.first()...)`
→ `base.push(p.base)`. `p.base` already carries the real authored `Origin` when the brush has one
(`brush_marshal.py`'s `origins_flat`, the same field already load-bearing for `pBase`/`Points` byte
parity on scaled brushes, §92 §45) and safely falls back to `verts[0]` when absent (`FPoly::new`'s
default) — so this is a strict correction with no new fallback gap. New regression test
(`validate_brush_links_uses_authored_base_not_verts0`) pins two coplanar faces whose own noisy
`verts[0]` would fail the ±0.001 band but whose authored `Base` links them correctly; the pre-existing
dome-cap test (`validate_brush_links_fuses_coplanar_same_facing_faces`) still passes unchanged (its
synthetic facets never diverge `Base` from `verts[0]`, so it couldn't have caught this).

**Result — OceanLab Lab surfs now EXACT.** Before: surfs native=11305 golden=11278 (d=+27, 9 brushes
each +3). After: **surfs native=11278 golden=11278 (d=+0), 0 differing brushes.** Nodes/leaves/verts/
points/vectors are UNCHANGED by this fix (nodes d=+465, leaves d=+86, verts d=+3980, points d=+1003,
vectors d=-66) — a separate, still-open residual, almost certainly the same class of `bsp_build`/
`FindBestSplit`-tie-break repartition-order gap already open on UNATCO/freeclinic08/nsfhq04 (see
`freeclinic08-nsfhq04-1-surf-under-build-root` above): same-face-set (surfs now exact), tree-shape-only
divergence. Not investigated further this round — per the task's own scope (surf attribution was the
assigned target; the node/leaf/vert residual is the SAME open architectural problem several other
rounds have already spent large, inconclusive effort on) and the standing no-guessing rule (no
confident root cause in hand for it).

**Non-regression, all cached goldens, geometry counts unchanged from pre-fix**: `DX.dx` exact on all 6
counts (26/26/5/250/32/6, d=+0 everywhere); NYC Bar exact on all 6 (1620/953/283/20878/2762/138,
d=+0); Wanchai Market nodes/surfs/leaves exact (11648/5284/3371, d=+0), verts+74/points+16/vectors-8
(matching the already-documented residual exactly); UNATCO nodes/surfs/leaves exact (6314/3616/762,
d=+0), verts+5/points+16/vectors+0 (matching `unatco-verts-points-residual-after-the-zone`'s own
figures exactly). `cargo test` (uedcli-native): 99/99 passed (was 99 before the new test was added —
so 100 after; re-ran the full suite post-fix, all green). Scoped pytest touching the affected native
paths (`test_native_scale`, `test_preview_native`, `test_native_surf_pan`, `test_brush_merge`,
`test_preview_faces`): 169/169 passed.

**Same mechanism likely explains part of NYC 747's parallel shape-flip** (also flipped from severe
under-build to a smaller over-build per the same breadth pass, +79 nodes/+12 surfs/-10 leaves) — not
independently re-investigated (breadth over depth per the task's own instruction), but the "small
CSG_Add PF_Semisolid decorative brush with a nonzero surf delta" shape is consistent with the same
`Base`-vs-`verts[0]` gap; worth a quick per-brush attribution check in a future round before assuming
a new mechanism there.

Harness (all under `dev/docs/spikes/2026-09-01-oceanlab-overbuild/harness/`, committed per
`dev/docs/rules/spikes.md`): `oceanlab_isolate_golden.py` (live-editor isolated golden builder, with
the synthetic ADD-shell+SUBTRACT-room context), `oceanlab_isolate_check.py` (native-vs-isolated-golden
per-brush surf attribution). The full-level attribution script (`_scratch/oceanlab_surf_diff.py`) and
the pure-Python link-algorithm simulator (`_scratch/oceanlab_link_sim.py`, `/tmp/link_sim2.py`) were
throwaway one-shot analysis, not promoted — the committed harness above is sufficient to reproduce the
live-verification step; the full-level attribution is a straightforward reuse of
`fc08_surf_diff.py`'s already-committed pattern against OceanLab's own cached trunk/golden
(`/tmp/uedcli-parity-cache/4e3757c3f3b2144f3750084db83cdbbc8bd4412047aadffa17c0494f4fa51a39/`,
worktree-local trunk copy at `_scratch/uedcli-parity-cache/<same hash>/trunk/`).

## NYC 747 -5 surf residual — root-caused and FIXED: `bsp_validate_brush_links`'s texture-identity check was never wired up, an unconditional no-op (2026-09-01)

Follow-up to the OceanLab Lab fix above, whose write-up flagged NYC 747's post-fix residual (surfs
native=2021 golden=2026 d=-5, sign FLIPPED from the pre-fix +12) as "plausibly the same mechanism,
not independently re-investigated." Directly checked: **NOT the same mechanism.**

**Per-brush surf attribution** (`fc08_surf_diff.py`'s method, new script
`dev/docs/spikes/2026-09-01-oceanlab-overbuild/harness/nyc747_surf_diff.py`) found **exactly one**
brush differs: `Brush473` (idx 300 of 373 world-CSG brushes), native=117 surfs vs golden=122 (d=-5) —
the level's entire net residual, zero cancellation. `Brush473` is a 291-poly `CSG_Add PolyFlags=32`
(PF_Semisolid) brush, unscaled/unrotated (`MainScale`/`PostScale` both identity) — the OceanLab
noisy-`verts[0]` mechanism (a construction-noise coplanarity miss) does not apply, and the sign is
opposite (native here UNDER-counts surfs; OceanLab's affected brushes OVER-counted).

**Root cause: `bsp_validate_brush_links`'s "same Texture" gate was an unconditional no-op for every
freshly-ingested brush in the whole corpus — `FPoly.texture` was never populated from the T3D
`Texture=` at brush-marshal time.** A new env-gated diagnostic (`UEDCLI_BSPCSG_LINK_DUMP=<actor_index
>|ALL`, added to `bspcsg.rs`'s `brush_loop1`, dumps each poly's resolved link root + base/normal/
texture/axes) showed **all 291 of Brush473's polys carry `texture=0`** — the `FPoly::new` default —
so `polys[i].texture != polys[j].texture` (the gate's 3rd criterion) trivially passes (0==0) for
every pair, on every brush, always. Grepping every assignment to `FPoly.texture` in the crate found
exactly one (`bspcsg.rs:1047`, `p.texture = s.texture_ref`, inside the REPARTITION reconstruction
path that rebuilds FPolys from already-resolved `BspSurf`s) — the per-poly texture NAME from the T3D
was dropped entirely in `brush_marshal.py`'s `_build_brush_input`/`lib.rs`'s `brush_from_tuple`
marshal path, which never carried a texture-identity field at all (the pre-existing 12-field PyO3
tuple-arity workaround bundled `tex_v_flat`/`origins_flat`/`vec_xform_flat`/`pans_flat` in a nested
tuple, but texture identity was never added).

Cross-checked against the real, live-editor-built full-level golden (per-poly `i_brush_poly` on each
of Brush473's 122 golden `BspSurf`s — all 122 distinct, i.e. every surviving golden surf maps to a
UNIQUE original poly index): comparing that set against native's pre-fix 118 `bsp_validate_brush_
links` groups found 5 polys (`21`, `38`, `39`, `173`, `289`) that golden keeps as separate surfs but
native merged into 5 OTHER polys' groups (`20`, `35`×2, `140`, `288`). Every one of those 5 wrong
merges pairs polys with matching plane/normal/TextureU/TextureV/PolyFlags but a DIFFERENT authored
T3D `Texture=` (e.g. poly21 `Texture=CoreTexMetal.GripMetlFloor_A` merging into poly20's `Texture=
Airfield.AF_IronWOriv_A` — two real, different textures on axis-aligned wall panels that happen to
share the same infinite plane, normal and UV-axis convention). With the gate blind to texture
identity, every such coincidence merges; the fix restores exactly the discrimination the
already-decoded algorithm calls for. (An earlier pure-Python reimplementation of the link algorithm,
run first, gave 123 groups where native's real Rust build gave 118 — confirming a hand-rolled
`FPoly::calc_normal`/link-loop reimplementation is not trustworthy evidence here; the env-gated Rust
dump, not a Python simulation, is what pinned the real mechanism.)

**Fix**: added a 5th field (`textures_flat: Vec<i32>`) to the nested marshal-tuple bundle —
`brush_marshal.py`'s `_build_brush_input` computes a per-call dedup id per poly's `Texture=` (a
`None` texture gets its own id too, so two untextured faces still compare equal, matching a real
`Material == Material` NULL-pointer compare); `lib.rs`'s `brush_from_tuple` threads it into
`FPoly.texture` per poly (absent/empty -> keeps the pre-fix default 0, so an unpopulated caller sees
no behavior change). `bsp_validate_brush_links` itself is untouched — its texture-equality check was
already correct, just fed a constant. New regression test (`brush_from_tuple_threads_per_poly_
texture_identity`, `lib.rs`) pins the round-trip and the empty-list fallback.

**Result — NYC 747 surfs now byte-exact.** Before (post-`Base`-fix, pre-this-fix): surfs
native=2021 golden=2026 (d=-5), Brush473 alone native=117 golden=122. After: **surfs native=2026
golden=2026 (d=+0), 0 differing brushes.** Nodes/leaves/verts/points/vectors unchanged (nodes d=+68,
leaves d=-10) — a separate, still-open residual, the same `bsp_build`/`FindBestSplit`-tie-break
repartition-order class already open on UNATCO/freeclinic08/nsfhq04/OceanLab Lab: same face set
(surfs now exact both times), tree-shape-only divergence. Not investigated further this round.

**Non-regression, all four required goldens** (`parity_report.py`, cached goldens, re-run fresh
after this fix): `DX.dx` exact on all 6 counts (26/26/5/250/32/6, d=+0); NYC Bar (`02_NYC_Bar.dx`)
exact on all 6 (1620/953/283/20878/2762/138, d=+0); UNATCO (`03_NYC_UNATCOHQ.dx`) nodes/surfs/leaves
exact (6314/3616/762, d=+0), verts+5/points+16/vectors+0 (matching the pre-existing `unatco-verts-
points-residual-after-the-zone` figures exactly, unchanged); OceanLab Lab (`14_OceanLab_Lab.dx`)
surfs exact (11278/11278, d=+0, unchanged from its own already-shipped fix), nodes+465/leaves+86/
verts+3980/points+1003/vectors-66 (matching that item's own documented still-open residual exactly,
unchanged). `cargo test`: 101/101 (100 pre-existing + 1 new). Scoped pytest (`test_native_scale`,
`test_preview_native`, `test_native_surf_pan`, `test_brush_merge`, `test_preview_faces`): 164/164.

Harness: new script `dev/docs/spikes/2026-09-01-oceanlab-overbuild/harness/nyc747_surf_diff.py`
(per-brush surf attribution for `03_NYC_747.dx`, `fc08_surf_diff.py`'s pattern reused). The env-gated
Rust diagnostic (`UEDCLI_BSPCSG_LINK_DUMP`, `bspcsg.rs`'s `brush_loop1`) is committed as a permanent
diagnostic (matches the existing `UEDCLI_BSPCSG_PREMERGE_DUMP`/`UEDCLI_BSPCSG_SOUP_ORDER` pattern,
zero effect on the default path). The golden `i_brush_poly` cross-check and the pure-Python link
simulator were one-shot ad-hoc analysis, not promoted beyond this write-up.

## Left uncommitted

This item's code changes (`uedcli-native/src/bspcsg.rs`, `uedcli-native/src/lib.rs`,
`uedcli/native/brush_marshal.py`) are uncommitted in the worktree `nyc747-parity-residual` per this
round's task instructions — the coordinating session verifies (full non-regression incl. re-running
`parity_report.py` on DX.dx/NYC Bar/UNATCO/OceanLab Lab) and commits.

## Vandenberg Gas +606 node over-build — root-caused to a specific brush's CsgOper, mechanism NOT understood, OPEN (2026-09-01)

Picked up `12_Vandenberg_Gas.dx` (870 brushes) as the worst-parity level with no prior root-cause
thread (flagged "a third shape, not investigated further" in
`breadth-geometry-check-on-10-new-og-levels-1-10`). Fresh rebuild against current master (post
both the OceanLab `Base`-fix `d07622e` and the NYC 747 texture-identity fix `4b7b186`) reproduces
the exact pre-fix numbers, confirming both are genuinely zero-effect here: nodes native=11289
golden=10683 (d=+606), surfs native=4556 golden=4554 (d=+2), leaves native=3334 golden=3468
(d=-134), verts d=+9480, points d=+696, vectors d=+130. `LENGTH MISMATCH` on nodes/surfs/leaves —
real tree-shape divergence, not a value mismatch at matching indices.

**Per-brush attribution** (surf-count, `nyc747_surf_diff.py`'s method, plus a second axis —
node-plane-owner count via `node.i_surf -> surf.i_actor`, `fc08_node_owner_diff.py`'s method — since
the surf delta here is tiny (+2) while nodes/verts are large, unlike the OceanLab/NYC 747 cases;
script `dev/docs/spikes/2026-09-01-vandenberg-gas-node-overbuild/harness/vandenberg_attrib.py`)
found `Brush54` (world-CSG idx=3, `CsgOper=CSG_Subtract`, 412 polys, `MainScale=(1.243502 uniform)`,
`PostScale=(1.393913,1.149680,1.158020)` non-uniform, no `Rotation`, no mirror — ruling out the
already-fixed `c7b8b0b` determinant bug) as the dominant single outlier: surf native=181 editor=71
(d=+110, level's own net is only +2 — heavy cancellation elsewhere), node-owner native=1373
editor=472 (d=+901, level's own net is +606). 403/870 brushes differ in node-owner count at all
(diffuse, abs-sum 3144 against net +606) — a similar SHAPE to the already-known diffuse
`FindBestSplit`-tie-break class (freeclinic08/nsfhq04/UNATCO), but Brush54's own single-brush
delta far exceeding the level's net delta ruled out a simple "same diffuse class" conclusion without
checking further.

**Live isolation of Brush54 alone was CONTEXT-DEPENDENT, not intrinsic** — the key finding that
redirected the investigation. Isolating Brush54 with a synthetic 20000uu ADD shell (the world is
solid by default, so a lone `CSG_Subtract` only needs an enclosing shell, no separate subtract room
— `vandenberg_isolate_golden.py`/`vandenberg_isolate_check.py`): the live editor carved 472
nodes/181 surfs (matching the full-level node-owner attribution exactly, 472=472 — confirms editor's
per-brush node ownership is context-INDEPENDENT, as expected of a well-behaved engine), but
**native produced ZERO effect** — `UEDCLI_BSPCSG_STAGE_COUNTS` showed `post-repartition nodes=6`
(identical to the bare shell, no trace of Brush54's carve at any stage). So Brush54's own geometry
in isolation is not what's broken in native; something about its REAL preceding context (not
reproduced by a synthetic shell) matters.

**Traced to the REAL preceding context**: Brush54 is world-CSG order idx=3 (4th brush); the true
first 3 are `Brush230` (idx=0, `Class=Engine.Brush`, ONE poly, `Flags=8` NotSolid, carries
`LightBrightness`/`LightHue`/`LightSaturation`/`TempScale` — none of which are normal Brush
properties, looks like a stray original-game authoring artifact — and, load-bearing: **no
`CsgOper=` line at all**), `Brush2054` (idx=1, `CSG_Subtract`, 6 polys), `Brush73` (idx=2,
`CSG_Subtract`, 6 polys). Confirmed via `uedcli.classdefaults.ClassDefaults` against the real
`Engine.u`: `Engine.Brush.CsgOper`'s class default is `CSG_Active` (ordinal 0, no override text) —
NOT `CSG_Add`. `uedcli/native/brush_marshal.py::_build_brush_input` hardcodes
`raw.get("CsgOper", "CSG_Add")` — an absent `CsgOper` is currently marshaled as an active `CSG_Add`
brush, contradicting the class default. This is the ONLY brush actor in Vandenberg Gas (and in
every other cached level trunk checked — DX.dx, NYC Bar, UNATCO, Wanchai Market, OceanLab Lab,
NYC 747, freeclinic08, nsfhq04) with a genuine (non-Mover) `Engine.Brush` and no `CsgOper=` — zero
regression surface for any already-tracked level.

**Three live A/B/C builds, decisive** (`vandenberg_csgoper_test_golden.py` +
`vandenberg_csgoper_explicit_add_golden.py`, real UED22, `MAP NEW`→`EDIT PASTE`→`MAP REBUILD`→
`MAP SAVE`), each building `[Brush2054, Brush73, Brush54]` preceded by a variant of Brush230:

| build | Brush230 variant | editor nodes/surfs/leaves/verts/points/vectors |
|---|---|---|
| A | Brush230 OMITTED entirely | 483 / 193 / 87 / 4938 / 301 / 426 |
| B | Brush230 AS AUTHORED (no `CsgOper=`) | **181 / 84 / 46 / 1904 / 184 / 182** |
| C | Brush230 with an EXPLICIT `CsgOper=CSG_Add` added (same geometry) | 483 / 193 / 87 / 4938 / 301 / 426 |

C is byte-identical to A on every count — confirms an explicit `CsgOper=CSG_Add` on this same
degenerate 1-poly NotSolid brush is a genuine no-op (consistent with the documented "additive
brushes only matter where something was subtracted", `unrealed/quirks.md` "CSG model" — a leading
Add into the by-default-solid world adds nothing new). **This REFUTES two hypotheses in sequence**:
(1) "the real editor treats a `CsgOper`-absent brush as inert/skipped" — refuted by B ≠ A; (2) "the
real editor treats a `CsgOper`-absent brush the same as an explicit `CsgOper=CSG_Add`" — refuted by
B ≠ C (if native's current "default absent CsgOper to CSG_Add" bug were the whole story, B should
equal C; it does not). B is a **third, distinct, unexplained behavior** — the real editor does
something specific to a literal `CsgOper`-absent (`CSG_Active`) brush that neither skips it nor
treats it as an ordinary Add, and that specific behavior roughly HALVES the resulting geometry of
the three subtracts that follow it. Cross-checked `_build_brush_input` and `oper_from_i32` (Rust
`lib.rs`): the Rust core has no `CsgOper::Active` variant at all (`oper_from_i32` rejects int `0`
outright, `"unknown CsgOper 0 (expect 1..=4)"`) — so today's `"CSG_Add"` Python-side default is not
just wrong-valued, it is the ONLY thing standing between this brush and a hard `BuildError`, i.e.
native has never had any representation for what B's behavior actually is.

Also re-ingested B's own saved `.dx` (`ingest_dx_trunk.py`) and confirmed Brush230 re-exports with
**still no `CsgOper=` line** — the editor does not silently rewrite/coerce it to an explicit value on
round-trip, so its true resolved oper is genuinely `CSG_Active`, yet it still has this large,
concrete structural effect. Native, checked on the SAME three sets: A=native 483 (exact match to
editor — confirms native is correct for Brush2054/73/54 alone), B=native 504 (only +21 over A, far
short of editor's -302-from-A collapse to 181) — native's current handling reproduces neither A/C's
correct no-op-adjacent value for a real Add nor B's real, drastic reduction.

**NOT root-caused further — genuinely open.** What the real UnrealEd `csgRebuild` does internally
for a brush whose `CsgOper` is literally `CSG_Active` (why it structurally reduces, not omits or
adds) is unknown; establishing it needs disassembly-level work (`unrealed/extracting-from-dll.md`)
not done this round — a live black-box A/B/C test can prove WHAT happens but not WHY. Per the
standing no-guessing rule, no fix is shipped: native has no representation for `CSG_Active` at all
(Rust rejects the ordinal outright), and shipping either "treat as Add" (already refuted, and
already what happens today via the Python default) or "skip/exclude from world CSG" (also refuted
by B ≠ A) would be shipping a KNOWN-WRONG behavior with more confidence than warranted. Given
`bspcsg.rs`'s own already-filed `first_add_seed` gap describes a superficially similar "leading Add
behaves unexpectedly" class, it was directly checked and ruled out here (C reproduces A exactly, so
a genuine leading `CSG_Add` on this same geometry does NOT trigger any shell-mismatch anomaly) —
this is a distinct, new, unexplained mechanism, not that already-known one.

Whether this same mechanism explains any of the remaining diffuse 402-brush node-owner delta
elsewhere in the level (net +606 against Brush54's own +901) was not checked further — Brush230 is
the only `CsgOper`-absent world-CSG brush in the level, so if it IS the root cause of Brush54's
divergence (plausible given the isolation test showed Brush54 alone, against a real shell, is
correct — it's the PRECEDING real context that's wrong, and Brush230 is the one confirmed-different
element of that context), it likely also explains a meaningful share of the diffuse residual
elsewhere, but this was not measured (would need a live full-level A/B, expensive, out of this
round's scope).

**No fix shipped, no code changed.** Filed as board item
`vandenberg-gas-csg-active-csgoper-brush-causes` (inbox). Harness (all committed,
`dev/docs/spikes/2026-09-01-vandenberg-gas-node-overbuild/harness/`):
`vandenberg_attrib.py` (per-brush surf + node-owner attribution), `vandenberg_isolate_golden.py` +
`vandenberg_isolate_check.py` (Brush54-alone live isolation), `vandenberg_csgoper_test_golden.py` +
`vandenberg_csgoper_test_compare.py` (the A/B live builds), `vandenberg_csgoper_explicit_add_golden.py`
(the C live build), `vandenberg_csgoper_native_compare.py` (native-vs-editor on sets A/B).

**Non-regression**: no code changed this round, so no re-verification was needed; the fresh rebuild
at the top of this entry (confirming both prior fixes are genuinely zero-effect on Vandenberg Gas)
is the only measurement taken against already-shipped code.

## Session status snapshot (2026-09-01, before a context compaction)

Written to survive a compaction — captures what's fixed, what's open, and what's in flight right now.

**Parity: still zero levels at full byte parity.** 30% floor (≥6 of 21) unmet.

**Shipped this session (all committed to master, all live-verified or non-regression-checked):**
- `zones.rs::assign_leaves` DFS visit-order fix (`i_leaf` numbering, closed DX.dx's node array).
- `light.rs` row-padding-carry fix (`1ef4fe4`) — NYC Bar shadow bits 99.76%→100%, UNATCO
  99.27%→100%; records NYC Bar 87.7%→93.1%, UNATCO 83.6%→90.9%.
- `permeating_lights.rs`'s `split_with_plane_fast` decode (`f9d2e73`) — port correct, deliberately
  NOT wired into `bake` (owner ruling stands: `iPermeating=-1` honest stub beats 95%-correct data).
- `parity_report.py` resolved-identity comparison for `texture_ref`/`i_actor` (`dcc08db`) — proven
  the ONLY definition of correctness these two fields can ever have (raw-byte matching is
  categorically impossible: viewport-camera exports encode lost UI session state, actor bodies
  carry provably non-deterministic `LatentAction` bytes).
- `bsp_validate_brush_links` fixed twice, same shared function, both live-verified against a real
  UED22 build: (1) `d07622e` — use authored `Base`, not `verts[0]`, for the coplanarity check
  (closed OceanLab Lab's +27 surf gap to 0). (2) `4b7b186` — actually populate `FPoly.texture` at
  marshal time, it was an unconditional no-op before (closed NYC 747's -5 surf gap to 0).

**Still open, each with a board item:**
- `p_base` (Points-array intra-block order) — 5 rounds (9-13) on DX.dx/UNATCO/Wanchai. Mechanism
  fully characterized for both unsplit AND split-fragment cases (live gdb, multiple synthetic
  brushes). A real incremental point-pool architecture was attempted (`6ba3f2b`, gated off,
  measured WORSE) and round 14 found WHY: `bspRefresh` never runs during brush CSG at all, it's a
  separate post-CSG rebuild-phase call, not per-brush. The real rebuild-phase call site and its
  scaling on deep recursion (UNATCO/Wanchai) are still unknown. Thread:
  `texture-ref-i-actor-divergence-traced-to-golden`.
- `node_flags` `0x40`/`0x80` — static disassembly found a real `bspRefresh` block-copy site that can
  carry stale flag bytes, but whether its source content is real state or relocated garbage is
  unconfirmed. `NODE_FLAGS_NOISE_MASK` stays as-is. Thread:
  `node-flags-0x40-0x80-divergence-from-movers-no`.
- Lighting `grid`-only bucket (Points/Vectors ULP-level value drift) — traced to CSG_Add faces
  keeping the authored (lossy 6-decimal-text) normal where the real editor recomputes it from the
  winding. A gated experiment (`UEDCLI_BSPCSG_ADD_RECOMPUTE_NORMAL`, `81e64c9`) cuts the mismatch
  54-85% but contradicts an existing castle-bastion-derived test — NOT shipped as default, needs
  live gdb confirmation or an explicit owner yes. Thread: `lighting-bits-only-divergence-localizes-to`.
- 3 corpus levels have no cached golden at all: `Endgame4` (extraction gap, unrelated), `smuggler`
  and `nyc-street` (both crash at `EDIT PASTE` right after `MAP NEW`, not reproduced live this
  session). Thread: `wanchai-self-build-edit-paste-crash` (same crash signature).
- `12_Vandenberg_Gas.dx` — `Brush230`, a `CsgOper`-absent `Engine.Brush` (real class default
  `CSG_Active`, not `CSG_Add` as native assumes), has a real, live-A/B/C-proven ~2.7x geometry
  reduction on the brushes that follow it. Owner ruling: reproduce it faithfully (it's genuine
  original-game level data, not tooling corruption) even though the brush itself looks like a
  stray/mistaken authoring artifact — comment the code, flag for future reconsideration, don't
  silently correct the data. Mechanism not yet disassembly-confirmed. Thread:
  `vandenberg-gas-csg-active-csgoper-brush-causes`.

**In flight right now (dispatched, not yet landed — check for their board items/ledger entries
before re-dispatching either):**
- Disassemble `csgRebuild`'s real `CsgOper==CSG_Active` dispatch and implement it (Rust `CsgOper`
  enum + `brush_marshal.py`'s wrong `CSG_Add` default), per the owner ruling above. Non-regression
  bar: DX.dx, NYC Bar, UNATCO, OceanLab Lab, NYC 747 (all 5 already-fixed goldens) plus the existing
  A/B/C golden data (`dev/docs/spikes/2026-09-01-vandenberg-gas-node-overbuild/harness/`).
  Board item: `vandenberg-gas-csg-active-csgoper-brush-causes`.
- `04_NYC_NSFHQ.dx`'s node/leaf/vert under-build (nodes d=-92, leaves d=-26, verts d=-1774,
  points d=-129) — the existing `freeclinic08-nsfhq04-1-surf-under-build-root` thread only ever
  explained a tiny `+1` surf delta (`Brush531`/`Brush143` `CSG_Add`+`PF_Semisolid` misclassification);
  this much larger residual is unexplained. `08_NYC_FreeClinic.dx` has a similar-shaped unexplained
  residual and shares the narrow prior thread — worth checking for a shared mechanism.

**Standing process discipline this session** (see "Standing directives" above for the owner-given
ones): before copying a subagent's file into the main checkout, diff it against the file's CURRENT
committed HEAD to confirm it's a pure addition — several rounds this session (light30, permeating,
oceanlab, nyc747, vandenberg) forked their worktree before a LATER commit landed, and a naive
wholesale overwrite silently deleted that later content; the fix each time was extracting only the
genuinely-new section and appending it onto the current HEAD, not trusting the worktree's full file.
Also: after any native code change, force-verify the Python-importable `.venv` extension is
genuinely freshly built (check its `.so` mtime against your last source edit) before trusting any
parity measurement — `bin/test`'s own build-skip-if-no-pytest-match caching silently produced a
stale-binary false negative on the NYC 747 round.

## Vandenberg Gas CSG_Active mechanism — DECODED via disassembly, FIX SHIPPED (2026-09-01, round 2)

Follow-up to the entry above. Disassembled `bspBrushCSG` (`Editor.dll 0x355e0`) directly against
this worktree's own `uned/UED22/Editor.dll` (📖, `harness/adis.py`/`pe.py`, capstone) rather than
re-deriving from the prior spike's `sections/10-bsp-csg-build.md`/`re-raw-zones/
bspbrushcsg-filter-decode.md` write-ups (both already fully cover the Add/Subtract/Intersect/
Deintersect dispatch but never mention `CsgOper=0`, since no known level authored one before
Brush230 surfaced it).

**The mechanism.** Every `CsgOper` dispatch inside `bspBrushCSG` that gates node/surf/vert output is
a LITERAL equality test against a specific ordinal — never a range/validity check — so ordinal 0
(`CSG_Active`) falls through each one into the "not this specific value" branch, which is the
SUBTRACT-shaped one at every site that matters for geometry:
- **`subtractMask`** (`0x10035688`): `mov [local],0x28; cmp CsgOper,1; cmovne eax,[local]` — mask is
  `0x28` (`PF_Semisolid|PF_NotSolid`) whenever `CsgOper != 1`, so `Active` strips `PF_NotSolid` off
  Brush230's own (authored-NotSolid) poly exactly as a real Subtract would — the "acts solid despite
  being authored NotSolid" mechanism.
- **LOOP-2 pass-1 filter func** (`0x10035a84`-`0x10035a95`): `mov eax,SubtractFunc(0x348c0); cmp
  CsgOper,1; cmove eax,AddFunc(0x31770)` — Subtract is the pre-cmove DEFAULT, overridden to Add only
  on a literal `CsgOper==1`.
- **World-thru-brush leaf func** (`0x33472`-`0x1003347f`, independently re-disassembled — already
  decoded in `re-raw-zones/bspbrushcsg-filter-decode.md` for Add/Subtract, not previously connected
  to this investigation): `mov eax,SubtractFunc(0x34980); cmp CsgOper,1; cmove eax,AddFunc(0x31b90)`
  — same shape.
- **`CsgOper==3||4` branch-away** to the Intersect/Deintersect tail (`0x100359d3`-`0x100359df`,
  `cmp eax,3/4; je 0x35ab3`) does NOT match `CsgOper=0`, so `Active` falls through into the shared
  Add/Subtract body instead of being diverted — confirms it is a REAL participant, not skipped.
- One and only one site keys on the LITERAL value 2 (not "not Add"): a `Model->NumZones=0` reset
  (`0x100356a2`, `cmp CsgOper,2; jne skip`) — `Active` does NOT trigger it. Confirmed orthogonal to
  node/surf/vert output (`Model+0x100`=`NumZones`, per `re-raw-zones/passC-zonesetter.md`; zones are
  recomputed wholesale by the later `TestVisibility` flood and are outside native's current
  single-zone-first-cut scope, §8.3 of `sections/10-bsp-csg-build.md`).
- Also checked `csgRebuild`'s own PASS-A structural loop (`0x1004a650`+): the semisolid+Add "defer to
  detail pass" `continue` (`0x1004a804 cmp byte[actor+0x20c],1`) is ALSO a literal `CsgOper==1` test
  (bonus finding: `Actor+0x20c` is the in-memory `CsgOper` field offset) — `Active` is not diverted
  there either, so it reaches `bspBrushCSG` as an ordinary PASS-A structural brush, as the live A/B/C
  test's magnitude already implied.

**Net conclusion: `CsgOper::Active` is, for BSP geometry purposes, dispatched IDENTICALLY to
`CsgOper::Subtract`** inside `bspBrushCSG` — not a distinct "structural flag" (hypothesis (a) from
this round's task, refuted: nothing in `bspBrushCSG` special-cases ordinal 0 as anything other than
"not 1/not 3/not 2"), and not a coincidental curve-fit — every dispatch point that differs between
Add and Subtract was independently disassembled and found to route `Active` into Subtract's own
branch, by the mechanical fact that x86-compiled `(CsgOper==X) ? A : B` ternaries take the `B` arm
for ANY non-`X` value, ordinal 0 included.

**One deliberately unresolved residual.** `bspcsg.rs`'s pre-existing `oper == CsgOper::Subtract`
gate on the §92 §48 "Subtract recomputes the winding normal, Add keeps authored" rule was NOT
extended to `Active` — that rule was derived empirically from a real-level census containing only
Add/Subtract brushes, never disassembled to instruction level, so there is no evidence it keys on
literal `CsgOper==2` vs. "not Add" like every other site above. Extending it on pattern-alone would
be exactly the un-derived guess the no-guessing rule forbids. Flagged in code (`bspcsg.rs` comment
next to the `oper == CsgOper::Subtract` condition). Irrelevant to Brush230 itself (a single poly).

**Fix shipped**: `uedcli-native/src/csg.rs` — new `CsgOper::Active` enum variant (with the mechanism
above as its doc comment); `csg.rs`'s own `bsp_brush_csg`/`point_in_solid` dispatch already used
`_ => Subtract-shaped` wildcard arms, so they needed no change. `uedcli-native/src/lib.rs` —
`oper_from_i32` now maps int `0` to `CsgOper::Active` instead of erroring. `uedcli-native/src/
bspcsg.rs` — the REAL bug: `bsp_brush_csg`'s early guard `if oper != Add && oper != Subtract:
return` used to silently no-op any newly-representable `Active` brush (the ALREADY-REFUTED "skip"
hypothesis, live build A); narrowed to `if oper == Intersect || oper == Deintersect: return` so
`Active` falls through to the shared body. Also broadened the world-thru-brush leaf-func selector
(`oper == Subtract` → `oper != Add`) per the disassembly-confirmed pattern above. `uedcli/native/
brush_marshal.py::_build_brush_input` — default `raw.get("CsgOper", "CSG_Add")` →
`raw.get("CsgOper", "CSG_Active")`, matching `Engine.Brush.CsgOper`'s real class default (the
`_CSG_OPER` string→ordinal table already had `"CSG_Active": 0`; only the default string was wrong).
Every comment flags this as reproducing likely-unintentional level authoring, per the owner ruling.

**TDD**: `csg_active_dispatches_exactly_like_subtract` (`bspcsg.rs`) pins that a single-brush
`CsgOper::Active` build (a) is NOT a no-op (6 surfs carved, not an empty world — rules out the
refuted "skip" hypothesis regressing) and (b) is node/surf/vert/point/vector-count IDENTICAL, with
identical surf normals, to the same geometry built as `CsgOper::Subtract`. `bin/test -k bspcsg`:
cargo test 102/102 (was 101, +1 new), pytest 78/78 (native ext freshly rebuilt — `.so` mtime
confirmed newer than every edited source file). Scoped pytest matching the standard native-path set
(`test_native_scale`/`test_preview_native`/`test_native_surf_pan`/`test_brush_merge`/
`test_preview_faces`): 169/169.

**Live re-verification against this item's own A/B/C harness** (goldens rebuilt fresh — the prior
round's worktree and its `_scratch/` goldens no longer exist; harness scripts' hardcoded `ROOT`/
`TRUNK` repointed at the current worktree, reusing its already-extracted trunk):
- Fresh live-editor rebuild of A/B reproduces the prior round's numbers exactly (483/193/87/4938/
  301/426 and 181/84/46/1904/184/182) — confirms the golden data is reproducible, not a fluke.
- Fresh live-editor rebuild of C (explicit `CsgOper=CSG_Add`) again reproduces A exactly
  (483/193/87/4938/301/426) — unaffected by this round's change (as expected: C never touches the
  `CsgOper::Active` path at all).
- **Native vs. editor, set B (Brush230 as authored, the motivating case)**: nodes/surfs/leaves/
  points now EXACT (181/84/46/184, `d=+0` each — was 504/unmeasured pre-fix, an unmeasured-direction
  wrong value). verts `d=+21` (1925 vs 1904), vectors `d=+0`. **Set A (baseline, Brush230 excluded —
  untouched by this fix)** shows the SAME class of small residual (verts `d=+71`, vectors `d=-2`,
  nodes/surfs/leaves/points otherwise exact) — proves the small vert/vector residual is a PRE-
  EXISTING, separate class (present even with Brush230 absent entirely), not something this fix
  introduced or should chase (out of scope; likely the same vertex-pool-dedup/tie-break class already
  open on UNATCO `d=+5` verts and others).

**Full-level Vandenberg Gas re-measure** (`parity_report.py`, fresh native rebuild, cached golden
reused — golden is a pure real-editor build, independent of native code):
before (this entry's own pre-fix numbers, confirmed unchanged from the entry above) nodes
native=11289 golden=10683 `d=+606`, surfs `d=+2`, leaves `d=-134`, verts `d=+9480`, points `d=+696`,
vectors `d=+130`; **after**: nodes native=10715 golden=10683 **`d=+32`**, surfs native=4554
golden=4554 **`d=+0` (exact)**, leaves native=3473 golden=3468 `d=+5`, verts native=144824
golden=144950 **`d=-126`**, points native=15069 golden=15030 `d=+39`, vectors native=1505
golden=1523 `d=-18`. The dominant residual is closed (node delta cut ~95%, vert delta cut ~99%);
`LENGTH MISMATCH` no longer describes a single dominant cause — the remaining `d=+32` nodes is
presumably (not measured this round) some share of the diffuse 402-brush node-owner residual this
entry's round 1 flagged as "unmeasured whether related." Not full byte parity yet — a distinct,
smaller, unexplained residual remains, out of THIS round's scope.

**Non-regression, all 5 required goldens** (`parity_report.py`, fresh native rebuild against cached
goldens): `DX.dx` exact on all 6 counts (26/26/5/250/32/6, `d=+0`, UNCHANGED). `02_NYC_Bar.dx` exact
on all 6 (1620/953/283/20878/2762/138, `d=+0`, UNCHANGED). `03_NYC_UNATCOHQ.dx` nodes/surfs/leaves
exact (6314/3616/762, `d=+0`), verts `d=+5`/points `d=+16`/vectors `d=+0` — matches the documented
pre-existing residual exactly, UNCHANGED. `14_OceanLab_Lab.dx` surfs exact (11278/11278, `d=+0`),
nodes `d=+465`/leaves `d=+86`/verts `d=+3980`/points `d=+1003`/vectors `d=-66` — matches its own
documented still-open residual exactly, UNCHANGED. `03_NYC_747.dx` surfs exact (2026/2026, `d=+0`),
nodes `d=+68`/leaves `d=-10` — matches, UNCHANGED (verts/points/vectors not individually re-quoted
in the prior entry but consistent: `d=+698`/`d=+227`/`d=-7`). Every one of these 5 levels is
confirmed to contain NO `CsgOper`-absent `Engine.Brush` (per round 1's corpus check), so zero effect
was the expected and observed result on all five.

**Left uncommitted** — this round's code changes (`uedcli-native/src/csg.rs`, `uedcli-native/src/
lib.rs`, `uedcli-native/src/bspcsg.rs`, `uedcli/native/brush_marshal.py`) are uncommitted in the
worktree `vandenberg-csg-active`; the coordinating session verifies independently and commits.

Harness: reused all of round 1's committed scripts (`dev/docs/spikes/2026-09-01-vandenberg-gas-
node-overbuild/harness/`), only repointing their hardcoded `ROOT`/`TRUNK` at the current worktree —
no new harness files this round.

## Vandenberg Gas mechanism confirmed on freeclinic08/nsfhq04: the CsgOper-absent-first-brush pattern recurs, and fully explains freeclinic08's structural-only residual (2026-09-01)

Continuation of `freeclinic08-nsfhq04-1-surf-under-build-root`'s 3rd-round finding ("Poly-list order
divergence localized one stage further... would need a live per-brush Pass-1 tree-shape trace to
attribute the +70-poly PREMERGE gap to specific brushes"). Took a cheaper route than new GDB
instrumentation: Pass 1 is a pure sequential fold over brushes in CSG order (brush *i* depends only
on `1..i-1`; the ONE world-level `bspRepartition` runs once, after all of them), so truncating the
freeclinic08 structural-only 141-brush list to its first *N* and building BOTH sides — native
in-process (`uedcli_native.build_geometry_bspcsg`), editor via a fresh `build_ued_golden.py --world-
only --no-light --no-obj-load` `MAP REBUILD` — reproduces the true Pass-1 state after *N* incremental
adds. Binary-searching *N* by final node/surf/leaf count localizes the first diverging brush with no
new disassembly (new harness: `prefix_search_lib.py`'s `PrefixSearch.binary_search`).

**Result: prefix *n*=12 is byte-exact; *n*=13 (adding `Brush47`, a plain 6-poly axis-aligned
`CSG_Subtract` box) diverges by nodes=-12/leaves=-4.** Per-brush node-owner attribution on this
13-brush minimal case (`node.i_surf -> surf.i_actor`) found the missing 12 nodes NOT on Brush47 —
spread across `Brush1`(-2)/`Brush4`(-2)/`Brush7`(-2)/`Brush9`(-2)/`Brush10`(-4), all brushes added
BEFORE it. Same "diffuse repartition reshuffling" shape as every prior round — until checking WHAT
was common to every single prefix tested (including the trivial *n*=1): **`Brush586`, freeclinic08's
very first world-CSG brush, has no `CsgOper=` property.** `Engine.Brush.CsgOper`'s real class default
is `CSG_Active` (ordinal 0); `brush_marshal.py::_build_brush_input` currently defaults an absent
`CsgOper` to `CSG_Add` — **exactly the mechanism `vandenberg-gas-csg-active-csgoper-brush-causes`
(above) found and left unfixed**, live A/B/C-verified there to be neither a no-op nor equivalent to
Add. That item's own scope claim ("`Brush230` is the ONLY non-Mover `Engine.Brush` actor with no
`CsgOper=` across every cached level trunk checked... `freeclinic08`, `nsfhq04`") is **wrong** —
freeclinic08's `Brush586` and nsfhq04's `Brush8321` are both also `CsgOper`-absent, and BOTH sit at
world-CSG index 0, same as `Brush230`. Corrected in that item directly.

**Decisive live test (`fc08_n12_noactive_search.py`)**: rebuilt the same brush sets with `Brush586`
removed, both native and live-editor, `--world-only --no-light --no-obj-load` throughout.

| set | native (n/s/l) | editor (n/s/l) | delta |
|---|---|---|---|
| 12 brushes (`Brush1`..`Brush47`, minus `Brush586`) | 68/62/15 | 68/62/15 | **+0/+0/+0** |
| Full 140 structural brushes (minus `Brush586` only) | 1135/658/284 | 1135/658/284 | **+0/+0/+0** |

**`Brush586` alone fully explains freeclinic08's entire structural-only residual** (WITH it: native
1141/editor 1179 nodes, native 290/editor 313 leaves — the -38/-23 this whole thread chased since
round 1). The diffuse 75-of-141-brush node-owner spread every earlier round measured was a real
symptom at the wrong level of attribution: ONE mishandled brush cascades through the whole
incremental Pass-1 tree; by the time you inspect FINAL node ownership it reads as scattered
cancellation across dozens of unrelated brushes.

**nsfhq04 — same mechanism confirmed present and significant, but NOT sufficient alone**
(`nsfhq04_noactive.log`). Removing `Brush8321` (world-CSG index 0, same no-`CsgOper=` pattern) from
the full 660-brush structural-only set: native 4958/2170/1484, editor **4721/2170/1438 — d_nodes=+237,
d_leaves=+46**, WORSE than the WITH-`Brush8321` baseline (native 4975/editor 4958, d_nodes=+17/
d_leaves=-26). Native's own count barely reacts to removing the brush (4975→4958, -17) while the real
editor's build swings by 237 nodes — the true `CSG_Active` effect on this level is large and native's
`CSG_Add`-substitute badly under-reproduces it in both directions; the closer WITH-`Brush8321` number
was accidental cancellation, not correctness. Surfs stay exact regardless (2170=2170 both ways —
independent of the semisolid/Pass-2 surf axis, already root-caused separately as `Brush531`'s
`PF_Semisolid` misclassification).

**No fix shipped** — same standing reason as Vandenberg's own entry: no Rust representation for
`CsgOper::Active`, real mechanism unknown without disassembly, not attempted this round (per the
no-guessing rule). This round's contribution: confirms the mechanism recurs (3 levels now, all with
the pattern at world-CSG index 0 — a level's first-ever-placed brush), and that it can be the SOLE
explanation for a level's residual (freeclinic08) or a major-but-partial one (nsfhq04) — materially
raising the priority of the already-filed disassembly work over treating it as a one-off curiosity.

**Methodology bug found and fixed mid-round, worth flagging for any other concurrent investigation
this session**: this round's harness initially imported `uedcli`/`uedcli.native.brush_marshal` via
`sys.path.insert(0, "/workspace/uedcli")` — the shared MAIN CHECKOUT, not this investigation's
isolated worktree. A concurrent agent had uncommitted, actively-changing edits to that exact file
(the same Vandenberg `CsgOper` work) in the main checkout; native's own compiled `.so` was correctly
isolated (built in-worktree) but the PYTHON marshal layer was silently reading whatever the other
session's in-flight edit happened to be at that instant. Symptom: `BuildError: unknown CsgOper 0`
appeared and disappeared across byte-identical reruns of the same script with no source changes on
this worktree's own side (confirmed via `git status`/mtime — genuinely a different process's writes
to a different path, not a caching artifact). Fixed by pointing every `sys.path` entry at the
worktree (`.../nsfhq04-residual-investigation/`) instead of the bare root; `prefix_search_lib.py`
carries the fix and the full explanation in its header comment. Re-verified determinism (3 identical
reruns, same result) after the fix. Any other script from this session importing `uedcli` via a bare
`/workspace/uedcli` path rather than its own worktree should be treated as suspect and re-verified.

**Non-regression**: no `bspcsg.rs`/`brush_marshal.py` changes shipped this round (investigation +
harness only), so no regression gate re-run needed. `regression_gate.py` last known state unaffected.

Harness (committed, `dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness/`):
`prefix_search_lib.py` (shared prefix binary-search library), `fc08_prefix_search.py`/
`nsfhq04_prefix_search.py` (level-specific CLIs), `nsfhq04_filter_trunk.py` (structural-only trunk
extractor), `fc08_n13_node_owner.py` (per-brush node-owner attribution), `fc08_n12_noactive_search.py`
(the decisive `Brush586`-removal test). Logs under `.../logs/`. Board:
`freeclinic08-nsfhq04-1-surf-under-build-root` (this thread, 4th continuation) and
`vandenberg-gas-csg-active-csgoper-brush-causes` (corrected + cross-referenced).
is the only measurement taken against already-shipped code.

## Confirmation: the shipped CsgOper::Active fix (528e602) already closes FreeClinic08's structural residual (2026-09-01)

Re-measured FreeClinic08 and NSFHQ04 directly against the already-shipped fix (predicted by the
prior round's isolated-brush-removal test, not yet checked at the time it landed).

**FreeClinic08: nodes/surfs/leaves now ALL byte-count exact** (was `LENGTH MISMATCH` on all three;
nodes d=-30, surfs d=+1, leaves d=-23 -> all d=+0). Residual verts d=+1/points d=+20 (was -729/-23)
— a near-total closure, exactly matching the prior round's prediction that `Brush586` alone fully
explained this level's structural residual. FreeClinic08 is now one of the geometry-closest levels
in the corpus, alongside DX.dx/NYC Bar.

**NSFHQ04: unchanged** (nodes d=-92, surfs d=+1, leaves d=-26, all still `LENGTH MISMATCH`) — matches
the prior round's own finding that `Brush8321` is a major but not sole driver there (removing it made
native's count MOVE, not converge), so correctly reproducing it doesn't close the gap alone.

## Area51 Entrance / Training Final breadth check: CsgOper-absent-first-brush pattern does NOT apply; Area51's entire residual localized live to one brush (`Brush1852`), mechanism not yet found (2026-09-01)

Checked whether the shipped `528e602` (`CsgOper::Active`) fix retroactively closes any of Area51
Entrance's or Training Final's residual, per the standing 3-for-3 pattern (Vandenberg Gas/
FreeClinic08/NSFHQ04, all `CsgOper`-absent world-CSG-index-0 brushes). **Negative for both**: Area51's
first world-CSG brush (`Brush529`) and Training Final's (`Brush55`) both carry an explicit
`CsgOper=CSG_Subtract`; a full-corpus scan found **zero** `CsgOper`-absent `Engine.Brush` actors across
either level's entire world-CSG brush set (1343 for Area51, 764 for Training Final). Also algebraically
inert here regardless: `528e602`'s only behavior changes are gated on `CsgOper::Active`, which neither
level's brush set contains at all (both are pure Add/Subtract).

**Stale-`.venv`-build false alarm caught and corrected.** A first measurement (before any deliberate
rebuild) showed Area51 catastrophically under-built (nodes native=3834 vs golden=12630) — wildly
inconsistent with the corpus table's recorded `d=+85`. Bisected by checking out
`uedcli-native/src`+`uedcli/native/brush_marshal.py` at `c7b8b0b`→`d07622e`→`4b7b186`→`528e602` (current
HEAD) into the worktree and rebuilding via `bin/test -k bspcsg` at each point: all four give the
correct `d=+85`, proving the bad reading was a stale/incorrectly-built `.venv` extension (mtime looked
newer than source but content wasn't current) — exactly the standing-directive trap, not a real
regression. Source restored to HEAD before continuing; **fresh re-measure confirms both levels'
residuals are UNCHANGED from the last breadth pass**: Area51 nodes native=12715 golden=12630 `d=+85`,
surfs exact `d=+0`, leaves native=3315 golden=3264 `d=+51`, verts `d=+1055`, points `d=+99`, vectors
`d=-9`. Training Final nodes native=11227 golden=11122 `d=+105`, surfs exact `d=+0`, leaves native=861
golden=848 `d=+13`, verts `d=+1464`, points `d=+286`, vectors `d=+11`. Both geometry 1/6 (surfs only).

**Static per-brush node-owner attribution (final-tree) is diffuse on both — the fc08/nsfhq04
"wrong level of attribution" trap, confirmed again.** Area51: 548/1343 brushes differ (abs-sum 2095,
net `+85`), no dominant outlier. Training Final: 297/764 brushes differ (abs-sum 1533, net `+105`);
notable but unconfirmed lead — 4 near-consecutive small (6-poly `CSG_Add`) brushes `Brush907`/`909`/
`911`/`915` (world-CSG idx 660-668) carry large partially-offsetting diffs (`+71`/`+71`/`-52`/`+77`),
reminiscent of the still-open `smuggler-4-surf-delta-traced-to-4-pf-semisolid` repeated-composite-prop
shape — not live-verified this round.

**Area51: live prefix binary search (reusing `prefix_search_lib.py` from
`dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness/`, same method that found FreeClinic08's
`Brush586`/NSFHQ04's `Brush8321`) localizes the ENTIRE residual to ONE brush.** Full prefix (n=1343)
reproduces `d_nodes=+85 d_surfs=+0 d_leaves=+51` exactly (harness validated against `parity_report.py`).
Binary search: n=1 exact; n=672 already diverges (`d_nodes=+169 d_leaves=+54` — non-monotonic, more
than the final delta, so later brushes partially cancel it); converges to **n=506 (`Brush1851`) exact,
n=507 (adding `Brush1852`) diverges** (`d_nodes=+48 d_surfs=+0 d_leaves=-18` at that prefix size).

**Decisive test: removing `Brush1852` from the FULL 1343-brush level closes the residual to ZERO on
all three counts**, both sides freshly rebuilt (native in-process, editor via `build_ued_golden.py
--world-only --no-light --no-obj-load`): native (no `Brush1852`) nodes=12580 surfs=6057 leaves=3264;
editor (no `Brush1852`) nodes=12580 surfs=6057 leaves=3264 — **`d_nodes=+0 d_surfs=+0 d_leaves=+0`**.
Same shape as FreeClinic08's `Brush586`: one brush fully explains a level's entire structural residual.

**The isolated addition's own numbers show WHERE it goes wrong.** Adding `Brush1852` to the 1342-brush
base: native gains **+135 nodes, +51 leaves**; the real editor gains **+50 nodes, +0 leaves** — the
editor absorbs this brush's CSG_Add with no new leaf region at all, native creates 51 new ones.
`Brush1852` (`CsgOper=CSG_Add`, 6 polys, `Rotation=(Yaw=-49152)`, no mirror scale) is one of 4
placements of the same-shape prop (`Brush1849`/`1850`/`1851`/`1852`, all identical 6-poly geometry and
rotation) — the first 3 (different `Location`s, all exact through n=506) build byte-identical, the 4th
alone diverges, so the divergence is NOT the brush's own geometry (proven identical to 3 exact copies)
but something about how it CSGs against the world tree accumulated by that point (its `Location`
differs from the other 3, suggesting the trigger is positional/context-dependent, not the brush shape).

**No fix shipped — mechanism not disassembly-confirmed, per the no-guessing rule.** The shape (a small
`CSG_Add` producing extra native leaves while the editor absorbs it with none) is suggestive of an
Add-brush-largely-inside-solid over-fragmentation class, but no live capture ties it to a specific
`bspcsg.rs` code path this round. Training Final not live-localized (static lead only, see above,
followup). Non-regression: no code changed this round, no gate re-run needed. Board:
`area51-entrance-training-final-residual-localized` (new item this round).

Harness (this worktree, not yet committed to a spike dir — coordinating session should commit under
`dev/docs/spikes/` if kept): `_scratch/area51_attrib.py`/`_scratch/tf_attrib.py` (static per-brush
node-owner attribution, `vandenberg_attrib.py`-style), `_scratch/area51_prefix_search.py` (prefix
binary search, wraps `prefix_search_lib.PrefixSearch` with this worktree's paths),
`_scratch/area51_remove1852.py` (the decisive removal test).

## Session status snapshot #2 (2026-09-01, before another context compaction)

Supersedes nothing in the first snapshot (search "Session status snapshot (2026-09-01, before a
context compaction)") — this one covers everything that happened AFTER it, once the owner pivoted
the sweep to the WORST-parity levels instead of the closest ones.

**Parity: still zero levels at full byte parity.** Geometry-6/6 count-exact: 3/20 measured levels
(`DX.dx`, and two `NYC_Bar` cache entries — `02_`/`08_`). `DX.dx`'s nodes array remains the only
content-exact array anywhere in the corpus. Full fine-grained table generated and shown to the
owner as an artifact this round (not reproduced here — regenerate via `parity_report.py` for exact
current numbers, this ledger tracks mechanisms, not a live scoreboard).

**Shipped this stretch (all committed to master, all live-verified, all independently reverified
with a genuinely fresh rebuild before commit):**
- **`528e602` — added `CsgOper::Active`, disassembly-confirmed to dispatch inside `bspBrushCSG`
  identically to `Subtract`** (three independent dispatch sites, all literal-ordinal equality
  tests, never range checks). `Engine.Brush.CsgOper`'s real class default is `CSG_Active` (0), not
  `CSG_Add` as `brush_marshal.py` assumed for any brush with an absent `CsgOper=`. Root cause: a
  brush actor that never went through a real `BRUSH ADD`/`SUBTRACT` exec command (i.e. a level's
  own first-ever-placed brush, before the original 1999 author picked an explicit op) silently
  carries this default. **Owner ruling, pinned above under "Standing directives": reproduce this
  faithfully even though the triggering brush looks like unintentional authoring — never silently
  correct the data.** Closed Vandenberg Gas's dominant residual (nodes +606→+32, surfs now exact).
- **The same mechanism, once shipped, retroactively fixed a level nobody had directly targeted**:
  FreeClinic08's nodes/surfs/leaves are now ALL byte-count exact (was `LENGTH MISMATCH` on all
  three) — its own `Brush586` is the same class-default-`CsgOper`-absent pattern. Found only by
  re-checking after the fact, not predicted in advance.
- The pattern recurs a 3rd time on NSFHQ04 (`Brush8321`) but only PARTIALLY explains its residual
  there (confirmed via live prefix-removal: removing it makes native's count diverge FURTHER, not
  converge — a major but not sole driver). NSFHQ04 unchanged by the fix, as predicted.
- Area51 Entrance and Training Final do NOT have this pattern at all (checked their full brush sets,
  zero `CsgOper`-absent brushes) — ruled out cleanly, not assumed.

**New open thread this stretch:**
- Area51 Entrance's entire structural residual (+85 nodes/+51 leaves, surfs already exact) is
  live-localized to ONE brush, `Brush1852` — removing it from the full 1343-brush level closes the
  gap to zero on both native and a fresh editor rebuild (same "one brush explains everything" shape
  as FreeClinic08's `Brush586`). Mechanism NOT disassembly-confirmed: the real editor absorbs this
  small `CSG_Add` brush with zero new leaves; native creates 51. Not the brush's own geometry (3
  identical-shape sibling placements build byte-exact) — something position/context-dependent about
  how it CSGs against the accumulated world tree at that point. Thread:
  `area51-entrance-residual-localized-to-brush1852`.
- Training Final: only a static, unconfirmed lead (4 near-consecutive small `CSG_Add` brushes with
  large partially-offsetting diffs) — not live-localized this round.

**Process notes worth keeping**, beyond what's already in the first snapshot:
- A `/tmp` tmpfs (512M cap) genuinely filled completely this stretch (`No space left on device`),
  silently risking every background job including the live parity-table generation. Cleared ~150M
  of loose one-off `.dx`/`.json`/`.t3d` scratch files from completed, already-committed rounds.
  `/tmp` usage is worth a periodic `df -h /tmp` sanity check on a long session — it fills silently
  and several tools (JSON diff dumps especially) write large temp files there without warning.
  A stale-build false alarm THIS caused (a transiently wrong Area51 measurement, `nodes=3834` vs
  the real `+85` delta) was correctly bisected and corrected by the investigating agent rather than
  reported as a regression — a good model for how to handle a surprising number: verify the build
  is genuinely fresh (or bisect across known-good commits) before trusting it, every time.
- Subagents that stall with a stub ("waiting for background job X") sometimes DO eventually
  produce real, valuable findings if resumed rather than abandoned — two rounds this stretch
  (NSFHQ04's harness-contamination fix, Area51's full localization) looked stalled/stubbed on a
  first or second check but converged on genuine results after being resumed with a direct request
  to report synthesized findings now. Worth one or two resumes before concluding a thread is a dead
  end, even past the usual "nudge once, take over" threshold — but don't wait indefinitely either.
- A subagent working in a SHARED/reused worktree (not a fresh one, despite instructions) risks
  reading a CONCURRENT agent's in-flight uncommitted edits via a shared-checkout `sys.path` —
  caused nondeterministic `BuildError`s in the NSFHQ04 round. Always import from the SAME isolated
  worktree the comparison is running in, never the main checkout, when multiple agents may be
  active.

**Nothing currently in flight** — every dispatched thread this stretch has concluded (fixed, or
open with a clear next step recorded in its own board item). The natural next targets, in rough
priority order: Area51 Entrance's `Brush1852` mechanism (needs live gdb/disassembly, has a precise
minimal repro already), NSFHQ04's residual beyond `Brush8321`, Training Final's unconfirmed lead,
or returning to the `p_base`/`node_flags` threads from the first snapshot.

## Area51 Entrance `Brush1852`: live-traced to OVER-FRAGMENTATION in the classify-BSP descent, NOT
## a keep/discard logic bug — mechanism narrowed, exact cause not yet pinned (2026-09-01)

Live gdb-traced the real editor's `bspBrushCSG` (`Editor.dll`, this tree's own `uned/UED22/Editor.dll`)
against native for Brush1852's own incremental CSG call, isolated at the n=506 (byte-exact)  n=507
(adds Brush1852) prefix transition — the same brush/context the prior round localized the residual to.
Fresh worktree, fresh `bin/test -k bspcsg` build (`.so` mtime verified newer than every `.rs` source
file before trusting any measurement).

**Infrastructure fix (reusable): `docker cp` is broken in this sandbox whenever a container has a
`:ro` bind mount.** Every `docker cp` (both directions) against a `uned`-family container fails with
`Error response from daemon: remount-ro .../stubs, flags: 0x1021: operation not permitted` — rootless
dockerd here cannot remount the container's `/stubs:ro` asset mount, which `docker cp`'s
implementation touches regardless of the actual copy destination. Confirmed live: a bare `docker run`
with just `-v host:/stubs:ro` reproduces it for `docker cp` in EITHER direction; `docker exec -i
container bash -c "cat > /path"` (write) and `docker exec container cat /path` (read, capture stdout)
bypass it entirely and were verified working. The existing `editor_tree_oracle.py`/`editor_descent.py`
harnesses still use raw `docker cp` — they may be silently broken in this same sandbox; a session
resuming live-editor gdb work here should swap to the `exec`-based transfer first, not re-diagnose the
same failure. Root cause is host/sandbox-level (rootless docker + this overlay/kernel combination), not
a code bug — no fix filed against the harness itself beyond the workaround.

**Disassembly re-confirms `AddBrushToWorldFunc` (`Editor.dll` RVA `0x31770`) matches
`bspcsg.rs::leaf_func`'s `LeafFunc::Add` arm byte-for-byte.** Args at (breakpoint on the FIRST
instruction, prologue not yet run, so `$esp`-relative not `$ebp`-relative — the same trap
`editor_tree_oracle.py`'s own header warns about, hit and fixed live this round after a first attempt
crashed gdb with "Cannot access memory" from stale caller-frame `$ebp`): `$esp+4`=Model, `+8`=iNode,
`+0xc`=EdPoly, `+0x10`=Filter, `+0x14`=Place. The add-gate is a literal cumulative `sub eax,0` /
`sub eax,2` / `sub eax,3` chain — `Filter==0` (Outside) or `Filter==2` (CoplanarOutside) add
unconditionally; `Filter==5` (CospatialFacingOut) adds only if `EdPoly->PolyFlags` bit `0x20`
(`PF_Semisolid`, byte offset `+0x1b0`) is clear — then calls `bspAddNode` via the vtable
(`GEditor` vtable slot `+0x224`) with args `(Model, iParent, Place, NodeFlags=0x20, EdPoly)`. This is
IDENTICAL to `F_OUTSIDE=0`/`F_COPLANAR_OUTSIDE=2`/`F_COSPATIAL_FACING_OUT=5` and the semisolid gate in
`bspcsg.rs`. **The keep-vs-discard decision logic is confirmed correct** — this is not where the bug is.

**The real divergence: native's classify-BSP descent produces MORE terminal fragments than the
editor for the SAME 6-poly brush against the SAME byte-exact n=506 world.** Traced BOTH sides for the
n=506→507 transition (Brush1852 is world-CSG brush index 506, 0-based, the last of the n=507 prefix):

- **Editor** (`AddBrushToWorldFunc` gdb trace, n=507 log tail minus n=506 log tail — clean since
  Brush1852 is the only brush added between them): **17 total classify calls** — 13 kept
  (`Filter∈{0,2}` or non-semisolid `5`), 4 discarded (`Filter=1`, Inside).
- **Native** (`UEDCLI_BSPCSG_DESCENT_ACTOR=506` LEAF trace, same n=507 build, one process so the NADD
  and LEAF counts are directly comparable): **26 total classify calls** — 14 kept, 12 discarded.
  (A separate NADD-only tail count of 21 is NOT the same granularity — `bsp_add_node` internally
  splits an oversized polygon into multiple stored nodes per one `LEAF`-gated classify decision, so
  21 NADD insertions came from only 14 `LEAF add=true` calls; the apples-to-apples count against the
  editor's `AddBrushToWorldFunc` call count is the 26 LEAF classifications, not the 21 NADD lines.)

**26 vs 17 — native produces 53% MORE terminal fragments**, concentrated in one of the brush's 6
authored polys: `i_brush_poly=4` alone accounts for 10 of native's 26 classifications (poly 0: 4,
poly 1: 3, poly 2: 3, poly 3: 1, poly 4: 10, poly 5: 5). A fragment-level Base/Normal diff (coarse —
`FPoly::Base` is the plane's stored base point, unchanged across a split, so this cannot fully
disambiguate distinct split fragments sharing a plane) found 14 native-kept fragments with NO
corresponding editor call (kept OR discarded) at the same Base/Normal at all, and 2 Base/Normal pairs
where the editor calls the leaf 4× (3 kept + 1 discarded — a coplanar cascade) that native does not
reproduce with the same multiplicity — consistent with native's descent visiting more/different nodes
of the classify BSP than the editor's, not a difference in what gets kept once classified.

**Conclusion: the mechanism is over-fragmentation during `FilterEdPoly`'s descent/split (native
splits Brush1852's polys against more of the accumulated world's structural planes than the editor
does), not the leaf keep/discard decision (disassembly-verified identical).** This is a NEW,
narrower finding than the prior round's "editor absorbs with 0 leaves, native creates 51" — that
full-level number is not reproduced at this reduced n=506/507 scale (the editor here still keeps 13
of its own fragments, not 0; the "0 new leaves" full-level number is apparently specific to the much
larger 1343-brush accumulated context, not an artifact reproducible in isolation at this prefix size).
**No fix shipped** — the specific `split_with_plane` call, node, or accumulated-tree-shape difference
responsible for the extra ~9 splits is NOT pinned; per the no-guessing rule this needs a
`FilterEdPoly`-loophead-level live trace (the exact node/plane visited at each recursion step, the way
`editor_descent.py` already does for `iLink`-scoped fragments) on BOTH sides, correlated fragment-by-
fragment via a finer key than Base/Normal (the full vertex list, or the `i_brush_poly`+split-path),
to find the FIRST node where the two descents disagree on Front/Back/Split/Coplanar classification.
That live-loophead trace was not run this round (time-boxed); the gdb harness and RVAs needed for it
are proven working this round (see Infrastructure fix above) and the next session can go straight to
it without re-deriving the container/mount workarounds.

Harness: `dev/docs/spikes/2026-09-01-area51-training-final-residual/harness/area51_subset.py` (N-brush
editor golden builder, mirrors `unatco_subset.py`), `area51_addfunc_oracle.py` (live gdb trace of
`AddBrushToWorldFunc`, `$esp`-relative, `docker exec`-based transfer), `area51_native_leaf_dump.py`
(native's `UEDCLI_BSPCSG_TREE_DUMP`+`UEDCLI_BSPCSG_DESCENT_ACTOR` trace, one process for both n=506
and n=507 so NADD/LEAF counts are directly comparable), `area51_compare_tail.py` /
`area51_frag_diff.py` (tail-diff and fragment-level Base/Normal comparison).

## 2026-09-01, NSFHQ04 5th continuation: post-`CsgOper::Active` fix, second divergent brush localized — `Brush842`, first non-axis-aligned rotation in the level

Worst-parity level in the corpus (0/6 geometry, per the 2026-09-01 regenerated breadth table). The
`528e602` `CsgOper::Active` fix (which correctly handles `Brush8321`, the `CsgOper`-absent brush from
the 4th continuation above) is confirmed shipped and in effect; this round asks the open question that
continuation left: what explains the residual BEYOND `Brush8321`.

**Method**: re-ran the existing `nsfhq04_prefix_search2.py`/`prefix_search_lib2.py` harness (already
committed, built for exactly this follow-up — a "round 2" search over the same structural-only,
non-`PF_Semisolid` 660-brush set, WITHOUT removing `Brush8321`, now that `CsgOper::Active` handles it
natively) to completion. A dispatched investigation agent had built the harness and started the search
but stalled twice waiting on background builds that had already finished without producing a
completion signal (both times verified via `ps`/`docker ps`/file-mtime — no live process, no recent
file writes); the coordinating session ran the already-built, already-committed script directly to
finish the search rather than re-deriving it.

**Binary search result**: prefix *n*=512 (`Brush841`) is byte-exact (nodes=surfs=leaves match
natively-computed vs a freshly self-built editor golden); *n*=513 (adds `Brush842`) diverges by
`d_nodes=+131 d_surfs=+0 d_leaves=+38`.

**`Brush842`'s properties are notable**: `CsgOper=CSG_Add`, `Rotation=(Pitch=65536, Yaw=-131072,
Roll=-32768)` — in Unreal's 65536-units-per-circle angle representation this is Pitch=360°≡0°,
Yaw=-720°≡0°, Roll=-180°, i.e. algebraically a pure 180° flip, not an arbitrary tilt. Despite that, its
authored T3D poly data is NOT perfectly axis-planar: e.g. poly 0's `Normal=(-0.002003, 0, 1.0)` (not
exactly `(0,0,1)`) and its 4 vertices' Z values are `+65.919899, +66.000000, +65.919899, +65.919899`
(not identical) — a ~0.08uu spread across nominally-coplanar vertices. `MainScale`/`PostScale` both
specify `SheerAxis=SHEER_ZX` but no `Scale=`/`SheerRate=`, so both default to identity scale/zero
shear rate — the near-degenerate poly shape is NOT an actual applied shear transform, it's baked into
the T3D-authored vertex/normal data itself (both native and the editor consume this SAME authored data
from the SAME T3D — this is not an input difference between the two sides).

**Not yet root-caused; strong hypothesis, unconfirmed**: a near-but-not-exactly-planar poly is exactly
the class of input that would stress a coplanar-vs-split epsilon/threshold decision during
`filter_ed_poly`'s classify-BSP descent — the SAME code path (`bspcsg.rs`'s `filter_ed_poly`, dispatch
into `THRESH_SPLIT_POLY_WITH_PLANE`/`THRESH_POINTS_ARE_SAME`/etc., all already disassembly-confirmed
per `fpoly.rs`'s own citations) that the PARALLEL Area51 Entrance `Brush1852` investigation (see
"Area51 Brush1852... classify-BSP over-fragmentation" above) independently converged on THE SAME ROUND,
also as a "native produces more fragments than the editor" pattern. **This may be the same underlying
mechanism as Area51's residual** — both are `CSG_Add` brushes whose over-fragmentation shows up as a
node/leaf-only (surf-exact) delta, both localized to a single brush via live prefix binary search, both
pointing at the classify-BSP split/descent stage rather than the leaf keep/discard decision. Not proven
identical — Area51's `Brush1852` is NOT reported as having a similarly degenerate poly shape (that
wasn't checked for it), and NSFHQ04's is the first such case measured. Worth checking Area51's
`Brush1852` for the same near-non-planar-authored-poly property once the concurrent `angr`-decompile
round on `FilterEdPoly` lands — if both share a poly-shape trigger, one fix should close both.

**No fix shipped** — per the no-guessing rule, the epsilon-threshold hypothesis above is not
disassembly-confirmed at this specific call site for this specific poly; the existing
`THRESH_SPLIT_POLY_WITH_PLANE=0.25`/`THRESH_POINTS_ARE_SAME=0.002` constants are already
disassembly-cited elsewhere in `fpoly.rs`, so a naive "just widen the epsilon" change would be
unverified guessing, not a confirmed fix. Next step: a `FilterEdPoly`-loophead live trace on `Brush842`
specifically (the same technique the Area51 thread is applying, now that `angr`'s decompiler is being
tried there for readable pseudocode instead of raw capstone) to see whether the divergence is a
Front/Back/Split/Coplanar classification flip on this poly's near-planar faces.

No `bspcsg.rs`/`csg.rs` changes this round. `bin/test` not re-run (read-only investigation, no source
touched). Board: `freeclinic08-nsfhq04-1-surf-under-build-root` (existing item), appended.

## `angr` decompiler tried on Brush1852's over-fragmentation; located `FilterEdPoly`/`FilterLeaf`/
## `FPoly::SplitWithPlane` by address, confirmed the existing port matches disassembly, and RULED OUT
## the epsilon-flip hypothesis with a live measurement — mechanism still open (2026-09-01)

Owner-approved new tool for this investigation: `angr`'s decompiler (`proj.analyses.Decompiler`),
instead of continuing pure gdb/register tracing. Worked in a fresh worktree
(`.claude/worktrees/area51-filteredpoly-decompile` branched off `master`, fast-forwarded onto this
same round's prior commit).

**Method note (faster than caller-chase): a raw byte scan beats `angr` CFGFast for "who calls this
address".** The plan was to find `FilterEdPoly` by locating every caller of `AddBrushToWorldFunc` (VA
`0x10031770`). A linear-sweep capstone/raw-`E8` scan of `Editor.dll`'s `.text` for direct
`call 0x10031770` found **zero hits** — the call is INDIRECT (the function pointer is threaded through
`FilterEdPoly`'s recursion as a parameter, never a hardcoded `call rel32`). The fix: scan the whole
file for the raw 4-byte VA `70 17 03 10` (little-endian `0x10031770`) as an IMMEDIATE operand instead
of a call target. **Exactly one occurrence**, at `Editor.dll` VA `0x10035a91`, inside `bspBrushCSG`
(RVA `0x355e0`, ~0x4b1 bytes in): a `cmove` picks `AddBrushToWorldFunc` when `CsgOper==1`(Add), else a
sibling leaf func at `0x100348c0` (almost certainly `SubtractBrushFromWorldFunc`), then
`push eax; call 0x10031f50`. `0x10031f50` is a small bootstrap wrapper (empty-tree fast path calls the
filter func directly; else calls `0x10032bf0` with `(Filter, Model, iNode=0, EdPoly, CoplanarInfo,
Outside)`). **`0x10032bf0` is `FilterEdPoly`** — confirmed self-recursive (4 call sites to itself: one
for the `>=14`-vertex `SplitInHalf` pre-split, two for the `SP_Split` front/back children, consistent
with "~2 recursive calls per invocation") and it calls a fixed leaf dispatcher at `0x33130`
(`FilterLeaf`). **These are the SAME two addresses `bspcsg.rs`'s `filter_ed_poly`/`filter_leaf` already
cite in their doc comments** (`0x32bf0`, `0x33130`, plus the `+0x18..+0x28` `FCoplanarInfo` frame
layout) — a prior round had already hand-disassembled this function; this round's `angr`+raw-scan
route re-derives the same two addresses independently and much faster (minutes, not a live gdb
session).

**`angr`'s decompiler verdict: usable, with real caveats.** `CFGFast` over `Editor.dll` (835 KB `.text`)
took ~126 s and found 9147 functions including `FilterEdPoly` at the right address (though its
recovered `size` was short — 1275 bytes vs the function's true extent past `0x331bb`, since MSVC's SEH
frame gives it multiple epilogues and at least one exception-dispatch-only edge `CFGFast` can't see
statically; the recovered graph was still enough to decompile). `proj.analyses.Decompiler(fn,
cfg=cfg.model)` produced pseudo-C in a few seconds that is READABLE and structurally correct — it
correctly resolved the self-recursive calls, the `FPoly::SplitInHalf`/`FPoly::SplitWithPlane` calls
(see below — it even recovered the cross-DLL IMPORTED symbol names, not just addresses), and the
overall Front/Back-loop / Split-recurse / Coplanar-cascade shape matches `bspcsg.rs`'s existing
port and doc comments line for line. Caveats: variable names are generic (`v1`..`v51`, `a0`..`a9`),
a few SIMD/struct-copy instructions came out as `/* unsupported instruction */` or a raw `_INSERT`/
`CONCAT` pseudo-op, and one 20-byte-struct-by-value argument (the `FCoplanarInfo`) decompiles as
manual stack-slice copies rather than a named struct — exactly the "reliability" caveat the task
anticipated, so every non-obvious line was still cross-checked against raw capstone disassembly
before being trusted. Net: worth using AGAIN for locating/skimming a large unfamiliar function fast,
but not a substitute for disassembly on the specific lines that matter.

**`FPoly::SplitWithPlane` didn't need any of the above — it's a direct export of `Engine.dll`, not
`Editor.dll`.** `FPoly` is an Engine-core class; `Engine.dll`'s export table has
`?SplitWithPlane@FPoly@@QBEHABVFVector@@0PAV1@1H@Z` at VA `0x101518b0` (RVA `0x1518b0`) directly —
no caller-chase needed. (General navigational fact for future spelunking: `UEditorEngine::bsp*`
methods — `bspBrushCSG`, `bspAddNode`, etc. — are `Editor.dll` exports; `FPoly` methods —
`SplitWithPlane`, `SplitInHalf`, `SplitWithNode`, `CalcNormal`, `Fix`, `Reverse` — are `Engine.dll`
exports/imports. `Editor.dll` never defines `FPoly`'s own methods, it only imports them.)
Disassembled it directly (no decompiler needed, the function is a clean, single-epilogue vertex-loop):
confirms **both threshold constants read straight out of `.rdata`** — `THRESH_SPLIT_POLY_PRECISELY` =
`0.009999999776482582` (f32 `0.01`) at RVA `0x1fee1c`, `THRESH_SPLIT_POLY_WITH_PLANE` = `0.25` at RVA
`0x206780` — selected by the function's last (`InOverrideThreshold`/"VeryPrecise") argument, which
`FilterEdPoly` **always passes as literal `0`** at its one `SplitWithPlane` call site (confirmed in
both the raw disassembly and the `angr` pseudo-C: `SplitWithPlane(v13, base, normal, &front, &back,
0)`). **`fpoly.rs`'s constants (`THRESH_SPLIT_POLY_WITH_PLANE: f32 = 0.25`,
`THRESH_SPLIT_POLY_PRECISELY: f32 = 0.01`) and every `split_with_plane(..., false)` call site in
`bspcsg.rs` already match this exactly** — no discrepancy found in the threshold value or which one
gets used.

**Live measurement: RULES OUT the "near-threshold float-precision epsilon flip" hypothesis for
Brush1852's `i_brush_poly=4`.** Since the classify/split code structurally matches and the threshold
constant matches, the next natural hypothesis was that native and the editor compute a given vertex's
signed plane distance via a different FP operation order and land on opposite sides of `±0.25` for
some vertex sitting very close to the boundary — which would explain a divergence localized to one
specific brush/context without any logic bug. Built the venv + native `.so` fresh in this worktree and
ran the existing env-gated `filter_ed_poly` DESCENT trace
(`UEDCLI_BSPCSG_DESCENT_ACTOR=506 UEDCLI_BSPCSG_DESCENT_POLY=4`, new harness
`area51_dist_threshold_probe.py`) against the real n=507 trunk (via the cached extraction under
`breadth-parity-check`'s `_scratch`). Result: **47 descent nodes traced for this poly; the closest any
min/max signed distance comes to the `±0.25` threshold is a margin of `0.2498`** (i.e. the actual
distances there are `~0.00015`/`~0.00016` — comfortably inside the Coplanar band, not near the Front/
Back/Split boundary at all) — every genuine `SPLIT` classification has a margin `>= 0.32`, most far
larger (up to `20+`). **No node anywhere in this poly's descent is a plausible epsilon-boundary
coincidence.** This rules out the float-precision hypothesis outright for this poly — native's 26-vs-
17 divergence is not explained by any vertex sitting near the classify threshold.

**Conclusion — mechanism still NOT pinned; do not guess a fix.** Both the classify/split logic AND
its threshold constant are disassembly-confirmed to match `bspcsg.rs` exactly, and the "some vertex is
right at the epsilon boundary" explanation is now live-measured and ruled out. What remains
unexplained is HOW two structurally-identical descents over the SAME byte-exact n=506 world tree visit
a different NUMBER of nodes for the same input poly. The leading remaining hypothesis (untested this
round) is a TRAVERSAL-ORDER/tie-break difference rather than a classify difference: multiple world-tree
nodes can share one coplanar group (`iLink`), and if native and the editor pick a different member of
that group as the traversal "leaf" at some level, the two descents could disagree in fragment COUNT
while every individual classification decision (Front/Back/Split/Coplanar, and the threshold used to
make it) stays byte-identical. Confirming that needs exactly what the prior round already flagged as
the next step and this round did not attempt: a `FilterEdPoly`-loophead-level trace on BOTH sides
(the specific node index + its `i_surf`/`iLink` visited at each recursion step, not just the classify
verdict), correlated finer than Base/Normal.

Harness added this round: `find_addfunc_callers.py` (the `E8`-scan / raw-VA-immediate-scan caller
finder — documents the "call is indirect, scan for the immediate instead" method for reuse),
`area51_dist_threshold_probe.py` (the `DESC`-trace threshold-margin diagnostic).

## Full `FilterEdPoly`/`FilterLeaf` decompile: structural port confirmed exact end-to-end; the
## coplanar `iPlane` node-chain is NEVER read during classify — narrows the Area51/NSFHQ04
## traversal-order hypothesis away from the classify function itself (2026-09-01)

Follow-up to the prior round's `angr` caller-scan (above): full decompile of both functions, read
line-by-line against `bspcsg.rs`'s `filter_ed_poly`/`filter_leaf`/`bsp_add_node` and `fpoly.rs`'s
`split_with_plane`/`split_in_half`. Fresh worktree off `master`. `CFGFast` over `Editor.dll` (835 KB
`.text`, 9147 funcs) ~2m15s; `proj.analyses.Decompiler(fn, cfg=cfg.model)` on `FilterEdPoly`
(`0x10032bf0`) and `FilterLeaf` (`0x10033130`).

**Tooling trap for reuse: `fn.normalize()` is required before `Decompiler`, and its absence fails
SILENTLY.** Without it, `Decompiler.__init__` raises `ValueError: Decompilation must work on
normalized function graphs` — but `angr`'s own "resilience" wrapper catches and logs it, so
`dec.codegen.text` comes back as a 12-byte near-empty stub with no exception surfaced to the caller.
A future session must check `codegen` is non-trivial, not just that the call didn't throw.

**Cross-check result: no divergence found anywhere in either function's own logic.** Point by point
against `bspcsg.rs`:
- **`>=14`-vertex `SplitInHalf` pre-split**: same `NumVertices` field read, same order — recurse on
  the split-off half FIRST (direct self-call), then fall through to keep processing the retained
  first half in the same loop iteration. Matches.
- **Front/Back single-child tail recursion**: `SplitWithPlane`'s Front/Back return codes drive a
  `i_node = child; continue` loop for a non-terminal child, `FilterLeaf` + return for a `-1` (leaf)
  child. Matches.
- **`Split` (straddle) case**: both fragments are ALWAYS visited, FRONT unconditionally before BACK,
  each independently either `FilterLeaf`'d (child `-1`) or recursed into — no early return between
  them. Matches `bspcsg.rs`'s `Split::Split` arm exactly, order included.
- **Out-of-place coplanar** (rare re-entrant case): decompiles to a debug counter bump + `FOutputDevice::Logf(L"FilterEdPoly:
  Encountered out-of-place coplanar")`, then falls straight into the ordinary front-continue path —
  confirms `bspcsg.rs`'s own comment ("Out-of-place coplanar (rare): classify as Front") is not just
  plausible but the literal binary behavior, log message included.
  Zero geometric effect (the bump is a pure engine-side stat, not ported, and doesn't need to be).
- **Ordinary coplanar (facing test)**: `dot = edpoly.normal · node.plane` via `FPlane::operator|`;
  `dot>=0` → front child is "facing" else back, `Coplanar{i_original_node, i_back_node=other_child,
  back_seed=other_out, processing_back=false}` built, then facing-child-empty short-circuits straight
  to the back pass while facing-child-present recurses into it first. Matches `bspcsg.rs` arg-for-arg.
- **`FilterLeaf`'s 3-way dispatch** (ordinary leaf / `processing_back` classify / front-pass-done →
  descend other side) decompiles to the same 3 branches; the `(leaf_outside, front_outside)` →
  `{COPLANAR_INSIDE, COPLANAR_OUTSIDE, FACING_OUT, FACING_IN}` 4-way truth table was hand-derived from
  the decompiled branch conditions and matches `bspcsg.rs`'s `filter_leaf` on all 4 combinations.
- **No degenerate/near-empty-fragment special case anywhere in `FilterEdPoly` itself**: a `Split`
  fragment is recursed/leaf-classified unconditionally regardless of resulting vertex count — no
  `NumVertices>=3` gate in this function (that's `Fix`'s job inside `SplitWithPlane`, already ported).
  Matches.
- `SplitWithPlane`'s `VeryPrecise` arg is a literal `0` at both decompiled call-sites — re-confirms
  (not independently re-derived) the prior round's disassembly finding.

**The one new, decisive fact this round adds: neither function ever reads a node's `iPlane` field
(the coplanar-SIBLING chain pointer — distinct from a poly's own `i_link` surf-identity attribute)
anywhere.** Exhaustively enumerated every `FBspNode` struct offset either decompiled function
touches: only two ever appear, `iFront` and `iBack`, both read off the SAME node object reached at
`i_node` — no third offset in the `iPlane` position appears in `FilterEdPoly` or `FilterLeaf` at all.
`bspcsg.rs`'s `filter_ed_poly` independently never reads `model.nodes[i_node].i_plane` either
(confirmed by direct source read, not just absence-of-mention) — **this is a MATCH, not a
divergence**. `iPlane` IS walked in the real editor, but only at INSERT time, inside `bspAddNode`'s
`NodePlace==NODE_PLANE` branch (`bspcsg.rs`'s own `bsp_add_node`, mirrored line-for-line: `while
node.i_plane != -1 { i = node.i_plane }`, a plain append-to-chain-tail) — outside this round's two
assigned functions, disassembly-cited elsewhere already, not independently re-verified this round.

**Conclusion — narrows, does not confirm, the leading Area51/NSFHQ04 hypothesis.** The prior round's
"traversal-order/tie-break difference among coplanar-grouped nodes" candidate, AS APPLIED TO
`FilterEdPoly`'s classify descent, has no mechanism to act through: the descent is blind to the
`iPlane` chain by construction, on BOTH sides. If a genuine coplanar-node traversal-order effect is
real, it can only come from WHICH node ends up occupying a given `i_front`/`i_back`/chain-tail slot
(a tree-SHAPE difference from earlier `bsp_add_node` calls), never from `FilterEdPoly` picking a
different chain member during classify — because it never looks at the chain at all. This
corroborates, from the opposite direction, the parallel `freeclinic08`/`nsfhq04` thread's
independently-reached "poly-list ORDER, not scoring" finding (this file, search "poly-list ORDER
mismatch"): both threads now point at a tree-shape/insertion-order divergence UPSTREAM of the
classify function, not a bug in the classify function's own logic. Closing Area51/NSFHQ04 needs a
live trace of `bsp_add_node`'s own linkage decisions or Pass-1 tree-shape (the freeclinic08 thread's
own next step), not further reading of `FilterEdPoly` pseudo-C — reading it further is very unlikely
to find anything new since the port has now been checked against the binary exhaustively, branch by
branch, twice (raw disasm, this round's decompile).

**No fix shipped** — no divergence found to fix; this round's job was understanding, not a fix.

Harness: `dev/docs/spikes/2026-09-01-filteredpoly-full-decompile/harness/decompile_fep.py` (the
`CFGFast` + normalize + `Decompiler` recipe, addresses hardcoded) plus the two saved pseudo-C outputs
(`FilterEdPoly.decompiled.c`, `FilterLeaf.decompiled.c`) for future reference — re-decompiling costs
~2m15s of `CFGFast`, these files let a future session skip straight to reading.

**Follow-up (same session, read fresh before this note): a concurrent NSFHQ04 round (below,
"NSFHQ04 6th continuation") landed while this entry was being written and live-traced `Brush842`'s
own incremental classify-BSP add as byte-exact against the editor** — corroborating this entry's
conclusion (no divergence in `FilterEdPoly`/`FilterLeaf`'s own logic) from an independent,
live-gdb angle rather than a static decompile. It also flags that the raw `NADD`-tail method the
PRIOR Area51 round used to get "26 vs 17" fragments is not properly per-brush-scoped (it also
captures the world-level repartition's own node-seeding) and may be inflated — worth re-checking
against a `LEAF add=true`-only count before trusting that figure. See that entry for detail.
## DISPROVEN — live gdb trace shows its own classify-BSP descent is byte-exact; the real residual is
## diffuse, at the one-time world-level repartition, same class as UNATCO's open problem (2026-09-01)

Fresh worktree off `master` (fast-forwarded to `3716973`, which already carries `528e602`
`CsgOper::Active` and the Area51 `angr`-decompiler round). Native `.so` rebuilt fresh (mtime
confirmed newer than `bspcsg.rs`). Re-ran `nsfhq04_prefix_search2.py 512 513` end to end (own
editor-driven golden builds, not reused from any other worktree): reproduced the 5th continuation's
result exactly — n=512 (`Brush841`) byte-exact, n=513 (`Brush842`) `d_nodes=+131 d_surfs=+0
d_leaves=+38`.

**Step 1 — epsilon-margin probe (`nsfhq04_dist_threshold_probe.py`, adapted from Area51's
`area51_dist_threshold_probe.py`): RULES OUT the epsilon-flip hypothesis.** Unlike Area51 (which had
a prior per-poly attribution pinning the search to `i_brush_poly=4`), no such attribution existed for
`Brush842` yet, so this run scoped only `UEDCLI_BSPCSG_DESCENT_ACTOR=512` (no `_POLY` filter),
tracing all 6 authored polys' full descent in one pass (115 `DESC` lines). Closest margin to the
`±0.25` `THRESH_SPLIT_POLY_WITH_PLANE` boundary: **0.169890** (poly 0 — the near-degenerate one,
`min=0.00000 max=0.08011`, classified `COPLANAR dot=-1.00000`). Every other node's margin is `>=
0.21`. A margin of 0.17 is not a plausible float-precision coincidence (that would need an FP
divergence on the order of 0.1uu, far beyond float32 noise) — poly 0's authored ~0.08uu
non-planarity is real but lands solidly inside the coplanar band, nowhere near the split/coplanar
boundary. Same qualitative outcome as Area51's `Brush1852` probe, though NSFHQ04's margin (0.17) is
meaningfully tighter than Area51's (0.2498) — still decisively not a boundary case.

**Step 2 — per-brush node-owner attribution (`nsfhq04_brush842_attrib.py`, `area51_attrib.py`'s
method) on the FINAL built trees at n=513: `Brush842` itself is EXACT.** Native's own build vs a
fresh editor golden (`golden_n0513.dx`, built by the same `nsfhq04_prefix_search2.py` run): surf
count owned by `Brush842` native=5 editor=5; node-plane-owner count native=8 editor=8 — no
difference at all. The `+131`/`+38` delta is entirely attributed to **172 of 513 OTHER brushes**
(net `+131`, abs-sum `637` — heavy cancellation), not to `Brush842`.

**Step 3 — live gdb trace of the REAL editor's own `AddBrushToWorldFunc` calls for `Brush842`
(`nsfhq04_addfunc_oracle.py`, same `$esp`-relative-args technique as `area51_addfunc_oracle.py`, VA
`0x10031770`): its incremental CSG-add is byte-identical to native's, fragment for fragment.**
Traced `MAP REBUILD` of `golden_n0512.dx` (2701 `AddBrushToWorldFunc` calls total) and
`golden_n0513.dx` (2720 calls); the tail (`nsfhq04_compare_tail.py`) — the calls attributable to
`Brush842`'s own incremental add — is **19 calls, 12 kept / 7 discarded**. Native's own `LEAF` trace
for the same brush (`nsfhq04_native_leaf_dump.py`, properly actor/poly-scoped via
`descent_scope_matches`) is **19 total, 12 `add=true` / 7 `add=false`** — an EXACT match, both in
total count and in the kept/discarded split. This directly disproves the 5th continuation's framing:
`Brush842`'s own classify-BSP descent does not over-fragment relative to the editor at all; it is
provably identical.

**Methodology correction, relevant to the parallel Area51 thread.** `trace_node_add`'s `NADD` dump
(`UEDCLI_BSPCSG_TREE_DUMP`) is NOT actor-scoped — it fires from `bsp_add_node`'s callers at BOTH the
per-brush CSG leaf-add sites (`leaf_func`'s `ADD`/`SUB`) AND the one-time world-level repartition's
own node-seeding (`SEED`/`FWTB`, `bspcsg.rs` lines ~1306/2688), which `build_geometry_bspcsg` always
runs (`UEDCLI_BSPCSG_STAGE_COUNTS`'s `post-repartition` stage, confirmed present on every call, subset
or full). Measured directly here: `Brush842`'s raw `NADD`-tail count (n=513 total minus n=512 total)
is **42** — 3.5x the properly-scoped `LEAF add=true` count of **12** — because the world-level
repartition's own node-seeding differs between the two builds and leaks into the same tail window.
The `LEAF` trace (gated by `descent_scope_matches` on `actor`/`i_brush_poly`) is immune to this and is
the correct clean per-brush metric. **Area51's own `area51_frag_diff.py`/`area51_native_leaf_dump.py`
"native kept: 26" figure for `Brush1852` is computed from the SAME raw `NADD`-tail method and may be
similarly inflated** — worth re-checking against a `LEAF add=true`-only count before treating 26 (vs
editor's 17) as ground truth for that investigation. Not re-verified here (out of this round's scope);
flagging for that thread.

**Conclusion: the whole "`Brush842` over-fragments its own descent" hypothesis is disproven, not just
its epsilon-flip sub-case.** Two independent, live-trace-confirmed measurements (step 2's final-tree
attribution, step 3's live incremental-add gdb trace) agree: `Brush842`'s own CSG-add is exact on both
sides. The real mechanism is that `Brush842`'s mere inclusion changes the polygon pool the ONE-TIME
world-level `bspBuildFPolys`→`bspMergeCoplanars`→`bspBuild` repartition consumes (confirmed present in
native's pipeline at the `post-repartition` stage, node count 3568 already close to final 3604 there),
and that step's output differs diffusely across 172 already-settled brushes — the SAME symptom
signature (surf-exact, node/leaf-only delta, diffuse cross-brush node-ownership, present at/before the
one-time world-level rebuild) as UNATCO's still-open residual and freeclinic08's PRE-`Brush586`-fix
diffuse residual (both previously traced to a world-level poly-list-order/`FindBestSplit`-tie-break
sensitivity that remains unresolved — see freeclinic08's "divergence traced one stage further"
continuation above). This is very likely the SAME open problem recurring on a third level, not a new,
locally-fixable bug — but this round did not re-run the `prepart_tree_*`/`fpolys_stage_order.py`-style
world-level poly-order live capture needed to prove it's the IDENTICAL mechanism rather than a
different instance of the same class; that remains the concrete next step, shared with UNATCO's own
open item. Not confirmed (or denied) as the SAME mechanism as Area51's `Brush1852` residual — that
depends on whether Area51's own per-brush attribution also shows `Brush1852` itself exact, which this
round did not check (out of scope; flagged for that thread above).

**No fix shipped.** No logic difference was found in `bspcsg.rs` — the opposite: `Brush842`'s own
classify-BSP logic is proven byte-exact by direct live comparison. The actual mechanism is the
still-open world-level poly-order class, not something to guess-fix here, per the standing
no-guessing rule. `bin/test`: Rust `cargo test` 102/102 pass; pytest has 10 pre-existing failures (2
`test_board.py` frontmatter checks on unrelated board items, 6 `test_csg_native_differential.py`
cases failing on a `ValueError: expected tuple of length 5, but got tuple of length 4`, 1
`test_doc_links.py` case) — all pre-existing on `master` tip `3716973` before this round (zero
`uedcli-native/src` or `uedcli/` changes made this round); not investigated further, out of scope.

Harness added this round, all under
`dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness/`: `nsfhq04_dist_threshold_probe.py`,
`nsfhq04_brush842_attrib.py`, `nsfhq04_native_leaf_dump.py`, `nsfhq04_addfunc_oracle.py`,
`nsfhq04_compare_tail.py`. Board: `freeclinic08-nsfhq04-1-surf-under-build-root`, appended.

## Brush1852 "26 vs 17 over-fragmentation" framing is very likely a wrong-pipeline-stage measurement, not a confirmed root cause — a coordinator cross-check (mid-session) caught this before the traversal-order trace shipped anything (2026-09-01)

Dispatched to run a node-visit-SEQUENCE trace (native `bspcsg.rs` DESC trace vs a new live editor
`FilterEdPoly`-loophead trace) to test the "traversal-order/tie-break among coplanar nodes" hypothesis
the prior round left open. Mid-session, a coordinator cross-check flagged that NSFHQ04's parallel
investigation (Brush842) had just found its own "raw fragment tail count" measurement was contaminated
by unscoped world-level repartition activity (3.5x inflation, 42 raw vs 12 properly-scoped) and that
Brush842 itself turned out classify-BSP-EXACT once properly isolated — the real NSFHQ04 residual is
diffuse across 172 other brushes. Asked to re-verify the SAME risk here before continuing. It checked
out, and worse than suspected — three independent findings, all pointing the same way:

**1. My own attempt at a properly-scoped editor-side trace reproduced the SAME class of bug directly.**
New harness `area51_filteredpoly_descent.py` breaks at `FilterEdPoly`'s loop head (`0x10032cb6`, the
address `editor_descent.py` already validated live) and — since the editor's `EdPoly` struct carries
no `actor`/`i_brush_poly` bookkeeping (that's native's own extension) — filters by `EdPoly->Normal`
(offset `+0xc`) matching Brush1852 `i_brush_poly=4`'s known normal `(-0.707107,-0.707107,0.0)` (added
to `bspcsg.rs`'s existing DESC trace this round as `edN=`, confirmed constant across all 47 of native's
own descent steps for this poly — splitting a polygon never changes its own face normal). Ran it live
against a fresh single-session `MAP REBUILD` of the Area51 Entrance n=507 prefix (the SAME golden the
native-side probe uses). Result: **12 FEP lines, all at node indices 0–52** — nowhere near Brush1852's
real descent (native's own trace for this exact poly visits node indices up to 7380, deep into a
mature ~thousands-of-nodes n=506 tree, since Brush1852 is brush #507 of 507, processed dead last). This
is a clean FALSE-POSITIVE COLLISION: some unrelated, small, EARLY brush happens to share the exact
same 45°-diagonal face normal, and my filter had no way to tell them apart. Face-normal alone is not a
safe per-poly identity at full-level scale — exactly the class of scoping fragility the coordinator
warned about, independently reproduced. (A second, compounding bug in the same script: `_wait_quiescent`
polls the FILTERED match count for stability, which is fine for an unconditional trace like
`area51_addfunc_oracle.py`'s but wrong for a sparse filtered one — long stretches of a 507-brush build
produce zero new filtered hits even while the build is still very much in progress, so quiescence
almost certainly fired before the rebuild ever reached brush 507 at all.)

**2. `build_ued_golden.py`'s own docs independently confirm the contamination vector NSFHQ04 found.**
A bare `MAP REBUILD` is documented (that script's own `--rebuild-cmd` help text) as `csgRebuild`
(per-brush CSG, what `AddBrushToWorldFunc`/`FilterEdPoly` do) followed by `bspBuild`
(`bspRepartition GOOD/Balance-12/stride=NumPolys/20`) — a GLOBAL, whole-tree repartition pass that
runs ONCE, AFTER every brush's own CSG, with a stride parameter that is a function of the TOTAL poly
count at that point. Any trace-window or line-count-delta measurement taken during a full `MAP REBUILD`
(exactly what the prior round's `area51_compare_tail.py` editor "17" figure was — `lines507[len(
lines506):]`, a raw AFUNC line-count delta between two SEPARATE editor processes) risks conflating a
specific brush's own CSG-add calls with this later, brush-count-sensitive, unrelated pass. This is the
SAME contamination class NSFHQ04 found, confirmed here from the harness's own documentation rather than
by re-deriving it live.

**3. Bigger and more fundamental: native's OWN production pipeline shows the CSG-incremental tree is
torn down and rebuilt before the final Nodes/Surfs/Verts are emitted — so "terminal classify-BSP
fragment count" (this entire investigative thread's central metric, all the way back to the prior
round's "26 vs 17") is very likely measuring the WRONG PIPELINE STAGE.** `bspcsg.rs::build_geometry_bspcsg`
(the actual function `level materialize`'s native path calls) runs the per-brush `FilterEdPoly`/
`leaf_func`/`bsp_add_node` CSG descent (everything this session and the prior one have been tracing)
to build an INTERMEDIATE tree, then at line ~2946 calls `bsp_build_fpolys` to flatten that tree back
into a bare poly SOUP ("in the editor's EXACT order" — mirrors `MakeEdPolys`), then at line ~3050 feeds
that soup into a SEPARATE `bsp_build` call which **repartitions the poly list into a fresh node tree
from scratch** (cost-based `FindBestSplit`, matching `build.rs`'s documented byte-verified `MAP REBUILD`
partition params `Balance=50, PortalBias=70, OPTIMAL`) — this is what actually produces the final
Nodes/Surfs/Verts array. The CSG-incremental tree's own shape (what `FilterEdPoly`'s recursive descent
visits, what "terminal fragment count" counts) is discarded once it has served its ONE purpose — decid-
ing which polygons survive CSG and what they look like — and never directly becomes the final tree.
A difference in the incremental-CSG fragment count does not, by itself, predict or explain a difference
in the final node/leaf count; what matters is (a) whether the SURVIVING POLY SOUP differs between native
and editor, and (b) whether the SEPARATE repartition step handles that soup identically. (There is
already an `UEDCLI_BSPCSG_SOUP_ORDER` env-gated debug hook for dumping the soup-order stage, suggesting
a prior round already anticipated this distinction — it does not appear to have been cross-checked
against the CSG-classify-fragment framing before this round.)

**Full-level static node-owner attribution corroborates this reframe, and does NOT support "Brush1852
itself is exact" as decisively as it does NOT support "Brush1852 itself is the direct cause".**
`area51_attrib.py` (fixed this round to self-resolve its `ROOT`/`GOLDEN` paths — was hardcoded to a
now-gone ephemeral worktree) computes final-tree node-plane ownership (`node.i_surf -> surf.i_actor`)
per brush, native vs a real editor golden, at the FULL 1343-brush scale. Result: **548/1343 brushes
differ in node ownership, abs-sum=2095 vs net=+85 (the level's whole residual) — massive cancellation,
Brush1852 not even in the top 40** (largest: `Brush500` `d=-48`, `Brush3255` `d=-38`, `Brush1178`
`d=+37`, …). This is the exact "diffuse, no dominant outlier" shape already flagged for Training Final
and for NSFHQ04's own (now-resolved) Brush842 case — consistent with the divergence actually living in
the LATER, whole-tree-sensitive repartition stage (finding 3 above), which would ripple across however
many brushes are processed after whatever triggers it, not sit locally on the one brush that happened
to trigger it. This does NOT contradict the earlier decisive removal test (removing Brush1852 from the
full 1343-brush level closes the residual to exactly `d_nodes=+0 d_surfs=+0 d_leaves=+0`, live-verified
both sides) — that test is still solid evidence that Brush1852's PRESENCE is necessary and sufficient
to trigger the residual. What it no longer supports is the INTERPRETATION that Brush1852's own CSG
classify logic is where the bug lives; a brush-count-sensitive threshold in the later repartition stage
(e.g. `stride=NumPolys/20` crossing a boundary exactly when Brush1852 is added) would produce the SAME
removal-test result without Brush1852's own CSG being wrong at all.

**Conclusion: stopped before shipping anything, per the no-guessing rule — the traversal-order/iLink
tie-break hypothesis this round was dispatched to test is very likely NOT the right lever**, since it
is scoped to the same CSG-add stage this round's evidence now says is not what determines the final
tree. Did not complete the dispatched trace (the live editor-side FilterEdPoly descent for Brush1852
poly 4 — collected, but known-contaminated per finding 1, so not used for any conclusion). Recommended
next steps for whoever picks this up: (a) compare the POLY-SOUP stage (`bsp_build_fpolys`/
`UEDCLI_BSPCSG_SOUP_ORDER`) between native and editor for Brush1852's own contribution, not the CSG
classify-fragment count; (b) if the soup matches, the divergence is in the LATER `bsp_build`/repartition
stage's poly-order or threshold sensitivity — the same open "world-level-repartition poly-order" class
already tracked for UNATCO/NSFHQ04/Training Final, not a Brush1852-specific bug; (c) a genuinely
brush-scoped live editor trace (if still wanted) needs EITHER a same-session incremental single-brush
add (`EDIT PASTE` onto an already-built n=506 golden, avoiding a second full `MAP REBUILD`'s repartition
pass entirely) or a much tighter cross-side correlator than face-normal alone (e.g. normal AND the
first-hit world node's own plane, paired as a tuple, to disambiguate collisions) — `area51_fep_seq_compare.py`
(committed this round) is ready to consume such a trace's output once one exists, pairing steps by
`(Normal, plane_w)` rather than raw node index (`area51_frag_diff.py` already established raw indices
use unrelated numbering schemes across the two sides).

Harness added this round: `area51_filteredpoly_descent.py` (the live editor `FilterEdPoly`-loophead
trace, edN-scoped — collected but flagged contaminated, kept for its method/fix value, not its result),
`area51_fep_seq_compare.py` (native-vs-editor DESC/FEP plane-sequence pairing, ready once a clean
editor-side trace exists). `bspcsg.rs`'s DESC trace gained two new fields this round (`edN=`, the
poly's own Normal; the 4th `N=` component, `plane_w = Base·Normal`, the same convention as the editor's
raw `FPlane`) — debug-print-only, env-gated, no behavior change. Fixed stale hardcoded `ROOT`/`GOLDEN`
worktree paths (pointing at now-deleted ephemeral session worktrees) in `area51_subset.py`,
`area51_addfunc_oracle.py`, `area51_frag_diff.py`, `area51_native_leaf_dump.py`, `area51_compare_tail.py`,
`area51_attrib.py` to self-resolve via `Path(__file__)`, so this whole harness family is reusable from
any worktree again.

**Update, same session: the traversal-order/iLink tie-break hypothesis is independently RULED OUT, not
just deprioritized.** A parallel session's full decompile read of `FilterEdPoly`/`FilterLeaf` (`b23de44`,
"full FilterEdPoly/FilterLeaf decompile confirms port exact; iPlane chain never read in classify")
confirms the port is exact AND that neither function ever reads a node's `iPlane`
(coplanar-sibling/`iLink` chain) during classify — only `bsp_add_node`'s INSERT-time tail-walk touches
it. Both sides are structurally blind to that chain during the descent this whole thread has been
tracing, so a traversal-order/tie-break difference among coplanar-grouped nodes cannot be the mechanism
regardless of the pipeline-stage question above; this is now closed off by full-decompile confirmation,
not just a spot-check. The SAME parallel session also disproved NSFHQ04's Brush842 over-fragmentation
hypothesis by live gdb trace (byte-exact descent, 19 vs 19) — the same symptom shape as this round's
finding that Brush1852 is not a full-level node-owner outlier. Both threads now point at the same open
question: is Area51's Brush1852 residual the SAME diffuse world-level-repartition-poly-order class
NSFHQ04's Brush842 turned out to be? Not yet checked directly for Area51 (would need the equivalent
byte-exact-descent live trace, done properly single-session/incremental this time per finding 1 above,
or the poly-soup/repartition-stage comparison from the "next steps" list) — flagging as the concrete
next action rather than guessing.

## Training Final live prefix search: BLOCKED by a reproducible editor operational stall, not level content — no mechanism finding this round (2026-09-02)

Fresh worktree off `master` (fast-forwarded `da119b3`→`b23de44`, which carries the full decompile
round through "coplanar `iPlane` node-chain is NEVER read"). Native `.so` rebuilt fresh (mtime
confirmed newer than `bspcsg.rs`). Sanity check reproduced the documented residual exactly from this
worktree's own trunk copy + the cached editor golden: native nodes=11227 surfs=5307 leaves=861,
editor nodes=11122 surfs=5307 leaves=848 (`d_nodes=+105 d_surfs=+0 d_leaves=+13`) — confirms the
worktree/build setup is sound before attempting anything live.

**Goal: adapt the `prefix_search_lib.py` live prefix binary search (`fc08_prefix_search.py`/
`nsfhq04_prefix_search.py`/`area51_prefix_search.py`'s method) to Training Final's 764-brush
world-CSG set, to test the existing static lead (`Brush907`/`909`/`911`/`915`, world-CSG idx
660-668) live.** Wrote `tf_prefix_search.py` (classic `binary_search()`, lo=1/hi=764) and
`tf_probe.py` (targeted `compare(n)` calls at chosen prefixes, to test the static-lead window
directly without a full log2 search). n=764 (full prefix, `build_ued_golden.py --world-only
--no-light --no-obj-load`) built and matched the sanity check exactly on the first try.

**Every OTHER prefix size tried — n=1 (2 attempts), n=660 (2 attempts), n=650 (1 attempt) —
timed out in `build_ued_golden.py`'s `_wait_idle` step (`map-new` once at its hardcoded 1800s
cap, `rebuild[0]` once at the `--rebuild-timeout` 2400s cap), never producing a second live data
point.** Live-diagnosed, not just retried blind: `docker exec <container> wmctrl -l` during a stall
found the documented "Cleaning up..." GC `xmessage` dialog (`unrealed/quirks.md` "Stability")
present and blocking on at least 2 of the stalls. `build_ued_golden.py`'s `_wait_idle` does NOT call
`Driver.dismiss_blocking_dialog()` defensively on each poll (unlike `qualify.dump_obj_dependencies`,
which already does per that same doc) — a real, fixable gap in the harness, distinct from the CSG
question this round is chasing. Manually dismissing the dialog live (`xdotool windowactivate --sync`
+ `key Return`, the documented technique) unblocked the container's CPU from a dialog-driven plateau,
but on the SAME container the CPU then sat borderline at 18-46% (repeatedly crossing the 30%
`_wait_idle` threshold) for 25+ more minutes without ever sustaining 8 consecutive quiet reads,
distinct from the dialog symptom. Both symptoms recurred across n=1/650/660 — three unrelated prefix
sizes, ruling out a size- or content-specific `MAP NEW` hang (the natural alternative hypothesis) in
favor of general operational flakiness, plausibly host contention from this session's many
concurrently-running agent-worktree containers (`docker ps` showed 2-3 other long-lived `uned-*`
containers throughout, up to 11h old).

**No live second data point obtained; the static lead (`Brush907`/`909`/`911`/`915`) remains
UNCONFIRMED.** Per the standing no-guessing rule, not attempting a `bspcsg.rs` fix with zero live
divergence evidence to act on. **Not a wasted round**: rules out that the static lead's brushes
themselves cause an editor-side `MAP NEW` hang (they don't — the hang recurred on prefix sizes that
exclude them, e.g. n=1/n=650), and pins a concrete, actionable harness gap (`_wait_idle` missing the
standard dialog-dismiss defensiveness) that will keep costing future live-search rounds on ANY level
until fixed — not fixed here (out of this round's scope; the fix belongs in
`build_ued_golden.py`/`driver.py`, not `bspcsg.rs`).

`bin/test`: cargo test 102/102 pass; pytest 13177 passed / 10 failed / 45 skipped / 1 xfailed
(662s) — the same pre-existing 10 (2 `test_board.py` frontmatter, 7 `test_csg_native_differential.py`
tuple-length `ValueError`s, 1 `test_doc_links.py`) as prior rounds; zero `uedcli-native/src` or
`uedcli/` changes made this round, so this only re-confirms no regression.

Harness added this round, under
`dev/docs/spikes/2026-09-01-area51-training-final-residual/harness/`: `tf_prefix_search.py` (the
full lo/hi binary search, generalized-library-based), `tf_probe.py` (targeted single-prefix
`compare(n)` probing with retry, used to test the static-lead window directly). Board:
`area51-entrance-residual-localized-to-brush1852`, appended (Training Final section).

## INDEPENDENT PASS — full-breadth decompile of the CSG/BSP build pipeline: the whole pipeline is faithful EXCEPT the node vertex-RING pooling threshold (0.015 NEAR, native used 0.002); native's `TryToMerge`-neighbour=0.015 is a symptom-patch for it. Root-cause found + measured, NOT shipped (gated) — improves scaled-brush node counts, does NOT move the rotated-brush open cases (2026-09-02)

Second, independent pass at the UNATCO/Area51/NSFHQ04/Training Final world-repartition node-over-build
problem, run in parallel with another agent, deliberately BROADER than one or two functions: `angr`
decompiled EVERY function in the CSG/BSP build call chain and each was read line-by-line against
`bspcsg.rs`. Fresh worktree off `master` (`ea1bc3f`). Harness + all 27 saved pseudo-C files:
`dev/docs/spikes/2026-09-02-csg-pipeline-breadth-decompile/harness/` (`decompile_pipeline.py` — the
`CFGFast`+normalize+`Decompiler` recipe with every address; `measure_addnode_weld.py`/`measure_flag.py`
— the offline A/B geometry harness over the cached parity goldens).

**Decompiled + confirmed FAITHFUL to `bspcsg.rs`, branch by branch (no divergence):** `csgRebuild`
(pass order), `bspRepartition` (BuildFPolys→MergeCoplanars→bspBuild→bspRefresh), `bspBuildFPolys`/
`MakeEdPolys` (pre-order **self→iFront(+0x24)→iBack(+0x20)→iPlane(+0x28)** tree walk), `bspBuild`
(feeds `SplitPolyList` in plain Polys-array order), `SplitPolyList` (Split→front/back append, `>=14`
`SplitInHalf`, front-before-back recursion), `FindBestSplit` (score `|F-B|*Bal + (100-Bal)*splits`,
`Inc` stride GOOD=`n/20`/LAME=`n/4`, eligibility slot-walk, portal split-weight 16, portal-bias, best
= lowest-score-first-wins), `bspMergeCoplanars` (index-order grouping, anchor skip-gated / candidate
NOT skip-gated, original-index-order compaction), `MergeCoplanarPolys` (fixpoint upper-triangle
accumulate), `CleanupNodes` (recursion order + Case-A coplanar-promote-with-swap / Case-B splice),
`FilterWorldThroughBrush` (bound-sphere prune, recursion order, `GLastCoplanar`=iPlane-chain-tail,
re-add), `AddWorldToBrushFunc`/`SubtractWorldToBrushFunc` (re-add/discard sets), `bspAddNode` (iPlane
chain-tail insert, surf alloc, `derive_nf`, `>16`-vert storage split, iLeaf/iZone parent-seeding,
child linkage), `bspNodeToFPoly` (reconstruction + `RemoveColinears` + `<3`→NumVertices=0),
`bspValidateBrush` (surf-link grouping), `bspAddPoint`/`bspAddVector`. **The port is exact everywhere
this pass could reach — corroborating (from a wider angle) the prior rounds that found
`FilterEdPoly`/`FilterLeaf`/`FindBestSplit`/`bspMergeCoplanars` individually faithful.**

**THE ONE REAL DIVERGENCE — the node vertex-RING pooling threshold.** `bspAddPoint` (`0x35430`)
selects its `FindNearestVertex` threshold from its `arg_2` flag (`0x3545c`: `arg_2 ? 0.002 : 0.015`,
both f32 constants at `.rdata` `0x100dcb…`, decoded this pass). `bspAddNode`'s two call sites
(raw-disassembled, decompile crashed on this one function): the surf **pBase** add (`0x34f0b`) pushes
`1` → **0.002 (SAME)**, but the node **vertex-ring** add (`0x352fd`) pushes `0` → **0.015 (NEAR)**.
`bspcsg.rs` pooled BOTH at 0.002. So the real editor welds a node's own ring vertices at the *looser*
0.015, the surf base at 0.002.

**Native's `try_to_merge` neighbour threshold (0.015) is a downstream SYMPTOM-PATCH for this.** Fresh
raw disassembly of `TryToMerge` (`0x34b10`): all THREE coincidence tests — the step-2 anchor
(`call 0x34bdb`) AND both step-3 neighbour edge tests (`0x34c46`, `0x34ca9`) — `call 0x10032b90`,
which is `FPointsAreSame` (±0.002 box). There is NO `FPointsAreNear` call anywhere in the function, so
the binary uses **0.002 for the neighbours too**, contradicting the current default's NEAR (0.015). The
0.015 was introduced by `bspmergecoplanars-8-case-merge-gap-live-traced` for Wanchai Brush754's PostScale
seam (corners 0.00439 apart): the editor fuses that pair because its 0.015 RING pooling already welded
the two corners to ONE point (so `FPointsAreSame`(0.002) then passes trivially); native, pooling the
ring at 0.002, kept them separate and papered over it by loosening the *merge* threshold instead.
The faithful binary is: ring pool **0.015 (NEAR)**, merge anchor+neighbour **0.002 (SAME)**.

**Also found (disassembly-confirmed) but MEASURED INERT: two omissions in `bspAddNode`'s vertex-pool
tail (`0x353a1`-`0x353ef`).** A WRAP-DUP collapse (`iVertPool[0].iVertex == iVertPool[nv-1].iVertex`
→ drop the last) and a `nv<3` degenerate KILL (`NumVertices=0`, bump `GBadNodeCount`). Native ported
neither. Both are downstream-masked (`bsp_node_to_fpoly`'s `RemoveColinears` drops a coincident wrap
vertex and rejects a sub-3 ring at repartition anyway). `UEDCLI_BSPCSG_ADDNODE_WELD` A/B: **ZERO effect
on all 8 tested levels** (DX/UNATCO/bar/747/oceanlab/nsfhq/area51/vandenberg/trainingfinal) — never
triggers on the corpus. Clean negative.

**Measurements (offline A/B vs cached parity goldens, `measure_flag.py`).** `UEDCLI_BSPCSG_RING_NEAR`
(ring pool 0.015; the faithful `+MERGE_NEIGHBOR_SAME` combo is IDENTICAL — once the ring welds seams to
one point, the merge threshold no longer bites), native-vs-golden node/leaf delta OFF→ON:

| level | nodes off→on | surfs | leaves off→on | verts off→on | note |
|-------|--------------|-------|---------------|--------------|------|
| `06_wanchai_market` | +0 → **+0** | +0 | +0 → **+0** | +74 → +99 | stays node/surf/leaf EXACT — the Wanchai fix is preserved WITHOUT the 0.015-merge hack |
| `03_nyc_unatcohq` | +0 → **+0** | +0 | +0 → **+0** | +5 → +11 | stays EXACT |
| `08_nyc_bar` | +0 → +0 | +0 | +0 → +0 | +0 → +0 | unchanged (grid geometry, no sub-0.015 seams) |
| `dx` | +0 → +0 | +0 | +0 → +0 | +0 → +0 | unchanged |
| `12_vandenberg_gas` | **+32 → -6** | +0 | +5 → **-56** | -126 → **-1354** | scaled brushes: nodes improve, leaves/verts REGRESS |
| `04_nyc_nsfhq` | -92 → **-92** | +1 | -26 → -26 | -1774 → -1714 | node count UNCHANGED |
| `03_nyc_747` | +68 → **+68** | +0 | -10 → -10 | +698 → +717 | node count UNCHANGED |
| `14_oceanlab_lab` | +465 → **+465** | +0 | +86 → +86 | +3980 → +5198 | node count UNCHANGED |

`UEDCLI_BSPCSG_MERGE_NEIGHBOR_SAME` ALONE (without ring-near) is NOT shippable: it REGRESSES Wanchai
(+0→+20 nodes/+13 leaves — the exact residual 0.015-merge fixed) and swings 747 (+68→-290) and
oceanlab (+465→+802) — confirming it is only correct *paired* with the ring fix.

**Conclusion.** The ring-pool threshold (0.015 NEAR) is a genuine, disassembly-confirmed root-cause
divergence, and native's `try_to_merge`-neighbour=0.015 is its symptom-patch. The faithful combination
(ring 0.015 + merge-neighbour 0.002) **preserves every currently-EXACT level** (Wanchai/UNATCO/bar/DX
node/surf/leaf unchanged) and **improves Vandenberg's node count (+32→-6)** — but it also **regresses
Vandenberg leaves/verts** (native's +32 nodes was partly two errors cancelling; the correct ring-pool
exposes a separate leaf/vert divergence) and has **ZERO effect on the primary open cases**
(nsfhq/747/oceanlab node over-build UNCHANGED). Those are rotated- (not scaled-) brush levels whose
ring vertices land at exact rotated positions, never in the 0.002–0.015 gap, so the ring threshold is
not their lever — the primary UNATCO-class world-repartition node-over-build problem is **still open**
after this pass. **NOT shipped** (default byte-unchanged, `cargo test` 102/102): per the standing rule,
a change that improves one count while regressing others on a level is a tradeoff for the owner, not a
silent default flip. Both fixes are committed **gated OFF** (`UEDCLI_BSPCSG_RING_NEAR`,
`UEDCLI_BSPCSG_MERGE_NEIGHBOR_SAME`, `UEDCLI_BSPCSG_ADDNODE_WELD`) with the disassembly citations in
their code comments, so a future round can re-measure without re-deriving. Open follow-ups: (a) the
editor's `bspAddPoint` uses `FindNearestVertex` (NEAREST-within), native's default ring pool is
FIRST-within — the large Vandenberg vert overshoot (-1354) is likely this, worth pairing with ring-near
before judging vert parity; (b) the rotated-brush node-over-build (nsfhq/747/oceanlab/area51/trainingfinal)
is untouched by anything in this pass and remains the real open problem.

`bin/test` full run: cargo 102/102; pytest 13184 passed / 10 failed — the SAME pre-existing 10 as
prior rounds (2 `test_board.py` frontmatter on unrelated items, 7 `test_csg_native_differential.py`
tuple-length `ValueError`s, 1 `test_doc_links.py`), all present on `master` `ea1bc3f` before this
round's gated-off changes.

## Full `bspAddNode` decompile: a genuine, disassembly-confirmed insertion-logic gap FOUND and FIXED (a post-loop wrap-vertex trim) — but MEASURED ZERO effect on every tested level; the poly-list-order/tree-shape mystery remains open (2026-09-02)

Continuation of the "poly-list ORDER mismatch" thread (this file, search "coplanar `iPlane` node-chain
is NEVER read" and "Poly-list order divergence localized one stage further"). That work confirmed
`FilterEdPoly`/`FilterLeaf` (the classify descent) are exact and are structurally BLIND to the `iPlane`
coplanar-sibling chain during classify — the chain is touched only at INSERT time, inside `bspAddNode`'s
own `NodePlace==NODE_PLANE` branch. This round reads THAT function in full (not just the zone/leaf tail
block already disassembly-cited in `bspcsg.rs`, `Editor.dll` `0x3524a`-`0x352c7`/`0x3535b`-`0x3539c`) to
check every ordering/placement decision against `bspcsg.rs::bsp_add_node` (~line 311).

**Tooling: two `angr` traps found and worked around, one of them a genuine upstream bug.**
`CFGFast` over `Editor.dll` (~2 min, cached) finds `bspAddNode` cleanly at `0x10034e80` (matches the
already-known entry-args fact in this file). `Decompiler(fn, cfg=cfg.model)` (after the already-known
`fn.normalize()` requirement) still failed SILENTLY (`dec.codegen` came back `None`, worse than the
FilterEdPoly round's "near-empty stub" — no text to inspect at all). Root-caused: installed `angr`
9.3.3's own `SimStruct.offsets` property (`sim_type.py:1699-1703`) computes
`align = ty.alignment * self._arch.byte_width` and only THEN checks `if align is NotImplemented` — but
`SimStruct`/`SimUnion.alignment` legitimately return the literal `NotImplemented` when every field's own
alignment is itself unresolved (a struct-inside-a-struct `angr`'s type inference gave up on, e.g. some
`UModel` `TArray`-internal field) — so `NotImplemented * int` raises `TypeError` before the very guard
meant to catch it. This fires inside the resilience-wrapped codegen call and `angr` swallows the
exception too. Fixed by monkey-patching `SimStruct.offsets` with a corrected version that checks
`NotImplemented` BEFORE multiplying (fixing `angr`'s own ordering bug, not routing around real type
info) — lets codegen finish; ~10.8 KB of readable pseudo-C. A handful of bottom-typed struct fields
still render as raw-offset/plain-int casts rather than named members; every non-obvious line below was
cross-checked against raw `capstone` disassembly, not trusted from pseudo-C alone (same caveat the
FilterEdPoly round already flagged).

**Cross-check result, point by point against `bsp_add_node`:**
- **`NODE_PLANE` tail-walk** (`while node.i_plane != -1 { i = node.i_plane }` to resolve the REAL
  `i_parent`): happens as the literal FIRST executable logic in the real function too — before surf
  resolution, before the `>16`-vertex check. Matches.
- **Surf alloc/reuse gate**: the real editor tests EXACT equality (`iLink == Surfs.Num()` → alloc new)
  and, on the else branch, hard-asserts `iLink != -1` (`appFailAssert("EdPoly->iLink!=INDEX_NONE", …
  UnBsp.cpp, 233)`) and `iLink < Surfs.Num()` (`appFailAssert(…, 234)`) rather than `bspcsg.rs`'s
  permissive `i_link < 0 || i_link >= surfs.len()` → alloc-new. Functionally equivalent for any
  well-formed input (the two formulas agree on every value a real `iLink` can hold: `-1`, `==Surfs.Num()`,
  or a valid existing index) — the real editor's asserts just mean `iLink == -1` reaching `bspAddNode` is
  a program-bug condition, not a silent auto-recovery path. Not shipped as a change (no observable
  behavior difference identified), noted for completeness per the task's "however small" instruction.
- **`>16`-vertex split-in-half**: the real editor resolves the surf and derives `NodeFlags`
  (`derive_nf`-equivalent) ONCE, using the ORIGINAL edpoly's `iLink`, THEN checks the vertex count and —
  if splitting — passes the ALREADY-DERIVED flags into both recursive calls (front half first, self-call;
  back half second, `NodePlace=NODE_PLANE` chained onto the front's own new node). `bspcsg.rs` instead
  recurses first and lets EACH recursive call independently resolve its own surf/derive its own flags
  from the raw, unmodified `node_flags` argument. Structurally different call shape, but functionally
  identical output: `derive_nf`'s bit-setting is pure OR (`|= 1`, `|= 4`, `|= 2`), so re-deriving from an
  already-derived value is idempotent, and both fragments end up sharing the same surf either way (the
  second call's `iLink` is a stale pre-resolution copy that lands exactly on the just-created surf's real
  index on re-resolution). No behavior difference; not shipped.
- **Front/Back/Plane parent-linkage + zone/leaf inheritance**: independently re-derives, via a DIFFERENT
  technique (full decompile + capstone, not the live-gdb method that produced the existing doc comment),
  the EXACT same three formulas already in `bspcsg.rs`'s `inherit_parent_leaf_zone` doc comment
  (`NODE_Root`: `iLeaf=-1,-1; iZone=0,0`; `NODE_Front`/`NODE_Back`: both sides copy `parent.iLeaf/iZone
  [NodePlace]`; `NODE_Plane`: the `k = (newPlane|parentPlane)<0` swap formula). Byte-for-byte match,
  confirming the 2026-08-27 disassembly finding via an independent method. The NODE_PLANE branch's own
  tail-append (`parent(tail).iPlane = newNode`) also matches `bsp_add_node`'s existing chain-tail-append
  semantics exactly.
- **Vertex-pool dedup loop** (consecutive-only): matches — same `bspAddPoint`-per-vertex call, same
  "skip if equal to the immediately preceding pushed value" collapse.

**The one real divergence found: a post-loop "wrap trim" `bsp_add_node` does not implement.**
Disassembly-confirmed independently of the pseudo-C (raw `capstone` dump,
`0x100353a1`-`0x100353ef`, cross-checked line-for-line): after the consecutive-only dedup loop, the real
editor compares the FIRST pushed pool entry's point index against the LAST pushed entry's
(`cmp eax, [edi+ecx*8-8]` at `0x100353b0`) — if they're equal (a ring whose authored last vertex,
after dedup, still closes back onto its first), it decrements the reported vertex count by one
(`dec dh` at `0x100353b6`) WITHOUT popping the vert-pool array entry itself (the real editor
over-allocates the pool region for the pre-trim count and simply under-reports it, so later nodes'
`iVertPool` offsets stay correctly aligned with the real editor's own array growth). Then, if the
resulting count drops under 3, it is treated as a degenerate "Infinitesimal polygon"
(`FOutputDevice::Logf(L"bspAddNode: Infinitesimal polygon %i (%i)")`, `0x100353bb`-`0x100353eb`) and
`NumVertices` is forced to 0 rather than left as a genuine 1/2-vertex sliver. `bsp_add_node` had neither
check.

**Fixed** (`uedcli-native/src/bspcsg.rs`, after the vertex-pool loop): ports both checks exactly,
including NOT popping the vert-pool array on trim (to preserve later `i_vert_pool` alignment). Pinned
with two new unit tests constructed directly against `bsp_add_node` (not just cargo-tested via a full
build): `add_node_drops_a_wrap_duplicate_closing_vertex_from_the_count_not_the_pool` (a 5-vertex ring
whose last vertex repeats the first trims to `num_vertices=4` while `model.verts.len()` stays 5, and a
SECOND node added right after starts its own pool region at index 5, not 4) and
`add_node_reports_zero_vertices_for_a_degenerate_post_trim_result` (a 3-vertex "poly" that trims to 1
distinct vertex reports `num_vertices=0`). Both confirm the new code path is genuinely REACHABLE and
correct, not dead code — `cargo test bspcsg`: 104/104 (102 pre-existing + 2 new).

**MEASURED, before shipping, per the standing no-guessing rule: ZERO effect on every tested level.**
Used the existing `/tmp/uedcli-parity-cache` shared golden-build oracle
(`dev/docs/spikes/2026-08-31-native-parity-report/harness/parity_report.py`, cache HITS throughout — no
live editor needed) for a clean A/B (a temporary env-gated toggle around the fix, removed before
shipping) on the six levels most relevant to this exact investigation thread — the two structural-tree-
shape residuals this thread is centrally about, plus four others as a breadth/regression check:

| level | nodes (native/golden) | surfs | leaves | fix ON vs OFF |
|---|---|---|---|---|
| freeclinic08 (`08_NYC_FreeClinic.dx`) | 2522/2522 (d=+0) | 1580/1580 | 313/313 | IDENTICAL |
| nsfhq04 (`04_NYC_NSFHQ.dx`) | 7564/7656 (d=-92) | 3831/3830 | 1492/1518 | IDENTICAL |
| UNATCO (`01_NYC_UNATCOHQ.dx`) | 6740/6390 (d=+350) | 3598/3595 | 861/822 | IDENTICAL |
| Wanchai Market | 11648/11648 (d=+0) | 5284/5284 | 3371/3371 | IDENTICAL |
| Training Final | 11227/11122 (d=+105) | 5307/5307 | 861/848 | IDENTICAL |
| Area51 Entrance | 12715/12630 (d=+85) | 6058/6058 | 3315/3264 | IDENTICAL |

Every geometry count (nodes/surfs/leaves/verts/points/vectors) is byte-identical with the fix on vs off,
on all six levels — the wrap-trim case the disassembly confirms IS real in the editor's own algorithm
apparently never triggers for any of these levels' actual CSG-fragment output (no ring's authored last
vertex happens to duplicate its first after consecutive-only dedup, in the specific fragment shapes
these builds produce). **This does NOT explain NSFHQ04's diffuse Brush842-class residual, UNATCO's
larger one, Training Final's `Brush907`/`909`/`911`/`915` lead, or Area51's `Brush1852` residual — none
of them.**

**Shipped anyway, as a faithful-port correctness fix, NOT as a fix for the open poly-order mystery.**
It is a genuine, twice-independently-disassembly-confirmed (pseudo-C AND raw capstone) gap from the
real algorithm, costs nothing (zero regression across 6 levels, 104/104 cargo tests), and is pinned by
two new unit tests that prove it fires on realistic-shaped input — consistent with this project's
standing "faithfully reproduce the real algorithm" convention even where a specific case doesn't move
today's measured parity. It is explicitly NOT claimed to explain any of this investigation's open
residuals.

**Where this leaves the poly-list-order/tree-shape mystery.** With this round, `bspAddNode`'s own
insertion logic (parent-slot selection, `iPlane` chain tail-append, zone/leaf inheritance, surf
alloc/reuse, vertex-pool population) is now FULLY checked — decompiled in full and cross-referenced
against raw disassembly, not just spot-verified — and matches `bspcsg.rs` in every respect that has any
observable effect. Combined with the existing full `FilterEdPoly`/`FilterLeaf` decompile (classify
descent, also exact), **both ends of the pipeline `bsp_add_node` sits between are now closed off as
candidates.** The remaining, unexamined surface is narrower than before this round: not "does
`bspAddNode` link nodes correctly" (now checked, yes) and not "does the classify descent walk the tree
correctly" (already checked, yes) — but WHICH EdPolys get generated, and in what per-brush sequence,
during `bsp_brush_csg`'s own incremental per-brush CSG loop (the `AddFunc`/`leaf_func` dispatch that
DECIDES whether/when to call `bspAddNode` at all, and the world-brush processing order feeding it) —
neither of which this round's decompile covered. That is the concrete next step for whoever picks this
up; a live per-brush Pass-1 tree-shape trace (the `prepart_tree_*` technique, not yet run at world level
for any of these levels) remains the most direct way to attribute the divergence to a specific brush/
decision, as already named in this file's prior rounds.

Harness (`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`): `decompile_bspaddnode.py` (the
`angr` recipe, including the `SimStruct.offsets` monkeypatch, documented inline),
`bspAddNode.decompiled.c` (the saved pseudo-C, ~10.8 KB, for future reference — re-decompiling costs the
same ~2 min `CFGFast` as the FilterEdPoly round), `disasm_bspaddnode_tail.py` (the raw `capstone` dump
used to cross-check the wrap-trim finding independently of the pseudo-C). `bspcsg.rs` change: the
wrap-trim + infinitesimal-polygon guard after the vertex-pool loop (~15 lines), plus 2 new unit tests.
Full `bin/test` run clean before shipping (see commit). Board:
`area51-entrance-residual-localized-to-brush1852` and `freeclinic08-nsfhq04-1-surf-under-build-root`,
both appended.

## Full-corpus A/B of `UEDCLI_BSPCSG_RING_NEAR` / `UEDCLI_BSPCSG_MERGE_NEIGHBOR_SAME`: RING_NEAR and BOTH are byte-identical on every level (corpus-wide confirmation); 5 levels improve, 3 regress (verts-only), 1 is the known Vandenberg tradeoff, 1 gets a genuinely clean multi-count win. DECISION NEEDED — not shipped, not decided here (2026-09-02)

Broadens the single-level (Vandenberg Gas) A/B from "INDEPENDENT PASS — full-breadth decompile" (this
file, above) to every level with a cached golden in `/tmp/uedcli-parity-cache/` (20 of 23 cache
entries; 3 excluded as gaps — see below). Pure measurement round: no source change, no default
flipped. Fresh worktree off `master` (`9988365`), native ext rebuilt clean (`.so` mtime confirmed
fresh). Harness: `dev/docs/spikes/2026-09-02-ring-threshold-corpus-measurement/harness/
measure_corpus.py` (adapted from the prior round's `measure_flag.py` — same cached-golden, no-live-
editor A/B technique, generalized from one flag/11 levels to three configs/every cached level), raw
JSON output and the table-builder script committed alongside it.

**Gaps (not measured — cache incomplete, not rebuilt per the "fast broad pass, not a deep dive"
instruction):** `04_nyc_street` (status `building`), `99_endgame4` (status `extracting`),
`dxmp_smuggler` (status `building`). A future round wanting these needs a live editor golden build.

**Corpus-wide confirmation: RING_NEAR and BOTH are IDENTICAL on all 20 measured levels, no
exception.** This was previously observed only on Vandenberg Gas ("once the ring welds seams to one
point, the merge threshold no longer bites"); it now holds everywhere in the corpus, including levels
where MERGE_NEIGHBOR_SAME ALONE differs sharply from OFF (`03_nyc_747`, `04_nyc_nsfhq`,
`06_hongkong_wanchai_market`, `14_oceanlab_lab`) — RING_NEAR fully absorbs the merge-threshold's
effect in every one of those cases too, not just Vandenberg's.

**Per-level nodes/surfs/leaves/verts delta (native − golden), each cell `n/s/l/v`:**

| level                      | OFF n/s/l/v       | RING_NEAR n/s/l/v | MERGE_NEIGHBOR_SAME n/s/l/v | BOTH n/s/l/v      | note |
| -------------------------- | ----------------- | ----------------- | --------------------------- | ----------------- | --- |
| 00_trainingfinal           | +105/+0/+13/+1464 | -59/+0/-11/+229   | +105/+0/+13/+1464           | -59/+0/-11/+229   | RING_NEAR/BOTH strictly better on ALL 4 counts |
| 01_nyc_unatcohq            | +350/+3/+39/+3242 | +350/+3/+39/+3248 | +350/+3/+39/+3242           | +350/+3/+39/+3248 |  |
| 02_nyc_bar                 | +0/+0/+0/+0       | +0/+0/+0/+0       | +0/+0/+0/+0                 | +0/+0/+0/+0       |  |
| 03_nyc_747                 | +68/+0/-10/+698   | +68/+0/-10/+717   | -290/+0/-59/-2540           | +68/+0/-10/+717   |  |
| 03_nyc_unatcohq            | +0/+0/+0/+5       | +0/+0/+0/+11      | +0/+0/+0/+5                 | +0/+0/+0/+11      |  |
| 04_nyc_nsfhq               | -92/+1/-26/-1774  | -92/+1/-26/-1714  | -230/+0/-24/-1594           | -92/+1/-26/-1714  |  |
| 04_nyc_underground         | +0/+0/+0/+26      | +0/+0/+0/+41      | +0/+0/+0/+26                | +0/+0/+0/+41      |  |
| 06_hongkong_helibase       | +9/+0/+0/+122     | +9/+0/+0/+101     | +9/+0/+0/+122               | +9/+0/+0/+101     |  |
| 06_hongkong_wanchai_garage | -68/+0/-12/-1224  | -68/+0/-12/-1222  | -68/+0/-12/-1224            | -68/+0/-12/-1222  |  |
| 06_hongkong_wanchai_market | +0/+0/+0/+74      | +0/+0/+0/+99      | +20/+0/+13/+210             | +0/+0/+0/+99      | MERGE_NEIGHBOR_SAME alone breaks node/surf/leaf exactness |
| 08_nyc_bar                 | +0/+0/+0/+0       | +0/+0/+0/+0       | +0/+0/+0/+0                 | +0/+0/+0/+0       |  |
| 08_nyc_freeclinic          | +0/+0/+0/+1       | +0/+0/+0/+1       | +0/+0/+0/+1                 | +0/+0/+0/+1       |  |
| 09_nyc_shipfan             | +0/+0/+0/+1       | +0/+0/+0/+1       | +0/+0/+0/+1                 | +0/+0/+0/+1       |  |
| 10_paris_chateau           | +4/+0/+0/+16      | +4/+0/+0/+16      | +4/+0/+0/+16                | +4/+0/+0/+16      |  |
| 10_paris_club              | +2/+0/+0/+36      | +2/+0/+0/+76      | +2/+0/+0/+36                | +2/+0/+0/+76      |  |
| 11_paris_underground       | -108/+0/-4/-1306  | -108/+0/-4/-1306  | -108/+0/-4/-1306            | -108/+0/-4/-1306  |  |
| 12_vandenberg_gas          | +32/+0/+5/-126    | -6/+0/-56/-1354   | +32/+0/+5/-126              | -6/+0/-56/-1354   | RING_NEAR/BOTH: nodes better, leaves/verts worse (tradeoff) |
| 14_oceanlab_lab            | +465/+0/+86/+3980 | +465/+0/+86/+5198 | +802/-1/+164/+6566          | +465/+0/+86/+5198 |  |
| 15_area51_entrance         | +85/+0/+51/+1055  | +85/+0/+51/+1038  | +85/+0/+51/+1055            | +85/+0/+51/+1038  |  |
| dx                         | +0/+0/+0/+0       | +0/+0/+0/+0       | +0/+0/+0/+0                 | +0/+0/+0/+0       |  |

**MERGE_NEIGHBOR_SAME alone: confirmed NOT shippable, corpus-wide.** It never strictly improves any
level (every cell it changes from OFF is either unchanged or worse). It breaks `06_hongkong_
wanchai_market`'s node/surf/leaf exactness (+20 nodes/+13 leaves, reproducing this file's earlier
Wanchai regression finding exactly) and swings `03_nyc_747` (+68→-290 nodes), `04_nyc_nsfhq` (-92→-230
nodes), and `14_oceanlab_lab` (+465→+802 nodes) sharply worse. Consistent with the standing
conclusion that the 0.015 merge-neighbor threshold is a symptom-patch for the ring-pool threshold, not
an independently correct value.

**RING_NEAR / BOTH: a genuine multi-way tradeoff across the corpus, not a clean win.**

- **Zero currently-exact levels lose node/surf/leaf exactness.** All 8 levels with `OFF` nodes=surfs=
  leaves=0 (`02_nyc_bar`, `03_nyc_unatcohq`, `04_nyc_underground`, `06_hongkong_wanchai_market`,
  `08_nyc_bar`, `08_nyc_freeclinic`, `09_nyc_shipfan`, `dx`) stay structurally exact under RING_NEAR/
  BOTH. But **3 of those 8 regress on verts** (`03_nyc_unatcohq` +5→+11, `04_nyc_underground` +26→+41,
  `06_hongkong_wanchai_market` +74→+99) — a real cost against the project's actual goal (full BYTE
  parity, not just the looser node/surf/leaf "EXACT" label; see the `goal-full-byte-parity` note this
  file's readers should already have in mind).
- **5 levels improve** (`00_trainingfinal`, `04_nyc_nsfhq`, `06_hongkong_helibase`,
  `06_hongkong_wanchai_garage`, `15_area51_entrance`) — but 4 of the 5 (all but `00_trainingfinal`)
  improve ONLY on verts; nodes/surfs/leaves are byte-identical to OFF. This matches the earlier
  single-level finding that the ring threshold "does NOT move the rotated-brush open cases" — these 4
  are exactly that class (`nsfhq`/`helibase`/`wanchai_garage`/`area51` node counts are untouched,
  confirming the primary UNATCO-class world-repartition over-build problem is still not this lever).
- **`00_trainingfinal` is a genuinely NEW, cleaner result than anything found before this round:**
  nodes +105→**-59** (magnitude 105→59), leaves +13→**-11** (13→11), verts +1464→**+229** (1464→229)
  — every one of the 4 counts moves toward zero, none regress. This is the first level found in this
  whole investigation thread where RING_NEAR/BOTH improves node AND leaf AND vert magnitude together,
  not just verts, and not as a nodes-vs-leaves tradeoff like Vandenberg. Worth flagging loudly:
  whatever caused this level's original over-build looks closer to Vandenberg's scaled-brush class
  than the rotated-brush class the other 4 improving levels belong to, and here the fix is unambiguous.
- **3 levels regress, verts-only** (`01_nyc_unatcohq` +3242→+3248, `03_nyc_747` +698→+717,
  `10_paris_club` +36→+76) — none currently node/surf/leaf-exact, so no exactness is lost, but the
  regression is real and, for `10_paris_club`, more than doubles the vert delta.
- **`12_vandenberg_gas` reproduces the exact prior single-level finding** (nodes +32→-6 improves,
  leaves +5→-56 and verts -126→-1354 regress) — the corpus run is a clean replication, not a new
  result, and confirms this round's harness against the already-published number.
- **`11_paris_underground` shows ZERO effect** from any flag (identical across all 4 configs) — no
  sub-0.015 ring seams present in this level's CSG fragments.

**Conclusion — DECISION NEEDED, not made here.** Per the standing rule (a change that improves some
counts while regressing others on any level is a tradeoff for the owner, not a silent default flip),
none of RING_NEAR/MERGE_NEIGHBOR_SAME/BOTH is shipped or defaulted on by this round. The corpus data
narrows the tradeoff's shape but does not resolve it:
- MERGE_NEIGHBOR_SAME alone is now conclusively dead — no level anywhere in the corpus favors it over
  OFF or over RING_NEAR/BOTH.
- RING_NEAR (== BOTH) is a **net-positive-leaning but not clean** change: 5 levels improve (1 of them,
  `00_trainingfinal`, unambiguously and on every count) vs 3 that regress (all verts-only, no lost
  exactness) vs 1 genuine cross-count tradeoff (Vandenberg) vs 11 unaffected. Whether "5 up / 3 down
  (verts-only) / 1 mixed / 11 flat, with one clean multi-count win" clears the bar for shipping as the
  new default, stays gated for opt-in measurement, or needs the `00_trainingfinal`-class win isolated
  from the rest, is the owner's call.

`bin/test` not run — zero `.rs`/`.py` production files touched this round (pure env-var-gated
measurement via the existing `UEDCLI_BSPCSG_RING_NEAR`/`UEDCLI_BSPCSG_MERGE_NEIGHBOR_SAME` flags
already shipped gated-off in `bspcsg.rs`); the native ext build itself (`maturin build --release`)
and a spot-check against the `dx` level (all 4 configs byte-identical, `nodes=surfs=leaves=verts=0`
delta) are the only correctness checks this round needed.

## NYC 747 rotated-brush transform cross-validation: localized the residual to a diffuse, unrotated-brush class; found (and confirmed FOR THE FIRST TIME) a real few-ULP `FPoly::transform` divergence on the level's one non-cardinal multi-axis brush, but it does NOT explain the residual (2026-09-02)

Independent, parallel cross-validation of the same hypothesis being tested on Area51 Entrance:
`rotation.py`'s own module header flags a THEORETICAL gap — a genuine NON-CARDINAL multi-axis
FRotator composes its 3×3 in Python double (`euler_to_matrix_uu` → `matmul(Rz, matmul(Ry, Rx))`,
what `brush_marshal._build_brush_input` hands the Rust `FPoly::transform` as `rot`), while the real
editor composes in float32 `FCoords`; every rotation checked up to now was single-axis or CARDINAL
multi-axis, both proven bit-identical, so the gap was flagged "unexercised and UNMEASURED against the
editor." NYC 747 (`03_NYC_747.dx`) currently sits at nodes native=4530 golden=4462 (d=+68), surfs
EXACT (2026/2026), leaves native=560 golden=570 (d=-10) — unchanged from every prior round including
the `INDEPENDENT PASS` ring-pool measurement, confirmed fresh this round (`parity_report.py`, cache
hit on golden hash `3c2fa428…`).

**Step 1 — inventory every world-CSG brush's Rotation** (`nyc747_scan_rotations.py`, fresh worktree
off `master` `9988365`): 373 world-CSG brushes, 195 rotated (non-identity). Of those, exactly **ONE**
is a genuine non-cardinal multi-axis case: `Brush562`, `Rotation=(Pitch=32768,Yaw=32768,Roll=59392)`
— Pitch/Yaw are both cardinal (180°), but `Roll=59392` is not a multiple of 16384 (59392/16384 =
3.625). This is the first confirmed real instance of the theoretical case `rotation.py` flags as
unmeasured, anywhere in the corpus checked so far.

**Step 2 — is Brush562 actually implicated in the residual?** Since surfs are already exact (unlike
the earlier OceanLab/NYC747 surf-count fixes), the surf-count attribution method
(`nyc747_surf_diff.py`) shows nothing; used node-plane-OWNER attribution instead
(`node.i_surf → surf.i_actor`, `vandenberg_attrib.py`'s method — `nyc747_attrib.py`). Result: 155/373
brushes differ in node-plane-ownership (abs-sum 754, net +68, matching the level's full delta).
**Brush562's own node ownership is IDENTICAL: native=8, editor=8** — it contributes ZERO to the
residual. The dominant single outlier is `Brush473` (CSG_Add, 291 polys, **no Rotation at all**,
d=+124 — nearly double the level's whole net delta, heavily cancelled by everything else), and most
of the rest of the diff list is unrotated small brushes (`npolys=6`, simple boxes) plus several
*single-axis, cardinal* `Yaw=±32768`/`Yaw=-32768` rotated brushes (already proven bit-exact per
`rotation.py`'s own scope note) — the same diffuse "FindBestSplit tie-break"-class signature already
on record for UNATCO/nsfhq04/Training Final/Area51, not a rotation-transform signature.

**Step 3 — bit-level check of Brush562's rotation matrix anyway** (`brush562_bitcheck.py`), per the
task's explicit requirement to verify the transform math bit-exactness directly, not just infer it
from the attribution result. Simulated the real editor's float32 `FCoords` compose (each axis matrix
built from f32 GMath table values, every multiply-accumulate rounded to f32 at each step, same
Rz·(Ry·Rx) association) and diffed it entry-by-entry against the production
double-precision `euler_to_matrix_uu` result. **One entry differs: `R[0][1]`, by 2 ULP**
(double-path 0x32cf302e vs simulated-f32-path 0x32cf3030, magnitude ~2.4e-8) — every other entry is
bit-identical. This is the first actual MEASUREMENT of the gap `rotation.py` only theorized.

**Step 4 — does that 2-ULP matrix entry propagate to a real vertex/normal/plane difference?**
(`brush562_vertex_compare.py`): paired every one of Brush562's 8 native node planes against the
golden's actual 8 node planes (nearest-plane match, since node/surf order need not agree even when
the plane SET does). **5 of 8 are byte-identical** (the two axis-aligned cap planes untouched by the
Roll tilt, `(1,0,0,…)`/`(-1,0,0,…)`). **3 of 8 differ by 1–6 ULP** in the components touched by the
Roll rotation (e.g. plane `(-1.2126e-7, 0.55557030…, -0.83146960…, -724.16876…)` native vs
`(-1.2126e-7, 0.55557024…, -0.83146960…, -724.16870…)` editor — Y and W off by 1 ULP each; a third
plane off by up to 6 ULP across three components). **So the transform IS measurably, confirmedly NOT
bit-exact for this rotated brush** — the theoretical gap is real, not hypothetical, and this is the
first live-golden confirmation of it anywhere in the codebase.

**Conclusion.** Two things are both true and do not contradict each other: (1) `FPoly::transform`'s
double-precision rotation-matrix compose has a genuine, now-measured few-ULP divergence from the real
editor's float32 `FCoords` compose on a genuine non-cardinal multi-axis rotation — exactly the
mechanism the task's hypothesis proposed, confirmed bit-for-bit against a live self-built golden, not
inferred. (2) It does **not** explain NYC 747's open node/leaf-count residual: Brush562's own node
ownership is exactly right (8=8, no extra/missing splits — a few-ULP plane-VALUE drift with no
tree-SHAPE consequence for this brush's specific geometry), and the level's actual dominant
contributor (`Brush473`, d=+124) carries no rotation whatsoever. The residual is the same diffuse,
still-unexplained tree-shape class already open on UNATCO/nsfhq04/Training Final/Area51 Entrance —
this round did not move it, and per the standing no-guessing rule **no fix was shipped** (nothing to
narrow: Brush562 already matches).

**Worth a separate look, NOT scoped to this round:** the confirmed few-ULP `plane`-value drift is a
genuine CONTENT-exactness gap (would show up as a `parity_report.py` "content NOT EXACT" field diff
even on a level that's already node/surf/leaf-COUNT-exact), relevant to the standing full-byte-parity
goal independent of any node/leaf-count residual. Filed as a board inbox item rather than fixed here —
fixing it means porting a float32 `FCoords`-style compose into `rotation.py`/`fpoly.rs` specifically
for the non-cardinal multi-axis case, unverified against any level that would actually benefit (no
DX level in the corpus is known to be blocked on this — Brush562 itself is not), and this round found
no live case to validate a fix against.

**Left uncommitted / for reconciliation:** this round touched no production code (`uedcli-native/src`,
`uedcli/`) — only the harness scripts under
`dev/docs/spikes/2026-09-02-nyc747-rotated-transform/harness/`. If the parallel Area51 Entrance agent
independently ships a `fpoly.rs`/`rotation.py` change for the same non-cardinal-multi-axis ULP gap,
this round's Brush562 measurement (2 ULP matrix / 1–6 ULP plane) is a second, independent data point
for it — not a conflicting one — since it confirms the mechanism is real without needing the fix to
close NYC 747's own residual.

Harness: `dev/docs/spikes/2026-09-02-nyc747-rotated-transform/harness/` — `nyc747_scan_rotations.py`
(rotation inventory), `nyc747_attrib.py` (node-plane-owner attribution), `brush562_bitcheck.py`
(matrix-level bit compare), `brush562_vertex_compare.py` (plane-level bit compare against the live
golden). Fresh worktree off `master` `9988365`. `bin/test -k fpoly`: 17/17 pass. Full `bin/test`:
same pre-existing 10 failures as every prior round (2 `test_board.py` frontmatter on unrelated items,
7 `test_csg_native_differential.py` tuple-length `ValueError`s, 1 `test_doc_links.py`) — zero
regression, since zero production code changed.

## `build_ued_golden.py`'s `_wait_idle` now defensively dismisses the GC dialog — fixes the operational stall that blocked Training Final's live prefix search (2026-09-02)

Infra fix, not a CSG/BSP finding — addresses the harness gap the prior "Training Final live prefix
search: BLOCKED" round (above) flagged: `_wait_idle` polled `docker stats` for CPU-idle but never
called `Driver.dismiss_blocking_dialog()`, unlike `qualify.dump_obj_dependencies`/`_read_loaded_classes`
(`unrealed/quirks.md` "Stability"), so the "Cleaning up..." GC `xmessage` dialog — which never
auto-closes headless — could sit forever with nothing to dismiss it, timing the caller out at its own
ceiling (observed live: `map-new` at 1800s, `rebuild[0]` at the 2400s `--rebuild-timeout`).

**Fix** (`dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py`): `_wait_idle` now
takes the `Driver` (was the bare container-name string) and calls `driver.dismiss_blocking_dialog()`
on every poll iteration, before the `docker stats` CPU read — mirroring the established
`qualify.py` pattern exactly (same call, same per-iteration cadence), not inventing a new one. All 5
call sites in `main()` (`obj-load`/`map-new`/`re-add`/`rebuild[i]`/`light-apply`) updated to pass the
already-constructed `Driver` instance instead of the container name.

**Verified two ways:**
1. Offline mocked unit check (no docker) against a `Driver` stub: confirms `dismiss_blocking_dialog()`
   fires every poll in both the normal case (dialog never present — behavior identical to the
   pre-fix function) and a dialog-present-then-clears case, with the idle-detection state machine
   (`quiet_reads`/`thresh`/`timeout`) otherwise unchanged.
2. **Live end-to-end smoke test**, no `Test_Castle` needed (a fresh 1-brush scratch trunk built via
   `uedcli brush build cube` + `actor add -`, run through the PATCHED `build_ued_golden.py
   --world-only --no-light --no-obj-load` against a real ephemeral editor container): completed
   successfully — `map-new` idle after 377s, `re-add` after 33s, `rebuild[0]` after 179s, `MAP SAVE`
   wrote a valid 2908-byte `.dx`, exit 0. The 377s `map-new` wall time for a single-brush level (far
   longer than CPU-bound work alone would take) is consistent with the GC dialog having actually
   appeared and been dismissed mid-poll, not just an inert no-op path. Did not attempt to reproduce
   the original hang directly (non-deterministic per the prior round, and reproducing it needs
   sustained host contention this round didn't have) — the live smoke test instead confirms the
   patched function completes a real build cleanly, which is the documented fallback for this case.

Other spike harnesses under `dev/docs/spikes/*/harness/` (`build_ued_lit_golden.py`,
`oceanlab_isolate_golden.py`, `geo_golden_driver.py`, `vandenberg_*_golden.py`, `a51_editor_prefix.py`,
etc.) carry their OWN independent copies of `_wait_idle` — this fix only touches
`2026-07-15-native-materialize/harness/build_ued_golden.py`, the one the Training Final round actually
hit and the one this task was scoped to. The same gap likely exists in those other copies; not fixed
here (out of scope for this round, no live evidence any of them hit it) — worth checking before relying
on one of them for a long live drive.

Ready for a future round: Training Final's static lead (`Brush907`/`909`/`911`/`915`, world-CSG idx
660-668) can now be retried with the live prefix binary search (`tf_prefix_search.py`/`tf_probe.py`,
`dev/docs/spikes/2026-09-01-area51-training-final-residual/harness/`) without this specific stall —
host contention (the other named flakiness source in the prior round) is a separate, unaddressed risk.
