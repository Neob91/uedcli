+++
priority = "p3"
kind = "chore"
summary = "`docs/usage.md` now under-states which verbs fail on an off-path actor class"
+++

# `docs/usage.md` now under-states which verbs fail on an off-path actor class

The
per-actor paragraph says "the verbs listed above exit 2 naming that class", listing only the
mover-aware verbs — but `apply.run_materialize` resolves every actor's class defaults before the
editor starts and raises `SchemaError` → clean exit 2 naming the class, so `level materialize`
fails the same way for a different reason (schema/defaults, not mover-ness). One sentence.
(2026-07-25, round-4 cold review.)
