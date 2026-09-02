# Plan: `brush clip` as a T3D-stdin filter

Build in a feature worktree (`andrzej/p2/brush-clip-filter`), one squash-merged commit. The clip
math (`clip.py` `clip_brush`/`classify_clip`/`axis_plane`) is already stateless and unchanged; this
moves clip from a by-name trunk edit to a T3D-in/T3D-out generator and deletes the old form.

## Slice 1 — the filter handler

- Replace `edit._clip(args, src)` (`edit.py:356`) with a stateless `clip(args)` in the
  `brush intersect`/`deintersect` mould (`edit.merge`, `edit.py:32`):
  - `ingest.read_t3d_input(args.set)`; empty/whitespace stdin → `return 0` (clean no-op).
  - `parse_t3d_actors(text)`, drop builder brushes (`is_builder_brush`) as every ingest path does.
  - A **point** (non-brush) actor in the set → collect, exit 2 naming it (matches `merge`'s
    non-brush refusal; all-or-nothing across the set).
  - For each brush actor: map the world plane into that actor's local frame with
    `rotation.world_to_local_point`/`world_to_local_normal` (the by-name form's exact math,
    `edit.py:381-382`), `classify_clip`; a `"whole"` classify (plane misses the interior) → emit the
    brush unchanged + a stderr note; otherwise `clip_brush` then `validate_brush`. A plane that
    discards the whole brush → `clip_brush` raises `GeometryError` (`clip.py:163`) → collect, exit 2
    naming the actor.
  - Emit clipped actors to stdout via `emit_actor_t3d`.
  - Plane-argument validation (`--plane` xor `--axis`+`--offset`, else exit 2) stays as in `_clip`.
- No `src.load()`/`src.save()` — the filter touches no trunk.
- Delete the two remaining `clip` references that outlive `_clip`:
  - the `if args.sub == "clip": return _clip(args, src)` dispatch branch in `edit.run`
    (`edit.py:186-187`);
  - `clip` from the module docstring listing the source-consuming verbs (`edit.py:1-9`).

## Slice 2 — parser + route

- `cli/parsers/brush.py:63-74`: drop the `name` positional; add the `-|FILE` positional (`dest="set"`,
  the `merge`/intersect spelling) and keep `--axis`/`--offset`/`--plane`/`--keep`. Remove `_tree_flag`
  (a filter reads no trunk). Help per spec §"Proposed CLI surface".
- `routes.py:34`: give `clip` its **own** stateless route, `return edit.clip(args)`, alongside the
  `intersect`/`deintersect` branch (which routes to `edit.merge`, not `edit.clip`) and, like it,
  **before** `resolve_level_source`. Remove `clip` from the source-consuming group at `routes.py:41`.

Tests (`tests/test_cli.py`/`test_brush_merge.py` neighbours, new `test_brush_clip.py`):
- `brush build cube | brush clip - --plane 96,0,0 1,0,1 --keep below | actor add -` → the 7-face
  chamfered box in one pipe.
- Rotated input: `actor show <rotated-brush> | brush clip - …` == the world-space result the deleted
  by-name path produced (capture a parity golden from the current code before deleting it).
- Empty stdin → exit 0, no output. Name-list stdin → exit 2. Non-brush member → exit 2 naming it.
- Whole-brush discard → exit 2 naming the actor; interior miss → passthrough + stderr note.
- 2-brush set clipped by one plane; degenerate result → `validate_brush` → exit 2 naming the actor.
- Both/neither of `--plane` and `--axis/--offset` → exit 2.
- Regenerate the parser-baseline fixtures with `python -m uedcli.tests.parser_baseline` and commit
  `tests/fixtures/parser_baseline/{action_tree.json,help.json,argv_corpus.json}` — any parser-surface
  change (here the positional + route change) reddens `test_action_tree_matches_baseline` /
  `test_help_screens_match_baseline` (`test_parser_baseline.py`) otherwise.
- Confirm no test still exercises `brush clip <name>` in-place; delete/convert any that do.

## Slice 3 — user docs (same change)

- `docs/usage.md:500`: change the `brush clip <name> …` table row to `brush clip -|FILE …`; update the
  `:509` "world-space plane" note and the `:525` rotation-aware note to the filter framing (drop the
  by-name wording; the placed-actor path is now `actor show X | brush clip - … | brush replace X -`).
  Check `:640`/`:745` references to `brush clip`.
- `docs/leveldesign/general/recipes/shapes/`: convert the worked two-step examples in
  `chamfered-box.md` (`:24`), `add-subtract-twin.md` (`:20`), `triangular-wedge.md` (`:20`),
  `ring-cornice.md` (`:18-19`) to the one-pipe `brush build … | brush clip - … | actor add -` form,
  and fix the cross-references in `l-ledge.md` (`:39`), `moulded-cornice.md` (`:45`), `README.md`
  (`:11`, `:25`). Tool-behavior documentation → no owner approval needed.

## Verify

- `bin/test` green; formatter/linter/type-checker on touched files; read own diff.
- Exercise both flows live: the one-pipe chamfered box, and `actor show WALL | brush clip - … |
  brush replace WALL -` on a placed rotated brush (result matches a pre-change by-name capture).
- One subagent reviews `git diff base...HEAD` (must read `dev/docs/direction/generators.md`,
  `dev/docs/direction/conventions.md`, `dev/docs/unrealed/t3d.md`, `CLAUDE.md`); fix confirmed
  findings; re-test.
- `git mv` to `done/`, cut `overview.md` to one line, squash-merge.
