# Pre-spec — render the full transform stack in the textured/solve preview

Status: PRE-SPEC. Options + owner questions; nothing decided or built. File:line anchors vs `master`.
Ephemeral (`CLAUDE.md`): on build, fold into `architecture.md` "Preview internals" + `docs/usage.md`,
then delete.

## Goal

The textured/CSG-solve preview (`actor preview --faces textured`, `level preview` offline) renders a
scaled / sheared / mirrored brush instead of exiting 2. The wire and measure paths already do this;
this closes the gap for the textured tier.

## What already works vs what refuses

| Path | Scale/shear today | Where |
|-------------------------------|--------------------|-------------------------------|
| `actor preview --faces wire`, `actor bbox`, `find --within-bbox` | **renders/measures** full `Location + PostScale·R·MainScale·(v−PrePivot)` | `rotation.world_vertices`/`actor_linear` (`rotation.py:407`/285) |
| `actor preview --faces textured` | **exit 2** | `_reject_transformed_brushes` (`rendering.py:746`) + `_reject_scaled` (`preview_native.py:88`) |
| `level preview` (offline) | **exit 2** | `_reject_scaled` via the solve (`preview_native.py:423`) |
| `level materialize` (real build) | **applies** scale by baking `L` upstream | `native/materialize._build_brush_input` (`_pointxform_f32`) |

## Why the solve path refuses

1. The Rust CSG core rejects non-identity scale (`bspcsg.rs:2257`, `build.rs:792`); `_marshal_brush`
   hardcodes identity scale (`preview_native.py:149`) and leans on `_reject_scaled`.
2. The UV frame `texframe.world_uv_frame` is rotation-only, so a texture would not follow scaled/
   sheared geometry — the stated reason for `_reject_transformed_brushes` (`rendering.py:750`).

Both are already solved for the real build; the pattern is reusable.

## Design

### A. Geometry — apply `L` to the solve (the fork, `questions/geometry-scale-approach.md`)

Two ways to make the CSG solve see a scaled brush:

- **(A) Bake `L = PostScale·R·MainScale` upstream** in `_marshal_brush`, exactly as
  `native/materialize._build_brush_input` does (the f32 `_pointxform_f32` vertex map,
  `materialize.py:41`): transform vertices in Python, reverse the poly ring on `det(L)<0` (mirror),
  and keep the Rust core's identity-scale guard. **No Rust change, no cargo, works now**; reuses proven
  materialize code. Recommended.
- **(B) Make the bspcsg core apply scale** — the `bspcsg-core-apply-scaled-brushes` item (Rust change,
  needs `bin/rust-build`), then `_marshal_brush` passes real scale and drops nothing. More faithful
  (the core sees true brush geometry) but heavier and gated on that item.

### B. UV under scale/shear — covariant texture axes

Port materialize's covariant texture-axis transform (`(L⁻¹)ᵀ` for normals, `(LᵀL)⁻¹` pre-cancel for
axes, `materialize.py:614/638`) into the preview's UV frame so a texture follows the scaled geometry.
`texframe.world_uv_frame` is SHARED with `brush poly align` — extend it to take the linear map `L`
(one function, both callers stay consistent) rather than forking a scaled variant. This removes the
"rotation-only UV" reason for `_reject_transformed_brushes`.

### C. Drop the guards

Once A + B land, delete `_reject_transformed_brushes` (`rendering.py:746`) and `_reject_scaled`
(`preview_native.py:88`) and their callers; the wire/textured split at `test_preview_faces.py:677`
becomes "both render". `SheerRate`/`SheerAxis` need no special case — `actor_linear`'s `fscale_matrix`
already folds shear into `L` (`transform.py:141`).

### D. Non-brush `DrawScale`/`DrawScale3D` — scope question (`questions/drawscale-scope.md`)

Point actors' `DrawScale`/`DrawScale3D` are **not modeled at all** (no typed field in `model.py`; the
sprite footprint takes a bare `draw_scale` scalar, `preview.py:339`). Rendering them is a separate
modeling lift (parse/store typed fields + sprite/mesh footprint scaling). In scope here, or its own
item?

## Interplay with the consolidation

`consolidate-level-preview-native-onto-the-actor` (in build) changes the DRAW side (`preview.py`); the
SOLVE side (`solve_world_surfaces` → Rust core) is unchanged by it and is where scale is refused. So
this item is orthogonal to the consolidation and should sequence AFTER it lands (one renderer to fix).

## Edge cases

- Mirror (`det(L)<0`): ring reversal so faces don't invert; verify a mirrored room shows its interior.
- Degenerate scale (a zero axis → non-invertible `L`): refuse naming it (materialize already does,
  `materialize.py:609`) — this is the one legitimate remaining refusal.
- `PrePivot` is subtracted before `L` (already in `world_vertices`); the solve marshal must match.
- A whole level mixing scaled and unscaled brushes solves as one set.

## Tests

- The `test_preview_faces.py:677` refusal test inverts: textured now renders the scaled/sheared/
  mirrored set (goldens), wire unchanged.
- A scaled brush's textured render matches its `world_vertices` geometry (same `L`), and its texture
  follows (a stretched wall's texels stretch, a mirrored wall's lettering flips) — golden or a
  `--game` cross-check if cheap.
- Degenerate (zero-axis) scale still exits 2 naming it.
- Parity: a scaled brush's textured preview vs `level materialize`'s built geometry agree in shape.

## Sequencing

- After the consolidation lands. Independent of the unified-asset-catalog work.
- If the owner picks core-applies-scale (B), gated on `bspcsg-core-apply-scaled-brushes` + `bin/rust-build`.
