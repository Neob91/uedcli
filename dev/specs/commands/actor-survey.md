# actor survey — relation spec

Two tiers: **raw** (pure authored geometry, ignores CsgOper/CSG order)
and **csg** (resolved, CSG-order-aware). Every relation is tagged
`raw:` or `csg:`. Where the same concept exists in both tiers, it keeps
one name — the prefix carries tier identity, not the verb.

**Interior**, for a polygon: its 2D interior relative to its own plane
(the polygon minus its boundary edges) — not a 3D notion, which is empty
for any flat face.

**"A resolved up until right before B"**: A's geometry after every
earlier-in-CSG-order brush has acted on it, but before B itself is
added. Raw-tier rules never use this — raw always reads each brush's
full authored shape.

**Area contact**: two polygons, lying on the same plane, facing away
from each other (opposite-facing normals) — one's outline minus the
other is where each is "outside" the other, so opposite-facing normals
is what makes this a touch rather than an overlap — whose 2D outlines
share more than a single point or a single edge: the overlap between
them covers a real patch of area. A shared corner or a shared edge
alone is *not* area contact, and is not any relation at all here — not
`touches`, and not `crosses` either, since nothing's interior reaches
into the other's. Two polygons on different (non-coplanar) planes can
never be in area contact — their shared points, if any, form at most a
line, never a patch — which is why `crosses` (the non-coplanar relation)
is never required to clear this bar: a shared point there is already as
much contact as the geometry allows.

## raw:touches

Given Brush A (ANY) and Brush B (ANY), B touches A when:
- Some polygon of brush A (full authored shape) and some polygon of
  brush B (full authored shape) are coplanar
- Their 2D outlines, within that shared plane, overlap by a real area —
  not just a shared point or a shared edge

Normals not considered here, unlike area contact below — raw doesn't
distinguish "opposite-facing coplanar overlap" from "same-facing
coplanar overlap"; either one, by itself, is `raw:touches`.

## csg:touches

Given Brush A (ANY) and Brush B (ANY), B touches A when:
- Brush A is before brush B in CSG order
- Some polygon of brush A (resolved up until right before brush B) and
  some polygon of brush B are in area contact (see above)

## raw:crosses

Given Brush A (ANY) and Brush B (ANY), B crosses A when:
- Some polygon of brush A (full authored shape) and some polygon of
  brush B (full authored shape) lie on non-coplanar planes
- The interior of one of those polygons shares a point with the
  interior of the other

## csg:crosses

Given Brush A (ADDITIVE/SEMISOLID/SUBTRACTIVE/NONSOLID) and Brush B
(ADDITIVE/SEMISOLID/NONSOLID/MOVER), B crosses A when:
- Brush A is before brush B in CSG order
- Some polygon of brush A (resolved up until right before brush B) and
  some polygon of brush B lie on non-coplanar planes
- The interior of one of those polygons shares a point with the
  interior of the other

Mover note: for this rule only, a Mover's CSG order position is defined
as after every real brush (not a change to the real CSG order used
elsewhere). Consequences: as B, the order condition always holds and "A
resolved up until right before B" is A's fully resolved state; as A, the
order condition can never hold, so a Mover can never be crossed (which
is also why Mover is absent from A's kind list above).

Non-coplanar note: a coplanar pair with opposite-facing normals is pure
touch (→ `touches`). Same-facing normals is real overlap but adds
nothing: any genuine straddle also produces a non-coplanar crossing pair
elsewhere (two closed, gap-free boundaries that overlap without either
enclosing the other must cross transversally somewhere, and a
transversal crossing is never coplanar). Confirmed against
`Brush698`/`Brush693` (`nyc_unatco_island`): excluding their coplanar
floor-overlap still leaves `Brush693`'s top face crossing three of
`Brush698`'s side faces.

## raw:encloses

Given Brush A (ANY) and Brush B (ANY), A encloses B when:
- Brush A's full authored shape fully contains brush B's full authored
  shape

## raw:coincides

Given Brush A (ANY) and Brush B (ANY), A coincides with B when:
- Brush A's full authored shape and brush B's full authored shape fully
  contain each other (identical/duplicate volumes)

No csg analog: pure authored-duplicate fact, unaffected by CSG order.

## csg:carves

Given Brush A (ADDITIVE/SEMISOLID/NONSOLID) and Brush B (SUBTRACTIVE), B
carves A when:
- Brush A is before brush B in CSG order
- Some polygon of brush A (resolved up until right before brush B) and
  some polygon of brush B lie on non-coplanar planes
- The interior of one of those polygons shares a point with the
  interior of the other

Movers excluded entirely — never carved, never carve.

## csg:connects

Given Brush A (SUBTRACTIVE) and Brush B (SUBTRACTIVE), B connects with A
when:
- Brush A is before brush B in CSG order
- Some polygon of brush A (resolved up until right before brush B) and
  some polygon of brush B are either in area contact (see above) or
  have interiors that share a point

Coplanar pairs included — unlike `crosses`/`carves`, there's no
same-normal/opposite-normal ambiguity here: this is about void
continuity, not which side has solid matter.

## csg:occupies

A point/volume question, not a boundary one — not a polygon-crossing
test like the relations above.

Given Brush A (SUBTRACTIVE) and Brush B (ADDITIVE/SEMISOLID/NONSOLID/
MOVER) or a non-brush point actor, B occupies A when:
- Brush A is before brush B in CSG order (Mover convention from
  `csg:crosses` applies: a Mover's order position is after every real
  brush, so this always holds for a Mover B)
- The void carved by brush A (resolved up until right before brush B)
  fully contains brush B's raw (authored) geometry — or, for a
  non-brush point actor, contains its Location point

## Open, not yet resolved

- Float-noise epsilon on the coplanarity and interior-crossing checks.
- Whether raw tier's *existing* `overlaps`/`meets` implementation
  (volume/cell-based, not polygon-based) already handles Nonsolid
  brushes correctly, or needs the same polygon-based fix `csg:crosses`
  got. Not assumed either way — needs checking before implementation.
- Implementation must walk every surviving/authored polygon fragment —
  never deduplicate to one fragment per (owner, plane); that dedup was
  the root cause of the original bug.
- Scope: brush-vs-brush only. Non-brush point-actor sources are
  untouched by this spec.
