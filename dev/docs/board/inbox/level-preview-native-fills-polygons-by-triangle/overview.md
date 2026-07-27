+++
priority = "p2"
kind = "debug"
summary = "`level preview --native` fills polygons by triangle FAN, which bleeds outside a concave face"
+++

# `level preview --native` fills polygons by triangle FAN, which bleeds outside a concave face

`render.rs:196-206` triangulates each poly as `(v0, vk, vk+1)`; that is only valid
for a convex polygon, and for a concave one it paints area outside the boundary.
`architecture.md` records **0.1–0.6 % of faces in real exported maps are concave** (spike
`concave-faces/`, live 2026-07-23), which is why `preview.py` already carries
`_poly_is_convex_2d` rather than assuming convexity.
**Scope caveat from the reviewer who found it:** `render.rs` rasterizes post-CSG **BSP node**
polys, which the build produces convex, so the authored-face measurement reaches it only on the
**mover** path (movers are not carved into the world model). Narrower than it first looks, but
real. Surfaced while speccing `actor preview --faces`, whose scanline fill handles concave faces
correctly — so the two renderers deliberately disagree here until this is fixed. *(2026-07-26.)*
