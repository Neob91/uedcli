# How does the CSG solve see a scaled brush — bake `L` upstream, or teach the core?

## Context

The textured/solve preview refuses scaled brushes because the Rust CSG core rejects non-identity
scale. Two ways to fix it:

- **(A) Bake `L = PostScale·R·MainScale` into the vertices in Python** before marshalling, exactly as
  `native/materialize._build_brush_input` already does (`_pointxform_f32`, mirror ring-reverse on
  `det(L)<0`). The Rust core keeps its identity-scale guard; it never sees a scale field.
  - Pro: **no Rust change, no `bin/rust-build`, works immediately**; reuses code proven in materialize.
  - Con: the core solves already-scaled geometry (fine for a preview; it's what materialize does).
  - **Recommended.**
- **(B) Make the bspcsg core apply scale** — do `bspcsg-core-apply-scaled-brushes` (Rust), then the
  marshal passes the real scale field and bakes nothing.
  - Pro: the core sees true brush geometry; one code path for scale everywhere.
  - Con: heavier; gated on that Rust item + a `bin/rust-build`; CSG on scaled/sheared geometry is the
    harder thing to get byte-right.

They are not exclusive long-term — (A) unblocks the preview now; (B) can supersede the upstream bake
later when the core learns scale. The question is which this item ships.

## Answer

<!-- Empty = open. -->
