+++
priority = "p2"
kind = "debug"
summary = "UNATCO Verts end 66037 vs the editor's 76488 — NOT a bspOptGeom weld gap (both weld exactly +21712); the whole 10.5k is csgRebuild's ~209 per-node sub-BSP repartitions, which native does not port at all"
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

**Still unknown, blocking a port:** WHERE and under what condition list 1 / list 2 get populated —
this has to be inside the detail-brush loop body (`0x1004a900`-`0x1004a9fc`, not yet traced past the
PolyFlags gate at `0x1004a986`-`0x1004a99d`), presumably one `TArray::AddItem` per processed detail
brush's newly-added node(s), split front/back by some condition. Next step: keep tracing that range
for the `AddItem`-shaped call(s) writing into `ebp-0x64`/`ebp-0x58`.
