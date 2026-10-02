+++
priority = "p2"
kind = "implement"
summary = "A `brush shear` / diagonal-wall helper — and a grid-alignment caveat on `actor rotate`"
+++

# A `brush shear` / diagonal-wall helper — and a grid-alignment caveat on `actor rotate`

p2. Building a 45° wall the RIGHT way (grid-aligned, no rotation) was: `brush build cube` → then
`brush vertex move` the 4 corners at one end by a grid delta to shear the box onto the diagonal.
Correct + watertight + all-integer vertices, but I had to hand-compute the far-end corner coords and
the shear delta. A `brush shear --edge <face> --by dX,dY,dZ` (or a diagonal-wall builder taking two
grid endpoints + thickness) would make this one call. **Related bug/UX:** `actor rotate` cheerfully
applies an arbitrary rotation that puts vertices OFF the grid (a 45° yaw → ×0.707 fractional coords →
CSG cracks/leaks) with no warning — Andrzej flagged this live. `actor rotate` should warn when a
rotation yields off-grid vertices (or snap to grid / suggest the vertex-shear path), and the
grid-align-don't-rotate rule is a real UnrealEd best-practice to document in `unrealed/` (diagonal
geometry is built by vertex-editing to grid points, not by rotating).
