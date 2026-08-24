+++
priority = "p2"
kind = "implement"
summary = "Unify transform-application logic into one double-precision apply"
+++

# Unify transform-application logic into one home

Built 2026-08-24. One double-precision apply for `L = PostScale·R·MainScale`: shared helpers
`apply_linear`/`flip_winding`/`covariant_axes`/`reject_degenerate` in `transform.py`, consumed by
`transform.bake`, `rotation.world_vertices`, and `native/brush_marshal._build_brush_input`. Dropped the
vestigial f32 machinery. `level preview --native` and `brush intersect`/`deintersect` now build
scaled/mirrored/sheared brushes (Option A — bake `L` into the Rust `rot`); a non-invertible scale exits
2 naming the brush. Reviewed 2× (fable). Covariant UV in preview stays a follow-on
(`render-the-full-transform-stack-in-the-textured`).

**Remnant:** the durable-design fold into `architecture.md` (and the correction of its now-stale
`preview_native._reject_scaled` line) is pending the owner's approval — `spec.md`/`plan.md` kept until
then, then deleted.
