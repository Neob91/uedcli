+++
priority = "p1"
kind = "implement"
summary = "Native materialize remaining slices (N-1..N-5)"
+++

# Native materialize remaining slices (N-1..N-5)

p1. **N-1 CSG core LANDED
(2026-07-15):** `fpoly` (Finalize/Reverse/Transform/SplitWithPlane) + `csg` (bspBrushCSG two-pass
leaf-filter, FilterEdPoly/FilterLeaf cospatial routing, all 4 CsgOper funcs) + `build`
(bspAddNode/FindBestSplit/SplitPolyList/bspBuild, pooling, surf-sharing) are ported and wired into
`lib.rs build_geometry` (flat-buffer brush API). Validated by an **editor-golden differential** —
the harness (`native/csg_golden.py` + frozen `tests/fixtures/csg_golden/*.json`, captured on a
live ephemeral editor) plus `tests/test_csg_native_differential.py` (offline). **Tier-S surf-set
parity reached on cases a (single subtract), c (add-in-subtract), d (abutting-subtracts — the known
prior-port 11-vs-10 ANNIHILATION bug, PROVEN fixed via the exact-0.0 cospatial facing route), e
(semisolid detail).** cargo: 13 tests; pytest: 6 pass + 2 xfail. **RESIDUALS (see below).** Still
to build: N-2 zones/cleanup, N-3 `pkgref`+typed props+game-load smoke, N-4 `linecheck`+`light`,
N-5 `paths`. FP-model + Nuitka bundling already de-risked (spikes 40/41).
