+++
priority = "p1"
kind = "unknown"
summary = "Composable `actor find` — a stdin name-set input for FULL boolean queries (2026-07-24)"
+++

# Composable `actor find` — a stdin name-set input for FULL boolean queries (2026-07-24)

Today `find`'s repeated filter = OR within a dimension, different filters = AND across them; there is
**no same-dimension AND** (`--label X --label Y` is X OR Y, not "both") and **no NOT**. Rather than a
`--where` expression DSL (a whole grammar + a second filter syntax competing with the `--label`/
`--folder`/`--class` flags + poor pipe-composition), make `find` a CONSUMER of a name-set as well as a
PRODUCER: **`actor find <filters> -` restricts the search to the piped-in actors** (intersection),
with **`--exclude`** subtracting instead. Boolean algebra then falls out of pipes, exactly like the
mutating verbs' `-` convention: **AND** `find --label X | find --label Y -`; **AND across dimensions**
`find --folder castle.** | find --exact-class Light - | find --label hero -`; **OR** repeated flag or
`{ find --label X; find --label Y; } | sort -u`; **NOT** `find --label Y | find --label X --exclude -`
(X ∖ Y). One capability → full boolean, no DSL, no per-dimension `--all-labels` flags. Keep repeated
`--label` as OR (consistency with `--folder`/`--group`/`--exact-class`); AND comes from chaining.
**Orthogonal to the actor-labels spec** — a general `find` feature benefiting every dimension; do NOT
bloat the label spec with it. Rejected alternatives: `--where` DSL (overkill, second syntax);
per-dimension `--all-labels` (narrow, no NOT); explicit `actor intersect`/`diff` verbs (clunky
two-input, need process substitution — subsumed by the stdin restrict). Raised while speccing
actor-labels (`find --label` OR-within); Andrzej flagged high-prio.
