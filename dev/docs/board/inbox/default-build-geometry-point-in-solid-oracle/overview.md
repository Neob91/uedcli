+++
priority = "p1"
kind = "debug"
summary = "Default `build_geometry` (point-in-solid oracle) is IMPRACTICAL at UNATCO scale"
+++

# Default `build_geometry` (point-in-solid oracle) is IMPRACTICAL at UNATCO scale

The full 762-brush `01/03_NYC_UNATCOHQ` trunk takes **>45 min** in the default
`build::build_geometry_from_brushes` (each fragment classification replays `point_in_solid`
against every accumulated `WorldBrush` ⇒ ~O(brushes²·fragments)) — it never finished under a
45-min timeout even running alone. The OPT-IN `build_geometry_bspcsg` (BSP-growing core) builds
the SAME 762 brushes in **38 s** (nodes 6822 / surfs 3644 / points 9579 / leaves 2861) and the
full unlit materialize (assemble + self-check + write, 1.0 MB `.dx`) in **44 s**. So the byte-
identity `bspcsg` core is ALSO the only viable FUNCTIONAL path for real levels — the default
oracle path scales fine for the 95-brush castle but not a real DX map. Decision needed: route
`run_materialize_native`/`_build_level_model` (and `preview_native`) through `build_geometry_bspcsg`
once it's trusted, OR optimize the oracle (spatial index over `WorldBrush`). (Found 2026-07-17
driving the UNATCO native build.)
