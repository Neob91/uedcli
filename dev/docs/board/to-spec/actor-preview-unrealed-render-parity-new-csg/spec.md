+++
status = "draft"
date = "2026-08-02"
+++

# actor preview: UnrealEd render parity — spec

Parent: this item's `overview.md` (owner ruling 2026-08-01, revised 2026-08-02). Every build decision
is now ruled (below). Ready to plan once it has a `direction/` home (see end).

## Goal

Make `actor preview` (and its `stash`/`prefab preview` siblings) render like UnrealEd's 3D viewport.
`--faces textured` becomes the **CSG-solved textured world** (UnrealEd's PlainTex, mode 6): the set is
run through the native CSG solve and only the surviving world surfaces are drawn, so an additive brush
not inside subtracted (empty) space is invisible, and every surface shows its real texture in proper
alignment. `--faces` collapses to two values, `wire` and `textured`. Every mode renders on **black**.

## Decisions (owner-ruled 2026-08-02, via widget)

- **Modes are `wire` + `textured` only.** `flat` (the CSG-colour occlusion diagram) is removed; the
  old per-brush `textured` (per-face UV fill, no solve) is removed; no `uv` variant. Known cost: the
  solid-fill occlusion `flat` gave is gone — CSG *role* still reads because `wire` keeps CSG-coloured
  outlines (add=blue, subtract=gold), but the occlusion/solidity view does not survive.
- **`textured` = the CSG-solved world**, rendered by the native **solve** half through `preview.py`'s
  orthographic pipeline (NOT `render_frame`).
- **Texture alignment is a hard requirement.** Each CSG fragment keeps its SOURCE poly's authored UV
  frame, so a texture stays continuous and aligned across BSP splits, exactly as UnrealEd draws it.
  Pinned by a UV-continuity test.
- **Non-add kinds:** all brushes drawn textured + CSG-resolved; **movers** drawn as a magenta overlay
  (a mover carries no CsgOper and is not part of the world CSG — UnrealEd's behaviour); **point
  actors** keep their sprite/marker overlay.
- **World & empty:** the selected set is solved **in isolation** against a **solid** world; a solve
  that leaves **zero surfaces** exits 2 naming the cause (never a blank frame plus a scrolling
  warning). Accepted consequence: an isolated add (not inside a subtract in the set) renders nothing.
- **Black background** for both modes; the `wire` palette is re-tuned for black.

## Current state (cite file:line)

`actor preview` renders **orthographically**, in-process, stdlib-only. `render_actors_to_out`
(`rendering.py:307`) resolves per-mode data and calls `preview.render_brushes_pgm`/`render_quad_pgm`
(`preview.py:2141`, `:2494`). The `--faces` flag (`_arguments.py:219`,
`choices=["wire","flat","textured"]`) picks the fill: **wire** (outlines only, resolves nothing, no
game content — `rendering.py:599`), **flat** (each face filled in its CSG colour through a depth
buffer, wire kept over — `_fill_face`, `preview.py:823`), **textured** (each face sampled from its own
texture/UV frame, no wire — `_fill_face_textured`, `preview.py:779`). Visibility today is a per-brush
approximation, not a solve: `_scene_geometry` (`preview.py:1867`) culls a subtract's near faces and an
add's far faces; it never hides an add by containment. Background/palettes are grey-tuned: `BG = 224`
(`preview.py:485`), `_CSG_PALETTE` (`:117`), `FRONT/BACK/DIVIDER/CAPTION/MARKER` (`:93-98`).

`level preview --native` already does the real thing on a separate, **perspective** path. `_level_preview`
(`level.py:411`, `--native` branch `:528-540`) calls `preview_native.render_shots` (`preview_native.py:360`),
which runs `build_scene` (`:300`): the CSG solve (`uedcli_native.build_geometry` → `serialize_model` →
`parse_model_body`), node-poly extraction (`_node_polys`, `:171`), a join back to each surf's SOURCE
brush poly for texture/Pan/flags (`:344-352`), Python UV frames (`world_uv_frame`), native texture
decode (`_TextureTable`, `:229`), and movers as world `extra_polys` (`_mover_world_polys`, `:191`). It
rasterizes with `render_frame` (`lib.rs:358`), a **perspective** camera. The native solve starts from a
**solid** world (`build.rs:5-6`, `:785`).

**Being removed:** `flat` and the old per-brush `textured`. **Being added:** the CSG-solved `textured`,
and the black background.

## Design

### `textured` — the CSG-solved world

Reuse the **solve**, not the renderer. Split `build_scene` into a solve half and a render half; extract
`solve_world_surfaces(actors, index, search_files) -> list[(actor, poly, world_verts)]` — the CSG build
+ `_node_polys` + source-poly join + mover `extra_polys`, taking an **ad-hoc actor list** (what
`actor preview` already holds) instead of a trunk `level`. The per-actor iteration is already the shape
`_brush_inputs`/`_mover_world_polys` use (`preview_native.py:112`, `:191`) — the change is the input
type, not the algorithm; `render_shots`/`render_frame` keep the render half unchanged. Then in
`_scene_geometry` (`preview.py:1867`), under `textured`, draw **that solved surface set** instead of each
brush's own polys. Each surface carries its source `(actor, poly)`, so the existing fill
(`_fill_face_textured`, `preview.py:779`, already `render.rs`-faithful, `:706-713`) and the
poly-index/legend annotations apply unchanged — only the SET of faces differs.

`render_frame` is rejected: it is a perspective camera, so faking `actor preview`'s orthographic
multi-view through it distorts and bypasses all of `preview.py`'s annotation/legend/highlight/focus
machinery — `textured` would become a different KIND of image from `wire`. Growing `level preview` an
actor-set input instead is rejected unless the solve-half duplication proves large: the two verbs'
inputs (posed shots vs an ortho actor set) stay genuinely different.

**Alignment (hard requirement).** A surviving surface is a BSP-split fragment of a source poly; it is
drawn through that source poly's authored UV frame (`world_uv_frame` off Origin/TextureU/TextureV/Pan),
so a texture spanning a split stays continuous — no per-fragment re-projection. A regression test must
assert UV continuity across a split (a wall cut by a subtract keeps one unbroken texture).

### Removing `flat` and the old `textured`

Per the no-back-compat convention, delete outright: drop `flat` from `_arguments.py:219` `choices` and
its help; delete the `flat` solid-CSG-fill path (`_fill_face`, `preview.py:823`) and its tests/golden;
the old per-brush `textured` fill is *replaced* by the world solve above (the `_fill_face_textured`
rasterizer is kept — the world path reuses it — but it now draws solved surfaces, not each brush's own
faces). `--faces` choices become `["wire", "textured"]`, default `wire` unchanged.

### Black background + `wire` palette re-tune

Set `BG = 0` (`preview.py:485`) so both modes render on black. Keep the CSG **hues** (add=blue,
subtract=gold, mover=magenta) and re-tune **luminance** for black — notably `FRONT/BACK` (`:94-95`): the
uncoloured path draws black FRONT lines, invisible on black, so invert to a light default; the wire
palette's obscured/back shade becomes a **dimmer** partner of the hue rather than a lighter one. Re-check
`DIVIDER/CAPTION/MARKER` (`:96-98`) and label knockout boxes for legibility on black. `_fade_dimmed`'s
fade-toward-`BG` (`:913`, `:1129`) follows `BG` automatically (a `--focus` fade now darkens toward
black — intended). Exact RGBs are a build-time visual call, blessed against the re-rendered `wire`
golden; this spec fixes the constraints, not the values.

### CLI surface

`--faces {wire,textured}` (default `wire`) on `actor preview` / `stash preview` / `prefab preview` (all
route through `render_actors_to_out`). `textured` help, e.g.:

> `textured` = the CSG-solved textured world, as UnrealEd's 3D viewport draws it: runs the native CSG
> solve over the set and fills only the surfaces that survive, each through its real texture and
> authored UV frame. An additive brush not inside subtracted space is invisible; a solve that leaves
> nothing exits 2. Needs a project, the games config, and readable textures. Use `wire` for a
> content-free schematic.

Composition: `--layout`, `--view`, `--iso-angle`, `--annotate`, `--highlight`, `--focus`, `--from-t3d`,
`--size` all apply unchanged — `textured` swaps the drawn face SET, not the framing. `--brush-colors` is
meaningless under `textured` (it samples real textures), so refuse it as the old textured did
(`_reject_explicit_brush_colors`, `rendering.py:621`). `textured` inherits the project + games-config +
readable-texture requirement (`preview_textures`, `rendering.py:689`; `preview_movers`, `:548`); `wire`
still needs no game content.

### Non-add kinds under the solve

- **Movers** — excluded from world CSG (`_brush_inputs` skips them, `preview_native.py:124`); drawn as a
  world-transformed **magenta** overlay on the solved world (`_mover_world_polys`, `:191`).
  `movers.is_mover` (schema-aware, `preview.py:341-360`) is the predicate the overlay needs — which is
  why `textured` loads the class hierarchy.
- **Semisolid / non-solid** — passed to the solve with their poly flags (`poly_flags_flat`,
  `preview_native.py:152`); their surviving faces draw textured like any other surface.
- **Point actors** — no geometry; keep the existing marker/sprite overlay (`PointRender`,
  `preview.py:268`; `_preview_point_data`, `rendering.py:749`) over the solved world.

### World & empty

The solve starts from a **solid** world (`build.rs:5-6`, `:785`), and the selected set is solved **in
isolation** — `actor preview` renders the named/`--from-t3d` set, not the whole level, so an add renders
only where the set's own subtracts carve empty space around it. A **zero-surviving-surface** solve exits
2 naming the cause (e.g. "nothing survives the solve: the set has no subtracted space; see `--faces
wire`"), never a blank frame plus a warning (`conventions.md`). `generators.md` is the precedent that
background polarity is a real per-operation choice (`intersect`=empty, `deintersect`=solid); `textured`
states **solid**.

## Edge cases & errors

- Empty actor set / empty stdin → exit 0 no-op (as `wire`, `rendering.py:345`).
- `uedcli_native` not built → exit 2 naming it (`preview_native.py:312`).
- Set with no CSG brush actors (all point/mover) → exit 2 naming the cause (tie to the zero-surface
  rule), or fall through to overlays only — the plan picks one, consistently with zero-surface.
- Unreadable texture / broken games config / outside a project → the same refusals the old textured
  used, naming the offender (`rendering.py:715-736`, `:548-596`).
- Scaled/sheared brush → the native solve rejects it (`_reject_scaled`, `preview_native.py:87`); refuse
  up front for one clean message.
- `--size` uncapped → `PreviewAbort` naming the size (`preview.py:493`), no traceback.
- Never a bare `KeyError`/`IndexError`: the solve's index joins are bounds-guarded
  (`preview_native.py:179-187`, `:344-352`).

## Tests (`bin/test`, never bare pytest — `rules/tests.md`)

- **Delete** the `flat` golden (`preview_flat_golden_iso.png`) and the old per-brush `textured` golden
  (`preview_textured_golden_iso.png`), and the `flat`/old-`textured` behaviour tests in
  `test_preview_faces.py`.
- **Re-bless the `wire` goldens** for black (`preview_wire_golden_iso.png`, `preview_wire_golden_quad.png`,
  `test_preview_faces.py:43-44`) — only after eyeballing each (`UEDCLI_BLESS_GOLDEN=1`, `:7`).
  `native_preview_golden.png` is `level preview --native`'s own renderer — untouched.
- **New `textured` world golden** over a set that carves empty space (a subtract room with an add
  inside): the add shows only where it borders empty, hidden where buried — the parity claim, byte-blessed.
- **UV-continuity test**: a wall cut by a subtract keeps one continuous, aligned texture across the
  split (the alignment requirement).
- **Zero-surface test**: an adds-only set exits 2 naming the cause.
- **Native world-parity test**: `textured`'s solved surface set matches `level preview --native`'s
  `build_scene` surfaces for the same brushes, so the two offline world solves cannot silently diverge.
- Palette-wiring tests stand (they pin classify→palette→render wiring, not literal RGBs); re-check any
  assertion hardcoding a shade rather than deriving it from `BG`.

## `direction/` home (owner action on landing — do NOT edit `direction/`)

The parity rule, the two-mode set, and the black background are durable product intent with no
`direction/` home (there is no actor-preview direction topic; `materialize.md`/`trunk-and-editor.md`
cover the build pipeline, not the preview modes). Raise a `[OWNER — confirm]` item for an approved home
when this lands. It supersedes: the 2026-08-01 "keep `textured` as the per-brush inspector" note in this
item's `overview.md`, and the grey-ground tuning assumed by board item
`four-actor-preview-faces-rulings-need-a-durable` (note it there on landing).
