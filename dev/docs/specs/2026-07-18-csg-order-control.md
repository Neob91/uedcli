# CSG-order control — `actor order` + `actor add --order`

**Status:** spec (ephemeral). **Ledger:** [`decisions.md` 2026-07-18](../decisions.md).
**Closes** the inbox item "No CSG-order control — can't place a brush FIRST" (and reinforces the
`brush resize` item, which is blocked by the same gap).

## 1. Motivation
CSG precedence is the trunk's `(order_value, name)` sort (`architecture.md`; `order_value` is a
per-actor LexoRank sidecar). Today `actor add` only ever **appends** (mints a rank after the current
max — `trunk.append_rank`), and no verb reorders an existing actor. Consequences hit repeatedly in
dogfooding:
- realizing mid-build you need a world **SUBTRACT under everything** (lowest CSG order) means deleting
  every brush and rebuilding subtract-first;
- **in-place room resize** is impossible: a delete + re-add of the low-order `World` subtract lands it
  at the highest order and carves the whole level.

## 2. Surface (both a reorder verb and a place-at-add flag — decision)

### `actor order <names…|-> (--first | --last | --before NAME | --after NAME)`
Reorder EXISTING actors by minting new `order_value`s. Exactly one selector (mutually-exclusive,
required):
- `--first` — before the current minimum rank (new lowest CSG order).
- `--last` — after the current maximum (new highest).
- `--before NAME` — immediately before `NAME` (between `NAME`'s predecessor and `NAME`).
- `--after NAME` — immediately after `NAME` (between `NAME` and its successor).

`-` reads names from stdin (the compose-pipe spec). **Multi-actor = block move preserving relative
order** (decision): the named set is sorted by its *current* order, then given **consecutive** new
ranks in the target gap, so their internal CSG order is unchanged and they land contiguously.

### `actor add --order (first | last | before=NAME | after=NAME)`
Place NEW actor(s) at that CSG position instead of appending. **Default `last`** (today's behavior,
unchanged). Multiple actors added in one invocation keep their emit order, placed as a block at the
target.

## 3. Mechanics (LexoRank — `trunk.rank_between`)
All positions reduce to "mint K consecutive ranks strictly between neighbours `lo` and `hi`" (either
may be `None` = open end):
- `--first`: `lo=None`, `hi=min(current ranks)`. `--last`: `lo=max`, `hi=None` (== `append_rank`).
- `--before NAME`: `hi=rank(NAME)`, `lo=` the rank just below it (the predecessor in sorted order, or
  `None`). `--after NAME`: `lo=rank(NAME)`, `hi=` the successor's rank (or `None`).
- K consecutive ranks: iterate `rank_between(lo, hi)` → `r1`, then `rank_between(r1, hi)` → `r2`, …
  (each new rank becomes the next `lo`). `rank_between` already grows length when neighbours are
  adjacent, so a tight gap never exhausts.

The change is an **order_value-only** write. **⚠ CORRECTION (review B1) — this needs a new seam;
the original "save's delta diff already detects a reorder" claim was FALSE.** `TrunkLevelSource.save`
(`dispatch.py:919-952`) **re-derives** every existing actor's rank from the load snapshot
(`ranks[name] = self._ranks[name] if name in self._ranks else append_rank(...)`, line 929), so a
`Level` (which carries only `level.order`, a name list — no per-actor `order_value`) can NEVER change
an existing rank, and a new actor ALWAYS appends. The required design:
- **Add a `ranks` override param to `TrunkLevelSource.save`** (`save(..., ranks: dict[str,str]|None =
  None)`): for a name present in the override, use the override value instead of the line-929 rule;
  otherwise unchanged. The override flows straight into the existing `trunk.write_level(..., ranks)`
  argument (which already takes a full ranks dict), and the `changed` set (line 942-944, `ranks[name]
  != self._ranks.get(name)`) then **correctly** fires because the override differs from the untouched
  load snapshot — do NOT mutate `self._ranks` before the write, or the diff self-cancels.
- `actor order` computes the override for the moved set and calls `save(ranks=override)`;
  `actor add --order` puts the new actor's chosen rank in the override too (so it isn't appended).
- `canonical_level_hash` folds in `level.order` (`normalize.py:196`), so a *persisted* reorder is a
  real CSG state change (correct — once the seam above makes it persist).

