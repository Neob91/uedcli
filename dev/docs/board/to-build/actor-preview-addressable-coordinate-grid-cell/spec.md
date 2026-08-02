# Spec — addressable coordinate grid on `actor preview`

## Goal

Give every preview render a text handle on its pixels. Draw a label gutter (columns `A,B,C…` across
the top, rows `1,2,3…` down the sides — no gridlines), and assign every actor a grid cell emitted as
a `name → cell` legend on stderr plus a `--json` map. An agent that sees "a misaligned pillar at D4"
carries `D4` back into a name set. The address is a region of the **image/projection**, never a world
coordinate.

## Decisions (owner-ruled 2026-08-02, locked — do not reopen)

- **Cell = centroid + span.** One primary cell (the actor centroid) plus the covered range in parens:
  `Pillar_3f8a2c  D4  (C3–E5)`. A point actor is one cell, no span.
- **Addressing = letters × numbers.** Columns are letters `A,B,C…` (past `Z` → `AA,AB…`), rows are
  numbers `1,2,3…`. A letter is always a column, a number always a row (no comma to parse).
- **Quad = per-pane, pane-qualified.** One coordinate per projection, each naming its pane:
  `Pillar_3f8a2c  Top:D4 Front:B7 Side:C7 Iso:E5`. A single-view render is unqualified: `Pillar D4`.
- **Address ALL actors; flag hidden ones.** Under `--faces textured` (the CSG-solved world) an add
  outside subtracted space renders nothing but still gets a cell, marked hidden:
  `InnerAdd_77  E5  (hidden)`. Omitting it would hide the actor you are trying to find.
- **Always on.** The gutter + stderr legend draw on EVERY preview, unconditionally — no enable flag,
  no `--no-grid`, every `--faces` mode. Orthogonal to `--annotate` (which still governs on-geometry
  name/poly labels): `--annotate none` gives a clean image that still carries the gutter + legend.
- **Density = fixed default, `--grid N` override.** A same-cell collision is not an error — both
  actors co-list at that cell.
- **Breakdown = pane 0 only.** Under `--layout breakdown` the gutter + stderr legend draw on pane 0
  (the whole-scene pane, framed by `--view`); the per-actor zoomed panes render as today (each is
  already name-captioned). The legend addresses read off pane 0, so they are single-view and
  unqualified, exactly like a `single` render. (owner-ruled 2026-08-02, via widget)

## Current state (file:line)

- **Preview entry is one seam.** `actor preview`, `stash preview`, `prefab preview` all call
  `rendering.render_actors_to_out(actors, args)` (`cli/rendering.py:307`; callers
  `cli/commands/actor/preview.py:43,58`, `cli/commands/stash.py:208`, `cli/commands/prefab.py:90`).
  Wiring the grid there covers all three families.
- **Layouts.** `render_actors_to_out` dispatches on `--layout`: `single` →
  `preview.render_brushes_pgm` (`preview.py:2141`), `quad` (default) → `preview.render_quad_pgm`
  (`preview.py:2494`), `breakdown` → `_render_breakdown_grid` (`cli/rendering.py:235`). Quad renders
  each of the 4 panes by calling `render_brushes_pgm` at `size=half` with a per-pane `view`
  (`preview.py:2522-2530`).
- **World→pixel map.** `_framing(pts, region, size, view, iso_angle, inset_top, pad)` returns
  `world_to_pxf(p3)` mapping a 3-D world point to float pixel `(x, y)` (`preview.py:2078-2112`). The
  geometry is scaled by `scale = draw/span`, `draw = size - 2*pad - inset_top`, `pad = _FRAME_PAD = 6`
  (`preview.py:2075,2096`); y is flipped (`size-1-…`). This is the SAME map the render draws from, so a
  cell computed through it cannot drift from the image.
- **Per-actor projected points.** `_scene_geometry` (`preview.py:1867`) projects every brush poly and
  point actor; a brush's projected 2-D vertices accumulate in `brush_cands_2d`
  (`preview.py:1970,1985`) and point actors in `points` (`preview.py:1939`). But per-actor footprints
  are DISCARDED on the real (`color_by_csg=True`) preview path: `brush_names` is populated only when
  `not hybrid` (`preview.py:2068`). The build must collect per-actor projected points out of this loop
  (see Design).
