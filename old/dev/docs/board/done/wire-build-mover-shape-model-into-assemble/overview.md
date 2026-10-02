+++
priority = "p?"
kind = "implement"
summary = "Wire build_mover_shape_model into assemble_unbuilt (mover shape models + Polys iLink)"
+++

# Wire build_mover_shape_model into assemble_unbuilt (mover shape models + Polys iLink)

`unbuilt.build_mover_shape_model(polys)` reproduces UED22's `csgPrepMovingBrush` byte-exactly
(all 28 UNATCO import-golden mover models + their saved `Polys` iLinks; Rust
`bspcsg::build_brush_model` via the `uedcli_native` shim). `assemble_unbuilt` still writes EMPTY
mover shape models and default iLinks — the remaining ~60KB of the UNATCO byte gate.

To wire: in `_shape_model_body`/`_brush_desc`, for a MOVER (`movers.is_mover` needs a
`ClassIndex` — new plumbing into `assemble_unbuilt`) build the model, set
`none_index`/`field_0x54` (the caller already computes bbox/sphere via `_shape_bounds`), and
write the returned per-poly links into the mover's `Polys` body in place of the
`bsp_validate_brush_links` mirror used for static brushes.
