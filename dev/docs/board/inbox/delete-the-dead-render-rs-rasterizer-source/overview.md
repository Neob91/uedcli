+++
priority = "p3"
kind = "chore"
summary = "Delete the dead render.rs rasterizer source (needs a cargo environment)"
+++

# Delete the dead render.rs rasterizer source (needs a cargo environment)

After `consolidate-level-preview-native-onto-the-actor` lands, the Rust rasterizer `render.rs` is
dead code — nothing calls it (the offline tier draws in `preview.py`; the Rust CSG solver
`build_geometry_bspcsg` stays). The consolidation build could not delete it: the build host has no
`cargo`/`rustc`, so the extension cannot be recompiled, and deleting the source without a rebuild
leaves the crate source and the pre-built `.so` inconsistent.

Do this on a machine with `cargo`: delete `uedcli-native/src/render.rs`, the `render_frame` binding +
`RenderPolyTuple` (`lib.rs:347–416`), `mod render` (`lib.rs:23`), and its registration
(`lib.rs:510`); rebuild (`maturin develop --release`); confirm the CSG entries (`build_geometry`,
`build_geometry_bspcsg`, `serialize_model`, `bake_lighting`) still build and `bin/test` is green.
`render.rs` is self-contained (imports only `crate::model::Vec3`; only `lib.rs` uses it), so the
deletion is clean.

Owner: "we'll bring it back separately" (2026-08-05).
