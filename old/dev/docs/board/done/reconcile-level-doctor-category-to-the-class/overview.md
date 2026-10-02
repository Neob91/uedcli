+++
priority = "p3"
kind = "implement"
summary = "Reconciled `level doctor --category` to the `class show --category` shape — SHIPPED"
+++

# Reconcile `level doctor --category` to the `class show --category` shape

`level doctor --category` is now `action="append"` (repeatable, ORs), case-insensitive, and exits 2
via `CommandError` naming the first bad value with the sorted valid categories. Comma-split dropped
outright, no alias (owner 2026-08-02): `--category watertight,convex` fails naming the whole token.
Doctor lint and the exit-code-over-all-findings rule unchanged. `docs/usage.md` and the parser
baseline updated. Review: clean.
