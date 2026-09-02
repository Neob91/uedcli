+++
priority = "p1"
kind = "debug"
summary = "freeclinic08's ENTIRE structural-only node/leaf residual ROOT-CAUSED and FIXED (CsgOper::Active, 528e602): Brush586's no-CsgOper= case is now handled. nsfhq04's Brush8321 (same mechanism) is also fixed, but nsfhq04 is STILL the worst-parity level in the corpus (0/6). Second divergence localized to Brush842 (5th continuation), then DISPROVEN as a Brush842-local bug (6th continuation, live gdb trace): Brush842's own classify-BSP descent is byte-exact vs the editor; the +131/+38 node/leaf delta is diffuse across 172 OTHER brushes, same open world-level-repartition-poly-order class as UNATCO's still-unresolved residual. No fix shipped, mechanism still open."
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

## 2026-09-01, 4th continuation: root cause found — it's the Vandenberg Gas `CsgOper`-absent-brush mechanism, not a diffuse repartition tie-break

Picked up the concrete next step named above: a live per-brush Pass-1 tree-shape trace to attribute
the `+70`-poly PREMERGE gap to specific brushes. Used a cheaper technique instead of new GDB
instrumentation: since Pass 1 is a pure sequential fold (brush *i*'s CSG add depends only on brushes
`1..i-1`, and the ONE world-level `bspRepartition` runs after ALL of them), truncating the
structural-only 141-brush list to its first *N* (in CSG order) and building BOTH sides (native
in-process, editor via a fresh `build_ued_golden.py` `MAP REBUILD`) reproduces the exact Pass-1 state
after *N* incremental adds. Binary-searching *N* by final node/surf/leaf count (no new disassembly)
localizes the first diverging brush directly.

**Binary search result (freeclinic08 structural-only order)**: prefix *n*=12 is byte-exact
(nodes=surfs=leaves match); *n*=13 (adds `Brush47`, a plain 6-poly axis-aligned `CSG_Subtract` box,
no flags/rotation) diverges by nodes=-12/leaves=-4 in this 13-brush minimal case. Per-brush
node-plane-owner attribution (`node.i_surf -> surf.i_actor`) on this minimal case found the missing
12 nodes were NOT attributed to Brush47 itself — they were spread across `Brush1`(-2)/`Brush4`(-2)/
`Brush7`(-2)/`Brush9`(-2)/`Brush10`(-4), all brushes ADDED BEFORE Brush47. This is the same
"downstream repartition reshuffling" shape every prior round hit — until the actual root cause
surfaced:

**`Brush586` — the level's very FIRST world-CSG brush (position 0 of 141, present in every prefix
tested including *n*=1) — has NO `CsgOper=` property at all.** `Engine.Brush.CsgOper`'s real class
default is `CSG_Active` (ordinal 0); native's `brush_marshal.py` currently defaults an absent
`CsgOper` to `CSG_Add` (`raw.get("CsgOper", "CSG_Add")`) — **exactly the mechanism
`vandenberg-gas-csg-active-csgoper-brush-causes` already found and left unfixed** ("the real editor
does something else entirely... roughly halves the resulting geometry of what follows it", live
A/B/C-verified there). That item's own scope claim — "`Brush230` is the ONLY non-Mover `Engine.Brush`
actor with no `CsgOper=` across every cached level trunk checked... `freeclinic08`, `nsfhq04`" — is
**factually wrong**: both this level's `Brush586` and `nsfhq04`'s `Brush8321` are also `CsgOper`-absent,
and both sit at world-CSG index 0, same as Vandenberg's `Brush230` — this looks like a recurring
OG-DX authoring pattern (a level's first-ever placed brush, before an explicit CSG op was chosen in
the original editor), not a one-off.

**Decisive live test — freeclinic08 (`fc08_n12_noactive_search.py`, `fc08_full_noactive.log`)**:
built the SAME brush set with `Brush586` removed, both native and live-editor.
- 12-brush set (`Brush1`..`Brush47`, the exact minimal case above, minus `Brush586`): native
  nodes=68/surfs=62/leaves=15, editor **nodes=68/surfs=62/leaves=15 — EXACT, d=+0/+0/+0**.
- Full 140-brush structural-only set (all of freeclinic08's structural brushes minus `Brush586`
  alone): native nodes=1135/surfs=658/leaves=284, editor **nodes=1135/surfs=658/leaves=284 — EXACT,
  d=+0/+0/+0**.

