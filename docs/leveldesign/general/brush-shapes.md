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
- `--radius` — the circumscribed radius. `--align-to-side` offsets the cross-section by half a segment
  (`180/--sides` degrees) so a flat FACE, not a vertex, meets an axis — the same parameter as UED's own
  `AlignToSide` checkbox. (For any other angle use `--rotate`.) (uedctl's cylinder is a **solid** prism only — there is no inner-radius/hollow
  tube option; build a tube by subtracting a smaller cylinder from a larger one.)
- Round geometry is off-grid by nature — prefer **semisolid** for cylindrical detail so it doesn't seed
  BSP holes (see [geometry-and-bsp.md](geometry-and-bsp.md)).

### `cone` — `ConeBuilder`
A pyramid or **frustum** (truncated cone) — spires, tent roofs, tapered pillars. Requires `--height` and
`--radius`; `--sides` (default 8) and `--align-to-side` are optional.

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
  `level preview --game`) build this non-convex brush correctly; the coarse CSG core behind
  `level preview --native` assumes convex brushes, so it mis-builds the concave notches. Judge
  staircases with `--game`, not `--native`.

> The editor's separate curved-stair builder (`CurvedStairBuilder` — inner radius, angle of curve,
> clockwise/counter-clockwise) has **no uedctl verb**. For a rising rotation use `spiral` (a different
> builder); otherwise approximate a curved stair by placing linear runs at angles.

### `spiral` — `SpiralStairBuilder`
A real spiral staircase: a **central column** (a cylinder filling the axis over the full height) plus
one **wedge (pie-slice) tread per step**, each tread rotated `--angle-per-step` and raised one `--rise`
above the last — so the treads fan around the column and climb monotonically (a single helix, not a
mirrored fan). Prints `N+1` brush actors (`[column, wedge_0, …]`). Requires `--steps`, `--inner-radius`
(column radius = inner tread radius), `--step-width` (radial tread depth), and `--rise` (tread
thickness / per-step climb); `--angle-per-step` is optional — unreal rotation units like `--rotate`,
default `8192` (45°). `--at` anchors the base of
the column axis (bottom of the stair). Typically added as an **additive** structure (the treads read
as a solid stair); each emitted brush is a clean convex solid, so subtracting works too.

### `extrude` — sweep a profile you draw, in a straight line
The first of two **swept** shapes: instead of choosing sizes for a fixed silhouette, you *draw* the
cross-section. Repeat `--point U,V` once per profile vertex, in ring order (at least 3; the ring closes
implicitly), then `--depth` sweeps it along `--axis`. That is the shape for an L-ledge, an arch
voussoir, a moulded cornice, a chamfered pillar — any cross-section the fixed builders cannot express.
`--at` is the world point profile coordinate `(0,0)` lands on (nothing is re-centred), so a ring of
voussoirs drawn at known offsets stays laid out as drawn.

`--axis` names the world axis the profile plane is **normal to** — equivalently, the direction the
sweep grows. The profile's `(U,V)` then land on the other two world axes in right-handed cyclic order:

| `--axis`        | `U` | `V` | the sweep grows along |
|-----------------|-----|-----|---|
| `z` *(default)* | X   | Y   | +Z |
| `x`             | Y   | Z   | +X |
| `y`             | Z   | X   | +Y |

**Concave profiles are fine, and stay ONE brush.** The engine's polygon must be convex and holds at
most 16 vertices, so a concave profile (an L, a notched cornice) or one over 16 points has each of its
two caps tiled into several convex faces — adding only diagonals of your own outline, so the solid
stays watertight. Faces are `Cap` per end plus one `Side<k>` per profile edge, numbered in ring order,
so `brush poly find --item Side0` selects "the face swept by my first profile edge".

- **Native caveat:** as with `staircase`, UnrealEd (`level materialize`) and the real engine
  (`level preview --game`) build a concave swept brush correctly, but the coarse CSG core behind
  `level preview --native` assumes convex solids and draws a concave notch *filled in* — a
  preview artefact, not a geometry bug.

### `revolve` — sweep that same profile around an axis
Same profile grammar and same `--axis`; instead of a straight `--depth` it sweeps **around the profile
plane's own `V` axis** (the line `U = 0`, through profile coordinate `(0,0)`), in `--segments` flat
facets. `--at` is therefore the **bend centre**, and how far the shape sits from it is written in the
profile: a profile drawn at `U ∈ [64, 192]` revolves at radii 64 to 192. `--angle` is in unreal
rotation units (`16384` = 90°, `65536` = a closed full turn, which omits both caps); the default
density is one facet per 22.5°, matching UnrealEd. The profile must sit strictly on the positive-`U`
side of the axis.

- **A revolve is off the integer grid by construction** — every vertex away from `θ=0` lands on
  `radius · cos/sin θ`, and uedctl never snaps for you. An off-grid **solid** throws its BSP partition
  planes off-grid too, the primary cause of slivers, T-junctions and holes. Prefer
  **`--solidity semisolid`** wherever the swept shape is detail rather than structure; uedctl warns on
  stderr when it emits an off-grid solid.

## Curved geometry

**`brush build revolve` (above) is the dedicated curved-corridor verb** — it does exactly what this
section used to say had to be done by hand. The underlying fact is unchanged: curves in UE1 are still
many straight segments (16 facets = 360°), `revolve` just generates them for you instead of leaving you
to place each one. Vertex-edited curves remain fragile — they destroy surface alignment (re-align
after) and need a rebuild *before* editing. Prefer generated or straight-brush CSG and accept faceting;
it is far more robust than hand-curved geometry.

Also note: **UE1 terrain is 100% brush-based.** There is no heightmap `TerrainInfo` (that's UE2) —
sculpt terrain from tessellated brushes or intersect-before-add rock CSG.

## Beyond the builders — shape recipes

The builders make the base primitives; the **non-box** shapes real levels are full of (chamfered beams,
wedges, octagon columns, ring cornices, add/subtract-twinned trim) come either from *composing* them —
`brush build` + **`brush clip`** (bevel/taper/miter) and copy-rotate — or, when the cross-section is the
thing you care about, from drawing it directly with **`extrude`/`revolve`** above. Step-by-step,
build-verified recipes for each are in **[recipes/shapes/](recipes/shapes/)**.

## Related

- [geometry-and-bsp.md](geometry-and-bsp.md) — solidity, order, and why round/off-grid shapes want
  semisolid.
- [human-scale.md](human-scale.md) — the sizes to build these shapes to.
- [recipes/shapes/](recipes/shapes/) — the non-box constructions: composed (chamfer, wedge, octagon,
  ring, twin) and drawn-profile (L-ledge, arch voussoir, moulded cornice, curved corridor).
