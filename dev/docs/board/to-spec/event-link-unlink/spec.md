# `event link` / `unlink` — spec (DRAFT)

Status: draft for owner review. Open decisions are in `questions/`; nothing here is built until they
are answered.

## Goal

`event graph` reads the Tag↔Event trigger wiring but no verb authors it. Add `event link` /
`event unlink` — model-side, over the trunk — so an agent can wire and unwire triggers by name
instead of hand-editing `Event`/`Tag` props. The natural completion of `event graph`.

## Current state

- `eventgraph.py` READS the wiring. An edge `A → B` exists when `A.Event == B.Tag`, both
  explicit and non-empty (`eventgraph.py:1-26`, `build_graph` at `:94-128`). A `Tag` that is
  unset — so UE1 would default it to the class name at runtime — is deliberately NOT a receiver
  (`:14-21`). Prop reads case-fold and treat empty/whitespace as absent (`_prop`, `:81-91`).
- `event` is its own top-level family with one sub-verb, `graph`
  (`cli/commands/event.py:16-21`, `cli/parsers/event.py:7-29`). `run()` raises `CommandError` for
  any unimplemented sub-verb (`:21`).
- The scalar model-side prop write pattern: replace-or-remove a `(key, value)` in `actor.props`
  (`movers.py:115-119`, `_set`). Actors store props as a `list[tuple[str, str]]`
  (`model.py:77-80`).
- The set-input convention: `-` reads a newline name list from stdin and is the sole names source
  (`cli/targets.py:17-40`, `resolve_target_names`); empty stdin → `[]` → no-op exit 0. Mixing `-`
  with CLI names exits 2. Canonical resolution + dedup are the caller's
  (`query.resolve_actor_names`, `query.py:283-299`; miss → exit 2 `Actors not found: …`).
- Precedent for "value on a flag, actors as the piped set": `actor folder set --to <path>
  <names…|->` (`cli/parsers/actor.py:171-179`, `cli/commands/actor/folder.py`), and the
  producer/two-phase pattern (validate-all, then mutate, echo touched names to stdout, count to
  stderr) in `actor/label.py:18-67` and `actor/prop.py:89-117`.
- Save: `src.save(verb=…, args=…, level=level, touched=names)` (see `actor/label.py:61`).
- Two open inbox findings bear on this:
  - `unset-tag-treated-as-not-a-matchable-receiver` — the owner flagged the "explicit Tag only"
    rule as an assumption; `link` must therefore write an EXPLICIT Tag, never rely on the
    class-name default.
  - `tag-of-a-single-space-is-not-round-trip-stable` — a whitespace-only `Tag` (`Tag= `) does not
    survive emit→parse. `link` must not mint or propagate such a value.

## Design

An edge `A → B` is created by setting `A.Event := B.Tag`, minting `B.Tag` if B has no explicit one.
`link` is directional (source fires, target receives); `unlink` removes the wire the source fires.

### CLI surface (proposed — see `questions/cli-shape-and-fan-out.md`)

Mirror `actor folder set`: the piped/positional set is the SOURCES (the actors whose `Event`
changes); the single target is on `--to`. This makes fan-in (many sources → one target) the natural
pipeline and keeps `-` as the sole names source.

```
event link --to TARGET  SOURCE…|-
  help (link):   "wire trigger SOURCE(s) to fire at TARGET: set each SOURCE's Event to TARGET's Tag,
                  minting TARGET's Tag if it has none, so `event graph` then shows SOURCE --Event--> TARGET.
                  SOURCEs are actor Names (case-insensitive) or - for a newline name list on stdin
                  (`actor find … | event link --to Door01 -`); - is the sole source, not mixable with
                  names. Empty stdin is a clean no-op (exit 0). Producer: touched SOURCE Names to stdout,
                  a count to stderr — chains into another verb's -."
  help (--to):   "the receiver actor SOURCE(s) will fire at (one Name, case-insensitive). Its Tag is the
                  event name written into each SOURCE's Event; if TARGET has no explicit Tag one is minted
                  and stored on TARGET (see help for how). Must resolve to an existing actor (exit 2 if not)."

event unlink  SOURCE…|-
  help (unlink): "remove the trigger wire each SOURCE fires: clear its Event (revert to unset), so it no
                  longer targets any receiver. Does NOT touch any target's Tag (a Tag is the receiver's own
                  identity and may have other sources). SOURCEs are actor Names or - for a stdin name list;
                  - is the sole source. Clearing a SOURCE that fires nothing succeeds silently. Empty stdin
                  is a clean no-op. Producer: touched Names to stdout, a count to stderr."
```

Both take `_tree_flag` (edit a named tree, default `$UEDCLI_LEVEL`), like every trunk mutator.

**Why sources-as-set, not `event link SOURCE TARGET` (two positionals).** Two actor-name positionals
cannot use the `-` stdin convention (which owns the names slot), breaking `find | link`. The
value-on-`--to`, set-as-positional/`-` shape is the established one (`folder set --to`).

