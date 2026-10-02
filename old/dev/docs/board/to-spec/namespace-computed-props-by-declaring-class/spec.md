# Spec — namespace `COMPUTED_PROPS` by declaring class

Status: DRAFT for owner review. Every fork is an `AskUserQuestion`; the two blocking ones are in
`questions/`.

## Goal

Stop `normalize.COMPUTED_PROPS` from stripping an engine-computed property name off a class that
declares that name as real authored content. Make each entry apply only to the class that declares
it (and its subclasses), not to every actor that happens to carry the name.

## Current state

- `normalize.COMPUTED_PROPS` (`uedcli/normalize.py:60`) is a flat `frozenset` of **bare** names:
  `TimeSeconds, Summary, Region, OldLocation, NavigationPointList, PawnList, nextNavigationPoint,
  prevNavigationPoint, Level, bSelected, BasePos, BaseRot, SavedPos, SavedRot` (14 exact) plus the
  prefix `AIProfile` (`_COMPUTED_PREFIXES`, `normalize.py:95`). (The overview says "12"; the set is
  14+1 today.)
- `is_computed_key(key)` (`normalize.py:108`) matches case-insensitively against the bare name — no
  class context.
- It is consumed in two places:
  - `normalize_actor` (`normalize.py:139`) drops matching props. This feeds
    `canonical_actor_t3d` (`normalize.py:453`) — **the durable git trunk emit, the `MAP IMPORT`
    payload, `actor show`, stash/prefab bodies** — so a wrongly-scoped entry erases authored content
    from the source of truth, not just from a comparison.
  - the compare copy `_actor_values` (`normalize.py:417`), which is schema-aware already (it holds
    `info: ClassInfo`).
- The strip runs at two data-entry points, both reachable with a project:
  - **ingest**: `store_export.py:71` calls `normalize_level` when a `.dx` is imported to the trunk —
    this is where engine-computed fields (`BasePos`, `SavedPos`, …) actually enter, since a
    uedcli-authored actor never carries them;
  - **durable emit**: `canonical_actor_t3d` re-runs `normalize_actor` per actor (idempotent belt-and-
    suspenders over already-clean trunk data).
- The correctness of the 14 entries rests on hand audits recorded inline (`normalize.py:84-92`):
  `SavedTrigger` was kept OUT because `Engine.TriggerLight` declares its own and is placeable;
  `Tag` was moved out earlier because 5 TNM classes default it. Nothing enforces the audit.
- A class resolver that gives ancestry already exists: `ClassIndex.ancestry` / `descends_from`
  (`uedcli/classindex.py:149,188`), built offline from the composed `.u` path.
- The `actor prop set` "won't persist" warning shares `is_computed_key` (`propedit.py:659`).

## The load-bearing constraint

Class-scoped matching needs the actor's ancestry, i.e. a class resolver. But `canonical_actor_t3d`
**must stay schema-free**: its bytes may not depend on which packages are installed (same trunk,
same bytes, every machine — `unrealed/t3d.md`, `architecture.md` "compare view vs identity hash").
So a class-scoped strip cannot live inside `canonical_actor_t3d`. That forces the design.

## Design

### Entry format

Key each entry as `<Package>.<Class>.<Prop>`, scoped to the **declaring** class and **inherited by
descendants**. `DeusEx.DeusExMover` then picks up `Engine.Mover.BasePos` automatically via
`ClassIndex.descends_from(actor_fqcn, "Engine.Mover")`. Proposed re-keying of today's set:

| bare name today | proposed scoped key | declaring class (to verify at build)
|--------------------|------------------------------|---
| `BasePos`/`BaseRot` | `Engine.Mover.BasePos` / `.BaseRot` | `Engine.Mover`
| `SavedPos`/`SavedRot` | `Engine.Mover.SavedPos` / `.SavedRot` | `Engine.Mover`
| `AIProfile` (prefix) | `Engine.Pawn.AIProfile` (prefix, scoped) | `Engine.Pawn` / `Engine.ScriptedPawn`
| `Level`, `bSelected`, `OldLocation`, `Region` | `Engine.Actor.<Prop>` | `Engine.Actor` (every actor carries them)
| `TimeSeconds`, `Summary`, `NavigationPointList`, `PawnList` | `Engine.LevelInfo.<Prop>` | `Engine.LevelInfo` (LevelInfo-only)
| `nextNavigationPoint`, `prevNavigationPoint` | `Engine.NavigationPoint.<Prop>` | `Engine.NavigationPoint`

