+++
priority = "p2"
kind = "implement"
summary = "lean classify trees"
+++

# lean classify trees

p2 native CSG build sub-minute scaling: the behavior-preserving pass (2026-07-17,
`architecture.md` "Native CSG build performance") cut the build ~2–3.7× (N=150 15.5→7.1s
byte-identical; AABB fast-path + parallel `FindBestSplit`), but the per-brush classify-BSP rebuild
is still O(M²)×N ≈ O(N³) — the dominant cost, so full 762-brush UNATCO is still single-digit
minutes, not the <1 min ideal. Three faster ideas were REJECTED for changing output / not being
provably byte-identical (see architecture.md): (a) **lean classify trees** (skip the transient
tree's per-node vertex pool) — ~15%, byte-identical on the WHOLE acceptance corpus (castle +
UNATCO-150/300) but only *empirically*; the `model.points`-dedup coupling means a surf `p_base`
could shift ≤0.002uu. Recoverable if we either accept empirical verification + add sheared-brush
differential fixtures, or decouple the classify-tree split base from the shared points pool.
(b) **brush-local classify tree** (drop world faces whose plane clears the brush AABB) — ~100×
(full-762 → seconds) but changed node/vert counts (coplanar double-routing + whole-face/`discarded`
emission depend on the full tree). (c) **point_in_solid AABB cull** — only ~2% and not exact for
sheared/acute brushes (axis pad vs face-normal tolerance). The real sub-minute path is an
ALGORITHMIC change: incremental CSG (update the classify tree instead of rebuilding), a PROVABLE
form of the local-tree restriction, or `rayon::join` on the `SplitPolyList` recursion (exact but
only ~2× more). ANDRZEJ: is empirical byte-identity (a) acceptable to reclaim the ~15%? Harness:
`spikes/2026-07-15-native-materialize/harness/csg_perf.py` (`time` + `hash` byte-identity gate).
