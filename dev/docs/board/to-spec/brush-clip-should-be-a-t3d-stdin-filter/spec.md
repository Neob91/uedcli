# Spec: `brush clip` as a T3D-stdin filter

## Goal

Make `brush clip` a stateless T3D filter: read a brush T3D snippet on stdin (`-`) or a saved FILE,
clip it by a world plane, write the clipped brush T3D to stdout. Clip then composes *before* the
trunk in one pipeline — `brush build cube | brush clip - --plane 96,0,0 1,0,1 --keep below |
actor add -` (a chamfered box in one pass) — matching every other geometric brush transform
(`brush build`, `intersect`/`deintersect`, the proposed `snap`). Today clip is the odd one out: a
by-name in-place trunk edit.

## Current state

- `brush clip <name> …` mutates a placed trunk actor in place: parser `parsers/brush.py:63`, handler
  `edit.py:356` (`_clip`) — resolves the name in the loaded trunk, maps the world plane into the
  actor's local frame via `rotation.world_to_local_point/normal`, clips, `validate_brush`, `src.save`.
- The clip math is **already stateless**: `clip.py` `clip_brush` / `classify_clip` / `axis_plane`
  operate on a `Brush` + a local-space plane; nothing there needs a trunk.
- Precedent for a T3D-in / T3D-out generator: `brush intersect`/`deintersect` (`edit.py:32`, `merge`)
  read a snippet via `ingest.read_t3d_input`, parse with `parse_t3d_actors`, drop builder brushes,
  emit with `emit_actor_t3d`. Their positional is `-|FILE`; empty stdin is a clean no-op; a name list
  on stdin and a non-brush member are both exit 2.
- `brush replace <name> -` (`edit.py:402`) already applies a new shape in place keeping identity.

## Design

**Replace** the by-name in-place form with the filter (recommended; owner question below), per
no-back-compat-cruft — the new spelling is the only spelling.

- `brush clip -|FILE (--axis A --offset N | --plane PX,PY,PZ NX,NY,NZ) [--keep below|above]` reads a
  brush T3D snippet and clips **every** brush actor in it by the same world plane, mapping that plane
  into each actor's own local frame from the `Location`/`Rotation`/`PrePivot` the snippet carries — so
  the filter is as rotation-aware as the deleted by-name form. Emits the clipped actor T3D to stdout.
- To clip a **placed** actor, compose with `replace`:
  `actor show X | brush clip - --plane … | brush replace X -`. `actor show` carries the actor's full
  transform, so this is the same rotation-aware result the by-name form gave.
- **SET on stdin**: accept a set; clip each brush by the one plane; all-or-nothing. Builder brushes
  are dropped (every ingest path does). A non-brush (point) actor is **refused, exit 2 naming it** —
  matching `brush intersect`'s rule that a brush verb over a T3D set refuses non-brush members rather
  than silently passing them through. (Alternative — pass point actors through unchanged — is
  rejected: it turns a `brush` verb into a general actor filter and risks a silent half-answer.)
- A plane that **misses** a brush's interior (whole brush on the kept side): emit that brush
  unchanged and note it on stderr (today's by-name form prints "did not intersect … left unchanged"
  and exits 0). A plane that **discards a brush entirely**: exit 2 naming it (the clip would remove
  the whole brush — `clip_brush` already raises here). Collect all such across the set (all-or-nothing).

### Proposed CLI surface

```
brush clip -|FILE (--axis x|y|z --offset N | --plane PX,PY,PZ NX,NY,NZ) [--keep below|above]
  -|FILE     read the brush SET as a T3D snippet on stdin (`-`) or from a saved FILE (the build →
             clip → add convention). `-` is the sole names source. Empty stdin is a clean no-op (exit 0)
  --axis     axis-aligned clip plane; use with --offset
  --offset   plane offset along --axis, in world units
  --plane    general plane: a world point on it (PX,PY,PZ) + its normal (NX,NY,NZ); need not be unit
  --keep     keep the half below the plane (opposite the normal — DEFAULT) or above (the normal side)
```

## Edge cases & errors

- Both `--axis/--offset` and `--plane`, or neither → exit 2 (as today).
- Empty stdin → exit 0, no output.
- Stdin holds a newline name list, not T3D → exit 2 (as `intersect`: reads a T3D snippet, not a name
  list).
- Non-brush actor in the set → exit 2 naming it.
- Plane discards a whole brush → exit 2 naming it; plane misses a brush interior → pass it through
  unchanged + stderr note.
- Degenerate result → `validate_brush` raises → exit 2 naming the actor.

## Tests

- `brush build cube | brush clip - --plane 96,0,0 1,0,1 --keep below | actor add -` → the 7-face
  chamfered box in one pipe.
- Rotated input: `actor show <rotated-brush> | brush clip - …` equals the world-space result the
  deleted by-name path produced (parity golden).
- Empty stdin exit 0; name-list stdin exit 2; non-brush member exit 2; whole-brush discard exit 2;
  interior miss → passthrough + note; a 2-brush set clipped by one plane.
- `brush build cube | brush clip - … | brush replace WALL -` round-trips (the placed-actor recipe).

## Docs to update in the same change

- `docs/usage.md`: clip becomes a filter (`brush clip -|FILE …`); delete the by-name row and its
  rotation-aware note's by-name framing.
- `docs/leveldesign/general/recipes/shapes/` — `chamfered-box.md`, `l-ledge.md`, `moulded-cornice.md`,
  and the others that show the two-step add-then-clip-by-name form → the one-pipe filter form.

## Open questions

- **Replace the by-name in-place clip, or keep both forms?**
  (`questions/keep-by-name-clip-or-replace.md` — recommend replace.)
