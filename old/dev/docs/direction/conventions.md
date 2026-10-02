# Conventions — explicit, discoverable, model-side

## What we want

### No back-compat cruft — a removed thing is DELETED

uedcli is unreleased: no external users, no pinned versions, no scripts in the wild. Nothing is kept
for backward compatibility. When a flag, verb, option value, output format, on-disk layout, config
key or internal API is removed or renamed, it is deleted in the same commit that introduces the
replacement — the new spelling is the only spelling.

None of these are introduced or kept:

- deprecated aliases (the old name still working);
- no-op flags kept so old invocations still run;
- migration-error shims (a flag that only `parser.error("X renamed to Y")`);
- dual-format support kept to avoid rewriting callers;
- "old way" branches in code, tests or docs.

Each is permanent maintenance surface and a second thing to keep true in the docs — the cause of the
stale-help bug (`--png`'s help described behaviour the code hadn't had for months).

The T3D trees are the one place to think before deleting, because a user's content lives there — but
the rule holds: change the format and migrate or regenerate the trees, never document two layouts.

Superseded the day uedcli is released, when a real deprecation policy replaces it.

### No fallbacks, and no silent half-answers

**No fallbacks — for any command or script — unless the owner explicitly asked for or agreed to one.**
*(Owner ruling, 2026-08-24.)* A fallback is any alternate path taken automatically when the primary
can't run.

- A command that cannot fully satisfy a request **exits 2 naming the offending value**, never a
  partial result plus a stderr note.
- An unresolvable `<package>.<name>` resource — class, texture, sound, music, or any later kind — is
  a hard error naming it, never a substituted zero, default, placeholder, nearest match, empty set,
  or "the one probably meant". *(Owner ruling, 2026-07-27.)* A verb that newly needs a package is
  allowed to start failing where it used to guess; do not add a fallback to keep the old behaviour.
  Resolving lazily — never needing a resource a run doesn't reference — is fine; the rule bites once
  the reference is made. An optional resolver parameter that answers from a default when omitted is a
  fallback in disguise: make it required.
- **Never switch behaviour on the environment.** A verb does the same thing on every host — same code
  path, same engine, same output — or it exits 2 naming what's wrong. Never branch on CPU arch, OS,
  an env var, or the presence/absence of a tool to pick a different implementation. When an approach
  is specified (e.g. a dockerized setup), it is the only path: a missing host tool is a broken host
  to fix, surfaced as a clear error, never a reason to silently keep a host path "in case docker
  isn't there". *(Owner ruling, 2026-08-06.)*
- There is no `--force` and no `--allow-partial` — a flag to opt into a wrong answer is still a wrong
  answer.
- A flag that cannot act where it was passed is an error, not warn-and-continue.
- A predicate answers or **raises**. "Don't know" is never returned as `False`.
- No Python exception ever reaches the user: a bad name, corrupt package or non-finite number exits
  non-zero naming the offending value, never a bare traceback. Every such path carries a regression
  test.
- A batch is all-or-nothing: collect all misses and report the full set, never act on the good ones
  and skip the rest, or die on the first.
- An exact name matching nothing is an error; an empty glob or set result is not (empty stdout, exit
  0) — an empty selection is legitimate pipeline data.
- The one calibrated exception: a set member a verb structurally cannot act on (a point actor handed
  to a poly verb) is named on stderr and skipped, because a mixed `find` result is normal input to a
  shape-specific verb. An unknown name in that set is still exit 2.
- **An ambiguous served set is an error, not a precedence rule.** Where two inputs claim one name —
  two documentation files deriving the same topic key, say — the tool refuses and names both, rather
  than picking one silently. Where such a conflict can only be created by an author (not by a user of
  a shipped binary), the refusal fires during enumeration so it breaks the test suite and every
  invocation at authoring time, and can never reach a user. *(Owner ruling, 2026-07-24.)*

### A class question is answered from the class hierarchy, never the name

"Is this a Mover?" means "does its class descend from `Engine.Mover`?", resolved offline against the
game's own `.u` — one shared predicate, no per-substrate class list, no name-suffix guess. Every
mover-aware verb (`mover key`, `level doctor`, `event graph`, `brush scale`/`apply-transform`/
`intersect`/`deintersect`, `stash capture`, `level photo --native`, the native build) needs a
resolvable package search path, and without one exits 2 naming the verb and what is missing.

### Verbs compose

Small, single-purpose verbs that pipe together — never a big verb grown a bespoke flag at a time.

- Producer/query verbs print their result to stdout, one item per line; human summaries and counts go
  to stderr. Add `--json` where a caller needs structure.
