+++
priority = "p?"
kind = "unknown"
summary = "`ACTOR DUPLICATE`/`MIRROR`/`APPLYTRANSFORM` — CONFIRMED console-drivable"
+++

# `ACTOR DUPLICATE`/`MIRROR`/`APPLYTRANSFORM` — CONFIRMED console-drivable

(2026-06-23,
Spike 8). `ACTOR DUPLICATE` copies selection with ~16uu XY offset. `ACTOR MIRROR X=-1`/`Y=-1`/
`Z=-1` sets `MainScale` per-axis (corrected from the wrong `BRUSH MIRROR XY` inference).
`ACTOR APPLYTRANSFORM` bakes scale into vertices. uedcli does symmetry model-side; these console
verbs are documented for completeness in `unrealed/commands.md`. (The model-side `actor mirror`
CLI verb is tracked in `to-spec.md`.)
