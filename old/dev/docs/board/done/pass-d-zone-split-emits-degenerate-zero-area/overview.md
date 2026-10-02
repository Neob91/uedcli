+++
priority = "p1"
kind = "debug"
summary = "Fixed — c228e60's real bspAddNode ring fill plus the kill half in zones.rs: an nv=0 Frag ships no node (post-Pass-D bspCleanup) and a killed OriginalRing retargets the original onto the next surviving fragment. Zero <3-distinct/zero-area rings corpus-wide; club +2→0, chateau +4→0, helibase +9→+2, OceanLab +465→+390; 04_NYC_Underground exact without cancellation."
+++

# Pass-D zone-split emits degenerate zero-area fragment nodes the editor never stores

Fixed in two layers: `fill_ring_verts` (c228e60, the disasm-pinned `bspAddNode` fill — NEAR 0.015
pooling, consecutive-index collapse, wrap trim, <3 → nv=0) and the kill half on the consume loop
(`zones.rs`): no node for an nv=0 `Frag` (the editor's ringless fragment is culled by the
post-Pass-D `bspCleanup`, §70 §1), and an owner whose `OriginalRing` was killed is retargeted onto
its next surviving fragment (the editor killed the original up front; without this club surf 89
shipped two identical quad nodes). Pinned by `zones.rs::club_brush20_strip_landings_are_killed`
(the exact `Brush20` landing set). If NO fragment survives, the original keeps its base ring — a
node delete is not representable; not observed on the corpus (code comment records it).

Residual nv0-node count imbalances (747/wanchai/area51 +1 native, trainingfinal/nsfhq/vandenberg/
oceanlab +1 golden) are NOT Pass-D-born — see
`inbox/nv0-node-count-imbalance-native-vs-golden-is`.
