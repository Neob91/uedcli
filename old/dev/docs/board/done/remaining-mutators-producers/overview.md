+++
priority = "p?"
kind = "unknown"
summary = "Remaining mutators → producers"
+++

# Remaining mutators → producers

— DONE 2026-07-19. `actor delete` / `move` / `prop set|unset`
and `brush poly set` now print their touched names to stdout (one/line) + a summary to stderr,
matching `rotate`/`scale`/`order`/`align` — so they chain via `| verb -`. (For `delete` the stdout
is the removed names, a log/count.) usage.md updated; 8 regressions (3 roundtrip tests drained the
new `set` stdout line). Commit `15bd6acd5`.
