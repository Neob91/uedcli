+++
priority = "p3"
kind = "unknown"
summary = "actor preview grid: the per-actor `hidden` bool (legend `(hidden)` + JSON `hidden`) aggregates the per-pane hidden flags as AND (hidden in EVERY pane). Underspecified in the spec — recording the call."
+++

# Preview grid: quad `hidden` aggregation is provisional

The spec fixes a single `hidden` bool per actor (JSON `actors.<name>.hidden`; legend `(hidden)` suffix)
and per-pane cells, but does not say how the bool is derived under `--layout quad`, where an actor can
draw in some panes and not others.

**Call made (implemented):** aggregate as AND — an actor is `hidden` only when it drew nothing in
EVERY pane. Rationale: the owner's hidden case is a `--faces textured` add outside subtracted space,
which renders nothing in every projection, so AND is the faithful reading of "flag the invisible ones".
A depth-occlusion that only hides an actor in one view leaves it visible elsewhere, so it is not
flagged. Single-view/breakdown reduce to that one pane.

`_grid_legend_lines`/`_grid_json` in `uedcli/cli/rendering.py` (`all(c.hidden for c in cells.values())`).

If the owner wants per-pane hidden surfaced in quad (e.g. `Top:D4(hidden)`), that is a different shape
and a separate change.
