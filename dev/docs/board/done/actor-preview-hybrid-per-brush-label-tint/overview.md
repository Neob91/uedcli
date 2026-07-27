+++
priority = "p?"
kind = "unknown"
summary = "`actor preview` HYBRID per-brush label tint + legend + `--focus`"
+++

# `actor preview` HYBRID per-brush label tint + legend + `--focus`

— BUILT 2026-07-22.
Extends the label system so a cold reader can map every label→brush even when two brushes share a
CSG op (one wireframe hue). The wireframe stays CSG-coloured; each **actor** now gets a distinct
categorical **tint** (`preview.assign_tints` → `_TINT_PALETTE`, ~10 hues, cycled) used as the accent
(leader/arrow/box-border + a faint tint WASH of the label box, `_pale`) for that brush's poly-index
labels and as the fill of a point actor's marker (a haloed filled diamond); index digits stay black.
A top-left **legend** (`_draw_legend`, one row per labelled brush = tint square + NAME, per labelled
point = tint diamond + NAME) maps tint→name, and **actor names moved OFF the geometry into it**
(`name:*` selectors gate legend rows, `poly:*` gate on-geometry indices). New **`--focus BRUSH`**
(cli/dispatch → renderer): only the focused brush shows indices (bold, its tint), every other brush
dims to a faint wireframe; **`--highlight` overrides focus** (a highlighted poly/actor stays
vivid+bold on top and keeps its index). All gated behind the `color_by_csg` (real-preview) path — the
legacy black/grey path keeps on-geometry names + no legend. Bad `--focus` name / point actor → clean
exit 2. Cold-reader validated (`_scratch/labelclarity/hybrid/`, iso @460): default views ~4.3
(two same-CSG rooms now cleanly split by tint), `--focus` ~4.7 for the dense case; beats the ~3.5
baseline. `docs/usage.md` updated. See **inbox** for two residual notes (palette-cycle collision at
11+ actors; dense-default center still busy — `--focus` is the remedy).
