+++
priority = "p1"
kind = "implement"
summary = "UNATCO Verts end 66037 vs the editor's 76488 — the whole 10.5k is csgRebuild's ~209 sub-BSP repartitions of newly-grown subtrees (mechanism fully decoded 2026-08-29, independent of the invalidated spike). Affects EVERY level's geometry, not just UNATCO. Needs new subtree-graft capability in bspcsg.rs -- real implementation work, not yet started."
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
18). Reverted (`bspcsg.rs` back to the pre-attempt commit) rather than debug further this session —
the node-count blowup suggests either the frontier collection is over-broad (collecting nodes that
shouldn't be there, so the loop repartitions far more of the tree than the real ~209 calls should
touch) or `bsp_refresh` isn't compacting the pre-repartition orphans the way assumed. Next attempt
should start by comparing `repart_frontier_a`/`repart_frontier_b`'s size against the expected ~209
(one board-item citation), and instrumenting `collect_repartition_frontier` to check whether it's
walking correctly before touching `split_poly_list` at all.
