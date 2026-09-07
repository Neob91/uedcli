+++
priority = "p2"
kind = "bug"
status = "fixed"
summary = "native textured photo cannot resolve mesh skin package though utx exists in substrate"
+++

# native textured photo cannot resolve mesh skin package though utx exists in substrate

FIXED. `level photo --native --faces textured` and `class preview` decoded mesh skins via
`ClassIndex.package_paths()` (the `.u`-only code-package set), so a skin in a `.utx`
(`Effects.BioCell_SFX`) raised "no package named 'Effects' on the composed search path" even though
`Effects.utx` is on the full composed path (world surfaces resolve against it fine).

Fix: `meshrender.resolve_skins` now takes the FULL composed `search_files` (superset of
`package_paths` — both filter the same `composed_search_files`), threaded from
`preview_native.build_scene` and via a new mockable `resources.mesh_search_files` seam for
`class preview`. Regression: `test_preview_native.py::test_mesh_skins_resolve_over_full_search_files_not_u_only`.

Also widened the skin resolver with the `class_index` so a procedural skin (an `Engine.Texture`
descendant) resolves to `no-mip-data` and renders as solid RED (owner ruling), not a hard-fail.
Distinct follow-up — real procedural rendering: `native-draft-rasterizer-procedural-mesh-skins`.
