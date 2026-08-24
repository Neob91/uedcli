# Spec — unify transform-application logic

Ephemeral (`CLAUDE.md`): on build, fold the durable design into `architecture.md` and delete this.
Anchors vs the `remove-native-materialize` branch (which this builds on). Reviewed 2026-08-23.

## Goal

One double-precision apply for `L = PostScale·R·MainScale` over a brush's polys, the mirror/covariant/
degenerate rules single-sourced. Side effects: `level preview --native` AND `brush intersect`/
`deintersect` render/build scaled, mirrored (and sheared) brushes instead of refusing.

## Design (what actually shares)

- **Matrix**: `rotation.actor_linear(actor)` — sole source of `L`. (already)
- **New shared helpers** (double precision), each with its true consumer set:
  - `apply_linear(polys, L)` → `v' = L·v` per poly. Consumers: `transform.bake`, `rotation.world_vertices`.
    (`_build_brush_input` does NOT use it — it passes `L` as the Rust `rot` and lets `FPoly::transform`
    apply it; keep that.) Preserve `bake`/`world_vertices` output: the `L is None` fast path, float
    output, and `world_vertices`' Location-add/PrePivot-subtract affine glue stay in the callers.
  - `covariant_axes(L)` → `(L⁻¹)ᵀ`. Consumers: `transform.bake` (texture axes), `_build_brush_input`
    (`vec_xform_flat`/`tex_cov` for the Rust surf normals). Replaces the f32 `_recip_diag`.
  - `flip_winding(L)` → `det3(L) < 0`. Consumers: `bake`, `_build_brush_input` (mirror ring-reverse),
    the mover path.
  - `reject_degenerate(L, name)` → raises a typed error when `|det3(L)| < eps`. Consumers:
    `_build_brush_input` and the preview/intersect callers. NOT `bake` — `bake` deliberately ALLOWS a
    degenerate `L` (`transform.py:242`); leave that.

## f32 → double (drop the vestige)

`_pointxform_f32`, `_f32`, `_recip_diag` in `brush_marshal.py` exist only for the removed materialize
byte-parity. Replace: the vertex transform becomes double `actor_linear` (passed as `rot`), the covariant
map becomes double `covariant_axes`; delete `_f32`. Coupled tests to rewrite (all pin the f32 bits):
`test_scaled_brush_stored_normal_bits_match_editor_end_to_end`, `test_pointxform_genuine_two_stage_rounding`,
`test_scaled_brush_stores_authored_origin_as_pbase`, the C2 wiring assert (`…[6] == _pointxform_f32`),
plus the re-pinned `_build_brush_input` covariance + mirror tests (from `remove-native-materialize`) —
switch their expectations f32→double.

## Preview + brush-intersect get transforms (geometry)

- **Preview**: collapse `preview_native._marshal_brush` onto `_build_brush_input` (thin wrapper);
  delete `_reject_scaled` and its three sites (`preview_native.py:177,209,423`); movers world-transform
  via `actor_linear` (+ `flip_winding`) instead of `actor_matrix`.
- **brush intersect/deintersect** (owner steer 2026-08-23): lift `brushcsg.check_unscaled`
  (`brushcsg.py:125`) so scaled/mirrored source brushes are accepted, routed through the SAME
  `_build_brush_input` bake. **OPEN**: whether `intersect_brushset` (the incremental `bspcsg.rs` core)
  applies the `rot` matrix like `build_geometry` does — if yes, Option A (Python bake) works with no Rust
  change; if it rejects a non-identity linear map, this half is gated on `bspcsg-core-apply-scaled-brushes`.
  Verify before building the intersect half; if gated, ship the preview half and file the intersect half.
- This gives `_build_brush_input`'s covariant axes + mirror ring-reverse their live consumers, so KEEP
  them (converted to double) — not dead machinery.

## Error plumbing (must specify — else a traceback reaches the user)

`reject_degenerate`/sheer raises `brush_marshal.BuildError`. Today nothing catches it on the preview
path (`build_scene` catches only the Rust `uedcli_native.BuildError`, `preview_native.py:343`; the
CLI guards catch `NativePreviewError`/`BrushCsgError`). So: the preview callers translate a
`brush_marshal.BuildError` into `NativePreviewError`; the intersect caller into `BrushCsgError`.
Degenerate/sheared scale must exit 2 naming the brush, never traceback.

## Out of scope

- **Covariant UV in preview** (`world_uv_frame` stays rotation-only → textures slide on scaled faces).
  Follow-on `render-the-full-transform-stack-in-the-textured` (narrow it to UV + `--faces textured` +
  DrawScale). It computes covariant UV Python-side via the new `covariant_axes` helper — it does NOT
  reuse `_build_brush_input`'s Rust-facing `vec_xform_flat`.
- **Option B** (Rust core applies scale) — later; this ships the Python bake (Option A).

## Behavior changes (intended)

- `level preview --native` / `brush intersect` on a scaled/mirrored brush: exit 2 → renders/builds.
- Marshaller output shifts f32→double (~1e-4). No surviving consumer needed f32 parity.
- `bake`, `world_vertices`: output unchanged (already double).

## Tests / verification

- **Parity**: with a fixture at Location=0 AND PrePivot=0, `bake`→`L·v` equals `world_vertices`→
  `Loc+L·(v−pp)` within tolerance (`bake` runs `emit.clean` 6-dp + grid-snap; `world_vertices` raw
  floats). The "preview renders identical" half compares EXTRACTED node-poly world geometry (not PNG
  pixels), offline via `uedcli_native` (importorskip).
- **Mirror**: pin winding on a WORLD-CSG mirrored brush (where the Rust core uses ring order), not a
  mover (the native renderer is winding-agnostic, `render.rs:55`).
- **Degenerate/sheared**: preview AND intersect exit 2 naming the brush (no traceback).
- **f32-drop**: the coupled tests above rewritten to double.
- `bin/test` green.

## Sequencing

- After `remove-native-materialize` merges (needs `native/brush_marshal.py`).
- The intersect half may gate on `bspcsg-core-apply-scaled-brushes` (verify first).
- Independent of Option B and the UV follow-on.
