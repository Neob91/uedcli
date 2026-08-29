+++
priority = "p1"
kind = "finding"
summary = "native under-builds Area51 Entrance geometry far below editor golden"
+++

# native under-builds Area51 Entrance geometry far below editor golden

Found while confirming the NEAR merge-tolerance fix across 10 seeded random OG retail levels
(seed 20260828). Area51 Entrance is the lone level where native is FAR below the editor golden
— the over-fusion signature — unlike the other 9 levels where native is at or above editor.

## Measured (bare `MAP REBUILD` golden = editor's own build of the same trunk vs native)

| | nodes | surfs | points |
|---|---|---|---|
| editor golden | 12630 | 6058 | 17619 |
| native (master incl. fix) | 9252 | 5547 | 13332 |
| delta | −3378 | −511 | −4287 |

−26.7% nodes / −8.4% surfs / −24.3% points. 1343 CSG brushes.

## Why the fix is not the cause

The merge-tolerance change's measured net effect is tiny by comparison: Wanchai −2 soup polys /
−20 nodes; UNATCO control unchanged (6314/3616). Area51's −3378 is ~150x larger and is an
independent native-only under-build on this specific map. No pre-fix counterfactual was run, so
attribution is unproven — but the magnitude rules out the 0.015-NEAR tolerance as the cause.

## Direction for the spike

Plausible (unproven) confound: Area51 is the densest **scaled-brush** map of the 10-level set
(359/1343 = 27% of CSG brushes scaled, vs UNATCO 12%). Likely the native scaled-brush path
drops or misbuilds geometry here. Next step: run a pre-fix native counterfactual on Area51 to
attribute the −3378 exactly (needs a Rust checkout at the pre-merge state; no goldens re-run).
