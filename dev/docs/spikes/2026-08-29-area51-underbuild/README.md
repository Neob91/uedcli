# Area51 Entrance native under-build

Root-causes native building `15_Area51_Entrance.dx` at 9252/5547/13332 vs the editor golden's
12630/6058/17619 (bare `MAP REBUILD`, same trunk). The under-build is an over-retention +
over-carving failure in the world-CSG first 49 brushes (the entrance-room build): native keeps
early subtract-loft faces then over-carves them to 0, so the dome/entrance walls never form.

Evidence and verdict in the board item:
`dev/docs/board/inbox/native-under-builds-area51-entrance-geometry/overview.md`.

## Harness

Scripts in `harness/` (all `a51_*.py`) run from the spike dir against:
- trunk: `_scratch/geo-confirm-area51-entrance/maps/area51-entrance`
- editor golden: `_scratch/geo-confirm-area51-entrance/golden_area51.dx`

Each prints one reproducible measurement; run with the venv python and `PYTHONPATH="$UEDCLI_DIR"`.
The 18 scripts (cumgap, fixture_iso, per_brush_attr, norepart_bisect, isolate, overlap, ablate,
geom, faceprobe, goldenprobe, dome_walls, order, golden_geom, no1178mirror, progress, grid,
first20, firstbrush) isolate one angle each; see the board item for which script backs which claim.

## Current state

Counterfactual (pre/post merge fix) is conclusive: 0 of the −3378 comes from the NEAR
merge-tolerance change. Scaled-brush confound ruled out as the mechanism. The residual root
cause — the editor's per-brush subtract-face retention rule at indices 0–48 — needs a live
differential trace of UnrealEd's build, not a guess from the final golden.
