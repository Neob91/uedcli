+++
priority = "p2"
kind = "debug"
summary = "`level photo --native` renders NO revolve brush at all — absent, not mis-drawn"
+++

# `level photo --native` renders NO revolve brush at all — absent, not mis-drawn

Measured 2026-07-26 (`dev/docs/spikes/2026-07-26-poly-rotate-curved-track/` finding 6). A
`brush build revolve` never appears in a `--native` render. Ruled out: framing (re-measured on a
clean level holding only a subtracted room and one 128-uu-tall arc); off-grid vertices
(`brush build cylinder --sides 8` is off-grid and renders fine); non-convexity
(`revolve --segments 1` is a convex 6-plane hexahedron and is ALSO absent). So this is **not** the
documented "native assumes convex solids" caveat `docs/usage.md` attaches to `staircase`/`extrude`
— that predicts a *mis-drawn* brush, and this is total absence for a convex one. `--game` renders
the same brush correctly, so the geometry is sound. **Cause not identified**; winding/normal
orientation on the swept faces is the leading suspect (an inside-out add contributes nothing to
CSG) but was not tested. Impact: the fast offline preview is unusable for any revolved geometry,
which is most curved detail, forcing the ~1-min `--game` path.
