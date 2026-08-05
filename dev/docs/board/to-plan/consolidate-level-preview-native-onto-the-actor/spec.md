# Spec — consolidate the offline preview onto one renderer

Status: full spec; owner rulings recorded; **spike resolved** — both gated assumptions confirmed
(`2026-08-05-perspective-in-preview-py`). One open owner question (offline flag name). Requested by
the owner 2026-08-05. File:line anchors vs `master`. Ephemeral (`CLAUDE.md`): on build, fold into
`architecture.md` "Preview internals", the `actor-preview-parity` `direction/` home, and
`docs/usage.md`, then delete this file.

## Decisions (2026-08-05, owner)

- **One shared renderer; add perspective to `preview.py`.** `level preview` (offline) is wired to the
  SAME render path `actor preview` uses. `render.rs` + the camera/scene half of `preview_native.py`
  retire.
- **Ship pure-Python; a Rust rasterizer is a planned separate follow-on**
  (`rust-rasterizer-for-the-consolidated-offline`), not a gate.
- **Missing texture = batch-report then refuse** (collect all undecodable surviving-surface refs,
  exit 2 once naming the set). Closes `level-preview-native-checkerboards`.
- **CLI flag = `--offline`** (2026-08-05). `level preview --native` becomes `level preview
  --offline`; the only spelling, no alias (`conventions.md`). `--game` stays default and mutually
  exclusive; `--fov` stays gated to `--offline`.

## Goal

One offline rasterizer (`preview.py`) draws both the `actor preview` orthographic schematic AND
`level preview`'s freely-posed perspective whole-level stills. Retiring the second renderer
(`render.rs` + the `preview_native` camera/scene half) removes the divergence that caused the native
render bugs, and moving the offline level tier onto the faithful CSG core fixes the doorway defect.

## What exists today (file:line)

- `actor preview` → `cli/commands/actor/preview.py:run` (23) → `rendering.render_actors_to_out`
  (`cli/rendering.py:360`) → `preview.render_quad_pgm`/`render_brushes_pgm` (`preview.py:430`/420).
  Projection is strictly orthographic — `preview._project(v, view, iso_angle)` (`preview.py:409`),
  `view ∈ {top,front,side,iso}`. **No camera, fov, perspective, or polygon clipper anywhere in
  `preview.py`.**
- `--faces textured` resolves a resolver-free `PreviewData` (`preview.py:317`) whose `FaceData.solved`
  (`preview.py:307`) is the CSG solve from `preview_native.solve_world_surfaces` → Rust
  `build_geometry_bspcsg` (the **faithful** core), rasterized in Python by `preview._solved_scene`
  (`preview.py:1882`).
- `level preview --native` → `cli/commands/level.py:_level_preview` (423), native branch (537–553) →
  `preview_native.render_shots` (453) → `build_scene` (321, Rust **coarse** `build_geometry`) →
  `uedcli_native.render_frame` (Rust `render.rs`). Pose comes from the SHOT grammar
  (`preview_shots.parse_shot` → `ResolvedShot{eye,pitch,yaw}`, the backend-agnostic pose shape,
  `preview_shots.py:51`); camera basis `preview_native.camera_basis` (288); `--fov` default 75°.

## Design — the shared renderer

The whole pipeline **after projection** is already shared-able: CSG solve → surviving world surfaces
→ per-face scanline fill with texture + depth + key-light shade → PNG. Only the **projection** and a
**near-clip** differ between the two verbs. So:

### 1. A `Projection` seam in `preview.py`

Replace the bare `_project(v, view, iso_angle)` calls with a projection object that maps a world
vertex to `(screen_x, screen_y, depth)` and declares whether faces must be near-clipped:

- `OrthoProjection(view, iso_angle)` — today's behaviour exactly (`_project` + `_view_depth`); no
  clip; `depth = dot(world, into_screen)`. `actor preview` byte-output unchanged.
- `PerspectiveProjection(eye, basis, fov, near, size)` — NEW. `basis` from the existing
  `rotation.euler_to_matrix_uu` (the spike-pinned FRotator convention, reused from
  `preview_native.camera_basis`). Transforms world→camera, **near-clips the face polygon**
  (Sutherland–Hodgman against `z_cam = near`, the one primitive `preview.py` lacks today), perspective-
  divides, maps to pixels; `depth = camera-space z` for the z-buffer. Non-square `--size WxH` sets the
  aspect.

