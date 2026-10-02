# Recipe: moulded cornice / skirting  [ENGINE]

A moulding is a strip of trim whose profile is stepped or chamfered — a cornice where wall meets
ceiling, a skirting at the floor, a string course along a façade. `brush build extrude` draws the
cross-section once and sweeps it the length of the wall.

> This supersedes the copy-rotate approach for a straight run. [ring-cornice.md](ring-cornice.md)
> fakes a curved cornice out of many straight blocks copy-rotated around an axis, because there was
> no way to sweep a shape. That is still the right recipe when the cornice must follow a circular
> wall and you want separate blocks — but for a straight run, one extrude replaces a row of clipped
> boxes, and for a curved run [`brush build revolve`](curved-corridor.md) sweeps the same profile
> around the bend as one brush.

### What you're building

One brush, 512 uu long, whose cross-section is a 24×24 moulding with a square step and a 45° chamfer
— 7 profile points. It emits 11 faces: 7 side quads plus 2 tiled cap pieces at each end (the profile
is concave, so each cap is split into convex faces automatically).

### uedcli pipeline (what you run)

```
brush build extrude --axis x --depth 512 --at 0,0,0 --solidity semisolid \
  --point 0,0 --point 24,0 --point 24,8 --point 16,8 --point 16,16 --point 8,24 --point 0,24 \
  --base-name Cornice --folder castle.hall.trim | actor add -   # prints e.g. Cornice_ab12cd
```

Reading the profile: from the wall face `(0,0)` out to the full 24-uu projection, up 8 to the first
step, back in to 16, up to 16, then a 45° chamfer to `(8,24)` and back to the wall at `(0,24)`.
`--axis x` puts `U`→Y and `V`→Z, so the moulding stands in the YZ plane and runs 512 uu along X.

### Notes

- Make trim semisolid. A long thin solid brush cuts the BSP along its whole length for no gameplay
  benefit. `--solidity semisolid` keeps collision and lets it receive cuts without splitting the
  world — see [../../geometry-and-bsp.md](../../geometry-and-bsp.md).
- Concave profiles stay one brush. The engine's polygon must be convex and holds at most 16
  vertices, so uedcli tiles each cap into convex faces while the brush as a whole stays concave — the
  same arrangement `brush build staircase` uses. The tiling only adds diagonals of your profile, so
  the solid stays watertight.
- Preview: `level photo --native`, the fast offline draft, assumes convex solids and draws the
  moulding's notch filled in. Use the default `level photo --game` (or build it) to see the real
  shape — the geometry is correct either way.
- Mitre the corners by hand. A sweep has square ends; where two runs meet at a corner, either overlap
  them and accept the seam, or cut each end with [`brush clip`](chamfered-box.md) at 45°.
- Face naming: each side quad is `Side<k>` for profile edge `k` in ring order, so
  `brush poly find --item Side0` grabs the moulding's face against the wall — handy for aligning the
  texture along the run only where it shows.
