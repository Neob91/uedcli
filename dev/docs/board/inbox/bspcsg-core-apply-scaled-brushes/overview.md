+++
priority = "p3"
kind = "implement"
summary = "bspcsg core: apply scaled brushes (port the coarse core's `MainScale`/`PostScale` math into `build_geometry_bspcsg`)"
+++

# bspcsg core: apply scaled brushes (port the coarse core's `MainScale`/`PostScale` math into `build_geometry_bspcsg`)

The default incremental core `build_geometry_bspcsg`
(`bspcsg.rs:2064`) **rejects** any non-identity-scale brush ("scaled brushes are not yet supported"),
while the older coarse `build_geometry` DOES apply scale (`_build_brush_input`, built 2026-07-19,
`board/done/`). So the bspcsg core — the default for materialize AND the base for the new
`brush intersect`/`deintersect` — cannot build any map or set containing a scaled brush. **Deferred
from the intersect/deintersect feature** (`spec.md`
§6) with this as the tracking item, per Andrzej ("if we defer scale, we need a prioritized board
item"). Cross-cutting: also gates bspcsg materialize of real (scaled) DX maps. Scope: apply the linear
part `L = PostScale·R·MainScale` to the brush polys where the coarse core already does, drop the
`bspcsg.rs:2064` reject, add a scaled-vs-explicit differential test (mirror `test_native_scale.py`).
(Andrzej, 2026-07-24.)

**Update 2026-08-24 (`unify-transform-application-logic-into-one-home`):** the user-facing gap is
RESOLVED via Option A — `brush intersect`/`deintersect` now bake `L = PostScale·R·MainScale` into the
brush's `rot` matrix (`brush_marshal._build_brush_input`) and pass an identity `scale` tuple, so
`build_geometry_bspcsg` applies the full transform via `FPoly::transform` and its scale-tuple reject
never fires. Scaled/mirrored/sheared brushes build today. This item is no longer blocking any feature —
it now covers only the internal nicety of the core applying a `scale` tuple DIRECTLY (Option B).
Downgraded to p3.
