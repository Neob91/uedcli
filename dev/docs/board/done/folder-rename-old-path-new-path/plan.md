# Plan — `actor folder rename OLD NEW`

Build in a worktree (`andrzej/p3/actor-folder-rename`). One merged commit. Model-side; no editor.
Home is `actor folder rename` (not a top-level `folder` family — `direction/organization.md`).

## Slice 1 — parser

In `uedcli/cli/parsers/actor.py`, add a `rename` sub-parser under `fsub` (the folder subparsers,
`actor.py:167`), beside `set`/`unset`/`get`:
- two positionals `old` (metavar `OLD-PATH`), `new` (metavar `NEW-PATH`), no `-`/stdin (the set is
  the path, not a name list), help per spec.
- `_tree_flag(frn)` for parity (guard already rejects stash/prefab).

Same slice, update the `folder` subparser help at `actor.py:166` — "Sub-verbs: set / unset / get" →
"… set / unset / get / rename" (no-back-compat: the help must not lag the surface).

## Slice 2 — handler

In `uedcli/cli/commands/actor/folder.py`, `run` dispatches on `args.foldersub`. Add a `rename` branch
**before** the `resolve_target_names(args.names)` / empty-stdin no-op path (`folder.py:26-28`) —
`rename` has no `args.names`, its set comes from `old`. The branch:

1. `validate_folder_path(old)` and `validate_folder_path(new)` (both, before any write; a `ValueError`
   → `CommandError` → exit 2, mirroring `folder.py:31-33`).
2. `level = src.load()`; single pass over `level.actors.items()` per the spec algorithm
   (case-insensitive `old` match; `f == old` → `new`; `f startswith old + "."` → `new + f[len(old):]`,
   preserving the tail's authored case).
3. `if not touched: raise CommandError(f"no actor is filed under folder {old!r}")` — exit 2 (owner,
   2026-08-02), no save, no stdout.
4. Else `src.save(verb="folder", …, touched=touched)`, echo touched Names to stdout, `renamed OLD →
   NEW on N actor(s)` to stderr (producer contract, mirrors `folder.py:54-58`).

Routing: `routes.py:42-43` already sends `args.sub == "folder"` to `folder.run`; `routes.py:65-66`
already rejects `--tree stash|prefab` for `sub == "folder"` unconditionally, so `rename` is covered
with no route change.

## Slice 3 — tests

New cases in `uedcli/tests/test_folders.py`:
- fixture at `castle.tower`, `castle.tower.roof`, unrelated `barn`: `rename castle.tower keep.spire`
  → first two become `keep.spire`/`keep.spire.roof`, `barn` untouched, the two names to stdout.
- segment-boundary safety: `castle.towerhouse` NOT moved by `rename castle.tower …`.
- case-insensitive `old`; `new` stored as authored.
- nest-into-self (`a` → `a.b`) rewrites one pass as specified.
- bad `old`/`new` grammar → exit 2, no traceback.
- **`old` matching nothing → exit 2 naming `old`, no mutation, empty stdout** (pins the owner ruling).
- `--tree stash` rejected.
- persists via delta save (reload shows new folders) — mirror
  `test_folder_only_change_persists_via_delta_write`.
- Regenerate the parser-baseline fixtures with `python -m uedcli.tests.parser_baseline` and commit
  `tests/fixtures/parser_baseline/{action_tree.json,help.json,argv_corpus.json}` — any parser-surface
  change (here the new `rename` sub-parser) reddens `test_action_tree_matches_baseline` /
  `test_help_screens_match_baseline` (`test_parser_baseline.py`) otherwise.

## Slice 4 — docs

Add `actor folder rename <old> <new>` in three places that list the folder verbs, all currently
`set`/`unset` only:
- the Folders "Manage" bullet (`usage.md:341`);
- the command-table row (`usage.md:413`, currently `actor folder set/unset`);
- the chainable-producer verb list (`usage.md:44`, currently `folder set|unset`).

## Verify

`bin/test` green; formatter/linter/type-checker on touched files. Exercise on a fixture level: a
real rename, then `rename bogus.path x` → exit 2 naming `bogus.path`.
