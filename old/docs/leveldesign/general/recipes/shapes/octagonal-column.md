# Recipe: octagonal column  [ENGINE]

A faceted round pillar. UE1 has no smooth curves; you get a low-sided cylinder. An 8-sided prism
reads as round enough for columns, drums, pedestals, and pipes.

### What you're building

A free-standing 8-sided vertical prism, base on the floor. One brush, one verb.

### uedcli pipeline (what you run)

```
# 8-sided prism, 64 across, 256 tall, base seated on the floor (Z=0)
brush build cylinder --height 256 --radius 32 --sides 8 --at 0,0,128 | actor add -
```

`--sides 8` is the octagon; `--radius 32` gives ~64 across; `--at` centres the brush on every axis
including Z, so to put the base on the floor set `Z = height/2` (128 for a 256-tall column).

### Notes

- `--sides` trades roundness for cost. The engine caps a single poly at 16 sides, and every side is
  another face plus BSP cut. Use 8 for columns, 6 for chunky pillars, 12–16 only for a hero drum.
  See [../../brush-shapes.md](../../brush-shapes.md).
- Round geometry is off-grid: its vertices land at `radius·cos/sin` angles, not on the power-of-two
  grid. Prefer semisolid (`--solidity semisolid`) for cylindrical detail so it doesn't seed BSP
  holes ([../../geometry-and-bsp.md](../../geometry-and-bsp.md)).
- `--align-to-side` offsets the cross-section by half a segment, sitting a flat face on an axis
  instead of a vertex so the column meets an axis-aligned wall flush.
- No UE1 curve is truly round; each is facets you pay for. A cylinder is the cheapest.
  `brush build revolve` is the general one — sweep a cross-section you draw around an axis
  ([curved-corridor.md](curved-corridor.md)) — for a bend, a torus, or a turned profile rather than
  a plain prism. Beyond those, curves are faked: a ring of straight blocks copy-rotated around the
  axis ([ring-cornice.md](ring-cornice.md)), or 45° chamfers ([chamfered-box.md](chamfered-box.md))
  standing in for fillets.
