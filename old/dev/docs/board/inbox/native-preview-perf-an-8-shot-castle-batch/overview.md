+++
priority = "p3"
kind = "implement"
summary = "Native preview perf: an 8-shot castle batch is ~11.5 s vs the ≤10 s soft target, and 8.0 s of it is `build_geometry` (the CSG carve) — the rasterizer is 0.35 s/frame"
+++

# Native preview perf: an 8-shot castle batch is ~11.5 s vs the ≤10 s soft target, and 8.0 s of it is `build_geometry` (the CSG carve) — the rasterizer is 0.35 s/frame

p3.
Preview needs neither collision hulls nor lighting; a build flag skipping `bsp_build_bounds`
(and any other materialize-only pass) for preview builds is the lever — COORDINATE with the
native-materialize line (it owns `build.rs`/`passes.rs`; measured in
`spikes/2026-07-16-native-preview-anchor/perf.md`).
