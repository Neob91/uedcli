+++
status = "draft"
date = "2026-08-02"
+++

# actor preview: UnrealEd render parity — spec

Parent: `dev/docs/board/to-spec/actor-preview-unrealed-render-parity-new-csg/overview.md`
(owner ruling 2026-08-01). Draft — needs the owner gate on the four `questions/` before build.

## Goal

Give `actor preview` (and its `stash`/`prefab preview` siblings) a new `--faces` mode that renders the
brush set as UnrealEd's 3D viewport does: run the native CSG solve over the set and draw only the world
surfaces that survive, so an additive brush that is not inside subtracted (empty) space is invisible —
the parity the existing per-brush modes cannot reach because they never solve for spatial containment.
Separately, and for every `--faces` mode, replace the light-grey preview background with black and
re-tune the wire/flat palettes that were built for grey.

## Current state (cite file:line)

`actor preview` renders **orthographically**, in-process, stdlib-only. `render_actors_to_out`
(`uedcli/cli/rendering.py:307`) resolves per-mode data and calls `preview.render_brushes_pgm` /
`render_quad_pgm` (`uedcli/preview.py:2141`, `:2494`) — top/front/iso/side views, PPM bytes in memory,
PNG on the write boundary. The `--faces` flag (`uedcli/cli/parsers/_arguments.py:219`,
`choices=["wire","flat","textured"]`) picks the fill:

- **wire** — outlines only; resolves nothing, needs no game content (`_preview_render_data`,
  `rendering.py:599`, leaves `faces=None`).
- **flat** — every surviving face filled solid in its brush's CSG colour through a depth buffer, wire
  kept over it (`_fill_face`, `preview.py:823`).
- **textured** — each face filled by sampling its OWN authored texture/UV frame, no wireframe
  (`_fill_face_textured`, `preview.py:779`); the per-brush UV inspector.

Visibility today is a **per-brush** approximation, not a solve: `_scene_geometry` (`preview.py:1867`)
culls a subtract brush's near faces and an add's far faces, and `classify_brush` (`preview.py:341`)
keys the palette. It never hides an add by containment — no world solve exists on this path.

Background and palettes are tuned for grey. `BG = 224` (`preview.py:485`); `_new_buf` fills the canvas
with it (`preview.py:489`). `_CSG_PALETTE` (`preview.py:117`) gives each CSG op a (front, back) shade
pair "re-tuned for our light-grey bg" (`preview.py:104-112`); `FRONT/BACK/DIVIDER/CAPTION/MARKER`
(`preview.py:93-98`) and `_TINT_PALETTE` (`preview.py:147`) are likewise grey-tuned. `--focus` fades
toward `BG` (`_fade_dimmed`, `preview.py:913`; the blend at `preview.py:1129`).

`level preview --native` is a **separate, perspective** path. `_level_preview` (`level.py:411`; the
`--native` branch, `:528-540`) calls `preview_native.render_shots` (`preview_native.py:360`), which
runs `build_scene` (`preview_native.py:300`): the real CSG solve (`uedcli_native.build_geometry` →
`serialize_model` → `parse_model_body`), node-poly extraction (`_node_polys`, `:171`), join back to
each surf's SOURCE brush poly for texture/Pan/flags (`build_scene`, `:344-352`), Python-side UV frames
(`world_uv_frame`), native texture decode (`_TextureTable`, `:229`), and movers rendered as world
`extra_polys` (`_mover_world_polys`, `:191`). It then rasterizes each posed SHOT with
`uedcli_native.render_frame` (`lib.rs:358`) — a **perspective camera** `(location, forward, right, up,
fov_deg)`, PNG per shot. So a native textured world render already exists offline; its inputs are a
trunk level plus freely-posed camera shots, not an ad-hoc actor set and not orthographic views.

The native solve starts from a **solid** world: `build.rs:5-6` and `:785`
(`root_outside=false`, "a DX level is solid; Subtract carves"). Surviving surfaces are solid↔empty
boundaries only.

**New in this item:** the CSG-solved `--faces` value (all else on the ortho path is reused), and the
black background + palette re-tune across all modes.

## Design

### The new mode

Reuse the SOLVE, not the renderer. `preview_native.build_scene` already turns brushes into
world-space, textured, CSG-**solved** surface polys; `render_frame` is a separate perspective
rasterizer. The new mode wants the surviving surfaces drawn through `actor preview`'s existing
**orthographic** pipeline — same top/front/iso/side framing, quad layout, legend, `--annotate`,
`--highlight`, `--focus`, and the black bg below — because that framing (not a posed shot) is what
distinguishes `actor preview` from `level preview`. Concretely:

