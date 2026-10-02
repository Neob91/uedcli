+++
priority = "p?"
kind = "unknown"
summary = "Native cross-check on heavy-SUBTRACT retail level — Paris-Catacombs"
+++

# Native cross-check on heavy-SUBTRACT retail level — Paris-Catacombs

(2026-07-19, §86
`sections/86-catacombs-parity.md`; harness `build_native_catacombs.py`). Measurement + diagnosis,
no production code touched. Ingested `10_Paris_Catacombs.dx` (1283 Brush + 18 DeusExMover, pinned
by Brush-export count; 2710-actor trunk, 9984 tex-refs 0-miss) and built `NativeCatacombs.dx`
UNLIT via `bspcsg`: **61 s / 176 MB / no crash / no CSG degenerate** on the densest overlapping-
subtract geometry — building at all is the headline. RAW ground-truth diff: whole-body 16.27 %
positional (editor lighting = 42.7 % of body, unlit). **NEW finding the castle+UNATCO never
surfaced: the SURFACE SET diverges — Surfs +436 (+6.7 %)** vs UNATCO's −0.2 %/castle's exact;
overlapping SUBTRACT makes native fragment/merge world surfaces differently from `bspBrushCSG`.
Reproduces the two §84 gaps: over-zoning **33 vs 17 (+94 %)** and uniform BSP over-split **+10…
+17 %** (NOT worse than UNATCO despite subtract density). **Deferred → inbox:** chase the surface-
set fragmentation (coplanar-merge / T-junction on overlapping subtracts) — needs a heavy-subtract
level kept in the parity loop.
