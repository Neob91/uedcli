+++
priority = "p2"
kind = "debug"
summary = "Verify `write_paths_and_reload`'s `Paths=` ini-edit is redundant once `OBJ LOAD` runs"
+++

# Verify `write_paths_and_reload`'s `Paths=` ini-edit is redundant once `OBJ LOAD` runs

Spike 2 (2026-06-23) confirmed `OBJ LOAD FILE=<abs>` works without `Paths=` entries
and packages survive `MAP NEW`; the full probe was substrate-gated. To close: run a real DeusEx
content-map apply with the `Paths=` ini-edit disabled but `OBJ LOAD` kept; if it resolves, delete
`write_paths_and_reload` (and its fragile dedup check) and simplify `packages.py`.
