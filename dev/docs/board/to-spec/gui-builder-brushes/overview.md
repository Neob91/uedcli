+++
priority = "p?"
kind = "implement"
summary = "GUI: a UED22-style red builder brush, exposed as one ordinary reserved-name actor"
+++

# GUI builder brushes

Add a UED22-style builder brush to the GUI, exposed to the frontend transparently — as one ordinary
actor under a reserved Name, always present in the scene, edited through the same staged-edit
mechanism a real actor's edits use. Build a parametric shape (cube/cylinder/cone/sheet/staircase/
extrude/revolve), reposition/rotate/re-shape it, then press Add or Subtract to clone it into a new
staged brush with that CSG operation (the builder brush itself is untouched) — reaching the trunk only
on the existing Save action. Reuses existing model-side brush builders and edit verbs end to end — no
brush-geometry or CSG logic duplicated in the GUI frontend, and no parallel API surface. See
`spec.md`.
