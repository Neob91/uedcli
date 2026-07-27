+++
priority = "p3"
kind = "implement"
summary = "The two profile generators have NO editor-blessed parity case"
+++

# The two profile generators have NO editor-blessed parity case

All six
parametric shapes are pinned against real-editor captures by `tests/builder_parity_cases.py`;
`extrude`/`revolve` ship with SELF-blessed goldens (`fixtures/builder_extrude.t3d`,
`builder_revolve.t3d`), which pin drift, not correctness. Adding a parity case needs the
`integration`-gated capture run against a live editor. Note the two families already dropped from
the live capture suite (`OFFLINE_ONLY`: staircase, spiral) were dropped because the DEINTERSECTION
readout invents vertices on non-convex / non-axis-aligned geometry — a swept profile is likely to
hit the same wall, so this may end up offline-only too.
