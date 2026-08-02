# Spec — `brush poly move`

## Goal

`brush poly move` — translate whole faces: move every vertex of a selected poly at once, by a world
delta (`--by`). Model-side, no editor. Builds directly on `vertex.move_vertices`.

Semantics (fixed by the board overview): a face is moved by moving its **welded corners** — every
copy of each corner across the whole brush moves together. This keeps the brush watertight and
**deforms the adjacent faces** that share those corners. Moving only that face's own vertex copies
would open the solid and is illegal (`vertex.py:11-16` forbids add/delete for exactly this reason).
`validate_brush` must pass, so most non-axis-aligned moves are rejected — document it.

**DECIDED (owner, 2026-08-02): v1 ships `--by DX,DY,DZ` only.** No `--to` (move-centroid-to-point):
it is deferred to a later change. `--by` is the core, unambiguous operation; `--to` is pure sugar
(`delta = target − centroid`) and picking the centroid as the anchor is a commitment nobody has
asked for yet.

## Current state

- No `move` sub-verb. `brush poly` has `list/set/pan/rotate/scale/find/align`
  (`cli/commands/brush/poly.py:54-70`; the subparsers at `cli/parsers/brush.py:400-541`).
- `vertex.move_vertices(brush, selectors, *, to, by)` (`vertex.py:55-98`) moves welded corners
  selected by local coordinate, validates the result (`vertex.py:97`), returns a new brush. Exactly
  the primitive `poly move` needs; call it with `by=` only.
- `surface.resolve_targets(level, targets)` (`surface.py:108-134`) resolves `BRUSH:SELECTOR` tokens
  to a deduped, ordered `(brush, poly_index)` list — the multi-actor grammar `set/pan/rotate/scale`
  already share. Raises `ValueError` naming the first offender (unknown/non-brush/out-of-range).
- `rotation.world_to_local_delta(actor, world_delta)` (`rotation.py:385`) maps a world `--by` into
  the brush's local frame (rotation/PrePivot/scale-aware); `brush vertex move` uses it the same way
  (`cli/commands/brush/vertex.py:85`).
- `_POLY_TARGETS_HELP` and `_print_poly_selectors` (`cli/parsers/brush.py:416-421`,
  `cli/commands/brush/poly.py:20-39`) — the shared per-face target grammar and stdout contract.

## Design — CLI surface

    brush poly move BRUSH:SELECTOR… --by DX,DY,DZ [--tree …]

Same `BRUSH:SELECTOR` grammar as `set`/`pan`/`rotate`/`scale` (multi-actor; `-` reads `BRUSH:idx`
lines from `brush poly find`). Prints the touched `BRUSH:idx` selectors via `_print_poly_selectors`.

Help lines:

    (verb)   translate whole faces — move every vertex of each selected face at once, model-side
    targets  <_POLY_TARGETS_HELP>
    --by     world delta DX,DY,DZ added to every vertex of each selected face. Moves the brush's
             WELDED corners, so a corner shared with an UNSELECTED face moves too and that neighbour
             deforms. Most non-axis-aligned moves push a neighbour non-planar and are REJECTED
             (exit 2); moving a face along its own normal is the safe case

`--by` is a plain required flag (not a one-member mutually-exclusive group — that only degrades the
error text; mirror the `rotate`/`scale` note at `cli/parsers/brush.py:479-482`). The group comes
back with `--to`.

Mechanism, per brush in the resolved set: collect the union of the selected polys' corner coords
(cleaned, welded), map the world `--by` through `rotation.world_to_local_delta(actor, args.by)` for
that brush, then `vertex.move_vertices(brush, corner_coords, by=local_delta)`. Each brush is resolved
and welded independently, so the delta is mapped per-actor.

**DEDUPE the collected corners before the call.** `move_vertices` rejects a repeated selector
(`vertex.py:84-85`, `duplicate --at selector for corner …`), and two selected adjacent faces of one
brush share a corner, so the naive concatenation lists that corner twice and would exit 2 on a valid
move. Deduplicate on the cleaned coord key (the `_clean3` form `move_vertices` compares) so each
welded corner is passed exactly once.

## Edge cases & errors

- Non-brush actor in a target / unknown brush / poly index out of range / bad index → exit 2 naming
  the brush (existing `resolve_targets`/`resolve_polys` messages).
- Result degenerate or non-planar → `validate_brush` in `move_vertices` raises `GeometryError` → exit
  2. This is the "most non-axis moves rejected" path.
- Empty stdin (`-`) / no targets → clean no-op, exit 0 (mirror the other poly mutators,
  `cli/commands/brush/poly.py:92-93`).
- `PrePivot`/`Rotation`/`Location` untouched — only vertices change (like `vertex move`).
- A corner shared with a face in a DIFFERENT brush does not move — each brush is resolved and welded
  independently (welding is per-brush). Only same-brush neighbours deform. State this.

## Tests

New `test_poly_move.py` (or extend `test_surface.py`):

- Cube top face `--by 0,0,64` → valid, watertight (weld count preserved), top raised, sides taller.
- Cube face `--by 32,0,0` (in-plane, non-normal) → side faces non-planar → exit 2.
- Out-of-range poly index → exit 2 naming the brush; non-brush actor → exit 2.
- Multi-actor `--by` across two brushes applies per brush.
- Two selected adjacent faces of one brush that share a corner `--by 0,0,64` → the shared corner is
  moved once (dedupe), no `duplicate --at selector` error, watertight result.
- `brush poly find --facing +Z | brush poly move - --by 0,0,64` end-to-end.
- Rotated/PrePivot brush: world `--by` maps through `world_to_local_delta` correctly.

## Docs to update in the same change

- `docs/usage.md`: the new `brush poly move BRUSH:SELECTOR… --by` verb, beside `set`/`pan`/`rotate`/
  `scale`.
