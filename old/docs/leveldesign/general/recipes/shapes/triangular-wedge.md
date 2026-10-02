# Recipe: triangular wedge / ramp  [ENGINE]

A right-triangle prism — a ramp, a gusset, angled fill under stairs, a sloped buttress. Same single
clip as the [chamfered box](chamfered-box.md), but the plane cuts the whole brush corner-to-corner
instead of trimming one edge.

### What you're building

A box sliced by a single diagonal plane running the full length, leaving a triangular cross-section
that ramps from 0 up to full height. One brush.

### uedcli pipeline (what you run)

```
# a 192(X) x 64(Y) x 96(Z) box, origin-centred -> X:-96..96, Y:-32..32, Z:-48..48
# diagonal plane through the origin, cutting the XZ cross-section corner-to-corner (parallel to Y):
#   normal (1,0,-2) passes through opposite corners (-96,-48) and (96,48); keep the lower triangle
brush build cube --width 192 --breadth 64 --height 96 \
  | brush clip - --plane 0,0,0 1,0,-2 --keep above \
  | actor add -                                                 # prints e.g. Cube_ab12cd
```

The result is a triangular prism whose top face ramps from Z=-48 at X=-96 to Z=+48 at X=+96 — a 96-tall
rise over the 192 run. `brush poly list` shows 5 faces (2 triangular end-caps + 3 rectangles).

### Notes

- The normal encodes the slope: `(1,0,-2)` means "for every +1 in X, the plane drops 2 in Z" — i.e.
  the cut goes through corners `(−96,−48)` and `(96,48)` of a 192×96 box. Change the ratio to change the
  ramp angle; the point can stay at the origin.
- `--keep above`/`--keep below` picks which triangle you keep; wrong one, flip it.
- For a ramp you'll actually walk up, keep the rise ≤ the pawn's step where it meets the floor, or lead
  into it with a step — see [../../human-scale.md](../../human-scale.md).
- A wedge is just a box + one clip, so it composes: clip twice for a tapered (trapezoidal) block — see
  [ring-cornice.md](ring-cornice.md).
