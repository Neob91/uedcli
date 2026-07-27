# Composable `actor find` — a stdin name-set input for full boolean queries

**Status:** spec (ephemeral — fold into `architecture.md` + `usage.md` on build, then this file may be
deleted). **Revised 2026-07-24** after two cold reviews — the `--exclude` semantics changed from
"subtract the piped set" (`M∖P`) to a **grep/universe model** (see §2, §4); several factual fixes folded in.
**Decisions ledger:** APPENDED — [`dev/docs/decisions.md`](../../../decisions.md) `2026-07-24 10:02 UTC` records the
§7 sub-choices (`--exclude` spelling, `find -` kept, strict unknown-name exit 2, grep/universe model).
**Motivation source:** board `inbox.md` `[spec] p1` (raised while speccing actor-labels — `find --label`
ORs, so "label X AND Y" was inexpressible).
**Orthogonal to** the actor-labels spec (`2026-07-22-actor-labels.md`) — this is a general `find`
feature that benefits EVERY filter dimension; it does not change any filter's OR-within semantics.
**NOTE on examples:** `--label` is NOT built yet (it is the separate actor-labels spec). The primary
examples below use dimensions that exist TODAY (`--folder`/`--group`/`--class-exact`); `--label`
appears only where called out as label-dependent, so this spec is buildable and testable on its own.

---

## 1. The gap

`actor find` composes filters two ways today (`query.list_actors`, `query.py:164-229`):

- **repeated same flag = OR** — `--group A --group B` matches an actor in group A *or* B; likewise
  repeated `--folder`/`--class-exact`.
- **different flags = AND** — `--group A --folder castle.**` matches in-A-AND-under-castle.

Two things are therefore inexpressible:

- **Same-dimension AND** — "in group A *AND* group B" (both on one actor).
- **NOT / difference** — "matches A but *not* B."

The concrete trigger (label-dependent): after `actor duplicate` mints a `dup-<rand>` batch label, you
can address the batch (`find --label dup-<rand>`), but you cannot say "the lit ones in this batch AND
also `hero`" in one query.

## 2. The design — `-` sets the UNIVERSE, filters are a PREDICATE (the grep model)

