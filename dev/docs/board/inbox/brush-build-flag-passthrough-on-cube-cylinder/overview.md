+++
priority = "p3"
kind = "unknown"
summary = "brush build --flag passthrough on cube/cylinder/other generators needs its own decision"
+++

# `brush build --flag` passthrough on cube/cylinder/other generators needs its own decision

`brush build sheet --flag <name>` landed 2026-07-19 (a sheet is one face, so a poly flag maps
cleanly). Extending `--flag` to the other `brush build` generators is deferred: `cube`/`cylinder`/…
emit multi-face solids, where a per-face flag differs semantically from a single-face sheet — which
faces get it, and what a whole-solid flag would even mean. Wants its own decision before building.

Split out of `water-cluster-resolved-triaged-2026-07-19-live` (now in `done/`), whose sheet-`--flag`
scope is complete.