- **Out-of-render collector precedent.** `shown_highlights: set` is a mutable set threaded through
  every pane and mutated in place to report what drew (`preview.py:2149,2191-2194`; quad passes ONE
  set through all four panes, `cli/rendering.py:352`). The cell map uses the same pattern.
- **stderr vs stdout.** Human notes already go to stderr (`_note_invisible_highlights`,
  `cli/rendering.py:197`); the PNG path is printed to stdout (`cli/rendering.py:408`). `--json` verbs
  print `json.dumps(obj, indent=2)` to stdout (`cli/commands/event.py:36`,
  `cli/commands/level.py:359`, `cli/commands/classes.py:218`). No `--grid`/`--json` exists on preview
  today (`cli/parsers/_arguments.py:205-312`).
- **Font.** `_draw_text` renders the 3×5 `_FONT` (`preview.py:978`, `_FONT` at `:380`); it has every
  `A–Z`, `0–9`, `:` and `-`. So gutter letters/numbers and pane-qualified legend text draw. The en-dash
  `–` in a span is NOT in the font — spans appear only in the stderr/JSON text, never on the image.

## Design

### Grid geometry (image-space, canvas-anchored)

The grid divides the pane's **drawable canvas rect**, not the geometry footprint — so `D4` is a fixed
region of the projection regardless of where geometry landed. `--grid N` sets `N` columns × `N` rows
(panes are square, so square cells: `--grid 12` → cols `A..L`, 12 rows); default `N` fixed at **12**
(an agent choice → record in `rationale/preview.md`, not a direction doc). The drawable rect is `[x0, x1] × [y0, y1]` in pixels,
where `x0 = pad + gutter`, `x1 = size-1 - pad - gutter`, `y0 = pad + gutter + inset_top`,
`y1 = size-1 - pad - gutter` (`inset_top` is the existing legend reserve). Column of a pixel:
`col = clamp(floor((px - x0) / ((x1-x0)/N)), 0, N-1)`; row likewise from `py` (top row = 1). Letters:
0→`A` … 25→`Z`, 26→`AA` (base-26 bijective). Rows: 1-based integers.

### The gutter (drawn in a reserved band, not `_FRAME_PAD`)

`_FRAME_PAD` is 6 px — too small to hold a font glyph (`name_scale·5` px tall). So add a **gutter
reserve** to `_framing` for the top and BOTH sides by `gutter` px, so labels sit clear of geometry.
Note this is NOT a copy of `inset_top`: `inset_top` shrinks `draw` while the geometry stays anchored
bottom-left, so it insets the top and the RIGHT only (`preview.py:2096-2107`). The gutter must inset
left+right symmetrically — so `_framing`'s x-mapping gains its own left offset, it is not a second
`inset_top`. Draw each column letter centered at its column's x-center in the top band, and each row
number centered at its row's y-center in the left AND right bands, via `_draw_text`. No gridlines.
`gutter` sized to the label glyph (`name_scale` from `preview.py:2218`) plus a margin.

### Cell per actor (same map as the image)

Inside `render_brushes_pgm`, after `_framing`, project each actor's centroid and bbox through the
pane's own `world_to_pxf` and map to cells:

- **Centroid** = the actor's world centroid (brush: mean of its world vertices; point actor: its
  `Location`) projected → one `(col,row)` → the primary cell. (Projection is affine, so this equals
  the mean of the projected vertices — collect them from the `_scene_geometry` loop.)
- **Span** = the projected AABB of all the actor's points → `(min col..max col, min row..max row)`.
  A point actor's span equals its cell (no parens).

Collect `{actor_name: (cell, span, hidden)}` into a mutable per-pane collector passed into
`render_brushes_pgm` — like `shown_highlights`, EXCEPT each pane gets its OWN collector (cells are
per-pane; `shown_highlights` is one set shared across panes). `render_quad_pgm` tags each pane's
result by pane name (`Top/Front/Iso/Side`). `render_actors_to_out` owns the collectors and builds the
outputs.

**Layout gating.** The gutter + cell collection are driven by a `grid` parameter on
`render_brushes_pgm` (the density `N`, or None = off), NOT drawn unconditionally inside it — because
`_render_breakdown_grid` calls `render_brushes_pgm` once per pane. `render_actors_to_out` turns it on
for `single` and `quad` (always), and under `breakdown` passes it (with a cells collector) only to
pane 0's `render_brushes_pgm` call, None to every per-actor pane. So "always on" is enforced at the
orchestration seam, and breakdown's per-actor panes render byte-identically to today.

