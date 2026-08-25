+++
priority = "p2"
kind = "debug"
summary = "materialize mishandles a trunk actor named DefaultBrush (silent only under --no-verify)"
+++

# materialize silently drops a trunk actor named DefaultBrush

`native/unbuilt.py:207-256` (`assemble_unbuilt`). The synthesized builder-brush actor is hardcoded
`dbrush = "DefaultBrush"` (line 207). Trunk brush actors and the final `Actors[]` order are then
filtered with `x.name != dbrush` (line 217) and `n not in (li_name, dbrush)` (line 255). Unlike the
`LevelInfo0` collision — which routes through `_reserve`'s duplicate-name guard and raises loudly —
the `DefaultBrush` exclusion happens in the list comprehension BEFORE any reserve, so a real trunk
actor so named is never reserved and never warned about.

Trigger: `brush build … | actor add DefaultBrush -`, then `level materialize`.

Scope correction (double-check): the drop is NOT silent under a normal `level materialize`. The H3
post-verify (`apply.py:276` → `verify.py:135-139`) strips the synthetic builder brush from the built
compare view (`is_builder_brush` keys on inner model name `Brush`, `normalize.py:142-160`) but keeps
the genuine trunk actor in the expected view, so it reports a loud exit-2
`"actor 'DefaultBrush' … MISSING from the built map"` and writes nothing. The failure is real but
MISDIAGNOSED (blamed on a missing actor, not a reserved-name collision). It is only truly SILENT
under `--no-verify`. Low likelihood (users rarely name a brush `DefaultBrush`).

The code defect is still real: `unbuilt.py:217` (`… if x.name != dbrush`) and `:254-255`
unconditionally drop a brush actor named `DefaultBrush` with no reserved-name check, asymmetric with
`_reserve`'s duplicate guard (`assemble.py:91-93`) that would catch the NON-brush case loudly.

Fix (double-checked, CONFIRMED): DELETE the two `!= dbrush` exclusion filters so a colliding brush
name naturally hits `_reserve`'s duplicate `ValueError` — a no-op for every level without the
pathological name, and `apply.py:431-439` already turns that `ValueError` into a clean exit-2
`"materialize failed (nothing written): duplicate export object name: 'DefaultBrush'"`. Regression
test. (Do NOT "add a guard and keep the filter" — the filter is what bypasses the existing guard.)
