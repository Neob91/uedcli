# Plan — materialize fails loudly on a missing referenced package

Build in a feature worktree (`worktrees.md`), one squash-merge commit. Fully offline-testable (mocked
editor) — the whole gate runs before the editor is created.

## Slice 1 — referenced-package fail-fast (ii), the load-bearing half

- In `apply.run_materialize` (`apply.py:226`), after `host_search_dirs = editor_search_dirs(...)`
  (`apply.py:278`) and **before** `ensure_editor` (`apply.py:281`):
  ```
  referenced = [p for p in _level_referenced_packages(level) if p not in packages._ALWAYS_LOADED]
  missing = packages.missing_packages(referenced, host_search_dirs)
  if missing:
      return ApplyResult(rc=2, message=f"materialize failed (nothing written): "
                                       f"{packages.ensure_load_message(missing)}")
  ```
  - `_level_referenced_packages` (`apply.py:49`) already yields class + texture pkgs; filter through
    the same `_ALWAYS_LOADED` (`packages.py:18`) `obj_load_entries` uses (`packages.py:103`), so a
    level referencing `Engine.Light` does not false-miss.
  - `missing_packages`/`ensure_load_message` (`packages.py:84`, `:89`) exist and are unit-tested
    (`tests/test_packages.py:47-60`) but are called by nothing on the live path — this wires them in.
  - Gate runs **regardless of `no_verify`** — it is verify-independent; with the verify off it is the
    only thing standing between a missing package and a silently wrong map.
- Remove the dead `packages=` param from `run_materialize` (`apply.py:226`) and its call site
  (`level.py:397`) — no back-compat cruft. `_materialize` already uses
  `_level_referenced_packages(level)` directly (`apply.py:287`), so nothing else depends on it. Also
  update the `run_materialize` docstring, which still documents `packages` in detail
  (`apply.py:231-236`), so it doesn't describe a removed param.
- Tests (`tests/test_materialize*` / mocked editor, via `bin/test`):
  - `run_materialize` with `host_search_dirs` missing a referenced texture pkg → rc 2, message names
    the pkg; assert the editor container was **never created** (fail-fast is before `ensure_editor`).
  - Same with `no_verify=True` → still rc 2 (pins the gate is verify-independent).
  - Referenced set = only `Engine`/`Core` → passes the gate (excluded).
  - Several missing → one message, complete sorted set.

## Slice 2 — empty-composed-path advisory (i), Option A

- In `_level_materialize` (`level.py:378`), after `level = src.load()` (`level.py:392`): when
  `resources.composed_load_set(project)` is empty **and** the level references no loadable packages
  (`[p for p in apply._level_referenced_packages(level) if p not in packages._ALWAYS_LOADED]` is
  empty), print one advisory line to stderr and continue (rc unaffected):
  `note: composed package search path resolved 0 packages — check the games config paths`.
  - After Slice 1's gate, an empty composed path that still built means the level referenced nothing
    loadable, so the two conditions coincide; checking both keeps the message honest per the owner
    wording ("0 packages AND references no packages").
  - Non-blocking, advisory only — a reference-free greybox still materializes (rc 0).
- Tests (via `bin/test`):
  - Reference-free level + empty composed path → rc 0 with the advisory line on stderr.
  - Level referencing a present package + non-empty path → rc 0, **no** advisory line.

## Slice 3 — docs

- `docs/usage.md` (`level materialize`): note that materialize exits 2 naming every referenced
  package it cannot resolve on the package path (before any editor work), and that an empty composed
  package path prints an advisory but does not block a reference-free build. Tool-behavior only.

## Verify (before review)

- `bin/test` green; formatter/linter/type-checker clean on touched files.
- Exercise: run `level materialize` against a level referencing a package absent from the configured
  paths → confirm exit 2 naming the package and that no editor container was spawned (fast failure).
- One subagent reviews `git diff base...HEAD`; fix confirmed findings; move item to `done/`.

## Follow-on (do NOT build here)

Separate board item: make a *dangling configured paths dir* a `ConfigError` at
`config.composed_search_files` (stop swallowing `OSError`, `config.py:462-463`), tool-wide — catches
a typo'd `paths` entry at its source for every verb, not just materialize.
