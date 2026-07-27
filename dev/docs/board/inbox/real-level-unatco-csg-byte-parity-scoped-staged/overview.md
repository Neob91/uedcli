+++
priority = "p2"
kind = "unknown"
summary = "Real-level (UNATCO) CSG byte-parity — SCOPED + staged plan (spike §92, 2026-07-19)"
+++

# Real-level (UNATCO) CSG byte-parity — SCOPED + staged plan (spike §92, 2026-07-19)

Corrects the §91 §9.4 framing and splits the real-level residual into TWO clean pieces, with the
incremental-`bspBrushCSG` port already DONE + byte-exact for the castle. **(1) The "native −6 % nodes /
−1067 solid" vs the §91 golden is a PARITY-BASIS ARTIFACT, not a native defect** ✅: the §91 golden is
`MAP REBUILD; **BSP REBUILD OPTIMAL** OPTGEOM ZONES`, and the `BSP REBUILD OPTIMAL` step re-partitions
the whole BSP with OPTIMAL (stride 1) — which native does NOT model (native = `csgRebuild` = GOOD/12).
Against the single-`MAP REBUILD` (GOOD) golden native is only **+111 nodes (+1.8 %, +163 solid / −90
semi)** and the sign FLIPS. Proven from cached builds: both goldens carry identical 3616 surfs / 599
vectors while nodes differ 6314 (GOOD) vs 6859 (OPTIMAL). **(2) The +82 surfs / +146 vectors residual
is REAL and basis-independent** ✅ — the one genuine CSG-partition gap. By class: **+38 solid + +46
semisolid**, BIDIRECTIONAL (174 only-native / 92 only-editor — NOT a pure under-merge, so forcing a
merge regresses, §82 §10.6). Born in the incremental `FilterWorldThroughBrush`/`bspMergeCoplanars`
phase (surf-count-invariant to OPTIMAL vs GOOD; not `SplitPolyList`/`bspOptGeom`). **Follow-ups:**
(a) **Stage 0 = fix the basis** (highest-leverage, no `bspcsg.rs`): grade the node tree against a GOOD
golden, resolve the Leaves-vs-node basis tension (a `MAP REBUILD; BSP REBUILD GOOD ZONES` golden build
wedged twice this session — the editor crash-proneness; decode `Editor.dll 0x65220`'s GOOD Balance if
needed). (b) **Stage 1 = editor-tree oracle on UNATCO subsets** (the §82 §10.7 gdb-`bspAddNode` method,
bisected over ~730 solid+detail brushes) to pin the FIRST surf-set divergence, then decode+port each class
(castle-byte-gated). **Honest effort: WEEKS of staged oracle-driven work, NOT a few merge-rule fixes**
— the castle already implements every known merge rule byte-exactly, so the UNATCO residual is by
construction the next-order divergences it doesn't exercise. Full plan + attribution:
`sections/92-bspbrushcsg-reallevel-port-plan.md`; harness `surf_class_diff.py`,
`reallevel_brush_profile.py`.
