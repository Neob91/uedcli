# Brush shapes  [ENGINE]

`brush build <shape>` reimplements the editor's native brush builders model-side (it does not call
the editor), with a curated subset of their parameters. Each prints one T3D brush actor (`spiral`
prints a central column plus one wedge-tread brush per step; `staircase` prints a single non-convex
brush actor); pipe it to `actor add -` with `--csg` and `--solidity`.

```
brush build cube --csg subtract --height 256 --width 512 --breadth 512 | actor add -
brush build cylinder --csg add --height 256 --sides 8 --radius 128 --solidity semisolid | actor add -
```

## The shapes and their parameters

### `cube` — `CubeBuilder`
A box.
- `--width` / `--breadth` / `--height` — the three dimensions (editor default 256³).
- Subtract a cube for rooms; add one for blocks/pillars.

> The editor's cube builder has a hollow-box + wall-thickness option; uedcli does not expose it.
> Build a room shell by subtracting a solid cube instead.

### `cylinder` — `CylinderBuilder`
A prism / round pillar. Requires `--height` and `--radius`.
- `--sides` — facet count. The engine caps a single poly at 16 sides; more sides means more faces
  and more BSP cuts, so keep it low. 8 reads round enough for most pillars.
- `--radius` — the circumscribed radius. `--align-to-side` offsets the cross-section by half a segment
  (`180/--sides` degrees) so a flat face, not a vertex, meets an axis — the same as UED's
  `AlignToSide` checkbox. For any other angle use `--rotate`. The cylinder is a solid prism only —
  no inner-radius/hollow tube option; build a tube by subtracting a smaller cylinder from a larger one.
- `--axis x|y|z` (default `z`) lays the prism's long axis along that world axis directly, so a
  horizontal pipe or beam needs no `--rotate` and emits no `Rotation` — same `--axis` meaning as
  `extrude`/`revolve`. For any other orientation use `--rotate`, which stacks on top.
- Round geometry is off-grid by nature — prefer semisolid for cylindrical detail so it doesn't seed
  BSP holes (see [geometry-and-bsp.md](geometry-and-bsp.md)).

### `cone` — `ConeBuilder`
A pyramid or frustum (truncated cone) — spires, tent roofs, tapered pillars. Requires `--height` and
`--radius`; `--sides` (default 8), `--align-to-side` and `--axis x|y|z` (default `z`, orients the
cone's long axis — a horizontal cone needs no `--rotate`) are optional.

### `sheet` — `SheetBuilder`
A single flat poly, the basis of most special surfaces:
- Zone portals (`--flag portal`, nonsolid) — see [zones-and-performance.md](zones-and-performance.md).
- Water surfaces and glass — a translucent sheet (see recipes).
- Banners / signs — a masked or 2-sided sheet.
- `brush build sheet` is 2-sided and nonsolid by default (matching `SheetBuilder`, whose polys are
  `PF_TwoSided|PF_NotSolid`), so no `--flag 2sided` is needed. Sheets never block collision — back
  one with a hull (see [actors.md](actors.md)).

### `staircase` — `LinearStairBuilder` (linear only)
A straight run of steps as one non-convex brush (named `Staircase`): a `Base`, a `back` wall, and per
step a `Step` tread + `Rise` riser, with the sides tiled into convex `Side` strips (`2 + 4·steps`
faces). Parameters: `--steps` (count), `--depth` (X per step), `--rise` (Z per step), `--breadth` (Y
width). Address an individual tread/riser/side by its `Item` (the whole run is one actor).
- Keep step rise ≤ 25 — the engine auto-climbs steps only up to the pawn's `MaxStepHeight` (25 uu in
  Deus Ex — see [human-scale.md](human-scale.md)); a taller step needs a jump. Recommended rise 16.
- Native caveat: UnrealEd (`level materialize`) and the real engine (`level preview --game`) build
  this non-convex brush correctly; the coarse CSG core behind `level preview --native` assumes convex
  brushes, so it mis-builds the concave notches. Judge staircases with `--game`, not `--native`.

> The editor's curved-stair builder (`CurvedStairBuilder` — inner radius, angle of curve,
> clockwise/counter-clockwise) has no uedcli verb. For a rising rotation use `spiral`; otherwise
> approximate a curved stair by placing linear runs at angles.

