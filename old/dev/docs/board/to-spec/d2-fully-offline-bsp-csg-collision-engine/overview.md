+++
priority = "p2"
kind = "implement"
summary = "D2 — fully-offline BSP/CSG/collision engine (the no-editor-ever upgrade — FOR LATER)"
+++

# D2 — fully-offline BSP/CSG/collision engine (the no-editor-ever upgrade — FOR LATER)

The pure-Python reimplementation so build-emergent holes/HoM/invisible-walls/
fall-through are caught with **no editor at all**. Fully specced:
board item `bsp-issue-ground-truth-detector-d0-d1` (D2 sections) + board item `bsp-issue-detector`
(D0+D1). Slice-1/1b/2/3 already prototyped (`_scratch/bspspike/`): single-box &
abutting-subtracts exact, 3/5 corpus diverge 4–8 nodes with both gaps located — port the
leaf-filter `0x32bf0`/`0x32030` and the real `SplitPolyList 0x34530`, then cleanup passes +
leaf/zone + a binary `UModel` parser (Tier-S oracle), behind the spec's budgeted Tier-S bar.
Build when prioritized; D0 doubles as its verification oracle. **Partition-heuristic gate CLOSED
2026-06-26** (`spikes/2026-06-26-bsp-partition-heuristic-from-binary.md`): `FindBestSplit`'s last
open items (the structural-splitter candidate skip + `SplitWithPlaneFast`) are decoded and
byte-verified, and a faithful reference port (incl. the slot-scan candidate selection for
GOOD/LAME) ships in that spike's `harness/find_best_split.py`. The remaining D2 work is the
`SplitPolyList` recursion + CSG filter (volume, not unknowns).
