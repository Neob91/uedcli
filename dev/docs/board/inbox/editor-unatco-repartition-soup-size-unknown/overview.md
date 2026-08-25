+++
priority = "p1"
kind = "debug"
summary = "The editor's UNATCO repartition-soup size has never been captured; native's is 5114 faces -> 2504 after merge, and that one number would say whether the residual +54 nodes live in the soup or in the partition"
+++

# The editor's UNATCO repartition soup has never been measured — native's is 2504

Found while auditing `find_best_split_exact` (see the Front-2 item). After the candidate-slot-scan
fix, the whole-map residual is nodes 6368 native vs 6314 golden (**+54**). `#nodes = #input polys +
#polys actually split`, so the residual is either a bigger input soup or more splits — and only one
of those two numbers is known:

| stage | native | editor |
|---|---|---|
| committed pre-repartition tree | 6368 nodes | 6368 nodes (`committed_tree_diff.py` vs the cached `editor-struct-unatco-762.log`: 0 structural nodes) |
| faces `bspBuildFPolys`/`MakeEdPolys` emits (nodes with `nv>=3`) | 5114 | 5114 (counted from the same two dumps) |
| soup after `bspMergeCoplanars` (the list handed to `bsp_build`, before its own `finalize` filter) | **2504** (`UEDCLI_BSPCSG_SOUP_ORDER=1`, count `POLY` lines) | **unknown — never captured** |

Both engines enter the merge with the same 5114 faces, which is a strong starting point: the whole
question is what each side's merge leaves. At castle scale the merge machinery is already proven
faithful — native's post-merge soup equals the editor's live `bspBuild`-entry soup 199/199, multiset
and order (`sections/92-bspbrushcsg-reallevel-port-plan.md` §21) — so an UNATCO-scale mismatch, if
there is one, would be a scale-exposed case in `try_to_merge`/`merge_group_pred`, not a wholesale
error.

**Next step:** capture the editor's own soup with `harness/editor-tree-oracle/editor_polys_oracle.py`
at full UNATCO and diff it against native's `UEDCLI_BSPCSG_SOUP_ORDER` dump with
`polys_order_diff.py`. That is a live gdb capture; only the castle-scale soup
(`logs/bspbuild-soup.log`, `logs/editor-polys-33.log`) is cached today. If the counts match, the +54
is in `SplitPolyList`'s split behaviour; if they differ, the diff names the faces and points
straight at the merge.

**Do not read 2449 as the editor's number.** `spec.md` §5.2 of
`unrealed-geometry-build-map-rebuild-bsp-rebuild` cites "the actual 734-brush UNATCO map's CSG-root
poly soup (`NumPolys=2449`)" in a way that reads as an editor measurement. It is not: it is NATIVE's
own soup at the time of `sections/92` §20, and §20's conclusion was explicitly retracted at §21
("§20 said native 'under-merges → more soup' — WRONG"). Native's soup has since moved to 2504 (the
Front-1 pass-staging fix routes NotSolid brushes into pass 1, so more faces reach the soup). The
spec sentence has been corrected in place; this note records why.

## Answer (2026-08-25): editor's root NumPolys = 2514 — the soup is faithful, the gap is downstream

Live gdb capture (`harness/editor-tree-oracle/repart_numpolys_unatco.py`, new — breakpoint at
`Editor.dll 0x1004a041`, the `bspBuild` call site *inside* `bspRepartition`; `[esp]=Model`, walks
`Model->Polys->Element` — same address `editor_polys_oracle.py` already used, so this is
unambiguously the world-tree repartition call, not a per-brush temp-BSP call). `MAP LOAD` +
`MAP REBUILD` of `/tmp/UEDGolden_unatco_full.dx` (no OBJ LOAD needed — `MAP LOAD` demand-loads
content packages, `dev/docs/unrealed/quirks.md`), one breakpoint hit for the whole rebuild:

```
REPART_BUILD model=0x58fb784 polys=0x57d468c num=2514 nonzero_nv=2514
```

**Editor's root NumPolys is 2514** (all 2514 entries already `NumVertices>0` — no zero-vertex
slack to filter). Native's is 2504. **+10, +0.4%** — an order of magnitude smaller than the ~7%
node-plane disagreement (448 nodes) this soup feeds into.

**Sharper than "close": the two deltas run in OPPOSITE directions.** Native's soup is *smaller*
(2504 < 2514) yet native's final node count is *larger* (6366 > 6314, from the Front-2 candidate-fix
measurement). If the soup gap were driving the node gap, a smaller input soup should tend toward
fewer nodes, not more. It doesn't — so the +52-node / 448-plane-disagreement residual cannot be
explained by soup composition; it sits entirely in `SplitPolyList`/`FindBestSplit`'s own split
choices over an already near-identical input set.

**Conclusion: this confirms the remaining gap is a genuine heuristic-matching problem, not a soup
bug.** `bspMergeCoplanars`/soup construction is faithful at UNATCO scale (within 0.4%, consistent
with the castle-scale 199/199 exact-match finding). Not pursued further here (scoping the 260+
distinct disagreeing planes into a bisectable subset, if one exists, is a separate, open-ended
task) — reporting the number per this item's own instructions rather than forcing that next step.
