# Actor-name composition pipe — stdin `-` on name-takers + `actor add` name output

**Status:** spec (ephemeral). **Ledger:** [`decisions.md` 2026-07-18](../../../decisions.md).
**Closes two board items** (inbox): "Name-taking verbs accept actor names from STDIN (`-`)" and
"`actor add` should print the allocated Name(s)". They are the two ends of one pipe, so one spec.
**Pairs with** the folders spec (`actor find --folder … | actor folder set --to … -`).

## 1. Motivation — close the compose pipe
`actor find` already prints matching names one-per-line, but the mutate/query verbs take names only
as CLI args, and `actor add` prints only a count — so neither end of the obvious pipeline closes:

```
# want:
actor find --folder castle.tower | actor prop set - Texture=CoreTexBrick.brick
brush build cube --at 0,0,0 | actor add - | actor prop set - bHidden=True   # add → names → edit
```
*(Note the real `prop` grammar: `actor prop set|unset|get <name> <tokens…>` — sub-verb + positional
`KEY=VALUE` tokens, NOT `--set`. See §8 review-gate resolutions.)*

This spec adds the two missing halves: **producers emit names** (`actor add` → stdout) and
**consumers read names** (`-` from stdin). It's the CLAUDE.md "verbs compose" principle made real.

## 2. Half A — `actor add` prints the allocated Names
`actor add` mints `<base>_<rand>` names (D6); today it prints `added N actor(s)` (`dispatch.py:2214`)
and callers re-run `actor find --name '<base>*'` to recover them. Change:

- **Allocated Names → stdout, one per line, in allocation order** (the order actors were added). This
  is the pipe-friendly output that feeds the `-` consumers below.
- **The `added N actor(s)` summary → stderr** (still shown to a human, never pollutes the pipe).

*(Decision: names→stdout, count→stderr. Rejected: dropping the count; keeping count as default behind
a `--names` opt-in — pre-release, no output contract to preserve.)*

## 3. Half B — name-taking verbs read `-` from stdin

A verb given the single token `-` in its name position reads a **newline-separated list of actor
names** from stdin (exactly `actor find`'s output) instead of taking names on the command line.

### Verbs that get `-`
- **`actor delete -`**, **`actor rotate -`** (already `names nargs="+"`).
- **`actor prop set|unset|get -`** — extends `prop` to **multi-actor** (today single-name): the same
  `--set`/`--unset` tokens (or `get` keys) apply to **every** piped name.
- **`actor get -`**, **`actor show -`** — read verbs, multi-actor dump (see output note below).
- **`actor folder set --to <path> -`** (from the folders spec).
- **NOT `actor move`** — multi-actor `move --to` collapses targets onto one point (a footgun; excluded
  by decision). **NOT `actor add`** — its `-` already means "read a T3D snippet from stdin" (§5).

### Semantics (all decisions)
- **`-` is the SOLE source of names** — mutually exclusive with names given as CLI args (mirrors
  `actor add -`). Passing both → exit 2 with a clear message. Unambiguous; no silent set expansion.
- **Empty stdin → no-op, exit 0.** Zero names = do nothing, succeed (standard Unix filter: a filter
  that matched nothing is not an error; `find … | rotate -` never fails just because `find` was empty).
- **Name resolution is all-or-nothing**, as today: every piped name is resolved case-insensitively
  (`resolve_actor_names`); an unknown name → exit 2 naming it, **before** any mutation (the model is
  only touched after all names validate, so a bad name leaves the trunk untouched — invariant D2 /
  the `actor prop` validate-then-apply contract).
- **Duplicate piped names are deduped** (first occurrence wins), so `find` output with an accidental
  repeat is harmless.

### Multi-actor output for the read verbs
- **`actor show -`** emits each actor's T3D block in piped order (each block self-identifies via its
  `Name=`; with the folders carrier, its `// uedcli-folder:` line). Concatenation is valid T3D.
- **`actor get -`** prints, **per actor**, its value line(s) **prefixed with `<name>\t`** so a
  multi-actor dump stays parseable (`Wall1\t512`); a single CLI name (not `-`) is unchanged (bare
  value). *(Small format point — flagged for review.)*

## 4. CLI implementation shape
One shared helper `cli`/`dispatch` `resolve_target_names(args) -> list[str]`: if the name token(s) ==
`["-"]`, read+split+strip+dedup stdin (empty → `[]`); else the CLI names; error if both a real name
and `-` appear. Each name-taking handler routes through it. `prop`/`get`/`show` gain a loop over the
resolved set (validate-all-then-apply for `prop`). Argparse: the single-name verbs (`prop`, `get`,
`show`) accept `-` in their `name` positional; multi-name verbs already take `nargs="+"`.

