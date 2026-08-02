# Spec — subtractive CSG: the remaining CLI surface

## Goal

Reconcile the stale board note with what actually shipped, and confirm that CSG-type discovery needs
**no new CLI surface** — it lives on the existing `actor find --prop CsgOper=…`.

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

Nothing new is genuinely missing. **Select-by-type (additive vs subtractive) already works** through
the existing `actor find --prop` (verified live 2026-08-02, see Decisions):

    actor find --kind brush --prop CsgOper=CSG_Subtract    # every carve
    actor find --kind brush --prop CsgOper=CSG_Add         # every additive

`CsgOper` is a declared `ECsgOper` enum on `Engine.Brush`, and `--prop` matches it type-aware
(enum name == ordinal). So no `--csg` flag is added, and `brush find`/`brush list` are not added
(owner ruling 2026-08-02) — a second discovery surface duplicating `actor find` is what
`conventions.md` "one stateless query verb" rejects.

## Design — no new CLI surface

This item is **verify + document + close**. There is no code to add.

### 1. Reconcile docs

State plainly in `docs/usage.md`/`docs/leveldesign/` that:
- CSG-set authoring is `brush intersect`/`brush deintersect` (on `brush`), fed a T3D set on stdin.
- CSG reorder (precedence) is `actor order` (trunk-only LexoRank).
- **Brush/CSG-type discovery is `actor find --kind brush [--prop CsgOper=CSG_Add|CSG_Subtract]`** —
  there is no `brush find`/`brush list` and no `--csg` flag.

### 2. `--solidity` live verification → separate spike

`brush intersect/deintersect --solidity` is implemented (`brushcsg.apply_solidity`); only a live
spike confirming the built map's collision matches the per-face rule remains. That is a `to-spike`
task, filed as its own board item — out of scope here.

## Decisions

- **No `brush find`/`brush list`, and no new `actor find --csg` flag** (owner, 2026-08-02).
  CSG-type discovery uses the existing `actor find --prop CsgOper=…`.
- **Verified live (2026-08-02)** on a trunk with one `CSG_Subtract` cube, one `CSG_Add` cube, and a
  `LevelInfo`, resolved against the Deus Ex `.u` at `uned/UED22`:
  - `actor find --prop CsgOper=CSG_Subtract` → the subtractive only, exit 0.
  - `actor find --prop CsgOper=CSG_Add` → the additive only, exit 0.
  - `actor find --kind brush --prop CsgOper=CSG_Subtract` → ANDs correctly.
  - `--prop CsgOper=CSG_Bogus` → exit 2, `'CSG_Bogus' is not a value of ECsgOper (…)`.
  - Schema: `CsgOper` declared on `Engine.Brush`, enum `ECsgOper`
    `(CSG_Active, CSG_Add, CSG_Subtract, CSG_Intersect, CSG_Deintersect)`, class default `CSG_Active`.
  - Handler: `cli/commands/actor/query.py:68-119` (`--prop` → `propedit.effective_match`); the enum
    comparison is `propedit`'s designed behaviour (`--prop` help, `cli/parsers/actor.py:51-56`).

Two caveats to note in the doc, both correct:
- **A `CsgOper`-absent brush matches `CSG_Active`, not `CSG_Add`.** `--prop` reads the *class default*
  (`CSG_Active`) when the prop is unset, whereas uedcli's internal `query._csg_oper` treats absent as
  `CSG_Add`. This diverges only for the red builder brush (the sole brush that omits `CsgOper`); every
  placed world brush carries an explicit `CSG_Add`/`CSG_Subtract` (`normalize.py:145-146`), so
  `--prop CsgOper=…` classifies all real world brushes correctly.
- **A considered set with no brush errors.** `actor find --kind point --prop CsgOper=CSG_Add` exits 2
  (`no considered actor's class declares CsgOper`) — `--prop`'s typo-protection, not an empty result.
  The canonical spelling `actor find --kind brush --prop CsgOper=…` always includes brushes when any
  exist. (This differs from the rejected `--csg` design, which would have returned empty here.)

## Tests

- `test_find_compose.py` (or `test_cli.py`): a trunk with additive + subtractive brushes + a light,
  built against the game `.u` (integration-marked if the offline suite has no schema) —
  `--prop CsgOper=CSG_Subtract` returns only carves, `--prop CsgOper=CSG_Add` only additives,
  `--kind brush --prop CsgOper=CSG_Subtract` ANDs, invalid enum value exits 2. One test pins that
  `--prop CsgOper=` discovers CSG type, so the documented workflow cannot silently rot.
- No parser-baseline refresh (no flag added).
