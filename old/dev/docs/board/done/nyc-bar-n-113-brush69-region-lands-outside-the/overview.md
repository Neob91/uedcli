+++
priority = "p1"
kind = "debug"
summary = "DONE — NYC_Bar N=113's `Brush69` Region fell out of the tree because native evaluated the node plane in f64 where `FPlane::PlaneDot` is single-precision SSE. Same root cause and same fix as Island N=10; byte-exact, no mask."
spikes = ["dev/docs/spikes/2026-09-06-pointregion-planedot-f32/"]
+++

# NYC_Bar N=113 — `Brush69`'s `Region` descends out of the world

Fixed 2026-09-06 by the Island N=10 fix — one root cause, two levels. `Brush69`'s pivot
`(-384, -440, 0)` sits ON world node 272's plane. Native's f64 dot made it `-7.629e-06` (back, off
the tree, `iLeaf -1` / zone 0); `FPlane::PlaneDot` (`Core.dll 0x10024e60`) is an SSE horizontal add
in SINGLE precision and gives exactly `0.0`, which `setae` takes as front — leaf 55, zone 1.

Detail: `dev/docs/spikes/2026-09-06-pointregion-planedot-f32/spike.md`.
