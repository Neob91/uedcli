+++
priority = "p2"
kind = "implement"
summary = "actor diagram --faces textured (was actor preview) now renders scaled/mirrored/sheared brushes, textured correctly"
+++

# actor diagram --faces textured now renders the full transform stack

Owner ask (2026-08-05): render `MainScale`/`PostScale` (`Scale`/`SheerRate`/`SheerAxis`), `PrePivot`,
`Rotation` instead of refusing, under the textured/CSG-solve preview.

Turned out mostly already done by prior work (`unify-transform-application-logic-into-one-home`,
`consolidate-level-preview-native-onto-the-actor`): the geometry solve
(`native/brush_marshal._build_brush_input`, shared by `actor diagram --faces textured`, `level photo
--native`, `brush intersect`/`deintersect`) already bakes the full `L = PostScale·R·MainScale` into
the CSG transform, and `texframe.world_uv_frame` already takes `L` covariantly for the UV frame
(shared with `brush poly align`) — so textures already followed transformed geometry everywhere
except through one stale CLI-level guard. Removed `_reject_transformed_brushes`
(`cli/rendering.py`), which refused on a since-fixed premise ("UV frame is rotation-only"). Degenerate
(non-invertible) scale still exits 2, naming the brush — the one legitimate remaining refusal, raised
by the shared marshaller. Folded into `dev/docs/architecture.md` "Preview internals" and
`docs/usage.md`; new coverage in `test_preview_faces.py`
(`test_textured_renders_scaled_sheared_and_mirrored_brushes`,
`test_textured_degenerate_scale_still_exits_2_naming_the_brush`).

Deferred: non-brush `DrawScale`/`DrawScale3D` (point-actor sprite/mesh scaling) — filed separately,
`inbox/point-actor-drawscale-drawscale3d-is-not-modeled`.
