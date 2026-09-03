---
kind: finding
---

# UNATCO first-divergent brush: #137 `Brush85` glass sheet → one extra Z=240 repartition split

Localized with the incremental first-N-brush harness
(`dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/subset_parity.py`), world-only geometry
bisect over `03_NYC_UNATCOHQ` [8,734]:

- **N=136 clean** (byte-identical geometry), **N=137 first divergence**.
- Brush #137 (trunk order, world-CSG) = `Brush85`: a single-poly `CSG_Add` **two-sided, non-solid,
  translucent glass sheet** (`PolyFlags=268` = `PF_TwoSided|PF_NotSolid|PF_Translucent`, texture
  `CoreTexGlass.WindOpacStrek_A`), world plane x≈811 normal (−1,0,0), Z span −16..80.

Delta at N=137 (native vs self-built bare-`MAP REBUILD` golden): nodes 1184 vs 1183 (**+1**), verts
17646 vs 17630 (**+16**), points 2110 vs 2108 (**+2**); surfs/leaves/vectors equal.

Order-independent diff: **surf multiset identical**; node-plane multiset differs by exactly **one**
extra native node, plane **(0,0,1,240)** — a horizontal Z=240 splitter, *not* Brush85's own plane.
So Brush85's presence in the candidate soup shifts native's `FindBestSplit`/`bspRepartition` scoring
to make one extra split at an existing Z=240 plane that the editor leaves un-split; the extra split
fragments produce the +16 verts / +2 points.

This is a `bspRepartition` split-selection divergence (same class as the Vandenberg residual thread,
[[built-parity-campaign-state]]), not two-sided-sheet mishandling in isolation — the node count is
non-monotonic across N (full repartition each build). Whole-level UNATCO net is +6 verts/+6 points
(later brushes partially cancel this first +16).

Next: disassembly-grounded characterization of *why* Brush85 as a candidate shifts the score at the
Z=240 subtree — needs the editor split trace / FindBestSplit disasm, per the HANDOFF rule (native
code is never evidence for editor behavior). Overlaps active repartition work; coordinate before
editing `bspcsg.rs` FindBestSplit.
