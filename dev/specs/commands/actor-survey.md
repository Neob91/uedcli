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

**Real area** (as opposed to a mere point or edge): two coplanar
polygons' 2D outlines overlapping by more than a single point or a
single edge — the overlap covers an actual patch. A shared corner or
edge alone is not real area, and is not any relation at all here.

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

A point/volume question, not a polygon-area test — the same class as
`csg:occupies`, not `csg:crosses`/`csg:carves`. Corrected from an
earlier draft of this spec: a flush contact's surviving face routinely
belongs to neither authored polygon at all (two Adds butted exactly
face-to-face lose BOTH owners' faces at the shared plane; a self-carved
stub's cap belongs entirely to the Subtract that cut it, never to the
matter actor whose authored body never had a face there) — no
polygon-to-polygon area test can see either shape, so the fact is
decided by a matter-side probe instead.

Given Brush A (ANY) and Brush B (ANY), B touches A when some site
exists where:
- Brush A's and brush B's own authored polygons coplanar-overlap by a
  real area, OR (when no such matching polygon exists on one side) one
  side's own authored polygon, clipped to the other actor's own extent,
  still has a real area there
- At that site, brush A's and brush B's resolved matter sit on opposite
  sides of the site's plane (ordinary matter-against-matter contact) —
  OR one side's resolved matter is on exactly one side AND the other
  side is a Subtractive brush that genuinely carved real matter away
  right there (matter resting against a real carve boundary — never a
  no-op Subtract, and never a Subtract's boundary floating deep inside
  the other actor's volume rather than at its own edge)

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

Same class of test as `csg:touches` (matter-side probe, not polygon
area contact), with "void on both sides, nothing solid between"
in place of "matter on opposite sides."

Given Brush A (SUBTRACTIVE) and Brush B (SUBTRACTIVE), B connects with A
when any of:
- Some polygon of brush A and some polygon of brush B (full authored
  shapes) lie on non-coplanar planes with interiors sharing a point
  (same test `crosses`/`carves` use — a real intersection, not just a
  shared boundary)
- Some site exists (found the same way `touches` finds one) where
  neither brush A's nor brush B's resolved matter is on either side
  (both are genuinely void there, not merely "not present at all"),
  both are at their own real authored boundary at that site, and no
  OTHER actor's matter fills the gap between them either
- Brush A's full authored shape fully contains brush B's, or vice versa
  — a nested Subtract's void is trivially continuous with its
  container's, redundant carve or not

Known gap, not fixed: no reachability check across the whole level. A
Subtract's void sealed off by an unrelated solid block can still
report `connects` to a neighbor sharing a coincident wall plane, since
this only checks void-ness locally at the shared site, never whether a
void path actually threads all the way between the two Subtracts'
interiors.

## csg:occupies

A point/volume question, not a boundary one — not a polygon-crossing
test like the relations above.

Given Brush A (SUBTRACTIVE) and Brush B (ADDITIVE/SEMISOLID/NONSOLID/
MOVER) or a non-brush point actor, B occupies A when:
- Brush A is before brush B in CSG order (Mover convention from
  `csg:crosses` applies: a Mover's order position is after every real
  brush, so this always holds for a Mover B)
- The void carved by brush A (resolved up until right before brush B),
  restricted to where it OVERLAPS brush B's raw (authored) geometry —
  not full containment: an occupant seated across two Subtracts' voids,
  fully inside neither, must still report occupies against each one
  independently (`Bridge`, 20uu into each of two Subtracts' voids,
  composing where full containment structurally cannot) — or, for a
  non-brush point actor, contains its Location point

## Open, not yet resolved

- Float-noise epsilon on the coplanarity and interior-crossing checks.
- `csg:crosses`/`csg:carves` must walk every surviving/authored polygon
  fragment — never deduplicate to one fragment per (owner, plane); that
  dedup was the root cause of the original bug. Not relevant to
  `csg:touches`/`csg:connects`/`csg:occupies`, which test authored
  polygons and resolved matter directly, not resolved face fragments.
- `csg:connects`'s reachability gap (sealed voids) — see its own
  section above.
- Scope: brush-vs-brush only. Non-brush point-actor sources are
  untouched by this spec.