1. Split `build_scene` into a solve half and a render half. Extract
   `solve_world_surfaces(actors, index, search_files) -> list[(actor, poly, world_verts)]`: the CSG
   build + `_node_polys` + source-poly join + mover `extra_polys`, taking an **ad-hoc actor list**
   (what `actor preview` already holds) instead of a trunk `level`. The per-actor iteration is already
   the shape `_brush_inputs`/`_mover_world_polys` use (`preview_native.py:112`, `:191`) — the change is
   the input type, not the algorithm. `render_shots`/`render_frame` keep the render half unchanged.
2. In `_scene_geometry` (`preview.py:1867`), under the new mode, draw **that solved surface set**
   instead of each brush's own polys. Each surviving surface carries its source `(actor, poly)`, so the
   existing textured fill (`_fill_face_textured`, `preview.py:779`, which already matches `render.rs`
   shade-for-shade, `preview.py:706-713`) and the poly-index / legend annotations apply unchanged — a
   surface is drawn exactly as `textured` draws its owning poly today, only the SET of faces differs.

**World-render-path options (see `questions/world-render-path.md`).** The question frames it as
(a) `actor preview --faces world` calls a shared native path re-targeted at the actor set, vs (b)
`level preview` grows an actor-set input and `--faces world` is sugar over it. Recommend **(a)**, and
within (a) reuse only `build_scene`'s solve half as above — **not** `render_frame`:

- *Reuse `render_frame` (the perspective renderer).* Cost: `render_frame` is a perspective camera;
  `actor preview` is orthographic multi-view. Faking ortho with a distant camera + narrow FOV is
  approximate and distorts, and it bypasses all of `preview.py`'s annotation/legend/highlight/focus
  machinery — so `--faces world` would produce a different KIND of image from `wire`/`flat`/`textured`,
  breaking the one-verb/four-consistent-modes model. High cost, poor fit.
- *Reuse the solve half, render through `preview.py` (recommended).* Cost: the `build_scene` refactor
  above (extract a `level`-free solve entry), plus one branch in `_scene_geometry`. Modest, and it
  keeps `--faces world` framed and annotated exactly like the other three modes. Option (b) is
  rejected unless measurement shows the solve-half duplication is large — the two verbs' inputs
  (posed shots vs an ortho actor set) stay genuinely different.

### CLI surface

New `--faces` value on `actor preview` / `stash preview` / `prefab preview` (all route through
`render_actors_to_out`). Recommended name **`world`** — reads as "the built world" against the
per-brush `flat`/`textured`; **defer to `questions/mode-name.md`** (alternatives `solid`/`csg`/`built`).
Add it to `choices` at `_arguments.py:219` and to the `--faces` `help=`, e.g.:

