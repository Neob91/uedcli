+++
priority = "p3"
kind = "unknown"
summary = "`level preview --lit` — the scoped fast-follow (native-preview spec §8, decision 2026-07-16 12:13): consume the N-4 `bake_lighting` arrays in `render_frame` (raw dot-product lumel frame, NOT the panned texel frame — spec §8 pins the math)"
+++

# `level preview --lit` — the scoped fast-follow (native-preview spec §8, decision 2026-07-16 12:13): consume the N-4 `bake_lighting` arrays in `render_frame` (raw dot-product lumel frame, NOT the panned texel frame — spec §8 pins the math)

p3. v1 shipped flat-shaded
2026-07-16; `render_frame`'s FFI grows optional lightmap arrays.
