+++
priority = "p2"
kind = "debug"
summary = "native materialize: a transient schema-resolve failure silently strips ALL of a class's props"
+++

# native materialize: a transient schema-resolve failure silently strips ALL of a class's props

— **native materialize: a transient schema-resolve failure silently strips ALL of a
class's props** (`native/materialize.py:260`, silent-swallow audit 2026-07-18). `except Exception:
cache[fqcn] = {}` is far broader than "class has no schema" — an absent package, an `OSError` on a
`.u`, or a resolver bug all collapse to `{}`, so the caller treats every prop as untyped and DROPS
them; the level materializes SILENTLY incomplete instead of failing loudly. Fix: narrow to
`except SchemaError` (or surface the real error) so a real fault ≠ "no schema".