**Fan-out (one source → many targets)** is NOT expressible in this shape: a source's single `Event`
string can equal only one tag value, so "one source, many targets" means all targets share one tag.
That is a distinct operation. Options and recommendation are in the CLI-shape question.

### What `link` writes

Per source S and the single target T:

1. Resolve T's event name E:
   - if T has an explicit, non-empty `Tag`, reuse it (so a second source linked to T shares the
     same receiver identity);
   - else mint E and store it as `T.Tag` (an explicit write on T — the one actor outside the piped
     set this verb mutates). Mint scheme is an open decision — see
     `questions/tag-minting-scheme.md`. Proposed default: E = T's Name (unique, readable, explicit,
     never the class-name default).
2. Set `S.Event := E` (replace-or-append in `S.props`, `movers._set` pattern).

Validate-all-then-mutate across the whole piped set (a bad source name, a missing/whitespace target
tag, or an unresolvable target leaves ALL actors untouched), matching `actor/label.py` and
`actor/prop.py`. Then `src.save(...)`, echo touched SOURCE names to stdout, count to stderr.

### What `unlink` writes

Clear `Event` on each source (remove the prop). Never touches any Tag. `save`, echo, count.

### Scope: scalar `Event` only (proposed)

Match `event graph`'s scope (`eventgraph.py:22-26`): the single scalar `Event` prop. Multi-event
ARRAY firers (Dispatcher `OutEvents(n)`, Counter) are NOT authored here in v1. Whether to include
them is an open decision — see `questions/array-prop-firing-scope.md`.

## Edge cases & errors

- **Empty stdin** → no-op, exit 0 (`resolve_target_names` returns `[]`).
- **`-` mixed with names** → exit 2 (inherited from `resolve_target_names`).
- **Unknown source / target** → exit 2 naming it (`Actors not found: …` / `Actor not found: …`),
  never a traceback.
- **Target has a whitespace-only or empty explicit `Tag`** → exit 2 naming the target; do not
  propagate a non-round-trip-stable value (ties to the `tag-of-a-single-space…` finding). Minting
  never produces such a value.
- **Source already fires a different `Event`** → overwrite (that IS re-linking) and print a
  `warning: <src> was firing Event=<old>, now <new>` to stderr, so a silent rewire can't scroll
  past. (Recommendation; not a separate owner question.)
- **Source already fires exactly E** → still a clean success (idempotent), touched name still echoed.
- **Self-link (source == target)** → allowed; produces a self-edge, which `event graph` already
  keeps (`eventgraph.py:104`). No special-case.
- **`unlink` on a source with no `Event`** → silent success (like `prop unset` of an absent prop).
- **Minting `T.Tag` when T is also a source in the same run** → resolve T's E once, before any
  write, so ordering can't matter (two-phase plan).

## Tests

Mirror `tests/test_eventgraph.py` + the command-isolation/dispatch tests. Cover:

- `link` sets `source.Event` to the target's existing explicit `Tag`.
- `link` mints `target.Tag` (deterministic value) when the target has none, and the value is
  explicit and non-whitespace.
- `link` over a stdin name list (fan-in): every source fires the target's tag; feeding the result
  through `build_graph` yields the expected edges (integration with the reader).
- `link` reuses one shared tag when two sources target the same receiver.
- `link` refuses a target whose explicit `Tag` is a single space / empty → exit 2 naming it.
- `link` overwrites a differing `source.Event` and emits the stderr warning.
- Unknown source and unknown target each → exit 2 with a naming message, no traceback.
- `-` mixed with names → exit 2; empty stdin → exit 0 no-op.
- `unlink` clears `Event`; `unlink` of an eventless actor is a silent no-op; `unlink` never alters
  any `Tag`.
- Round-trip: `link` then `event graph` shows the wire; `unlink` then it is gone.
- Producer contract: touched names to stdout, count to stderr (both verbs).

## Open questions (owner)

1. `questions/cli-shape-and-fan-out.md` — sources-as-set with `--to TARGET` (recommended) vs. an
   alternative; and how/whether to support fan-out (one source → many targets sharing a tag).
2. `questions/tag-minting-scheme.md` — what value to mint for a tagless target (target Name,
   recommended, vs. a random token), and whether to add a `--tag NAME` override.
3. `questions/array-prop-firing-scope.md` — v1 scalar `Event` only (recommended) vs. also authoring
   Dispatcher `OutEvents(n)` / Counter array firers now.

## Docs

On build, update `docs/usage.md` "Level lint & trigger wiring" (the `event graph` section,
`usage.md:316-329`) to add the `link`/`unlink` mutators, and add them to the "Set-mutating verbs are
producers" list (`usage.md:41-47`). This is tool-behavior documentation (no owner approval needed).
