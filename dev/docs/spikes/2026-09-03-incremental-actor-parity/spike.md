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
