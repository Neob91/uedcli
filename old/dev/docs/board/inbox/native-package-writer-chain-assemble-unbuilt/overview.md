+++
priority = "p1"
kind = "implement"
summary = "native package writer chain (assemble/unbuilt/level_write/pkgref) has no offline test coverage"
+++

# native package writer chain has no offline test coverage

`native/assemble.py` (365), `native/unbuilt.py` (260), `native/level_write.py` (81),
`native/pkgref.py` (217) — no test file imports any of them; only comment mentions exist. This is the
binary-format writer behind `level materialize`'s native path (name/import/export tables, `ULevel`
body, actor bodies, brush polys, texture/class import resolution) — the highest-risk "writes" tier.

Silent failure modes with no net:

- `assemble._patch_surf_refs` / `_patch_light_refs` / `_patch_zone_refs` — an off-by-one mis-links
  every surf texture, light, or zone in the package.
- `pkgref.Resolver` / `build_class_package_index` / `build_texture_group_index` — wrong resolution
  yields a package that fails to load in-editor ("Can't find Texture in file").
- `level_write.write_level_body` — the documented byte layout (`TTransArray`, `FURL`, `ModelRef`,
  `ReachSpecs`, 16 trailing obj-refs) has no regression pin.
- `unbuilt.assemble_unbuilt` — ambiguous-texture resolution and the `_fpolys` degenerate-poly guard,
  documented as load-bearing against retail maps, untested.

All offline `test_materialize_verb.py` / `test_apply.py` monkeypatch `_materialize` to a no-op; the
one real-path test is `@pytest.mark.integration`, skipped by default. The Rust CSG differential
(`test_csg_native_differential.py`) serializes via a DIFFERENT path (`serialize_model`), so it
doesn't cover this ~1,000-line seam.

Fix: offline golden tests over each writer (byte-layout goldens + ref-patch unit tests). Relates to
active WIP on branch `materialize-native-writer`.
