+++
priority = "p2"
kind = "chore"
summary = "`level photo --game`'s INTERNAL materialize runs the H3 post-verify, with no way to skip it"
+++

# `level photo --game`'s INTERNAL materialize runs the H3 post-verify, with no way to skip it

A preview `.dx` is throwaway, so verifying it buys nothing and any post-verify mismatch
blocks previewing the level at all — the failure mode that made the mover `Saved*` bug (fixed
2026-07-25) block previews as well as builds. `level photo --game` does not expose
`--no-verify`; today's workaround is the two-step `level materialize --no-verify --out foo.dx`
then `level photo --game --map foo.dx`. Preview's internal build should skip the verify (or
expose the flag). (Split out of the mover `Saved*` item when that was fixed, 2026-07-25.)
