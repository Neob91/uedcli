+++
priority = "p2"
kind = "unknown"
summary = "Native OMITS the per-LEAF permeating light lists — the dominant raw-byte gap in `Model.Lights` (e4): native 3928 vs editor 11392 entries"
+++

# Native OMITS the per-LEAF permeating light lists — the dominant raw-byte gap in `Model.Lights` (e4): native 3928 vs editor 11392 entries

p2 **Native OMITS the per-LEAF permeating light lists — the dominant raw-byte gap in
`Model.Lights` (e4): native 3928 vs editor 11392 entries.** Pinned 2026-07-18 (spike §20 §21;
harness `lights_run_diff.py`). `Model.Lights` has TWO regions: region 1 `[0,7455)` = per-leaf
permeating runs indexed by `FLeaf.iPermeating` (366/384 leaves; monotonic in leaf order;
`iVolumetric` all −1 here), region 2 `[7455,11392)` = the per-surface shadow runs native already
bakes. Native emits ONLY region 2, and `zones.rs` stubs every leaf `iPermeating=0` (points at a
surface run — wrong garbage for dynamic-actor lighting). Reproducing region 1 needs a port of
UnrealEd's per-leaf volumetric light-permeation gather (convex leaf volume × radius × BSP shadow),
INCLUDING the editor's exact within-run light ORDER (gather-discovery order, non-ascending, e.g.
leaf0=`[2,1,3,6,7,11,12]`). Union-of-bounding-surfaces was REFUTED (Jaccard 0.42). Belongs in
`light.rs` (a lighting bake), runs after zones, sets `leaves[i].i_permeating` + prepends region-1
runs to `model.lights`. NOTE: even done, the section stays raw-byte NON-identical until export
renumbering (wrapper) + BSP surf/leaf ORDER (bspBrushCSG byte-identity) parity land — so this
closes CONTENT/COUNT, not positional bytes. Lighting is never hashed/never blocks load, so p2.
