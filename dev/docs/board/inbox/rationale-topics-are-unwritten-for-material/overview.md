+++
priority = "p2"
kind = "chore"
summary = "`rationale/` topics are unwritten for material the drafters surfaced"
+++

# `rationale/` topics are unwritten for material the drafters surfaced

Agent-owned
engineering decisions with no home yet: the schema-cache mechanism (stat tuple over content hash,
per-package primitives over compositions, marshal over JSON, the frozen-golden version guard);
the intersect `BUILDER_PAD`/seed-subtract findings; the actor-name resolution implementation
(case-fold the dict key, per-callsite try/except); the `root_outside` CSG detail. `rationale/`
currently holds only `cli.md`, `emit.md`, `README.md`, `MIGRATION.md`. *(Multiple drafters,
2026-07-26.)*
