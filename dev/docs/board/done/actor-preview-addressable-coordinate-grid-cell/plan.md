# Plan — addressable coordinate grid on `actor preview`

Build in a feature worktree (`dev/docs/rules/worktrees.md`), commit per slice, one subagent review of
`git diff base...HEAD`, then squash-merge as one commit. Tests via `bin/test` (`dev/docs/rules/tests.md`).
Update `docs/usage.md` (the `actor preview` flags + the always-on gutter/legend) in the same change.

Ordered so each slice is verifiable on its own; the grid stays invisible to output until slice 4 wires
it, so early slices can't half-break preview.

## Slice 1 — cell math (pure, no render)

`preview.py`: `_col_label(i) -> str` (base-26 bijective), `_cell_of_pixel(px, py, rect, n) -> (col,row)`
(clamped), `_actor_cells(points, rect, n) -> (cell, span)` from a projected-point set (centroid = mean,
span = AABB → col/row range), and address formatting (`D4`, span `C3–E5`).
- Verify: unit tests for letters (`0→A,25→Z,26→AA,701→ZZ,702→AAA`), edge clamping, centroid+span,
  point-actor single cell. `bin/test -k preview`.

## Slice 2 — gutter render + always-on framing

`preview.py`: add a `gutter` reserve to `_framing` that insets the drawable rect on top AND both
sides. This is NOT a copy of `inset_top` — `inset_top` shrinks `draw` with geometry anchored
bottom-left, so it insets top+right only (`preview.py:2096-2107`); the gutter needs a symmetric
left/right inset, so the x-mapping gains its own left offset. Draw column letters (top band) and row
numbers (both side bands) via `_draw_text`, no gridlines. Add a `grid` parameter to
`render_brushes_pgm` (density `N`, or None = off) that gates the gutter — NOT drawn unconditionally,
because breakdown calls `render_brushes_pgm` per pane and only pane 0 gets a grid. It is independent
of `--annotate`. `render_quad_pgm` forwards `grid` to each pane's `render_brushes_pgm` call.
- Verify: a render shows the gutter; a pixel probe confirms geometry does not draw under a label band;
  `--annotate none` still draws the gutter; `grid=None` renders byte-identically to today. Golden/param
  tests in `test_preview.py`.

## Slice 3 — per-pane cell collection

`preview.py`: collect each actor's projected points in `_scene_geometry` (return them as a new
`_SceneGeom` field, incl. on the `color_by_csg`/hybrid path where `brush_names` is empty today —
`brush_cands_2d` is computed at `preview.py:1970,1985` but discarded at `:2068`, and point-actor
projections at `:1933-1938`), and in `render_brushes_pgm` fill a mutable `cells_out` collector
(`{name: (cell, span, hidden)}`) using the pane's own `world_to_pxf` + drawable rect — same map as the
image. Each pane gets its OWN `cells_out` (unlike the shared `shown_highlights`). `render_quad_pgm`
tags results by pane name (`Top/Front/Iso/Side`) into a per-pane dict.
- Verify: unit test that a known scene yields the expected `(cell, span)` per actor per pane, and that
  the cell matches where the label draws on the image (consistency probe). `bin/test -k preview`.

## Slice 4 — stderr legend + `--json`

`cli/parsers/_arguments.py`: add `--json` (`store_true`, real `help=`).
`cli/rendering.py`: own the per-pane collectors, pass them into the render call for each layout, build
the stderr legend (scene order; single/breakdown unqualified, quad pane-qualified; density header;
collisions co-list) and, under `--json`, the stdout object (`{"image", "grid", "actors"}`, pane-keyed).
Under `breakdown`, thread the `grid`/collector into `_render_breakdown_grid` for pane 0 only (its
legend/JSON take the single-view, `--view`-keyed shape). Without `--json` keep the bare path on stdout
and the legend on stderr — one stdout form, never both.
- Verify: capsys tests — legend on stderr for single + quad (golden), `--json` object on stdout with
  image path + per-pane cells, bare path unchanged without `--json`, collision co-lists, breakdown emits
  the pane-0 legend. `bin/test -k preview`.

## Slice 5 — `--grid N`

`cli/parsers/_arguments.py`: add `--grid N` (`type=int`, default 12, real `help=`).
`cli/rendering.py`: validate bounds beside `--frame-tightness` (`[1, 52]`, else exit 2 naming the
value); thread `N` into the render + cell math.
- Verify: `--grid 4` changes addresses vs default; `--grid 0` / `--grid 999` exit 2 naming the value
  (regression tests, no traceback). `bin/test -k preview`.

## Slice 6 — hidden-actor flag

`preview.py`: mark an actor `hidden` when none of its faces draw a pixel in a pane (culled or
depth-hidden — the `hidden` set); carry it in `cells_out`. `cli/rendering.py`: append `(hidden)` in the
legend and `"hidden": true` in JSON. Cell still comes from the projected centroid.
- Verify: a `--faces textured` add outside a subtract flags `hidden` and keeps its cell; a `--faces wire`
  render never flags hidden. Note the parity coupling in a code comment referencing item slug
  `actor-preview-unrealed-render-parity-new-csg`. `bin/test -k preview`.

## Close-out

Update `docs/usage.md`. File a `rationale/preview.md` entry for the default grid size (`12`) with its
Rejected alternatives. `git mv` the item to `done/`, cut `overview.md` to a one-line record, squash-merge.
