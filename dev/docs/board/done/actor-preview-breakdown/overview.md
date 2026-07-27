+++
priority = "p2"
kind = "unknown"
summary = "`actor preview --breakdown` — per-brush grid"
+++

# `actor preview --breakdown` — per-brush grid

(+ `--zoom` name/poly, `--brush-colors`,
legend-reserve) — BUILT 2026-07-23. p2. A near-square GRID (`ceil(sqrt(N))` cols) of panes: pane 0 is
the whole scene in CSG with a name-only legend (roster incl. point actors, no numbers); each
following pane is ONE brush, `--focus`ed + zoomed to its AABB with all faces numbered + name
captioned. Point actors get no pane (named in the overview). `dispatch._render_breakdown_grid`, Pillow
stitch (kept in dispatch — `preview.py` buffers are square-only). Replaces **`--split`** (the
non-shadowing number-group
filmstrip, built 2026-07-22 then superseded same-week): `--breakdown` sidesteps number-overlap by
giving each brush a big zoomed shot instead of graph-coloring groups; `split_groups`/`_group_decals`/
`_boxes_overlap`/`_SPLIT_*` and the `render_brushes_pgm(only_polys=)` gate were removed. **`--zoom-poly`
→ `--zoom`** (clean rename): now frames a bare brush NAME (whole AABB) OR `BRUSH:idx` (one poly).
Kept from the `--split` work: the `_scene_geometry`/`_framing` extraction, `reserve_legend`/
`draw_legend` split (legend reserved into a band, drawn once per filmstrip), `--brush-colors
{csg,legend}`, band cap. Two cold-review passes. Decisions `2026-07-23 06:01`/`10:00 UTC`; the
`spikes/poly-split-groups/` spike is superseded (kept as history).
