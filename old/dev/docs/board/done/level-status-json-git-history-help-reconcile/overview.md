+++
priority = "p?"
kind = "unknown"
summary = "`level status --json` + git-history help reconcile"
+++

# `level status --json` + git-history help reconcile

— BUILT 2026-07-19. `level status --json`
emits `{kind, name, actors, duplicate_order_values, git, texture_packages}` (`{"selected": null}`
when nothing selected). Reworded the top-level `--help` "Git is the history" → clarifies it is the
project's OWN git and history exists only once it is its own repo (`level status` reports when not) —
resolving the probe's contradiction. Commit `0d70a564f`.
