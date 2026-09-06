+++
priority = "p3"
kind = "debug"
summary = "The Rust CSG core writes `brush_marshal`'s per-brush texture dedup ordinal into `BspSurf.texture_ref`, a field whose engine meaning is a `UTexture*`; only the assembly patch makes it valid, so any other consumer of a freshly built world Model reads a bogus object ref."
+++

# The CSG core stores a texture dedup ordinal in `BspSurf.texture_ref`

`brush_marshal` marshals each poly's texture as a per-brush dedup ordinal (0, 1, 2 … in
first-appearance order) so `bsp_validate_brush_links` can answer "same texture?". `alloc_surf`
(`uedcli-native/src/bspcsg.rs`) then copies that ordinal into `BspSurf.texture_ref` — the slot the
engine reads as a `UTexture*` object ref.

`unbuilt._patch_native_surf_refs` now overwrites the slot for every surf, so the shipped package is
correct (the fix for `unatco-n-29-world-model2-vert-rings-reference`). But the model is only valid
AFTER that patch: any other consumer of `materialize.build_world_model`'s output reads an ordinal as
an object ref. `native/pathplace.py` serializes exactly such a model into the path placer — inert
today because the placer reads no textures.

The source-level fix is a separate `tex_id` field on the Rust `FPoly`/`BspSurf` for link/merge
identity, leaving `texture_ref` at 0 out of the core. Note that the current regression
`uedcli/tests/test_native_surf_texture_ref.py` asserts the core leaves a non-zero value in the slot
— that assertion is the thing this item would retire.
