+++
priority = "p1"
kind = "implement"
summary = "Per-surface texture verbs — all 5 steps shipped"
+++

# Per-surface texture verbs

Shipped: steps 2-4 (`align wall|floor|run` subcommands, editor projection family, connected run +
`--turn`) and step 5 (`TextureResolver.dimensions`, `align one-tile`, `scale --to`, the
`--fit-perimeter` whole-tile fix). `uedcli/utexture.py`, `uedcli/polyalign.py`, `uedcli/surface.py`,
`uedcli/cli/parsers/brush.py`; design choices in `dev/docs/rationale/polyalign.md`.
