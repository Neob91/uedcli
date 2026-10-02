+++
priority = "p?"
kind = "unknown"
summary = "Spiral staircase — wedge-tread + central-column redo"
+++

# Spiral staircase — wedge-tread + central-column redo

— BUILT 2026-07-22.
`builders.spiral_staircase` no longer emits rotated rectangular slabs (planks that didn't
tessellate, no column, mirrored-V in front/side). It now returns `steps+1` convex brushes: a
central `cylinder` column (radius `inner_radius`, base at z=0, full height) plus one **wedge
(pie-slice) tread** per step — a convex 6-face prism (top/bottom trapezoid + inner/outer chord + 2
radial sides), rotated `k·degrees_per_step` about Z, climbing one `rise` per step so the tread tops
ascend strictly monotonically (a single helix). Each wedge passes `validate_brush` (rotation about
Z preserves planarity/winding). `--at` anchors the column-axis base. `spiral_3`/`spiral_4` parity
goldens regenerated and moved to `OFFLINE_ONLY` (builder-sourced, dropped from the LIVE capture
suite — rotated coords make DEINTERSECTION invent vertices, same as `stair_*`). Tests in
`test_builders.py`/`test_generators.py`; decisions 2026-07-22 08:28 UTC. (Split out of the
one-actor `brush build` spec, 2026-07-21.)
