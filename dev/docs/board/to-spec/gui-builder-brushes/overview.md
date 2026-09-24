+++
priority = "p?"
kind = "implement"
summary = "GUI: a UED22-style red builder brush — build/reshape/move/CSG-toggle, commit to trunk"
+++

# GUI builder brushes

Add a UED22-style builder brush to the GUI: build a parametric shape (cube/cylinder/cone/sheet/
staircase/extrude/revolve), preview it as the scratch red brush, reposition/rotate/re-shape/toggle
CSG add-vs-subtract, then commit it into the trunk as a real placed brush. Reuses existing model-side
brush builders and edit verbs end to end — no brush-geometry or CSG logic duplicated in the GUI
frontend. See `spec.md`.
