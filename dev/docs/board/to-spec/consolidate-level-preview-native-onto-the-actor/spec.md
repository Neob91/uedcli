# Spec — consolidate the offline preview onto one renderer

Status: full spec; owner rulings recorded. **Two points are gated on the running spike**
`2026-08-05-perspective-in-preview-py` (perspective feasibility in `preview.py`, and whole-level
pure-Python perf) — see "Spike gate". Requested by the owner 2026-08-05. File:line anchors vs
`master`. Ephemeral (`CLAUDE.md`): on build, fold into `architecture.md` "Preview internals", the
`actor-preview-parity` `direction/` home, and `docs/usage.md`, then delete this file.

## Decisions (2026-08-05, owner)

- **One shared renderer; add perspective to `preview.py`.** `level preview` (offline) is wired to the
  SAME render path `actor preview` uses. `render.rs` + the camera/scene half of `preview_native.py`
  retire.
- **Ship pure-Python; a Rust rasterizer is a planned separate follow-on**
  (`rust-rasterizer-for-the-consolidated-offline`), not a gate.
- **Missing texture = batch-report then refuse** (collect all undecodable surviving-surface refs,
  exit 2 once naming the set). Closes `level-preview-native-checkerboards`.
- **CLI flag name** is the one open owner question — `questions/offline-tier-flag-name.md`.

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
and UV (divide by w), where ortho uses the affine on-plane solve; this is the part the spike proves
fits cleanly (see gate). Both projections feed one z-buffer and one texture/shade path.

### 2. Where each verb plugs in

Both verbs build the same `PreviewData` and call one renderer with a projection:

- `actor preview` (`render_actors_to_out`): unchanged except it passes `OrthoProjection` per pane
  (quad = four; single/breakdown as today). No behaviour change; goldens must stay byte-identical.
- `level preview` (offline): a new branch in `_level_preview` builds `PreviewData` over **all** the
  level's actors with `--faces textured` semantics (the solve), then renders one PNG per
  `ResolvedShot` with a `PerspectiveProjection(shot.eye, basis(shot.pitch,shot.yaw), fov, near,
  size)`. It replaces the `render_shots` import; `preview_shots`/pose resolution and the `--out-dir`/
  `--size`/`--fov`/`--list-actors`-free arg surface (`level.py:453–553`) stay.

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

## Spike gate (`dev/docs/spikes/2026-08-05-perspective-in-preview-py`)

Two assumptions the spec rests on are being measured before build:

1. **Perspective fits `preview.py` cleanly** — the near-clip + perspective-correct interpolation is a
   localized addition to the fill, not an invasive rewrite. If the spike finds it invasive, revisit
   the seam (§1).
2. **Whole-level pure-Python rasterization is acceptable** — the perf ruling ("ship pure-Python")
   assumes a whole retail level renders in single-digit seconds/frame. If the spike measures tens of
   seconds+, escalate: either pull the Rust-rasterizer follow-on forward, or reconsider.

Fold the spike's numbers into this spec before it leaves `to-plan`.

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
