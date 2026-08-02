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
- **`textured` = the CSG-solved world**, rendered by the native **solve** through `preview.py`'s
  orthographic pipeline (NOT `render_frame`).
- **The solve uses the faithful `build_geometry_bspcsg` core (`lib.rs:220`, `bspcsg.rs:2228`), NOT the
  default `build_geometry` (`lib.rs:205`).** The default core mis-renders overlapping-subtract
  doorways (`direction/trunk-and-editor.md:82-83`), which is exactly the geometry parity exists to show;
  `build_geometry_bspcsg` is the incremental `bspBrushCSG` port driving toward a byte-identical `UModel`.
  Its **residual byte-divergences are acceptable for a visual preview** — the depends-on item
  `incremental-bspbrushcsg-core` records the residual is now in the merge/repartition stage
  (`bspMergeCoplanars`), not the leaf filter, so containment/visibility is correct even where a merged
  edge count differs. *(Owner ruling 2026-08-02.)*
- **Texture alignment is a hard requirement.** Each CSG fragment keeps its SOURCE poly's authored UV
  frame, so a texture stays continuous and aligned across BSP splits, exactly as UnrealEd draws it.
  Pinned by a UV-continuity test.
- **Non-add kinds:** solid/semisolid/nonsolid brushes go through the solve and their surviving faces
  draw textured; **movers** are excluded from world CSG and draw as a **magenta overlay** on the solved
  world (a mover carries no world CsgOper — UnrealEd's behaviour); **point actors** keep their
  sprite/marker overlay.
- **World & empty:** the selected set is solved **in isolation** against a **solid** world; a solve
  that leaves **zero surfaces** exits 2 naming the cause. A set with **no world-CSG brushes at all**
  (only points/movers) skips the solve and renders overlays over black (exit 0). An **empty** set is a
  clean no-op (exit 0), as `wire`.
- **Black background** for both modes; the `wire` palette is re-tuned for black.

## Current state (cite file:line)

`actor preview` renders **orthographically**, in-process, stdlib-only. `render_actors_to_out`
(`rendering.py:307`) resolves per-mode data (`_preview_render_data`, `:599`) and calls
`preview.render_brushes_pgm`/`render_quad_pgm` (`preview.py:2141`, `:2494`), both of which build their
geometry through `_scene_geometry` (`preview.py:1867`). The `--faces` flag (`_arguments.py:219`,
`choices=["wire","flat","textured"]`) picks the fill: **wire** (outlines only, resolves nothing, no
game content), **flat** (each face filled in its CSG colour, wire kept over — `_fill_face`,
`preview.py:823`, called at `:2248`), **textured** (each face sampled from its own texture/UV frame,
no wire — `_fill_face_textured`, `preview.py:779`, called at `:2262`). Visibility today is a per-brush
approximation, not a solve: `_scene_geometry` culls a subtract's near faces (`cull_front`,
`preview.py:1962`, applied `:1980`) and never hides an add by containment. Background/palettes are
grey-tuned: `BG = 224` (`preview.py:485`), `_CSG_PALETTE` (`:117`), `FRONT/BACK/DIVIDER/CAPTION/MARKER`
(`:94-98`).

`level preview --native` already runs a real world solve on a separate, **perspective** path.
`build_scene` (`preview_native.py:300`) runs: `_brush_inputs` (`:112`, iterates `level.order` `:120`,
excludes movers/builder `:124`) → **`uedcli_native.build_geometry` (the DEFAULT core, `:320`)** →
`serialize_model` (`:321`) → `parse_model_body` (`:325`) → `_node_polys` (`:171`, called `:344`, each
BSP node → `(world_verts, i_surf.i_actor, i_surf.i_brush_poly)`, all index-joins bounds-guarded) →
source-poly join back to the brush's authored poly for texture/UV (`:344-352`) → `_mover_world_polys`
(`:191`, called `:354`, movers world-transformed at base pose). It packs the result into `render_frame`
tuples (UV frame baked in via `world_uv_frame`, `tex_index` into a native texture table) and rasterizes
with `render_frame` (`lib.rs:358`), a **perspective** camera. `build_scene` calls the **default** core,
which is exactly why "split build_scene" is the wrong framing for this change (see Design).

