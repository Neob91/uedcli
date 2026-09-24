+++
priority = "p?"
kind = "implement"
summary = "GUI: a UED22-style red builder brush — build/reshape/move, Add/Subtract stages a new brush"
+++

# GUI builder brushes

Add a UED22-style builder brush to the GUI: build a parametric shape (cube/cylinder/cone/sheet/
staircase/extrude/revolve), preview it as the scratch red brush, reposition/rotate/re-shape it, then
press Add or Subtract to clone it into a new staged brush with that CSG operation (the builder brush
itself is untouched) — reaching the trunk only on the existing Save action. Reuses existing model-side
brush builders and edit verbs end to end — no brush-geometry or CSG logic duplicated in the GUI
frontend. See `spec.md`.
