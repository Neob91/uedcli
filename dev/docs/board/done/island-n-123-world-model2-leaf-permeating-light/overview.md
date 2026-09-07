+++
priority = "p2"
kind = "debug"
summary = "FIXED with `wanchai-n45-leaf-20-permeating-light-over-included` — the beam clip's crossing vertex came from the wrong f32 rearrangement. Island N=122 -> 123."
spikes = ["dev/docs/spikes/2026-09-07-gather-box-verdict/"]
+++

# Island N=123 — world leaf 26 got a permeating-light run UED22 leaves empty

Not the portal graph (that was already ruled out here) and not the beam-clip algorithm as decoded:
`SplitWithPlaneFast` takes its crossing vertex from `FLinePlaneIntersection`, whose f32 differs from
the `alpha = dp/(dp-ds)` native used, and a crossing that lands exactly on a grid coordinate
collapses the next hop's clip edge to zero length. Root-caused on WanChai N=45 against a live
`ActorVisibility` capture; N=123 gates byte-exact with the same fix.