## 5. The two stdin conventions — DISTINCT, disambiguated by verb
This is the one thing to document loudly so it doesn't confuse:

| Verb | `-` reads from stdin | Producer |
|---|---|---|
| `actor add -` | a **T3D snippet** (actor blocks) | `brush build` / `actor build` / generators |
| `actor delete/rotate/prop/get/show -`, `actor folder set … -` | a **newline name list** | `actor find` (or any name-printing verb) |

So `brush build | actor rotate -` does **not** work (rotate wants names, not T3D) and `actor find |
actor add -` does not either — the pipe grammar is `build → (T3D) → add → (names) → mutate` and
`find → (names) → mutate`.

## 6. Testing (offline)
- `actor add` prints Names to stdout (one/line, allocation order) and the count to stderr; a
  `build | add - | prop - --set …` pipe end-to-end sets the prop on the added actors.
- Each `-` verb: reads names from stdin; empty stdin → no-op exit 0; unknown piped name → exit 2
  naming it, trunk untouched; `-` together with a CLI name → exit 2; duplicate names deduped.
- `actor prop - --set` applies to every piped actor atomically (a bad token leaves all untouched).
- `actor get -` prefixes `<name>\t`; `actor show -` concatenates valid per-actor blocks.
- `actor move` does NOT accept `-` (still errors on it as an unknown actor / rejects) — guard test.

## 7. Touchpoints
`cli.py` (allow `-` in the single-name positionals; the shared `resolve_target_names`) ·
`dispatch.py` (`actor add` output split stdout/stderr; `prop set|unset|get`/`show` multi-actor
plan-all-then-apply; route all name-takers through the helper) · `query.resolve_actor_names` (reused).
No model/trunk change.

## 8. Review-gate resolutions (2026-07-18 — two cold reviews; these OVERRIDE any conflicting prose above)
Both reviewers verified against the code. Corrections folded:
- **There is NO `actor get` / `actor prop --set`.** The read verb is **`actor prop get`**; edits are
  **`actor prop set|unset <name> KEY=VALUE…`** (sub-verb + positional tokens, `cli.py:218-264`).
  Everywhere this spec wrote `actor get -` read `actor prop get -`; everywhere it wrote `actor prop -
  --set` read `actor prop set -`. The `-` verbs are: `actor delete -`, `actor rotate -`, **`actor prop
  set|unset|get -`**, `actor show -`, `actor folder set --to <path> -`.
- **Dedup AFTER resolution, not on the raw token.** `resolve_actor_names` is case-insensitive
  (`query.py:241`), so two differently-cased tokens are the same actor; dedup with
  `dict.fromkeys(resolved)` (as `actor rotate` already does, `dispatch.py:2271`) — else `prop`/`rotate`
  double-applies.
- **Multi-actor `prop` is TWO-PHASE, not a save-as-you-go loop.** Piped actors can be different classes,
  so build a per-actor `_class_ctx` + `plan_edit` for **all** actors FIRST, then apply all (one save).
  A per-actor apply-then-save loop would violate the "a bad token leaves ALL untouched" guarantee.
- **Multi-actor `prop get` output = `<name>\t<key>=<value>`** (the `--kv` shape, prefixed by name) —
  because `get` takes multiple keys (`tokens nargs="*"`), a bare `<name>\t<value>` can't tell `Health`
  from `Texture`. Single (non-`-`) name keeps today's bare output. (Resolves the §3 flagged point.)
- **`actor show -` must intercept `-` BEFORE the glob path** — `show`'s `name` is glob-capable
  (`*?[`, `query.py:275`), a separate multi-actor mechanism; `-` (stdin list) is checked first.
- **`actor add` emits Names to stdout ONLY AFTER `src.save()` returns** (it already does, line 2213
  before 2214 — pin it as a REQUIREMENT): in a live `add - | prop -` pipe, `prop`'s `load()` must not
  race ahead of the trunk write. Do not stream/flush names before the save.
- **Update the existing test** `test_dispatch.py:237` (`"added 3 actor(s)" in out`) — that summary moves
  to **stderr**; assert it on `err` and the Names on `out`.
- Minor: `actor delete -` with no pipe blocks on tty stdin (accepted Unix behavior).
