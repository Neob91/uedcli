# Spec — native mesh rendering in `level photo --native`

## Status

The mesh vertex-to-world formula is derived, RE-verified, and documented (spike
`dev/docs/spikes/2026-09-07-mesh-origin-rotorigin-transform/`, durable write-up
`dev/docs/unrealed/mesh-transform.md`; ✅ source, two independent derivations agree). The spike's
live in-game render cross-check never completed — blocked repeatedly (4 attempts total) by
shared-sandbox resource contention, not a formula issue. Owner decision (2026-09-07): proceed to
planning/implementation on RE confidence; the harness (`harness/build_test_level.sh`) stays
committed to re-run whenever the sandbox is calmer, ideally before this ships.

## Goal

Placed actors with `DrawType == DT_Mesh` and a resolved `Mesh` render in `level photo --native`
still shots, at frame 0 / rest pose, with the same skin resolution `class preview` already does in
production. Movers are excluded (they already render via their own private `Model`). Sprites
(`DT_Sprite*`) stay out of scope.

DX is the validation substrate: build against Deus Ex levels/meshes first. `uedcli/umesh.py`'s
mesh decode is already substrate-generic (Deus Ex v68 8-byte verts, stock Unreal/UT v69 packed
verts, no flag) — keep the new code substrate-agnostic the same way (no `if deusex` branches).
Validating against stock Unreal/UT99 content is tracked as its own item,
`validate-native-mesh-render-against-stock` (p2, depends on this one).

## Architecture

No `uedcli-native/src/render.rs` / FFI change. A mesh triangle is flat, so its 3 vertex+UV pairs
solve exactly for `RenderPoly`'s existing planar UV-axis representation (verified: `render.rs`
computes UV as an affine function of world position via `dot(p - uv_base, axis) + pan`, so a 2×2
solve over the triangle's in-plane component reproduces the target UVs exactly, including through
near-plane clipping) — one more thing Python computes before handing flat world-space textured
polygons to the same rasterizer that already draws world polys and mover polys.

New Python-side mesh instancing (in `uedcli/preview_native.py` or a sibling module it imports), per
qualifying actor:

1. Resolve the actor's `Mesh` (its own `Mesh=` property override if set, else the class default —
   both need reading; today's `class preview` only resolves the class default). Decode it via
   `uedcli/umesh.py` and get frame-0 triangles via **`uedcli/meshrender.py::frame_triangles`** — do
   not re-derive this: it already handles the `Mesh`-vs-`LodMesh` divergence (`Tris` vs
   `Wedges`+`Faces`), the frame-major vertex layout, and the `SpecialVerts` frame-offset trap the
   decode spike found (`frame_base = frame*FrameVerts + SpecialVerts`). **Gap**: `frame_triangles`'s
   `Tris` branch currently discards each triangle's own `PolyFlags` (the `_flags` in
   `(iv, uv, _flags, tex)`) — extend it to return that too; needed for step 4.

2. World-transform the frame-0 vertices with the verified formula (spike
   `2026-09-07-mesh-origin-rotorigin-transform`, ✅ RE-derived from `UMesh::GetFrame`, two
   independent derivations agree; live in-game cross-check still pending, see Status):

   ```
   world = Location + PrePivot + R · Ro · diag(Scale · DrawScale) · (v − Origin)
   ```

   `Origin`/`Scale` are the mesh's own fields; `Ro` is `RotOrigin` as a matrix (mesh's own local
   reorientation); `R` is the actor's `Rotation`, applied outside `Ro`; `DrawScale` is the actor's
   uniform scalar multiplying all three `Scale` axes; `Location`+`PrePivot` are added last as one
   **unrotated** offset. `R`/`Ro` both use `rotation.euler_to_matrix_uu` — no new rotation code.

   **This is NOT the brush/CSG convention** (`Location + R·(v−PrePivot)`, `architecture.md` D8,
   `PrePivot` *inside* the rotation) — do not reuse `_mover_actor_world_polys`/`actor_linear`/
   `actor_prepivot` for this step, they apply the wrong `PrePivot` convention for a mesh actor. (A
   mesh actor's `PrePivot` is `(0,0,0)` in practice unless deliberately set, so this rarely
   produces a visible divergence — but the formula above is the correct one to implement.) The
   existing thumbnail renderer (`meshrender.py::render_class`) applies `Scale` only, not `Origin`/
   `RotOrigin`/`DrawScale`/actor placement — it isn't reusable for this step either.

   Still worth reusing from the mover path: mirrored-winding detection (`flip_winding`,
   `.transform`) and degenerate-transform rejection (`reject_degenerate`) — apply them to the
   combined mesh-local+actor linear map above, same reasoning as `_mover_actor_world_polys`
   (a mirrored or degenerate transform needs the same handling regardless of which formula built it).

