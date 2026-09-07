+++
priority = "p1"
kind = "debug"
summary = "FIXED — the beam clip took its crossing vertex from `alpha = dp/(dp-ds)`; `SplitWithPlaneFast` uses `FLinePlaneIntersection`, whose f32 differs in the last ulps. WanChai N=44 -> 45, and the same fix took OceanLab to 93 and Island to 123."
spikes = ["dev/docs/spikes/2026-09-07-gather-box-verdict/"]
+++

# WanChai N=45 — leaf 20 got one permeating light UED22 does not

A live `FEditorVisibility::ActorVisibility` capture put it on one crossing: leaf 24 → 25, which
native took and the editor did not. Native's clip polygon entering leaf 24 carried `1344.0` where
the editor's carried `1343.99988`, which collapsed that beam's last edge to zero length —
`clip_beam` skips a degenerate edge, so it dropped a constraint the editor still clipped by.

`FPoly::SplitWithPlaneFast` (`Engine.dll 0xa1f90`) does not interpolate the crossing; at `0xa214b`
it calls `FLinePlaneIntersection` (`0xa07c0`), which re-derives the numerator from `P1` and dots the
DIFFERENCE vector with the normal. Same point in exact arithmetic, different f32. Ported as
`permeating_lights::line_plane_intersection`; all 11 of WanChai N=45's lights then match the capture
leaf for leaf and crossing for crossing.
