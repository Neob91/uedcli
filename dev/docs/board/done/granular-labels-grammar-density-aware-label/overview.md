+++
priority = "p?"
kind = "unknown"
summary = "Granular `--labels` grammar + density-aware label placement"
+++

# Granular `--labels` grammar + density-aware label placement

— BUILT 2026-07-22.
`actor preview`'s single `--labels {none,all,highlighted}` switch is replaced by a composable
colon-filter grammar parsed to a `LabelSpec` (bare kind = ALL, filters narrow, commas union; kinds
`poly`/`name`, filters `vis`/`hi`/`brush`/`point`; keywords `none`/`all`/`highlighted`; default
`poly:vis,poly:hi,name`). Adds **brush-name labels** (net-new). All three label kinds place through
one pass that minimises a cost over a geometry `DensityGrid` (flee dense knots, never cover a point
icon, moderate drift cap); brush names anchor at the least-dense point on their own wireframe. Spec
+ plan cold-review-gated (spec + Part-A gates); decisions 2026-07-22 09:54 UTC; spec
`specs/2026-07-22-labels-granularity.md`, plan `plans/2026-07-22-labels-granularity-plan.md`. Tests
in `test_preview.py`/`test_cli.py`/`test_actor_preview.py`.
