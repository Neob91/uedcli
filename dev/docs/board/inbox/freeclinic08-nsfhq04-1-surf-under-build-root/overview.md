+++
priority = "p2"
kind = "debug"
summary = "freeclinic08/nsfhq04's node deficit traced to the world-level bsp_build reconstruction (-38 nodes/-23 leaves on freeclinic08's structural-only set) — NOT the same repartition_frontier bug UNATCO's fix (bcc3693) closed; that fix is confirmed a no-op for these two levels"
+++

# freeclinic08/nsfhq04 +1-surf under-build

Follow-up to `breadth-geometry-re-check-across-11-og-levels-2`: dug into the two closest-to-exact
non-exact levels (freeclinic08 nodes -20/surfs +1/leaves -23, nsfhq04 nodes -78/surfs +1/leaves
-26).

**CORRECTION (2026-08-30, same session, independently re-verified before overwriting per the
findings-ledger process):** this item originally claimed `uedcli-native/src/csg.rs`'s
`classify_fragment` (a nudge-based point-in-solid approximation) was the root mechanism. That is
**wrong** — `csg.rs::bsp_brush_csg`/`classify_fragment` is called only from `build.rs`, which backs
`build_geometry` (the OLD default path). `uedcli_native.build_geometry_bspcsg` — the function every
script in this investigation (and `breadth_gate.py`) actually calls — dispatches to
`bspcsg::build_geometry_bspcsg`, which has its **own**, separate `bsp_brush_csg`/`filter_ed_poly`
(`bspcsg.rs` ~700-900, ~2433-2530): a faithful recursive BSP-node-plane descent (Split::Front/Back/
Split/Coplanar, CSG-adjusted `outside` propagation, exact-0.0 coplanar facing test) that matches the
editor's real `FilterEdPoly`/`bspBrushCSG` algorithm as decoded in
`dev/docs/spikes/2026-07-15-native-materialize/sections/10-bsp-csg-build.md` §4 and
`re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`. Re-ran that doc's verification harness
(`verify_csg_build.py`) against the CURRENT `uned/UED22/Editor.dll`/`Engine.dll` this session:
**33/33 checks pass** — the decoded algorithm is confirmed live, not just read from a pre-2026-08-14
doc. So there is no "port the real algorithm" work to do — it's already there and correct as far as
the decode goes. The real question is why a faithful `filter_ed_poly` still misclassifies Brush143's
poly1; see "Live investigation" below.

## The +1 surf, precisely

Per-brush surf-count attribution (`_scratch/fc08_surf_diff.py`, matching native `BspSurf.i_actor`
— a 0-based world-CSG brush index — against golden's `i_actor` resolved via
`epkg.name_of_ref`) finds **exactly one** brush differs in both levels:

- freeclinic08: `Brush143` (world-csg idx 144) — native attributes 6 surfs to it, editor 5.
- nsfhq04: `Brush531` (world-csg idx 733) — same 6-vs-5 pattern.

Both are `CsgOper=CSG_Add`, `PolyFlags=32` (`PF_Semisolid`) brushes. For Brush143 (a 6-poly
beveled-corner wedge, ~72×72×2uu), native keeps its authored poly index 1 (the underside, base
point world `(1088, -2432, -274)`, normal `(0,0,-1)`) as a surf; the editor's built model has no
surf for that poly at all — every other poly (0, 2, 3, 4, 5) matches exactly (same base
point/normal on both sides).

## Live investigation (in progress, current session continuation)