### Hidden-actor flag

An actor is `hidden` in a pane when none of its faces produce a drawn pixel there (all culled in
`_scene_geometry` or depth-hidden — the `hidden` set at `preview.py:2227`). Under `--faces wire`
nothing is CSG- or depth-hidden, so a non-degenerate actor is never hidden. Under `textured` an add
outside subtracted space draws nothing → `hidden`, reason `(hidden)`. This couples to the
render-parity item `actor-preview-unrealed-render-parity-new-csg` (the CSG-solved textured world):
the flag mechanism (drew-nothing per actor) is built here against current textured mode; the precise
"outside subtracted space" cause sharpens when parity lands. An actor still gets its cell from its
projected centroid whether or not it drew.

### Output

- **stderr legend** — always, one line per actor, in scene order. Single view:
  `Pillar_3f8a2c  D4  (C3–E5)`. Quad: `Pillar_3f8a2c  Top:D4 Front:B7 Side:C7 Iso:E5`. A hidden actor
  appends `(hidden)`. Same-cell collisions each get their own line (both list that cell). A header line
  names the grid density (`grid: 12×12 columns A–L, rows 1–12`). Breakdown emits the pane-0 legend,
  single-view and unqualified (same shape as `single`).
- **`--json`** (new `store_true` flag) — replaces the bare-path stdout line with one object:
  `{"image": "<path>", "grid": {"cols": N, "rows": N}, "actors": {"<name>": {"panes":
  {"Top": {"cell": "D4", "span": "C3–E5"}, …}, "hidden": false}}}`. Single view has one `panes` entry
  keyed by its `--view`. Uniform pane-keyed shape so a script reads every layout the same way. Printed
  `json.dumps(obj, indent=2)` to stdout; without `--json` the bare path stays on stdout (unchanged) and
  only the legend goes to stderr.

## Edge cases & errors

- **Empty actor set** — the existing "nothing to render" warning path (`cli/rendering.py:345`); no
  legend rows, `actors: {}` in JSON, exit 0 (an empty piped set stays a clean no-op).
- **`--grid N` bounds** — `type=int`; reject `N < 1` (and an absurd upper bound, e.g. `N > 52` so
  single-letter/short addresses stay legible) with a clean `exit 2` naming the value
  (`--grid must be in [1, 52], got 0`), never a traceback. Validate in `render_actors_to_out` beside
  the existing `--frame-tightness` check (`cli/rendering.py:311`).
- **`--layout breakdown`** — the gutter + legend draw on pane 0 only (the whole-scene pane, framed by
  `--view`), single-view and unqualified like `single`; the per-actor zoomed panes render byte-for-byte
  as today. `_render_breakdown_grid` passes the `grid`/collector to pane 0's `render_brushes_pgm` call
  and None to the rest (owner-ruled 2026-08-02).
- **No Python exception reaches the user** — every new path (bad `--grid`, empty set, a degenerate
  actor with no projectable points → no cell, skipped from the legend with a stderr note) exits cleanly.

## Tests

- Unit (pure, no render): base-26 bijective letters (`0→A`, `25→Z`, `26→AA`, `701→ZZ`, `702→AAA`);
  pixel→cell mapping and clamping at the drawable-rect edges; centroid cell + span range from a
  synthetic projected point set; same-cell collision co-lists.
- Render: a fixed 2–3-actor scene renders a deterministic legend (golden string) under `single` and
  `quad` (pane-qualified); `--grid 4` vs default changes the addresses; `--annotate none` still emits
  the legend; the gutter band reserves space (geometry does not draw under a label — pixel probe).
- Output: `--json` emits the documented object to stdout (image path + per-pane cells + hidden);
  without `--json` the bare path stays on stdout and the legend on stderr (capsys).
- Hidden: a textured add outside a subtract flags `hidden` and still carries a cell; a wire render
  never flags hidden.
- Errors (regression, per convention): `--grid 0` / `--grid 999` exit 2 naming the value; empty set is
  exit 0 with `actors: {}`.
- All via `bin/test -k preview`.