The scanline fill (`_fill_face`/`_fill_face_textured`, `preview.py:809`/765) consumes screen-space
polys + per-vertex depth and is reused. The new interpolation work is **perspective-correct** depth
and UV (divide by w), where ortho uses the affine on-plane solve; the spike confirmed this is a
localized fill-loop change reusing `_affine_on_plane` (see "Spike results"). Both projections feed one
z-buffer and one texture/shade path.

### 2. Where each verb plugs in

Both verbs build the same `PreviewData` and call one renderer with a projection:

- `actor preview` (`render_actors_to_out`): unchanged except it passes `OrthoProjection` per pane
  (quad = four; single/breakdown as today). No behaviour change; goldens must stay byte-identical.
- `level preview` (offline): a new branch in `_level_preview` builds `PreviewData` over **all** the
  level's actors with `--faces textured` semantics (the solve), then renders one PNG per
  `ResolvedShot` with a `PerspectiveProjection(shot.eye, basis(shot.pitch,shot.yaw), fov, near,
  size)`. It replaces the `render_shots` import; `preview_shots`/pose resolution and the `--out-dir`/
  `--size`/`--fov` arg surface (`level.py:453–553`) stay, with the tier flag renamed `--native` →
  `--offline`.

### 3. CSG core — adopt the faithful one (resolves §3)

The offline level tier moves from the coarse `build_geometry` to `solve_world_surfaces` →
`build_geometry_bspcsg`. That alone fixes `native-preview-mis-renders-overlapping` (p1 doorway
magenta — the coarse core's defect). Two shared-core items then apply to the level path uniformly and
should be honoured here, not re-littered:

- `actor-preview-faces-textured-does-not-sort-the`: sort the actor set by `(order_value, name)` before
  the solve (a trunk level has the order sidecar), so a level render matches `materialize` order.
- `actor-preview-bspcsg-starts-from-an-empty-world`: the empty-vs-solid seed. A whole level always
  contains subtracts, so the adds-only degenerate does not arise for `level preview`; note it, do not
  block on it.

### 4. Draft fidelity — adopt `actor preview`'s model (resolves §4)

Drop `--native`'s draft shortcut of rendering masked/translucent/portal faces opaque. Masked faces
already honour `TextureData.masked` (`preview.py:295`); `PF_Invisible` is dropped by both today.
State one rule: the offline level tier draws exactly what `--faces textured` draws, no separate draft
opacity. (Lighting is still out — both tiers are flat/key-light; real lighting is `--game`.)

### 5. Background / shade

Match `actor preview` parity: **black** background (the `actor-preview-parity` ruling), replacing
`--native`'s dark-grey `[56,56,60]`. Shade formula is already identical (`0.55+0.45·|N·L|`,
`preview.py`/`render.rs:54`), so shading is unchanged.

## What retires (the deletion surface — clean, per the code map)

- **`preview_native.py` DROP** (level-preview-native only): `render_shots` (453), `build_scene` (321),
  `camera_basis` (288), `_TextureTable`/`_checkerboard` (250/239), `_mover_world_polys` (225), the
  render constants (38–44).
- **`preview_native.py` KEEP** (used by `actor preview --faces textured`, and `actor_aim_point` by
  `preview_game.py:615/644`): `solve_world_surfaces` (400), `_marshal_brush` (113), `_node_polys`
  (185), `_reject_scaled` (88), `_mover_actor_world_polys` (205), `SolvedWorld`/`SolvedSurface`
  (392/381), `actor_aim_point` (301).
- **Rust DROP**: `render.rs` (whole file, 444 lines), the `render_frame` binding + `RenderPolyTuple`
  (`lib.rs:347–416`), `mod render` (`lib.rs:23`), its registration (`lib.rs:510`). Self-contained
  (imports only `crate::model::Vec3`; only `lib.rs` uses it).
- **Rust KEEP**: coarse `build_geometry` (`lib.rs:204`) — still a byte-identity pin for
  `native/materialize.py` core="coarse" (`materialize.py:807,828`); only its `preview_native` caller
  goes.

