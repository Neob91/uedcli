+++
priority = "p?"
kind = "unknown"
summary = "`BRUSH ADDMOVER` + `ACTOR KEYFRAME NUM=#` — CONFIRMED console-drivable"
+++

# `BRUSH ADDMOVER` + `ACTOR KEYFRAME NUM=#` — CONFIRMED console-drivable

(2026-06-23,
Spike 7). `BRUSH ADDMOVER` creates a `Mover` actor (log: `Preparing brush <name>`);
`ACTOR KEYFRAME NUM=#` sets `KeyNum=N`. Keyframe POSITION requires T3D authoring
(`KeyPos(N)=(...)` + `NumKeys=N`). Superseded for authoring by the model-side mover support
(`to-build.md` #7); documented in `unrealed/commands.md`.