> `world` = the CSG-solved world: runs the native solve over the set (as UnrealEd's 3D viewport does)
> and draws only the surfaces that survive, so an additive brush not inside subtracted space is
> invisible. Needs the same project + games config + readable textures as `textured` (it decodes real
> textures); a solve over an additive-only set can render empty — see `--faces textured` to inspect
> brushes in isolation.

Composition: `--layout` (quad/single/breakdown), `--view`, `--iso-angle`, `--annotate`, `--highlight`,
`--focus`, `--from-t3d`, `--size` all apply unchanged — `world` swaps the drawn face SET, not the
framing. `--brush-colors` is meaningless under `world` (it samples real textures, like `textured`), so
refuse it the same way `textured` does (`_reject_explicit_brush_colors`, `rendering.py:621`).

Empty stdin stays a clean no-op (exit 0), as `wire` is (`rendering.py:345`). A degenerate/unsolvable
set exits 2 naming the cause (native `BuildError` → `NativePreviewError` → `CommandError`; the
`uedcli_native`-not-built and no-CSG-brush cases already do this at `preview_native.py:312`, `:317`).
No Python traceback reaches the user (`conventions.md`; the existing `PreviewAbort`/`NativePreviewError`
seams cover it). A zero-surviving-surface solve is the open question below.

### Black background + palette re-tune (all `--faces` modes)

Set `BG = 0` (`preview.py:485`) so every mode — `wire`, `flat`, `textured`, `world` — renders on
black. Re-tune the grey-built colours for a black ground, keeping every cue legible and distinct:

- `_CSG_PALETTE` (`preview.py:117`): keep the **hues** (add=blue, subtract=gold, semisolid=coral,
  nonsolid=green, mover=magenta — the cues the ruling names) and re-tune **luminance** for black. The
  current (front, back) split has front vivid / back **lighter** to stand off grey; on black the back
  (obscured) shade must instead read as a **dimmer** partner of the hue, since "lighter than black" is
  the whole field. This is closer to UnrealEd's own near-black-viewport tuning that `preview.py:106`
  says the grey values departed from.
- `FRONT`/`BACK` (`preview.py:94-95`): the uncoloured/legacy path draws black FRONT lines, invisible on
  black — invert to a light default (FRONT light, BACK a dimmer grey).
- `DIVIDER`, `CAPTION`, `MARKER` (`:96-98`), and `_TINT_PALETTE` (`:147`, "chosen for contrast on the
  light-grey bg") re-tuned for black and re-checked for mutual separation and clearance from add-blue /
  subtract-gold. Overlay colours `COL_COLLISION`/`COL_SOUND`/`COL_LIGHT` (`:129-131`) re-checked too.
- Label knockout boxes (currently white on grey) and `_fade_dimmed`'s fade-toward-`BG` (`:913`, `:927`,
  `:1129`) follow `BG` automatically once it is 0 — a `--focus` fade now darkens toward black, which is
  the intended de-emphasis. Verify the white knockout still reads.

The exact re-tuned RGBs are a build-time visual call (bless against the re-rendered goldens); this spec
fixes the constraints, not the literal values. `test_preview.py` pins the classify→palette→render
*wiring*, not literal RGBs (`preview.py:107`), so the wiring tests stand; the many `BG`-relative colour
computations in `test_preview.py` (e.g. `:753`, `:778`, `:797`, `:1174`) recompute against the new `BG`
automatically since they derive from the constant.

### Texture seam reuse

`world` decodes real textures, so it inherits `textured`'s requirement: a resolved project + per-user
games config + every referenced texture readable (`preview_textures`, `rendering.py:689`; the
`preview_movers` class-hierarchy load, `:548`). Route `world` through the same `_preview_render_data`
branch that builds `FaceData`/`TextureData` for `textured` (`rendering.py:610-617`). A brush-only
`wire`/`flat` still needs no game content — unchanged. (Whether `world` should also refuse scaled/
sheared brushes as `textured` does, `rendering.py:645`, or lean on the native solve's own scale gate
`_reject_scaled` at `preview_native.py:87`, is an edge case below.)

## The background/world assumption (surfaced — needs an owner ruling)

A CSG solve needs a starting world, and the native one starts **solid** (`build.rs:5-6`, `:785`). That
is what makes the ruling true: an additive brush is a solid↔empty boundary only where it borders carved
(empty) space, so an **adds-only** set — the three floating cubes that prompted this item — survives as
**nothing**. That is faithful, and it is also the case that most needs an owner call, because:

- **A subset is solved in isolation.** `actor preview` renders the named/`--from-t3d` SET, not the
  whole level. An add that sits inside a subtracted room in the real map still renders blank under
  `world` unless its enclosing subtract is in the set. "World parity" over a subset is parity of *that
  subset's own solve*, not of the subset's look in the finished level.
- **What a zero-surface solve should do** — a legitimate blank frame with a stderr note, or exit 2
  naming the cause (`conventions.md` forbids a blank result plus a scrolling warning).

`generators.md` ("the set merge") is the precedent that background polarity is a real per-operation
choice here: `brush intersect` assumes background **empty**, `brush deintersect` assumes **solid** and
emits the void as a solid plug. `--faces world` needs its own stated assumption, and none of the three
already-filed questions covers it. **Filed as a 4th question:**
`questions/background-world-and-empty-result.md` (recommends solid background, subset solved in
isolation, zero-surface = exit 2 — owner to confirm).

## Non-add kinds under the solve (see `questions/non-add-kinds-in-world.md`)

Only add/subtract shape the BSP world; the solve already handles the rest specially and this spec must
surface, not resolve, how they draw:

- **Movers** carry no `CsgOper` and are excluded from world CSG (`_brush_inputs` skips them,
  `preview_native.py:124`); the native path already draws them as world-transformed `extra_polys`
  overlaid on the solved world (`_mover_world_polys`, `:191`). Recommend the same here: draw the mover
  in mover colour over the world. `movers.is_mover` is the schema-aware predicate the fill needs
  (`preview.py:341-360` explains why the name guess is not enough), which is why `world`, like `flat`,
  loads the class hierarchy.
- **Semisolid / non-solid** add faces without splitting the world. Under the native solve they are
  passed to `build_geometry` with their poly flags (`poly_flags_flat`, `preview_native.py:152`); the
  owner must rule whether their faces appear in the world render and in what colour (the `semisolid`
  coral / `nonsolid` green cues from `_CSG_PALETTE` would apply).
- **Point actors** (lights, playerstarts) have no geometry. Keep the existing marker/sprite overlay
  (`PointRender`, `preview.py:268`; `_preview_point_data`, `rendering.py:749`) on top of the solved
  world, or drop them for viewport fidelity — an owner call. Recommend keeping the overlay: it is what
  makes `actor preview` an inspection tool.

## Edge cases & errors

- Empty actor set / empty stdin → exit 0 no-op (as `wire`, `rendering.py:345`).
- `uedcli_native` not built → exit 2 naming it (`preview_native.py:312`).
- Set with no CSG brush actors (all point actors, or all movers) → the solve has no world; today
  `build_scene` raises "nothing to render: the trunk has no CSG brush actors" (`preview_native.py:317`).
  For `actor preview` this must exit 2 naming the cause, or fall through to point/mover overlays only —
  tie to the zero-surface ruling in the 4th question.
- Unreadable texture / broken games config / outside a project → same refusals as `textured`
  (`rendering.py:715-736`, `:548-596`), naming the offender.
- Scaled/sheared brush → the native solve rejects it (`_reject_scaled`, `preview_native.py:87`); decide
  whether `world` refuses up front like `textured` (`rendering.py:645`) for a single clean message.
- `--size` uncapped → `PreviewAbort` naming the size, no traceback (`preview.py:493-512`), unchanged.
- Never a bare `KeyError`/`IndexError`: the solve's index joins are already bounds-guarded
  (`_node_polys`, `preview_native.py:179-187`; `build_scene`, `:344-352`).

## Tests (`bin/test`, never bare pytest — `dev/docs/rules/tests.md`)

- **Re-bless the four ortho goldens** the black bg changes — every one has grey background pixels:
  `preview_wire_golden_iso.png`, `preview_wire_golden_quad.png` (`test_preview_faces.py:43-44`),
  `preview_flat_golden_iso.png` (`:45`), and `preview_textured_golden_iso.png`. Re-bless only after
  looking at each image (`UEDCLI_BLESS_GOLDEN=1`, `test_preview_faces.py:7`, `:94`).
  `native_preview_golden.png` is `level preview --native` (its own renderer/background) and is **not**
  touched by this change.
- **New `world` golden** over a set that actually carves empty space (a subtract room with an add
  inside), asserting the add shows only where it borders empty and stays hidden where buried — the
  parity claim, byte-blessed like the others.
- **Zero-surface behaviour test** (adds-only set): asserts whatever the 4th question rules (exit 2
  naming the cause, or a blank frame + note) — a regression pin either way (`conventions.md`).
- **Native world-parity check**: assert `world`'s solved surface set matches `level preview --native`'s
  `build_scene` surfaces for the same brushes (same solve, one renderer difference), so the two offline
  world renderers cannot silently diverge.
- **Palette-wiring tests stand** (`test_preview.py`, `test_preview_faces.py` pin classify→palette→
  render wiring, not literal RGBs); re-check the few explicit-colour assertions that hardcode a shade
  rather than derive it from `BG`.

## Open questions (do NOT answer here)

- `questions/mode-name.md` — the `--faces` value name (recommend `world`).
- `questions/world-render-path.md` — reuse the shared native path (recommend (a) + solve-half only) vs
  grow `level preview`.
- `questions/non-add-kinds-in-world.md` — movers / semisolids / non-solids / point actors under the
  solve.
- `questions/background-world-and-empty-result.md` — **filed by this spec**: solid vs other background,
  subset-in-isolation vs in-context, and the zero-surface outcome.

**No `direction/` home yet.** This ruling lives only in this board item; there is no actor-preview
direction topic, and `materialize.md`/`trunk-and-editor.md` cover the build pipeline, not the preview
modes. The parity rule and the black-bg decision are durable product intent that will outlive the
board item and need an owner-approved home under `dev/docs/direction/` — **do not edit `direction/`**;
raise it with the owner when this lands (a `[OWNER — confirm]` item, per `CLAUDE.md`). It also
supersedes the grey-ground tuning assumed by board item
`four-actor-preview-faces-rulings-need-a-durable` — note it there on landing (overview, 2026-08-01).
