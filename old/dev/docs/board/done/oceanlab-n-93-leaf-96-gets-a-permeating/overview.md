+++
priority = "p2"
kind = "debug"
summary = "FIXED with `wanchai-n45-leaf-20-permeating-light-over-included` — the beam clip's crossing vertex came from the wrong f32 rearrangement. OceanLab N=92 -> 93."
spikes = ["dev/docs/spikes/2026-09-07-gather-box-verdict/"]
+++

# OceanLab N=93 — world leaf 96's permeating run carried Light111, which UED22 leaves out

Same cause as `wanchai-n45-leaf-20-permeating-light-over-included`: the permeating-light beam clip
built its crossing vertex as `alpha = dp/(dp-ds)` where `SplitWithPlaneFast` calls
`FLinePlaneIntersection`, and the f32 difference collapsed a later clip edge to zero length. N=93
gates byte-exact with that fix.
