# Conventions — explicit, discoverable, model-side

## What we want

### No back-compat cruft — a removed thing is DELETED

uedcli has **never been released**: no external users, no pinned versions, no scripts in
the wild. So **nothing is kept for backward compatibility.** When a flag, verb, option
value, output format, on-disk tree layout, config key or internal API is removed or
renamed, it is **deleted outright in the same commit that introduces the replacement** —
the new spelling is the only spelling.

None of these may be introduced or retained:

- **deprecated aliases** — the old name still working, silently or with a warning;
- **no-op flags** kept so old invocations still run;
- **migration-error shims** — a flag defined only to `parser.error("X was renamed to Y")`;
- **dual-format support** kept to avoid re-writing callers;
- **"the old way" branches** in code, tests or docs.

Every such shim is permanent maintenance surface and a second thing to keep true in the
docs — the direct cause of the stale-help class of bug (`--png`'s help described behaviour
the code had not had for months). An unreleased tool's one advantage is that it can simply
change.

The T3D trees are the one place to **think** before deleting, because a user's *content*
lives there — but the rule still holds: change the format and migrate or regenerate the
trees, never teach the reader two layouts.

**This is superseded the day uedcli is released**, when a real deprecation policy replaces
it.

### No silent half-answers, and no fallbacks

A command that cannot fully satisfy a request **exits 2 naming the offending value**,
rather than returning a partial result with a note on stderr — stderr scrolls away and the
caller takes the partial answer for a complete one.

- **No fallbacks, anywhere.** An unknown property, an unresolvable class schema, an
  unreadable ancestor package, an absent games config: each is an error naming what is
  missing, never a degraded answer. There is no `--force` and no `--allow-partial` — a flag
  to opt into a wrong answer is still a wrong answer.
- **ANY `<package>.<name>` resource that cannot be resolved is an ERROR — expected, and
  correct.** *(Owner ruling, 2026-07-27.)* This covers every kind alike: **class, texture,
  sound, music**, and whatever kinds come later. If a verb references a resource by
  package-qualified name and that resource is unavailable, the verb **exits 2 naming it**.
  It does not substitute a zero, a default, a placeholder, a nearest match, an empty set,
  or "the one that is probably meant".
  - **Erroring here is not a regression to be softened.** A verb that newly needs a package
    — because it started resolving something it used to assume — is *allowed* to start
    failing where it used to "work", because what it used to do was guess. Do not add a
    fallback to keep the old behaviour, and do not water the requirement down to a warning.
  - **Not needing the resource is different from failing to find it.** Resolving lazily, so
    a run that never references a resource never needs its package, is fine and encouraged
    — that is not a fallback, it is not asking a question whose answer does not matter. The
    rule bites only once the reference is actually made.
  - **An OPTIONAL resolver parameter is a fallback in disguise.** A function that takes
    `resolver=None` and quietly answers from a zero/default when the caller omits it has a
    silent wrong-answer path that no test of the wired-up verb will ever cover. Make it
    required; let the omission be a `TypeError` at author time rather than a wrong pivot,
    texture or sound at run time.
- **A flag that cannot act where it was passed is an error**, not a warn-and-continue: a
  flag that silently succeeds while doing nothing is indistinguishable from a broken one.
- **A predicate answers or it RAISES.** "Don't know" is never returned as `False` — an
  unresolvable case must not become a confident negative that nothing downstream re-checks.
- **No Python exception ever reaches the user.** A bad name, a corrupt package, a
  non-finite number: a clear message naming the offending value and a non-zero exit, never
  a bare `KeyError`/`ValueError` traceback. Every such path carries a regression test.
- **A batch is all-or-nothing.** A verb given several names collects *all* misses and
  reports the complete set, rather than acting on the good ones and skipping the rest, or
  dying on the first — either leaves a partially-applied mutation and an unreliable record.
- **An exact name matching nothing is an error; an empty GLOB or set result is not.** A
  glob with zero matches stays grep-like — empty stdout, exit 0 — because an empty
  selection is legitimate pipeline data. A typo is not.
- **The one calibrated exception: a set member the verb structurally cannot act on** (a
  point actor handed to a poly verb) is named on stderr and skipped, succeeding for the
  rest, because a mixed `find` result is the normal input to a shape-specific verb. An
  **unknown** name in that same set is still a hard exit 2 — "this actor has no polys" is a
  fact about something real; "no such actor" is a question that cannot be answered.

