# Spec — plain `brush build` hard-requires the games config for zero validation value

## Goal

Consider relaxing the author-time ingest gate for a *plain* `brush build` (no `--texture`, no `--prop`,
no `--mover-class`), where the gate has nothing substrate-specific to check yet still exits 2 when
`~/.uedcli/config.toml` is absent.

## Current state

- `brush build` always runs the ingest gate before emit: `cli/commands/brush/build.py:324`
  `ingest.validate_ingest_actors(actors, args)`.
- The gate (`cli/ingest.py:42`) calls `resources.package_path_or_exit(args)`
  (`cli/resources.py:250`), which exits 2 with `NO_GAMES_CONFIG` when the per-user games config is
  absent (resources.py:256).
- For a plain shape the class is the hardcoded `Engine.Brush` (via `builders.make_brush_actor`, always
  exists) and there is no texture (the per-poly texture loop is skipped when `p.texture is None`). So
  the gate can only ever pass — but still blocks the stateless generator on config it does not use.
- `--prop` is a separate config dependency anyway (`resources.class_ctx`, build.py:304), so relaxing
  the gate only helps when `--prop` is also absent.

Surfaced 2026-07-21 while exercising the preview verbs.

## The conflict (why this needs the owner)

`direction/generators.md` decides the opposite on purpose:

> "'Stateless' means no level and no session — **not 'no project'**. A generator validates that the
> classes and textures it names actually exist … so it needs a resolvable project and package path and
> exits 2 without one."

and, under Rejected: "Validating class/texture existence only at the write boundaries — the generators
are checked too, **accepting that this makes them project-dependent**."

So the board item's proposal (skip the gate / config requirement when nothing is substrate-specific)
directly contradicts a standing direction ruling. Per `CLAUDE.md` this cannot be implemented as a
chore — it is an owner decision, and `direction/generators.md` cannot be edited without a yes.

## Approach (only if approved)

When `shape` is a fixed-`Engine.Brush` build with no `--texture`, no `--prop`, no `--mover-class`, skip
`validate_ingest_actors` (nothing resolvable to validate), so `brush build cube …` runs with no games
config. Any of those flags present keeps the current gate unchanged. Update `docs/usage.md` to state
that a plain `brush build` needs no project/config.

## Test

If approved: a regression test that `brush build cube` succeeds with no `~/.uedcli/config.toml`, and
that `brush build cube --texture X` / `--prop …` / `--mover-class …` still exit 2 without it.

## Open questions

See `questions/relax-generator-project-requirement.md`.
