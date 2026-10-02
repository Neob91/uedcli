+++
priority = "p2"
kind = "implement"
summary = "Namespace `COMPUTED_PROPS` by declaring class — `Engine.Mover.BasePos`, inherited by subclasses"
+++

# Namespace `COMPUTED_PROPS` by declaring class — `Engine.Mover.BasePos`, inherited by subclasses

p2. `normalize.COMPUTED_PROPS` is a flat set of BARE property names matched
case-insensitively against every actor (`is_computed_key`), so a name that is engine-computed on one
class is stripped from EVERY class that happens to declare it. That is a silent-data-loss shape: the
strip runs in `normalize_actor`, which feeds `canonical_actor_t3d` — the durable git-tracked trunk
emit AND the `MAP IMPORT` payload — so a wrong entry erases authored content from the source of
truth, not just from a comparison.
**This nearly happened.** Adding `SavedTrigger` alongside `SavedPos`/`SavedRot` (2026-07-25) looked
obviously right — same `Engine.Mover` runtime family — but `Engine.TriggerLight` declares its OWN
`SavedTrigger` and IS placeable, so the bare name would have silently stripped a real property from
every TriggerLight ever materialized. Caught by a cold reviewer, not by the code. `Tag` was moved out
of this set earlier for the same reason (5 TNM classes default it to `'Player'`). The current 12
entries are correct only because each was hand-audited; nothing enforces that.
**Proposal:** key entries as `<Package>.<Class>.<Prop>` (`Engine.Mover.BasePos`), scoped to the
DECLARING class and inherited by descendants (so `DeusEx.DeusExMover` picks up `Engine.Mover`'s
entries automatically).
**The load-bearing design question the spec must resolve:** class-scoped matching needs the actor's
ANCESTRY, i.e. a class resolver — but `normalize_actor` must stay schema-free, because
`canonical_actor_t3d`'s bytes may not depend on which packages happen to be installed (same trunk,
same bytes, every machine). The likely answer is the one the rest of the
2026-07-25 work converged on: move the computed-strip OFF the durable emit and onto the THROWAWAY
COMPARE COPY, where the schema is already available and `typedprops`/`ClassDefaults` already run —
which also stops the strip from mutating authored data at all. Spec should confirm that, or justify a
schema-free approximation.
**Also in scope:** re-audit all 12 existing entries against the same collision test (which other
classes declare each name, and are any placeable?); decide the fallback when a class is unresolvable
(hard-fail vs strip nothing); `actor prop`'s "won't persist" warning shares `is_computed_key` and
moves with it; and the parked `[debug]` `DistanceFromPlayer`/`LastRenderTime` item becomes decidable
once entries can be scoped. (Andrzej, 2026-07-25.)
