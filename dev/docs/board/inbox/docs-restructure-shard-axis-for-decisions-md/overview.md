+++
priority = "p1"
kind = "owner-question"
summary = "Docs restructure: shard axis for `decisions.md`"
+++

# Docs restructure: shard axis for `decisions.md`

All 3 reviewers:
entries are 46 in 2026-06 / 181 in 2026-07, so a monthly shard leaves `2026-07.md` at ~7,030
lines — 78% of the original, against a D4 rationale that rejected one-file *because* it is ~9k
lines. Options: topic/subsystem axis (loses order-preservation, which C1's verification depends
on), fixed entry-count, prune-first-then-remeasure, or keep monthly and drop the size rationale.
