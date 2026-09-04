# Incremental first-N-brush parity (WanChai / UNATCO / NYC_Hotel)

Owner request 2026-09-03: drive native `level materialize` to full geometry+lighting parity with
UED22 by building the first N world-CSG brushes both ways, comparing, and ramping/bisecting N to
isolate the exact brush where native first diverges — then fix, then continue.

## Tool

`harness/subset_parity.py` — level-agnostic, full geometry+lighting. Reuses the maintained
`build_ued_lit_golden` (editor golden) + `parity_compare` (native + comparison) paths, so a subset
row matches `parity_report.py`'s numbers for the same trunk+golden.

- "first N actors" = first N **world-CSG brushes** (non-brush actors don't CSG; Movers keep a private
  model the world BSP never sees). The subset keeps every non-(world-CSG-brush) actor and truncates
  the brush tail.
- `--world-only`: fast GEOMETRY probe — golden keeps Brush+LevelInfo, skips LIGHT APPLY; compares
  geometry COUNTS only. Full content+lighting parity is checked without the flag.
- Modes: `count` / `build N` / `diff N` / `bisect LO HI`. Goldens cache under
  `_scratch/subset-parity/<level>/`.

## UNATCO baseline (`03_NYC_UNATCOHQ`, whole level, native vs self-built lit golden)

nodes 6314=6314, surfs 3616=3616, leaves 762=762, vectors 599=599 — all exact. **verts +6, points
+6.** The 4701 node / 3592 surf / 734 leaf content diffs are dominated by index shifts cascading
from those +6 (node `i_vert_pool`, surf `p_base`, leaf `i_permeating`), plus a few genuine ones (one
`i_zone (2,2)` vs `(0,2)`; some non-uniform `p_base`). Lighting 94.2% records identical, shadow bits
100.00% (80/3.75M off).

So UNATCO's whole geometry gap is native over-producing 6 verts + 6 points. Isolating it via the
world-only bisect over [8,734]; N=8 is byte-identical (verts 398/398, points 88/88).

## UNATCO first divergence (world-only bisect [8,734])

N=136 clean, **N=137 first divergence**. Brush #137 = `Brush85`, a single-poly two-sided non-solid
translucent glass sheet (`PolyFlags=268`). Delta: +1 node, +16 verts, +2 points; surfs/leaves/vecs
equal. Order-independent: surf multiset identical; node-plane multiset differs by exactly ONE extra
native node at plane (0,0,1,240) — an extra Z=240 repartition split triggered by Brush85's presence
in the candidate soup, not Brush85's own plane. A `bspRepartition` split-selection divergence
(same class as the Vandenberg residual). Board: `board/inbox/unatco-first-divergent-brush-137-brush85-glass`.

## Why the ingest verbs carve different trees — ROOT CAUSE (confirmed 2026-09-04)

Not a semisolid subtlety. **UED22 excludes whatever sits in `Actors[1]` from CSG at every rebuild**
(established rule; `native/unbuilt.py:328` synthesizes a sacrificial builder there for exactly this
reason). EDIT PASTE (via MAP NEW) and native keep a throwaway builder in `Actors[1]` → all real
brushes CSG'd → 6314. Whole-file MAP IMPORT/IMPORTADD had no builder → the first real brush (Brush74)
landed in `Actors[1]` and was dropped → the defective 6270 tree. Minimal repro: editor IMPORTADD
`{Brush74,Brush132}` → 0 surfs (Brush74=Actors[1] excluded ⇒ empty); `{Brush663,Brush74,Brush132}` →
8 surfs (Brush663 sacrificed, Brush74 kept); native keeps all (7 / 14). Brushes byte-identical across
ingests (ingest does not alter geometry). Fix: reference golden must emit an explicit sacrificial
builder as `Actors[1]` (MAP NEW's builder is discarded by IMPORTADD FILE=). Full detail + fix status:
`board/inbox/ued22-world-bsp-differs-per-ingest-verb-paste`.
