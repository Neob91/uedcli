+++
priority = "p1"
kind = "debug"
summary = "Native surface SET HALVES on a DENSE level — `06_HongKong_WanChai_Market`: Surfs 2664 native vs 5224 editor (−49 %), and the whole BSP UNDER-builds ~−50 %"
+++

# Native surface SET HALVES on a DENSE level — `06_HongKong_WanChai_Market`: Surfs 2664 native vs 5224 editor (−49 %), and the whole BSP UNDER-builds ~−50 %

Second real-level
cross-check (§85): build SUCCEEDS unlit (26 s, 110 MB, no crash, no geometry warning, no brush
dropped) on 1330 brush-bearing actors / 8229 source polys. But the UNATCO pattern **inverts**:
where UNATCO's surf set matched (−0.2 %) and its BSP *over-split* (+9…+21 %), HK's surf set
**halves** and the BSP *under-builds* — Nodes −54 %, Verts −55 %, Points −51 %, Bounds −51 %,
Leaves −63 %, LeafHulls −43 %, Vectors −22 %. Native's HK body (863 KB) is SMALLER than native's
UNATCO body (1.05 MB) despite 1.8× the brushes — native is collapsing/absorbing the dense,
overlapping additive coplanar surfaces the editor keeps distinct. So the BSP-count divergence has
**level-dependent SIGN**, and the "surface set generalizes cleanly" claim from §84 is FALSE on a
dense level. Root cause (not chased): incremental-`bspBrushCSG` over-merge on tightly-packed
overlap; density (not add/subtract ratio — both levels are additive-dominant) is the trigger.
Evidence: `spikes/2026-07-15-native-materialize/sections/85-hkmarket-parity.md`; reproduce via
`harness/build_native_hkmarket.py`. (Found 2026-07-19.)