## Spike results (`dev/docs/spikes/2026-08-05-perspective-in-preview-py`, resolved 2026-08-05)

Both assumptions confirmed; the design above holds.

1. **Perspective fits `preview.py` as a localized addition.** On a planar face, `1/d`, `u/d`, `v/d`
   are affine in screen space, so `preview.py`'s existing `_affine_on_plane` solver and even-odd
   scanline fill carry over unchanged in structure. Perspective adds: a ~20-line self-contained
   near-plane Sutherland–Hodgman clip, a ~10-line camera-space transform, and a fill inner-loop change
   (one per-pixel divide + z-buffer storing `1/d`, larger = nearer). The one helper that does NOT
   carry over is `_plane_screen_probes` (`preview.py:645`) — its world-space probes can fall behind
   the near plane; the perspective path instead solves the affine maps from the CLIPPED polygon's own
   projected verts. An added mode, not a rewrite; the ortho path is untouched.
2. **Whole-level pure-Python raster is low single-digit seconds** — ~1.1 s (424 surfaces) to ~4.1 s
   (100% frame coverage) at `--size 1024`; ~25–40× slower than Rust but within the offline-draft
   budget, matching the owner's ruling. **CSG dominates, not raster** (~13.8 s CSG vs ~2.0 s raster at
   401 brushes), so retiring `render.rs` does not touch the bottleneck — consistent with
   `native-preview-perf-an-8-shot-castle-batch`.
3. **Correctness:** the Python prototype matches the Rust `render.rs` to mean-abs **0.000–0.001/255**
   across scenes (the residual is f32-vs-f64), and the near clip cross-checks exactly (behind→0 px,
   straddle→partial, front→full, mad 0.0). So the port is faithful, not an approximation.

**Caveat carried forward:** retail Deus Ex content sat behind dead `neob91` symlinks on the spike
host, so the CSG figure is on synthetic scenes and the castle's 8 s is cited, not reproduced; the
castle frame *extrapolates* to ~6–10 s @1024 at the high-overdraw end. Re-measure on real content
during build to confirm the whole-level budget; nothing in the design depends on the exact number.

## Edge cases

- `actor preview` (all `--faces`, all layouts) byte-identical after the refactor — the ortho path is
  unchanged; pin it.
- Near-clip: a face straddling the near plane clips to a valid polygon; a face entirely behind it
  emits nothing; no NaN on a back-only subtract face or a degenerate/coincident pose (`resolve_pose`
  already raises on look==eye).
- Movers (`_mover_actor_world_polys`) compose under perspective as extra world polys at base pose.
- Empty solve with world brushes present → exit 2 (existing guard); a mover/point-only level draws
  overlays over black at exit 0.
- `preview_game.py`'s `actor_aim_point`/`NativePreviewError` survive the `preview_native` trim.

## Tests

- `actor preview` goldens (wire + textured, quad/single/breakdown) byte-unchanged.
- New whole-level offline perspective goldens on a fixture exercising: a **doorway** (proves the
  faithful core killed the magenta), a **concave** face (scanline fill vs the retired triangle-fan
  bleed), a **revolve** brush (proves `level-preview-native-renders-no-revolve-brush` gone), and a
  near-plane-**straddling** face (the new clipper).
- Missing-texture: a level referencing an undecodable texture exits 2 naming the full set (batch),
  never a checkerboard.
- CSG-order: a set whose arrival order differs from `(order_value, name)` renders the sorted image.
- A `build_geometry` (coarse) reachability/identity test independent of `preview_native`.
- Perspective-correct sanity: a textured wall at a grazing angle does not swim (perspective divide,
  not affine) — compare to a `--game` reference if cheap, else a hand-checked golden.

## Sequencing / docs

- Independent of the unified-asset-catalog work; gated only on the spike's two answers.
- On build: fold into `architecture.md` "Preview internals" and the `actor-preview-parity`
  `direction/` home (`actor-preview-parity-direction-home`), extended to the offline `level preview`
  tier; update `docs/usage.md`'s `level preview` section. Owner approval required for any `direction/`
  or `docs/leveldesign/` edit.
