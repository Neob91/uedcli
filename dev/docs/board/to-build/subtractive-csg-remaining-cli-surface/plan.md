# Plan: subtractive CSG — verify + document (no new surface)

No code change. The owner ruled out `brush find`/`brush list` and a `--csg` flag; CSG-type discovery
already works on `actor find --prop CsgOper=…` (verified live 2026-08-02, spec §Decisions). This item
is a doc note plus a pinning test, then close. Build in a feature worktree
(`andrzej/p3/csg-discovery-doc`), one squash-merged commit.

## Slice 1 — pinning test

- Add a test (`tests/test_find_compose.py`, or `test_cli.py` beside the other `--prop` cases) that
  builds a trunk with a `CSG_Subtract` cube, a `CSG_Add` cube, and a `LevelInfo`, resolved against the
  game `.u`, and asserts:
  - `actor find --prop CsgOper=CSG_Subtract` → the subtractive name only, exit 0.
  - `actor find --prop CsgOper=CSG_Add` → the additive name only, exit 0.
  - `actor find --kind brush --prop CsgOper=CSG_Subtract` → the subtractive only (ANDs).
  - `actor find --prop CsgOper=CSG_Bogus` → exit 2.
  - Mark it integration if the offline suite carries no class schema (the `--prop` effective match
    needs the `.u`); mirror how existing schema-dependent `--prop` tests gate themselves.
- This is the regression that keeps the documented "discover CSG type via `--prop CsgOper=`" workflow
  from rotting.

## Slice 2 — user docs

- `docs/usage.md` / `docs/leveldesign/`: add a short note that brush/CSG-type discovery is
  `actor find --kind brush [--prop CsgOper=CSG_Add|CSG_Subtract]` (no `brush find`/`brush list`, no
  `--csg` flag); CSG-set authoring is `brush intersect`/`brush deintersect`; CSG reorder is
  `actor order`. Place it near the existing `actor find`/`brush` coverage. Tool-behavior
  documentation → no owner approval needed. Grep for any doc implying a missing "select subtractive"
  verb and fix it.

## Slice 3 — spin off the `--solidity` spike

- File a separate `to-spike` board item: live-confirm that a `brush intersect/deintersect --solidity`
  build's collision matches the faithful per-face rule. Not built here.

## Verify

- `bin/test -k "find or prop or csg"` green; formatter/linter on touched files.
- One subagent reviews `git diff base...HEAD` (must read `dev/docs/direction/conventions.md`,
  `dev/docs/direction/generators.md`, `CLAUDE.md`); fix confirmed findings.
- `git mv` the item straight to `done/` (it never needed new code), cut `overview.md` to a one-line
  record, squash-merge.

## Note — this item may CLOSE rather than build

The verification is already done and recorded in `spec.md`. If the owner prefers, the item can be
moved to `done/` with just the doc note and no separate test slice — there is no feature to ship.
