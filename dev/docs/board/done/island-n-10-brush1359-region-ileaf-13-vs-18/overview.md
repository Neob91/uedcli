+++
priority = "p2"
kind = "debug"
summary = "DONE — Island N=10's `Brush1359` Region iLeaf 13-vs-18 was native evaluating the node plane in f64 where `FPlane::PlaneDot` is single-precision SSE. Fixed faithfully; byte-exact, no mask. Same root cause as NYC_Bar N=113."
spikes = ["dev/docs/spikes/2026-09-06-pointregion-planedot-f32/"]
+++

# Island N=10 — `Brush1359`'s `Region` iLeaf

Fixed 2026-09-06. `Brush1359`'s pivot `(-11680, 4528, -384)` sits ON world node 22's plane. Native's
f64 dot made it `-9.632e-05` (back, leaf 13); the editor's `FPlane::PlaneDot` (`Core.dll 0x10024e60`)
is an SSE horizontal add in SINGLE precision — `(P.Z*Z + -W) + (P.Y*Y + P.X*X)` — which gives exactly
`0.0`, and `setae` takes that as front (leaf 18).

`materialize._plane_dot` now reproduces that expression exactly and `_model_point_region` uses it.
Detail: `dev/docs/spikes/2026-09-06-pointregion-planedot-f32/spike.md`. Regression:
`dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/test_pointregion_planedot_f32.py`.
