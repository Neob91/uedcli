# Spec — materialize fails loudly when a referenced package can't be loaded

## Goal

`level materialize` must never silently drop a face's `Texture=` (or an actor's `Class=`) because
the package that ref names is absent from the load set. Today an unresolved referenced package is
dropped without a word; the failure only surfaces as an opaque H3 post-verify mismatch far
downstream, and under `--no-verify` it ships a wrong map with no signal at all. This is a
conventions-alignment fix (`CLAUDE.md`: "a command that can't fully satisfy a request exits 2 naming
the offending value, never a partial result").

## Current state

- `apply._level_referenced_packages(level)` (`uedcli/apply.py:49`) already computes the exact set the
  level references — each actor's qualified `Package.Class` and each brush poly's `Package[.Group].Name`
  texture ref.
- `run_materialize` (`uedcli/apply.py:286`) passes that set to `_materialize` → `packages.ensure_load`.
- `packages.obj_load_entries` (`uedcli/packages.py:94`) **silently omits an unresolved package** — its
  docstring says "`missing_packages`'s fail-fast already gates materialize before this runs", but that
  gate no longer exists on the live path.
- `packages.missing_packages` (`uedcli/packages.py:84`) and `packages.ensure_load_message`
  (`uedcli/packages.py:89`) are written, tested (`tests/test_packages.py:47-60`), and **called by
  nothing but the tests** — the fail-fast was dropped when materialize moved to
  `_level_referenced_packages`. So the guard is present-but-unwired.
- `config.composed_search_files` (`uedcli/config.py:450`) silently skips any search dir that fails
  `os.listdir` (`except OSError: continue`, line 463) — a dangling/nonexistent config dir contributes
  nothing, and if every dir is empty/missing the composed path resolves to 0 packages with no signal.
- `resources.composed_load_set` (`uedcli/cli/resources.py:50`) and `composed_dirs` already hard-error
  (exit 2) when there is **no games config at all**; they do not check the resolved set is non-empty
  or covers what the level references.
- Dead param: `run_materialize(packages=…)` (`uedcli/apply.py:226`) — the composed load set is passed
  in but never used in the body (the load set is re-derived from `_level_referenced_packages`). Fold
  it out as part of this change (see Open questions).

## Design

### (ii) Referenced-package fail-fast — the load-bearing half

Reinstate the existing, tested fail-fast, over the *referenced* set (not the whole composed install),
before the ephemeral editor is created — mirroring how `_level_defaults` resolves class defaults up
front so an unresolvable input costs ~0.1 s and exit 2 rather than a ~100 s build then an opaque
mismatch.

In `run_materialize`, after computing `host_search_dirs` and before `ensure_editor`:

```
referenced = _level_referenced_packages(level)
missing = packages.missing_packages(referenced, host_search_dirs)
if missing:
    return ApplyResult(rc=2, message=f"materialize failed (nothing written): "
                                     f"{packages.ensure_load_message(missing)}")
```

`_ALWAYS_LOADED` ({Engine, Core, Editor}) are substrate code always resident, so they must be excluded
from the check exactly as `obj_load_entries` excludes them — otherwise a level referencing
`Engine.Light` would false-miss. Filter `referenced` through the same `_ALWAYS_LOADED` set before
`missing_packages`.

This runs on the offline path (pure `os.listdir` over host dirs), so it is fully unit-testable with no
editor — the same seam `test_packages.py` already exercises.

`--no-verify` must **not** skip this gate. `--no-verify` disables the post-verify (the thing that today
catches the drop late); with the verify off, the silent-wrong-map is exactly the outcome. The
referenced-package gate is independent of verification and always runs.

### (i) 0-package / dangling-glob diagnostic

Two sub-cases:

- **Level references packages, composed path resolves 0 (or misses them):** fully covered by (ii) —
  every referenced package is missing, so exit 2 names the complete set. No separate code needed.
- **Level references no packages at all (bare classes, no textures), composed path is empty:** (ii)
  finds nothing missing and materialize proceeds correctly (nothing to load). A genuinely empty
  composed path is still a likely-misconfiguration worth surfacing. Options below.

**Option A (recommended): rely on (ii); add a stderr note only for the empty-composed-path smell.**
When `composed_load_set(project)` is empty, emit one stderr line
(`note: composed package search path resolved 0 packages — check the games config paths`) and
continue. The correctness guarantee is (ii); this is advisory only, and only fires when the path is
empty, so it never scrolls under normal builds.

**Option B: make an empty composed path a hard exit 2** regardless of what the level references.
Strictly conventions-pure, but it blocks the legitimate reference-free level (a pure-BSP greybox with
no textures materializes fine with 0 content packages), so it would reject correct input.

**Option C: turn a dangling config dir into a `ConfigError`** at `composed_search_files` (don't swallow
`OSError` for a configured dir that does not exist). This catches a typo'd `paths` entry at its source
for *every* verb, not just materialize — a broader change than this item, and it interacts with the
config walk-up rules. Out of scope here; file separately if wanted.

Recommend Option A. The hard guarantee lives in (ii); (i) stays a non-blocking smell so a valid
reference-free build is never rejected.

## Edge cases & errors

| Case | Behavior | Exit |
|-----------------------------------------------|---------------------------------------------------|---
| Referenced texture pkg absent from load set | exit 2, `ensure_load_message` names the complete missing set | 2 |
| Referenced class pkg absent | same gate, same message (the set is class + texture pkgs unioned) | 2 |
| Several missing | one message, complete sorted set (not just the first, unlike UCC's own abort) | 2 |
| Missing pkg + `--no-verify` | still exit 2 — the gate is verify-independent | 2 |
| Only `Engine`/`Core`/`Editor` referenced | pass (excluded, always resident) | 0 |
| Level references nothing, path non-empty | pass, silent | 0 |
| Level references nothing, path empty (Opt A) | pass, one stderr advisory line | 0 |
| No games config at all | existing `composed_load_set` hard error | 2 |

All exits are `ApplyResult(rc=2, message=…)` surfaced by `_level_materialize` to stderr — never a
traceback. The message uses the "materialize failed (nothing written)" prefix already used by the
schema-resolve and driver guards, so the "nothing was written" promise is consistent.

## Tests

- Offline `run_materialize` with a mocked editor and a `host_search_dirs` missing a referenced texture
  package → rc 2, message contains the package name; assert the editor container was **never created**
  (fail-fast is before `ensure_editor`).
- Same with `--no-verify` → still rc 2 (regression pinning that the gate is verify-independent).
- Referenced set = only `Engine`/`Core` → passes the gate.
- Reference-free level + empty composed path → rc 0 (+ the advisory line on stderr under Option A).
- `missing_packages`/`ensure_load_message` unit coverage already exists — extend to assert the
  materialize path calls them (the wiring is what was missing).

## Open questions

- (i) disposition: Option A vs B vs C — an owner fork on whether an empty/partial composed path warns
  or blocks. See `questions/zero-package-path-warn-or-fail.md`.
- The dead `run_materialize(packages=…)` parameter: recommend removing it in this change (no
  back-compat cruft). Low-risk, no owner call needed, but noted so the reviewer expects the signature
  change and the `_level_materialize` call-site edit.
