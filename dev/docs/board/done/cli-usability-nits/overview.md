+++
priority = "p?"
kind = "unknown"
summary = "CLI usability nits (batch)"
+++

# CLI usability nits (batch)

— 4/7 DONE 2026-07-19: `--facing -X/-Y/-Z` space form now parses
(`_FACING_NEG` in `_CoordArgumentParser`, regression in `test_cli.py`); `mover key add` help
clarified (key 0 = base, first add = key 1); `prop get` help notes Rotation reads back in raw rotator
UNITS (get/set round-trip, `actor rotate` is the degree verb); `--at` anchor doc was ALREADY present.
Commit `18913531b`. **Remnants → `inbox.md` (3, deferred with tradeoffs):** `--prefab-dir` position
consistency (touches the documented `prefab [--prefab-dir] <sub>` form), single-name-verb-multi-name
scoped error (argparse wart), and upstream-pipe-error-as-data (fuzzy detect/annotate).