The exact declaring class of each is what the build-time re-audit must confirm (the table above is
the proposal, not verified) — several of today's "global" entries are actually declared on
`LevelInfo`/`NavigationPoint`, not `Actor`, and scoping each to its true declarer is the point of the
exercise. All of it stays ONE matching rule (`descends_from(actor, entry_class)`); an
`Engine.Actor`-scoped entry still strips from every actor, exactly as today.

### Where the strip runs (the central fork — `questions/strip-location.md`)

Two coherent designs; the spec recommends **A**.

- **A. Compare-only + schema-aware ingest.** Remove the strip from `canonical_actor_t3d`/
  `normalize_actor` entirely. Keep it in `_actor_values` (already schema-aware). Add a schema-aware
  strip on the **ingest** path (`store_export.normalize_level`, which has a resolvable project) so
  imported map data is cleaned before it lands in the trunk. `canonical_actor_t3d` then passes
  authored data through verbatim and stays schema-free — and can never mutate a real property again.
  This is what the rest of the 2026-07-25 typed-compare work converged on (move reductions off the
  durable emit onto the throwaway copy).
- **B. Schema-free proven-safe bare-name strip.** Keep a bare-name strip in `canonical_actor_t3d`,
  but pin an **offline audit test** that fails if any entry's bare name is declared, with authored
  meaning, by a placeable class other than the intended one. Adds class-scoping only to the compare
  copy. Simpler diff, but the durable emit keeps a (now test-guarded) power to over-strip, and the
  audit test needs the game `.u` to run.

Recommendation: **A** — it removes the whole silent-data-loss shape the item was filed against,
rather than guarding it. Cost: the ingest gate gains a class-resolver requirement (already true for
class qualification on `level import`, so no new dependency in practice).

### Unresolvable class (the second fork — `questions/unresolvable-class-fallback.md`)

Under A the ingest strip needs the actor's ancestry. When the class will not resolve (missing
package), the choices are: **hard-fail exit 2** naming the actor/class (the house no-fallback rule);
**strip nothing** for that actor (leave computed props in the trunk); or a **schema-free bare-name
fallback** for that actor only. Recommendation: **hard-fail**, consistent with
`conventions.md` "no fallbacks" and with `level import` already requiring a resolvable path to
qualify classes — but this is an owner call because it makes `level import` newly fail on an actor
whose class package is absent.

## Edge cases & errors

- Actor whose class resolves but is not a descendant of any scoped entry's class → nothing stripped
  (correct: `Engine.TriggerLight.SavedTrigger` survives because no entry is scoped to it).
- Cyclic/broken super chain in a corrupt `.u` → `ClassIndex.ancestry` already truncates with a
  stderr note (`classindex.py:149`); the strip then simply matches fewer entries, never crashes.
- `AIProfile` prefix scoped to `Engine.Pawn`: verify offline that only Pawn descendants carry it, or
  keep it root-scoped if any non-Pawn placeable class declares an `AIProfile*` field.
- `actor prop` "won't persist" warning: `is_computed_key` gains a class argument and moves with the
  new matcher; the warning needs the actor's class (it has it) and a resolver (the prop verbs
  already build one). A no-resolver context downgrades to no warning, not a wrong one.

## Tests

- Re-key regression pins in `test_normalize.py` to the scoped grammar; keep the existing
  round-trip-identity assertions.
- New: a `TriggerLight` carrying an authored `SavedTrigger` survives `canonical_actor_t3d` (the bug
  the item names) — this passes trivially under A, and is the guard under B.
- New: a `DeusEx.DeusExMover` still has `BasePos`/`SavedPos` stripped (inheritance works).
- Offline audit test (B, or a belt for A): no scoped entry's name is declared with authored meaning
  by a placeable class outside its scope — the `SavedTrigger` near-miss, mechanised.
- Ingest test (A): importing a `.dx` with mover sentinels yields a trunk with none.

## Open questions

- `questions/strip-location.md` — A (compare-only + schema-aware ingest) vs B (schema-free
  proven-safe bare-name strip).
- `questions/unresolvable-class-fallback.md` — hard-fail vs strip-nothing vs schema-free fallback
  when a class will not resolve during the ingest strip.

Out of scope (separate items): whether to ADD `DistanceFromPlayer`/`LastRenderTime`
(board `distancefromplayer-lastrendertime-look-like`) — becomes a clean per-class decision once
entries can be scoped, but stays that item's call.
