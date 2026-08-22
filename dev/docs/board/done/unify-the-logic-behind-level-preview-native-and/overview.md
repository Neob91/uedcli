+++
priority = "p3"
kind = "implement"
summary = "Duplicate of consolidate-level-preview-native-onto-the-actor; closed unbuilt."
+++

# Unify the logic behind level preview --native and actor preview

Duplicate. `consolidate-level-preview-native-onto-the-actor` owns this work and is further along —
it carries the owner's 2026-08-05 ruling (keep `preview.py` + `build_geometry_bspcsg`, retire
`preview_native.py`'s Rust rasterizer and the coarse `build_geometry`), a full spec, a plan, and the
spike `2026-08-05-perspective-in-preview-py` proving perspective grafts onto `preview.py`'s scanline
byte-level against `render.rs`.

Filed 2026-08-05 from the same observation, specced 2026-08-22 in a session that had not yet pulled
the parallel work. Nothing here survives that the consolidation item does not already say.