3. Resolve each triangle's skin by material index through **`uedcli/meshrender.py::resolve_skins`**
   (mesh `Textures[]`/`Materials[i].TextureIndex` → class `MultiSkins`/`Skin`; class wins) — this is
   already a production code path (`class preview`, `uedcli/cli/commands/classes.py`), not a spike
   harness. Per-actor `Skins[]` override is explicitly deferred — see
   `per-actor-skins-override-in-native-mesh-render` (p1).

4. Convert each triangle's raw byte UV (`FMeshUV`, 0–255) to texel units against its now-resolved
   skin texture's width/height (mirrors the conversion `meshrender.py` already does for thumbnails)
   — this must happen after step 3, since it needs the resolved texture's dimensions. Solve the
   per-triangle affine UV frame (2×2 linear solve from the 3 world vertices + 3 texel-space UV
   pairs; skip a degenerate/collinear triangle the same way `render.rs` already skips a zero-area
   world poly) and emit a `RenderPoly` per triangle into the same list and texture table world polys
   and movers already share. Set `RenderPoly.poly_flags` from the triangle's own flags — `Materials[
   material_index].PolyFlags` for a `LodMesh`, the per-triangle `FMeshTri.PolyFlags` directly for a
   plain `Mesh` (two different source fields, not one) — so the existing generic
   `light_in_front`/backface-cull logic in `render.rs` (which already consults `poly_flags` for any
   poly source) applies unchanged.

## Error handling — supersedes the existing texture-checkerboard fallback

Current behavior (`uedcli/preview_native.py::_TextureTable.index_for`, `_checkerboard`): an
unresolvable texture ref renders a magenta/black checkerboard placeholder and warns once per ref;
the shot still succeeds. **Owner ruling (2026-09-06): remove this fallback.** `level photo --native`
must always error on an unresolvable texture OR an unresolvable/undecodable mesh — naming the actor
and the offending ref, exit non-zero, no partial image. This applies to `--native` only (`--game`
is UnrealEd itself, out of scope) and reverses the prior documented decision — the reversal is
deliberate, not an oversight.

Concretely: `_TextureTable.index_for` raises instead of falling back to `_checkerboard()`; the new
mesh-instancing code raises the same way on a decode failure (`umesh.py` already refuses to guess on
an unsupported field — that exception propagates, it doesn't get caught into a placeholder) or an
unresolvable skin ref (`resolve_skins` already raises `PreviewError` naming the ref for an
undecodable one — reuse that, don't reinvent it). `_checkerboard()` and its call site are deleted,
not kept as dead code. Verified scoped: no other caller of `_TextureTable`; two existing tests assert
checkerboard behavior (`uedcli/tests/test_preview_native.py:191`, `:210`) and need updating to assert
the new error instead.

## Testing

- Unit: the mesh-local transform formula once verified (against the spike's regression test/case);
  the actor-level transform reuses `_mover_actor_world_polys`'s already-tested primitives; the
  per-triangle affine UV solve.
- Regression: the new strict-error behavior — an unresolvable texture ref and an unresolvable mesh
  ref each abort the shot with an error naming the ref (replaces the two existing checkerboard tests
  above).
- Visual: render DX levels covering decorations, items, weapons, and at least one character via
  `--native`, compare side by side against `--game` (the real in-game/UnrealEd-driven renderer) —
  correct shape, place, orientation, scale, skin. No pixel-parity requirement (`--native` is a draft
  tier, not a byte-parity target like `level materialize`). **Prerequisite to nail down in the plan**:
  which project/trunk supplies DX test levels with placed decoration/item/weapon/character mesh
  actors — this repo's own tests don't carry one.
- No `cargo test` changes needed (no Rust changes).

## Open risk (not blocking, flag during implementation)

Mesh triangle winding-order convention (CW/CCW vs UE1's) isn't yet verified against `render.rs`'s
backface cull — could render meshes invisible or inside-out. Verify empirically against a simple
decoration first. Elevated caution: the sibling pure-Python thumbnail renderer
(`meshrender.py`/`render_class`) has a **confirmed, still-open handedness/mirroring bug**
(`class-preview-mirrors-mesh-horizontally-atm`) in its own screen-space projection — a different
code path than this one (that bug is in `meshrender.py`'s own 3D→2D projection; `render.rs`'s
camera is already proven correct against BSP world geometry and movers), but it's a signal to
verify the new mesh-local triangle winding empirically rather than assume it, not to port
`meshrender.py`'s projection code.

## Follow-ups filed separately

- `per-actor-skins-override-in-native-mesh-render` (p1) — per-actor `Skins[]` override, deferred
  from v1.
- `validate-native-mesh-render-against-stock` (p2) — confirm this holds on stock Unreal/UT99
  content, not just Deus Ex.
