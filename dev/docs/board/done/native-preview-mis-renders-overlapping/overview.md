+++
priority = "p1"
kind = "debug"
summary = "Native preview mis-renders overlapping subtractive DOORWAYS, and `doctor` says \"no issues\" — FIXED"
+++

# Native preview mis-renders overlapping subtractive DOORWAYS — fixed

Fixed by `8fd9b2cf` (2026-08-24, "Render level preview --native with the faithful bspcsg CSG
core"): `build_scene` swapped the coarse `build_geometry` core (which dropped ~69% of surfaces) for
`build_geometry_bspcsg`, exactly the root cause this item diagnosed. Never moved to `done/` after
landing. Re-verified 2026-09-11: two real UNATCO renders (an office, a stairwell with a visible
doorway opening) show zero magenta missing-texture artifacts. This was the documented reason
`level photo` defaulted to `--game`; with it fixed, the default flipped to `--native` (board
`bake-lighting-into-level-photo-native`).
