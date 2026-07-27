+++
priority = "p2"
kind = "debug"
summary = "Native BSP is uniformly OVER-SPLIT at UNATCO scale (~+9…+21 % nodes/verts/points/ leaves)"
+++

# Native BSP is uniformly OVER-SPLIT at UNATCO scale (~+9…+21 % nodes/verts/points/ leaves)

Same cross-check (§84): Nodes +21.4 %, Vectors +16.6 %, LeafHulls +15.1 %, Leaves
+13.6 %, Bounds +12.3 %, Verts +10.9 %, Points +9.1 % vs editor 03 — while **Surfs is
essentially exact (3581 vs 3589, −0.2 %)**. So the world-surface SET generalizes cleanly; the
BSP tree that carves it is less-optimal (more split) than the editor's. Negligible on the
95-brush castle, compounds at real scale — a CSG/BSP-balancing gap castle-tuned byte-parity work
can't see. (Found 2026-07-18.)
