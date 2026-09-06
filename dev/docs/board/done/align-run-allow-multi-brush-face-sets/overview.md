+++
priority = "p2"
kind = "implement"
summary = "brush poly align run: drop the one-brush restriction, walk a run across multiple brushes"
+++

# align run: allow multi-brush face sets

Done. `brush poly align run` now walks a connected run across any number of brush actors (composite
`(brush, poly)` keys throughout `_run_prewalk`/`_run_adjacency`/`_run_align` in `uedcli/polyalign.py`,
replacing the old single-brush guard). Docs and rationale updated; new tests cover multi-brush
positive/disconnected/branch/`--fit-perimeter`/`--turn`/mixed-CSG-polarity cases.