Both `build_geometry` and `build_geometry_bspcsg` take the same flat `BrushTuple` list and return a
`Built` handle over a `Model` whose `surfs` carry `i_actor`/`i_brush_poly` (`model.rs:107-108`), so both
feed `serialize_model` → `parse_model_body` → `_node_polys` identically. The swap is one call site.

**Being removed:** `flat`, the old per-brush `textured` MODE branch, and their stale references.
**Being added:** the CSG-solved `textured` (via the bspcsg core), the solved-surface channel into
`_scene_geometry`, and the black background.

## Design

### `solve_world_surfaces` — the solve, via the bspcsg core

`build_scene` (`preview_native.py:300`) is NOT split. It ends by producing perspective `render_frame`
tuples through the DEFAULT core — the wrong core and the wrong output shape for this path. Instead add a
sibling **solve** function that reuses `build_scene`'s middle (the CSG build + extraction + join +
movers) but routes through the faithful core and returns raw world-space fragments:

```
solve_world_surfaces(actors, index, search_files=None)
    -> (world_surfaces: list[(actor, source_poly|None, world_verts)],
        mover_polys:     list[(actor, source_poly, world_verts)])
```

- **Ad-hoc actor list, not a trunk `level`.** `actor preview` already holds an actor list. Adapt
  `_brush_inputs`'s per-actor marshalling (`preview_native.py:112`) to iterate the given list instead of
  `level.order`; the algorithm is unchanged, only the input type. It excludes movers and the builder
  brush (`:124`) and rejects scaled/sheared brushes (`_reject_scaled`, `:87`) as today.
- **Route through the bspcsg core:** call `uedcli_native.build_geometry_bspcsg(brushes)` (`lib.rs:220`),
  NOT `build_geometry`. Then `serialize_model` → `parse_model_body` → `_node_polys` (`:171`) →
  source-poly join (`:344-352`), all unchanged — both cores emit the same `Model` shape.
- **Return world fragments, not `render_frame` tuples.** `actor preview` draws with `preview.py`'s own
  rasterizer (`_fill_face_textured`), not `render_frame`, and computes UV frames itself
  (`world_uv_frame`) at draw time. So the solve returns each surviving surface as
  `(actor, source_poly, world_verts)` — the same shape `_scene_geometry`'s per-poly loop consumes, minus
  the local→world transform (the verts are already world-space). A node that joins to no source poly
  (`:349-352`) yields `(None, None, world_verts)` (see M5).
- **Movers** are returned separately via `_mover_world_polys` (`preview_native.py:191`), world-
  transformed at base pose, NOT run through CSG — they draw as the magenta overlay (see Non-add kinds).

`render_frame` and any perspective path stay rejected: perspective distorts `actor preview`'s
orthographic multi-view and bypasses all of `preview.py`'s annotation/legend/highlight/focus machinery,
so `textured` would become a different KIND of image from `wire`.

Depends-on `incremental-bspbrushcsg-core`: the core **exists and is exposed** (`build_geometry_bspcsg`),
with a known residual in merge/repartition (byte counts), accepted for a visual preview.

### Feeding the solved surfaces into `_scene_geometry` (the B3 plumbing)

`_scene_geometry` (`preview.py:1867`) is **hardwired to per-actor, per-source-poly iteration**
(`:1925`, `:1972`) and builds world verts from LOCAL verts via `local_offset(R, prepivot, v)`
(`:1973-1974`). It cannot just take "a different SET of faces"; the solved surfaces are already
world-space fragments with no owning brush transform. So:

1. **A new channel.** Today `FaceData` (`preview.py:297`, built at `rendering.py:617`) carries only
   `movers` + `textures`. Add a field carrying the solved payload — the `world_surfaces` +
   `mover_polys` lists from `solve_world_surfaces`. `_scene_geometry` reads it off
   `render_data.faces`; no draw-time call-site signature changes (it already receives `render_data`).
