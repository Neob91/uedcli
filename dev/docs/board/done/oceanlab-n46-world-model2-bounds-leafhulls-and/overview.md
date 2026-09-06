+++
priority = "p2"
kind = "debug"
summary = "FIXED: Pass D must KILL the split original and let bspCleanup promote its coplanar successor; OceanLab N=46 byte-exact"
spikes = ["dev/docs/spikes/2026-09-06-passd-kill-split-original/"]
+++

# OceanLab N46 world Model2 bounds, leafhulls and permeating lights differ — FIXED

Root cause: `AssignAllZones`'s split branch kills the ORIGINAL chain node
(`passD-assignzones-7400.md` §1) and the post-Pass-D `bspCleanup` (§70 §1) promotes its coplanar
successor, which inherits the dead node's children — swapped when the two planes face opposite ways.
Native reused the original in place, so on OceanLab N=46 (`Brush1427`) two coplanar chains came out
headed by the split node instead of by the promoted successor, and the `Bounds` / `LeafHulls` /
`LightMap` / permeating-light walks diverged from there.

Fix: `zones.rs` emits `KillOwner` + a real node per surviving landing, and `assign_leaves_and_zones`
ends with `bsp_cleanup` + `compact_unreachable_nodes`; `bspcsg::reorder_nodes_to_tail` (which faked
the resulting array layout) is deleted. Verified byte-exact at N=46 with no new mask; full
re-verification of all five levels in the spike.
