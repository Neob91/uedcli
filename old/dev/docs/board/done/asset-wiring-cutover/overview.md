+++
priority = "p?"
kind = "implement"
summary = "The config's asset directories drive the container mounts and the editor `Paths` (shipped 2026-07-14)"
+++

# Asset wiring cutover

Before this, the directories mounted into the editor/preview containers and the `Paths` lines
written into the editor's ini were hardcoded in two places that could disagree. After it, both are
derived from the configured asset directories. Shipped 2026-07-14; the follow-on parts are their own
board items.

This item exists to hold the spec, which no board entry owned.
