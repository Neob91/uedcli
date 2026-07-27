+++
priority = "p?"
kind = "unknown"
summary = "`actor duplicate` verb"
+++

# `actor duplicate` verb

— BUILT 2026-07-19 (2-reviewer cold-gated). Sugar for `actor show <names>
| actor add -`: copies actors in place with fresh names, prints them to stdout (both a `-`/stdin
CONSUMER and a producer). Extracted the `actor add` ingest body into a shared
`dispatch._ingest_actor_t3d(args, src, level, text, *, verb)` (reviewer-confirmed behavior-preserving
for add); `--folder` override + `--target`; folder guards extended to `duplicate`. Docs
(usage/architecture) + 5 tests. Commit `c3bfb1d1c`.
