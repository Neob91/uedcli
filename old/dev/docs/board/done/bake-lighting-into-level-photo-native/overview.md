+++
priority = "p1"
kind = "implement"
summary = "level photo --native is flat-shaded; bake real lighting into the preview"
+++

# Bake lighting into level photo --native (done)

`level photo --native` now renders real per-lumel lighting on world BSP surfaces: RE'd the HSV-
style light-color/falloff formula (`dev/docs/unrealed/leveldesign/kb/lighting.md` §1.4,
`dev/docs/spikes/2026-09-11-light-color-falloff-re/`), added `light::radiance()` +
`bake_radiance` (`uedcli-native/src/light.rs`/`lib.rs`), and threaded a `Lightmap` through
`render.rs`'s rasterizer + `preview_native.py`'s `build_scene`. Conceptual RE, not byte parity
(owner ruling 2026-09-11) — `level materialize` untouched. Mesh/mover lighting scoped out, see
`mesh-mover-per-vertex-lighting-in-level-photo`. Independently reviewed (`code-review high`);
findings fixed (empty-run/dark-record bug, per-light precompute, cross-module reach, named
unpacking, redundant config reload).
