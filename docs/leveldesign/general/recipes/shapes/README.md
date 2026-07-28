# Shape recipes  [ENGINE]

How to build non-box brush shapes — the constructions you reach for once a plain `brush build cube`
isn't enough. These are shape recipes (a chamfered beam, an octagon column, a ring cornice), distinct
from the feature recipes in the parent dir (water, doors, lifts). All are engine-generic CSG technique.

> **Build-verified.** Every pipeline here was executed end-to-end using only the CLI (no source, no
> hand-authored T3D) and the result checked against the target.

> **Names are placeholders.** `actor add` allocates a random-suffixed name (e.g. `Cube_ab12cd`); feed
> the actual name it prints to any follow-up `brush clip`/`actor prop set`/`actor rotate`.

| Recipe                                         | Builds |
| ---------------------------------------------- | --- |
| [chamfered-box.md](chamfered-box.md)           | A box with a 45°-beveled edge — hoods, trims, troughs, mitered ends |
| [triangular-wedge.md](triangular-wedge.md)     | A right-triangle prism — ramps, gussets, angled fill |
| [octagonal-column.md](octagonal-column.md)     | A faceted round pillar (and how "round" is done at all) |
| [ring-cornice.md](ring-cornice.md)             | A ring of blocks around an axis — the fake-a-curve copy-rotate pattern |
| [add-subtract-twin.md](add-subtract-twin.md)   | A solid piece + its matching carved recess (the seat-the-trim workflow) |
| [l-ledge.md](l-ledge.md)                       | A shelf/curb whose cross-section is an L — the simplest drawn-profile sweep |
| [arch-voussoir.md](arch-voussoir.md)           | One wedge stone of a masonry arch — a trapezoid swept through the wall |
| [curved-corridor.md](curved-corridor.md)       | A passage that bends — a cross-section revolved around the bend centre |
| [moulded-cornice.md](moulded-cornice.md)       | Stepped/chamfered trim swept along a wall (supersedes copy-rotate for straight runs) |

The verbs almost every shape recipe leans on: `brush clip` (cut a brush by an arbitrary plane, keep
one half — how you bevel, taper, and miter), `brush build cylinder --sides N` (a faceted round
pillar), and `brush build extrude` / `brush build revolve`, which sweep a silhouette you draw
yourself and are the general answer to "this cross-section is not a box". Read
[../../brush-shapes.md](../../brush-shapes.md) and [../../geometry-and-bsp.md](../../geometry-and-bsp.md)
for the underlying builders and BSP rules.

---

## Two workflow patterns

These are ways of working the shape recipes build on, not single shapes:

- **Fake curves with straight brushes.** UE1 has no smooth curves — every curve is facets. Three ways
  to get them: a low-side `cylinder` (octagon columns/drums); `brush build revolve`, which sweeps a
  cross-section around an axis in flat facets and is the natural one for a bend, ring, or turned
  profile ([curved-corridor.md](curved-corridor.md)); or a ring of straight blocks copy-rotated around
  an axis ([ring-cornice.md](ring-cornice.md)), still what you want when the pieces must be separate
  actors. Chamfers (45° clips) stand in for fillets.
- **Add then carve its twin.** Build a shaped additive solid, `actor duplicate` it, flip the copy to
  subtractive, and seat it into a wall to carve a matching recess
  ([add-subtract-twin.md](add-subtract-twin.md)).

> **Provisional observation (📊 one map, no control — not yet a general claim).** In HK: WanChai
> Street, the add/subtract-twin workflow and facet-faked curves dominated the non-box geometry, and
> brush complexity stayed low (3–8-sided prisms; only stairs/domes were high-vertex). Whether that's
> DX-general or engine-general is unconfirmed until a second map or a UE1 control is measured.
