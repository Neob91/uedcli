# `actor move` over a SET — stdin name-list input, `--by`-only for multi-actor

**Status:** spec (ephemeral — fold into `architecture.md` + `usage.md` on build, then this file may be
deleted).
**Decisions ledger:** APPENDED — [`../decisions.md`](../decisions.md) `2026-07-25 00:43 UTC` records the
§4 sub-choices (`--to` requires exactly one actor, `--by` for any count, dedupe, empty-stdin no-op,
group-anchor `--to` rejected).
**Motivation source:** board `to-spec.md` `[spec] p1` ("`actor move` over a SET (`-`/stdin), `--by`-only
for multi-actor"; consistency-audit H2, accepted 2026-07-19; Andrzej: `--by`-only for sets).
**Sibling verbs:** `actor rotate` (`cli.py:687`) and `brush scale` (`cli.py:731`) already implement the
`names… | -` set contract this spec brings to `move`; the design mirrors them.

---

## 1. The gap

`actor move` is the **only** actor/brush transform verb that cannot take a set. Today (`cli.py:609`,
`dispatch.py:3669`):

```
actor move <name> (--to X,Y,Z | --by DX,DY,DZ)
```

- one positional `name` (single actor), and
- no `-` / stdin source.

So the compose-verbs idiom that works for every sibling transform **fails** for move:

```bash
actor find --folder castle.props | actor move -    # ERROR today: move takes a bare name, not -
actor find --label lit          | actor move - --by 0,0,64   # can't nudge a set up 64uu
```

`actor rotate` and `brush scale` both take `names… | -` (`nargs="+"`, `-` the sole stdin source) and a
mutually-exclusive `--by` / `--to`. `move` is the odd one out — a direct violation of the
compose-verbs philosophy (uedcli `CLAUDE.md`: "a verb over a SET takes the set, and that IS the
operation").

## 2. The design

Bring `move` to the sibling shape, with one asymmetry the geometry forces:

```
actor move <names…> | -   (--to X,Y,Z | --by DX,DY,DZ)
```

- **`names…`** (`nargs="+"`) — one or more actor Names, **or** the single token `-` to read a
  newline-separated name list from stdin (the `-` convention; `-` is the sole source, not mixable with
  named args), matching `rotate`/`scale` exactly.
- **`--by DX,DY,DZ`** — a world-space translation delta added to **every** target's Location. Works for
  **any** count (1 or many; negative components allowed — moving a selection *down* `0,0,-64` is the
  common case). This is the natural set operation: a rigid translation of the whole group.
- **`--to X,Y,Z`** — an absolute world target. **Rejects a set: >1 resolved actor is a hard error**
  (§4, exit 2). Moving a set to a single point would stack every actor there — meaningless. **0** actors
  is the standard empty-stdin no-op (exit 0, §3 step 1); **exactly 1** (named, or a `-` pipe that
  yields one) keeps today's behaviour.
- `--to` / `--by` stay **mutually exclusive and required** (unchanged).
- **No `--pivot`.** Move is a pure translation; unlike `rotate`/`scale` (which orbit Location about a
  pivot) there is no pivot to compute. `--by` is the same delta on every actor.
- **`_tree_flag(mv)` retained** — the `--tree` flag stays, as on today's `move` and on rotate/scale.
- **Movers:** a set-move is N independent Location translations. A mover's keyframes are base-relative
  (offsets from its own Location), so translating Location moves the whole mover and its animation
  unchanged — identical to today's single-actor move, no new concern.

### 2.1 Why `--to` can't generalize to a set

`--by` is inherently a set operation (translate all by the same delta). `--to` is inherently
single-target (one absolute destination). The alternative — "move the set so its *anchor* (centroid /
bbox-min) lands at `--to`" — is a genuinely different feature with an ambiguous anchor choice; it is
**deferred**, not built (§4 rejected-alternatives, §6). v1 keeps `--to` single-actor-only, exactly as
the board item specifies.

## 3. Behaviour (exact)

Resolution + iteration mirror `actor rotate` (`dispatch.py:3909`):

1. **Read targets** — `_resolve_target_names(args.names)`: `-` pulls the newline list from stdin,
   otherwise the CLI names. **Empty stdin → no-op, exit 0** (the standard consuming-verb contract; a
   clean no-op, not an error — matches rotate/scale/order/delete).
2. **Resolve + dedupe** — `query.resolve_actor_names(level, raw)`; an unknown name → exit 2 naming it
   (all-or-nothing, no partial move). **Dedupe on canonical names, order-preserving**
   (`dict.fromkeys`): a repeated name is the SAME actor object, and `--by` applied twice would
   double-move it. (rotate dedupes for the same reason.)
3. **`--to` arity gate — checked AFTER dedupe (step 2)** — if `--to` is given and the **deduped** set
   has **>1** actor: exit 2, `actor move --to moves ONE actor to an absolute point; got N (use --by for
   a set, or move one at a time)`. Exactly 1 proceeds; **0 already returned at step 1** (empty stdin).
   The gate operates on the deduped set, so a single name piped twice (`printf 'a\na' | move - --to …`)
   dedupes to one and **succeeds** — a load-bearing ordering (§5 tests it).
4. **Apply**
   - `--by`: for each target, `Location = (Location or origin) + delta` (per-axis `Decimal` add;
     unset Location is treated as origin, as today).
   - `--to`: the single target's `Location = (X, Y, Z)` (today's path, unchanged).
   - No brush re-validation — move touches only the actor's Location field, never the local PolyList,
     so `validate_brush` is unnecessary (and today's single-actor move doesn't call it).
