+++
priority = "p3"
kind = "implement"
summary = "Subtractive CSG: remaining CLI surface"
+++

# Subtractive CSG: remaining CLI surface

Closed verify+document (owner ruling 2026-08-02, no new CLI surface). Verified the existing
`actor find --kind brush --prop CsgOper=CSG_Add|CSG_Subtract` covers CSG-type discovery — pinning
test in `test_dispatch.py`, doc note in `docs/usage.md`. The `--solidity` live-collision check spun
off to `to-spike/live-verify-brush-intersect-deintersect`.