### A question about an actor's CLASS is answered from the class hierarchy, never its name

"Is this a Mover?" means "does its class descend from `Engine.Mover`?", resolved offline
against the game's own `.u` packages — **one shared predicate**, no per-substrate class
list, no name-suffix guess, no optional heuristic fallback. A name guess is wrong in both
directions and invisibly so.

The cost is accepted deliberately: every mover-aware verb (`mover key`, `level doctor`,
`event graph`, `brush scale`/`apply-transform`/`intersect`/`deintersect`, `stash capture`,
`level preview --native`, the native build) needs a resolvable package search path, and
without one **exits 2 naming the verb and what is missing** rather than guessing. `level
doctor` gaining a config requirement is the accepted price of not keeping two predicates
that diverge the moment one is fixed.

### Verbs compose

Small, single-purpose verbs that pipe together — never big verbs grown a bespoke flag at a
time.

- **Producer/query verbs print their result to stdout, one item per line.** Human
  summaries and counts go to **stderr**, so they never pollute the pipe. Add `--json` where
  a caller needs structure rather than lines.
- **Mutating/consuming verbs read their target set from stdin via `-`.** `-` is the **sole**
  names source — mutually exclusive with names as arguments, both together being an error.
  Empty stdin is a clean no-op (exit 0), never a failure: an empty upstream query must not
  break the pipe.
- **Exactly TWO stdin conventions, disambiguated by verb** — a newline **name list**
  (`find → mutate -`) and a **T3D snippet** (`build → add -`). Keep them distinct; never
  add a third, which would blur what `-` means per verb.
- **A verb over a SET takes the set, and that IS the operation.** No flag may merely
  restate "operate on this set" — `actor bbox` has no `--union`, because
  `actor find … | actor bbox -` already is the union.
- **Prefer one stateless query verb** whose output feeds the others, over
  `--only-groups`/`--only-actors` filter flags sprinkled on every verb. Two verbs with the
  same output shape are one verb too many.
- **Every command, flag and argument carries a real `help=`** that says what it actually
  does, so `-h` is self-explanatory — never a restatement of the flag's own name.

### `find` vs `search` — a naming RULE, never merged into one verb

- **`find`** = a deterministic query over concrete **T3D-tree state** — actors, polys,
  brushes that exist in the trunk. Exact, and produces a name/selector SET to pipe into a
  mutating verb (`actor find`, `brush poly find`).
- **`search`** = ranked / fuzzy **discovery over a catalog or corpus** — textures, the
  asset catalog, docs. Finding out *what exists* by relevance, not enumerating a known set
  (`texture search`; the future `catalog search`, `docs search`).

Pick the verb by which of the two a new command is. Nothing is renamed to unify them.

### Model-side by default

Content reads and mutations are pure model-side compute against the T3D. The editor is
touched only to **build** or **preview**, never to answer a question about the trunk.

### PLACEMENT anchors the bbox-min corner; ROTATION pivots a member's own Location

*(Owner ruling, 2026-07-26.)* Two different default reference points, and the split is
deliberate — neither is "the bbox point we happened to have".

- **Placement anchors the bbox-MIN corner.** `stash`/`prefab apply --at`, `actor duplicate
  --at`, and `stashlib.normalize_for_capture` all put the set's minimum corner on the target.
  You place a prefab by dropping a corner on a known grid point; a corner is a coordinate you
  can read off the level and type, and it stays exact under repeated placement. **This is
  KEPT** — it is not to be "unified" with the rotation default.
- **Rotation and scale pivot a MEMBER'S OWN LOCATION — the one nearest the bbox center.**
  `actor rotate --by` and `brush scale --by` take the `Location` of the set member closest to
  the center, not the center itself. You turn a thing about its middle, but through a point
  that already exists in the trunk.

**Never synthesize the pivot coordinate.** *(Owner ruling, 2026-07-26 — this is the load-bearing
half.)* A `Location` is authored: whatever grid the designer built on, it is already on it, so
grid alignment is **inherited rather than computed**. Every rule that instead *derives* a pivot
has to round it back onto some grid, and picking that grid is where it goes wrong — a computed
center rounded to a size-proportional grid can be less aligned than the geometry it turns, which
walks on-16-grid brushes onto the 8-grid. Rotating about an authored point cannot do that.