2. **A solved branch in `_scene_geometry`.** Under `textured`, iterate the solved `world_surfaces`
   instead of the per-actor `for actor … for poly` loop. Each fragment carries its own world verts, so
   **SKIP `local_offset`** (`:1973-1974`) — use the verts directly as `v3`. Emit the same `fills` +
   `tex_faces` entries (`:2007`, `:2022`): `world_uv_frame(actor, source_poly)`, `_poly_texture_ref`,
   `tex_data.by_ref`, `masked` — all keyed off the SOURCE poly, so alignment survives the split. Point
   actors keep their existing handling (`:1927-1940`); it is orthogonal to the geometry source.
3. **DISABLE the subtract-front cull and the mirror correction on the solved path.** `cull_front`
   (`:1962`, applied `:1980`) and `mirrored`/`_is_front_corrected` (`:1968`, `:1978`) are per-brush
   visibility heuristics; the solve has ALREADY resolved visibility globally. Re-culling would delete a
   subtracted room's interior walls, which MUST show. On the solved path, `cull_front = False`,
   `mirrored = False`; `front` is still computed (from world verts, for occluder/depth ordering and the
   edge/label machinery) but never used to remove a face.
4. **Per-poly index decal when one source poly becomes N fragments.** The decal loop draws one label per
   poly (`:2065-2067`); with the solve, one source poly can survive as several fragments, which would
   N-plicate the number. Rule: draw the index **once per `(actor, source_poly_idx)`**, on the
   largest-projected-area surviving fragment (so it lands on a visible piece). A `(None, None)` fragment
   carries no source index and gets no decal. *(Implementation call — pin in `rationale/`; alternative
   "first fragment" rejected because the first fragment may be a sliver.)*

`wire` is untouched: it never sees the solved channel and keeps the per-actor loop.

### Removing `flat` and the old `textured` MODE

Per the no-back-compat convention, delete outright:

- Drop `flat` from `_arguments.py:219` `choices` and rewrite the `--faces` help (below); `--faces`
  choices become `["wire", "textured"]`, default `wire` unchanged.
- **Delete only the `flat` MODE branch and its call.** In the fill loop, remove the non-textured branch
  `_fill_face(...)` at `preview.py:2248`. **Do NOT delete `_fill_face` (`preview.py:823`)** — the
  textured path still calls it at `:2255` to fill a grey/untextured face (`mips is None` →
  `DEFAULT_GREY × shade`). `_fill_face` stays; only the `flat`-mode call at `:2248` goes.
