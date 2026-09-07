+++
priority = "p2"
kind = "debug"
summary = "FIXED by the OceanLab N=48 zone-retire port -- same cause, verified by rebuilding both sides at N=163."
spikes = ["dev/docs/spikes/2026-09-07-oceanlab-n48-lightbits/"]
+++

# UNATCO N=163 — 7 extra `Model.Lights` entries and 217 extra `LightBits` bytes — FIXED

Same root cause as `oceanlab-n48-world-model2-lightbits-differ-on`: the gather never retired a zone
whose span buffer had emptied, so it over-descended and left `NF_BoxOccluded` on nodes UED22 never
box-tests, which changes what a `PF_BrightCorners` shadow ray treats as solid. Verified, not
assumed — N=163 was rebuilt and gated before and after the change.
