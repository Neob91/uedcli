# Brush shapes  [ENGINE]

`brush build <shape>` mirrors the editor's native brush *builders* — it reimplements the same shapes
model-side (it does not call the editor), with a curated subset of their parameters. Each prints one
T3D brush actor (the `spiral` prints a **central column plus one wedge-tread brush per step**; the
`staircase` prints a single non-convex brush actor); pipe it to `actor add -` with a `--csg` and
`--solidity`.

```
brush build cube --csg subtract --height 256 --width 512 --breadth 512 | actor add -
brush build cylinder --csg add --height 256 --sides 8 --radius 128 --solidity semisolid | actor add -
```

## The shapes and their parameters

### `cube` — `CubeBuilder`
The workhorse. A box.
- `--width` / `--breadth` / `--height` — the three dimensions (editor default 256³).
- Build rooms by **subtracting** a cube; build blocks/pillars by **adding** one.

> The editor's own cube builder has a hollow-box + wall-thickness option; uedctl's `brush build cube`
> does **not** expose it. Build a room shell by subtracting a solid cube instead.

### `cylinder` — `CylinderBuilder`
A prism / round pillar. Requires `--height` and `--radius`.
- `--sides` — facet count. **The engine caps a single poly at 16 sides** — more sides means more faces
  and more BSP cuts, so keep it low. 8 reads as round enough for most pillars.
- `--radius` — the circumscribed radius. `--angle-offset` rotates the cross-section (deg) to flatten a
  face onto an axis. (uedctl's cylinder is a **solid** prism only — there is no inner-radius/hollow
  tube option; build a tube by subtracting a smaller cylinder from a larger one.)
- Round geometry is off-grid by nature — prefer **semisolid** for cylindrical detail so it doesn't seed
  BSP holes (see [geometry-and-bsp.md](geometry-and-bsp.md)).

### `cone` — `ConeBuilder`
A pyramid or **frustum** (truncated cone) — spires, tent roofs, tapered pillars. Requires `--height` and
`--radius`; `--sides` (default 8) and `--angle-offset` are optional.

### `sheet` — `SheetBuilder`
A single flat poly. The basis of most special surfaces:
- **Zone portals** (`--flag portal`, nonsolid) — see [zones-and-performance.md](zones-and-performance.md).
- **Water** surfaces and **glass** — a translucent sheet (see recipes).
- **Banners / signs** — a masked or 2-sided sheet.
- `brush build sheet` is **2-sided and nonsolid by default** (matching the editor's `SheetBuilder`, whose
  polys are `PF_TwoSided|PF_NotSolid`), so no `--flag 2sided` is needed. **Sheets never block** collision
  — back one with a hull (see [actors.md](actors.md)).

### `staircase` — `LinearStairBuilder` (linear only)
A straight run of steps as **one non-convex brush** (named `Staircase`) — the UED `LinearStairBuilder`
stepped wedge: a `Base`, a `back` wall, and per step a `Step` tread + `Rise` riser, with the sides tiled
into convex `Side` strips (`2 + 4·steps` faces). Parameters: `--steps` (count), `--depth` (X per step),
`--rise` (Z per step), `--breadth` (Y width). Address an individual tread/riser/side by its `Item`
(the whole run is one actor).
- **Keep step rise ≤ 25** — the engine auto-climbs steps only up to the pawn's `MaxStepHeight` (25 uu in
  Deus Ex — see [human-scale.md](human-scale.md)); a taller step needs a jump. Recommended rise **16**.
- **Native caveat:** UnrealEd (the default `level materialize`) and the real engine (the default
  `level preview --game`) build this non-convex brush correctly; the experimental native CSG core
  assumes convex brushes, so `level preview --native` / native materialize mis-build its concave
  notches. Judge staircases with `--game`, not `--native`.

> The editor's separate curved-stair builder (`CurvedStairBuilder` — inner radius, angle of curve,
> clockwise/counter-clockwise) has **no uedctl verb**. For a rising rotation use `spiral` (a different
> builder); otherwise approximate a curved stair by placing linear runs at angles.

### `spiral` — `SpiralStairBuilder`
A real spiral staircase: a **central column** (a cylinder filling the axis over the full height) plus
one **wedge (pie-slice) tread per step**, each tread rotated `--degrees-per-step` and raised one `--rise`
above the last — so the treads fan around the column and climb monotonically (a single helix, not a
mirrored fan). Prints `N+1` brush actors (`[column, wedge_0, …]`). Requires `--steps`, `--inner-radius`
(column radius = inner tread radius), `--step-width` (radial tread depth), and `--rise` (tread
thickness / per-step climb); `--degrees-per-step` is optional (default 30°). `--at` anchors the base of
the column axis (bottom of the stair). Typically added as an **additive** structure (the treads read
as a solid stair); each emitted brush is a clean convex solid, so subtracting works too.

## Curved geometry

There is no dedicated curved-corridor verb. Curves in UE1 are built from many straight segments (e.g. a
revolve of a cross-section — 16 pieces = 360°), and vertex-edited curves are fragile: they destroy
surface alignment (re-align after) and need a rebuild *before* editing. Prefer clean straight-brush CSG
and accept faceting — it's far more robust than hand-curved geometry.

Also note: **UE1 terrain is 100% brush-based.** There is no heightmap `TerrainInfo` (that's UE2) —
sculpt terrain from tessellated brushes or intersect-before-add rock CSG.

## Beyond the builders — shape recipes

The builders make the base primitives; the **non-box** shapes real levels are full of (chamfered beams,
wedges, octagon columns, ring cornices, add/subtract-twinned trim) come from *composing* them —
mostly `brush build` + **`brush clip`** (bevel/taper/miter) and copy-rotate. Step-by-step, build-verified
recipes for each are in **[recipes/shapes/](recipes/shapes/)**.

## Related

- [geometry-and-bsp.md](geometry-and-bsp.md) — solidity, order, and why round/off-grid shapes want
  semisolid.
- [human-scale.md](human-scale.md) — the sizes to build these shapes to.
- [recipes/shapes/](recipes/shapes/) — the non-box constructions (chamfer, wedge, octagon, ring, twin).