5. **Save** — `src.save(verb="move", args=…, level=level, touched=names)`. `args` records
   `{"names": [...], "by": [...]}` for the set/`--by` path and `{"names": [<one>], "to": [...]}` for the
   `--to` path (the recorded shape moves from the single-`name` form to the list form, consistent with
   rotate).
6. **Output** — **PRODUCER**: print each moved canonical name to **stdout**, one per line, in piped
   order (so `… | actor move - --by … | actor prop set - …` chains); a `moved N actor(s)` summary to
   **stderr**. This **replaces** today's single-actor `moved <name>` stderr string with the count form
   (unifying with rotate/delete/order); the single-actor regression asserts the NEW summary.

## 4. Decisions (→ `decisions.md`)

- **`--to` rejects a set: >1 resolved actor → exit 2** (0 = empty-stdin no-op; exactly 1 proceeds).
  *Rejected:* silently moving all to the
  point (stacks them — a silent nonsense result, the half-answer `direction.md` forbids). *Rejected for
  v1:* **group-anchor `--to`** — move the set so its centroid or bbox-min lands at the point. A real
  feature but with an ambiguous anchor (centroid vs bbox-min vs a named actor's Location) and its own
  flag surface (`--anchor`); deferred to a follow-up rather than overloading `--to` now. The board item
  explicitly scoped v1 to "`--by`-only for sets, `--to` single-actor-only."
- **`--by` applies to any count** (1..N) — the set operation needs no extra flag (uedcli `CLAUDE.md`:
  "a verb over a SET takes the set, and that IS the operation"; no `--all`/`--set` flag).
- **Dedupe on canonical names** — a repeated/aliased name is one actor; `--by` twice would double-move.
- **Empty stdin → exit 0 no-op** — the uniform consuming-verb contract.
- **No `--pivot`** — translation has no pivot (distinguishes move from rotate/scale).

The arity gate is checked at **dispatch** (after stdin is read — the count is unknown at parse time),
not in argparse, exactly like `rotate --to` rejecting `--pivot` at dispatch (`dispatch.py:3926`).

## 5. Tests

**New set-behaviour tests** — add alongside the rotate/scale set tests (rotate's live in
`test_transform.py` + `test_dispatch.py`; put move's set tests in `test_transform.py` for symmetry):

- `move - --by` over a 3-name stdin set translates all three; output lists all three names in order.
- `move - --by 0,0,-64` uses a **negative** delta (the common designer case) and lands correctly.
- `move - --by` with a **duplicated** piped name moves that actor **once** (dedupe — a double-move bug
  guard).
- `move - --by` over an actor with **no stored `Location`** writes `Location = delta` (the
  unset-Location-is-origin guarantee, §3 step 4).
- `move - --to` with a **single** piped name works (regression: `--to` still valid for one via `-`).
- `move - --to` with a name **piped twice** (dedupes to one) **succeeds** — locks in gate-after-dedupe
  ordering (§3 step 3).
- `move a b --to …` (2 named) → exit 2, message names the count and points at `--by`.
- `move - --to …` with a **2-name** stdin set → exit 2 (same gate via the pipe).
- **Empty stdin** (`printf '' | move -`) → exit 0, no change, no output.
- Unknown name in the set → exit 2 naming it, nothing moved (all-or-nothing).
- The `- not mixable with named args` rule (`move a - --by …` → error) is enforced by the shared
  `_resolve_target_names` and already covered by its rotate/scale tests — no new move-specific test
  needed (delegated, noted so an implementer doesn't re-add it).
- Single named `move X --to …` / `move X --by …` — the move MATH is unchanged; the **stderr summary is
  now `moved N actor(s)`** (assert the new form, not the old `moved <name>` string).

**Existing tests that MUST be migrated/removed** (the `name`→`names` positional rename + `args["name"]`
→ `args["names"]` save-shape change break these; the CLI is unreleased, so they change outright — no
compat shim, `direction.md` "no back-compat cruft"):

- **REMOVE** `test_actor_name_compose.py:392` `test_move_dash_is_treated_as_an_unknown_actor_not_stdin`
  (and its `# ── move does NOT accept - ──` banner) — it asserts the exact behaviour this spec
  reverses (`move -` now READS stdin). This supersedes the earlier "move does NOT accept `-`" decision.
- **MIGRATE** every `SimpleNamespace(cmd="actor", sub="move", name=…)` construction to the list
  positional `names=[…]`, and any `saved["args"]["name"]` assertion to `saved["args"]["names"]`:
  `test_actor_name_resolution.py:63/74/88/103` (two assert `args["name"]`), `test_env_level_and_echo.py:31`,
  `test_tree_flag.py:255/444`, `test_trunk_verbs.py:94`. (Grep `sub="move"` / `sub='move'` to catch any
  the review missed.)

## 6. Deferred / follow-ups (→ `inbox.md`)

- **Group-anchor `--to`** (move a set so its centroid/bbox-min/named-anchor lands at a point). Needs an
  `--anchor` choice; file as a separate `[spec]` if wanted. Not in v1.

## 7. Docs + in-code help to update on build

- **In-code `help=` strings** (`cli.py:609`–616) — all are single-actor-framed today and will lie after
  the change (the stale-help bug class `direction.md` calls out; every arg needs an accurate `help=`).
  Rewrite to match rotate/scale's `names…|-` phrasing:
  - subparser: `"move actor(s) by a world delta (--by, any count) or one actor to an absolute point
    (--to)"`;
  - positional `names`: the `names…|-` help verbatim from rotate (`cli.py:690-693`);
  - `--by`: "world delta added to EVERY target's Location (any count; negatives allowed)";
  - `--to`: "absolute world target — ONE actor only (a set → exit 2; use --by for a set)".
- `docs/usage.md` — the `actor move` entry: `names… | -`, the `--by`-any-count / `--to`-single rule,
  the producer output (stdout names + `moved N actor(s)` stderr).
- `dev/docs/architecture.md` — if it enumerates which transforms take sets, add `move` to the list
  (rotate/scale/move now uniform).
- This spec's decisions fold into `decisions.md` (already appended); delete this file once built.
