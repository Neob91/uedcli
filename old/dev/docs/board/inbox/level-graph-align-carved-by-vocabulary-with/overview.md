+++
priority = "p?"
kind = "unknown"
summary = "level graph: align carved_by/vocabulary with actor survey"
depends-on = ["actor-survey-and-actor-relation-csg-resolved"]
+++

# level graph: align carved_by/vocabulary with actor survey

`actor survey`'s spec (board item `actor-survey-and-actor-relation-csg-resolved`) settled on one
name per relation, consistently: `carves`, with the Subtract (agent) always leading regardless of
which side is surveyed. This deliberately does not match `level graph`'s own shipped output, which
still uses `carved_by` with the Add (victim) leading (`uedcli/actorgraph.py::classify_pair`).

`actor survey`'s own scope was deliberately kept to just the new verb — it does not touch
`level graph`, on the owner's explicit instruction ("focus on getting `actor survey` clean, ignore
what `level graph` does, we'll want to revisit that"). This item is that revisit.

Bring `level graph` in line with `actor survey`'s now-settled conventions:
- Rename `carved_by` → `carves`, Subtract leading (matching `actor survey`'s raw tier exactly).
- Re-check whether any of `actor survey`'s other presentation choices (e.g. its per-relation
  directionality table) should also change how `level graph` presents its own, still purely-raw
  output — `level graph` has no CSG tier and never will under this design, so most of that table
  doesn't apply, but the `carves` rename does.
- Update `level graph`'s own tests (`uedcli/tests/test_actorgraph.py`, `test_cli_level_graph.py`)
  and docs (`docs/reference/level/graph.md`) for the rename.
- Check callers/consumers of `level graph`'s current `carved_by` output for the same rename
  (agent-facing docs, any plugin skill referencing it by name).

Not started — filed for triage, no spec written yet.
