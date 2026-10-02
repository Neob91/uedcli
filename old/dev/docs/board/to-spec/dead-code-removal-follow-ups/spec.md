# Spec — dead-code removal follow-ups (from the 2026-07-19 store-deletion)

Two independent, mechanical deletions. No back-compat concerns (uedcli is unreleased).

## (a) Drop `apply_set`'s unused `packages` param

The monolith `dispatch._apply_set` is now `cli/placement.py:apply_set` (`packages: list[str]`
positional). Its own docstring says the trunk has no package manifest so "`packages` is not recorded"
— the param is never read.

- `uedcli/cli/placement.py:22` — remove the `packages` positional from the signature (and the
  docstring line that explains why it is ignored).
- `uedcli/cli/commands/prefab.py:80` — drop the `packages` argument; destructure `read_or_exit(...)`
  at line 75 to `_pkgs` (like the other prefab sub-verbs).
- `uedcli/cli/commands/stash.py:179` — drop the `pkgs` argument; destructure `reg.read_stash(...)` at
  line 178 to `_pkgs`.

Leave `read_or_exit` / `read_stash` returning their 5-tuple: `packages` is still read by other
sub-verbs (stash promote/export, stash.py:194–197).

## (b) Stale-prose sweep

`export_and_qualify` no longer exists (no `def`, no callers), yet is named in prose:

- `uedcli/packages.py:32`, `:175`; `uedcli/stub.py:330`; `uedcli/apply.py:88`; `uedcli/driver.py:510`
  — comments/docstrings.
- `dev/docs/architecture.md:266`, `:1442`, `:2643` — needs owner approval (it is under `dev/docs/`,
  not the board); propose the exact edits and wait.
- Tests: `uedcli/tests/test_packages.py:83`, `uedcli/tests/test_driver.py:603` — comment references
  only.

The item also cited a `dispatch.py` "no editor_lock" comment referencing a deleted helper — that
comment is already gone (not found in the current `cli/dispatch.py`); nothing to do.

Prose only, no live code — but the `architecture.md` edits need the owner's yes before landing.

## Test

None new — existing suite must stay green after (a). Run `bin/test`.

## Open questions

None (the `architecture.md` wording goes through normal owner approval, not a board question).
