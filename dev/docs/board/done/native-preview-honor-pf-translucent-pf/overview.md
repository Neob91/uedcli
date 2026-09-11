+++
priority = "p2"
kind = "implement"
summary = "native preview: honor PF_Translucent / PF_Modulated (blended transparency)"
+++

# native preview: honor `PF_Translucent` / `PF_Modulated`

Done. `render.rs::render` now draws opaque faces first, then translucent/modulated faces
back-to-front, z-tested but not z-written: `PF_Translucent` additive, `PF_Modulated` modulate-2x.
Same fix landed in the pure-Python `class preview` rasterizer (`meshrender.py::render_class`),
replacing the skip-based stopgap from `PF_NO_OPAQUE_DRAFT` (commit c807eb32).
