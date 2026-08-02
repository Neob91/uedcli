# Plan — `stash capture -` (bare stdin T3D)

Build in a feature worktree (`worktrees.md`), one squash-merge commit. Ergonomics + spelling change:
stdin capture already works as `stash capture --from-t3d -`; this adds the bare `-` source and drops
`--from-t3d -` (no dual spelling).

## Slice 1 — parser + source resolution

- Parser (`uedcli/cli/parsers/stash.py:14-23`): the leading-`-` token rides the existing `names`
  positional (`nargs="*"`) — a single `-` is a valid positional value in argparse (same as
  `actor add`'s `file`, `actor.py:264`, and `brush intersect`'s `set`, `brush.py:305`), and actor
  Names are never `-`, so a leading `-` is unambiguous. Update the `names` and `--from-t3d` help to
  the new shape: a leading `-` = read the T3D SET from stdin as the source; `--from-t3d` is
  **files-only** (drop "or - for a stdin stream").
- Dispatch (`uedcli/cli/commands/stash.py:100-129`): before the source branch, split the leading `-`:
  - `stdin_source = bool(args.names) and args.names[0] == "-"`; if so, `subset = args.names[1:]`,
    else `subset = args.names`.
  - Mutual-exclusion guards, mirroring the existing `--tree`+`--from-t3d` guard (`stash.py:105-107`)
    — each names a source, exit 2 (`CommandError`):
    - `-` with `--from-t3d` → exit 2.
    - `-` with `--tree` → exit 2.
  - Drop `--from-t3d -` (no back-compat): `read_t3d_files` still honors `-` for `actor preview`
    (`actor/preview.py:52`), so the removal is **stash-local** — reject a `-` value in
    `args.from_t3d` here (`CommandError` naming it: use bare `-` instead), not by editing
    `ingest.read_t3d_files`.
- Source read:
  - `stdin_source` → `text = ingest.read_t3d_input("-")` (`ingest.py:21`).
  - else `--from-t3d FILE…` → `text = ingest.read_t3d_files(args.from_t3d)` (files only now).
  - else trunk (`--tree`/`$UEDCLI_LEVEL`), unchanged (`stash.py:114-126`).
  - `validate = lambda actors: ingest.validate_ingest_actors(actors, args)` for both external
    sources (stdin and files), as today for `--from-t3d` (`stash.py:113`).
  - Pass `subset` (not `args.names`) as the subset filter to `_capture_from_t3d` (`stash.py:127`).
- Empty stdin → the existing `capture source has no actors` exit 2 (`stash.py:69-70`), matching
  `actor add -` (`edit.py:375-376`) — no new code, the empty stream parses to zero actors.

## Slice 2 — tests (via `bin/test`)

- `stash capture -` from a piped snippet stores all actors; stdout prints the id.
- `stash capture - Name1` subsets the stream to `Name1`.
- `stash deintersect … | stash capture - --id baked` round-trips (or the nearest available producer).
- `-` + `--from-t3d FILE` → exit 2; `-` + `--tree KIND/NAME` → exit 2.
- `stash capture --from-t3d -` (the removed spelling) → exit 2 naming `-` (pins the removal so it
  can't creep back as a dual spelling).
- Empty stdin → exit 2 `capture source has no actors`, no traceback (regression for the "never a bare
  exception" rule).
- Duplicate Names in the stream → uniquified, none dropped (existing behavior, `stash.py:71-77`).

## Slice 3 — docs

- `docs/usage.md` (`stash capture`): bare `- [names…]` stdin-T3D source; `-` mutually exclusive with
  `--from-t3d`/`--tree`; `--from-t3d` files-only; empty stdin exits 2.

## Verify (before review)

- `bin/test` green; formatter/linter/type-checker clean on touched files.
- Exercise: `brush build cube | stash capture - --id c` then `stash show c` round-trips; confirm
  `stash capture --from-t3d -` now errors and `stash capture -` works.
- One subagent reviews `git diff base...HEAD`; fix confirmed findings; move item to `done/`.
