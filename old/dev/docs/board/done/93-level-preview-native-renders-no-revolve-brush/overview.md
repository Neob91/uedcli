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

## Resolved (2026-09-04)

Winding suspect was wrong: every revolve face's Newell normal matches its stored `Normal` exactly
(dot +1.00 on the `builder_revolve.t3d` fixture), so the brush is not inside-out. Real cause: the old
`build_scene` carved with the coarse `build_geometry` (convex point-in-solid survival test), which
dropped swept-brush surfaces wholesale — the same ~69% loss noted in
`native-preview-drops-large-geometry-on-full`. Commit `8fd9b2c` (2026-08-24) switched `build_scene` to
the faithful `build_geometry_bspcsg` core, now shared with `actor diagram --faces textured`
(`solve_world_surfaces`); `render.rs` does no backface cull.

Verified 2026-09-04: `level photo --native` renders a `brush build revolve` arc inside a subtracted
room, and `actor diagram` renders revolves in wire and textured at 90/180/360°. Concave-cap fill-in
(convex tessellation) is a separate, still-open artefact, not this absence.
