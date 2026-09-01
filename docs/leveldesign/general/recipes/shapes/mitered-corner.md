# Recipe: mitered corner join  [ENGINE]

Where two trim strips meet at a right angle — a wall rail, a floor inlay, a pit-lip frame — weld or
miter the corner rather than letting them touch or overlap. Three reasons:

- **Fewer visible seam polys.** Two strips crossing at a corner each add end-cap and side faces there;
  welding or a matched diagonal cut removes the extra ones.
- **Consistent shading.** Two separate faces meant to read as one surface can shade slightly
  differently, even with no gap between them. A welded or matched-cut face avoids this. (Design
  rationale, not a confirmed engine fact; see [lighting.md](../../lighting.md).)
- **Texture/grain continuity.** Like mitered wood molding, a repeating pattern — grain, brushed metal,
  tile — wraps continuously around a miter. Two butted strips texture themselves independently, so
  the pattern can jump or misalign right at the seam even with no gap. A butt joint always breaks it;
  a miter doesn't.

## Closed frame — solid: additive outer + subtractive inner, no weld

A rectangular frame (a pit lip, a border) is an outer solid minus an inner void. Build both as
ordinary, separate brushes — outer `--csg add`, inner `--csg subtract` — and let normal CSG
resolution carve the frame shape at build time. Neither piece is the frame shape by itself — the
frame only appears where the engine's own CSG solve carves the two together.

    brush build cube --csg add      --width 200 --breadth 200 --height 8 --at 0,0,0 | actor add -
    brush build cube --csg subtract --width 168 --breadth 168 --height 8 --at 0,0,0 | actor add -

**Avoid:** don't weld the two into one brush with `brush intersect`. That produces a single concave
(ring-shaped) brush whose top and bottom faces have a hole in them — not a shape one flat face can
represent, so the CSG solve has to split it into pieces. This toolchain handles non-convex brushes
built this way unreliably; two ordinary convex brushes avoid the problem entirely. General rule:
avoid concave brushes; if one's ever truly unavoidable, prefer semisolid over solid — lower risk.
(Owner guidance; not an independently engine-verified defect.)

## Open run: miter with `brush clip --plane`

A 3-sided run (a wall rail stopping at a doorway, a floor inlay against a counter) has no fourth side,
so it can't be built with the additive/subtractive trick above. Instead, clip each piece on the SAME
45° plane through the corner, keeping OPPOSITE sides.

Both strips must be the same thickness (width/breadth across the run) — a 24uu rail against an 8uu
inlay won't close: the outer edges miss the tip and the inner edges won't taper to a point.

The plane is always 45°, but its normal — the direction that decides which side is `below` — depends
on which two strips meet there, not the corner alone. It flips between the two ends of a run:

    # west strip meets south strip, corner (-764,-572,140)
    actor show WallRailW | brush clip - --plane -764,-572,140 1,-1,0 --keep below | brush replace WallRailW -
    actor show WallRailS | brush clip - --plane -764,-572,140 1,-1,0 --keep above | brush replace WallRailS -

    # south strip meets east strip, corner (764,-572,140) -- same strip, opposite-sign normal
    actor show WallRailS | brush clip - --plane 764,-572,140 1,1,0 --keep below | brush replace WallRailS -
    actor show WallRailE | brush clip - --plane 764,-572,140 1,1,0 --keep above | brush replace WallRailE -

`--keep` is fixed too: the first piece clipped keeps `below`, the second `above`. Keep that consistent
— swapping it is the second failure mode below.

Build each piece past the corner already, not edge-exact — the clip needs overlap to cut a miter. An
edge-exact pair only clips a wedge off one side, leaving a pentagon.

### Verification pitfall

Two ways to get the pairing wrong, and both pass a naive check:

- **Same side for both pieces.** `brush measure relation` looks fine — coplanar, distance `0.000uu`,
  footprint coincident — because it only checks the cut face, not which side survived. It's still
  wrong: one triangle overlaps, the other is empty.
- **Opposite sides, swapped pairing** (below/above reversed). Both strips retreat from the corner
  instead of reaching it — a full gap, not an overlap — and the same check passes it just as wrongly.

What proves a clean miter: each piece's outer edge reaches the corner tip at full depth, and its inner
edge tapers to a point. Check with `actor bbox`/vertex inspection or a top-down `actor diagram` — a
bad miter is visible by eye even when the numbers look clean.

## Closed frame — semisolid: 4 mitered brushes

A semisolid can't be the target of a CSG subtraction (see
[geometry-and-bsp.md](../../geometry-and-bsp.md#solidity-solid-semisolid-nonsolid): semisolid can't
be subtracted-from), so the additive/subtractive trick above only works for a solid frame. Decorative
trim is usually semisolid anyway, to stay out of the structural BSP — for that case, build 4 separate
strips and miter every corner with the same `brush clip --plane` technique as the open run above,
applied to all 4 corners of a closed loop instead of 2. Unlike the open run, no strip has a
free end here: every one of the 4 strips gets clipped twice, once at each corner it touches. The same
two verification-pitfall failure modes above apply at each of the 4 corners.

Semisolids touching is fine — a clean miter produces exact touching (coincident plane, zero overlap),
never overlap, so this is safe by construction. It's semisolids *overlapping* that's uncertain and
best avoided; a correctly-verified miter (see above) never does that.

## Related

- [geometry-and-bsp.md](../../geometry-and-bsp.md) — the solidity rules (what each level cuts, seals,
  or may touch), and how `brush intersect` preserves per-face solidity.
- [`brush intersect` reference](../../../../reference/brush/intersect.md) — stdin CSG order,
  output-flag defaults, `--solidity`'s per-face rule.
- [chamfered-box.md](chamfered-box.md) — the same `brush clip` mechanism, for a single beveled edge.
- [ring-cornice.md](ring-cornice.md) — copy-rotated blocks around an axis; use instead when the pieces
  stay separate actors (gaps read as discrete blocks).
