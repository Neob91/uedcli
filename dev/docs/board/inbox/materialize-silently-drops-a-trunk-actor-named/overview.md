+++
priority = "p2"
kind = "debug"
summary = "materialize silently drops a trunk actor named DefaultBrush"
+++

# materialize silently drops a trunk actor named DefaultBrush

`native/unbuilt.py:207-256` (`assemble_unbuilt`). The synthesized builder-brush actor is hardcoded
`dbrush = "DefaultBrush"` (line 207). Trunk brush actors and the final `Actors[]` order are then
filtered with `x.name != dbrush` (line 217) and `n not in (li_name, dbrush)` (line 255). Unlike the
`LevelInfo0` collision — which routes through `_reserve`'s duplicate-name guard and raises loudly —
the `DefaultBrush` exclusion happens in the list comprehension BEFORE any reserve, so a real trunk
actor so named is never reserved and never warned about.

Trigger: `brush build … | actor add DefaultBrush -`, then `level materialize`. Exits 0, no warning,
the brush is absent from the export table and `Actors[]` — a room it should carve is missing from
the built map.

Low likelihood (users rarely name a brush `DefaultBrush`) but a silent geometry drop — violates
"no silent half-answers."

Fix: reserve `DefaultBrush` against real trunk names (route it through the same duplicate-name guard
`LevelInfo0` uses) so a collision exits 2 naming the actor. Regression test.

Confirmed by direct read.
