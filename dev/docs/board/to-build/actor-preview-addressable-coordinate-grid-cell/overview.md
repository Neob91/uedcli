+++
priority = "p2"
kind = "implement"
summary = "actor preview: an addressable coordinate grid — a gutter of column/row labels + a per-actor cell ref on stderr, so a render can be cross-referenced to a name set in text."
+++

# actor preview: addressable coordinate grid

## The idea (owner, 2026-08-02)

Overlay an addressable grid on the preview: no visible gridlines, but **column labels across the top
and row labels down the sides**, so every region of the image has an address. Then each actor in the
render is assigned a grid cell, emitted to **stderr** as a `name → cell` legend. This gives a **text
handle on the pixels** — an agent (or human) that sees "a misaligned pillar at D4" can carry `D4`
straight into `actor find`/a mutate. It moves actor addressing OFF the image (today names are painted
on the geometry and overlap in dense scenes) into a clean gutter + stderr legend, which fits the CLI
split: image to `--out`, human legend to stderr, machine map to `--json`.

## Decisions (owner-ruled 2026-08-02, via widget)

- **Cell assignment:** centroid + span — a single primary cell (the brush centroid) plus the covered
  range in parens, e.g. `Pillar_3f8a2c   D4  (C3–E5)`. Point actors are one cell.
- **Numbering:** letters × numbers — columns `A,B,C…` across the top, rows `1,2,3…` down the side
  (chess/spreadsheet). A letter is always a column, a number always a row (no comma to parse).
  Columns past `Z` → `AA,AB,…`.
- **Quad layout:** per-pane, pane-qualified — one coordinate per projection, each naming its pane:
  `Pillar_3f8a2c  Top:D4 Front:B7 Side:C7 Iso:E5`.
- **Hidden actors** (under `--faces textured`, the CSG-solved world, where an add outside a subtract
  renders nothing): address ALL actors; flag the invisible ones — `InnerAdd_77  E5  (hidden: outside
  subtracted space)`. Omitting them would hide exactly the actor you're trying to find.
- **Always on:** the grid gutter + stderr legend are shown on EVERY preview, unconditionally — not
  gated behind a flag, and there is no `--no-grid`. (owner: "always show grid")
- **Density:** a fixed default cell count, with a `--grid N` override. A same-cell collision is not an
  error — both actors co-list at that cell in the legend.

## Design sketch (pre-spec — needs a full spec before build)

- **Shape:** ALWAYS ON — every `actor preview` (and `stash`/`prefab preview`) render draws the gutter
  and emits the stderr legend, unconditionally; no enable flag, no `--no-grid`. It is orthogonal to
  `--annotate`, which still controls on-geometry name/poly labels independently (`parse_annotation_spec`,
  `preview.py:174`; `_arguments.py:243`) — so `--annotate none` gives a clean image that still carries
  the grid gutter + legend. Density via a new `--grid N` (fixed default). Applies under any `--faces`
  mode.
- **Rendering:** draw column labels along the top edge and row labels along the left/right edge in the
  frame padding (`_FRAME_PAD`), no gridlines. The cell address is computed from each actor's projected
  centroid/bbox in the SAME `_scene_geometry` world→pixel map the render already builds, so the legend
  and image cannot drift.
- **Output:** the `name → cell` legend to **stderr** (human summary, per convention); the machine form
  via `--json` (an actor→{pane→cell, span, hidden} map) so a script gets structure, not text.
- **Coordinate is image-space**, not world-space: `D4` is a region of that projection, not a world
  cell — documented so it is not mistaken for a world coordinate.

## Distinct from the render-parity item (`actor-preview-unrealed-render-parity-new-csg`); can build
independently, but the hidden-actor rule couples to that item's `textured` world mode.
