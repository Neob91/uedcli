# Native materialize — findings ledger

The one place for short, cross-cutting, independently-checkable technical facts uncovered during
the native `level materialize` (BSP/CSG geometry + lighting) byte-parity work — disassembly,
live captures, structural measurements. Not board-item narrative, not owner rulings
(`direction/`), not design rationale (`rationale/`). Agents maintain this freely, but only by the
process below — never overwrite silently.

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
loops) — `esp+8=iChild` verified reliable (matches known target node indices across 10+ live
captures). `esp+4` as "Model" is **UNVERIFIED for this call site** — only ever confirmed at the
2-arg world-level site above, which may use a different calling convention. A `repart_allcalls_unatco.py`
sweep reading `esp+4` here returned a suspicious constant (6314) for every one of 209 calls —
possible garbage read, not yet resolved. Do not trust `esp+4`-derived Model/Nodes.Num data from
this call site until the calling convention is confirmed by fresh disassembly.

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
