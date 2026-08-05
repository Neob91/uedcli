+++
priority = "p2"
kind = "implement"
summary = "Render the full transform stack in the textured/solve preview"
+++

# Render the full transform stack in the textured/solve preview

Owner ask (2026-08-05): render `MainScale`/`PostScale` (`Scale`/`SheerRate`/`SheerAxis`), `PrePivot`,
`Rotation` — the whole transform — in the preview instead of refusing.

## The task is narrower than it looks — half is already done

The transform math is settled and SHIPPED for one path. `world = Location + PostScale·R·MainScale·(v
− PrePivot)` (`rotation.world_vertices`/`actor_linear`, `rotation.py:407`/285). So:

- **`actor preview --faces wire` (default) + every measure verb (`actor bbox`, `find --within-bbox`)
  already render/measure the full stack** — scale, shear, mirror, PrePivot, rotation. Nothing to do.
- **The textured/CSG-solve path REFUSES** scaled/sheared brushes — `actor preview --faces textured`
  and `level preview` (now the offline default). Two guards: `_reject_transformed_brushes`
  (`cli/rendering.py:746`, CLI) and `_reject_scaled` (`preview_native.py:88`, solve). Pinned by
  `test_preview_faces.py:677` (textured exit 2 / wire exit 0).
- **Non-brush `DrawScale`/`DrawScale3D` is not modeled at all** — no typed field; point-actor sprite
  footprint takes a `draw_scale` scalar but nothing parses/stores actor draw scale (`model.py`).

So this item = make the textured/solve path apply the transform (drop the two refusals), plus decide
whether `DrawScale` is in scope. See `spec.md` + `questions/`.

## Why the solve path refuses (the real blockers)

1. The Rust CSG core rejects non-identity scale (`bspcsg.rs:2257`, `build.rs:792`) — the item
   `bspcsg-core-apply-scaled-brushes`. `_marshal_brush` hardcodes identity scale (`preview_native.py:149`).
2. The UV frame is rotation-only (`texframe.world_uv_frame`), so a texture would not follow scaled/
   sheared geometry — the stated reason for `_reject_transformed_brushes`.

Both are already solved in the REAL build: `native/materialize._build_brush_input` bakes
`L = PostScale·R·MainScale` into the vertex map handed to Rust (`_pointxform_f32`), reverses the ring
on `det(L)<0` (mirror), and transforms texture axes covariantly `(L⁻¹)ᵀ`. This item reuses that.

## Depends on / relates

- `bspcsg-core-apply-scaled-brushes`, `native-materialize-silently-ignores-postscale` — the core/
  materialize scale gaps; one design choice here is whether to lean on them or bake scale upstream.
- `consolidate-level-preview-native-onto-the-actor` (in build) — the consolidated `preview.py` renderer
  is the draw side; this is the solve side, which is unchanged by the consolidation. Sequence after it.
