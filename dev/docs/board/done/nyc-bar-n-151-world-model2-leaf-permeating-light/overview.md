+++
priority = "p2"
kind = "debug"
summary = "FIXED — the permeating-light beam clip built its clip planes from an unnormalized cross product, so `SplitWithPlaneFast`'s 0.25 epsilon was scaled to nothing and the flood over-reached. NYC_Bar N=150 -> N=152."
spikes = ["dev/docs/spikes/2026-09-06-permeating-beam-plane-normalize/"]
+++

# NYC_Bar N=151 — world `Model2` leaf 74 got a permeating-light run UED22 does not

`FPlane(A,B,C)` normalizes (`core.dll 0xb440` -> `FVector::SafeNormal`), so
`FPoly::SplitWithPlaneFast`'s `+/-0.25` is a world-unit epsilon. Native's `clip_beam` built the same
cross product but left it unnormalized (length ~1e4 for room-scale geometry), which turned the
epsilon off and let the beam carry slivers the editor rejects whole. Fixed in
`permeating_lights.rs` with `safe_normal`/`plane_w`/`plane_dot`, plus the 14-vertex guard as the
editor's `break` rather than a truncate. Spike:
`dev/docs/spikes/2026-09-06-permeating-beam-plane-normalize/`.

NYC_Bar now gates byte-exact N=1..152 and bails at N=153 on a different array —
`nyc-bar-n-153-world-model2-lightmap-runs-ued22`. Island N=123, which looked like the same bug, is
not: `island-n-123-world-model2-leaf-permeating-light`.
