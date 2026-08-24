# Plan — unify transform-application logic

Steps in order. Anchors vs the `remove-native-materialize` branch.

1. **Shared helpers** (double) in `transform.py`: `apply_linear(polys, L)`, `flip_winding(L)`,
   `covariant_axes(L)`, `reject_degenerate(L, name)` (raises a typed error). Reuse `det3`/`inverse`/
   `transpose`/`matvec`; lazy-import `rotation` as `bake` does (no cycle). Unit-test each.

2. **`transform.bake`** → helpers, keeping its PrePivot fold + field reset + emit glue. `bake` still
   ALLOWS degenerate `L`; do not call `reject_degenerate` here. Output unchanged (existing bake tests green).

3. **`rotation.world_vertices`** → `apply_linear` for the matvec loop only; keep Location-add/
   PrePivot-subtract + float output + the `L is None` fast path. Measure-verb tests green.

4. **`brush_marshal._build_brush_input`** → double: vertex map = `actor_linear` passed as `rot`;
   `vec_xform_flat`/`tex_cov` = `covariant_axes`; mirror ring-reverse via `flip_winding`; degenerate/
   sheared via `reject_degenerate`. Delete `_pointxform_f32`, `_f32`, `_recip_diag`.

5. **Rewrite the coupled f32 tests** to double: `test_scaled_brush_stored_normal_bits_match_editor_
   end_to_end`, `test_pointxform_genuine_two_stage_rounding`, `test_scaled_brush_stores_authored_
   origin_as_pbase`, the C2 wiring assert, and the re-pinned covariance + mirror tests. Grep-fix f32/
   materialize comments.

6. **Preview for free**: `_marshal_brush` → thin wrapper over `_build_brush_input`; delete
   `_reject_scaled` (`preview_native.py:177,209,423`); movers via `actor_linear` + `flip_winding`.
   Translate `brush_marshal.BuildError` → `NativePreviewError` at the preview callers so degenerate/
   sheared exits 2 (no traceback). Invert the exit-2 tests to render-tests.

7. **brush intersect/deintersect** (owner steer): FIRST verify whether `intersect_brushset`
   (`bspcsg.rs`) applies the `rot` linear map. If yes: lift `brushcsg.check_unscaled`, route scaled
   brushes through `_build_brush_input`, translate `BuildError` → `BrushCsgError`, add scaled/mirror
   build tests. If it rejects a non-identity linear map: ship steps 1–6 now, file the intersect half
   as depending on `bspcsg-core-apply-scaled-brushes`.

8. **Parity test**: fixture Location=0 ∧ PrePivot=0; `bake` verts == `world_vertices` within tolerance;
   scaled-brush preview node-poly geometry == its `world_vertices` geometry (offline `uedcli_native`
   importorskip, not pixels).

9. **Verify**: `bin/test` green; run `level preview --native` on a scaled + mirrored brush (renders,
   interior correct); scaled `brush intersect` builds (if in scope).

10. **Docs/review/merge**: fold the shared-apply design into `architecture.md` (owner approval);
    delete `spec.md`/`plan.md`; narrow `render-the-full-transform-stack-in-the-textured` to UV +
    `--faces textured` + DrawScale; review per `building-features.md`; squash-merge.
