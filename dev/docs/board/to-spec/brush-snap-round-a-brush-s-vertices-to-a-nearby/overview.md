+++
priority = "p2"
kind = "implement"
summary = "`brush snap` — round a brush's vertices to a nearby grid (T3D filter)"
+++

# `brush snap` — round a brush's vertices to a nearby grid (T3D filter)

A stateless
filter that reads a brush T3D on **stdin** and emits the snapped brush T3D on **stdout** (pipes like
`brush clip`/`intersect` → `actor add -` / `brush replace`). Two params: **`--grid N`** = the grid size
to snap to (e.g. 16 / 8 / 1), and **`--tolerance T`** = how close a vertex must be to a grid line to
snap — a vertex farther than T from the grid is **left in place**, so *intentional* off-grid geometry
(angled/rotated/curved brushes) is preserved and only near-grid **float-noise / slop** is corrected.
**DECIDED (Andrzej): snap the brush's LOCAL vertices, NOT world coords** — clean the authored geometry
independent of the actor's Location/Rotation/Scale transform, per-axis. **Motivation:** real/imported DX
brushes carry sub-unit off-grid noise (e.g. WanChai `Brush615` at x≈-62.5455 ±1e-4), and off-grid coords
are the main cause of BSP holes (`docs/leveldesign/general/geometry-and-bsp.md`); snapping the noise (not
the angles) cleans geometry for reliable CSG. Spec the exact snap/round rule (round-half behavior),
single-brush vs a brush SET on stdin, and whether a `level doctor`/lint tie-in should FLAG near-grid
slop. (Andrzej, 2026-07-25.)
