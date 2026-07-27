# Plan — CSG-order control (`actor order` + `actor add --order`)

**Spec:** [`spec.md`](spec.md)
(its **§7 review-gate resolutions OVERRIDE conflicting prose**). Ledger: `decisions.md` 2026-07-18.
Pure model-side, offline, no editor.

## Build order (the seam first — it's make-or-break)

### 1. The `save(ranks=…)` override seam — `dispatch.py` `TrunkLevelSource.save` (§3 / §7 B1)
Today `save` re-derives every existing actor's rank from the load snapshot (`self._ranks[name] if
name in self._ranks else append_rank(...)`), so a `Level` can never change an existing rank and a new
actor always appends. Add an override channel:
- `save(*, verb, args, level, touched, ranks: dict[str,str] | None = None)`. For a name present in
  `ranks` (the override), use the override value; else the existing line-929 rule (unchanged).
- The resolved per-actor dict flows into the existing `trunk.write_level(..., <resolved>)` arg.
- Do **NOT** mutate `self._ranks` before the write — the `changed`-set diff
  (`resolved[name] != self._ranks.get(name)`) must see the *old* snapshot so a rank-only delta fires.
- `StashLevelSource.save`/`PrefabLevelSource.save` gain an ignored `ranks=None` param (flat `order`,
  no `order_value` sidecar) so the seam signature is uniform; the guards below mean they never
  receive a real override.

### 2. `trunk.py` — `ranks_between(lo, hi, k)` over `rank_between`
K distinct ascending ranks strictly between `lo` and `hi` (either `None` = open end), minted by
iterating `rank_between` (each new rank becomes the next `lo`). Propagates `rank_between`'s
`ValueError` on a genuinely-adjacent imported gap.

### 3. `order_ops.py` — `compute_reorder_ranks` / `compute_add_ranks` (§7 B2)
- `_placement_gap(current_ranks, selector, ref, exclude) -> (lo, hi)` — neighbour boundaries with the
  `exclude` set filtered out (the moved set for reorder; empty for add). `first`→`(None, min)`,
  `last`→`(max, None)`, `before NAME`→`(pred, rank(NAME))`, `after NAME`→`(rank(NAME), succ)`, where
  pred/succ are over the NON-excluded actors sorted by `(order_value, name)`.
- `_mint(lo, hi, k)` — raises a clean `ValueError` if `lo >= hi` (duplicate/adjacent), else
  `trunk.ranks_between`.
- `compute_reorder_ranks(current_ranks, moved, selector, ref)` — exclude=moved; sort moved by their
  CURRENT `(order_value, name)` (block move preserves relative order); zip onto K minted ranks.
- `compute_add_ranks(current_ranks, new_names, selector, ref)` — exclude=∅; keep `new_names` in emit
  order; zip onto K minted ranks.

### 4. `cli.py`
- `actor order <names…|-> (--first | --last | --before NAME | --after NAME)` — variadic names +
  a required mutually-exclusive selector group; `_target_flag`.
- `actor add --order POS` — default `last`; `first | last | before=NAME | after=NAME`.

### 5. `dispatch.py` handlers
- Pre-resolve trunk-only guards (before `_resolve_level_source`, like the folder guards): reject
  `actor order` and `actor add --order <non-last>` on `--target stash|prefab` (exit 2, named).
- `actor order` handler: `_resolve_target_names` (`-`/stdin) → empty ⇒ exit 0; resolve+dedupe moved
  names (unknown ⇒ exit 2); resolve `--before/--after NAME` (unknown ⇒ exit 2; in moved set ⇒ exit
  2); `compute_reorder_ranks(src._ranks, moved, selector, ref)` catching `ValueError` → named exit
  2; `src.save(..., ranks=override)`.
- `actor add` handler: parse `--order`; for a non-`last` placement resolve the ref, compute
  `compute_add_ranks` (catch `ValueError` → exit 2), pass `ranks=override` into `save`; `last` keeps
  `ranks=None` (today's append, unchanged).

## Tests (spec §5 + §7) — `tests/test_order_ops.py`, `tests/test_order_verbs.py`, `tests/test_level_source.py`
Each selector lands the right sort position; multi-actor block move preserves relative order incl.
NON-contiguous sets; neighbour-exclude correctness; `rank_between` exhaustion (`a`/`a0`) → exit 2;
`--first` against a `'0'` min → exit 2; a reorder-only change PERSISTS and changes
`canonical_level_hash`; `actor add --order`; trunk-only guard; each named guard; `actor order -`
from stdin.

## Docs / board
- `architecture.md` Commands: note `actor order` + `actor add --order` and the `save(ranks=)` seam.
- Move the item from `board/to-plan/` to `board/done/`.
