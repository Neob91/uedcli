+++
priority = "p3"
kind = "implement"
summary = "A brush that contributes NOTHING to the CSG result should be reported"
+++

# A brush that contributes NOTHING to the CSG result should be reported

Hit
live 2026-07-26 while building the curved-track spike fixture: replacing a room with a taller one
put the new subtract AFTER the track bed in CSG order, so it carved the track away. The level then
rendered solid black with no error, no warning, and nothing to indicate which brush had vanished or
why — `actor order Room --first` fixed it, but only after the cause was guessed. CSG is behaving
exactly as specified (order = precedence); the gap is diagnostic. `level doctor` already reports
"a subtract that carves nothing" (`docs/usage.md`), so the symmetric case — an ADD wholly consumed
by a later subtract — belongs beside it. Cheap to detect model-side and it turns a black screenshot
into a named actor.