### `spiral` — `SpiralStairBuilder`
A spiral staircase: a central column (a cylinder filling the axis over the full height) plus one
wedge (pie-slice) tread per step, each tread rotated `--angle-per-step` and raised one `--rise` above
the last, so the treads fan around the column and climb as a single helix. Prints `N+1` brush actors
(`[column, wedge_0, …]`). Requires `--steps`, `--inner-radius` (column radius = inner tread radius),
`--step-width` (radial tread depth), and `--rise` (tread thickness / per-step climb); `--angle-per-step`
is optional — unreal rotation units like `--rotate`, default `8192` (45°). `--at` anchors the base of
the column axis. Typically added as an additive structure; each emitted brush is a clean convex solid,
so subtracting works too.

### `extrude` — sweep a profile you draw, in a straight line
Instead of choosing sizes for a fixed silhouette, you draw the cross-section. Repeat `--point U,V`
once per profile vertex, in ring order (at least 3; the ring closes implicitly), then `--depth`
sweeps it along `--axis`. Use it for an L-ledge, an arch voussoir, a moulded cornice, a chamfered
pillar — any cross-section the fixed builders cannot express. `--at` is the world point profile
coordinate `(0,0)` lands on (nothing is re-centred), so a ring of voussoirs drawn at known offsets
stays laid out as drawn.

`--axis` names the world axis the profile plane is normal to — the direction the sweep grows. The
profile's `(U,V)` then land on the other two world axes in right-handed cyclic order:

| `--axis`        | `U` | `V` | the sweep grows along |
|-----------------|-----|-----|---|
| `z` *(default)* | X   | Y   | +Z |
| `x`             | Y   | Z   | +X |
| `y`             | Z   | X   | +Y |

Concave profiles are fine and stay one brush. The engine's polygon must be convex and holds at most
16 vertices, so a concave profile (an L, a notched cornice) or one over 16 points has each of its two
caps tiled into several convex faces — adding only diagonals of your own outline, so the solid stays
watertight. Faces are `Cap` per end plus one `Side<k>` per profile edge, numbered in ring order, so
`brush poly find --item Side0` selects the face swept by the first profile edge.

- Native caveat: as with `staircase`, UnrealEd (`level materialize`) and the real engine
  (`level preview --game`) build a concave swept brush correctly, but the coarse CSG core behind
  `level preview --native` draws a concave notch filled in — a preview artefact, not a geometry bug.

### `revolve` — sweep that same profile around an axis
Same profile grammar and `--axis`; instead of a straight `--depth` it sweeps around the profile
plane's own `V` axis (the line `U = 0`, through profile coordinate `(0,0)`), in `--segments` flat
facets. `--at` is therefore the bend centre, and how far the shape sits from it is written in the
profile: a profile at `U ∈ [64, 192]` revolves at radii 64 to 192. `--angle` is in unreal rotation
units (`16384` = 90°, `65536` = a closed full turn, which omits both caps); default density is one
facet per 22.5°, matching UnrealEd. The profile must sit strictly on the positive-`U` side of the axis.

- A revolve is off the integer grid by construction — every vertex away from `θ=0` lands on
  `radius · cos/sin θ`, and uedcli never snaps for you. An off-grid solid throws its BSP partition
  planes off-grid too, the primary cause of slivers, T-junctions and holes. Prefer
  `--solidity semisolid` where the swept shape is detail rather than structure; uedcli warns on
  stderr when it emits an off-grid solid.

## Curved geometry

`brush build revolve` (above) is the dedicated curved-corridor verb. Curves in UE1 are many straight
segments (16 facets = 360°); `revolve` generates them for you. Vertex-edited curves are fragile —
they destroy surface alignment (re-align after) and need a rebuild before editing. Prefer generated
or straight-brush CSG and accept faceting; it is more robust than hand-curved geometry.

UE1 terrain is 100% brush-based. There is no heightmap `TerrainInfo` (that's UE2) — sculpt terrain
from tessellated brushes or intersect-before-add rock CSG.

## Beyond the builders — shape recipes

The builders make the base primitives. Non-box shapes (chamfered beams, wedges, octagon columns,
ring cornices, add/subtract-twinned trim) come either from composing them — `brush build` + `brush
clip` (bevel/taper/miter) and copy-rotate — or, when the cross-section is what you care about, from
drawing it directly with `extrude`/`revolve`. Build-verified recipes are in
[recipes/shapes/](recipes/shapes/).

## Related

- [geometry-and-bsp.md](geometry-and-bsp.md) — solidity, order, and why round/off-grid shapes want
  semisolid.
- [human-scale.md](human-scale.md) — the sizes to build these shapes to.
- [recipes/shapes/](recipes/shapes/) — the non-box constructions: composed (chamfer, wedge, octagon,
  ring, twin) and drawn-profile (L-ledge, arch voussoir, moulded cornice, curved corridor).
