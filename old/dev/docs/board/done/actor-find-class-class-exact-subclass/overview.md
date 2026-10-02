+++
priority = "p?"
kind = "unknown"
summary = "`actor find --class` → `--class-exact` + `--subclass-of`"
+++

# `actor find --class` → `--class-exact` + `--subclass-of`

— BUILT 2026-07-19 (WIDE breaking,
2-reviewer cold-gated). `--class-exact` = exact match (old behaviour); `--subclass-of` =
descendant-aware via `ClassIndex.descends_from` (expands to level classes descending from a base);
the two OR in `dispatch._find_class_filter`. Bare `--class` REMOVED via a `_RemovedFlag` (errored +
blocks argparse abbreviation resurrecting the footgun). Reviewers caught 3 missed stale refs
(README, two find `--help` strings) — fixed. cli/dispatch/usage/architecture + `test_cli`/
`test_dispatch`; decision 13:30 UTC; leveldesign KB docs deferred to inbox. Commits `1d9dc2d48`,
`8b9e523e0`.