`Brush143` is `PF_Semisolid CSG_Add`, so per the decoded `csgRebuild` pass order (§1 of the
`10-bsp-csg-build.md` spec, now live-reverified) it is processed in **PASS B** (the semisolid
"detail" loop), which runs AFTER PASS A's structural brushes have gone through ONE full
`bspRepartition` (BuildFPolys → MergeCoplanars → bspBuild/SplitPolyList → bspRefresh). So
`filter_ed_poly`'s descent for Brush143's poly1 walks the PASS-A **repartitioned** tree, not a raw
incremental append chain — `bspcsg.rs`'s `build_geometry_bspcsg` already mirrors this two-pass
structure (own code comments: "Pass 1: STRUCTURAL... Pass 2: SEMISOLID detail... NOT
repartitioned").

**Hypothesis under test:** if PASS A's own repartitioned structural tree is ALREADY not
node-exact vs the editor at the point Brush143 is processed (the same class of repartition/
`FindBestSplit` tie-break sensitivity that drives UNATCO's still-unresolved residual and the
diffuse 74-brush node-ownership smear below), Brush143's poly1 would land on a different node/
plane sequence during its `filter_ed_poly` walk purely as a DOWNSTREAM consequence — not a bug in
`filter_ed_poly` itself, and not independently fixable without first closing the PASS-A
repartition gap (the same open problem as UNATCO).

Test: built a `freeclinic08` trunk with all 164 semisolid-Add ("detail", PASS-B) world-CSG
brushes removed (141 structural brushes remain), then compared NATIVE's `build_geometry_bspcsg`
on that same structural-only brush list against a live UnrealEd `--world-only --no-light` build of
the identical filtered trunk (`build_ued_golden.py`, the same golden-build method the findings
ledger already validated).

**Result — CONFIRMED, hypothesis correct** (`/tmp/fc08_native_structural.py`,
`/tmp/fc08_golden_counts.py`):

| | nodes | surfs | leaves |
|---|---|---|---|
| native structural-only | 1141 | 680 | 290 |
| editor structural-only (live) | 1179 | 680 | 313 |
| delta | **-38** | 0 | **-23** |

Surfs match exactly (680=680) — Brush143's `+1 surf` is entirely a PASS-B effect, confirmed absent
when PASS B never runs. But nodes/leaves do NOT match: PASS A's own structural tree is already
**-38 nodes / -23 leaves**, same face set (0 surf delta) — the identical symptom shape as UNATCO's
residual (same face set, different tree shape only). So PASS A is confirmed non-exact *before*
Brush143 is even reached; its `filter_ed_poly` walk descending a wrong tree is sufficient to explain
the `+1 surf`, with no separate bug needed in `filter_ed_poly` itself. (The full-build leaf delta,
-23, exactly matches the structural-only leaf delta -23 — the semisolid PASS-B brushes don't move
leaf count at all here. The node delta shifts -38 → -20 once PASS B runs, i.e. adding the semisolid
brushes back happens to cancel 18 of the 38 structural-only node misses — cancellation, not a sign
PASS B fixes anything.)

## The -20/-78 node and -23/-26 leaf deficit is diffuse, not localized

Per-brush BSP-node-plane-owner attribution (`_scratch/fc08_node_owner_diff.py`: for each node,
resolve its splitting surf's owning brush via `node.i_surf -> surf.i_actor`, Counter per brush,
diff native vs editor) on freeclinic08: **75 of 305 brushes** (25%) have differing node-plane-
owner counts, summing to 260 in absolute delta against a net of -20 — heavy cancellation, not one
or two brushes driving the total. Top individual deltas (Brush28 -17, Brush62 -17, Brush175 +13,
...) are semisolid-brush-heavy, but freeclinic08 is 164/305 (54%) semisolid brushes overall, so
that's roughly base rate, not enrichment — semisolid-ness alone doesn't isolate the affected set.

This spread is consistent with the SAME kind of repartition/`FindBestSplit` tie-break sensitivity
UNATCO's residual shows — each near-tie shift rippling through which face becomes a repartition
split plane, the same kind of tree-shape cascade the Wanchai `try_to_merge` NEAR-threshold fix
(5b0a022) demonstrated (one merge-threshold miss on Brush754 alone moved Wanchai's node count by
20). Whether it's literally the SAME root cause as UNATCO's (unresolved, `blanket_merge` gated
off) or a distinct instance of the same class is what the live structural-only test above is
checking.

## Distinct from UNATCO's paused residual? — same class, confirmed

The previous version of this item claimed freeclinic08/nsfhq04 are **definitely not** the same bug
as UNATCO, based on the (now-corrected) `classify_fragment` claim. That was wrong the other way
too: the structural-only result above shows freeclinic08's PASS-A tree alone reproduces UNATCO's
exact residual *signature* — same face set (0 surf delta), node/leaf-count-only divergence
(-38/-23) — before the semisolid brushes that produce the final `+1 surf` are even added. The
FINAL full-build counts still differ from UNATCO's (freeclinic08 has a nonzero surf delta, UNATCO
doesn't), but that's because freeclinic08 additionally runs a PASS-B semisolid brush whose
classification depends on the already-wrong PASS-A tree — one root cause (PASS-A repartition
tie-break gap), two different-looking final symptoms depending on what PASS B does with it.

## Why not fixed this session

The structural-only test confirms PASS A is already non-exact (-38 nodes/-23 leaves, 0 surf delta)
before Brush143 is even processed — architecturally the same class of problem as UNATCO's residual
(a repartition/`FindBestSplit` tie-break gap), not a locally fixable bug in `filter_ed_poly` or
Brush143's classification. Per the task's "don't grind if architecturally stuck" instruction, this
item stops here rather than chasing PASS-A repartition parity — UNATCO's own investigation and the
concurrent Wanchai verts/points investigation have already spent large effort on this exact class
of problem with no resolution (see `native-materialize-findings.md`'s Wanchai entry, same session:
"correct per call, wrong in aggregate" contradiction, also stopped on coordinator steer).

## Harness

Scripts written this session (not yet promoted out of `_scratch/`, which is gitignored — rerun
against a clean tree before relying on them long-term): `_scratch/fc08_surf_diff.py`,
`_scratch/fc08_brush143.py`, `_scratch/fc08_poly1_verts.py`, `_scratch/fc08_node_owner_diff.py`,
`_scratch/fc08_combined_diff.py` (surf-count vs node-owner cross-reference — confirms 74/75
node-owner-divergent brushes have MATCHING surf counts, i.e. same face set/different split shape;
only `Brush143` differs in both), `/tmp/fc08_filter_trunk.py` + `/tmp/fc08_native_structural.py`
(builds the structural-only filtered trunk under `_scratch/fc08-structural-only/` and gets native's
counts) + `/tmp/fc08_golden_counts.py` (parses the live `build_ued_golden.py --world-only --no-light`
output of that same trunk) — the PASS-A-only structural comparison that confirmed the result above;
not yet promoted to a committed path, none survive in `/tmp` past this session — copy alongside the
others if this line of investigation continues. Baseline re-confirmed via
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/breadth_gate.py` unchanged (3/13
exact) at session start; no source changes were made, so no re-run needed after.

Also independently re-ran `dev/docs/spikes/2026-07-15-native-materialize/harness/verify_csg_build.py`
against the current `uned/UED22` binaries this session (`pip install pefile capstone` into
`.venv`) — 33/33 checks pass, confirming the `10-bsp-csg-build.md` §4 CSG-filter decode (which
`bspcsg.rs`'s `filter_ed_poly`/leaf funcs already implement) is still accurate on the current
tree, not just trusted from the pre-2026-08-14 doc.

## 2026-08-30 continuation: does the `repartition_frontier` fix (`bcc3693`) close this? — NO, and now we know precisely why

`bcc3693` ("`repartition_frontier`: reproduce the editor's real no-op-on-nodes fix") shipped after
this item's last entry and made UNATCO node/surf/leaf-EXACT. `breadth_gate.py` re-run post-fix:
freeclinic08 `nodes -30 surfs +1 leaves -23`, nsfhq04 `nodes -92 surfs +1 leaves -26` — same shape,
**unchanged** from before the fix. Re-verified from scratch (candidate 1 in the follow-up task: maybe
these levels never shared UNATCO's actual mechanism, just a similar-looking symptom) using
`UEDCLI_BSPCSG_STAGE_COUNTS` on the pre-existing `_scratch/fc08-structural-only/` golden (141
non-semisolid brushes, no Pass 2 at all):

```
STAGE post-repartition        nodes=1141   (golden final: 1179)
STAGE post-testvisibility     nodes=1141   (unchanged)
STAGE post-pass2              nodes=1141   (Pass 2 empty — 0 semisolid brushes in this set)
STAGE post-repartition-frontier nodes=1141 (unchanged — confirmed no-op)
STAGE post-finalize           nodes=1141   (unchanged)
STAGE post-optgeom            nodes=1141   (unchanged)
final: nodes -38, surfs +0, leaves -23 — BYTE-IDENTICAL to this item's own pre-fix measurement
```

**Confirmed: freeclinic08/nsfhq04 do NOT share UNATCO's mechanism.** UNATCO's bug lived entirely
inside `repartition_frontier`'s per-subtree calls (209/119 calls, run AFTER the semisolid detail
loop). freeclinic08's node deficit is already fully present at `post-repartition` — the ONE-TIME
world-level `bsp_build_fpolys`→`bsp_merge_coplanars`→`bsp_build` reconstruction, which runs BEFORE
`repartition_frontier` and is untouched by `bcc3693`. `repartition_frontier` is directly confirmed a
genuine no-op here (1141 unchanged across every later stage, including on the FULL build with real
Pass-2 growth: `post-pass2` 2492 → `post-repartition-frontier` 2492 unchanged; nsfhq04 same, 7564→7564
unchanged) — so the fix had literally nothing to act on for either level. That is the complete answer
to "why didn't the fix generalize": it fixed a different call site than the one these two levels are
actually broken in.

Cross-check: UNATCO's own world-level stage is independently confirmed EXACT (`post-repartition`
nodes=2953, matching the live-gdb-captured editor STAGEEND value already on record from
`emptymodel_worldlevel_trace.py`) — so native's world-level `bsp_build`/`FindBestSplit` machinery is
not systematically broken; something about freeclinic08/nsfhq04's specific brush sets trips it.
Re-ran the node-plane-owner attribution (`fc08_node_owner_diff.py`-style) isolated to the
structural-only world-level result: 37/141 brushes (26%) differ, summing to 102 absolute delta
against a net −38 (heavy cancellation) — the same diffuse, `FindBestSplit`-tie-break-shaped signature
as before, just now correctly attributed to the world-level one-shot call instead of
`repartition_frontier`'s per-subtree calls.

**Not fixed.** The root cause of the world-level `bsp_build`'s own divergence — why `FindBestSplit`
picks a different tree for freeclinic08's/nsfhq04's specific merged poly soup — is still open. Closing
it needs a live gdb capture of the editor's real world-level poly order for a ~141-poly soup
(`fbs_root_poly_order.py`-style, scaled up from UNATCO's single-subtree `child=6108` capture); not
attempted this round (diminishing-returns judgment call, per the task's own budget guidance — this
round's goal was root-causing why the UNATCO fix didn't generalize, which is now answered). No
`bspcsg.rs` changes; `regression_gate.py` UNATCO/Wanchai unchanged, `GATE: PASS`. Findings ledger entry
added in `native-materialize-findings.md` (search "DIFFERENT call site, not the same bug").

## No level added

freeclinic08 and nsfhq04 remain not-exact. The breadth gate is unchanged: 3/13 (2/11 unique
levels + the trivial `DX.dx`) still exact, still below the 30% floor.

## 2026-08-30, second continuation: world-level root cause found — poly-list ORDER, not scoring

Picked up the concrete next step named at the end of the last section: a live gdb capture of the
editor's real world-level `FindBestSplit` poly order, scaled up from the single-subtree technique
(`fbs_root_poly_order.py`) to the world-level call (`fbs_world_poly_order.py`, new, committed to the
harness dir).

**Result: CONFIRMED.** Target: freeclinic08's structural-only 141-brush golden (already isolates
Pass-2 out; 0 surf delta, −38 node delta). Native's own world-level `split_poly_list` call (offline,
`UEDCLI_REPART_FBS_DUMP` — a pre-existing diagnostic, no new capture needed for this half) has
`numpolys=1019`. The live gdb capture also got **1019** `FBSPOLY` entries for the same brush set —
same merged-poly-set SIZE both sides, so the divergence isn't a missing/extra poly. `Opt::Good`'s
stride for 1019 is `inc=50`, so only 21 candidates (indices 0,50,…,1000) ever get scored, on both
sides. The real editor's actual root split (read straight off the golden `.dx`, node[0].plane) is
`(0,−1,0,896)`. In the LIVE-CAPTURED real order, the poly with that exact plane sits at **k=700** —
itself a sampled window-start (`14×50`), an exact plane match at a genuinely-evaluated index: about
as decisive as evidence gets, since `FindBestSplit` can only return a plane it actually scored. In
NATIVE's own reconstruction (same brush set, `UEDCLI_BSPCSG_SOUP_ORDER`), the identical poly (matched
by plane AND the internal `i_link`, which numbers consistently across both captures) sits at **k=672**
— inside an already-sampled-elsewhere window, never tested. Native's own world-level winner
(`i=600`, plane `(1,0,0,576)`) is real and correctly the lowest-scoring **among the 21 candidates its
own list order exposes it to** — `find_best_split_exact`'s windowed-stride selection is exonerated a
SECOND time (first was UNATCO's `child=6108`): the algorithm is faithful, it is scoring the wrong
candidate set because the input order differs. A second poly (`i_link=57`) shows the same shape at a
different magnitude (editor `k=468` vs native `k=124`, a 344-position shift vs the first poly's
28-position shift) — ruling out a simple constant/linear reindex; this is a genuine structural
reordering, not a uniform permutation.

This is a DIFFERENT finding than the earlier "ordering hypothesis was wrong" conclusion for UNATCO's
`repartition_frontier` subtree calls (`child=6108`) — that call's whole reconstruction gets discarded
by `bspRefresh`, so its input order turned out irrelevant to the persisted tree. That escape hatch does
NOT exist here: the world-level call is confirmed (`emptymodel_worldlevel_trace.py`, prior session) to
commit straight to the persistent Model, so poly order here genuinely determines the real, final,
shipped tree shape.

**Not further root-caused, no fix shipped**, per the standing "no algorithm not confidently known"
rule. WHY native's world-level poly order differs from the editor's real order — traced to Pass-1's
incrementally-built tree shape, to `bsp_merge_coplanars`'s grouping/walk order, or elsewhere — is
still open; closing it needs at least one more live capture (the editor's real PRE-world-level tree
order, the `prepart_tree_*` technique not yet applied at world level) at a scope comparable to the
rest of this investigation. Diminishing-returns call per the task's own budget: this round's question
(order vs. scoring) is answered with high confidence; a speculative reorder was deliberately NOT
attempted (would be the forbidden tolerance-fudge). No `bspcsg.rs` changes — read-only capture only.
Full write-up: `native-materialize-findings.md`, search "poly-list ORDER mismatch". New file:
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/fbs_world_poly_order.py`.

## 2026-08-30, third continuation: divergence traced one stage further — already present coming out of Pass 1, not introduced by `bspBuildFPolys` or `bspMergeCoplanars`

Picked up the concrete next step from the second continuation: a live capture of the two
intermediate stage boundaries inside the world-level `bspRepartition` call — right after
`bspBuildFPolys` returns (pre-merge) and right after `bspMergeCoplanars` returns (post-merge) — to
localize which of the three steps (`bspBuildFPolys` extraction order, `bspMergeCoplanars` grouping/
walk order, or something already present in Pass 1) introduces the poly-order divergence.

New harness (`fpolys_stage_order.py`): disassembled `bspRepartition` fresh (`rdis.py dis Editor
0x10049fc0 0xb0`) to get the real return addresses after calls 1 and 2 (`0x1004a00d`, `0x1004a027`),
resolved the real vtable-dispatched function addresses via the already-committed `vtable-dump.log`
(`bspBuildFPolys=0x10036090`, `bspMergeCoplanars=0x10036200`), then broke at each return address and
dumped the CTX object's `Polys` array. First attempt used the offsets from an old, never-live-tested
ledger entry (`[[CTX+0x54]+0x2c]`=Data) and got garbage (`data=0x535 count=1449 max=91422268` —
`0x2c` is actually `Count`, not a pointer). Two more probe scripts
(`ctx_polys_struct_probe.py`/`_probe2.py`) found the real layout by testing candidate offsets as
`FPoly*` and checking for a sane unit normal: `Data=+0x28, Count=+0x2c, Max=+0x30` — 4 bytes off
from the old entry, now corrected in the ledger and in `fpolys_stage_order.py`'s own docstring.

**Result, freeclinic08's structural-only 141-brush golden:**

| stage | editor (live) | native | match |
|---|---|---|---|
| PREMERGE (post-`bspBuildFPolys`) | 1333 polys | 1263 polys | first order divergence at k=2; **counts differ** |
| POSTMERGE (post-`bspMergeCoplanars`) | 1019 polys | 1019 polys | same i_link multiset; same k=2 divergence pattern |

The POSTMERGE capture cross-validates cleanly against the already-committed
`fbs_world_poly_order.py` FindBestSplit-entry capture — index-for-index identical (`i_link=57` at
`k=468` both ways) — confirming `bspBuild` doesn't reorder between merge output and
`FindBestSplit`'s own input, and that the corrected CTX offsets are right.

**The count mismatch at PREMERGE (1333 vs 1263) is the finding.** It's not just reordering — the
real editor's Pass-1 incremental tree carries ~70 more raw poly-fragments than native's own Pass-1
tree for the identical 141-brush set, even though both sides converge to the SAME 1019-face
POSTMERGE set (and, per this item's own earlier measurement, the same final 680-surf set).
`bspMergeCoplanars`'s grouping/walk order is independently confirmed elsewhere in the findings
ledger to faithfully reduce whatever fragment soup it receives (child=6108's 40→29 merge matches the
editor's real root split exactly), and `bspBuildFPolys`/`make_ed_polys` is a plain DFS tree-walk on
both sides — so neither step INTRODUCES this divergence. It's inherited from a genuine tree-shape
difference already present in Pass 1's own incrementally-built world tree, before any of the three
repartition steps run.

**Not further root-caused.** WHY the real editor's Pass-1 tree ends up with ~70 more fragments for
the identical face set — a different CSG split/classification order across the 141 brushes, or a
gap in native's `bsp_brush_csg`/`filter_ed_poly` the existing 33/33 disassembly check-set doesn't
exercise — needs a live per-brush Pass-1 tree-shape trace (the `prepart_tree_*` technique, not yet
run at world level for freeclinic08) to attribute the delta to specific brushes. Per the standing
rule, no reorder/fudge fix attempted.

**No fix shipped.** `bspcsg.rs` change: one additive `ALL` mode on the pre-existing env-gated
`UEDCLI_BSPCSG_PREMERGE_DUMP` diagnostic (was name-filtered only) — zero effect on the default path
(`bin/test -k bspcsg` 90/90, `regression_gate.py` UNATCO/Wanchai both EXACT, `GATE: PASS`, before and
after). This is the 3rd consecutive round on this thread; the question posed this round (which step
introduces the divergence) is answered with high confidence — none of the three, it's upstream of
all of them — and this is logged as the next round's starting point rather than chased further here,
per the task's own diminishing-returns budget guidance.

New files (`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`): `fpolys_stage_order.py`,
`ctx_polys_struct_probe.py`, `ctx_polys_struct_probe2.py`. Log:
`.../logs/fpolys-stage-order-fc08struct.log`. Full write-up:
`native-materialize-findings.md`, search "Poly-list order divergence localized one stage further".
