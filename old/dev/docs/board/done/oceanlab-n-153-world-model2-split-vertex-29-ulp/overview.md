+++
priority = "p2"
kind = "debug"
summary = "FIXED — the temp brush BSP was built without `RebuildSimplePolys=1`, so a coplanar face's texture axis entered the temp Vectors pool and absorbed a later face's normal. OceanLab N=93 -> 153."
spikes = ["dev/docs/spikes/2026-09-07-oceanlab-n153-temp-brush-rsp/"]
+++

# OceanLab N=153 — two world `Model2` points land 29 ULP off (`152.0002` vs `151.99976`)

`Brush431` (trunk actor 153) subtracts a 2D-loft brush whose 45° face cuts `Brush147`'s big
`x=-12`/`x=-36` faces. The two cut vertices came out `152.0001983642578` where UED22 has
`151.999755859375` — the exact `Location.Y - PrePivot.Y` the plane sits on. The world `Model2` body
and its `Polys` body were the only divergences.

Cause: `bspBrushCSG` builds the temp brush BSP with `RebuildSimplePolys=1`
(`Editor.dll 0x35b85 push 1`), which makes `SplitPolyList` give every COPLANAR face the splitter's
surf (`iLink = Surfs.Num()-1`) instead of its own. `build_brush_temp_bsp` passed `None` for that
mode, so each of `Brush431`'s 20 faces allocated a surf — and each surf allocates its texture axes
into the same `Vectors` pool the normals go into. A coplanar sibling's authored
`TextureU = (0, 0.707106, 0.707108)` therefore entered the pool before the 45° face's normal
`(0, 0.70710695, 0.70710695)`, and `bspAddVector(exact)` deduped the normal onto that asymmetric
axis at `THRESH_NORMALS_ARE_SAME`. Splitting a world edge against the asymmetric plane moves the cut
vertex; against any symmetric ±1/√2 it is exact.

Fixed by engaging the `rsp_links` mode in `build_brush_temp_bsp`. Regression:
`bspcsg.rs::temp_brush_coplanars_share_the_splitters_surf`.
