# Plan — consolidate the offline preview onto one renderer

Implements [`spec.md`](spec.md) (spike-confirmed, `2026-08-05-perspective-in-preview-py`). Ephemeral
scratch — folded into `architecture.md` "Preview internals", the `actor-preview-parity` `direction/`
home, and `docs/usage.md` on build.

One offline rasterizer (`preview.py`) serves both `actor preview` (orthographic) and `level preview`
(freely-posed perspective, whole level). The Rust `render.rs` + the camera/scene half of
`preview_native.py` retire. `level preview` defaults to offline; `--game` opts into the faithful tier.

## Build order (each step compiles + `bin/test` green before the next)

1. **`preview.py` — extract a `Projection` seam, NO behaviour change.** Route the existing ortho
   draws through an `OrthoProjection(view, iso_angle)` object wrapping `_project` (409) + `_view_depth`
   (422); the fill (`_fill_face`/`_fill_face_textured`) takes the projection instead of a bare `view`.
   Pure refactor: every `actor preview` golden (wire + textured, quad/single/breakdown) stays
   **byte-identical** — that is the step's whole test. This isolates the risky feature from the move.

2. **`preview.py` — add `PerspectiveProjection` + the near-clip.** Port the spike's `proto_render.py`:
   world→camera transform from a `(pitch, yaw)` basis via `rotation.euler_to_matrix_uu` (the
   spike-pinned convention `preview_native.camera_basis` used); a self-contained near-plane
   Sutherland–Hodgman clip (`z_cam = near`, ~20 lines); perspective divide; a fill inner-loop variant
   that stores `1/d` in the z-buffer (larger = nearer) and does the per-pixel divide, solving the
   affine `u/d,v/d,1/d` maps from the **clipped** polygon's own projected verts (NOT
   `_plane_screen_probes` — its world probes can fall behind the near plane). Unit tests: the clip
   cases (behind→empty, straddle→valid poly, front→unchanged, from `clip_check.py`) and a small
   perspective golden on a hand-built solved scene, all in `preview.py`'s own test module — no
   `level preview` yet.

3. **`cli/rendering.py` — a whole-level offline render entry.** Add `render_level_shots(level, shots,
   size, fov, resources) -> list[(name, png_bytes)]`: build one `PreviewData` over **all** the level's
   actors with `--faces textured` semantics (reuse `_preview_render_data`/`solve_world_surfaces`, the
   **faithful** `build_geometry_bspcsg` core), then per `ResolvedShot` render with a
   `PerspectiveProjection`. Two spec rules live here:
   - **Missing texture = batch-refuse.** Resolve textures over ALL surviving surfaces collecting
     every undecodable ref, then exit 2 once naming the full set (extend the existing
     `preview_textures` refusal from first-miss to batch if it is not already all-or-nothing).
   - **CSG-order sort.** Sort the actor set by `(order_value, name)` before the solve for a trunk
     source (closes `actor-preview-faces-textured-does-not-sort-the`); apply the same sort to
     `actor preview`'s textured path so both match `materialize`. **Re-pin** any `actor preview`
     textured golden whose set was out of order — the only intended change to `actor preview` output.

4. **`cli/parsers/level.py` + `cli/commands/level.py` — flip the default, drop `--native`.** Parser:
   delete `--native`; keep `--game` as a plain opt-in `store_true` (no longer a mutually-exclusive
   pair). `_level_preview` (`level.py:423`): `use_game = args.game` (was `not args.native`, :435);
   invert the fov guard to "`--fov` is not valid with `--game`" (was `--fov requires --native`,
   :437–440); the `--map`/`--rebuild`/`--keep-alive`/`--list-actors` `if not use_game` guards
   (:441–464) are unchanged in effect. Replace the native branch (:537–553) `render_shots(...)` call
   with `rendering.render_level_shots(...)` + the PNG writes. Update every `level preview --native`
   test to the new surface (`level preview` default / `level preview --game`).

5. **Retire the dead renderer.** Now that nothing calls it:
   - `preview_native.py` — delete `render_shots` (453), `build_scene` (321), `camera_basis` (288),
     `_TextureTable`/`_checkerboard` (250/239), `_mover_world_polys` (225), the render constants
     (38–44). KEEP `solve_world_surfaces` (400), `_marshal_brush` (113), `_node_polys` (185),
     `_reject_scaled` (88), `_mover_actor_world_polys` (205), `SolvedWorld`/`SolvedSurface` (392/381),
     `actor_aim_point` (301, used by `preview_game.py`).
   - Rust (`uedcli-native/src/`) — delete `render.rs`, the `render_frame` binding + `RenderPolyTuple`
     (`lib.rs:347–416`), `mod render` (`lib.rs:23`), its registration (`lib.rs:510`). Rebuild the
     extension (`maturin develop --release`, via `bin/_venv.sh`/`bin/test`).
   - KEEP the coarse `build_geometry` (`lib.rs:204`) — still `native/materialize.py` core="coarse"
     (`materialize.py:807,828`). Add a test that `build_geometry` is reachable + byte-identical with
     no `preview_native` render caller.

6. **Docs (owner-approval gated).** Fold into `architecture.md` "Preview internals" — the default flip
   (`architecture.md:889` "`--game` (the DEFAULT)" becomes offline-default) and the one-renderer
   design; `docs/usage.md` `level preview` section (new default, no `--native`, `--fov` now default-
   tier); the `actor-preview-parity` `direction/` home extended to the offline `level preview` tier.
   Propose text, wait for the yes. Delete this spec + plan.

## The non-obvious traps

- **The near-clip is the one genuinely new primitive.** `preview.py` has no clipper; a face straddling
  the near plane must be split, and a face wholly behind it dropped, BEFORE the perspective divide — a
  divide on a behind-camera vertex yields garbage/NaN. Step 2's clip tests pin all three cases.
- **`_plane_screen_probes` does not carry to perspective** — solve the affine maps from the clipped
  polygon's projected verts, or a face crossing the near plane gets wrong UVs.
- **The CSG-order sort changes `actor preview` textured output** for out-of-order sets — an intended
  fix, not a regression; re-pin those goldens in step 3, keep the pure-refactor goldens (step 1)
  untouched.
- **Rust rebuild.** Deleting `render.rs` needs a `maturin` rebuild before tests pass; `bin/test`
  triggers it, a stale `.venv` extension does not.
- **Default flip is user-visible.** `level preview` with no flag no longer touches docker/the game;
  tests asserting the old default must flip, and a bare `level preview` on an undecodable-texture
  level now exits 2 (batch) instead of rendering through the engine.

## Tests (spec "Tests")

- Step 1: `actor preview` goldens byte-identical (the refactor gate).
- Step 2: near-clip unit cases + a `preview.py` perspective golden.
- Step 3: whole-level offline goldens — doorway (faithful core, no magenta), concave face (scanline,
  no fan bleed), revolve brush (`level-preview-native-renders-no-revolve-brush` gone), near-plane
  straddle; missing-texture batch exit-2 naming the set; CSG-order sorted image.
- Step 5: `build_geometry` (coarse) reachability/identity independent of `preview_native`.
- Perspective-correct sanity: a grazing textured wall does not swim.

## Subsumes / closes on build

`native-preview-mis-renders-overlapping` (p1), `level-preview-native-fills-polygons-by-triangle`,
`level-preview-native-checkerboards`, `level-preview-native-renders-no-revolve-brush`,
`native-preview-black-speckles-on-tower-roof`, most of `native-preview-post-build-review-findings`
(the `render.rs`/scene half), and `actor-preview-faces-textured-does-not-sort-the`. Verify each
against the built result before moving it to `done/`.
