+++
priority = "p2"
kind = "implement"
summary = "Unify transform-application logic into one double-precision apply"
+++

# Unify transform-application logic into one home

Owner ask (2026-08-23): a single home for the brush transform application. Behavior-preserving
refactor; standardize on double precision and drop the now-vestigial f32 (owner call, 2026-08-23).

`L = PostScale·R·MainScale` is applied to brush geometry in three places that share only the matrix
(`rotation.actor_linear`), re-implementing the rules (mirror winding-flip, covariant `(L⁻¹)ᵀ`
texture axes, degenerate-scale rejection) each time:

| Consumer | Impl | Output |
|---|---|---|
| `brush apply-transform` | `transform.bake` | new T3D actor (verts baked, fields reset) |
| `brush intersect`/`deintersect`, `level preview --native` | `native/brush_marshal._build_brush_input` | Rust `BrushTuple` |
| `actor bbox`, `find --within-bbox`, wire preview | `rotation.world_vertices` | world vertices |

`brush_marshal` still bakes in **f32** (`_pointxform_f32`) — an editor-byte-parity requirement that
existed ONLY for the native materialize build, now removed (`remove-native-materialize`). The
surviving consumers (draft preview, the CSG boolean verbs) never needed editor parity, so f32 is
vestigial.

**Preview gets geometry transforms for free** (owner call, 2026-08-23). `level preview --native`
carries its OWN rotation-only marshaller (`preview_native._marshal_brush`) plus `_reject_scaled`,
separate from `_build_brush_input`. Collapsing preview onto the unified marshaller and deleting
`_reject_scaled` makes scaled/mirrored brushes RENDER instead of exit-2 — this is Option A (bake `L`
in Python). Scope: GEOMETRY only. Preview's `world_uv_frame` stays rotation-only, so textures slide
on scaled faces until the covariant-UV follow-on (`render-the-full-transform-stack-in-the-textured`);
that item narrows to UV + `--faces textured` + DrawScale. Option B (Rust core applies scale) remains
a later refactor that would move the apply into the core and retire the Python bake.

`brush intersect`/`deintersect` likewise gain transformed-brush support through the shared bake
(owner steer 2026-08-23) — lifting `brushcsg.check_unscaled`. That gives `_build_brush_input`'s
covariant axes + mirror ring-reverse their live consumers, so both are KEPT (converted to double),
not stripped. The intersect half may gate on `bspcsg-core-apply-scaled-brushes` — verify whether
`intersect_brushset` applies the `rot` linear map before building it (see `spec.md`).

Two apparent blockers dissolved on inspection: **PrePivot** is per-consumer glue, not a shared rule
(`bake` folds+resets it; `world_vertices` subtracts it — different jobs, both correct); **Option B**
(`bspcsg-core-apply-scaled-brushes`) is orthogonal — this refactor changes no behavior and does not
depend on it.

See `spec.md`, `plan.md`.

## Refs
- Creates the shared home on top of `native/brush_marshal.py` (from `remove-native-materialize`).
- `render-the-full-transform-stack-in-the-textured`, `bspcsg-core-apply-scaled-brushes`.
