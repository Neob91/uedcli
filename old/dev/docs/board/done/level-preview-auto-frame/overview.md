+++
priority = "p?"
kind = "implement"
summary = "`level preview` auto-frame replaced the broken POS@ROT camera posing"
+++

# `level preview` auto-frame

`level preview` used to pose its camera with a `POS@ROT` string that the editor did not
honour, so previews pointed at nothing. Auto-frame computes the camera from the bounding box of
what is being previewed instead. Shipped 2026-07-12.

This item exists to hold the spec, which no board entry owned.