`find` already *prints* a name set to stdout (one per line, in-tree order). The missing half is letting
it *read* one. The clean framing (chosen over the first draft's "subtract a set", §4):

**`actor find <filters> -` reads a newline-separated actor-name list from stdin (the `-` convention)
and treats that piped set `P` as the UNIVERSE it searches. The flag filters are a PREDICATE evaluated
over `P`; the output is the members of `P` that pass — in in-tree order.** A **`--exclude`** flag
NEGATES the predicate (the members of `P` that do *not* pass).

So with `-`, `find` filters the *piped* actors instead of the whole tree — exactly `grep`'s model
(the pipe is the universe, the pattern is the predicate, `-v` inverts). Boolean algebra falls out, and
crucially **both AND and NOT pipe in the SAME base set** (no pipe-direction inversion):

```bash
# AND  (in group A AND group B):
actor find --group A | actor find --group B -            # universe = A-set; keep those also in B  → A∩B

# AND across ANY dimensions, chained indefinitely:
actor find --folder castle.** | actor find --class-exact Light - | actor find --group lit -

# NOT / difference (in A but NOT B) — SAME pipe direction as AND, just add --exclude:
actor find --group A | actor find --group B --exclude -  # universe = A-set; drop those in B  → A∖B

# OR  (already works via the repeated flag; or union two finds, then re-normalize order — see §3):
actor find --group A --group B                           # OR-within-flag (unchanged)
{ actor find --group A; actor find --group B; } | sort -u | actor find -

# (label-dependent, once actor-labels ships) the trigger case — batch AND label:
actor find --label dup-9f3c | actor find --label hero -
```

The AND chain and the NOT chain read identically except for the `--exclude` — you always pipe the base
you are narrowing. That symmetry is the whole point of the grep framing.

## 3. Semantics (exact)

- **`-` is an optional trailing positional** on `find` (`find` has no positional today, so it is free;
  give it a `dest` distinct from `--name`'s `dest="name"`). Present → read a name list from stdin.
  Absent → search the whole tree, exactly as today (fully backward-compatible; `-` is opt-in). A
  non-`-` positional value is a clean exit-2 error (not silently ignored).
- **Result:** let `P` = the resolved piped-in set (the universe) and `pass(a)` = "actor `a` satisfies
  all the flag filters" (the *complete* filter chain — see the `--prop` note below).
  - default: output = `{ a ∈ P : pass(a) }`
  - `--exclude`: output = `{ a ∈ P : not pass(a) }`
  So the output is **always a subset of `P`**. (Consequence: you cannot select actors *outside* `P`
  — the "complement of an arbitrary name-set" is not expressible; §4 explains why that trade is right.)
- **`pass(a)` is the FINAL filtered predicate, INCLUDING `--prop`.** `--prop` is not evaluated inside
  `list_actors` (which is schema-free, `query.py:186-187`); it is a post-filter that rewrites `names`
  *after* the `list_actors` call (`dispatch.py:3143-3198`). The universe restriction therefore applies
  to the **final** `names` list, immediately before the print/`--json` at `dispatch.py:3199` — NOT to
  the raw `list_actors` return. (A naive intersect against the pre-`--prop` set would be wrong.)
- **`P` is canonicalized before the set op.** `list_actors`/the handler yield canonical stored names;
  Unreal FNames are case-insensitive (`query.py:245-246`). Each piped name is resolved to its canonical
  form via the case-insensitive `resolve_actor_name` path FIRST, so `wall_n` piped against a stored
  `Wall_N` matches. Resolution is **strict, all-or-nothing** — see §3.1.
- **Order is in-tree order** (the surviving members of `P` are emitted in `list_actors` order, not piped
  order). The piped set is a *membership universe*, not an ordering. (Contrast `actor show -`, which
  preserves *piped* order because it is a per-name dump, not a query. `find` is a query and stays
  tree-ordered.)
- **No filters + `-`:** `pass` is vacuously true, so `find -` = `P` itself (an identity / strict
  validator pass — it errors on any unknown piped name, §3.1). `find --exclude -` (no filters) = `∅`.
- **Empty stdin:** `P = ∅`, so BOTH `find -` and `find --exclude -` output nothing (exit 0) — a clean
  no-op in both directions, consistent with every other `-` verb (`dispatch.py:158-166`). (This is a
  point in the grep model's favour: under the rejected `M∖P` model, `--exclude` on empty stdin returned
  *everything*, an ugly asymmetry.)
- **`--json`:** emits the restricted set (`find` has **no** stderr count today and this spec adds none —
  it stays stdout-only; do NOT claim any stderr summary is "unchanged").
- **`--tree` interaction:** the piped names resolve against the SAME tree `find` is querying (its
  `--tree`, else `$UEDCLI_LEVEL`). A cross-tree pipe resolves each name in the target tree; a name
  absent there is an error under the strict rule (§3.1).
- **`--exclude` requires `-`:** `--exclude` without a piped set is meaningless → clean exit 2. It
  composes with all existing filters and with `--no-label`/`--no-folder`.

### 3.1 Unknown piped names — STRICT (Decision, was the §7 open choice)
A piped name absent from the target tree is a **clean exit-2 error naming every miss**, resolved via
`query.resolve_actor_names` (all-or-nothing). Rationale: this matches EVERY existing `-` consumer —
`actor show -` (`dispatch.py:3219`), `actor bbox -` (`dispatch.py:3244`), `actor folder … -`
(`dispatch.py:227`) — and the `CLAUDE.md` house rule ("a bad actor name must raise a clear error naming
the offending value, never a bare `KeyError`"). The earlier draft's "silently ignore unknown names"
would make `find` the sole lenient `-` verb and turn a piped typo into a silent wrong answer. The
cross-tree-intersection case (names valid in tree A, absent in B) is handled by the user pre-filtering,
not by silent drops. (This also makes `find -` a genuine validator — §3.)

## 4. Why the grep model, and why not the alternatives

- **Rejected — the first draft's "subtract the piped set" (`M∖P`).** There, `find <filters> --exclude -`
  meant *(filter matches over the whole tree) minus (piped set)*, so "A but not B" was
  `find --group B | find --group A --exclude -` — you piped in **B** (the set to remove) while the
  *kept* set A was named by the filters. That silently inverts the pipe direction relative to the AND
  chain (`find A | find B -`), so a user writing the natural `find --group A | find --group B --exclude -`
  got `B∖A` — the wrong answer, no error. The grep model makes AND and NOT pipe the same base. The only
  capability lost is *complement of an arbitrary piped name-set* (`universe ∖ P`), which is rare and
  usually expressible as a negated filter anyway. Worth it for the consistency.
- **Rejected — a `--where 'group:A and group:B and not class:Light'` expression DSL.** Maximal
  expressiveness, but a whole grammar/parser to build and maintain, a SECOND filter syntax competing
  with the existing flags, and poor pipe-composition. Against "small verbs compose." (A possible
  far-future power layer, not this.)
- **Rejected — per-dimension AND flags (`--all-labels`, …).** Solves only one same-dimension case per
  flag, needs a mirror flag per dimension, still no NOT.
- **Rejected — explicit `actor intersect`/`diff` set-op verbs.** Clunky two-input verbs needing process
  substitution; the `-` universe subsumes them from one input.

Repeated same-flag filters **stay OR** (consistency across the whole filter family); same-dimension AND
comes from chaining `find … | find … -`.

## 5. Module shape / touchpoints

- **`uedcli/cli.py`** — `find` gains an optional trailing positional accepting `-` (distinct `dest`,
  e.g. `restrict`), and a `--exclude` flag (help: "with `-`, keep the piped actors that DON'T match the
  filters instead of those that do"). Reject `--exclude` without `-`, and a non-`-` positional, at
  parse/dispatch.
- **`uedcli/dispatch.py`** — the `find` handler (`dispatch.py:3124-3205`): if `-` is present, read the
  stdin name list (`_resolve_target_names`, which strips/blank-drops; the handler dedupes via
  `dict.fromkeys` as the other verbs do — `_resolve_target_names` itself does NOT dedupe), resolve it
  strictly to canonical names (`resolve_actor_names`, §3.1), then keep/drop against the FINAL `names`
  list AFTER the `--prop` block (`dispatch.py:3199`), honoring `--exclude`. Preserve in-tree order by
  filtering `names` in place (it is already `list_actors`-ordered).
- **`uedcli/query.py`** — NO change to `list_actors` (stays filter-only, in-tree order preserved for
  free). Reuse `resolve_actor_names` for the strict `P` resolution.

No model/trunk change; a pure read-path/query feature.

## 6. Test strategy (host-native `bin/test`) — grounded in dimensions that exist today

1. **AND (universe ∩ predicate):** `find --group A | find --group B -` returns exactly the actors in
   BOTH A and B (fixture with A-only, B-only, A&B — only A&B survive).
2. **NOT (`--exclude`):** `find --group A | find --group B --exclude -` returns A-minus-B; SAME pipe
   direction as #1 (the regression that pins the grep model vs the rejected `M∖P` inversion).
3. **Chaining across dimensions:** `find --folder F | find --class-exact C - | find --group G -` equals
   the triple-AND.
4. **`--prop` ordering:** a query mixing `--prop K=V` with `-` restricts the POST-`--prop` set (fixture
   where `--prop` narrows the result; assert the restrict applies after it, not before).
5. **No-filter forms:** `find -` = the piped set (identity, in tree order); `find --exclude -` = empty.
6. **Empty stdin:** both `find -` and `find --exclude -` output nothing, exit 0.
7. **Order:** feed a scrambled piped list; output is in-tree order regardless.
8. **Case-fold:** a piped name in the wrong case still matches its canonical actor.
9. **Strict unknowns:** an unknown piped name → exit 2 naming it (all-or-nothing; nothing printed).
10. **Guards:** `--exclude` without `-` → exit 2; a non-`-` positional → exit 2; `--json` reflects the
    restricted set; `--tree` restricts against the named tree.

Use artificial groups/fixtures (`A`, `B`, `hero`, `dup-1337ab`).

## 7. Resolved sub-choices (2026-07-24, Andrzej)

1. **`--exclude` spelling** — confirmed **`--exclude`** (not `-v`/`--invert`/`--not`).
2. **`find -` (no-filter identity/validator)** — **KEPT** (a cheap strict name-set validator and the
   base of the union re-normalization `… | sort -u | find -`).
3. **Unknown piped names** — STRICT error, all-or-nothing (§3.1).
4. **Grep/universe model (§2)** — adopted (the piped set is the universe, filters are the predicate,
   `--exclude` negates). *Pending Andrzej's final confirm after the model explanation; recommended.*

## 8. Docs to update on build

- **`docs/usage.md`** — the `find` reference: the `-` universe input, `--exclude`, and a "boolean
  queries" example block (AND/OR/NOT) using existing dimensions.
- **`docs/leveldesign/`** — a short "selecting complex subsets" note (compose `find` for AND/NOT).
- **`architecture.md`** — `find` is now a name-set consumer too; the universe restriction lives in the
  dispatch handler AFTER the `--prop` stage, `list_actors` stays filter-only.
- **`decisions.md`** — append the resolved §7 sub-choices + the grep-model / strict-unknowns decisions.
- Fold this spec's durable outcome into `usage.md`/`architecture.md`, then it may be deleted.
