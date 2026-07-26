# Recipe: curved corridor  [ENGINE]

A passage that **bends** instead of turning a corner — the shape UnrealEd's 2D shape editor makes by
moving the pivot away from the cross-section and hitting Revolve. In uedcli it is one verb: draw the
corridor's cross-section, then sweep it around the bend centre.

### What you're building

A 90° bend of a passage 128 uu wide and 128 uu tall, whose inner wall sits 64 uu from the bend
centre and outer wall 192 uu — subtracted out of solid rock, in 4 flat facets.

### uedcli pipeline (what you run)

```
brush build revolve --axis x --angle 16384 --csg subtract --solidity semisolid \
  --point 64,0 --point 192,0 --point 192,128 --point 64,128 \
  --at 0,0,0 --folder castle.corridor | actor add -      # prints e.g. Revolve_ab12cd
```

`--angle 16384` is 90° in unreal rotation units. With `--axis x` the profile's `(U,V)` are `(Y,Z)`,
so the four points are the passage's cross-section: `U` is distance from the bend centre and `V` is
height. The default segment count is one facet per 22.5°, i.e. **4** for a 90° bend — the density
UnrealEd itself uses. The result is 18 faces (4 profile edges × 4 segments, plus a cap at each end)
occupying a 192×192×128 quarter-annulus from `--at`.

### Notes

- **`--at` is the BEND CENTRE.** The revolve axis is the profile's own `U = 0` line, which passes
  through profile coordinate `(0,0)`, so there is no separate pivot flag: how far the corridor sits
  from the centre is written in the `U` values themselves. Widen the bend by adding to every `U`.
- **Every point must have `U > 0`.** A profile straddling the axis would sweep into a
  self-intersecting solid, and one touching it would collapse the faces along the axis; both exit 2.
  To bend the other way, mirror the `U` values.
- **`--solidity semisolid` is not decoration here.** Every vertex away from the sweep's start lands
  on `radius · cos/sin θ` — irrational, off the integer grid — and uedcli never snaps coordinates
  for you. An off-grid *solid* brush throws its BSP splitting planes off-grid too, which is the
  primary cause of slivers and holes in the built map; a semisolid receives cuts but emits no
  world-splitting planes. uedcli prints a stderr advisory if you build one solid anyway. Where the
  corridor IS the structure (a bend carved through a solid hill), keep it solid and keep the
  segment count low. See [../../geometry-and-bsp.md](../../geometry-and-bsp.md).
- **Segments cost faces fast:** `profile points × segments`, plus caps. A 16-segment sweep of an
  8-point profile is 130 faces in one brush; over 64 faces uedcli says so on stderr.
- **Selecting one wall.** Every face swept by profile edge `k` is `Side<k>` in *every* segment, so
  `brush poly find --item Side0 | brush poly set - --texture …` retextures the whole inner wall
  strip at once. Without that, inner and outer walls would both read as `slant` to `--facing` and
  there would be no handle at all.
- **`--angle 65536` closes the ring** into a full turn (a torus): both caps are omitted and the last
  facet welds onto the first. Needs at least 3 segments.
