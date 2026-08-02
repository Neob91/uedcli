+++
priority = "p2"
kind = "implement"
summary = "Composable `actor find` — stdin name-set input for full boolean queries"
+++

# Composable `actor find` — stdin name-set input for full boolean queries

Spec
written + **two cold reviews folded** (the `--exclude` semantics changed from "subtract the piped set"
(`M∖P`) to a **grep/universe model**): [`plan.md`](plan.md).
Makes `actor find` accept a name set on stdin (`-`) so filters COMPOSE into full boolean queries —
today `--label` (and every other dimension) ORs within itself, so "label X AND Y" is inexpressible.
Model: the piped set is the **universe**, the filters are the **predicate**, `--exclude` negates.
Sub-choices resolved in `direction/conventions.md` (2026-07-24 10:02 UTC): negation spelled `--exclude`; the
no-filter `find -` identity/validator form KEPT (base of the union re-normalization
`… | sort -u | find -`); an unknown piped name is a **strict all-or-nothing exit 2**. Orthogonal to
actor-labels — it benefits every filter dimension and changes no filter's OR-within semantics.
**One soft confirm outstanding:** the grep/universe model is recorded as the working model pending
Andrzej's final yes (`direction/conventions.md`, 2026-07-24 10:02). Otherwise ready to plan. (Andrzej, 2026-07-24.)
