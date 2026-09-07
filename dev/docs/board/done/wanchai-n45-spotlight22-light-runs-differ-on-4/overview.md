+++
priority = "p1"
kind = "debug"
summary = "Closed as a mis-measurement: `lmdiag.py` read `FLightMapIndex.VClamp` as `iLightActors`, so the four divergent Spotlight22 runs never existed. N=45's real blocker is `wanchai-n45-leaf-20-permeating-light-over-included`."
spikes = ["dev/docs/spikes/2026-09-07-gather-box-verdict/"]
+++

# WanChai N45 spotlight22 light runs differ on 4 lightmaps — they do not

`FLightMapIndex` is `i32 DataOffset, f32 Pan[3], ci UClamp, ci VClamp, f32 UScale, f32 VScale,
i32 iLightActors`; `lmdiag.py` walked `Model.Lights` from `VClamp`. Read correctly, native and UED22
agree on all 210 lightmap runs at N=45, and the gather's box tests match a live editor capture call
for call — so the scoped multi-day `FSpanBuffer`/`ClipBspSurf` rasterizer port this item called for
is not needed. The level's whole divergence is one over-included per-leaf permeating light:
`wanchai-n45-leaf-20-permeating-light-over-included`.
