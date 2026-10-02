# Recipe: L-shaped ledge  [ENGINE]

A shelf, a stair-side stringer, a curb, a countertop with an upstand — anything whose cross-section
is an L rather than a rectangle. Uses `brush build extrude`: draw the silhouette once and sweep it
along the run.

### What you're building

One brush whose cross-section is a 96×96 L with a 32-uu-thick tail, swept 16 uu along Y. Before the
profile generators this needed either two boxes (a seam through the corner, two actors to keep
aligned) or a box plus a subtractive box.

### uedcli pipeline (what you run)

```
brush build extrude --axis y --depth 16 --at 0,0,0 \
  --point 0,0 --point 96,0 --point 96,32 --point 32,32 --point 32,96 --point 0,96 \
  --folder castle.hall | actor add -            # prints e.g. Extrude_ab12cd
```

The result occupies X 0..96, Y 0..16, Z 0..96 (`actor bbox` confirms) and has 10 faces: 6 side
quads, one per profile edge, plus 2 cap pieces at each end — the concave cap is tiled into two
convex faces, because the engine's polygon must be convex. `level doctor` reports nothing.

### Notes

- `--axis` names the direction the sweep grows, and the profile's `(U,V)` fall on the other two
  world axes in right-handed cyclic order. Here `--axis y` means `U`→Z, `V`→X, so the L stands up in
  the XZ plane and the 16 uu is the ledge's thickness front-to-back. See
  [../../brush-shapes.md](../../brush-shapes.md) for the table.
- `--at` is where profile `(0,0)` lands, not the brush centre — the vertices are the numbers you
  typed, so the ledge lands exactly where you drew it. A consequence: `--rotate` turns the actor
  about that same local origin, so a profile drawn away from `(0,0)` swings through an arc instead
  of spinning in place.
- Ring order is argument order and the ring closes itself — do not repeat the first point last.
  Either winding works.
- Turn the corner into a chamfer: replace `--point 32,32` with the two points of a 45° cut
  (`--point 40,32 --point 32,40`). Doing the same thing with boxes would need a
  [`brush clip`](chamfered-box.md).
- Mind the CSG order if the ledge is additive inside a room you subtract later — `level doctor`
  flags an add that a later subtract carves away.
