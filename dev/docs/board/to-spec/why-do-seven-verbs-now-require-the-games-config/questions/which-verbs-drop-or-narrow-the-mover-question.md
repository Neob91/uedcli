# Which call sites drop or narrow the games-config (mover) requirement?

## Context

Schema-aware `is_mover` gave seven verbs + the `*preview` path a project-and-`config.toml`
requirement; only `level doctor` was sanctioned. Per-site analysis (spec "Current state"):

Recommended scoping set:

- **Drop the question (loses an observable output):**
  - `brush scale` — mover check only WARNS "keyframe travel does not scale". Drop → resolver-free;
    the warning goes (no name-suffix substitute).
  - `event graph` — mover check only adds an isolated node for a tagless mover. Drop → resolver-free;
    a tagless mover no longer shows as a lone node (eventing movers and the lint are unaffected).
- **Narrow the question (no behaviour change; drops the requirement only in the common case):**
  - `stash capture` — resolve the index only when a candidate carries a `KeyNum` prop; trunk captures
    (canonical movers) become resolver-free.
  - `brush intersect`/`deintersect` — build the index only when the piped set has a qualified class
    other than `Brush`; an all-generator pipe stays resolver-free.
- **Keep (correctness):** `mover key`, `level doctor`, `brush apply-transform`.

Rejected throughout: a name-suffix fallback, an optional silently-degrading resolver, a second
predicate, and reordering `is_mover` itself (decisions.md 2026-07-25 10:18). All changes are at the
call site.

Confirming this set also authorises the follow-on: reword `direction/conventions.md` lines 88-93 to
the kept set, and a superseding `decisions.md` entry (exact text proposed after this answer). Adjust
any row.

## Answer

<!-- Empty = open. -->
