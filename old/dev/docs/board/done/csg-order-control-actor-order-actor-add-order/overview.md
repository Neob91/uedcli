+++
priority = "p?"
kind = "unknown"
summary = "CSG-order control — `actor order` + `actor add --order`"
+++

# CSG-order control — `actor order` + `actor add --order`

— BUILT 2026-07-18 (plan
`plan.md`; spec `spec.md`; decisions same
ledger entry). `actor order <names…|-> (--first|--last|--before NAME|--after NAME)` reorders
existing actors' CSG precedence; `actor add --order (first|last|before=NAME|after=NAME)` places new
ones (default `last` == append). Multi = block move preserving relative order (incl. non-contiguous).
The make-or-break seam: `TrunkLevelSource.save(..., ranks=<override>)` — the override channel that
lets a reorder reach disk (the `changed`-diff then fires + folds into `canonical_level_hash`).
`order_ops.compute_reorder_ranks`/`compute_add_ranks` over `trunk.ranks_between`; neighbour lookup
excludes the moved set. Guards (named exit-2): trunk-only, unknown/missing/self-reference NAME,
and `rank_between` exhaustion (adjacent imported ranks, `--first` vs a `'0'` min). Folded into
`architecture.md` (Commands). Tests: `test_order_ops.py`, `test_order_verbs.py`,
`test_level_source.py`. Closes the inbox "can't place a brush FIRST" item.
