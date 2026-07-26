# Recipe: chamfered box  [ENGINE]

A box with one edge cut off at 45° (or any angle) — the workhorse "not a plain cube" shape. It's how
you make awning hoods, angled bays, beveled ledges, troughs, and the mitered ends of beams. The whole
trick is **build a cube, then `brush clip` the edge away**.

### What you're building

A box whose top-front edge is sliced off by a single plane, leaving a sloped face (a trapezoidal
cross-section). One brush, one clip.

### The CSG (the mechanism)

`brush clip` cuts the brush by an infinite plane and keeps one half. A plane is a **point on it** plus a
**normal** (which side is "above"). To bevel an edge at 45°, put the plane through the two points where
you want the cut to start, with a normal that points diagonally out of the corner you're removing.

### uedcli pipeline (what you run)

```
# a 192(X) x 128(Y) x 96(Z) cube, centred on the origin -> X:-96..96, Y:-64..64, Z:-48..48
brush build cube --width 192 --breadth 128 --height 96 | actor add -      # prints e.g. Cube_ab12cd

# slice the top-front (+X,+Z) edge at 45°: plane through (96,0,0) with normal (1,0,1); keep the inside
brush clip Cube_ab12cd --plane 96,0,0 1,0,1 --keep below
```

That single clip removes a 48×48 right-triangle prism from the top-front edge, leaving a clean 45°
slant face — a 7-face chamfered box.

### Notes

- **Computing the plane is arithmetic, not guesswork.** `brush build cube` is origin-centred on every
  axis (including Z), so you always know the corner coordinates; the clip plane follows from them. A
  non-normalized normal (`1,0,1`) is fine — only its direction matters.
- **`--keep below` vs `--keep above`** selects which half survives (below = the normal's negative side).
  If the wrong half vanishes, flip it.
- **Verify the cut** with `brush poly list <name>` — a 45° chamfer on a W×H edge adds one `slant` face
  whose area is `edge · √2 · depth`. (`brush clip` prints nothing on success, so inspect to confirm.)
- Miter a **beam end** the same way: build the long box, clip the end with an angled plane.
