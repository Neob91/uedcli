# Spec — expose `order_value` as a human-readable CSG rank

Written for a reader who has not seen the design discussion. Terms are defined before use.

## Background

`order_value` is a per-actor LexoRank string (e.g. `"m00001"`, `uedcli/t3dtree.py`). `level.order` —
the CSG evaluation order (`trunk.py`/`t3dtree.py`) — is the `(order_value, name)` sort over every
actor's `order_value`. LexoRank is deliberately not human-readable: it supports inserting a new value
strictly between any two existing ones with no renumbering, which is why it looks like `"m00001"`
rather than `5`.

Confirmed today (2026-09-14): `order_value` is not queryable as a per-actor CLI fact anywhere — it
appears only inside `doctor`/`materialize`'s duplicate-rank warnings. In the GUI, `Inspector.tsx`
renders the raw string via `SceneActor.order_value` (`uedcli/serve/scene.py`).

**Goal.** Expose a computed **rank**: an actor's 1-based position in `level.order` (rank 1 = evaluated
/ carved first). Both surfaces:

1. a new CLI query verb, `actor rank`;
2. a `SceneActor.csg_rank: int` field, shown in the GUI inspector.

**Non-goal.** Nothing about *changing* CSG order — `actor order` already does that. This item only
makes the existing order *readable*.

## CLI: `actor rank`

```
uedcli actor rank <names…|-> [--json]
```

**Model.** A query verb (pure model-side read, no mutation), routed alongside `find`/`show`/`bbox`
(`uedcli/cli/commands/actor/routes.py`'s `("find", "show", "bbox")` tuple gains `"rank"`, dispatched
to the same `cli/commands/actor/query.py` module). It supports `--tree stash|prefab` like
`bbox`/`find`/`show` do — `level.order` is populated for all three T3D-tree kinds
(`t3dtree.read_actor_tree` / `StashLevelSource.load` / `PrefabLevelSource.load` all set it), so rank
is meaningful on any of them, not trunk-only like `actor order`/`actor label`/`actor folder`. This is
not left as an untested claim: plan Task 1 adds a `--tree stash` test case, and registers `rank` in
`uedcli/tests/test_tree_flag.py`'s central cross-verb `--tree` parametrization (the one place this
codebase tests that a content/query verb accepts the flag), alongside `actor show`'s existing entry.

