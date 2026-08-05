# Pre-spec — consolidate `level preview --native` onto the `actor preview` renderer

Status: decisions recorded (2026-08-05); ready for spec review. Requested by the owner 2026-08-05:
merge the two offline renderers, **keep `actor preview`'s logic, ditch `level preview --native`'s**
(it's buggy). File:line anchors are against `master`.

## Decisions (2026-08-05, owner)

- **Projection = one shared renderer, perspective added to `preview.py`.** Add a perspective camera +
  the SHOT pose grammar to `preview.py`, and wire `level preview --native` to the SAME render path
  `actor preview` uses — one renderer serves both verbs, not two implementations. `render.rs` and the
  camera/scene half of `preview_native.py` retire. (Option (a) below, plus the explicit "share the
  rendering logic" constraint.)
- **Perf = ship pure-Python now; Rust rasterizer refactor is a planned, separate follow-on.** The
  consolidated whole-level tier ships on `preview.py` even if slower over a whole level; it is NOT
  gated on a speed lever. The planned Rust rasterizer is filed as
  `rust-rasterizer-for-the-consolidated-offline` (depends on this landing first).
- **Missing texture = batch-report then refuse.** Collect ALL surviving-surface refs that don't
  decode across the whole level, exit 2 once naming the set (the `conventions.md` batch rule) — no
  checkerboard, no silent exit 0. Closes `level-preview-native-checkerboards`.

The three sections below (fork + dependent decisions 1–2) are the analysis these rulings resolve;
kept for the mechanism, not still open.

## What "the two offline renderers" are

uedcli has three preview paths. Only the two OFFLINE ones are in scope; `--game` is untouched.

| Path | Verb | Renderer | Projection | CSG core |
|---------------------------|-------------------------|-----------------------------|-----------------------|--------------------------------|
| KEEP | `actor preview` (+ `stash`/`prefab preview`) | `preview.py` (pure-Python stdlib) | **orthographic** panes | **faithful** `build_geometry_bspcsg` |
| RETIRE | `level preview --native` | Rust `render.rs` | **perspective**, posed | **coarse** `build_geometry` |
| out of scope | `level preview` (`--game`, default) | real engine screenshot | perspective | real editor CSG |

## Current wiring (file:line)

**KEEP path.** `cli/commands/actor/preview.py:run` (23) → `rendering.render_actors_to_out`
(`cli/rendering.py:360`) → `preview.render_quad_pgm` (`preview.py:430`) / `render_brushes_pgm` (420).
`--faces textured` runs the CSG solve at `cli/rendering.py:702`
(`preview_native.solve_world_surfaces` → Rust `build_geometry_bspcsg`), then rasterizes the surviving
surfaces **in Python** via `preview._solved_scene` (`preview.py:1882`). Projection is strictly
orthographic (`preview.py:409` `_project`, top/front/side/iso); there is **no** perspective, camera,
fov, or basis code anywhere in `preview.py`.

**RETIRE path.** `cli/commands/level.py:_level_preview` (423), native branch (537–553) →
`preview_native.render_shots` (`preview_native.py:453`) → `build_scene` (321, Rust coarse
`build_geometry`) → `uedcli_native.render_frame` (the Rust `render.rs` rasterizer). Perspective camera
`camera_basis` (`preview_native.py:288`), `--fov` (`DEFAULT_FOV` 43), SHOT pose grammar
(`preview_shots.parse_shot`: `at:/rot:/look:/orbit:`), near-plane clip, z-buffer, key-light shading
(`render.rs:54`), checkerboard-on-missing-texture (`preview_native._checkerboard` 239).

**Already shared.** Both paths live in `preview_native.py` and the one Rust crate
(`uedcli-native/`), but call **different** CSG entry functions — the KEEP path the faithful
`build_geometry_bspcsg` (`bspcsg.rs`), the RETIRE path the coarse `build_geometry`
(`csg.rs`/`build.rs`). The Rust rasterizer `render.rs` / `render_frame` is used by `level preview
--native` **only** (`render::render` called only at `lib.rs:414`; the `render_frame` binding only at
`preview_native.py:482` ← `level.py:545`).

## The central fork — projection (DECIDED: option (a) + shared renderer)

`preview.py` is orthographic; `level preview --native` is freely-posed perspective. "Keep actor
preview's logic" is therefore not a drop-in swap. Three futures were on the table; the owner chose
**(a)**, with `level preview --native` wired to the same render path `actor preview` uses:

- **(a) Teach `preview.py` a perspective camera** + the SHOT pose grammar, so the offline
  `level preview` tier keeps posed whole-level perspective shots drawn by `preview.py`. Most work
  (new projection path + per-pixel perspective divide + near clip + pose resolution in Python);
  preserves every current capability and kills every render bug. Optionally also exposes a perspective
  mode to `actor preview` itself (a bonus capability — flag as a sub-decision, not required).
- **(b) Offline tier becomes orthographic-only.** Drop posed perspective offline; whole-level offline
  renders in `preview.py`'s top/front/side/iso. Perspective stays only in `--game`. Much less work;
  a real capability loss.
- **(c) Delete `--native` entirely.** No offline whole-level tier; whole-level offline is
  `actor preview <all-names>` (ortho), perspective is `--game` only. Deletes the most code.

## What retiring `render.rs` removes — the same under every option

The map shows a **clean split** (independent of the fork):

- **KEEP in `preview_native.py`** (used by `actor preview --faces textured`, and `actor_aim_point`
  also by `preview_game.py:615/644`): `solve_world_surfaces` (400), `_marshal_brush` (113),
  `_node_polys` (185), `_reject_scaled` (88), `_mover_actor_world_polys` (205), `SolvedWorld`/
  `SolvedSurface` (392/381), `actor_aim_point` (301).
- **DROP from `preview_native.py`** (only `level preview --native`): `render_shots` (453),
  `build_scene` (321), `camera_basis` (288), `_TextureTable`/`_checkerboard` (250/239),
  `_mover_world_polys` (225), the render constants (38–44).
- **DROP from Rust** (`uedcli-native/src/`): `render.rs` (444 lines, whole file), the `render_frame`
  binding + `RenderPolyTuple` (`lib.rs:347–416`), `mod render` (`lib.rs:23`), its registration
  (`lib.rs:510`). `render.rs` is self-contained — it imports only `crate::model::Vec3` and nothing
  but `lib.rs` imports it, so this deletes cleanly with every CSG entry intact.
- **DO NOT remove** the coarse Rust `build_geometry` (`lib.rs:204`): besides `build_scene` it is a
  byte-identity pin for `native/materialize.py` core="coarse" (`materialize.py:807,828`). Only its
  `preview_native` caller goes.

So the deletion surface is well-bounded. The design work is entirely in what REPLACES the perspective
render (the fork), not in the removal.

## Dependent decisions (each its own question or a spec §)

1. **Whole-level Python-rasterizer perf** — DECIDED: ship pure-Python; the Rust rasterizer is a
   planned follow-on (`rust-rasterizer-for-the-consolidated-offline`), not a gate. The CSG carve
   (~8 s, `native-preview-perf…`) is the *shared* core and unchanged by this.
2. **Missing-texture strictness** — DECIDED: batch-report then refuse (collect all missing refs,
   exit 2 once naming the set). Closes `level-preview-native-checkerboards`.
3. **CSG-core upgrade is automatic and desirable.** Moving the offline tier onto
   `build_geometry_bspcsg` (the faithful core) is what fixes `native-preview-mis-renders-overlapping`
   (p1 doorway magenta) — the coarse core's defect. Confirm the offline tier adopts the faithful
   core. Ties to `actor-preview-bspcsg-starts-from-an-empty-world` (the shared core's empty-vs-solid
   seed) and `actor-preview-faces-textured-does-not-sort-the` (CSG-order sort) — both then apply to
   the level tier too, uniformly.
4. **Draft-fidelity rules.** `--native` renders masked/translucent/portal faces opaque as a "draft";
   `preview.py --faces textured` has its own model. Consolidation should state one rule for the
   offline tier (likely: adopt actor-preview's, drop the draft opacity shortcut).
5. **CLI surface.** Under (c), `level preview --native` (the flag) is deleted; whole-level offline
   becomes `actor preview` over the level's actors. Under (a)/(b), `--native` survives as the offline
   backend flag but now points at `preview.py`. Decide the verb/flag shape, and whether the SHOT
   grammar stays (meaningful only under (a)).

## What each option closes on the board

- Under **(a)**: closes/moots the whole native-render bug cluster (see `overview.md`) — the
  rasterizer bugs vanish with `render.rs`, the doorway bug with the core swap — while keeping every
  capability. Biggest build.
- Under **(b)/(c)**: same bug closure PLUS a large code deletion (`render.rs`, the camera/scene half
  of `preview_native.py`), at the cost of offline perspective.

## Edge cases the real spec must cover

- Retiring `render.rs` must leave `actor preview --faces textured` byte-identical (its rasterization
  never touched `render.rs`) — pin it.
- `preview_game.py`'s use of `actor_aim_point`/`NativePreviewError` must survive the `preview_native`
  trim.
- Under (a): near-clip/degenerate-pose handling in Python; a whole-level frame must not NaN on a
  back-only subtract face; movers (drawn by `_mover_actor_world_polys`) must compose under the new
  projection.
- The coarse `build_geometry` stays for materialize; a test must prove it is still reachable after
  the `preview_native` caller is removed.

## Tests the real spec must add

- `actor preview` (all `--faces`) goldens byte-unchanged by the `render.rs` removal.
- Whichever option: a whole-level offline render regression on a fixture with a doorway (proves the
  faithful core fixed the magenta), a concave face (proves scanline fill), and a revolve brush
  (proves `level-preview-native-renders-no-revolve-brush` is gone).
- A `build_geometry` (coarse) reachability/identity test independent of `preview_native`.

## Sequencing / dependencies

- Independent of the unified-asset-catalog work.
- If the perf answer needs it, gated behind `make-actor-preview-faster`.
- On build, the durable outcome folds into `architecture.md` "Preview internals" and the
  `actor-preview-parity` `direction/` home (`actor-preview-parity-direction-home`), extended to the
  offline `level preview` tier; `docs/usage.md` `level preview` section updated. (Owner approval
  required for any `direction/` or `docs/leveldesign/` edit.)
