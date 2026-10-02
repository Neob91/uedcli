+++
priority = "p2"
kind = "unknown"
summary = "`find` RELATIONAL predicates — the deferred third \"conditionals\" family (2026-07-24)"
+++

# `find` RELATIONAL predicates — the deferred third "conditionals" family (2026-07-24)

Cross-actor reference filters, beyond what `--prop Base=X` incidentally catches: e.g. `--references
<actor>` (actors whose object-prop refs point AT the target), mover/trigger pairing by `Tag`/`Event`,
actors sharing a `Group`. Substrate-specific semantics (which fields are refs; DeusEx vs stock
Unreal), the most complex of the three families — Andrzej deferred it while the property + spatial
specs (`spec.md`, `spec-find-spatial.md`) go first. Adds
ATOMS to the composable-`find` boolean model, orthogonal to it. Spec when the first two land.
