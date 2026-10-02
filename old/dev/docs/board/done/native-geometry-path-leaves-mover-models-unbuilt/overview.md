+++
priority = "p2"
kind = "implement"
summary = "DONE — the mover models WERE built; what was missing was LIGHT APPLY's moving-brush pass (LightMap records + the iLink/iBrushPoly it writes). Fixed 2026-09-06."
spikes = ["dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers/"]
+++

# The editor-free build path leaves mover models unbuilt

Reopened 2026-09-05 off NYC_Bar N=59, where each mover's private `Model` differed from UED22's in
`Bounds` and in its `Polys`' `iLink`/`iBrushPoly`. Closed 2026-09-06 — and the reopening's reading
was wrong twice over:

- The mover models ARE built by native (`csgPrepMovingBrush` → `build_brush_model`): nodes, surfs,
  verts, points, vectors, bounds and leaf hulls were all byte-identical at N=59. The reported
  `Bounds` gap was a `model_dump.py` column mismatch — the array that differed was **`LightMap`**
  (6 records vs 0).
- Nothing about it depends on "real world CSG existing" in the geometry sense. It depends on
  `LIGHT APPLY`, which returns immediately when the world `Model` has no nodes — so the pass only
  shows up once a level has its first world brush.

The real gap was the moving-brush half of `shadowIlluminateBsp`: per-poly `FLightMapIndex`
allocation (the poly's `iBrushPoly` is the slot), the moving-brush tracker's transient world surfs
(the poly's `iLink`), and `PrecomputeSphereFilter` over the world nodes. Ported as
`unbuilt.light_apply_movers`; see `nyc-bar-n-59-brush-region-zone-and-ued22` and
`dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers/spike.md`.
