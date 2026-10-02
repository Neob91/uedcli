# When a class will not resolve during the ingest strip, hard-fail, strip nothing, or fall back to bare-name?

## Context

Under design A the ingest strip (`store_export.normalize_level`) needs the actor's ancestry to decide
which scoped entries apply. When the class will not resolve (its package is absent from the path),
the options are:

- **Hard-fail exit 2** naming the actor and class — the house rule (`conventions.md` "no fallbacks";
  "a predicate answers or it RAISES"). `level import` already needs a resolvable path to qualify
  classes, so this is consistent, but it makes import newly fail on an actor whose class package is
  missing where today it silently kept whatever the map held.
- **Strip nothing** for that actor — leaves engine-computed props (`SavedPos`, …) in the trunk for
  that actor, i.e. a dirty trunk rather than an error.
- **Schema-free bare-name fallback** for that one actor — reintroduces exactly the over-strip risk
  the item exists to remove, but only for the unresolvable case.

Recommendation: **hard-fail** — but this is a real behaviour change to `level import`, so it is the
owner's call.

## Answer

<!-- Empty = open. -->