## 4. Guards / edges (each a named exit-2, never a traceback)
- `--before/--after NAME`: `NAME` must exist (case-insensitive resolve) → else exit 2 naming it.
- `NAME` may not be in the moved set (`actor order A --before A`) → exit 2 (ordering relative to self).
- Unknown actor in `<names>` → exit 2 naming it; all-or-nothing (validate every name before writing).
- `--order before=NAME`/`after=NAME` on `actor add`: same not-found guard; `NAME` resolved against the
  trunk the add targets.
- Duplicate `order_value`s already possible (imported/hand-edited) — this verb never *creates* one
  (fresh ranks are strictly between neighbours); it does not attempt to repair pre-existing dupes
  (that stays `level doctor`'s WARN).

## 5. Testing (offline)
- Each selector mints a rank landing the actor at the intended sort position (`--first` lowest,
  `--last` highest, `--before/--after NAME` adjacent to NAME); the resulting `(order_value, name)` sort
  matches the intended CSG order.
- Multi-actor `order A B C --first`: A/B/C keep their prior relative order and land contiguously at the
  front; likewise `--before NAME`.
- Adjacent-rank gap (neighbours with no room) → `rank_between` grows length, still strictly between
  (no exhaustion, no dupe).
- `actor add --order first|before=NAME|after=NAME` places the new actor at the right sort position;
  default (no flag) still appends.
- Guards: missing `NAME`, self-reference, unknown moved actor — each exit 2, trunk untouched.
- A reorder-only change persists (delta-write detects the rank delta) and changes `canonical_level_hash`.

## 6. Touchpoints
`trunk.py` (a `ranks_between(lo, hi, k)` helper over `rank_between`) · **`order_ops.py`** (the natural
home — today just `order_after_add`/`order_after_delete`; add `compute_reorder_ranks(current_ranks,
moved, selector, ref) -> dict` that does the neighbour-exclude + K-consecutive minting) ·
**`dispatch.py` `TrunkLevelSource.save` — the `ranks=` OVERRIDE seam (§3; the make-or-break change,
omitted in the first draft)** · `dispatch.py` (`actor order` handler; `_apply_set`/`actor add` honor
`--order`, passing the chosen rank into `save(ranks=…)`) · `cli.py` (`actor order` subparser with the
mutually-exclusive selector group + `-`; `actor add --order`). Pure model-side; no editor.

## 7. Review-gate resolutions (2026-07-18 — two cold reviews; OVERRIDE conflicting prose above)
Both reviewers verified against the code. Corrections:
- **B1 — the `save(ranks=…)` override seam is REQUIRED** and was missing (see §3). Without it both
  `actor order` and `actor add --order` are inert. Highest-priority build step.
- **B2 — neighbour lookup for `--before/--after NAME` MUST exclude the moved set.** The predecessor/
  successor that bound the target gap are computed over actors **not** being moved; else the K new
  ranks are minted against a rank that is simultaneously being reassigned (non-strict / colliding).
  `compute_reorder_ranks` filters the moved set out before finding neighbours.
- **`rank_between` CAN raise `ValueError`** on genuinely-adjacent INGESTED ranks (`trunk.py:48-50`,
  e.g. between `a` and `a0`) and on `--first` when the current min is a smallest-digit rank
  (`rank_between(None,'0')` raises — the docstring warns). uedcli-minted ranks avoid this, but
  `actor order` runs on arbitrary/imported trunks. **Catch the `ValueError` around the mint loop → a
  named exit-2** ("cannot reorder: no order_value fits between X and Y — the trunk has adjacent
  imported ranks"), never a traceback (§4 / CLAUDE.md).
- **Trunk-only:** `actor order` and `actor add --order` are meaningless on `--target stash|prefab`
  (flat `order`, no `order_value` sidecar) → **exit 2** ("ordering applies only to a level target"),
  mirroring the folders spec's trunk-only guard.
- **Concurrency:** the flock covers only the write, so two concurrent `order X --first` can mint the
  same value below a shared observed-min — a **possible duplicate order_value**, NOT impossible as
  §4 implied. It degrades harmlessly to the name-tiebreak (same as concurrent adds, decisions
  2026-07-05 15:11); `level doctor` still WARNs. Don't claim impossibility.
