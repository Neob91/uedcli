+++
priority = "p?"
kind = "unknown"
summary = "Native `bspOptGeom` pass-1 over-weld — LIVE dup-guard table"
+++

# Native `bspOptGeom` pass-1 over-weld — LIVE dup-guard table

(`bspoptgeom.rs`, 2026-07-18,
`42-bspoptgeom-decode.md §9`). The T-junction dup-guard read a STATIC pre-pass1 vertex-occurrence
table; the editor's inserter (`0x31920`) updates it live on every weld. Fixed by threading `&mut
table` through `add_point_link` and appending `(node, point)` after each `insert_ring_vertex`. RAW
(`ground_truth_bytediff.py`, `NativeCastle.dx` vs `Test_Castle.dx`): pass-1 welds **977→975** (==
editor); **Verts count 16183→16172** (editor 16163); **Verts section 53924→53887 B** (editor 53866);
**NumSharedSides byte-identical 2739** (kept); Nodes section 54035→54034 B (== editor). Guards
unregressed (nodes 1156/1156, soup 853/853, surfs 485, vectors 26, Points 2035, Bounds 484,
LeafHulls 308/3866/1710, LightMap 484); `optgeom_validate` golden fixpoint holds; offline 1705
passed; `cargo test bspoptgeom` 4/4. Evidence: `editor-tree-oracle/weld_livetable_diff.py`.
**Remnant:** Verts still +9 (Pass-D orphan slots) + orphan `iVertex` stale-index bytes — out of lane
(`zones.rs`/`passes.rs`), tracked in `inbox.md`.
