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
