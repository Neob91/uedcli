+++
priority = "p2"
kind = "unknown"
summary = "`bspOptGeom` redundant-node removal (`Editor.dll 0x36870`) — decode to instruction level"
+++

# `bspOptGeom` redundant-node removal (`Editor.dll 0x36870`) — decode to instruction level

p2. Blocks the FINAL Tier-S surf-set parity for corpus case **b** (off-grid wedge) and
contributes to **f** (portal). Context: the native CSG/BSP core (N-1) + N-2 cleanup passes
(`bspMergeCoplanars` surface reassembly, `bspRefresh`, `bspBuildBounds`) now reproduce case b's
node COUNT (19) and surf COUNT (11) EXACTLY, but 5 surfs' per-surf VERTEX SETS still differ. Root
cause: `find_best_split` uses a **split-minimizing deviation** (see `uedcli-native/src/build.rs`)
instead of the byte-verified MAP REBUILD `Balance=50` heuristic, because `Balance=50` over-splits
(case c goes 12→24 nodes) and the editor only recovers via `bspOptGeom`'s redundant-node removal,
which §7.2/§10 of `spikes/2026-07-15-native-materialize/sections/10-bsp-csg-build.md` describe
**structurally but NOT instruction-by-instruction**. Need: disassemble `0x36870` (the node-dedup
/ "which split nodes are redundant" predicate) so the port can run the true `Balance=50` tree +
trim and reproduce the editor's exact split distribution (e.g. b's far +X wall split at y=-87.5
by a wedge plane the split-minimizing heuristic never makes). Simple adjacency-based trims were
ruled out (they would wrongly drop b's far-wall split, which no surf is adjacent to). Differential
harness ready: `uedcli/native/csg_golden.py` + `tests/test_csg_native_differential.py` (b/f are
strict xfail).
