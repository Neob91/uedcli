+++
priority = "p1"
kind = "implement"
summary = "SHIPPED 2026-08-29 (repartition_frontier + compact_unreachable_nodes, bspcsg.rs), but with a REGRESSION on UNATCO -- see the 'lighting regressed' section below before trusting this as a clean win. Wanchai: nodes stay exact (11648), Verts -1988->+138 (14x closer), lighting UNCHANGED (3228/4530 byte-identical, same as before). UNATCO: nodes drift off-exact 6314->6321 (+7), which breaks lightmap-record alignment and drops lighting byte-identical from 2628/3345 to 1627/3345 -- a real regression on the metric that matters more. 4 OTHER already-inexact levels get worse in Verts too (separate over-build bug)."
+++

# UNATCO `Verts`/`Points` residual — it is the unported sub-BSP repartition loop

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
