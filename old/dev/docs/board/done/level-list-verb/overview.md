+++
priority = "p?"
kind = "unknown"
summary = "`level list` verb"
+++

# `level list` verb

— BUILT 2026-07-19 (2-reviewer cold-gated). Enumerates the project's levels
(trunk dirs with an `actors/` tree under `<maps>`, dotted dirs skipped), one name/line to stdout
(pipe-friendly) + count/selected to stderr; `--json` → `[{name, selected}]`. New
`level_select.list_levels` helper; `dispatch._level_list`; docs (architecture/usage) + 11 tests.
Review fixes: stale-selection flagged on stderr (kept consistent with --json), dot-guard test now
exercises the guard. Commit `1e4ca932d`.
