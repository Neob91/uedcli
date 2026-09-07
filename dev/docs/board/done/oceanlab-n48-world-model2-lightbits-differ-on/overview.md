+++
priority = "p2"
kind = "debug"
summary = "FIXED -- the visibility gather never retired a zone whose span buffer emptied, so it marked NF_BoxOccluded on nodes UED22 never box-tests, unshadowing three PF_BrightCorners surfs' edge lumels."
spikes = ["dev/docs/spikes/2026-09-07-oceanlab-n48-lightbits/"]
+++

# OceanLab N=48 world Model2 LightBits differ on three surfs — FIXED

28 bytes over lightmap records 182/183/201 (surfs 194/204/209), all `PF_BrightCorners`, all at the
grid's `u = 0`/`u = 1` edge. Root cause: `visible_surfs.rs` was missing `URender::OccludeBsp`'s zone
retire (`render.dll 0x1001a737`–`0x1001a7e5`), so native's gather kept descending after the editor
had abandoned the traversal and marked `NF_BoxOccluded` on world node 512, which
`linecheck::is_csg` then treats as non-solid for a `0x14` `ExtraNodeFlags` shadow ray. Live probe at
the first `illuminateSurf`: UED22 carries the bit on `{32, 80, 160, 352}`, native on twelve nodes.
With the retire ported, native's box-test count and final flag set match the editor exactly.
