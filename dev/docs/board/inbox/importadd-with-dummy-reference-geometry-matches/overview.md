+++
priority = "p3"
kind = "debug"
summary = "IMPORTADD-with-dummy reference matches native world geometry/tree on min2, but package export order + surf point-order still diverge."
+++

# IMPORTADD-with-dummy reference: geometry matches native, package structure does not

Measured on the minimal repro `min2` = {LevelInfo, Brush74, Brush132} (owner ruling 2026-09-04, the
symmetric dummy-builder convention; harness `build_ued_import_built_golden.py`).

## What matches (the fix works)

Editor `MAP IMPORTADD` with the prepended sacrificial builder brush at Actors[1] vs native
`build_world_model`:

| build                                   | nodes | surfs | leaves | verts | points | vectors |
|-----------------------------------------|-------|-------|--------|-------|--------|---------|
| native `build_world_model`              | 7     | 7     | 1      | 100   | 12     | 8       |
| editor IMPORTADD + dummy (`min2_dummy.dx`) | 7  | 7     | 1      | 100   | 12     | 8       |

Both real brushes (Brush74, Brush132) survive CSG; the dummy `DefaultBrush` is sacrificed. Before the
dummy, the editor produced **0 surfs** (Brush74 sat in Actors[1] and was dropped). `nodes`/`leaves`
are field-for-field identical (`parity_compare.compare_content`).

## Residual divergences — pre-existing native-vs-editor, NOT introduced by this change

1. **Package export-table order + counter names differ.** native (`assemble_unbuilt`) uses its
   closed-form hoist order with cameras `Camera6..11` and world model `Model2`; the editor's IMPORTADD
   save uses a different order with `Camera0..5` and `Model1`. Sizes: native 6067 B, editor 5980 B. So
   this IMPORTADD-with-dummy path does **not** byte-match `assemble_unbuilt`'s package layout — the
   2026-09-02 unbuilt-structure-parity work matched a *different* ingest path.
2. **Surf `p_base` point-array ordering differs on 4/7 surfs** (native vs golden: 2↔3, 3↔4, 4↔2,
   5↔8). Same 12 points, same tree, but the dedup order into the `points` array differs between
   native CSG and the editor's BSP. Geometry-only (independent of lighting).
3. The **dummy `DefaultBrush` actor does not byte-match**: different export-table position (native
   export 3 vs editor 9) and different surrounding refs; the editor re-serialises its own builder
   representation from the imported 2-face cube.

`i_light_map` also differs, but only because native was built lit (dark records) and the editor golden
with `--no-light`; not a real divergence.

## Scope

The owner ruling's target — symmetric world CSG so `IMPORTADD-with-dummy == native materialize` — is
met at the geometry/tree level. Full package-byte parity on this path (export order, point ordering)
is a separate axis, unfixed, owner's call whether to pursue. My change did not touch native's min2
build (no builder in the trunk; the removed `is_builder_brush` skip had 0 hits), so divergences 1-3
predate it.
[[incremental-actor-parity]]
