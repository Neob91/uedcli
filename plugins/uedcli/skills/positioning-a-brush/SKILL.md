---
name: positioning-a-brush
description: Use when placing a new or moved UE1/Deus Ex brush against an existing reference face in uedcli — flush against a wall, centered on a floor, aligned to an edge — instead of hand-computing or eyeballing a Location.
---

# Positioning a Brush Against a Reference Face

## Overview

Computing a target `Location` by eye (reading a face's coordinates, adding an offset by hand) is
exactly the kind of spatial arithmetic that goes wrong — off by a few units, flush on one axis but
not the other, or embedded inside the wall instead of resting against it. `brush relation
measure`/`set` solve the placement directly from the geometric relationship you want, not from a
coordinate you compute.

**REQUIRED BACKGROUND:** read `../../references/brush-relation-basics.md` for the `find`/`measure`
mechanics used below.

## When to Use

- Placing a new brush flush against an existing wall, floor, or ceiling.
- Moving an existing brush to align with another (centered, edge-flush, or a specific gap).
- Any time the target position is defined by a RELATIONSHIP to another face ("flush against this
  wall", "centered on that floor") rather than an absolute coordinate you already know.

Not needed for a placement with no reference face (e.g. free-floating in open space by a rough
eyeball position that doesn't need to be exact).

## Core Pattern

```bash
# 0. Find the reference face's world-space location (measure never prints world coordinates —
#    brush poly list does) and its CsgOper (grep the actor.t3d, or `actor prop get <brush> CsgOper`)
uedcli brush poly list Wall
uedcli actor prop get Wall CsgOper

# 1. Build NewBrush at a ROUGH position first, offset from the reference on BOTH in-plane axes —
#    this makes step 2's U/V reading free (see "U/V axes" below)
uedcli brush build cube --width .. --breadth .. --height .. --at <rough x,y,z> --csg add|subtract ...

# 2. Read the CURRENT relationship (picks the mating face, reads U/V mapping — see below)
uedcli brush relation measure Wall:5 NewBrush --top all

# 3. Move NewBrush to the exact target relationship
uedcli brush relation set NewBrush:3 --relative-to Wall:5 --gap 0 --centroid-u 0 --centroid-v 0
# or, for a brush that must sit on the floor rather than centered vertically:
uedcli brush relation set NewBrush:3 --relative-to Wall:5 --gap 0 --centroid-u 0 --edge-v-min 0
```

- `--gap N` sets the signed perpendicular distance to the reference plane (`0` = flush).
- `--centroid-u N --centroid-v N` centers the target's footprint on the reference face's own U/V
  axes (`0,0` = centered both ways).
- `--edge-u-min/max N` / `--edge-v-min/max N` align to a specific edge instead of centering on
  that axis — mix and match per axis. **This is the common case, not an advanced option**: a
  floor-standing object wants `--edge-v-min 0` (or whichever axis is vertical), not
  `--centroid-v` — centering vertically floats it above the floor.
- `set` only ever moves `Location` — it never resizes or reshapes. Build the brush at the right
  size first (`brush build ...`), then position it.
- `set` also never decides `CsgOper` — whether the new brush should be `--csg add` (a solid
  object) or `--csg subtract` (a recess carved into surrounding solid, e.g. an alcove cut into a
  subtractive room's wall) is a design call you make at `brush build` time, before any of this.
- Batch form: `find ... | relation set - --relative-to REF:idx --gap 0` places every piped
  candidate against the same reference in one pass.
- **Measuring an existing precedent settles ambiguity for free.** If a similar object already
  sits correctly against a similar reference elsewhere in the level (another sign on another
  wall, another alcove off the same corridor), `measure` that pair first — its gap/edge values
  are the house convention, and matching them is more reliable than guessing.

## Picking the mating face

A symmetric brush (a box) has faces on every side, but only ONE of them actually touches the
reference correctly — the opposite face would land your brush *embedded inside* the reference
instead of resting against it. Which one depends on the reference's `CsgOper`, and getting this
backwards is the single most common mistake with this skill:

- **Reference is `CSG_Add`** (a solid object — furniture, a pillar, a standalone block): its face
  normal points OUTWARD, away from the solid. The mating face is the one **ANTI-parallel**
  (opposite direction) to the reference's normal — the two surfaces face each other.
- **Reference is `CSG_Subtract`** (a room, corridor, or any void carved into the world — the
  common case for an interior wall/floor/ceiling): its face normal points OUT of the empty space
  and INTO the solid it carves — inverted from the additive convention. The mating face is the
  one **PARALLEL** (same direction) as the reference's normal. Picking anti-parallel here embeds
  the new brush in the wall.

Check `CsgOper` before reading normals — a wall in a real level is a subtractive room's face far
more often than a standalone additive block, so defaulting to "anti-parallel" is wrong more often
than it's right.

```bash
uedcli actor prop get Wall CsgOper
uedcli brush relation measure Wall:5 NewBrush --top all
```

**Verify after `set`, don't just trust the rule:** measure the OTHER (non-chosen) candidate face
too. It must land on the solid/exterior side — for a subtractive reference this means its
`distance` reads positive (outside the carved void); a negative distance there means you picked
the wrong face and the brush is embedded.

## U/V axes are the reference face's own, not world XYZ

`measure`'s `centroid_u`/`centroid_v`/`edge_u`/`edge_v` and `set`'s matching flags are all in the
REFERENCE face's own in-plane axes — which world axis is U and which is V (and which direction is
positive) depends on that face's orientation. This matters most on a floor/ceiling (horizontal)
face, where U/V could map to either world X or Y depending on how the face was authored — don't
assume, and don't assume the sign either (U sometimes maps to −X, not +X).

The cheapest way to read the mapping costs nothing extra: build the new brush at a rough position
that's offset from the reference on BOTH in-plane axes (Core Pattern step 1), then read the first
`measure`'s `centroid`/`edge` U/V values against the world offset you already know — the deltas
*are* the mapping, no separate probing pass needed.

On a rotated brush, U/V rotate with the face — `measure`/`set` handle this correctly with no extra
work, but don't try to convert to world XYZ by hand; use the reported U/V values directly.

## Common Mistakes

- **Hand-computing `Location`** from a face's coordinates and an offset. Use `measure` + `set`
  instead — no arithmetic to get wrong.
- **Assuming "anti-parallel" always wins.** It's inverted for a subtractive reference — see
  "Picking the mating face" above. Check `CsgOper` first.
- **Assuming U maps to world X.** Read it from the first `measure` against a known rough offset
  (see above) before writing `--centroid-u`/`--edge-u-*` values that assume a world-axis mapping.
- **Forgetting `set` doesn't resize.** If the brush is the wrong size for the target space, that's
  a separate `brush build`/`brush scale` step, not something `--gap`/`--centroid`/`--edge` fixes.
- **Centering on the vertical axis for a floor-standing object.** Use `--edge-v-min 0` (or
  whichever in-plane axis is vertical), not `--centroid-v` — see Core Pattern.
- **Forgetting `set` doesn't decide `CsgOper` either.** An alcove carved into a room's wall needs
  `--csg subtract` at build time; positioning alone won't make a `CSG_Add` block "recess."