**`Brush586` alone fully explains freeclinic08's entire structural-only residual** (the WITH-`Brush586`
baseline was native=1141/editor=1179 nodes, native=290/editor=313 leaves — the -38/-23 this whole
thread has chased since round 1). The "diffuse, 75-of-141-brushes, tie-break-shaped" node-owner
spread every earlier round measured was a real symptom but the WRONG level of attribution: ONE
brush's mishandled `CsgOper` cascades its error through the entire incremental Pass-1 tree, and by
the time you look at FINAL node ownership it reads as scattered across dozens of unrelated brushes
(cancellation), obscuring the single upstream cause.

**nsfhq04 — same mechanism confirmed present and significant, but does NOT fully explain the
residual alone** (`nsfhq04_noactive.log`). `Brush8321` (world-CSG index 0, same no-`CsgOper=`
pattern) removed from the full 660-brush structural-only set: native nodes=4958/surfs=2170/
leaves=1484 vs editor **nodes=4721/surfs=2170/leaves=1438 — d_nodes=+237/d_leaves=+46**, i.e. WORSE
than the WITH-`Brush8321` baseline (native=4975/editor=4958, d_nodes=+17/d_leaves=-26). Removing the
brush makes native's own count barely move (4975→4958, -17) while the REAL editor's count moves by
237 (4958→4721) — the real `CsgOper=CSG_Active` brush has a LARGE true effect on this level that
native's current (wrong) `CSG_Add`-substitute barely reproduces in either direction; the closer WITH-
`Brush8321` match was accidental error cancellation, not correctness. Surfs stay exact either way
(2170=2170 both configurations) — consistent with the surf axis being independent (Pass-2/semisolid
concern, already root-caused as `Brush531`'s `PF_Semisolid` misclassification, see "The +1 surf,
precisely" above).

**No fix shipped** — same standing reason as `vandenberg-gas-csg-active-csgoper-brush-causes`: the
Rust core has no representation for `CsgOper::Active` at all, and the real mechanism (what the editor
actually does with a `CsgOper`-absent brush) is unknown without disassembly, not attempted this
round. This round's contribution is confirming the mechanism is NOT a Vandenberg-only curiosity —
it fully explains one level's entire structural residual and is a major (if not sole) driver of a
second, and the "first brush has no stated `CsgOper`" pattern likely recurs across the wider OG-DX
corpus (unmeasured beyond these 3 levels). See `native-materialize-findings.md`, search "Vandenberg
Gas mechanism confirmed on freeclinic08/nsfhq04" for the full write-up and the cross-reference into
the Vandenberg item.

## 2026-09-01, 6th continuation: `Brush842`'s own classify-BSP descent proven byte-exact
(live gdb trace); NSFHQ04's residual is diffuse, at the one-time world-level repartition — same
class as UNATCO's still-open problem, not a new bug

Fresh worktree, fresh build, reproduced the 5th continuation's `Brush842` divergence exactly
(n=512 exact, n=513 `d_nodes=+131 d_surfs=+0 d_leaves=+38`). Two results:

1. **Epsilon-margin probe (all 6 authored polys, no prior per-poly attribution needed): RULES OUT
   the epsilon-flip hypothesis.** Closest margin to the `±0.25` split threshold is 0.169890 (poly 0,
   the near-degenerate one) — not a plausible float-precision coincidence.
2. **Live gdb trace of the real editor's `AddBrushToWorldFunc` calls for `Brush842`'s own
   incremental CSG-add, cross-checked against a final-tree node-owner attribution: `Brush842` itself
   is byte-exact.** Editor: 19 calls, 12 kept/7 discarded. Native's own `LEAF` trace: 19 total, 12
   `add=true`/7 `add=false` — an exact match. Final-tree attribution: native=8/editor=8 nodes,
   native=5/editor=5 surfs owned by `Brush842`. The `+131`/`+38` delta is diffuse across 172/513
   OTHER brushes (net +131, abs-sum 637 — heavy cancellation), not concentrated at `Brush842` at all.

**The 5th continuation's whole framing ("`Brush842`'s near-degenerate poly triggers a classify-BSP
over-fragmentation") is disproven**, not just its epsilon-flip sub-case — two independent live
measurements agree `Brush842`'s own CSG-add is exact. The real mechanism: `Brush842`'s mere
inclusion changes the polygon pool the one-time world-level `bspBuildFPolys`→`bspMergeCoplanars`→
`bspBuild` repartition consumes, and that step's output shifts diffusely across many already-settled
brushes — the same symptom signature (surf-exact, node/leaf-only delta, diffuse cross-brush
attribution) as UNATCO's still-open residual and freeclinic08's pre-`Brush586`-fix diffuse residual.
Very likely the same open problem recurring a third time, not confirmed identical (needs a
world-level poly-order live capture, not run this round). No fix shipped — no logic bug found;
the actual mechanism is the already-known-open world-level poly-order class. Also found and flagged
a methodology issue for the parallel Area51 thread: its `NADD`-tail-based fragment counts are not
actor-scoped and may be inflated by the same world-level repartition's own node-seeding (measured
3.5x inflation here: 42 raw vs 12 properly-scoped). Full write-up:
`native-materialize-findings.md`, search "NSFHQ04 6th continuation".