- Mutating/consuming verbs read their target set from stdin via `-`, the sole names source (mutually
  exclusive with names as arguments). Empty stdin is a clean no-op (exit 0).
- Exactly two stdin conventions, disambiguated by verb: a newline name list (`find → mutate -`) and a
  T3D snippet (`build → add -`). The calibrated exception is `classify set -`, which reads JSONL (a
  classification write carries per-item fields a name list can't express, and a per-ref process start
  (~0.3 s) would make classifying a corpus turn-bound); within the catalog nouns
  `-` still means exactly one thing per verb. No further convention without the same explicit
  approval.
- A verb over a set takes the set, and that is the operation — no flag restating "operate on this
  set" (`actor bbox` has no `--union`; `actor find … | actor bbox -` is the union).
- Prefer one stateless query verb feeding the others over `--only-*` filter flags on every verb.
- Every command, flag and argument carries a real `help=` that says what it does.

### `find` vs `search` — distinct verbs, never merged

- `find` — a deterministic query over concrete T3D-tree state, producing a name/selector set to pipe
  into a mutating verb (`actor find`, `brush poly find`).
- `search` — ranked/fuzzy discovery over a catalog or corpus (`texture search`; the future `catalog
  search`, `docs search`).

Pick the verb by which a new command is. Nothing is renamed to unify them.

### Model-side by default

Content reads and mutations are pure model-side compute against the T3D. The editor is touched only
to build or photo, never to answer a question about the trunk.

### Placement anchors the bbox-min corner; rotation pivots a member's own Location

*(Owner ruling, 2026-07-26.)* Two default reference points, deliberately different.

- **Placement anchors the bbox-min corner.** `stash`/`prefab apply --at`, `actor duplicate --at`, and
  `stashlib.normalize_for_capture` put the set's minimum corner on the target — a corner is a
  coordinate you can read off the level and type, exact under repeated placement.
- **Rotation and scale pivot a member's own Location** — the one nearest the bbox centre. `actor
  rotate --by` and `brush scale --by` take that member's authored `Location`, not the computed centre.

**Never synthesize the pivot coordinate.** *(Owner ruling, 2026-07-26.)* An authored `Location` is
already on whatever grid the designer built on, so grid alignment is inherited, not computed. A
derived centre has to be rounded back onto some grid, and picking that grid is where it goes wrong — a
size-proportional grid can round an on-16-grid brush onto the 8-grid. Consequences: a lone actor turns
in place; an off-grid decoration is never dragged onto the grid; actors sharing a Location rotate about
themselves. Locations are taken as authored — nothing filtered, snapped or averaged; equidistant members take the
alphabetically-first Name, so the pivot is order-independent. Accepted cost: a raw-CSG brush
(`Location=(0,0,0)`) contributes the world origin. `--pivot X,Y,Z` / `--pivot-actor` is the override.

## Rejected

**Back-compat**
- A deprecation window (warn now, remove later) — meaningless for a tool with no users.
- Keeping a migration-error shim "because the message is friendly".
- Carving one shim out of the rule — an exception that invites the next one.
- Keeping an output format with no consumer as an "escape hatch".

**Fallbacks and half-answers**
- Opaque-accept of an unknown property — the silent no-op at apply the validation exists to kill.
- Graceful degradation when the schema can't be built (own-props-only + a stderr note).
- A `--force` / `--allow-partial` escape hatch.
- Warn-and-continue for a flag that can't act.
- Returning `False` for "don't know" from a predicate.
- An optional class resolver that falls back to the name guess when absent.
- Keeping `level doctor` resolver-free by gating only the verbs that already have a resolver — two
  predicates that diverge the moment one is fixed.
- A per-substrate mover/subclass registry — the class graph is readable offline from the game's `.u`.
- A second host code path taken when a required tool or container is absent. *(Owner ruling, 2026-08-06.)*
- Erroring on a glob that matches nothing.
- Silently skipping a missing name in a batch, or dying on the first.
- Erroring on a structurally-inapplicable set member.

**Composition and naming**
- Per-verb filter flags (`--only-groups`/`--only-actors`).
- A second name-query verb alongside `find` — a table, if wanted, is a formatting flag on `find`.
- Mixing CLI names and stdin names in one invocation.
- Erroring on empty stdin.
- Keeping a count on stdout behind `--names`.
- A third stdin convention (a bare coordinate list via `-`).
- Renaming everything to `find`, or everything to `search`.

## Refs

`../architecture.md` "Mover support" · `../rationale/cli.md`
