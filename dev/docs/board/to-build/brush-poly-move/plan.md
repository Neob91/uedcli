# Plan — `brush poly move`

Build in a feature worktree (`worktrees.md`), one squash-merge commit. `--by` only (owner ruling).

## Slice 1 — model helper `surface.apply_move`

- Add `apply_move(level, targets, *, by)` to `uedcli/surface.py`, peer of `apply_pan`/`apply_rotate`
  (`surface.py:176`, `:424`). Body:
  - `pairs = resolve_targets(level, targets)` (all-or-nothing resolution, `surface.py:163`).
  - Group `pairs` by brush. For each brush, collect its selected polys' corner coords from the welded
    set and **dedupe on the cleaned coord key** — two selected adjacent faces share a corner, and
    `move_vertices` rejects a repeated selector (`vertex.py:84-85`, `duplicate --at selector`), so an
    un-deduped list would exit 2 on a valid move. Map `by` (world) → local via
    `rotation.world_to_local_delta(actor, by)`, then
    `actor.brush = vertex.move_vertices(actor.brush, coords, by=local_delta)`.
  - Return `_touched_brushes(pairs)` (`surface.py:137`).
- `move_vertices` already validates each result brush (`vertex.py:97`), so no extra `validate_brush`
  loop is needed; a degenerate/non-planar result raises `GeometryError` out of `apply_move`.
- Tests (`tests/test_surface.py` or new `tests/test_poly_move.py`, via `bin/test`):
  - Cube top face `--by 0,0,64`: watertight (weld-corner count unchanged), top +64, sides taller.
  - In-plane `--by 32,0,0` on a cube face → `GeometryError` (neighbour non-planar).
  - Rotated brush: world `--by` maps through `world_to_local_delta` (assert local delta ≠ world).
  - Multi-brush target set: each brush translated independently.
  - Two selected adjacent faces of one brush sharing a corner `--by 0,0,64`: shared corner deduped,
    no `duplicate --at selector` error, result watertight.

## Slice 2 — CLI verb + parser

- Parser: add `pmove = psub.add_parser("move", …)` in `uedcli/cli/parsers/brush.py` beside the other
  poly subverbs (near `:476`). `targets` positional (`nargs="+"`, `_POLY_TARGETS_HELP`), `--by`
  (`type=parse_coord`, `required=True`, the help block from the spec), `_tree_flag(pmove)`. Plain
  required flag, not a one-member group (mirror `:479-482`).
- Command: add `_move(args, src)` to `uedcli/cli/commands/brush/poly.py` and route it in `run`
  (`poly.py:54-70`), mirroring `_rotate` (`poly.py:134-147`): resolve targets → empty no-op exit 0 →
  `src.load()` → `surface.apply_move(level, targets, by=args.by)` inside `try/except ValueError` →
  exit 2 → `src.save(verb="poly-move", args={"targets": targets, "by": [str(c) for c in args.by]},
  …)` → `_print_poly_selectors(level, targets, touched, "moved")`.
- Tests (CLI-level, via `bin/test`):
  - Out-of-range poly index → exit 2 naming the brush; non-brush actor → exit 2.
  - Empty stdin (`brush poly move -` with empty stdin) → exit 0, no write.
  - `brush poly find --facing +Z | brush poly move - --by 0,0,64` end-to-end (stdout = touched
    `BRUSH:idx` selectors).
- Regenerate the parser-baseline fixtures with `python -m uedcli.tests.parser_baseline` and commit
  `tests/fixtures/parser_baseline/{action_tree.json,help.json,argv_corpus.json}` — any parser-surface
  change (here the new `move` sub-verb) reddens `test_action_tree_matches_baseline` /
  `test_help_screens_match_baseline` (`test_parser_baseline.py`) otherwise.

## Slice 3 — docs

- `docs/usage.md`: document `brush poly move BRUSH:SELECTOR… --by DX,DY,DZ`, beside `set`/`pan`/
  `rotate`/`scale`. Note it deforms shared neighbours and rejects most non-axis moves (exit 2).

## Verify (before review)

- `bin/test` green; formatter/linter/type-checker clean on touched files.
- Exercise: build a cube (`brush build cube`), `brush poly find --facing +Z | brush poly move -
  --by 0,0,64`, confirm stdout selectors + a raised top via `brush vertex list`.
- One subagent reviews `git diff base...HEAD`; fix confirmed findings; move item to `done/`.
