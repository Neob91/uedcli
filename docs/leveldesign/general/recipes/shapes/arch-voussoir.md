# Recipe: arch voussoir  [ENGINE]

A **voussoir** is one of the wedge-shaped stones of a masonry arch. Ring several of them around an
opening and you have an arch; the shape of one is a trapezoid — wider at the bottom (the extrados
side sits outward) — swept through the wall's thickness.

### What you're building

One trapezoidal prism, 48 uu wide at the base and 32 at the top over a 64-uu height, swept 64 uu
through the wall. Six faces: 4 side quads and 2 caps.

### uedcli pipeline (what you run)

```
brush build extrude --axis y --depth 64 --at 0,0,256 \
  --point 0,0 --point 48,0 --point 40,64 --point 8,64 \
  --base-name Voussoir | actor add -                  # prints e.g. Voussoir_ab12cd
```

To build the ring, place each stone with its own `--at` and turn it into position with `--rotate`
(unreal rotation units — `16384` = 90°), or duplicate the first one and rotate the copies. Because
`--at` is where profile `(0,0)` lands, the stones stay laid out exactly where you place them — the
authored coordinate system is not thrown away by re-centring.

### Notes

- **The taper lives in the profile**, which is why there is no `--taper` flag. Any wedge, splay or
  tapered block you can draw in cross-section is one `extrude`; what a profile *cannot* express is
  a taper **along** the sweep (a frustum), and that is deliberately out of scope.
- **A voussoir ring is the honest version of a curved arch.** If you want the *opening* curved
  rather than the stones, sweep the opening's cross-section with
  [`brush build revolve`](curved-corridor.md) and subtract it.
- **Rotation is stored on the actor, not baked into the vertices** (matching UnrealEd). `--rotate`
  warns on stderr when it carries a vertex off the integer grid; an off-grid *solid* brush is the
  main cause of BSP holes, so consider `--solidity semisolid` for a decorative ring — see
  [../../geometry-and-bsp.md](../../geometry-and-bsp.md).
- **Keep the ring's stones abutting, not overlapping.** Overlapping additives are legal but each
  overlap is extra BSP work; `level doctor` will not complain, the build will just be heavier.
