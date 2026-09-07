+++
priority = "p3"
kind = "debug"
summary = "Closed as a mis-measurement: the probe captured `BoundVisible`'s return, not `OccludeBsp`'s post-zone-loop verdict, and the compare key rounded one f32 two ways. Re-measured, native's gather matches the live editor on all 1218 calls."
spikes = ["dev/docs/spikes/2026-09-07-gather-box-verdict/"]
+++

# The gather still over-occludes against the live editor — it does not

The 49 "disagreements" were native's post-zone-loop verdict against the capture's pre-zone-loop
`BoundVisible` return (NULL `FSpanBuffer*` under `bUseZones`); the 45/45 "only" keys were one light
whose f32 Y rounds two ways under `round(v, 2)`. With the outcome sites captured and an f32-bit key,
OceanLab N=48 and WanChai N=45 both match the editor on every box test — same set, same order, same
screen rectangles, same verdicts. No native change.
