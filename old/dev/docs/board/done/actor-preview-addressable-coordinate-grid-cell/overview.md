+++
priority = "p2"
kind = "implement"
summary = "actor preview: an addressable coordinate grid — a gutter of column/row labels + a per-actor cell ref on stderr, so a render can be cross-referenced to a name set in text."
+++

# actor preview: addressable coordinate grid — BUILT

Always-on gutter (columns A,B,C… / rows 1,2,3…, no gridlines), a `name → cell` stderr legend (centroid
+ span, pane-qualified under quad, `(hidden)` for a drew-nothing actor), a `--json` map, and `--grid N`
(default 12, `[1,52]`). `preview.py` cell math + `_framing` gutter inset + `_scene_geometry.actor_points`;
`cli/rendering.py` legend/JSON + `--grid` validation. Docs in `docs/usage.md` +
`docs/leveldesign/general/design-craft.md`; default-density rationale in `rationale/preview.md`.
Provisional call filed: `preview-grid-quad-hidden-flag-aggregates-as`.
