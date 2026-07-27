+++
priority = "p3"
kind = "chore"
summary = "no byte-exact golden"
+++

# no byte-exact golden

byte-golden refactor guard for `_scene_geometry`/`_framing`` — the projection+framing
block extracted out of `render_brushes_pgm` (during the `--split` build, which has since been replaced
by `--breakdown`) is verified behavior-preserving only by the existing count/color/position tests;
there is **no byte-exact golden** of a fixed render guarding a future edit to those helpers (both
`_scene_geometry`/`_framing` survive `--breakdown`). A single committed golden PPM (e.g.
`brush_subtract.t3d` at a fixed size/view) would be the true guard. Flagged by the 2026-07-22
build-review gate (nit N1).
