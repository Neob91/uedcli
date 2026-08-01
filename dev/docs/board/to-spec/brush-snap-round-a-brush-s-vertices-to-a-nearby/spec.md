# Spec: `brush snap` — round a brush's vertices to a nearby grid

## Goal

A new stateless `brush snap` filter: read a brush T3D snippet on stdin (`-`) or a saved FILE, round
each **local** vertex component to a grid where it is within tolerance, and emit the snapped brush
T3D to stdout — pipes like `brush clip`/`intersect` → `actor add -` or `brush replace`. Two params:
`--grid N` (the grid to snap to) and `--tolerance T` (how close a component must be to a grid line to
snap). A component farther than T from the grid is left in place, so *intentional* off-grid geometry
(angled/rotated/curved brushes) is preserved and only near-grid float noise is corrected. Off-grid
coordinates are the main cause of BSP holes, so snapping the noise (not the angles) cleans imported
or drifted geometry for reliable CSG.

## Current state

- No `brush snap` today.
- `emit.clean` (`CLEAN_EPS = 0.001`) already snaps a coordinate within 0.001 of an **integer** to
  that integer — but only to integers, only within 0.001, and it never cleans an N-grid or a larger
  slop band.
- Precedent filters (T3D-in / T3D-out): `brush intersect`/`deintersect` (`edit.py:32`) and the
  proposed `brush clip` filter — read a snippet via `ingest.read_t3d_input`, parse with
  `parse_t3d_actors`, drop builder brushes, emit with `emit_actor_t3d`. Empty stdin is a clean no-op;
  a name list on stdin and a non-brush member are both exit 2.
- Weld model: a brush stores vertices per-polygon, so one corner appears once per touching face;
  `vertex.weld_vertices` groups copies by cleaned coordinate.

## Design

**DECIDED (owner):** snap the brush's **local** vertices (its own PolyList coordinates), per-axis,
independent of the actor's `Location`/`Rotation`/`Scale`. This cleans the authored geometry itself,
not a transformed view of it.

`brush snap -|FILE --grid N --tolerance T`:

- For each brush actor, each poly vertex, each axis component `c`: let `g = N · floor(c/N + 0.5)`
  (round half toward +∞ — deterministic, matching `build.py` `_revolve_sweep`'s deliberate
  non-banker's rounding). If `|c − g| ≤ T`, set the component to `g`; else leave `c`. Per-axis and
  per-vertex independently, so a slant vertex keeps its genuinely-off-grid axis and cleans the
  near-grid ones.
- Because a corner's copies get the identical rule, near-grid copies that had drifted apart (e.g.
  `32.00003` and `31.99997`) both snap to the same `g` — snapping **re-welds** them.
- `validate_brush` after each brush. Snapping some axes of a face's vertices can push the face
  non-planar or degenerate; that is refused (exit 2 naming the actor), never emitted.
- **SET on stdin**: accept a set; snap each brush; all-or-nothing. Builder brushes dropped. A
  non-brush (point) actor is refused, exit 2 naming it (matches `clip`/`intersect`). Movers carry a
  PolyList, so they are snapped.
- `--grid` and `--tolerance` are both **required, no default** — any default grid or tolerance is a
  silent guess: too large a tolerance snaps everything and destroys angles, too small cleans nothing.
  The author states the grid they built on and the noise band they mean to correct.

### Proposed CLI surface

```
brush snap -|FILE --grid N --tolerance T
  -|FILE        read the brush SET as a T3D snippet on stdin (`-`) or from a saved FILE. `-` is the
                sole names source. Empty stdin is a clean no-op (exit 0)
  --grid N      grid size in world units to round each LOCAL vertex component to (e.g. 16, 8, 1)
  --tolerance T  max distance in world units from the nearest grid line to snap. A component farther
                than T from the grid is LEFT IN PLACE, so intentional off-grid geometry (angled,
                rotated, curved) is preserved and only near-grid float noise is cleaned. Snapping is
                per-axis: a slant vertex keeps its off-grid axis and snaps the others. Rounds half
                toward +infinity
```

## Edge cases & errors

- `--grid ≤ 0` or non-finite → exit 2 naming it. `--tolerance < 0` → exit 2.
- `--tolerance ≥ N/2` snaps every component to a grid line (destroys any angle) — allowed (the author
  asked), with a stderr note that it will snap everything.
- Empty stdin → exit 0; name-list stdin → exit 2; non-brush member → exit 2 naming it.
- Snap pushes a face non-planar/degenerate → `validate_brush` raises → exit 2 naming the actor;
  collect all such across the set (all-or-nothing).
- A brush already exactly on the grid → emitted unchanged (idempotent).

## Tests

- A cube with `+1e-4` noise on integer corners, `--grid 1 --tolerance 0.01` → exact integer vertices.
- A 45° slant vertex with one axis genuinely off-grid by `> T` → that axis preserved, the near-grid
  axes snapped.
- `--grid 16` snaps `15.9997 → 16`, leaves a real `8.5` (distance 7.5 from 16 `> T`) in place.
- Re-weld: two copies of a corner at `32.00003` / `31.99997` both land on `32`.
- Round-half determinism at a component exactly `N/2` from a grid line within `T`.
- Non-brush member → exit 2; empty stdin → exit 0; face-non-planar snap → exit 2.

## Docs to update in the same change

- `docs/usage.md`: the new `brush snap -|FILE --grid --tolerance` filter, beside `clip`/`intersect`.
- Cross-reference from `docs/leveldesign/general/geometry-and-bsp.md` (off-grid coords cause BSP
  holes) to `brush snap` as the noise-cleaning tool.

## Open questions

- **Should `level doctor` also FLAG near-grid slop** (a vertex within a small band of a grid line but
  not on it), pointing at `brush snap`? (`questions/doctor-flag-near-grid-slop.md` — recommend
  deferring to a separate item; keep this one to the filter.)
