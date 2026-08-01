# `level delete` / `rename` / `clone` — DRAFT spec

Thin lifecycle verbs over the trunk DIRECTORY (`maps/<name>/`), filesystem-only, git-agnostic
(`trunk-and-editor.md`: uedcli never wraps version control). Not `git mv`/`git rm`.

## Goal

Give a project a way to delete, rename, and copy a level without hand-`mv`/`rm` of `maps/<name>/`.
The probe found no verb for any of the three.

## Current state

- Levels are created (`level create`) and imported (`level import`) but never deleted, renamed, or
  copied — `cli/commands/level.py:36` routes only `list/create/import/materialize/preview/status/
  doctor`.
- A level IS just a directory: `maps/<name>/actors/<actor>/{actor.t3d, order_value[, folder]
  [, labels]}` (`terminology.md`; `t3dtree.py`). The level name is the `<name>` dir name; an actor's
  identity is its own dir name. **Nothing inside references the level name**, so a rename is a pure
  directory move and a clone a pure recursive copy — no name or rank fixup is needed (the overview's
  "name/rank fixups" is unnecessary; recorded here so it is not re-added).
- **There is no persistent "selected level" pointer to retarget.** The ambient level is the
  per-process env var `$UEDCLI_LEVEL` (`level_sources.py:348`); a child process cannot change the
  parent shell's env (`level.py:124`). So the overview's "retarget the selected pointer" is obsolete
  — the most a verb can do about the ambient level is refuse or warn.
- Clobber rule (`safety.md`): a git-tracked trunk is protected work; every create-verb refuses an
  existing destination (exit 2, naming it) and takes one explicit opt-in. Trunk writes run under a
  per-level flock at `<maps>/.locks/level-<name>.lock` (`level_sources.py:115`).
- `list_levels` (`level_sources.py:325`) marks a dir a level by an `actors/` subdir;
  `check_safe_level` (`:316`) enforces a single safe segment, no leading dot.

## Design

Three subverbs under the `level` family, resolving `maps/<name>/` via `config.project_maps_dir`.
Each takes the source lock (and, for rename/clone, the destination lock) around the fs op, so it
cannot race a concurrent trunk writer. Source/destination names go through `check_safe_level`.

### CLI surface (help= lines)

```
level rename OLD NEW            "rename a level: move maps/OLD/ -> maps/NEW/. Filesystem-only
                                 (no git); commit the move yourself. Refuses if NEW exists"
level clone SRC DST            "copy a level: recursively copy maps/SRC/ -> maps/DST/, a new
                                 independent trunk. Filesystem-only. Refuses if DST exists"
level delete NAME  [--force]   "delete a level: remove maps/NAME/ and its trunk. Refuses
                                 without --force (the trunk is authored work; recover via git if
                                 it was committed)"
```

`--force` on delete (help=): `"delete NAME even though it is authored work — there is no uedcli
undo; a committed trunk is recoverable with git checkout, uncommitted work is not"`.

(Overwrite flag on rename/clone — see Q3; shown above as hard-refuse, the recommended default.)

### Options considered

- **Delete guard (Q1).** (a) always require `--force`; (b) refuse only when the trunk has
  uncommitted git changes; (c) delete freely (git is recovery). Recommend (a): uniform, git-agnostic,
  and `safety.md`'s "refuse-and-instruct" ethos. (b) reintroduces the git coupling the item rejects.
- **Ambient-level interaction (Q2).** Deleting/renaming the level named by `$UEDCLI_LEVEL` leaves a
  stale export. Options: refuse; warn on stderr; ignore. Recommend warn — the verb cannot fix the
  env, and refusing blocks the common "delete the level I'm on" case.
- **Rename/clone destination clobber (Q3).** (a) hard-refuse an existing destination, delete-first
  (recommend — a whole authored trunk is not the rebuildable map file that earns materialize's
  `--overwrite`); (b) add `--overwrite` for tool-wide uniformity. Recommend (a).

## Edge cases & errors

- Source level does not exist → exit 2 `level not found: NAME`.
- `NEW`/`DST` already exists (an `actors/` dir with content, matching `level create`/`import`) →
  exit 2 naming it; under (a) instructs `level delete` first.
- Malformed/dotted/nested name (either arg) → exit 2 via `check_safe_level` (never touches `.locks/`).
- `level delete` without `--force` → exit 2 naming the level and `--force`.
- Deleting/renaming the `$UEDCLI_LEVEL` level → warn on stderr that the export is now stale (Q2).
- `rename OLD OLD` / `clone SRC SRC` → exit 2 (same-name no-op is a mistake, not silent success).
- Stale `<maps>/.locks/level-OLD.lock` after a rename is harmless litter in the self-ignoring dir.
- No project (`uedcli.toml`) → the usual clean `ProjectError` exit 2.
- Filesystem failure mid-op (partial copy) → exit 2 naming it; clone should copy to a temp sibling
  then `os.rename` into place so a killed clone leaves no half-level (atomic-swap, `safety.md`).

## Tests (`tests/test_level_verbs.py` / a new `test_level_lifecycle.py`)

- rename moves the dir, level list reflects it, actors/ranks/folders/labels survive verbatim.
- clone yields an independent trunk (edit the clone, source unchanged); atomic (no half-copy left).
- delete removes the dir only with `--force`; without it exits 2 and touches nothing.
- Every guard: missing source, existing destination, dotted name, same-name, no `--force`.
- Ambient-level warning fires (Q2 outcome) when the target matches `$UEDCLI_LEVEL`.
- docs: add the three verbs to `docs/usage.md` in the same change.

## Open questions

- Q1 — `level delete` guard shape (`questions/delete-guard.md`).
- Q2 — behavior when the target is the ambient `$UEDCLI_LEVEL` (`questions/ambient-level.md`).
- Q3 — rename/clone: hard-refuse vs `--overwrite` (`questions/rename-clone-overwrite.md`).
