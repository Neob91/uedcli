+++
priority = "p1"
kind = "implement"
summary = "SHIPPED 2026-08-29 (repartition_frontier + compact_unreachable_nodes, bspcsg.rs), but with a REGRESSION on UNATCO's lighting -- see 'lighting regressed' below. UNATCO node gap (6321 vs 6314, unmerged baseline) root-caused: repartition_frontier's make_ed_polys reconstructs unmerged coplanar duplicates that bsp_merge_coplanars correctly fixes per-call (10/10 live-verified exact against the real editor) -- but blanket-applying the merge to all 209 calls reproduces a 5689-node UNDER-build (-625), not a fix. 2026-08-30: SIX architectural hypotheses refuted with real evidence. Later the same day: disassembly first suggested a separate scratch UModel holds subtree nodes -- REFUTED by direct live evidence (bspAddNode's own Model argument matches the persistent model 0/29 times mismatched; a Nodes.Num watchpoint shows real growth then a genuine FArray::Remove shrink back to baseline, every call, even for a known +1-delta subtree; that subtree's own root node bytes are unchanged before/after). Corrected mechanism: subtree calls write real nodes past the persistent model's own Nodes.Num as scratch, then bspRefresh removes them -- but where a delta actually becomes permanent is still not pinned down (checked: net Num growth -- no; root node content change -- no). See dev/docs/native-materialize-findings.md for the full write-up. Wanchai stays node-exact throughout (unaffected). No bspcsg.rs changes shipped this round -- default path unchanged (6321/11648)."
+++

# UNATCO `Verts`/`Points` residual — it is the unported sub-BSP repartition loop

Short, checkable, cross-cutting facts from this investigation are logged in
`dev/docs/native-materialize-findings.md` (check it before re-deriving something already known;
follow its check/recheck process before changing an entry).

Follow-up to `csgrebuild-runs-testvisibility-between-the`, which put native's UNATCO node tree exactly
on the editor golden (6314/6314). `Verts` and `Points` are what is still open, and both are now
stage-localized against live editor counts
(`harness/editor-tree-oracle/logs/repart-stage-unatco.log` and `brushcsg-calls-unatco.log`) versus
native's `UEDCLI_BSPCSG_STAGE_COUNTS`:

| point in the pipeline | native nodes | editor nodes | native verts | editor verts | native points | editor points |
|---|---:|---:|---:|---:|---:|---:|
| post-repartition | 2953 | 2953 | 11794 | 11794 | 5249 | 5607 |
| post-`TestVisibility` (first detail brush) | 2984 | 2984 | 31035 | 31024 | 5280 | 5638 |
| after the detail loop | 6314 | 6314 | 44325 | 44314 | 10810 | 11445 |
| after the ~209 sub-BSP repartitions | — (not ported) | 6314 | — | **54776** | — | 12909 |
| final (post-`bspOptGeom`) | 6314 | 6314 | 66037 | 76488 | 10758 | 10752 |

## `bspOptGeom`'s T-junction weld is already exact

Editor: `76488 − 54776 = 21712`. Native: `66037 − 44325 = 21712`. Identical. **Do not go looking for
a weld bug** — an earlier draft of this item said the weld was ~10.5k short, from reading the
post-detail-loop count as `bspOptGeom`'s input. It is not: `csgRebuild` runs its sub-BSP
repartitions in between.

The subtraction assumes `bspOptGeom`'s prologue `bspRefresh` does not compact `Verts` before pass 1
runs; no count is captured at `bspOptGeom` entry to prove that directly. Corroborating but not exact:
an earlier editor capture of pass 1's insertions (`logs/bspopt-insert-unatco.log`) holds 3599 `INS`
records whose `NumVertices+1` appended slots sum to 22064 — within 1.6% of 21712, from a different
session, so treat it as support for the order of magnitude rather than a second measurement of the
same run.

## What is actually missing

`csgRebuild` (`Editor.dll 0x4a650`) runs TWO loops of `bspRepartition(Model, iChild, 2)` after the
detail-brush loop and before `bspOptGeom` — `0x1004aa3f` over collected nodes' `iFront` and
`0x1004aa90` over their `iBack` **[DISASM]**. On UNATCO that is 209 calls
(`repart-stage-unatco.log` holds 210 `bspRepartition` groups for one `MAP REBUILD`: the world
repartition, then these 209). Their net effect **[LIVE]**:

