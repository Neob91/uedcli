# Spec — subtractive CSG: the remaining CLI surface

DRAFT. Surfaces the owner decision(s); do not build past an unanswered question.

## Goal

Enumerate what CSG-authoring CLI surface is still missing, reconcile the stale board note with what
actually shipped, and propose the one real remaining verb/flag.

## Current state — reconciling the overview with reality

The overview predates the `generators.md` rulings and is stale on three points:

- **"intersect/deintersect superseded by `stash intersect`/`stash deintersect`"** — WRONG. The shipped
  verbs are `brush intersect` / `brush deintersect` (`cli/parsers/brush.py:362-375`;
  `cli/commands/brush/edit.py:merge`), taking a T3D brush set on stdin.
  `generators.md` explicitly rejects stash/prefab wrappers ("every tier feeds them through its own
  `show`"). `stash intersect` does not exist (grep-confirmed). No work here beyond fixing the note.
- **(2) "wire `--solidity` through a live verification"** — `brush intersect/deintersect --solidity`
  already EXISTS (`brushcsg.apply_solidity`, `brushcsg.py:297`; faithful per-face default). What
  remains is a *live spike* confirming the built map's collision matches the per-face rule — a
  `to-spike` task, not a CLI change. Out of scope for this spec; flag it for a separate item.
- **(3a) "expose CSG order as a CLI verb"** — DONE: `actor order` (`cli/commands/actor/edit.py:72`,
  `order_ops.py`), trunk-only LexoRank reorder. Doc note only.

What is genuinely missing:

- **Select-by-type (additive vs subtractive).** `actor find` filters by `--kind point|brush`
  (`cli/parsers/brush.py`… `query.list_actors`, `query.py:179-240`) but has **no `--csg add|subtract`
  filter**, though `query._csg_oper` (`query.py:276-282`) already computes it. "find all subtractive
  brushes" (to reorder, retexture, or preview rooms) has no verb.
- **`brush find` / `brush list`** (the overview's "unify the fragmented brush namespace") do not
  exist. Whether they SHOULD is a convention call — see the question.

## Design — CLI surface

### 1. `actor find --csg add|subtract` (recommended, the one real gap)

Add a `--csg {add,subtract}` filter to `actor find`, ANDing with the other filters, matching on
`query._csg_oper` (`CsgOper` prop; absent counts as `CSG_Add`).

    --csg {add,subtract}
        keep only brush actors whose CSG operation is add / subtract (CsgOper; an unset CsgOper
        counts as add). A point actor, or a base Mover (no CsgOper), never matches. ANDs with the
        other filters, e.g. `actor find --kind brush --csg subtract` selects every carve.

Plumb a `csg` param into `query.list_actors` alongside `kind` (`query.py:191`), filtering in
`_passes` (`query.py:236-239`). Point actors and movers (no `CsgOper`) do not match either value.

### 2. Reconcile docs (no new verb)

State plainly that CSG-set authoring is `brush intersect`/`brush deintersect` (on `brush`), CSG
reorder is `actor order`, and brush discovery is `actor find --kind brush [--csg …]`. Update
`docs/usage.md`/`docs/leveldesign/` where they imply otherwise.

### 3. `--solidity` live verification → separate spike

`--solidity` is implemented; only a live confirming spike remains. It belongs in its own `to-spike`
item, not this one (I cannot file board items from here — flag it for the owner/next session).

## Edge cases & errors

- `actor find --csg subtract` with no matching actors → empty stdout, exit 0 (a filter matching
  nothing is not an error — existing `find` behaviour).
- `--csg` combined with `--kind point` → matches nothing (a point actor has no CsgOper); allowed, not
  an error.
- Unknown `--csg` value → argparse `choices=` rejects, exit 2.

## Tests

- `test_find_compose.py` / `test_cli.py`: a trunk with additive + subtractive brushes + a light —
  `--csg subtract` returns only carves; `--csg add` returns additives (incl. `CsgOper`-absent);
  `--kind point --csg add` returns nothing; ANDs with `--within-bbox`.
- Refresh `tests/fixtures/parser_baseline/*` — new `--csg` choice.

## Open questions

See `questions/add-brush-find-list-or-keep-on-actor-find.md`.
