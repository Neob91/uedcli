+++
priority = "p3"
kind = "implement"
summary = "Exact-single-node folder match (no subtree)"
+++

# Exact-single-node folder match (no subtree)

p3. Deferred from actor-folders v1:
a wildcard-free `--folder X` now selects X's whole subtree, and `--prop Group=` no longer reaches
the folder (it's a sidecar, not a prop), so there is no form for "exactly this folder, excluding
descendants." A niche need — add later, e.g. `--folder-exact` or an `=path` sigil. Andrzej,
2026-07-18.
