+++
priority = "p2"
kind = "unknown"
summary = "Native SURFACE SET diverges on heavy-overlapping SUBTRACT — Surfs +6.7 % on Paris-Catacombs"
+++

# Native SURFACE SET diverges on heavy-overlapping SUBTRACT — Surfs +6.7 % on Paris-Catacombs

§86 cross-check (2026-07-19): on `10_Paris_Catacombs.dx` native emits 6927
Surfs vs editor 6491 (+436), where the castle was exact and UNATCO −0.2 %. Overlapping SUBTRACT
brushes make native fragment/merge world surfaces differently from UnrealEd's `bspBrushCSG`
(coplanar-merge / T-junction handling). New, heavy-subtract-specific; castle+UNATCO never surfaced
it. Needs a heavy-subtract level kept in the parity loop. (Related, unchanged: over-zoning 33-vs-17
and uniform BSP over-split +10…+17 %.)
