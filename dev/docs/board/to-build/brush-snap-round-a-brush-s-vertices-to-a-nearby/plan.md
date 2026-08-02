# Plan — `brush snap`

Build in a feature worktree (`worktrees.md`), one squash-merge commit. Filter only — the `level
doctor` tie-in is a separate item (owner ruling).

## Slice 1 — model-side snap (pure, testable)

- New `uedcli/snap.py`: `snap_brush(brush, *, grid: Decimal, tolerance: Decimal) -> Brush` (peer of
  `vertex.py`/`clip.py`). `grid`/`tolerance` are **`Decimal`, not `float`** — brush vertices are
  `Decimal` (`vertex._dec`, `vertex.py:40-41`), so an exact/idempotent snap needs Decimal arithmetic
  throughout; a float grid reintroduces the binary-float noise the verb removes. For each poly, each
  vertex, each axis component `c` (as `Decimal`): `g = grid * floor(c/grid + 0.5)`; if
  `abs(c - g) <= tolerance` set the component to `g`, else keep `c`. Per-axis, per-vertex independent.
  - Round half toward +∞ via `floor(x + 0.5)`, matching the deliberate non-banker's rule in
    `cli/commands/brush/build.py:124-134` (do **not** use `round()`).
  - Copies of a corner get the identical rule, so near-grid drifted copies snap to the same `g` —
    re-weld is a consequence, not extra code.
  - `deepcopy` the brush, rewrite vertices, `geometry.validate_brush(result)` (raises
    `GeometryError` if a snapped face goes non-planar/degenerate), return the new brush. Mirror
    `vertex.move_vertices`' deepcopy→mutate→validate shape (`vertex.py:93-98`).
- Tests (`tests/test_snap.py`, via `bin/test`):
  - Cube with `+1e-4` noise on integer corners, `grid=1 tolerance=0.01` → exact integer vertices.
  - 45° slant vertex, one axis genuinely off-grid by `> tolerance` → that axis preserved, near-grid
    axes snapped (per-axis independence).
  - `grid=16` snaps `15.9997 → 16`, leaves a real `8.5` (7.5 from 16, `> tolerance`) in place.
  - Re-weld: corner copies at `32.00003` / `31.99997` both land on `32` (assert weld count drops).
  - Round-half determinism at a component exactly `grid/2` from a line, within tolerance.
  - Snapped face non-planar → `GeometryError`.
  - Idempotent: a brush already on-grid is returned unchanged.

## Slice 2 — CLI verb `brush snap -|FILE --grid N --tolerance T`

- Parser: new `bsub.add_parser("snap", …)` in `uedcli/cli/parsers/brush.py`, beside
  `intersect`/`deintersect` (`:362-375`). `set` positional (`-|FILE`, the shared help wording),
  `--grid` (required, no default) and `--tolerance` (required, no default), with the spec's help
  text. Both required so no silent default grid/tolerance guess (conventions.md). **Parse both as
  `Decimal`, not `float`** (e.g. `type=Decimal`/a Decimal-parsing helper), so the snap stays exact and
  idempotent against the Decimal vertices.
- Command: `snap(args)` in `uedcli/cli/commands/brush/edit.py`, modelled on `merge` (`edit.py:32`):
  - `text = ingest.read_t3d_input(args.set)`; empty/whitespace stdin → return 0 (no-op), like
    `edit.py:88-90`.
  - `actors = [a for a in parse_t3d_actors(text) if not is_builder_brush(a)]`; a name-list stdin (no
    brush actors) → exit 2 with the same "reads a T3D SNIPPET, not a NAME list" message as
    `edit.py:100-104`.
  - Validate params before mutating: `--grid <= 0`/non-finite → exit 2 naming it; `--tolerance < 0`
    → exit 2; `--tolerance >= grid/2` → stderr note "snaps every component to a grid line" and
    continue (owner-asked, conventions.md "a flag that cannot act is an error" does not apply — it
    acts, just widely).
  - A non-brush (point) member → exit 2 naming it (a brush snap needs a PolyList); collect **all**
    offenders across the set (all-or-nothing), mirror the batch rule in conventions.md. Movers carry
    a PolyList → snapped.
  - Snap each brush via `snap.snap_brush`; collect `GeometryError`s across the set and report the
    complete set (all-or-nothing) → exit 2; nothing emitted on any failure.
  - Emit every snapped actor's T3D to stdout in input order (`emit_actor_t3d` per actor) — a SET in,
    the same SET out, so it pipes to `actor add -` / `brush replace`.
- Tests (CLI-level, via `bin/test`):
  - Piped noisy cube → snapped T3D on stdout; round-trips through `actor add -`.
  - Non-brush member → exit 2 naming it; empty stdin → exit 0; name-list stdin → exit 2.
  - `--grid 0` → exit 2; missing `--grid`/`--tolerance` → argparse exit 2.
  - Face-non-planar snap → exit 2, no stdout.
- Regenerate the parser-baseline fixtures with `python -m uedcli.tests.parser_baseline` and commit
  `tests/fixtures/parser_baseline/{action_tree.json,help.json,argv_corpus.json}` — any parser-surface
  change (here the new `snap` verb) reddens `test_action_tree_matches_baseline` /
  `test_help_screens_match_baseline` (`test_parser_baseline.py`) otherwise.

## Slice 3 — docs

- `docs/usage.md`: the `brush snap -|FILE --grid --tolerance` filter, beside `clip`/`intersect`.
- `docs/leveldesign/general/geometry-and-bsp.md`: cross-reference `brush snap` as the tool that
  cleans near-grid float noise (off-grid coords cause BSP holes) — rephrasing/tool-behavior only, no
  new craft claim needing owner sign-off.

## Verify (before review)

- `bin/test` green; formatter/linter/type-checker clean on touched files.
- Exercise on a real noisy brush (e.g. a WanChai import) end-to-end: `... | brush snap - --grid 1
  --tolerance 0.01 | actor add -`, confirm the vertices land on-grid via `brush vertex list`.
- One subagent reviews `git diff base...HEAD`; fix confirmed findings; move item to `done/`.
