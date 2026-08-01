# Spec: `brush shear` / diagonal-wall helper + an `actor rotate` grid caveat

## Goal

Two connected pieces plus a doc:

- **A grid-aligned diagonal-wall helper.** Building a 45° wall the right way — grid-aligned, no
  rotation, all-integer vertices, watertight — is today `brush build cube` then `brush vertex move`
  the far-end corners by a grid delta, which forces the author to hand-compute each corner coord. One
  verb should do it.
- **An `actor rotate` grid caveat.** `actor rotate` applies an arbitrary rotation that puts a brush's
  world vertices off the grid (a 45° yaw scales grid coords by ~0.707 → CSG cracks/leaks) with no
  warning. `brush build --rotate` already warns here; `actor rotate` should too.
- **A best-practice doc.** Grid-align-don't-rotate is a real UnrealEd rule: diagonal geometry is
  built by vertex-editing/shearing to grid points, not by rotating. Document it (owner approval
  required for docs).

## Current state

- Manual diagonal-wall flow: `brush build cube | actor add -`, then `brush vertex move <name> --at …
  --by …` per far-end corner. `vertex.move_vertices` selects corners by coordinate and moves every
  poly-vertex sharing each (watertight), but the author must type each corner's exact coord.
- `brush poly find --facing +X|-X|+Y|-Y|+Z|-Z` already selects faces by outward facing
  (`parsers/brush.py` `pfind`).
- `actor rotate` (`actor/edit.py:199`) sets (`--to`) or composes (`--by`) `Rotation` and
  `validate_brush`es, but does **not** warn on off-grid world vertices. Rotation is stored, not baked,
  so the local PolyList stays on-grid; the *world* vertices (`Location + R·(v − PrePivot)`) go
  fractional.
- `brush build --rotate` DOES warn: `generators.apply_generator_rotate` diffs `offgrid_flags`
  (threshold `1e-3`) before/after and warns only on **newly** off-grid vertices.
- The GMath rotator table's own noise is ~`6e-6` (see `actor/query.py` reporting-noise note), ~170×
  below the `1e-3` off-grid threshold, so an exact-on-grid brush will not false-positive.

## Design

### Part A — `brush shear` as a T3D-stdin filter (recommended; owner question below)

`brush shear -|FILE --face +X|-X|+Y|-Y|+Z|-Z --by DX,DY,DZ` reads a brush T3D snippet, displaces every
vertex on the named face by the world delta, and emits the sheared brush T3D to stdout. It generalises
the manual `brush vertex move` flow: no corner coords to type, and grid-aligned in → grid-aligned out.
Watertight, because it moves a whole face's corners together (every poly-vertex sharing each).

```
brush build cube --width 32 --breadth 128 --height 256 \
  | brush shear --face +Z --by 128,0,0 | actor add -      # a leaning/diagonal wall, one pipe, no rotation
```

- Face selection reuses the `--facing` vocabulary; the target face is the set of vertices whose face
  snaps to that facing. `--face` accepts only the six axis facings (the grid-aligned case); a brush
  whose target face is slanted has no matching face.
- **SET on stdin**: all-or-nothing; builder brushes dropped; a non-brush member → exit 2 naming it
  (matches `clip`/`intersect`). Movers carry a PolyList, so they are sheared.
- A brush with no face matching `--face` → exit 2 naming it (the author expected a face; not a silent
  no-op).
- `validate_brush` after — a shear that degenerates a face → exit 2 naming the actor.

Alternative (owner question): a dedicated **diagonal-wall builder** (`brush build …` taking two grid
endpoints + thickness + height, emitting a grid-aligned slanted wall directly) instead of, or beside,
the shear filter. The shear filter is more general (any prism end, any brush) and composes with the
existing build family; the builder is a bespoke parametrized shape.

### Part B — `actor rotate` off-grid warning (recommended: warn only)

Add the same **newly-off-grid** stderr warning `brush build --rotate` emits to `actor rotate --to`
and `--by`, for brush actors: compute `offgrid_flags(rotation.world_vertices(actor))` before and after
the rotation and warn when the rotation newly pushes any vertex off the integer grid. Advisory only —
it does **not** change what `actor rotate` writes: no snap, no clamp, no block. (Snapping would
silently alter geometry — forbidden without an explicit yes — and could drag an on-grid brush off its
own grid; the `PrePivot`/`Rotation` fields are load-bearing.) The message names the actor and points
at the grid-align-don't-rotate path (build to grid + `brush shear`).

The item floats snapping / suggesting the shear path as alternatives to a plain warning — owner
question below.

### Part C — the best-practice doc (owner approval required)

Propose, for the owner's yes (docs need explicit approval — `CLAUDE.md`):

- `dev/docs/unrealed/` engine finding: a non-axis rotation multiplies grid coords by `cos/sin`
  (~0.707 at 45°), landing world vertices off-grid → off-grid BSP split planes → slivers, T-junctions,
  holes. Diagonal geometry is built by vertex-editing/shearing to grid points, not by rotating.
- `docs/leveldesign/` craft note (grid-align-don't-rotate), cross-referenced to `brush shear` and
  `brush vertex move`.

Park the proposed text via the board if it is unanswered when the build lands.

## Edge cases & errors (shear)

- Empty stdin → exit 0; name-list stdin → exit 2; non-brush member → exit 2 naming it.
- No face matches `--face` (incl. a brush whose target face is slanted) → exit 2 naming the brush.
- `--by` degenerates/collapses a face → `validate_brush` raises → exit 2 naming the actor.

## Tests

- `brush build cube | brush shear --face +Z --by 128,0,0 | actor add -` → a parallelepiped with
  integer vertices, `level doctor`-clean (watertight).
- `actor rotate` 45° yaw on an on-grid cube → stderr off-grid warning; the written `Rotation`/
  `Location` are unchanged (warn-only, no snap).
- `actor rotate` 180° yaw on an exactly-on-grid brush → NO warning (GMath noise below the `1e-3`
  threshold).
- Shear: non-brush member → exit 2; no-matching-face → exit 2; empty stdin → exit 0.

## Open questions

- **Diagonal-wall helper surface**: a `brush shear` filter (recommended), a dedicated diagonal-wall
  builder, or both? (`questions/shear-filter-vs-diagonal-wall-builder.md`.)
- **`actor rotate` off-grid behaviour**: warn only (recommended), snap to grid, or warn + suggest the
  shear path? (`questions/actor-rotate-offgrid-behaviour.md`.)
- The Part C docs need the owner's explicit yes; exact text proposed at build time.