**Why the shape below, not a literal copy of `bbox`'s.** The task that opened this item proposed
matching `bbox`'s convention (`names`/`-`, `--json`, `--field` for a single bare value). `bbox`'s
shape fits because `bbox` computes **one aggregate value for the whole set** (the union box) — that's
why it has `--field` to pick a face of that one result. Rank is the opposite: **one independent
scalar per actor**, no aggregation. That shape already has a precedent — `actor label get` / `actor
folder get`: "print each actor's `<property>`, one line per actor in **argument order**, as
`Name<TAB>value`; `--json` emits a JSON object mapping each canonical Name to its value." `actor
rank` follows that convention instead, borrowing only `bbox`'s `names…|-`/`--json` plumbing. No
`--field`: there is exactly one field (the rank itself), so a field-selector would be a flag with one
useless choice.

**Output — default (text).** One line per requested actor, **in argument order** (not CSG order — an
actor named later in the command line still prints later, even if its rank is numerically lower;
matches `label get`/`folder get`):

```
Name<TAB>RANK
```

`RANK` is a bare base-10 integer, no padding, `1` = first in `level.order`. Example, a level whose
CSG order is `Wall, Room, Door`:

```
$ uedcli actor rank Door Wall
Door	3
Wall	1
```

A human summary — count of actors ranked and the level's total actor count, for context ("rank 3 of
what total?") — goes to **stderr**, never stdout:

```
rank of 2 actor(s) (3 total)
```

**Output — `--json`.** A JSON object mapping each canonical actor Name to its integer rank (matching
`label get --json`/`folder get --json`'s shape), e.g. `{"Door": 3, "Wall": 1}` for the example above.
No stderr suppression — the human summary still goes to stderr under `--json`, matching every other
`--json` verb in this family.

**No bare-single-actor special case.** The task prompt that opened this item floated "or the bare
rank for a single actor" as an option. Rejected: it would be a **third** output convention (alongside
`bbox`'s single-aggregate form and `label`/`folder get`'s per-line form) for a single verb whose count
of targets is incidental — `actor rank Door` and `actor rank Door Wall` would print structurally
different things depending only on argument count, which every other multi-target query verb in this
family avoids. `Name<TAB>RANK` for exactly one actor is one line, already about as bare as useful, and
composes: `actor rank Door | cut -f2` gets the bare number when a script wants it.

**Names / stdin.** `names` — `nargs="+"` — is one or more actor Names (case-insensitive), or the
single token `-` to read a newline-separated name list from stdin (e.g. `actor find --folder castle
| actor rank -`); `-` is the sole source and is not mixable with names on the command line (the
family-wide rule). Empty stdin is a clean no-op, exit 0, no output (matching `bbox`/`show`/`order`).
Names are deduped on their canonical form, order-preserving (first occurrence wins), matching
`bbox`'s `dict.fromkeys(resolved)` pattern.

**Errors.** An unknown name is **all-or-nothing**: `query.resolve_actor_names` collects every miss
and raises once, so the CLI prints `Actors not found: <names>` to stderr and exits 2 naming every bad
name at once — identical to `bbox`'s/`show`'s existing behavior, no new error-message shape. There is
no other failure mode: rank is pure arithmetic over an already-loaded `level.order`, nothing to
validate beyond name resolution.

**Help text.** Every flag/arg carries a real `help=` (per `conventions.md`, "every flag needs help").
Sketch (final wording decided at implementation, not re-litigated here):

- `rank` subparser: `"print each actor's 1-based CSG evaluation-order position in level.order (rank 1 "
  "= evaluated/carved first) — a human-readable stand-in for the opaque order_value LexoRank string. "
  "One line per actor in argument order as Name<TAB>RANK"`
- `names`: `"actor Names to rank (case-insensitive), or the single token - to read a "
  "newline-separated name list from stdin (e.g. actor find … | actor rank -); - is the sole source, "
  "not mixable with names. Empty stdin is a clean no-op (exit 0)"`
- `--json`: `"emit a JSON object mapping each canonical actor Name to its integer rank, instead of "
  "the Name<TAB>RANK lines"`

**User docs.** `docs/reference/actor/rank.md` (new, following `bbox.md`'s / `order.md`'s shape) +
a new row in `docs/reference/actor/README.md`'s verb table, query column, next to `bbox`/`label
get`/`folder get`.

**Parser baseline fixtures.** `uedcli/tests/test_parser_baseline.py` snapshot-tests the ENTIRE live
`cli.build_parser()` tree (help text, action tree, argv corpus) against checked-in fixtures under
`uedcli/tests/fixtures/parser_baseline/`. Adding the `rank` subparser changes that tree, so
`test_help_screens_match_baseline`/`test_action_tree_matches_baseline` fail until the fixtures are
regenerated — this only surfaces on a full `bin/test` run, never on a scoped `-k actor`/`-k serve`
one. Plan Task 1 regenerates them explicitly (`python -m uedcli.tests.parser_baseline`) as part of
landing the verb, not left for the merge-time full suite to catch.

## GUI: `csg_rank` on `SceneActor`

**Backend.** `uedcli/serve/scene.py`'s `SceneActor` frozen dataclass gains one field:

```python
csg_rank: int
```

`build_scene_payload` already loops `for name in level.order:` to assemble each `SceneActor` — change
to `for rank, name in enumerate(level.order, start=1):` and pass `csg_rank=rank` into the
`SceneActor(...)` call. This is the whole backend change: `level.order` is already the exact sequence
`csg_rank` numbers, already in scope in that loop, verified by reading the current code (no other
change needed to reach it). The `actor is None: continue` guard (a dangling `order` entry with no
matching actor — a corrupt-tree edge case) keeps skipping as before; the rank number assigned to a
*kept* actor is still its literal 1-based position in `level.order`, matching the CLI verb's
definition exactly (both are `level.order`-index + 1, not a renumbering of only the emitted actors).

**Is `order_value` (the raw string) still shipped?** **Yes, in the wire payload — kept, not
removed.** `SceneActor.order_value: str` stays exactly as it is today, alongside the new `csg_rank`.
Reasoning: the human-GUI spec's audit design (`dev/docs/board/to-plan/uedcli-human-gui/spec.md`,
"Semantic diff") already names `order-changed (order_value)` as a diff category for the not-yet-built
Slice 3 audit module — it diffs the **literal stored string**, not the derived position. Those are not
interchangeable: `level doctor`'s duplicate-rank repair can re-mint a colliding `order_value` into a
fresh distinct value for actors whose *relative* order does not change — a real `order_value` text
change with an unchanged `csg_rank`. Dropping `order_value` from the payload now would blind that
future diff category to exactly the case it exists to catch, and no one has decided to narrow that
category's definition. Keeping the field costs nothing (it is already computed from the existing
`ranks.get(name, "")` in the same loop) — the smallest change that doesn't foreclose Slice 3.

**Is `order_value` still *shown* in the Inspector?** **No — call made: drop it from
`Inspector.tsx`'s visible rows, `csg_rank` replaces it.** The whole point of this item is that nobody
should have to read a LexoRank to answer "where does this actor sit in CSG order" — leaving the raw
string on screen right next to its human-readable replacement is clutter with no current consumer (no
power-user request for the literal string exists; today it is simply undecipherable, not a feature
someone relies on). If a future power-user need for the literal string surfaces, it is still in the
wire payload (above) for a later UI affordance to reach — this call is about the visible row, not the
data.

**`Inspector.tsx` change.** The existing "Order" `<dt>`/`<dd>` pair:

```tsx
<dt>Order</dt>
<dd>{actor.order_value}</dd>
```

becomes:

```tsx
<dt>Order</dt>
<dd>{actor.csg_rank}</dd>
```

No "N of M total actors" annotation: `Inspector` receives only the selected `actor` (`InspectorProps
{ actor: SceneActor | null }`, `web/src/panels/Inspector.tsx`), not the full scene/actor list, so a
total count isn't available without widening that prop — out of scope here (a natural follow-up if
the owner wants "rank 5 of 42" in the inspector; the bare number is the smallest change that solves
the stated problem, matching the CLI's own bare-`RANK` stdout — the CLI's "N total" context lives only
in its stderr summary, not its primary output, for the same reason).

**`web/src/api.ts`.** `SceneActor` interface gains `csg_rank: number` next to `order_value: string`
(both kept, per the call above).

**Existing fixtures that must still compile/pass** (all currently build a `SceneActor` literal with
`order_value: 'm'` and no `csg_rank`, which will fail to typecheck once the field is required):
`web/src/panels/Inspector.test.tsx`'s `fixtureActor()`, `web/src/api.test.ts`, and
`web/src/scene/selection.test.ts`'s `actor(...)` helper. Each needs a `csg_rank` value added to its
fixture (plan Task 5 below).

## Verification

- `bin/test -k actor` clean (covers the new `actor rank` verb alongside the rest of the `actor`
  family; narrow further to `-k actor_rank` while iterating).
- `bin/test -k serve` clean (covers `SceneActor.csg_rank` via `test_serve_scene.py`).
- `npx tsc -b` clean in `web/` (the widened `SceneActor` interface + the fixture updates above).
- `npx vitest run` clean in `web/` (`Inspector.test.tsx`, `api.test.ts`, `selection.test.ts`).
- Manual check against the real corpus: build a tiny fixture trunk (2-3 actors, `trunk.write_level`
  with distinct hand-assigned `order_value`s, same pattern as `uedcli/tests/test_bbox.py`'s
  `_project` helper) under a scratch project pointed at the git-tracked `uned/UED22` game packages,
  run `uedcli actor rank <names...>` against it, and confirm the printed ranks match the actors'
  intended CSG order by inspection (rank 1 = the actor whose `order_value` sorts first). Exercise
  `--json` and the unknown-name error path (exit 2) too.

## Open / deferred

- Inspector "rank N of M" (needs widening `InspectorProps` to carry the scene's total actor count, or
  passing it down separately) — deferred, no request for it yet.
- Any UI affordance to show the raw `order_value` string for a power user — deferred; the field is
  already in the wire payload if that need arises.
