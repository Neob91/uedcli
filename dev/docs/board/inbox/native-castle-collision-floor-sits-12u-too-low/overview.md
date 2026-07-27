+++
priority = "p1"
kind = "debug"
summary = "Native castle collision floor sits 12u too low (pawn rests z=35 vs editor z=47) — root cause RE'd 2026-07-16 to the BSP-tree IsCsg-propagation, NOT the bounds pass"
+++

# Native castle collision floor sits 12u too low (pawn rests z=35 vs editor z=47) — root cause RE'd 2026-07-16 to the BSP-tree IsCsg-propagation, NOT the bounds pass

p1. The
editor-vs-native gap reproduces exactly offline (`line_check.py` box sweep at (0,-250): editor
floor-contact z=0 on node 1152, native z=-12 on node 885 = the water-sheet plane node 15). The
z=0 stone-floor node plane EXISTS in the native tree (node 19) and `point_in_solid_world`/iLeaf
correctly call z=-2 solid — but the game's box LineCheck gates hull-testing on the IsCsg
`Outside` propagation (`if Outside: return` BEFORE the `iCollisionBound` read, per
`re-raw-zones/linecheck-oracle.md`), and that propagation produces NO solid terminal covering
z=0 at (0,-250) — an unbounded-splitter mis-flood (a far wall's plane, e.g. node 863 y=-380,
classifies the column empty and the room's own bounding faces never re-subdivide the cell). This
is the SAME mis-flood build.rs:519-561 already documents and patches for iLeaf; the patch is
impossible for collision because the game reads propagation live, not a stored field. So
`bsp_build_bounds`/`cull_parallel_planes` are faithful mirrors of the broken tree — the fix must
make the native BSP build (build_bsp_opt / csg.rs) produce a solid terminal cell for the stone
floor like the editor's node 1152 (i.e. propagation must match point_in_solid). Stopped short of
editing csg.rs per the task guardrail (it just passed render/zone parity gates) — needs
Andrzej's call on scope. Full trace in session transcript 2026-07-16.