Consequences that follow, rather than being separate rules: a lone actor turns exactly in place;
an off-grid decoration is never dragged onto the grid by being turned; several actors sharing a
Location rotate about themselves.

**Locations are taken as authored — nothing is filtered, snapped or averaged.** Equidistant
members take the **alphabetically first Name**, so the pivot is always a point that exists in
the trunk, and does not depend on the order the set arrived in. The accepted cost: a raw-CSG brush (`Location=(0,0,0)`, world-space vertices)
contributes the world origin, so a set of only those turns about the origin.
`--pivot X,Y,Z` / `--pivot-actor` is the override.

The asymmetry is the point — an operation's default reference point follows what the
operation means, not a single global choice of bbox landmark.

## Rejected

**Back-compat**

- **A deprecation window** (warn now, remove later) — a released-software ritual with no
  meaning for a tool that has no users.
- **Keeping a migration-error shim "because the error message is friendly"** — the
  friendliness is for users who do not exist; the real readers are the owner and the agents
  working this repo, who read `usage.md` and the commit.
- **Carving one shim out of the rule** (keep one, delete the rest) — an explicit exception
  that buys nothing and invites the next one.
- **Keeping an output format with no consumer as an "escape hatch"** (honouring a `.ppm`
  extension) — a format nothing downstream reads is how the next stale-docs bug starts.

**Half-answers and fallbacks**

- **Opaque-accept of an unknown property** — the silent no-op at apply is the exact bug the
  validation exists to kill.
- **Graceful degradation when the schema cannot be built** (own-props-only plus a stderr
  note, exit 0) — a half-answer that looks like a full one is worse than a refusal; the
  note scrolls away and the caller believes the class has no inherited props.
- **A `--force` / `--allow-partial` escape hatch** — a flag to opt into a wrong answer.
- **Warn-and-continue for a flag that cannot act** where it was passed.
- **Returning `False` for "don't know"** from a predicate, with a logged warning — the
  warning scrolls away and the confident negative propagates unchecked.
- **An OPTIONAL class resolver that falls back to the name guess when absent** — a fallback
  answers a question it cannot answer, and the wrong answer is invisible.
- **Keeping `level doctor` resolver-free by gating only the verbs that already have a
  resolver** — two predicates to keep true, diverging silently the moment one is fixed and
  the other is not.
- **A per-substrate mover/subclass registry** — unnecessary: the class graph is already
  readable offline out of the game's own `.u`.
- **Erroring on a glob that matches nothing** — it would make composed pipelines treat a
  legitimately-empty selection as a failure.
- **Silently skipping a missing name in a batch verb**, or dying on the first one — the
  first masks typos, the second leaves a partially-applied mutation.
- **Erroring on a structurally-inapplicable set member too** — then piping a mixed `find`
  result into a shape-specific verb always fails, and every compose needs a pre-filter.

**Composition and naming**

- **Per-verb filter flags** (`--only-groups`/`--only-actors`) sprinkled across mutating
  verbs — the anti-pattern the one stateless query verb exists to replace.
- **A second name-query verb** kept alongside `find` (a human-readable `actor list` table)
  — it re-splits query output into two shapes; a table, if ever wanted, is a formatting
  flag on `find`, not a verb.
- **Mixing CLI names and stdin names** in one invocation — ambiguous about which set the
  verb acts on.
- **Erroring on empty stdin** — breaks Unix-filter semantics and the composed pipeline.
- **Keeping a count on stdout** (behind an opt-in `--names` flag) — the pipe carries data,
  the human summary belongs on stderr.
- **A third stdin convention** (a bare coordinate list via `-`) — it would blur what `-`
  means per verb; a repeatable `--point U,V` flag stays visible in `--help` instead.
- **Renaming everything to `find`, or everything to `search`** — either erases a real
  semantic distinction (deterministic tree query vs ranked corpus discovery) that the two
  names usefully carry, and makes a verb's output shape unpredictable from its name.

## Refs

`../architecture.md` "Mover support" · `../rationale/cli.md` (the argparse
prefix-abbreviation trap and other CLI mechanics)
