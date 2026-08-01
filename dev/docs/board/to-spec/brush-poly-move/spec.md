# Spec — `brush poly move`

DRAFT. Surfaces the owner decision(s); do not build past an unanswered question.

## Goal

`brush poly move` — translate whole faces: move every vertex of a selected poly at once, by a world
delta (`--by`) or by moving the face centroid to a point (`--to`). Model-side, no editor. Builds
directly on `vertex.move_vertices`.

Semantics (fixed by the board overview): a face is moved by moving its **welded corners** — every
copy of each corner across the whole brush moves together. This keeps the brush watertight and
**deforms the adjacent faces** that share those corners. Moving only that face's own vertex copies
would open the solid and is illegal (`vertex.py` forbids add/delete for exactly this reason).
`validate_brush` must pass, so most non-axis-aligned moves are rejected — document it.

## Current state

- No `move` sub-verb. `brush poly` has `list/set/pan/rotate/scale/find/align`
  (`cli/commands/brush/poly.py:54-70`, `cli/parsers/brush.py:400-541`).
- `vertex.move_vertices(brush, selectors, *, to, by)` (`vertex.py:55-98`) moves welded corners
  selected by local coordinate, validates the result, returns a new brush. Exactly the primitive
  `poly move` needs.
- `surface.resolve_targets(level, targets)` (`surface.py:108-134`) resolves `BRUSH:SELECTOR` tokens
  to a deduped, ordered `(brush, poly_index)` list — the multi-actor grammar `set/pan/rotate/scale`
  already share.
- `rotation.world_to_local_point/_delta` (`vertex.py:75-81`) map a world `--at`/`--by` into the
  brush's local frame (rotation/PrePivot-aware).
- `_POLY_TARGETS_HELP` and `_print_poly_selectors` (`cli/parsers/brush.py:416-421`,
  `cli/commands/brush/poly.py:20-39`) — the shared per-face target grammar and stdout contract.

## Design — CLI surface

    brush poly move BRUSH:SELECTOR… (--by DX,DY,DZ | --to X,Y,Z) [--tree …]

Same `BRUSH:SELECTOR` grammar as `set`/`pan`/`rotate`/`scale` (multi-actor; `-` reads `BRUSH:idx`
lines from `brush poly find`). Prints the touched `BRUSH:idx` selectors via `_print_poly_selectors`.

Help lines:

    (verb)   translate whole faces — move every vertex of each selected face at once, model-side
    targets  <_POLY_TARGETS_HELP>
    --by     world delta DX,DY,DZ added to every vertex of each selected face. Moves the brush's
             WELDED corners, so a corner shared with an UNSELECTED face moves too and that neighbour
             deforms. Most non-axis-aligned moves push a neighbour non-planar and are REJECTED
             (exit 2); moving a face along its own normal is the safe case
    --to     move the selected face's CENTROID to this world point (ONE selector only — several
             faces have no single centroid). Sugar for --by (target − centroid)

Mechanism, per brush in the resolved set: collect the union of the selected polys' corner coords
(cleaned, welded), then `vertex.move_vertices(brush, corner_coords, by=local_delta)`. `--to` computes
`delta = target − centroid` for the single selected face, then routes through the same `--by` path.

Recommendation: ship `--by` and `--to` together; `--to` targets the centroid and takes a single
selector, mirroring `brush vertex move --to`. See the question.

## Edge cases & errors

- Non-brush actor in a target → `resolve_targets`/`resolve_polys` raise `ValueError` → exit 2 naming
  the brush.
- Poly index out of range / empty selector / bad index → exit 2 naming the brush (existing
  `resolve_polys` messages).
- Result degenerate or non-planar → `validate_brush` in `move_vertices` raises `GeometryError` → exit
  2. This is the "most non-axis moves rejected" path.
- `--to` with more than one selected face (across all brushes) → exit 2 ("--to moves a single face").
- Empty stdin (`-`) / no targets → clean no-op, exit 0.
- `PrePivot`/`Rotation`/`Location` untouched — only vertices change (like `vertex move`).
- A corner shared with a face in a DIFFERENT brush does not move — each brush is resolved and welded
  independently (welding is per-brush). Only same-brush neighbours deform. State this.

## Tests

New `test_poly_move.py` (or extend `test_surface.py`):

- Cube top face `--by 0,0,64` → valid, watertight (weld count preserved), top raised, sides taller.
- Cube face `--by 32,0,0` (in-plane, non-normal) → side faces non-planar → exit 2.
- Out-of-range poly index → exit 2 naming the brush; non-brush actor → exit 2.
- `--to` on one face moves its centroid there; `--to` with two selected faces → exit 2.
- Multi-actor `--by` across two brushes applies per brush.
- `brush poly find --facing +Z | brush poly move - --by 0,0,64` end-to-end.
- Rotated/PrePivot brush: world `--by` maps through `world_to_local_delta` correctly.

## Open questions

See `questions/offer-to-centroid-in-v1.md`.