**Methodology note, important for other concurrent investigations this session**: this round found
and fixed a real contamination bug in its own harness — `sys.path.insert(0, "/workspace/uedcli")`
(the shared main checkout) resolves `uedcli`/`brush_marshal.py` from whatever a CONCURRENT agent has
uncommitted there, not this investigation's isolated worktree. Silently nondeterministic: a `BuildError:
unknown CsgOper 0` appeared and disappeared across otherwise-identical reruns because the main
checkout's `brush_marshal.py` was being actively edited (by a different session's own Vandenberg
work) between runs. Fixed by pointing every `sys.path` entry at the worktree instead
(`prefix_search_lib.py`'s header comment has the detail). Any script built during this session that
imported from a bare `/workspace/uedcli` path rather than its own worktree should be treated as
suspect.

## Harness (this round)

Committed under `dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness/`: `prefix_search_lib.py`
(the shared prefix-binary-search library — native in-process build + live-editor `build_ued_golden.py`
build, per-*N* compare), `fc08_prefix_search.py`/`nsfhq04_prefix_search.py` (level-specific CLIs over
the library), `nsfhq04_filter_trunk.py` (structural-only trunk extractor, `smuggler_filter_trunk.py`'s
pattern), `fc08_n13_node_owner.py` (per-brush node-owner attribution on the 13-brush minimal case),
`fc08_n12_noactive_search.py` (the decisive Brush586-removal test). Logs under
`dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/logs/`.

## Not fixed / still open

- The real `CsgOper=CSG_Active` mechanism (shared blocker with `vandenberg-gas-csg-active-csgoper-
  brush-causes`) — needs disassembly, not attempted.
- nsfhq04's residual beyond `Brush8321`'s contribution is unmeasured (the no-Brush8321 test shows the
  mechanism is significant but not sufficient; whether the REMAINDER is the diffuse tie-break class or
  something else is unknown).
- The full (non-structural-only, 305/992-brush) level residuals were not re-tested with the offending
  brush removed this round — only the structural-only isolates. The Pass-2 semisolid brushes'
  interaction with a wrongly-modeled Pass-1 world shell is unmeasured.
- Whether other OG-DX levels share a `CsgOper`-absent first brush is unmeasured beyond these 3
  (Vandenberg Gas, freeclinic08, nsfhq04) out of the 21-level corpus.

## 2026-09-01, 5th continuation: `CsgOper::Active` (528e602) shipped, closes freeclinic08 fully; nsfhq04 has a SECOND, distinct divergence at `Brush842`

`528e602` shipped since the 4th continuation, fixing the `CsgOper`-absent mechanism this item
originally root-caused. freeclinic08 is now confirmed count-exact on nodes/surfs/leaves (side effect,
independently re-verified — see `native-materialize-findings.md`, "confirm CsgOper::Active fix already
closes FreeClinic08's structural residual").

nsfhq04 is NOT closed — it remains the single worst-parity level in the 2026-09-01 regenerated breadth
table (0/6 geometry). Re-ran the round-2 harness (`nsfhq04_prefix_search2.py`, already built for this
exact follow-up) to completion: with `Brush8321` correctly handled by `CsgOper::Active` (not removed),
the FIRST divergent brush in the level is `Brush842` (world-CSG index 513 of 660, structural-only set)
— `d_nodes=+131 d_surfs=+0 d_leaves=+38` at that prefix. `Brush842` carries a near-non-planar authored
poly (tiny normal/vertex deviations from axis-alignment despite an algebraically-trivial 180°-flip
rotation) — a plausible trigger for a coplanar/split-epsilon classification difference during the
classify-BSP descent, the SAME symptom shape (node/leaf-only delta, surf-exact) the parallel Area51
Entrance `Brush1852` investigation converged on this same round. Not proven the same root cause; not
disassembly-confirmed. No fix shipped. Full detail: `native-materialize-findings.md`, search "NSFHQ04
5th continuation".

## 2026-09-01, 6th continuation: full FilterEdPoly/FilterLeaf decompile -- port confirmed exact;
## corroborates this thread's own "poly-list ORDER, not scoring" finding from the other direction

Dispatched to fully decompile and read the real editor's classify-BSP function (`FilterEdPoly`/
`FilterLeaf`), not just locate it, to understand the mechanism behind both this level's `Brush842`
and the parallel Area51 `Brush1852` residual. Full detail: `native-materialize-findings.md`, search
"coplanar iPlane node-chain is NEVER read". Result: checked every branch of both functions
(vertex-overflow pre-split, Front/Back recursion order, the `Split` case's front-before-back order,
the out-of-place-coplanar path, the coplanar facing-test, `FilterLeaf`'s 3-way dispatch) against
`bspcsg.rs` -- no divergence found. New fact: neither function reads a node's `iPlane`
(coplanar-sibling chain) field during classify -- that chain is walked only at brush/node INSERT time
(`bsp_add_node`), never during the filter descent, on either side. This rules out "the classify
function itself picks a different coplanar-chain member" as a mechanism and points at tree SHAPE
(insertion order/linkage) instead -- the SAME conclusion this thread's own "poly-list ORDER, not
scoring" continuation (above) already reached independently for freeclinic08/nsfhq04's Pass-1 world
tree. Two independent methods (live gdb capture here, static decompile there) now agree the bug class
is upstream tree-build order, not the classify function. Does not by itself explain `Brush842`
specifically (its near-non-planar poly is still unexplained). No fix shipped. Harness + saved
pseudo-C: `dev/docs/spikes/2026-09-01-filteredpoly-full-decompile/harness/`.

## Independent full-pipeline decompile pass (2026-09-02) — NSFHQ04 node residual NOT moved by the one divergence found

A second, independent pass `angr`-decompiled the ENTIRE CSG/BSP build chain and confirmed every
function faithful to `bspcsg.rs` except the node vertex-RING pooling threshold: the editor welds ring
vertices at 0.015 (NEAR, `bspAddPoint arg_2=0`), native pooled at 0.002. Full detail:
`native-materialize-findings.md`, search "INDEPENDENT PASS — full-breadth decompile".

Measured (gated `UEDCLI_BSPCSG_RING_NEAR`): NSFHQ04's full-level node delta is UNCHANGED (-92 → -92),
as are 747 (+68) and OceanLab (+465). Only scaled-brush Vandenberg moved (+32→-6). NSFHQ04 (like
Area51) is a rotated-brush case whose ring vertices land at exact rotated positions, outside the
0.002–0.015 gap — so the ring threshold is not its lever. The world-repartition node-over-build
remains open. Also confirmed: the earlier freeclinic08 "PREMERGE 1333 vs 1263" divergence is the
already-fixed `CsgOper::Active` case; nothing new there. NOT shipped (gated off, `cargo test` 102/102).

## 2026-09-02: `bsp_add_node`'s own insertion logic fully decompiled and checked — closed off as a candidate; a real but INERT gap found and fixed

Continuation of the "poly-list ORDER, not scoring" thread: with `FilterEdPoly`/`FilterLeaf` (the
classify descent) already confirmed exact and confirmed blind to the `iPlane` chain during classify,
the remaining unchecked piece was `bsp_add_node` itself — the function that DOES walk that chain, at
insert time. Full `angr` decompile of the real `bspAddNode` (`Editor.dll 0x10034e80`, ~10.8 KB
pseudo-C, cross-checked against raw `capstone` disassembly for every non-obvious line) against
`bspcsg.rs::bsp_add_node`: the `NODE_PLANE` tail-walk order, the surf alloc/reuse gate, the
`>16`-vertex split-in-half, and the Front/Back/Plane parent-linkage + zone/leaf-inheritance formulas
(independently re-deriving the existing 2026-08-27 disassembly finding via a different method) ALL
match, with zero observable-effect differences. `bsp_add_node` is now closed off as a candidate
mechanism, the same way the FilterEdPoly/FilterLeaf decompile closed off the classify descent.

One real divergence WAS found and disassembly-confirmed twice (pseudo-C + raw capstone): a post-loop
"wrap trim" — the real editor drops a ring's redundant closing vertex if it duplicates its first
vertex (after the existing consecutive-only dedup), plus a degenerate-<3-vertex guard — that
`bsp_add_node` didn't implement. FIXED, pinned by 2 new unit tests. But measured, via the offline
`/tmp/uedcli-parity-cache` oracle (`parity_report.py`, no live editor needed, clean A/B with a
temporary env-gated toggle), to have **ZERO effect** on nsfhq04 specifically (native/golden nodes
7564/7656 `d=-92`, surfs 3831/3830 `d=+1`, leaves 1492/1518 `d=-26` — byte-identical fix on vs off) and
on freeclinic08 (already node/surf/leaf-exact post-`CsgOper::Active`; verts/points residual `d=+1`/
`d=+20` also unchanged by this fix) and 4 other levels. Shipped anyway as a faithful-port correctness
fix (zero regression, 104/104 cargo tests), NOT as an explanation for `Brush842`'s residual, which
remains diffuse and unexplained. Full detail: `native-materialize-findings.md`, search "Full
`bspAddNode` decompile".

**Narrows the remaining surface**: both ends of the pipeline `bsp_add_node` sits between — its own
insertion/linkage logic, and `FilterEdPoly`/`FilterLeaf`'s classify descent — are now fully decompiled
and checked exact. The unexamined piece is `bsp_brush_csg`'s own `AddFunc`/`leaf_func` dispatch (which
decides WHETHER/WHEN to call `bspAddNode` at all, per brush) and the world-brush processing/poly-soup
order feeding it — not yet decompiled or live-traced at this level of detail. A live per-brush Pass-1
tree-shape trace (`prepart_tree_*`, not yet run at world level for nsfhq04) remains the most direct way
to attribute the divergence to `Brush842` or a specific decision.

## Rotated-brush transform-precision hypothesis: RULED OUT for `Brush842` specifically (2026-09-02)

Dispatched to check whether `FPoly::Transform`'s exact vertex/normal floats explain the residual
(the CSG/BSP pipeline itself is already closed off above). `Brush842`'s own classify-BSP descent was
already live-gdb-proven byte-exact (6th continuation, above) — unrelated to transform precision — and
its rotation is a cardinal 180°-flip, same signed-permutation-matrix argument as Area51's `Brush1852`
(see that item's own addendum). Full writeup, including a genuine but content-thin gap found
elsewhere (Vandenberg Gas, not this level): `native-materialize-findings.md`, search "Rotated-brush
Transform math"; new board item `rotation-py-3-axis-non-cardinal-fcoords-compose`. `bsp_brush_csg`'s
poly-soup order remains the live lead for this item.

## World-brush processing ORDER: confirmed faithful — closes off one half of the last-named open lead (2026-09-02)

Picked up the "world-brush processing/poly-soup order feeding it — not yet decompiled or live-traced"
lead named above (task was UNATCO-scoped, this item is the cross-reference target for that thread).
Read the already-committed `csgRebuild.decompiled.c`
(`dev/docs/spikes/2026-09-02-csg-pipeline-breadth-decompile/harness/`) at the loop-structure level: the
structural- and detail-brush apply loops are each a plain ascending `Level->Actors[]` array-index walk
(no sort, no secondary key), matching `bspcsg.rs::build_geometry_bspcsg`'s own `brushes.iter().enumerate()`
+ `materialize.py`'s `for name in level.order:` exactly, including the structural-then-detail two-pass
split. Also checked the per-brush `bspRefresh` cadence question: the NODE-tree-shape-relevant half
(`bspCleanup`, `Editor.dll 0x35de1`) already runs unconditionally per-brush on native's side
(`bsp_cleanup`, not gated); the gated `UEDCLI_BSPCSG_INCREMENTAL_POINTS` experiment is a separate
verts/points-pool concern per its own doc comment, not node/leaf tree shape. **Both close clean — no
divergence found, no fix shipped.** Full writeup: `native-materialize-findings.md`, search "World-brush
processing ORDER and per-brush `bspRefresh` cadence".

Narrows `bsp_brush_csg`'s remaining unexamined surface to its own per-brush classify-BSP descent/insert
cycle on a specific not-yet-identified brush — the `prepart_tree_*` live trace this item has named twice
now remains the most direct next step, for UNATCO specifically (never run to completion there this
session; freeclinic08/Area51/NSFHQ04 all have theirs).