- The old per-brush `textured` is *replaced* by the solved path; `_fill_face_textured` (`:779`) is
  **kept** (the solved path reuses it — it now draws solved fragments, not each brush's own faces).
- Under `textured`, `draw_wire` stays `False` (`:2288-2290`) — the solved world draws no wireframe.

### Stale `flat` references to drop with the mode (M1)

- `_reject_explicit_brush_colors` message (`rendering.py:630`, "or use --faces flat").
- `_reject_transformed_brushes` message (`rendering.py:664`, "or use --faces wire/flat"). Keep the
  refusal itself: the solve also rejects scaled brushes (`_reject_scaled`), but this up-front check gives
  one clean batch message.
- The `--faces` help (`_arguments.py:219-236`) and the `--brush-colors` help mention of `--faces flat`
  (`_arguments.py:238`).
- `preview_movers` / `preview_textures` docstrings (`rendering.py:555-556`, `:675/678/685`) that say
  `flat` needs class/texture content — reword to `textured`.

### Black background + `wire` palette re-tune

Set `BG = 0` (`preview.py:485`) so both modes render on black. Keep the CSG **hues** (add=blue,
subtract=gold, mover=magenta) and re-tune **luminance** for black — notably `FRONT/BACK` (`:94-95`): the
uncoloured path draws black `FRONT` lines, invisible on black, so invert to a light default; the wire
palette's obscured/back shade becomes a **dimmer** partner of the hue rather than a lighter one. Re-check
`DIVIDER/CAPTION/MARKER` (`:96-98`) and label knockout boxes for legibility on black. `_fade_dimmed`'s
fade-toward-`BG` (`:913`) follows `BG` automatically (a `--focus` fade now darkens toward black —
intended). Exact RGBs are a build-time visual call, blessed against the re-rendered `wire` golden; this
spec fixes the constraints, not the values.

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

### The actor-set order IS the CSG order (M4)

`_brush_inputs` feeds brushes to the core in `level.order` (`preview_native.py:120`); the ad-hoc list
`solve_world_surfaces` takes has no `order_value` sidecar, so **the order the actors arrive in is the
CSG evaluation order** (a subtract before vs after an add changes the solve). For a faithful preview the
caller must pass actors in the trunk's effective CSG order (`(order_value, name)` sort), matching
materialize. The plan must confirm `actor preview` already sorts its set that way before the solve; if
it does not, that is a separate finding to board, not a silent fix here.

### Non-add kinds under the solve

- **Semisolid / non-solid** — passed to the solve with their poly flags (`poly_flags_flat`,
  `preview_native.py:152`); their surviving faces draw textured like any other surface.
- **Movers** — excluded from world CSG (`_brush_inputs` skips them, `preview_native.py:124`); returned
  by `solve_world_surfaces` as world-transformed `mover_polys` (`_mover_world_polys`, `:191`).
  **Compositing (M3):** movers draw **filled** in the mover CSG hue (magenta) through `_fill_face`,
  against the **same shared `zbuf`** as the solved world, so a mover behind a wall is occluded and a
  mover in front occludes — no wireframe (matching `textured`'s no-wire rule, `:2288`). `movers.is_mover`
  (schema-aware, `preview.py:341-360`) is the predicate; this is why `textured` loads the class
  hierarchy.
- **Point actors** — no geometry; keep the existing marker/sprite overlay (`PointRender`,
  `preview.py:269`; `_preview_point_data`, `rendering.py:749`) over the solved world.

### World, empty, and the pre-solve guard (B4)

The solve starts from a **solid** world (`build.rs:5-6`) and the selected set is solved **in isolation**
— `actor preview` renders the named/`--from-t3d` set, not the whole level, so an add renders only where
the set's own subtracts carve empty space around it.

Today the empty-set path only WARNS and does not return (`rendering.py:345`), and the reused solve
RAISES on a set with no CSG brushes (`preview_native.py:318`). So a **pre-solve guard** in
`_preview_render_data` (`rendering.py:599`), before `solve_world_surfaces` is called, partitions the
set:

- **Empty actor set / empty stdin** → no solve; clean exit-0 no-op, as `wire`.
- **No world-CSG brush actors** (only point actors and/or movers) → no solve; the solved world is empty,
  overlays (movers magenta, points sprites) draw over black; exit 0. This is the set's own defined
  behavior — an empty world was never intended, so it is not the zero-surface error.
- **World-CSG brushes present, solve yields ZERO surviving surfaces** → exit 2 naming the cause (e.g.
  "nothing survives the solve: the set has no subtracted space; see `--faces wire`"), never a blank
  frame plus a warning (`conventions.md`). This is the likely-error case (adds with no carving
  subtract), distinct from the point/mover-only case above.

`generators.md` is the precedent that background polarity is a real per-operation choice
(`intersect`=empty, `deintersect`=solid); `textured` states **solid**.

### Texture resolution follows the solve (M2)

`preview_textures` (`rendering.py:689`) today collects refs from EVERY brush face and refuses on any
unreadable one — including faces the solve culls, which the render never draws. Relax it: run the solve
FIRST, then collect refs only from the **surviving** `world_surfaces`' source polys, and resolve/refuse
only those. This is decision 2.6 ("needs is literal") applied to the solved set — a texture is "needed"
only if a surviving surface references it. Reorders `_preview_render_data` to: cheap arg/geometry
refusals → mover class index → **solve** → textures(surviving refs only) → build the `FaceData` with the
solved payload + movers + textures.

## Edge cases & errors

- Empty actor set / empty stdin → exit 0 no-op (pre-solve guard, above).
- No world-CSG brush actors (point/mover-only) → overlays over black, exit 0 (pre-solve guard).
- Zero surviving surfaces from a real brush set → exit 2 naming the cause.
- `uedcli_native` not built → exit 2 naming it (`preview_native.py:312`).
- Unreadable texture (that a SURVIVING surface needs) / broken games config / outside a project → the
  same refusals the old textured used, naming the offender (`rendering.py:715-736`, `:548-596`).
- Scaled/sheared brush → refused up front (`_reject_transformed_brushes`, `rendering.py:645`) and again
  by the solve (`_reject_scaled`, `preview_native.py:87`); one clean message.
- `--size` uncapped → `PreviewAbort` naming the size (`preview.py:493`), no traceback.
- Source-less solved fragment `(None, None)` → grey, never a `KeyError` (M5): routed to the `mips is
  None` → `DEFAULT_GREY` branch (`preview.py:2253`).
- Never a bare `KeyError`/`IndexError`: the solve's index joins are bounds-guarded
  (`preview_native.py:179-187`, `:344-352`).

## Tests (`bin/test`, never bare pytest — `rules/tests.md`)

- **Delete** the `flat` golden (`preview_flat_golden_iso.png`, `test_preview_faces.py:45`) and the old
  per-brush `textured` golden (`preview_textured_golden_iso.png`, `:1982`), and the `flat`/old-`textured`
  behaviour tests in `test_preview_faces.py`.
- **Re-bless the `wire` goldens** for black (`preview_wire_golden_iso.png`, `preview_wire_golden_quad.png`,
  `test_preview_faces.py:43-44`) — only after eyeballing each (`UEDCLI_BLESS_GOLDEN=1`, `:7`).
  `native_preview_golden.png` is `level preview --native`'s own renderer — untouched.
- **New `textured` world golden** over a set that carves empty space (a subtract room with an add
  inside): the add shows only where it borders empty, hidden where buried — the parity claim,
  eyeballed then byte-blessed. This golden IS the world-parity guard.
- **Doorway/overlapping-subtract test**: a scene of two overlapping subtracts whose shared opening the
  DEFAULT core mis-renders (`trunk-and-editor.md:82-83`) — assert the opening shows through, which only
  the bspcsg core produces. This is what proves the solve routes through `build_geometry_bspcsg`, not
  `build_geometry`.
- **UV-continuity test**: a wall cut by a subtract keeps one continuous, aligned texture across the
  split (the alignment requirement).
- **Zero-surface test**: an adds-only set (real brushes, nothing carved) exits 2 naming the cause.
- **Point/mover-only test**: a set with no world-CSG brushes renders overlays over black at exit 0
  (distinct from zero-surface).
- **Native world-parity — DROPPED as written.** The old plan pinned `textured` to
  `level preview --native`'s `build_scene` surfaces; but `build_scene` uses the DEFAULT core
  (`preview_native.py:320`), so that test would rubber-stamp the doorway flaw the switch to
  `build_geometry_bspcsg` exists to fix. The world golden + the doorway test above replace it. (A
  native-vs-textured cross-check is only meaningful once `--native` also moves to the bspcsg core — out
  of scope here.)
- Palette-wiring tests stand (they pin classify→palette→render wiring, not literal RGBs); re-check any
  assertion hardcoding a shade rather than deriving it from `BG`.

## `direction/` home (owner action on landing — do NOT edit `direction/`)

The parity rule, the two-mode set, the bspcsg-core choice, and the black background are durable product
intent with no `direction/` home (there is no actor-preview direction topic; `materialize.md`/
`trunk-and-editor.md` cover the build pipeline, not the preview modes). Raise a `[OWNER — confirm]` item
for an approved home when this lands. It supersedes: the 2026-08-01 "keep `textured` as the per-brush
inspector" note in this item's `overview.md`, and the grey-ground tuning assumed by board item
`four-actor-preview-faces-rulings-need-a-durable` (note it there on landing).