- nodes 6314 → 6314 (each call's `bspBuild` bumps the count and its `bspRefresh` brings it back),
- verts 44314 → 54776 (+10462),
- points 11445 → 12909,
- surfs 3703 → 6059 (a later `bspRefresh` compacts them back to the shipped 3616).

Native has no counterpart to this pass at all. It is the whole of the remaining `Verts` gap.

## Second, much smaller thread: the Points pool

The pool runs 358 short from the repartition onward (5249 vs 5607) while nodes and verts at that same
point are exact, so it is purely the pool, not the geometry. Native clears `model.points` before
rebuilding it in `bsp_build`; the editor's `bspBuild` calls `EmptyModel(0,0)`, which may retain
entries. The two converge by the end anyway (10758 vs 10752), so this costs 6 points in the shipped
map.

Prior state for reference: before the zone-pass reorder, native's final `Verts` were 95049 against
the same 76488 golden, i.e. the error was `+18561` and is now `−10451`.

## 2026-08-29: mechanism INDEPENDENTLY re-confirmed (owner ruling's "not portable" concern addressed
## for the mechanism identity; the exact fix is still not scoped)

The owner's 2026-08-28 ruling (`owner-ruling-all-native-decode-spike-findings`) named this item's
`sub_49380`/`bspRepartition` mechanism as diagnosed only from the invalidated pre-2026-08-14
disassembly. Re-verified TODAY from scratch, independent of the old write-up:

- Fresh `UEDCLI_BSPCSG_STAGE_COUNTS` run on the current tree reproduces the table above EXACTLY
  (post-repartition 2953/11794/5249, post-testvisibility 2984/31035/5280, post-detail-loop
  6314/44325/10810, final 6314/66037/10758) — the MEASUREMENTS were never in question and still
  hold on today's tree.
- Fresh disassembly of `Editor.dll 0x1004a650` (`csgRebuild`) confirms `0x1004aa3f` and `0x1004aa90`
  both `call [eax+0x1ec]` — the SAME vtable slot the current, already-trusted (post-2026-08-25)
  `bspcsg.rs` comment cites for `bspRepartition` at `0x1004a89a`. So the FUNCTION IDENTITY (two more
  `bspRepartition` calls after the detail loop) is now independently re-derived, not just re-quoted
  from the invalidated spike.
- **Fully decoded the two loops' mechanics** (`0x1004aa01`-`0x1004aaa1`): two separate `TArray<int>`
  node-index lists (stack locals at `ebp-0x64` and `ebp-0x58` — NOT the same list read two ways).
  For each `i` in list 1: `n = list1[i]`, `if Nodes[n].iFront != -1: bspRepartition(Model,
  Nodes[n].iFront, 2)`. List 2 is identical but reads `Nodes[n].iBack` (offset `+0x20` vs `+0x24` —
  matches the pinned `FBspNode` struct). `sub_49380` (called earlier, right after `TestVisibility`
  and BEFORE the detail-brush loop — a different position than assumed) is NOT this mechanism;
  its role is still unclear and it predates the gap this item is about.

**Resolved — the collector is `sub_49380` (`Editor.dll 0x10049380`), fully decoded 2026-08-29.**
Called ONCE, right after `TestVisibility`/zone pass and BEFORE the detail-brush loop (not inside
it — that assumption above was wrong). It's a recursive tree walk, `sub_49380(Model, List1, List2,
nodeIndex)`: for the given node, if `Nodes[n].iFront == -1` (`+0x24`), `TArray::AddItem(List1, &n)`
(`Editor.dll 0x100123e0`); else recurse into `Nodes[n].iFront`. Same for `iBack` (`+0x20`) / List2.
Called on the tree root, so it walks the WHOLE tree and collects, into List1, every node that is
CURRENTLY a front-side leaf (no front child yet), and into List2, every current back-side leaf.

**The full mechanism, now completely understood:**
1. Before the detail-brush loop: `sub_49380` snapshots the tree's current "frontier" — every node
   with an empty front slot into List1, every node with an empty back slot into List2.
2. The detail-brush loop runs (CSGs semisolid/detail brushes into the tree) — this can attach NEW
   subtrees onto any of those previously-empty slots.
3. After the detail loop: for each `n` in List1, if `Nodes[n].iFront` is NOW `!= -1` (a subtree grew
   there since the snapshot), `bspRepartition(Model, Nodes[n].iFront, 2)` — re-balance JUST that new
   subtree in place. Same for List2/`iBack`. This is why it's ~209 calls on UNATCO: one per leaf slot
   that gained a subtree during the detail pass, not one per detail brush.

**Why this isn't a quick port:** native's own "repartition" (the `post-repartition` stage) is a
FULL-TREE rebuild — `model.nodes.clear()` + `bsp_build(&mut model, merged_soup)` from scratch
(`bspcsg.rs` ~2585-2596) — there is no existing "repartition just this subtree in place" capability.
A faithful port needs: (a) collect the polygon soup for a subtree (`bsp_node_to_fpoly`,
`bspcsg.rs:871`, already reconstructs one node's poly — walking a whole subtree with it is new),
(b) run the split/build on that soup in an ISOLATED node range so it doesn't touch the parent tree's
existing indices, (c) graft the result back: append the new nodes to the model's node array
(index-rebased) and rewrite the parent's `iFront`/`iBack` to point at the new subtree root, sharing
the model's existing Points/Vectors/Verts pools rather than rebuilding them. This is real tree
surgery, not a small patch — attempted carefully in a dedicated pass, with UNATCO+Wanchai's current
exact node/surf counts as a hard regression gate (both are easy to break with a half-right graft).

## First implementation attempt 2026-08-29: reverted, did not work

Tried the graft using EXISTING primitives that turned out to already support it structurally:
`bsp_add_node` already accepts an arbitrary parent + `NODE_FRONT`/`NODE_BACK` place (not just
root), appending to the model's existing pools — no new low-level machinery needed. Wired: (1)
`collect_repartition_frontier` (port of `sub_49380`, recursing `i_back`/`i_front` only, no
`i_plane` — matches the disassembly), called right after the post-zone-pass `swap_node_children`,
before the detail loop; (2) `repartition_frontier`, called after the detail loop, reusing the
already-existing `make_ed_polys` (turns out to be exactly the subtree-poly-collector needed) +
`split_poly_list` to rebuild each grown subtree onto its original parent slot; (3)
`passes::bsp_refresh` after, to compact orphaned pre-repartition nodes (matches "each call's
bspBuild bumps the count and bspRefresh brings it back").

**Result: wrong, in the wrong direction.** UNATCO post-repartition-frontier: nodes 6314→9539
(target: stay ~6314), verts 44325→38084 (target: grow toward 54776 — it SHRANK instead). Also
broke an existing unit test (`a_semisolid_detail_brush_reaches_the_world`: expected 12 faces, got
18). Reverted (`bspcsg.rs` back to the pre-attempt commit) rather than debug further this session.

## Second attempt 2026-08-29: SHIPPED — root cause was a missing node-array GC, not the collector

Added a diagnostic-only build (collector wired, no mutation) to check `collect_repartition_frontier`
against the expected count BEFORE touching anything: `total_grown=209` on UNATCO, matching the
editor's own citation EXACTLY. The collector was correct all along — the bug was entirely in the
graft step. Root cause: `bsp_add_node` always APPENDS, never reuses a freed slot, so grafting a new
subtree onto an existing parent leaves the OLD subtree's nodes as permanent orphans — and
`passes::bsp_refresh` does NOT collect them (its own doc comment: it only compacts surfs/verts, not
nodes). That's the entire "node count blew up, verts shrank" failure from the first attempt: real
new nodes were being added, but sitting alongside thousands of unreachable orphans, and
`bsp_node_to_fpoly`/`make_ed_polys` on a corrupted tree pulled in less real geometry than before, not
more.

Fix: added `compact_unreachable_nodes` — a proper mark-and-sweep from root 0 over
`i_front`/`i_back`/`i_plane`, remapping every surviving node's links — run once after
`repartition_frontier`. Result:

| | UNATCO before | UNATCO after | Wanchai before | Wanchai after |
|---|---:|---:|---:|---:|
| nodes (target 6314 / 11648) | 6314 | 6321 | 11648 | 11648 |
| verts pre-weld (target ~54776 / n/a) | 44325 | 57201 | 110992 | 113118 |
| verts final (target 76488 / 169313) | 66037 | 78931 | 167325 | 169451 |
| points final (target 10752 / 16791) | 10758 | 10766 | 16807 | 16807 |

Wanchai's verts error dropped from −1988 (−1.2%) to +138 (+0.08%) — a ~14x improvement, nodes stay
exactly 11648 (editor-exact) before and after. UNATCO's nodes go from exact (6314) to 6321 (+7,
0.1% off) and verts from −10451 (native had never had this pass) to +2443 over (+3.2%) — much
closer than the prior "doesn't exist at all" gap, though not yet exact. `a_semisolid_detail_brush_
reaches_the_world` now passes (was the first attempt's casualty). Full `bin/test` green (84/84
Rust, only the pre-existing unrelated pytest failures).

**Caveat — makes 4 OTHER already-inexact levels' Verts worse, not better**
(`geometry-re-check-on-4-more-og-levels-0-4-exact`): smuggler/paris-chateau/training-final/
hk-helibase all had a DIFFERENT, still-unexplained node-count over-build even before this fix.
`repartition_frontier` reconstructs polygons FROM the current tree (`make_ed_polys`), so on a tree
that's already wrong for an unrelated reason, it compounds the error rather than correcting it —
their verts flip from under-built to over-built (e.g. smuggler −9624→+10615) and node over-build
roughly doubles on some. None of the 4 were geometry-exact before OR after, so nothing that worked
regresses — but it means this fix alone does not make those 4 exact, and the other over-build cause
needs its own investigation before it will.

## CORRECTION 2026-08-29, same day: UNATCO's node count is no longer exact, and lighting regressed

The "shipped anyway" line above was wrong to call this unqualified good news on UNATCO. Full
`level materialize` + `lightparity.py` against the UNATCO lit golden, AFTER this fix:

| | before this fix | after this fix |
|---|---:|---:|
| UNATCO nodes | 6314 (exact) | 6321 (+7, NOT exact) |
| UNATCO LightMap records byte-identical | 2628/3345 (78.6%) | 1627/3345 (48.6%) |
| Wanchai nodes | 11648 (exact) | 11648 (exact, unchanged) |
| Wanchai LightMap records byte-identical | 3228/4530 (71.3%) | 3228/4530 (71.3%, unchanged) |

Losing UNATCO's node-exactness breaks `LightMap` record ALIGNMENT (record `k` on each side no
longer describes the same surface — the same reason Wanchai needed the `5b0a022` fix before its
lighting could be compared meaningfully at all), so `lightparity.py`'s per-record comparison is
now comparing largely unrelated surfaces. **This is a real regression on the metric that actually
gates the parity goal (byte-identical output), not just a cosmetic Verts-count miss.**

Wanchai is unaffected and a clean win end to end (nodes exact throughout, Verts 14x closer,
lighting numbers literally unchanged) — the regression is UNATCO-specific: ~7 of its 209
repartition-frontier calls net one extra node each (202/209 are net-zero, matching the "bspBuild
bumps then bspRefresh brings back" citation; a handful aren't). Kept shipped rather than reverted
because Wanchai's result is unambiguously good and the mechanism is structurally verified correct
(the 209/209 frontier-collector match, the disassembly-decoded algorithm) — but UNATCO's +7-node
gap needs closing before this can be called done, and any NEW level added to the comparison corpus
should be checked for the same node-exactness-vs-lighting-alignment interaction before trusting a
Verts-only comparison as sufficient.

**Next step:** identify which ~7 of the 209 `repart_frontier_a`/`repart_frontier_b` entries add a
net node (compare `make_ed_polys`'s pre-repartition subtree node count against what
`split_poly_list` produces for that same subtree) rather than treating this as solved.

## Pinned exactly 2026-08-29, same day: it's 3 calls, not ~7 scattered ones

Added `UEDCLI_REPART_CALL_DIAG` (env-gated, committed `d9d69f3`) to log any call whose appended
node count differs from its original poly count. On UNATCO, exactly 3 of 209 calls are non-zero,
summing to the full +7:

| parent | place | child | orig polys | appended nodes | delta |
|---:|---:|---:|---:|---:|---:|
| 1917 | NODE_FRONT | 4096 | 85 | 89 | +4 |
| 1892 | NODE_FRONT | 3086 | 141 | 143 | +2 |
| 689 | NODE_FRONT | 6108 | 40 | 41 | +1 |

All three are `list_b` entries (native `i_front` = editor's iBack). The other 206 calls are exactly
net-zero, matching "bspBuild bumps the count and bspRefresh brings it back." This is NOT a
fundamental flaw in the mechanism — it's 3 specific `find_best_split_exact` tie-break/heuristic
choices differing from what the live editor's exact run picks for these 3 particular poly soups
(85/141/40 faces), the same category of residual as other split-heuristic edge cases elsewhere in
this codebase, not evidence the whole approach is wrong. Reproduce:
`UEDCLI_REPART_CALL_DIAG=1 UEDCLI_BSPCSG_STAGE_COUNTS=1 <build UNATCO>`.

**This is the actual blocker for UNATCO's node-exactness** (and therefore its lighting
comparability — see the CORRECTION section above).

## Root split checked, not it — divergence is deeper in the recursion (2026-08-29)

Added `UEDCLI_REPART_FBS_CHILD` (env-gated, `7496253`) to dump `find_best_split_trace`'s candidate
table for one repartition call's TOP-LEVEL split. Checked the smallest case (child=6108, 40 polys,
delta +1): winner is slot 12 at score 60, next-best is slot 32 at score 108 — not a near-tie, a
clean, unambiguous win by a wide margin. So the root split is NOT where native and the editor
diverge; the +1 extra node happens somewhere in the RECURSIVE sub-splits of the resulting front/back
halves (front=7, back=12 polys from the winning split), which the current trace tool doesn't reach
(it only traces one level, by design — "kept separate so the traced path never touches the hot
loop").

**Real next step needs a live differential, not more static tracing:** without an independent
capture of what the EDITOR'S `bspRepartition(Model, 6108-equivalent-node, 2)` actually produced for
this exact 40-poly subtree, there's no ground truth to diff native's recursive choices against —
same category of work as the Area51 N=5→N=6 trace (`native-under-builds-area51-entrance-geometry`).
Candidate approach: instrument the editor to dump its own `FindBestSplit` winner at each recursion
level for one `MAP REBUILD`, or — cheaper — bisect by re-running native with `UEDCLI_REPART_FBS_CHILD`
pointed at intermediate node indices once the recursive front/back children are known (recurse the
diff manually: split polys via slot 12's plane, dump each half's own trace, and keep descending
until node COUNTS between the two halves stop matching editor per-half node counts from a captured
tree — needs `a51`-style incremental capture infrastructure adapted for this soup instead of brush
prefixes).

**Checked whether an Area51-style minimal repro applies here — it doesn't, directly.**
`UEDCLI_REPART_FBS_CHILD` now also prints the subtree's source brush actors (`ff735ed`): child=6108's
40 polys trace back to 6 brushes (`Brush140`, `Brush148`, `Brush1158`, `Brush1550`, `Brush1551`,
`Brush132`). Unlike Area51 (where a prefix of N brushes in CSG order directly reproduces an
under-build native and the editor both hit), this subtree is a DEEPLY DERIVED intermediate state —
what's left after the world repartition, `TestVisibility`/zone pass, and the full detail-brush loop
have all run — so replaying just these 6 brushes in isolation would NOT reproduce the same 40-poly
soup; the surrounding tree shape these faces survived into depends on the other ~728 brushes too.
A live differential here needs the ACTUAL editor mid-build state at this exact point, not a
brush-subset repro.

**Confirms it's a pure tree-shape difference, not a lost face:** per-brush surf counts for all 6 of
child=6108's contributing brushes match the editor EXACTLY (6/6/6/6/6/4), and total surfs match
exactly (3616=3616) — the face SET is completely right; only how the ~209 repartitions carve that
set into nodes differs.

**Tried, reverted: `bsp_merge_coplanars` before re-splitting each subtree.** The world-level
repartition calls it on its poly soup before its own `bsp_build` (`bspcsg.rs:2660`);
`repartition_frontier` never did the equivalent for its reconstructed subtree polys, so tried
adding it. Mixed and net negative: UNATCO pre-weld verts got almost exact (54781 vs target 54776,
was +2425) and final verts much closer (76696 vs 76488, was +2443) — but nodes overshot the OTHER
way, badly (5689 vs target 6314, was 6321) — the merge is too aggressive applied per-subtree.
Worse, it broke Wanchai's previously node-EXACT match (11648 → 11628) while only marginally
helping its verts/points. Reverted; the shipped (no per-subtree merge) state stays better balanced
overall since it doesn't regress Wanchai's clean win. Whatever the real mechanism is, it's not a
blanket "always merge coplanars before re-splitting" — more likely the editor's actual
`bspRepartition` merges more selectively (e.g. only within-brush, or only truly co-planar AND
touching fragments, not the full cross-poly `bspMergeCoplanars` sweep this codebase's version
does) — another point supporting that this needs a live differential, not more parameter guessing.

## Live GDB capture of `child=6108` (2026-08-29 PM): root cause found — a poly-COUNT gap, not order

Static disassembly and parameter tuning (`Opt::Lame`, blanket `bsp_merge_coplanars`) were exhausted
without closing this. Built a live differential (`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/`,
gdb attached to the Wine-hosted `UED22` process, `Editor.dll` breakpoints on `bspRepartition`
(`0x10049fc0`), `bspAddNode` (`0x10034e80`), and `FindBestSplit`'s return (`0x100338ee`), gated to
fire only during this one subtree's own repartition call) against a full `MAP LOAD` +
`MAP REBUILD` of `_scratch/bsp-parity-proj/golden_unatco_control.dx` under `dx-lum-uned-dbg`. Note:
both `ued-x86-runtime`/`dx-lum-uned-dbg`/`uedcli-rust-build` images had been evicted from the shared
Docker daemon by disk pressure mid-session; rebuilt from their committed Dockerfiles (all three
reproducible on this x86_64 host — no FEX/arm64 snapshot problem here).

**Editor's real root split for `child=6108` is a DIFFERENT plane than native picks, and for a
concrete, measured reason:**

- Editor's actual first `bspAddNode` for this subtree uses plane `N=(1,0,0) B=(508, 8.000002, 280)`
  — i.e. `x=508`. This is NOT native's chosen winner (`slot=12`, plane `(0,0,-1,-280)`, score=60,
  `pf=0x21`=`PF_SEMISOLID|PF_INVISIBLE`); it matches native's OWN candidate at `slot=32`
  (`pf=0x20`=`PF_SEMISOLID` only, score=108) — a candidate native's own `find_best_split_exact`
  ranks WORSE (higher score) and rejects.
- **Ruled out: candidate-list ORDER.** Re-ran `find_best_split_trace` on the same 40
  `make_ed_polys`-reconstructed polys sorted by surf index (`i_link`, matching `bspBuildFPolys`'
  documented "from Surfs" order) instead of the tree-walk order `make_ed_polys` produces — native's
  winner is UNCHANGED (still the score=60 candidate, just at a different sampled slot). Order alone
  does not explain the divergence.
- **Confirmed: candidate-list SIZE.** The live `FindBestSplit` breakpoint (`0x100338ee`, args
  `NumPolys=[ebp+8] Opt=[ebp+0x10] Balance=[ebp+0x14] stride=[ebp-0x18]`, per
  `fbs_stride_oracle.py`'s decode) caught the editor's real root-level call for this subtree:
  `numpolys=29 opt=1 balance=12 stride=1`. Native's `make_ed_polys` reconstructs **40** polys for
  the same subtree — **11 more than the editor's real list**. (`opt=1`/`stride=1` also contradicts
  the old, pre-2026-08-14 `fbs_stride_oracle.py` comment's "Opt=1→N/10" formula — another data point
  the owner's invalidation ruling was right to flag; not chased further here.) The editor's 29-poly
  list also matches the 29 `bspAddNode` calls captured for this subtree's whole rebuild (one native
  fragment survives roughly 1:1 into one output node here), corroborating 29 as the real count, not
  a one-off artifact of the breakpoint.

**Root cause, not yet fixed:** `make_ed_polys` (native's subtree-poly reconstructor for
`repartition_frontier`, walking the OLD subtree's nodes self→front→back→coplanar-chain) emits 11
spurious extra polys the editor's real `bspBuildFPolys`+`bspMergeCoplanars` step does not — most
likely un-merged coplanar/adjacent fragments left over from the subtree's ORIGINAL (pre-repartition)
build that the editor's real merge pass coalesces and native's reconstruction does not. This is
consistent in direction with the reverted blanket-`bsp_merge_coplanars` experiment above (which
shrank the poly count and moved UNATCO verts almost exact) but explains why that blanket version
overshot elsewhere: merging needs to be scoped to reproduce this exact 40→29 reduction, not applied
indiscriminately across the whole reconstructed list.

**Not yet done:** identify which specific 11 of the 40 polys are the spurious ones (dump both lists
side by side, matched by plane+base, to see whether they're a coplanar-chain artifact specifically or
something else), then check whether a scoped fix generalizes to the other 2 residual calls and to
Wanchai's own (currently-exact) tree before touching shipped code — the prior blanket-merge attempt
broke Wanchai, so any fix here needs that as a hard regression gate before shipping.

## Mechanism fully identified (2026-08-29 PM) — but the general fix is still open; blanket
## application reproduces the EXACT prior regression, so this is NOT a quick port

Ran the 11-poly gap to ground: every one of the 11 "extra" polys in native's 40-poly reconstruction
shares its exact `i_surf` (via `FPoly.i_link = n.i_surf`, set in `bsp_node_to_fpoly`) with another
poly already in the list — e.g. `isurf=3555` appears 3 times (nv=4,3,4), `isurf=3556` 3 times,
five other surfs 2 times each: 29 unique `(actor, i_brush_poly)` pairs, 11 duplicate copies, exactly
`40 − 29`. These are unmerged coplanar fragments left over from the subtree's ORIGINAL (pre-repartition)
build, sharing a surf via UE1's normal coplanar-chain sharing — not a traversal bug in `make_ed_polys`
(vertex counts differ between "duplicate" entries, so they are genuinely different NODES, not the same
node visited twice).

**Isolated fix, verified exact:** the ALREADY-SHIPPED `bsp_merge_coplanars` (its `merge_group_pred`
already gates on `a.i_link == b.i_link`, i.e. it is already scoped to same-surf fragments, not a
blanket coplanar sweep) applied to JUST this subtree's 40 reconstructed polys, in isolation:
- Produces exactly 29 output polys — matching the editor's real `FindBestSplit` `NumPolys=29` to the
  digit (live-captured, see the GDB-capture section above).
- Feeding that merged 29-poly list into `find_best_split_trace` picks `plane=(1,0,0,508)` as the
  winner — the editor's EXACT real root split for this subtree, byte for byte.

This is airtight for `child=6108` specifically: candidate SET, count, and the resulting split
decision all match the editor exactly once merged.

**But wiring `bsp_merge_coplanars(polys)` into `repartition_frontier` for ALL 209 calls (not just this
one) reproduces the identical regression the earlier "Tried, reverted" experiment above already hit:
UNATCO nodes 6321→5689 (target 6314, surfs/leaves stay exact, points -569) — the SAME 5689 number,
independently reproduced.** So the merge step is provably correct for the one call that needs it, and
provably wrong in aggregate across the other ~208. The missing piece is SELECTIVITY: something
distinguishes the ~3 calls that need this merge from the ~206 that apparently don't (or where merging
actively corrupts an otherwise-correct split) — not yet identified. Reverted (`bspcsg.rs` back to the
pre-experiment commit; `cargo test --lib` 84/84 pass after).

**Live-capture infra now exists and is reusable**: `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/`
— `repart_child_trace.py <node>` attaches gdb to a real `MAP LOAD`+`MAP REBUILD` of
`_scratch/bsp-parity-proj/golden_unatco_control.dx` under `dx-lum-uned-dbg`, gates breakpoints on
`bspRepartition`/`bspAddNode`/`FindBestSplit` to fire only during one target subtree's own call, and
captures its exact node-by-node build; `native_child_trace.py <node>` gets native's own
`FBS_ROOT_TRACE`/`FBS_ACTORS` for the same call via `UEDCLI_REPART_FBS_CHILD`;
`regression_gate.py` re-measures full UNATCO+Wanchai geometry against their world-only goldens.
Both `ued-x86-runtime`/`dx-lum-uned-dbg`/`uedcli-rust-build` Docker images were evicted from the
shared daemon by disk pressure mid-session and rebuilt from their committed Dockerfiles (all
reproducible on this x86_64 host — the FEX/arm64 snapshot problem in
`ued-x86-runtime-reproducible-arm64-fex-image` does not apply here).

**Next step:** run the SAME live-capture method against one of the ~206 "clean" calls (any
`REPART_CALL_DIAG`-silent call, i.e. one whose native delta is already 0) to see whether the editor's
real poly count for it EQUALS native's unmerged `make_ed_polys` count (predicting merge should be a
no-op there and the 5689 regression comes from `try_to_merge`'s geometric weld being wrong on some
inputs) or is itself SMALLER (predicting native's reconstruction has a broader duplication problem
that merge over-corrects). That result should show which of the two failure modes is real before
attempting another wiring.

## `REPART_CALL_DIAG`'s delta flag is NOT a valid proxy for "needs merging" (2026-08-29 PM, cont'd)

Ran the next-step check above on `child=4077` — the 2nd of the 209 calls, `REPART_CALL_DIAG`-silent
(i.e. one of the ~206 calls this item's earlier write-ups assumed were already correct). Same live
gdb method as `child=6108`:

- Native's unmerged `make_ed_polys` reconstruction: **107** polys.
- Editor's real `FindBestSplit` (live-captured, `0x100338ee`): **numpolys=75**.
- `bsp_merge_coplanars` on the same 107 polys, in isolation: **75** — exact match again, and its
  winning plane's `score=0` (a clean, unambiguous winner, so this isn't a near-tie either).

**This overturns the working assumption that only ~3 of 209 calls need the merge.** `child=4077` was
never flagged by `REPART_CALL_DIAG` (its `appended_nodes == orig_polys`, i.e. native's own
un-merged 107-poly split happens to still emit exactly 107 nodes with no net loss) — that diagnostic
only measures native's OWN internal input/output consistency, not whether the result matches the
editor. It is silent here despite a 107-vs-75 gap even bigger than `child=6108`'s 40-vs-29. So the
merge is very likely needed on most/all 209 calls, not a handful — 2 for 2 tested so far, both exact.

**This makes the 5689-node blanket-merge regression MORE surprising, not less**: if merging
independently reproduces the editor's exact poly count and winning split on every call checked so
far, the -625 node deficit must come from something other than "merge is too aggressive on most
calls" — candidates not yet checked: (a) a genuine per-call node-count difference downstream of the
root split even when the poly SET matches (i.e. matching the root decision isn't sufficient — the
recursive front/back splits could still diverge and this happens to cost nodes on net), or (b) a
cross-call interaction from processing 209 grafts sequentially without recompacting between them
(`compact_unreachable_nodes` only runs once, at the very end, after ALL 209 calls — a later call's
`make_ed_polys` walk could be reading a subtree state some earlier call's graft already altered, in
a way this item hasn't traced). Neither is confirmed; both need their own live/isolated check before
another wiring attempt. `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/` has the reusable
harness for either.

## Per-call merge proven correct on 4/4 (full recursive tree, not just root); aggregate deficit still
## unexplained — root cause is NOT merge selectivity (2026-08-29, later PM)

Two new committed diagnostics in `bspcsg.rs::repartition_frontier` (both env-gated, zero effect on
the default path — confirmed by `regression_gate.py` and `bin/test -k bspcsg` unchanged at
6321/11648 with neither var set):

- **`UEDCLI_REPART_ISOLATED_TREE`** (paired with the existing `UEDCLI_REPART_FBS_CHILD=<child>`):
  merges the target call's `fbs_polys`, rebuilds them via `split_poly_list` into a scratch clone of
  `model` with `nodes` cleared (sharing the real surf/point/vector pools by clone, so `i_link`s still
  resolve), and dumps every resulting node's `iFront`/`iBack`/`iPlane`/plane — the FULL recursive
  shape, not just the root split `UEDCLI_REPART_FBS_DUMP`/`FBS_ROOT_TRACE` already gave.
- **`UEDCLI_REPART_BLANKET_MERGE`** (temporary experiment, kept as a diagnostic): reproduces the
  reverted blanket-merge attempt but adds a `REPART_MERGE_DIAG` line per call
  (`orig_polys`/`merged_polys`/`appended_nodes`), so the whole 209-call distribution can be
  inspected instead of just the final aggregate.

**Test 1 — full recursive shape for `child=6108`, not just the root.** Normalized the editor's real
29-`ADD` capture (`logs/repart-child-6108.log`) into a 0-based node tree (line `k`'s assigned index is
`6314+(k-1)`, confirmed by the `parent=` fields matching exactly on that assumption) and diffed it
node-for-node against `UEDCLI_REPART_ISOLATED_TREE`'s 29-node dump for the same call. **Every single
`iFront`/`iBack`/`iPlane` link matches exactly, all 29 nodes, plus spot-checked plane `W` values
(base·normal) at nodes 0/1/11/15/17 all agree to 4+ decimal places.** This refutes the standing
hypothesis (a): matching the root split is NOT insufficient here — the recursion the winning split
feeds into ALSO reproduces the editor exactly, once fed the merged poly list.

**Test 2 — where does the 209-call blanket regression's shortfall actually live?** Ran
`UEDCLI_REPART_BLANKET_MERGE` over full UNATCO and analyzed the 209 `REPART_MERGE_DIAG` lines
(`sum(orig_polys)=3218`, `sum(merged_polys)=2584`, `sum(appended)=2593`, matching the `-625`ish
regression via `6314 + 2593(appended) − 3218(removed by compact_unreachable_nodes) = 5689`, exact).
**Only 46 of 209 calls have ANY reduction under merge; 163 are pure no-ops.** The reduction is heavily
concentrated: the top 7 calls alone (`child=3086,3033,3088,3693,3079,4077,4096`) account for 367 of
the 634 total poly reduction (58%).

**Test 3 — live-verified the single BIGGEST contributor.** `child=3086` (`parent=1892 place=NODE_FRONT`,
the same call flagged by the old `REPART_CALL_DIAG` with `delta=+2` under the CURRENT shipped/unmerged
code — that diagnostic's "+2" is a red herring, an artifact of the `>=14`-vert split-in-half rule,
utterly unrelated to matching the editor): native's unmerged reconstruction is 141 polys, merged is
57. Live gdb capture (`repart_child_trace.py 3086`, `logs/repart-child-3086.log`): editor's real
subtree for this call is **exactly 57 `ADD` lines** — matching native's merged prediction exactly, not
the unmerged 141. Third call verified exact (after 6108, 4077), and by far the largest.

**Test 4 — live-verified a large ZERO-reduction call, to check the other side.** `child=3836`
(`parent=517 place=NODE_FRONT`, 59 polys, merge finds no duplicates so `orig_polys==merged_polys==59`):
live gdb capture (`logs/repart-child-3836.log`) — editor's real subtree is **exactly 59 `ADD` lines**,
matching native's UNMERGED reconstruction exactly. So native's current per-call poly-count
reconstruction is ALREADY correct here even without merging.

**4/4 live-verified calls now match the editor exactly** (6108, 4077 — poly count + root split only;
3086, 3836 — this session, full node count including the single biggest reduction and a large
zero-reduction control). Also ruled out: no two of the 209 `(parent, place)` entries target the same
`child` node index (checked programmatically), so double-processing/index-corruption across calls is
not happening at that level.

**The open contradiction.** If every call's own merge-and-resplit is individually correct (4/4,
covering both a shrinking case and a non-shrinking case), the AGGREGATE result of applying it to all
209 should land at editor's real total (6314) — not undershoot by 625. It doesn't. Arithmetically:
`6314 + appended − removed = final`, and `removed` (what `compact_unreachable_nodes` actually deletes)
equals `sum(orig_polys)=3218` exactly — i.e. the raw, UNMERGED size of every old subtree being
replaced. For the final total to reach 6314, `appended` would have to equal 3218 too (matching what's
removed), but the individually-verified-correct `appended` is `~2593` (the merged, smaller sizes).
This is not a contradiction in the per-call evidence — it means one of two things, neither confirmed
yet:
- Editor's own PRE-repartition subtree at these 46 spots is NOT the same size as native's (i.e. NOT
  141 raw nodes for the `child=3086` spot, but something smaller to begin with) — but this conflicts
  with the ALREADY live-verified fact that native and editor agree EXACTLY on the total node count
  (6314) at the post-detail-loop checkpoint immediately before repartition begins. If editor's own
  pre-repartition subtrees are smaller at exactly these 46 spots, something elsewhere in the tree must
  be correspondingly BIGGER on native's side to still land on 6314 at that checkpoint — not yet
  located.
- Or: some subset of the OTHER ~163 "merge is a no-op" calls actually need to GROW during repartition
  (editor's real post-repartition subtree bigger than the raw poly reconstruction), which neither the
  shipped unmerged code nor a merge-based fix can currently produce (`bsp_merge_coplanars` only ever
  shrinks-or-preserves; native's `split_poly_list` has no mechanism to emit more nodes than input polys
  except the rare `>=14`-vert split-in-half case). Only 1 of the 163 no-op calls has been live-checked
  (`child=3836`, which needed no growth) — nowhere near enough coverage to rule this out; a genuine
  "needs growth" call has never been found or looked for.

**Next step:** sample more of the 163 "merge no-op" calls (ideally biased toward LARGE ones, since a
compensating growth big enough to offset a 625-node deficit would likely be concentrated the same way
the reduction is) specifically looking for one where editor's real count EXCEEDS native's raw
`orig_polys` — the first direct evidence for or against the "some calls need to grow" hypothesis. If
none is found after a reasonable sample, the alternative (a genuine pre-repartition tree-shape
difference at the 46 reducing spots, currently masked by a compensating error elsewhere in the
~6314-node tree) becomes the leading explanation and needs its own hunt — most likely inside the
detail-brush CSG loop / `bsp_cleanup` immediately upstream of `collect_repartition_frontier`'s
snapshot, not inside `repartition_frontier` itself.

**Not shipped.** `bspcsg.rs`'s default build path is unchanged (`UEDCLI_REPART_ISOLATED_TREE` and
`UEDCLI_REPART_BLANKET_MERGE` are both opt-in, off by default); `bin/test -k bspcsg` (84/84) and
`regression_gate.py` with no env vars set both reproduce the pre-existing 6321/11648 baseline exactly,
confirmed after committing the two diagnostics. The regression_gate harness itself needed a small path
fix (`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/regression_gate.py`): the Wanchai
scratch trunk (`dev/games/trunks/tmp-wanchai-market`) no longer nests under a `maps/` subdirectory
(likely touched by a concurrent session sharing this checkout) — the script now detects an `actors/`
dir directly under the project root and uses that as the trunk path instead of assuming `maps/<name>`.

## 2026-08-29, later that night: growth hypothesis unconfirmed on the largest no-op calls; a
## pre-repartition SUBTREE-SIZE match (new, solid); a measurement-artifact dead end (documented so it
## isn't repeated)

Continuing the "sample more of the 163 merge no-op calls, biased large, looking for editor real count
> native's raw count" plan from the section above.

**More live verification: 7/7 calls now match exactly, zero growth found.** Added 3 more live gdb
captures (`repart_child_trace.py`) on the largest remaining zero-reduction calls:
`child=3600` (26 polys, `parent=340 place=NODE_FRONT`) — editor real = 26 exactly.
`child=4668` (25 polys, `parent=2487 place=NODE_FRONT`) — editor real = 25 exactly.
`child=3689` (18 polys, `parent=1241 place=NODE_BACK` — the only place=0/NODE_BACK case checked so
far) — editor real = 18 exactly.
Combined with the earlier `3086`/`3836`, this is **7/7 live-verified calls exact** — the top 7 largest
zero-reduction calls (out of 163) all confirm native's unmerged count is already correct, and the top
3 reducing calls (out of 46) all confirm the merged count is correct. No call checked so far shows
editor's real count EXCEEDING native's raw `orig_polys` — no evidence yet for "some calls need to
grow". But only 7 of 163 no-op calls are checked (all biased toward the LARGEST) — the ~156 untested
ones (each ≤17 polys) are not ruled out; if compensating growth exists, it is not concentrated at the
top and would have to be spread thin across many small calls to reach +625 in aggregate.

**New tool + solid finding: the pre-repartition SUBTREE feeding each call is IDENTICAL between native
and editor, not just its count.** Added `UEDCLI_BSPCSG_PREPART_NODES` (`bspcsg.rs`, dumps
`model.nodes` right before `repartition_frontier` runs — the post-detail-loop, pre-209-calls
checkpoint, 6314 nodes) and a new committed harness script,
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/prepart_tree_unatco.py`, which captures
the SAME checkpoint from the live editor (breaks on the SECOND `bspRepartition` entry — the first of
the 209 subtree calls — right before it runs, and dumps the editor's own full `Model->Nodes`, all
6314, via the same `FBspNode` layout `repart_tree_unatco.py` already used). Findings from
`logs/prepart-tree-unatco.log` (editor) vs the native dump:
- **Root node matches exactly** (plane `(-0,-0,1,240)`, `isurf` differs as expected — surf numbering
  is a separate pool that doesn't need to match) — confirms node-index correspondence holds at this
  checkpoint, a prerequisite for everything below.
- **The frontier LEAF SET matches almost perfectly**: reproducing `collect_repartition_frontier`'s
  logic in Python over both dumps (native's own `i_back`/`i_front` fields directly correspond to
  editor's raw `iBack`/`iFront` at this checkpoint — NO swap needed here, unlike the swap inside
  `zone_pass`'s own window) gives `list_b` (`NODE_FRONT` targets) matching 2691/2691 EXACTLY, and
  `list_a` (`NODE_BACK` targets) matching 1988/1990 — off by exactly ONE swapped pair (native has node
  2947, editor has node 2230; inspecting both shows they are the SAME physical coplanar chain at plane
  `(0,0,1,-64)`, just built in the opposite chain order — a tiny, localized coplanar-order quirk, not
  a systemic shape difference). **4679/4680 frontier slots agree exactly (99.98%)** — this refutes the
  "different pre-repartition tree SHAPE hides behind the matching aggregate count" hypothesis as an
  explanation for a 625-node gap; one swapped pair cannot account for it.
- **For every one of the 7 live-verified calls, native's raw (pre-merge) subtree size at that
  checkpoint EXACTLY equals editor's own raw subtree size at the same node index** (walked via each
  engine's own `iFront`/`iBack`/`iPlane` from the frontier child, in both dumps): `child=6108`
  40=40, `4077` 107=107, `3086` 141=141, `3836` 59=59, `3600` 26=26, `4668` 25=25, `3689` 18=18. This
  is a new, solid, offline-checkable result — the "duplicate coplanar fragments" `make_ed_polys`
  reconstructs are NOT a native-only reconstruction artifact; the editor's own pre-repartition tree
  carries the exact same duplicated fragments, at the exact same count, at the exact same spot. It
  strengthens (not weakens) the merge fix: both engines start from the identical "dirty" input: native's
  `bsp_merge_coplanars` reduces it to editor's own real output, exactly, every time checked.

**Dead end, documented so a future session doesn't repeat it: a "read `Model->Nodes.Num` after every
one of the 209 calls in one `MAP REBUILD` run" probe gives an internally-inconsistent, unusable
reading.** Built `repart_allcalls_unatco.py` (committed) to cheaply get editor's real per-call node
delta for ALL 209 calls at once (instead of one expensive live capture per call), breaking on
`bspRepartition` entry (`0x10049fc0`, caching `$m` = the Model pointer + `$child`) and dumping
`*(int*)($m+0x5c)` at `bspRefresh` completion (`0x1004a05f`) for every call. Confirmed `$m` is the
SAME pointer for every one of the 210 calls (rules out "reads a different/scratch Model" as the
explanation) and got a suspiciously clean result: **`Nodes.Num` reads EXACTLY 6314 after literally
every one of the 209 subtree calls, with zero exceptions** — and a 3-breakpoint version (adding
`0x1004a047`, "after bspBuild, before bspRefresh") showed the count TEMPORARILY bumps up by exactly
however many nodes that call's own `bspBuild` just appended (e.g. `child=4077`: 6314→6389, +75 — the
same size the merged prediction gives), then drops back down to EXACTLY 6314 at `bspRefresh`
completion, for every call, regardless of that call's own old/new subtree sizes.

This is **directly contradicted** by independently-verified ground truth: `child=6108`'s real 29-node
subtree (from the live `ADD`-sequence capture, cross-validated structurally against native's isolated
merge-and-resplit tree — see the "full recursive tree" section above) occupies freshly-assigned node
indices **6314 through 6342** — i.e. real, distinct, newly-built array entries that must exist for the
final map to be correct, yet `Model->Nodes.Num` claims the array is back at 6314 (as if nothing was
appended) immediately after. Ruled out as measurement bugs: breakpoint firing count is exactly 1 per
call for `ENTRY`/`POSTBUILD`/`CALLEND` (210/210/210, no duplicates), and the Model pointer is stable.
**Conclusion: whatever `Model->Nodes.Num` (`Model+0x5c`) reflects at the `bspRefresh`-completion PC
inside the PER-SUBTREE repartition path, it is not simply "how many live node entries exist" — reading
it this way is unreliable and should not be used as evidence for or against any hypothesis without
first resolving this contradiction** (candidates, none checked: the offset means something different
in this call path; `bspRefresh` writes back a saved pre-call checkpoint for unrelated bookkeeping
reasons and the real compaction happens in a later, separately-located pass — mirroring native's own
"append during the loop, `compact_unreachable_nodes` once at the end" shape, in which case per-call
reads during the loop simply aren't comparable between the two engines at all). The "sample per-call
editor deltas cheaply" idea is not disproven in principle — just this specific offset/breakpoint
combination is unusable. Do not resume this exact approach without first explaining the contradiction.

**Net position, unchanged in substance but now much better evidenced:** the per-call merge-and-resplit
operation is correct (7/7, including matching pre-repartition inputs, not just outputs). The -625/-634
aggregate deficit from blanket-applying it is real and still unexplained. The two most promising
un-eliminated leads: (a) growth concentrated in many small no-op calls rather than a few large ones —
untested, would need many more (cheap, since these are all small) live captures, or a fixed version of
the all-calls-in-one-run probe once its `Nodes.Num` semantics are understood; (b) something in the
FINAL, whole-model compaction (wherever/whenever it really happens — not `repartition_frontier`
itself) that native's single end-of-loop `compact_unreachable_nodes` doesn't reproduce faithfully. Not
eliminated: the specific coplanar-chain-order quirk found in the frontier-set diff (nodes 2947/2230)
could be a symptom of a broader chain-ordering difference elsewhere that a leaf-set diff alone
wouldn't surface — not investigated further this session.

## 2026-08-30: hypothesis (b) [compaction timing] cleanly REFUTED; pre-repartition structural match
## extended to ALL 209 calls (not just a sample); 3 more live-verified calls, still 0/10 growth found.
## Root cause remains OPEN — this is the state-of-investigation summary for a future round.

Per the coordinator's steer, tackled lead (b) first since it's a single measurement/experiment rather
than ~150 more live gdb round-trips.

**(b) is refuted, cleanly, with a real experiment (not just reasoning).** Added
`UEDCLI_REPART_COMPACT_PER_CALL` (`bspcsg.rs`, committed, opt-in): `compact_unreachable_nodes` now
returns its `old->new` remap table, and `repartition_frontier`'s worklist is index-based (not a plain
`for`) so a mid-loop compaction's remap can fix up the still-pending entries' `parent` field before
they're read on a later iteration (a real correctness requirement for this experiment — a mid-loop
compaction with no remap would silently corrupt every later call's `parent` index). Results:
- `UEDCLI_REPART_COMPACT_PER_CALL=1` alone (no merge): **byte-identical to the unmerged baseline**
  (6321/11648, matching every metric — verts, points, vectors, all unchanged). No `debug_assert`
  fired (a pending frontier parent never went unreachable mid-loop, confirming the structural
  disjointness reasoning from the prior session was right).
- `UEDCLI_REPART_COMPACT_PER_CALL=1` + `UEDCLI_REPART_BLANKET_MERGE=1` together: **byte-identical to
  blanket-merge alone** (5689/11628, every metric — verts +208/+84, points -569/-1, vectors +0/-8, all
  matching exactly between the two runs).
Compaction TIMING — once at the end of the whole 209-call loop vs. immediately after every individual
call — makes **zero difference** to the final result, with or without the merge fix. This is the
predicted outcome of the disjoint-subtree structural argument from the prior session (each frontier
target's subtree is reachable only via its own specific parent link, set once before
`repartition_frontier`'s loop starts, so no call's graft can ever alter what a DIFFERENT, not-yet-
processed call's own subtree contains — reachability GC run early or late collects the exact same
dead set either way) — now confirmed empirically, not just argued. The re-formulated hypothesis (b)
(per-call editor-side compaction interacting with `make_ed_polys`'s later reads) does not hold.

**Pre-repartition structural match extended from a 7-call sample to ALL 209 calls — still solid, still
free (uses the tree dumps already on disk, zero new live captures).** The prior session compared
native's `UEDCLI_BSPCSG_PREPART_NODES` dump against the editor's `prepart_tree_unatco.py` capture for
only the 7 live-verified calls. Re-ran the same reachability-walk comparison for every one of the 209
`(child)` values in `/tmp/merge_diag.log` (reusable one-off script, not yet committed — trivial to
reproduce from the two committed log files, `logs/prepart-tree-unatco.log` and a
`UEDCLI_BSPCSG_PREPART_NODES=1` native run): **all 209 calls' pre-repartition subtree NODE-INDEX SETS
match exactly between native and editor, and every node's `nv` (vertex count) within those sets also
matches exactly** — not just aggregate size, actual set-equality plus a per-node structural proxy. Zero
mismatches. This closes off "the pre-repartition tree has a hidden shape/size difference at some
untested call" as an explanation just as completely as the 7-call sample suggested, now for the WHOLE
frontier, not a biased subset.

**3 more live-verified calls, still 0/10 total showing growth**, diversifying away from the "biggest
calls only" bias of the prior round:
- `child=4247` (17 polys, no-op, `place=NODE_FRONT`) — editor real = 17 exactly.
- `child=4998` (8 polys, no-op, `place=NODE_BACK` — the smallest and only the 2nd `NODE_BACK` case
  checked) — editor real = 8 exactly.
- `child=4096` (85→54 under merge; **also one of the original 3 `REPART_CALL_DIAG`-flagged calls**,
  whose UNMERGED native reconstruction internally grows 85→89 via the `>=14`-vertex split-in-half rule
  — the same red-herring category as `child=3086`'s old `+2` flag) — editor real = **54**, exactly
  matching the MERGED prediction, not the internally-grown unmerged 89. Confirms again that
  `REPART_CALL_DIAG`'s "delta" signal (an internal self-consistency check, not a ground-truth compare)
  is meaningless for judging correctness — third such case now (`3086`, `6108`, `4096`).

**10/10 live-verified calls total** (`6108`, `4077`, `3086`, `4096`, `3836`, `3600`, `4668`, `3689`,
`4247`, `4998`), spanning sizes 8-141, both `place` values, both reducing and non-reducing calls, and
the one internally-inconsistent-under-unmerged edge case. Zero counter-examples to "native's merged
prediction (or raw prediction, when merge is a no-op) exactly equals editor's real output" — but this
is still only 10 of 209 (4.8%), and every selection was biased toward LARGE calls within each bucket;
the ~199 untested calls skew small (≤17 polys, mostly single digits to teens).

**Where this leaves the investigation.** Every offline-checkable structural question has now been
asked and answered favorably: the per-call merge operation is correct (10/10), the pre-repartition
INPUT to every one of the 209 calls is structurally identical between engines (209/209), and
compaction timing is provably irrelevant (a real experiment, not just an argument). The arithmetic
(`start(6314) + appended(~2593) - removed(3218, = sum of ALL 209 calls' raw old-subtree sizes) =
5689`) is airtight given those facts, which means the -625 deficit can ONLY come from `appended` being
too low relative to what editor's real per-call outputs would sum to — i.e. from a subset of the
untested ~199 calls where editor's real output does NOT match native's prediction. Two flavors remain
open, neither eliminated nor confirmed:
1. **True per-call growth** (editor's real output > native's raw/merged prediction) concentrated in
   the small, untested calls rather than the large, tested ones — 0/10 evidence so far, but the sample
   is entirely large-biased and could simply be missing it.
2. **A subtler, low-rate SPLIT-CHOICE divergence** — not a poly-count mismatch at all, but
   `bsp_merge_coplanars`'s geometric thresholds or `find_best_split_exact`'s heuristic picking a
   DIFFERENT (still node-count-EQUAL) tree shape than the editor's real recursion for some small
   fraction of calls, in a way a top-N-biased or "biggest reduction" sample would never surface — this
   would require comparing FULL recursive structure (like the `child=6108` isolated-tree check), not
   just final counts, against real per-call editor ground truth, for calls picked by some OTHER
   criterion than size (texture/geometry pattern, near-tie split scores, etc. — none tried yet).

**Recommended next step for a future round:** neither exhaustive live-sampling of ~199 more calls nor
more reasoning from existing data is likely to crack this cheaply. The highest-leverage remaining move
is probably either (a) a genuinely different, cheaper-than-live-gdb oracle for editor's real per-call
output across ALL 209 calls at once — which would need `repart_allcalls_unatco.py`'s `Nodes.Num`
contradiction actually resolved first (not attempted this round; the coordinator's suggested
per-call-compaction fix for it was a DIFFERENT experiment, already run and negative — see above), or
(b) accepting the -625 deficit is not going to yield to per-call analysis and instead looking at
whether a full recursive-structure diff (not just counts) on a RANDOM (not size-biased) sample of ~10
more small calls turns up anything.

## 2026-08-30: index-allocation check — the specific "progressive per-call compaction" hypothesis is
## REFUTED (9/9), but the underlying data reveals a THIRD architecture, neither native's nor the one
## just tested — this needs disassembly, not more live-gdb probing at the current breakpoints.
## STOPPING per the coordinator's own exhaustion criterion; state-of-investigation summary below.

The coordinator asked for a specific, sharper check before treating hypothesis (b) as fully closed:
does a call occurring LATER in the 209-call sequence — after a big reducer like `child=4077` (idx=2,
107→75) has already run — get a LOWER real node index for its own graft than native's append-only
model would predict (i.e. does editor really compact progressively, using the TRUE merged size, in a
way the already-completed `UEDCLI_REPART_COMPACT_PER_CALL` experiment might not have faithfully
tested)?

**Concrete check, using data already on disk (zero new live captures):** every `repart_child_trace.py`
capture logs each `bspAddNode` call's `parent=` argument. For a call's OWN first-added node (`place=3`,
`ROOT`, `parent=-1`), the SECOND `ADD` line names that first node's assigned index directly, via
`parent=<that index>`. Checked this for all 8 calls whose raw logs survive on disk (`3086`, `3836`,
`3600`, `4668`, `3689`, `4247`, `4998`, `4096` — `6108`'s own log was independently decoded to the same
value earlier this session, before a concurrent session truncated the file), spanning call-sequence
positions **idx=14 through idx=207** — i.e. from very early to almost the very last of the 209 calls,
on both sides of `child=4077`'s idx=2 reduction and several other reducers in between (confirmed via
each capture's distinct `ilink`/`N`/`B` values on the FIRST line — proof these are 8 independent, real
captures, not a stuck script). **Every single one of the 9 calls' second `ADD` line reads
`parent=6314`** — i.e. every one of the 209 calls, regardless of how many reducers already ran before
it, starts writing its own new subtree at the EXACT SAME fixed index (6314, the pre-loop baseline),
not a progressively lower one.

**This directly refutes the coordinator's specific hypothesis**: editor's real per-call node
allocation does NOT reflect a cumulative, TRUE-merged-size-based compaction that would push later
calls' indices down. If it did, `child=4096` (idx=116, occurring after MANY reducers including
`4077`'s -32 and `3086`'s -84) would start well below 6314; it starts at 6314, identically to
`child=3600` at idx=14 (right after the very first few calls).

**But this ALSO reveals something neither native's model nor the just-tested hypothesis predicts.**
6314 is not an arbitrary number — it is EXACTLY the well-established pre-loop baseline (confirmed via
both `UEDCLI_BSPCSG_PREPART_NODES` and the live `prepart_tree_unatco.py` capture). For 9 different
calls, spread across nearly the entire sequence, to ALL treat 6314 as "the next free index" — even
though real, distinct, necessary content from EARLIER calls in the sequence must persist somewhere for
the final map to be correct (verified structurally for `child=6108`, whose real content — 29 nodes —
occupies indices 6314-6342 per this exact chain-decoding method) — the only coherent reading is: **each
of the 209 individual `bspRepartition` sub-calls builds its new subtree into some kind of
scratch/temporary working region that is treated as starting fresh from the SAME baseline index every
time, and the true commit of that scratch content into its PERMANENT position in the model (without
colliding with every other call's use of the identical 6314+ index range) happens through a mechanism
this session's breakpoints never observed.** This is a genuinely different, THIRD architecture — not
native's "always append past the true end, GC once at the end" and not the coordinator's "progressively
compact using the true merged size" (which was tested directly via `UEDCLI_REPART_COMPACT_PER_CALL` +
`UEDCLI_REPART_BLANKET_MERGE` and gave the unchanged 5689 result — a result now understood to be fully
consistent with, not contradicted by, this new finding: that experiment tests WHEN native's own
correct-by-construction reachability GC runs, which has nothing to do with whatever the editor's real
per-call scratch/commit mechanism actually is).

**Why this is the right point to stop, per the coordinator's own exhaustion criterion.** Resolving
what the editor's real per-call commit mechanism is would need NEW disassembly work — tracing
`EmptyModel(0,0)` and whatever runs between it and the point where a subtree's data is durably in its
final position (not visible at the 4 breakpoints used this session: `0x10049fc0` entry, `0x1004a00d`,
`0x1004a027`, `0x1004a047`, `0x1004a05f` bspRefresh) — not more live captures at the current
instrumentation. Every clean, testable-with-current-tools architectural hypothesis has now been
checked and answered:
- Per-call merge correctness: **10/10 exact** (this session + prior).
- Pre-repartition input identity: **209/209 exact**, structurally (node sets + per-node `nv`), not
  just aggregate count.
- Compaction TIMING (once at the end vs. per-call, native's own GC either way): **provably irrelevant**
  (byte-identical results, with and without merge).
- Progressive REAL per-call index allocation (editor genuinely using smaller, merged sizes as it goes):
  **refuted, 9/9**, and refuted in a way that surfaces the deeper "fixed-baseline restart" puzzle above.

None of these four (nor last session's frontier-set/subtree-size structural matches) explain the -625
deficit. The path forward genuinely needs either fresh disassembly of the commit/graft mechanism, or a
fundamentally different live-capture technique (e.g. watching memory writes to the "old subtree"'s
original address range mid-call, to see whether the scratch-built new subtree gets copied there) —
both out of scope for more probing at the current breakpoint set. **Stopping here per the standing
instruction to not keep grinding once clean hypotheses are exhausted.** No code shipped this round
(no `bspcsg.rs` changes were needed or made — this was pure investigation using already-committed
diagnostics and already-captured logs). `bspcsg.rs` remains at its last-known-good, gate-passing state
(6321/11648 default, verified unchanged from before this investigation).

**Handoff for whoever picks this up next:** the concrete next step is disassembly, not another live
probe — find what code runs between `EmptyModel(0,0)` (before `0x1004a047`) and wherever a completed
per-subtree graft becomes durably reachable in the model, for the SPECIFIC per-subtree repartition
path (not the world-level one, which behaves differently — its own `Nodes.Num` readings were sane and
matched expectations). Candidate angle: `EmptyModel`'s own two integer arguments (`0, 0` here) likely
select a mode; the world-level call's arguments may differ and be worth re-checking too, since ITS
`Nodes.Num` readings never showed this fixed-baseline-restart behavior.

## 2026-08-30, continued: two more sharp coordinator hypotheses tested — surf-dedup mechanism REFUTED
## (wrong shape, not just count); the calling-convention/`ECX` hypothesis for the `Nodes.Num`
## contradiction also REFUTED, via disassembly this time, not another live guess

**Surf-dedup hypothesis (does `bspBuildFPolys` walk `Model->Surfs` emitting one poly per unique surf,
with NO geometric weld — making `bsp_merge_coplanars`'s actual weld unnecessary?): REFUTED, cleanly,
and more informatively than a pass/fail count check.** Added `surf_dedup` (`bspcsg.rs`, committed,
temporary) — keep only the FIRST poly per unique `i_link`, no geometry — and a
`UEDCLI_REPART_MERGE_MODE=dedup` switch shared by both `UEDCLI_REPART_BLANKET_MERGE` and
`UEDCLI_REPART_ISOLATED_TREE` (default stays `bsp_merge_coplanars`, so this is purely additive).
Results on `child=6108`:
- **Poly count**: dedup gives 29, identical to merge's 29 — a count-only check would call this a
  match.
- **Shape (the actual test the coordinator asked for)**: dedup's root node has plane
  `(0,0,-1,-280)` — this is native's OWN wrong winner from the unmerged 40-poly trace (`slot=12`,
  score=60) — NOT editor's real winning plane `(1,0,0,508)` (`slot=32`, score=108) that
  `bsp_merge_coplanars` reproduces exactly (independently re-verified this round: `ISONODE i=0`'s
  plane under merge mode is still `N=(1,0,0) W=508`). So dedup gets the COUNT right by coincidence
  and the SHAPE wrong — exactly the failure mode the coordinator flagged as possible, confirmed real.
  This makes sense in hindsight: "first poly encountered per surf, arbitrary" keeps whichever
  fragment happens to sort first, discarding the true weld's combined vertex extent — geometrically
  meaningless, not a coincidental stand-in for the real merge.
- **Blanket-wide** (`UEDCLI_REPART_BLANKET_MERGE=1 UEDCLI_REPART_MERGE_MODE=dedup`): UNATCO lands at
  **5599** (d=-715), WORSE than merge's 5689 (d=-625); Wanchai at 11628 (d=-20), same regression merge
  already causes. Dedup is strictly worse than merge on every axis checked. `bspBuildFPolys` walking
  `Surfs` with no weld is not what's happening — the geometric weld in `bsp_merge_coplanars` is doing
  real, necessary work, not an accidental substitute for simple dedup.

**Calling-convention hypothesis for the `Nodes.Num` contradiction (does `esp+4` actually mean Model at
the SUBTREE call site, or is Model really in `ECX` with `esp+4` reading unrelated caller-frame data?):
checked via static disassembly first, as instructed, then a live re-capture — REFUTED, though it
surfaced a real and interesting fact along the way.**

Disassembled `Editor.dll` around all three `bspRepartition` call sites inside `csgRebuild`
(`0x1004a650`, one clean aligned disassembly of `0x500` bytes covering all three — `rdis.py` from
`dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/`, works fine, `capstone` 5.0.7):
- **World-level** (`0x1004a89a`): `mov esi,[ebp-0x18]` (Model); `mov eax,[esi]` (vtable);
  `push 0; push 0; push dword ptr[edi+0x98]; mov ecx,esi` (ecx=Model=this); `call [eax+0x1ec]`.
- **Subtree loop1** (`0x1004aa3f`) and **loop2** (`0x1004aa90`): same shape —
  `mov ecx,[ebp-0x18]` (SAME local as the world-level Model read!); `mov eax,[ecx]` (vtable);
  `push 2; push ebx (iChild); push edx (=[edi+0x98]); call [eax+0x1ec]`.

So the coordinator's read of the pattern is right on one count: **`ecx` genuinely is a distinct value
from the pushed stack args at both call sites — it's the virtual-call `this`, loaded from the exact
same `[ebp-0x18]` local both times** (strong evidence it really is the persistent world Model). The
pushed args landing at `esp+4`/`esp+8`/`esp+0xc` inside the callee are `([edi+0x98], iChild, 2)`, not
`(Model, iChild, 2)` — `$child` (`esp+8`) has been reading `iChild` correctly the whole session by
coincidence of argument position, exactly as the coordinator suspected.

**But `ECX` is not the fix.** Re-disassembled `bspRepartition`'s own prologue (`0x10049fc0`): a normal
function prologue (`push ebp; mov ebp,esp; ...; mov edi,ecx; ...`) — no vtable-thunk `this`-adjustment,
so `ecx` at entry is exactly what the caller set it to, no surprises there. Re-ran
`repart_allcalls_unatco.py` with `$m = $ecx` instead of `$m = *(unsigned int*)($esp+4)` (temporary
edit, reverted after — `git diff` on the harness script is clean): the resulting pointer
(`0x3a854c4`) is STABLE across all 210 calls (same as the `esp+4` reading's own stability, `0x58fe1b4`
in that run) but reading `Nodes.Num` through it (`ecx+0x5c`) gives **6, constant, for every single
call** — obviously wrong (even the world-level repartition alone produces 2953 nodes). So `ecx` points
at some OTHER, smaller object — not the world Model, or not one holding `Nodes` at `+0x5c` — while the
ORIGINAL `esp+4` reading remains the one independently validated multiple times this multi-session
investigation (2953 post-world-repartition, 2984 post-testvisibility, 6314 post-detail-loop, all
matching independently-known-correct values at OTHER breakpoints in EARLIER, separate capture runs).
Swapping to `ecx` doesn't resolve the "flat 6314, contradicted by `child=6108`'s real content at
indices 6314-6342" contradiction — it replaces a validated-but-contradicted reading with an
unvalidated, actively-wrong one. **This specific calling-convention bug hypothesis is refuted.**

**Where this leaves things.** Both of this round's sharp, concrete hypotheses — surf-dedup instead of
geometric merge, and a `esp+4`-vs-`ecx` calling-convention bug — are now checked and refuted with
real evidence (a live blanket-wide regression_gate run for dedup; disassembly plus a live re-capture
for the calling convention). Combined with the prior rounds' four refuted hypotheses (per-call merge
correctness, pre-repartition input identity, compaction timing, progressive real index allocation),
this is now SIX independently-checked, clean architectural hypotheses, all refuted, plus the standing
unresolved `Nodes.Num`-flat-at-6314 contradiction that none of them explain. The `esp+4` reading is
still the best-supported one available and its contradiction with `child=6108`'s known real content
remains open — resolving it needs either disassembly of what runs BETWEEN `EmptyModel(0,0)` and a
completed graft becoming durably reachable (the same handoff note as before), or determining
`[edi+0x98]`'s actual field identity in `csgRebuild`'s own stack frame (not yet done — `edi` itself,
in `csgRebuild`, was assumed stable across the whole function but never independently confirmed by
disassembling `csgRebuild`'s OWN prologue to see where `edi` gets set).

**Not shipped.** `bspcsg.rs`'s only change this round is the `surf_dedup`/`reduce_repartition_polys`
diagnostic (opt-in, off by default); `bin/test -k bspcsg` (84/84) and `regression_gate.py` with no env
vars set both reproduce the pre-existing 6321/11648 baseline exactly. No fix cleared the hard gate.

## 2026-08-30, later: full disassembly of `bspRepartition` — a genuinely new architectural finding
## (a separate SCRATCH `UModel`, never before identified), but the exact commit mechanism is still
## unlocated. Redirected mid-round to use Wanchai's smaller 9-call case as the disassembly test bed
## per the coordinator's steer (same Editor.dll, findings apply to both levels identically).

Full write-up (live-verified, not just static reading) in `dev/docs/native-materialize-findings.md`
(two new entries) — summary here:

`bspRepartition` (`Editor.dll 0x10049fc0`) is a short 4-call dispatcher (`bspBuildFPolys`/
`bspMergeCoplanars`/`bspBuild`/`bspRefresh`, resolved to real addresses via a new `vtable_dump.py`
live capture), and **every per-subtree call builds its new geometry into a SEPARATE, single,
persistently-reused SCRATCH `UModel`** (`CTX = [[PersistentModel+0xa8]+0x98]`) — never the real
persistent world Model directly. Live-verified via a new `bspbuild_ctx_dump.py` (breaking inside
`bspBuild`, comparing `ebx`=this/persistent vs `esi`=CTX/scratch): `ebx≠esi` in 1203/1203 samples over
a full Wanchai `MAP REBUILD`, and the scratch address is a SINGLE CONSTANT across all 120 genuine
`bspRepartition`-triggered calls. **`bspBuild`'s `Flag` parameter (2 for every subtree call) skips
`UModel::EmptyModel` entirely** and appends straight into the scratch's EXISTING node array via the
`SplitPolyList` equivalent — meaning the scratch accumulates, uncleared, across the WHOLE 209/119-call
loop. This directly explains the earlier session's "`Nodes.Num` reads flat at the pre-loop baseline for
literally every one of 209 calls" contradiction: that reading (`esp+4` at `bspRepartition` entry) was
genuinely the PERSISTENT model, which really IS untouched throughout the whole loop — all the real
per-call construction happens in the separate scratch object instead.

## 2026-08-30, later still: the scratch-model reading above is WRONG. Corrected with direct live
## evidence (`bspAddNode`'s own argument, a `Nodes.Num` watchpoint, a fixed-node content diff) — see
## `dev/docs/native-materialize-findings.md` for the full write-up; summary here.

`repart_addnode_model_trace.py` captured `bspAddNode`'s own `Model` argument for all 29 node-adds
under `child=6108`'s `bspRepartition` call and diffed each against that call's own `Model` arg:
**0/29 mismatches** — every node write targets the persistent Model directly, never the CTX object
above. A hardware watchpoint on the persistent Model's `Nodes.Num` (`nodesnum_watch.py`) across a
full `MAP REBUILD` shows real `+1` growth per `bspAddNode` call — so `bspBuild`'s `esi` (the
`SplitPolyList` target for Flag=2) is the SAME persistent Model, referenced past its own `Num`
boundary as scratch slots within the SAME allocation, not a separate object as read from static
disassembly alone. At the end of every subtree call, `bspRefresh` calls
`Core.dll!Remove@FArray@@QAEXHHH@Z` (confirmed by IAT symbol) removing everything past a computed
"kept" boundary — a real array shrink, not a hardcoded reset. For every call sampled (2 through 44 of
209, including `child=6108` itself, independently known to have a `+1` delta by isolated-subtree
comparison), the kept boundary lands at EXACTLY the pre-call baseline (6314) — net zero. Checked
whether `child=6108`'s own fixed node slot is where new content lands (`node_content_before_after.py`,
its full 64 raw bytes at call entry vs. `bspRefresh` return): **byte-for-byte identical.** So the
subtree's root slot isn't rewritten either — the real content change (if any, for this specific
known-delta call) must land in a descendant slot, not yet checked, or the delta is realized some
other way not yet identified.

**Net status: the scratch-model claim (this session's earlier finding) is refuted by direct evidence
and corrected. In its place: a precise, live-verified mechanism at the array level (grow past `Num`
into the SAME persistent array as scratch, discard via a real `FArray::Remove` every call) — but the
exact site where a subtree's refined split becomes a permanent, visible change is still not pinned
down** — checked the two most obvious candidates (does `Num` net-grow: no; does the root node's own
slot change: no) and both came back negative for the one calibration case available (`child=6108`).
Concrete next step for a future round: check that call's DESCENDANT node slots (its original
`iFront`/`iBack` and their children) for a content change, and/or find which of the 209 calls
actually has non-zero net growth (only 3–9 of 209 are known to have any delta at all, so most calls
may legitimately net to zero — the growth-then-discard cycle seen so far may simply be working
scratch for calls that end up needing no change).

**Not shipped, no regression risk.** All new tools (`vtable_dump.py`, `bspbuild_ctx_dump.py`,
`repart_addnode_model_trace.py`, `nodesnum_watch.py`, `node_content_before_after.py`) are read-only
live captures; no `bspcsg.rs` changes this round. `bin/test -k bspcsg` (84/84) and
`regression_gate.py`'s default path unaffected (unchanged from the prior round: 6321/11648).

**Disk note:** the shared Docker daemon hit 100% full twice this round (0 bytes free) from container
churn across concurrent sessions; recovered both times via `docker builder prune -a -f` (safe —
regenerable build cache only, freed 2.5GB) and removing this session's own orphaned `uned-wp-vtdump`
volume (never another session's). Left `uned-wp-testdbg`/other unrecognized volumes untouched.
