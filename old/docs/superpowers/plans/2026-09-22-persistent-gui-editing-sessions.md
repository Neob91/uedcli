# Persistent GUI Editing Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `uedcli serve`'s web GUI durable, per-browser-tab sessions — each with its own staged
edits and its own independently-solved geometry/lighting build, surviving a browser refresh and a
server restart, with no auto-expiry — replacing the current one-level-shared-globally model.

**Architecture:** Introduce a `sessions/<sid>/` on-disk record (metadata, staged edits, build pin)
alongside the existing shared, content-addressed caches (now restructured under `staging/blobs/` and
`build/cache/`, plus a restored per-level `build/pin/<level>/current.json`). Replace `serve/app.py`'s
single set of process-global holder-cells with a `dict[level_name, LevelContext]`, since multiple
sessions can now share one level or span several. Add an in-memory claim-token model so the same
session opened in two windows never races itself. Re-route the existing per-level REST/WS surface to
per-session.

**Tech Stack:** Python (FastAPI, the existing `uedcli/serve/` package), TypeScript/React (`web/src/`,
Vitest + React Testing Library).

**Spec:** `dev/docs/board/to-spec/persistent-gui-editing-sessions/spec.md` — this plan implements it
task-by-task; read both together. All copy/naming/behavior calls not repeated here defer to the spec.

## Global Constraints

- No back-compat shims anywhere — `uedcli` is unreleased (`direction/conventions.md`). Old
  `preview/`, `snapshots/`, `build/<level>/current.json` shapes are replaced outright, not migrated.
- Every new on-disk write under `.uedcli/` is atomic (temp file + `os.replace`), per
  `direction/safety.md`'s "every write is atomic."
- `index.json`/`staged.json`/`build.json` (session-scoped) refuse-and-instruct on a corrupt read
  (raise a named error). `build/cache/*.marshal` and `build/pin/<level>/current.json` keep the
  existing silent-degrade-to-cache-miss behavior, unchanged.
- User-facing copy says "unsaved," never "staged"; action buttons name the action ("Move an actor"),
  never the staging mechanism.
- New code defaults to Python, not Rust, per `direction/conventions.md` (nothing here needs the
  native CSG engine itself).
- Run the project's test suite via `bin/test`, never bare `pytest` (`dev/docs/rules/tests.md`).
  Frontend tests run via the existing `npm test` under `web/`.
- **Tests set up state via lower-level module functions, never a not-yet-built HTTP endpoint.** A
  task's own tests exercise ITS OWN new HTTP endpoint (where it adds one); but when a test needs
  some *other* piece of state to exist first (a session, a staged edit), it constructs that directly
  by calling the earlier task's plain Python function (`sessions.create_session(...)`,
  `staging_store.stage(...)`) — never by calling a later task's not-yet-built endpoint. This is what
  lets Task 9 (`LevelContext`) be tested before Task 12 (the session-creation *endpoint*) exists, and
  Task 11 (Rebuild) be tested before Task 13 (the `/stage` *endpoint*) exists, without either
  depending on the other out of sequence.

---

## File Structure

```
uedcli/serve/atomic_io.py          NEW — shared temp-file+os.replace helpers (text + JSON)
uedcli/serve/sessions.py           NEW — session lifecycle: index.json CRUD, list, delete
uedcli/serve/claims.py             NEW — in-memory claim-token model + per-session lock
uedcli/serve/snapshots.py          MODIFY — StagingStore re-keyed to session id; atomic writes; blob eviction
uedcli/serve/build_pin.py          MODIFY — split into session pointer + level pointer, add writers
uedcli/preview_cache.py            RENAME → uedcli/build_cache.py — restructured paths, reference-aware eviction
uedcli/preview_native.py           MODIFY — build_scene returns geom_hash/light_hash (widened tuple)
uedcli/serve/scene.py              MODIFY — _BuiltGeometry construction uses real hashes
uedcli/serve/app.py                MODIFY — LevelContext, session endpoints, claim tokens, WS, re-routed verbs
uedcli/serve/edits.py              MODIFY — session-scoped staged overlay built on a copy, not the shared Level
uedcli/config.py                   MODIFY — two new Project fields + validation
uedcli/tests/test_serve_atomic_io.py       NEW
uedcli/tests/test_serve_sessions.py        NEW
uedcli/tests/test_serve_claims.py          NEW
uedcli/tests/test_serve_snapshots.py       MODIFY (existing file, re-keyed tests)
uedcli/tests/test_build_pin.py             NEW (was untested — no writer existed before)
uedcli/tests/test_build_cache.py           NEW (renamed from any existing preview_cache tests, if present)
uedcli/tests/test_serve_app.py             MODIFY (existing file, extensive additions)
uedcli/tests/test_config.py                MODIFY (existing file, two new keys)
web/src/session/SessionContext.tsx  NEW — session id from URL, claim token, superseded handling
web/src/session/SessionDropdown.tsx NEW — replaces LevelPicker.tsx
web/src/api.ts                      MODIFY — session-scoped endpoints, claim token header
web/src/App.tsx                     MODIFY — remove level-switch machinery, wire SessionContext
web/src/reload.ts                   MODIFY — WS carries claim token, superseded message
web/src/panels/LevelPicker.tsx      DELETE
web/src/session/SessionContext.test.tsx    NEW
web/src/session/SessionDropdown.test.tsx   NEW
web/src/App.test.tsx                       MODIFY (existing file, level-switch tests replaced)
```

---

### Task 1: Atomic write helpers

**Files:**
- Create: `uedcli/serve/atomic_io.py`
- Test: `uedcli/tests/test_serve_atomic_io.py`

**Interfaces:**
- Produces: `atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None`,
  `atomic_write_json(path: Path, data: dict, *, indent: int = 2) -> None`. Every later task that
  writes a session/pin/cache file uses these instead of a bare `write_text`.

- [ ] **Step 1: Write the failing tests**

```python
import json
from pathlib import Path
from uedcli.serve.atomic_io import atomic_write_text, atomic_write_json

def test_atomic_write_text_creates_file_with_exact_content(tmp_path):
    p = tmp_path / "sub" / "f.txt"
    atomic_write_text(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello"

def test_atomic_write_text_leaves_no_tmp_file_behind(tmp_path):
    p = tmp_path / "f.txt"
    atomic_write_text(p, "x")
    leftovers = [f for f in tmp_path.iterdir() if f != p]
    assert leftovers == []

def test_atomic_write_json_round_trips(tmp_path):
    p = tmp_path / "f.json"
    atomic_write_json(p, {"a": 1, "b": [1, 2]})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": [1, 2]}

def test_atomic_write_overwrites_existing_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("old", encoding="utf-8")
    atomic_write_text(p, "new")
    assert p.read_text(encoding="utf-8") == "new"
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test -k test_serve_atomic_io`
Expected: FAIL — `ModuleNotFoundError: No module named 'uedcli.serve.atomic_io'`

- [ ] **Step 3: Implement**

```python
"""Temp-file + os.replace writes, so a crashed write never leaves a torn file on disk
(direction/safety.md, "every write is atomic")."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data: dict, *, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(data, indent=indent))
```

- [ ] **Step 4: Run to verify it passes**

Run: `bin/test -k test_serve_atomic_io`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/atomic_io.py uedcli/tests/test_serve_atomic_io.py
git commit -m "Add atomic_write_text/atomic_write_json helpers"
```

---

### Task 2: Config — `build_cache_max_bytes` / `staging_blobs_max_bytes`

**Files:**
- Modify: `uedcli/config.py` (`Project` dataclass ~line 115, `_PROJECT_KEYS` line 51, `load_project()`
  lines 375-402)
- Test: `uedcli/tests/test_config.py`

**Interfaces:**
- Produces: `Project.build_cache_max_bytes: int | None`, `Project.staging_blobs_max_bytes: int | None`
  — later tasks (build_cache.py, snapshots.py eviction) read these off the `Project` passed to them.

- [ ] **Step 1: Write the failing tests**

```python
def test_project_accepts_build_cache_max_bytes(tmp_path):
    toml = tmp_path / "uedcli.toml"
    toml.write_text('game = "deusex"\nbuild_cache_max_bytes = 5000000\n', encoding="utf-8")
    project = load_project(str(toml))
    assert project.build_cache_max_bytes == 5000000

def test_project_accepts_staging_blobs_max_bytes(tmp_path):
    toml = tmp_path / "uedcli.toml"
    toml.write_text('game = "deusex"\nstaging_blobs_max_bytes = 200000\n', encoding="utf-8")
    project = load_project(str(toml))
    assert project.staging_blobs_max_bytes == 200000

def test_project_defaults_both_budgets_to_none(tmp_path):
    toml = tmp_path / "uedcli.toml"
    toml.write_text('game = "deusex"\n', encoding="utf-8")
    project = load_project(str(toml))
    assert project.build_cache_max_bytes is None
    assert project.staging_blobs_max_bytes is None

def test_project_rejects_non_positive_build_cache_max_bytes(tmp_path):
    toml = tmp_path / "uedcli.toml"
    toml.write_text('game = "deusex"\nbuild_cache_max_bytes = 0\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="build_cache_max_bytes must be a positive integer, got 0"):
        load_project(str(toml))

def test_project_rejects_non_integer_staging_blobs_max_bytes(tmp_path):
    toml = tmp_path / "uedcli.toml"
    toml.write_text('game = "deusex"\nstaging_blobs_max_bytes = "lots"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="staging_blobs_max_bytes must be a positive integer"):
        load_project(str(toml))
```

(Add `import pytest` and `from uedcli.config import ConfigError, load_project` at the top of
`test_config.py` if not already present — check the existing imports first.)

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test -k test_config and max_bytes`
Expected: FAIL — `Project` has no such field / no such key is accepted.

- [ ] **Step 3: Implement**

In `Project` (after `maps: str | None = None`):
```python
    build_cache_max_bytes: int | None = None
    staging_blobs_max_bytes: int | None = None
```

Update `_PROJECT_KEYS` (line 51):
```python
_PROJECT_KEYS = {"game", "paths", "catalog", "prefabs", "maps",
                  "build_cache_max_bytes", "staging_blobs_max_bytes"}
```

In `load_project()`, add validation alongside the existing string-key loop (lines 396-399), matching
its style:
```python
    for key in ("build_cache_max_bytes", "staging_blobs_max_bytes"):
        v = raw.get(key)
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v <= 0):
            raise ConfigError(f"{key} must be a positive integer, got {v!r}")
```
(`isinstance(v, bool)` excluded explicitly — `bool` is an `int` subclass in Python, and `True`/`False`
are not valid byte counts.)

Update the final constructor call to pass both through:
```python
    return Project(root=os.path.dirname(toml_path), game=game, paths=raw.get("paths"),
                   catalog=raw.get("catalog"), prefabs=raw.get("prefabs"), maps=raw.get("maps"),
                   build_cache_max_bytes=raw.get("build_cache_max_bytes"),
                   staging_blobs_max_bytes=raw.get("staging_blobs_max_bytes"),
                   source=toml_path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `bin/test -k test_config`
Expected: PASS, no regressions on existing `test_config.py` cases.

- [ ] **Step 5: Commit**

```bash
git add uedcli/config.py uedcli/tests/test_config.py
git commit -m "Add build_cache_max_bytes/staging_blobs_max_bytes to Project config"
```

Also update `dev/docs/direction/projects-and-config.md`'s key table to list the two new keys — this
needs the owner's explicit yes (`CLAUDE.md`'s direction-doc rule). File it as a note in the PR
description for the owner to approve separately; do not edit that doc in this task.

---

### Task 3: `build_cache.py` — rename, restructure, reference-aware eviction

**Files:**
- Rename: `uedcli/preview_cache.py` → `uedcli/build_cache.py`
- Modify: every importer of `preview_cache` (`grep -rn "preview_cache" uedcli/` first — expected in
  `uedcli/preview_native.py`, `uedcli/serve/build_pin.py`, `uedcli/serve/app.py`, and any existing
  tests)
- Test: `uedcli/tests/test_build_cache.py` (new — check for and remove/merge any existing
  `test_preview_cache.py`)

**Interfaces:**
- Consumes: `Project.build_cache_max_bytes` (Task 2).
- Produces: `load_geometry(project, level_name, geom_hash12)`, `store_geometry(project, level_name,
  geom_hash12, payload)`, `load_scene(project, level_name, geom_hash12, light_hash12)`,
  `store_scene(project, level_name, geom_hash12, light_hash12, payload)` — same signatures as
  today's `preview_cache.py`, callers unaffected beyond the import rename. New:
  `evict_unreferenced(project, level_name, *, live_geom_hashes: set[str], live_pairs:
  set[tuple[str, str]]) -> dict` (mirrors `schema_cache.evict_lru`'s return shape: `{"evicted",
  "freed_bytes", "kept_bytes", "kept_entries"}`).

- [ ] **Step 1: Read the current file in full**

`uedcli/preview_cache.py` — confirm `_CACHE_VERSION`, `_dir()`, `_sweep_old_versions()`'s exact
bodies before changing them (already summarized in this plan's research, but read live before
editing since this task changes their core logic).

- [ ] **Step 2: Write the failing tests**

```python
from pathlib import Path
from uedcli import build_cache

class _Project:
    def __init__(self, root):
        self.root = str(root)

def test_store_and_load_geometry_round_trips(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "abc123def456", {"polys": []})
    assert build_cache.load_geometry(project, "unatco", "abc123def456") == {"polys": []}

def test_geometry_lives_under_versioned_per_level_path(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "abc123def456", {"polys": []})
    expected = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry" / "abc123def456.marshal"
    assert expected.exists()

def test_lighting_nests_under_its_geometry_hash(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_scene(project, "unatco", "geomhash1234", "lighthash5678", {"polys": []})
    expected = (tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "lighting"
                / "geomhash1234" / "lighthash5678.marshal")
    assert expected.exists()

def test_load_scene_missing_entry_is_a_cache_miss_not_an_error(tmp_path):
    project = _Project(tmp_path)
    assert build_cache.load_scene(project, "unatco", "nope", "nope") is None

def test_load_geometry_corrupt_file_degrades_to_cache_miss(tmp_path):
    project = _Project(tmp_path)
    p = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry"
    p.mkdir(parents=True)
    (p / "abc123def456.marshal").write_bytes(b"not marshal data")
    assert build_cache.load_geometry(project, "unatco", "abc123def456") is None

def test_evict_unreferenced_removes_only_entries_with_no_live_reference(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "keepme000001", {"polys": []})
    build_cache.store_geometry(project, "unatco", "dropme000001", {"polys": []})
    result = build_cache.evict_unreferenced(
        project, "unatco", live_geom_hashes={"keepme000001"}, live_pairs=set())
    kept = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry" / "keepme000001.marshal"
    dropped = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry" / "dropme000001.marshal"
    assert kept.exists()
    assert not dropped.exists()
    assert result["evicted"] == 1

def test_evict_unreferenced_never_touches_a_live_entry_even_over_budget(tmp_path):
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "onlylive0001", {"polys": list(range(1000))})
    result = build_cache.evict_unreferenced(
        project, "unatco", live_geom_hashes={"onlylive0001"}, live_pairs=set(), max_bytes=1)
    p = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry" / "onlylive0001.marshal"
    assert p.exists()
    assert result["evicted"] == 0

def test_evict_unreferenced_evicts_oldest_unreferenced_first_over_budget(tmp_path):
    import os, time
    project = _Project(tmp_path)
    build_cache.store_geometry(project, "unatco", "older0000001", {"polys": [0] * 500})
    d = tmp_path / ".uedcli" / "build" / "cache" / "v3" / "unatco" / "geometry"
    os.utime(d / "older0000001.marshal", (time.time() - 1000, time.time() - 1000))
    build_cache.store_geometry(project, "unatco", "newer0000001", {"polys": [0] * 500})
    result = build_cache.evict_unreferenced(
        project, "unatco", live_geom_hashes=set(), live_pairs=set(),
        max_bytes=(d / "newer0000001.marshal").stat().st_size)
    assert not (d / "older0000001.marshal").exists()
    assert (d / "newer0000001.marshal").exists()
```

- [ ] **Step 3: Run to verify it fails**

Run: `bin/test -k test_build_cache`
Expected: FAIL — `ModuleNotFoundError: No module named 'uedcli.build_cache'`

- [ ] **Step 4: Implement — rename and restructure**

```bash
git mv uedcli/preview_cache.py uedcli/build_cache.py
```

Rewrite `_dir` (now level-aware) and the four load/store functions to use the new nested layout;
keep `marshal.dumps`/`marshal.loads` and the existing atomic-write pattern (`_store`) unchanged —
only the path construction changes:

```python
_CACHE_VERSION = 3


def _dir(project, level_name: str) -> Path:
    root = config.state_subdir(project.root, "build/cache", create=True)
    return root / f"v{_CACHE_VERSION}" / level_name


def _geometry_path(project, level_name: str, geom_hash12: str) -> Path:
    return _dir(project, level_name) / "geometry" / f"{geom_hash12}.marshal"


def _lighting_path(project, level_name: str, geom_hash12: str, light_hash12: str) -> Path:
    return _dir(project, level_name) / "lighting" / geom_hash12 / f"{light_hash12}.marshal"


def load_geometry(project, level_name: str, geom_hash12: str):
    return _load(_geometry_path(project, level_name, geom_hash12))


def store_geometry(project, level_name: str, geom_hash12: str, payload) -> None:
    _store(_geometry_path(project, level_name, geom_hash12), payload)


def load_scene(project, level_name: str, geom_hash12: str, light_hash12: str):
    return _load(_lighting_path(project, level_name, geom_hash12, light_hash12))


def store_scene(project, level_name: str, geom_hash12: str, light_hash12: str, payload) -> None:
    _store(_lighting_path(project, level_name, geom_hash12, light_hash12), payload)
```

Keep the existing `_load`/`_store` bodies (marshal + atomic temp-file write + broad-except-on-read
degrading to `None`) exactly as they are today — only their callers' path arguments changed.
`_sweep_old_versions`/`_prune_prefix`/`_compose_stem` (the old flat, prefix-based, newest-N-by-mtime
scheme) are deleted outright — the new nested `v{N}/<level>/` layout makes a version bump a directory
rename/removal, and eviction is now `evict_unreferenced` below, not a filename-prefix scan.

- [ ] **Step 5: Implement — reference-aware eviction**

```python
def evict_unreferenced(
    project, level_name: str, *, live_geom_hashes: set[str], live_pairs: set[tuple[str, str]],
    max_bytes: int | None = None,
) -> dict:
    """Delete geometry/lighting cache entries with no live reference, oldest-atime-first, until
    under `max_bytes` (or `project.build_cache_max_bytes` if not given). A live entry is NEVER
    evicted regardless of budget — `live_geom_hashes`/`live_pairs` name every (geom_hash) and
    (geom_hash, light_hash) currently pinned by any session's build.json or any level's
    build/pin/<level>/current.json; the caller gathers those sets, this function only deletes."""
    budget = max_bytes if max_bytes is not None else project.build_cache_max_bytes
    base = _dir(project, level_name)
    geo_dir, lit_dir = base / "geometry", base / "lighting"
    candidates: list[tuple[float, int, Path]] = []
    total = 0
    if geo_dir.is_dir():
        for f in geo_dir.iterdir():
            if not f.is_file():
                continue
            st = f.stat()
            total += st.st_size
            if f.stem not in live_geom_hashes:
                candidates.append((st.st_atime, st.st_size, f))
    if lit_dir.is_dir():
        for geom_sub in lit_dir.iterdir():
            if not geom_sub.is_dir():
                continue
            for f in geom_sub.iterdir():
                if not f.is_file():
                    continue
                st = f.stat()
                total += st.st_size
                if (geom_sub.name, f.stem) not in live_pairs:
                    candidates.append((st.st_atime, st.st_size, f))
    evicted = freed = 0
    if budget is not None and total > budget:
        candidates.sort(key=lambda c: c[0])
        for _atime, size, path in candidates:
            if total <= budget:
                break
            try:
                path.unlink()
            except OSError:
                continue
            total -= size
            evicted += 1
            freed += size
    return {"evicted": evicted, "freed_bytes": freed, "kept_bytes": total,
            "kept_entries": len(list(geo_dir.glob("*"))) if geo_dir.is_dir() else 0}
```

- [ ] **Step 6: Fix every importer**

`grep -rn "preview_cache" uedcli/` and change each `from uedcli import preview_cache` /
`from uedcli.preview_cache import ...` to `build_cache`. Do NOT fix call sites' `level_name`
argument here — `preview_native.py`'s calls already pass one; `build_pin.py`'s calls are rewritten in
Task 4.

- [ ] **Step 7: Run to verify it passes**

Run: `bin/test -k test_build_cache`
Expected: PASS (8 tests). Also run `bin/test -k preview_native` to confirm the rename didn't break
its existing callers.

- [ ] **Step 8: Commit**

```bash
git add -A uedcli/build_cache.py uedcli/preview_cache.py uedcli/tests/test_build_cache.py uedcli/preview_native.py uedcli/serve/build_pin.py uedcli/serve/app.py
git commit -m "Rename preview_cache to build_cache, restructure paths, add reference-aware eviction"
```

---

### Task 4: `build_pin.py` — session pointer + level pointer, with writers

**Files:**
- Modify: `uedcli/serve/build_pin.py`
- Modify: `uedcli/serve/app.py` (`_bootstrap_geometry_if_empty` calls `build_pin.load_pointer` and
  `build_pin.resolve_pin` today — both names are deleted by this task, so this call site must be
  updated in the SAME commit, not left broken until Task 9)
- Modify: `uedcli/tests/test_serve_build_pin.py` (existing — already calls `pointer_path`,
  `load_pointer`, `resolve_pin` directly; re-key every test to the new split names)
- Modify: `uedcli/tests/test_serve_load_rebuild.py` (existing — calls `build_pin.pointer_path`
  directly at lines 75, 107, 206; update to `level_pointer_path`)
- Test: `uedcli/tests/test_build_pin.py` (new — for the genuinely new session-pointer half; the
  level-pointer half already has coverage in `test_serve_build_pin.py`, being re-keyed above, not
  written fresh)

**Interfaces:**
- Consumes: `build_cache.load_scene` (Task 3).
- Produces: `session_pointer_path(sessions_root, session_id) -> Path`,
  `load_session_pointer(sessions_root, session_id) -> tuple[str, str]` (raises
  `SessionPointerCorruptError` naming the file on a bad read — never `None`),
  `write_session_pointer(sessions_root, session_id, geom_hash, light_hash) -> None` (atomic),
  `level_pointer_path(project, level_name) -> Path`, `load_level_pointer(project, level_name) ->
  tuple[str, str] | None` (unchanged silent-degrade-to-`None` behavior), `write_level_pointer(project,
  level_name, geom_hash, light_hash) -> None` (atomic), `resolve_session_pin(project, level_name,
  sessions_root, session_id) -> tuple | None`, `resolve_level_pin(project, level_name) -> tuple |
  None`. **`pointer_path`/`load_pointer`/`resolve_pin` are deleted outright** — no back-compat
  alias (`Global Constraints`) — replaced one-for-one by `level_pointer_path`/`load_level_pointer`/
  `resolve_level_pin`, since today's single pointer concept only ever meant the level one (nothing
  session-scoped existed before this feature).

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from pathlib import Path
from uedcli.serve.build_pin import (
    session_pointer_path, load_session_pointer, write_session_pointer, SessionPointerCorruptError,
    level_pointer_path, load_level_pointer, write_level_pointer,
)

class _Project:
    def __init__(self, root):
        self.root = str(root)

def test_session_pointer_path_is_under_sessions_dir(tmp_path):
    p = session_pointer_path(tmp_path, "abc123")
    assert p == tmp_path / "abc123" / "build.json"

def test_write_then_load_session_pointer_round_trips(tmp_path):
    write_session_pointer(tmp_path, "abc123", "geomhash0001", "lighthash0001")
    assert load_session_pointer(tmp_path, "abc123") == ("geomhash0001", "lighthash0001")

def test_load_session_pointer_missing_file_raises_named_error(tmp_path):
    with pytest.raises(SessionPointerCorruptError, match="abc123"):
        load_session_pointer(tmp_path, "abc123")

def test_load_session_pointer_corrupt_json_raises_named_error(tmp_path):
    d = tmp_path / "abc123"
    d.mkdir()
    (d / "build.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionPointerCorruptError, match="build.json"):
        load_session_pointer(tmp_path, "abc123")

def test_level_pointer_path_is_under_build_pin_level(tmp_path):
    project = _Project(tmp_path)
    p = level_pointer_path(project, "unatco")
    assert p == tmp_path / ".uedcli" / "build" / "pin" / "unatco" / "current.json"

def test_write_then_load_level_pointer_round_trips(tmp_path):
    project = _Project(tmp_path)
    write_level_pointer(project, "unatco", "geomhash0002", "lighthash0002")
    assert load_level_pointer(project, "unatco") == ("geomhash0002", "lighthash0002")

def test_load_level_pointer_missing_degrades_to_none(tmp_path):
    project = _Project(tmp_path)
    assert load_level_pointer(project, "unatco") is None

def test_load_level_pointer_corrupt_degrades_to_none_not_an_exception(tmp_path):
    project = _Project(tmp_path)
    p = level_pointer_path(project, "unatco")
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    assert load_level_pointer(project, "unatco") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test -k test_build_pin`
Expected: FAIL — none of these names exist yet.

- [ ] **Step 3: Implement**

```python
"""Two build pins, not one. `sessions/<sid>/build.json` is this session's own current pin while it
edits — corrupt-and-instruct, since a session's own state is closer to "work" than to a cache
(direction/safety.md). `build/pin/<level>/current.json` is the level's pin, written only by Save,
naming the build matching the last-saved trunk — unchanged from before this feature: silent-degrade
to "never built" on any read failure, since it's purely regenerable (a fresh Rebuild replaces it)."""
from __future__ import annotations

import json
from pathlib import Path

from .. import build_cache, config
from .atomic_io import atomic_write_json


class SessionPointerCorruptError(Exception):
    pass


def session_pointer_path(sessions_root: Path, session_id: str) -> Path:
    return Path(sessions_root) / session_id / "build.json"


def load_session_pointer(sessions_root: Path, session_id: str) -> tuple[str, str]:
    p = session_pointer_path(sessions_root, session_id)
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data["geom_hash"], data["light_hash"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SessionPointerCorruptError(
            f"session {session_id}: build pin at {p} is missing or unreadable: {exc}"
        ) from exc


def write_session_pointer(sessions_root: Path, session_id: str, geom_hash: str, light_hash: str) -> None:
    atomic_write_json(session_pointer_path(sessions_root, session_id),
                       {"geom_hash": geom_hash, "light_hash": light_hash})


def resolve_session_pin(project, level_name: str, sessions_root: Path, session_id: str):
    geom_hash, light_hash = load_session_pointer(sessions_root, session_id)
    return build_cache.load_scene(project, level_name, geom_hash, light_hash)


def level_pointer_path(project, level_name: str) -> Path:
    return config.state_subdir(project.root, "build/pin", create=False) / level_name / "current.json"


def load_level_pointer(project, level_name: str) -> tuple[str, str] | None:
    try:
        raw = level_pointer_path(project, level_name).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
        return data["geom_hash"], data["light_hash"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def write_level_pointer(project, level_name: str, geom_hash: str, light_hash: str) -> None:
    atomic_write_json(level_pointer_path(project, level_name),
                       {"geom_hash": geom_hash, "light_hash": light_hash})


def resolve_level_pin(project, level_name: str):
    pin = load_level_pointer(project, level_name)
    if pin is None:
        return None
    geom_hash, light_hash = pin
    return build_cache.load_scene(project, level_name, geom_hash, light_hash)
```

- [ ] **Step 4: Fix the existing consumers this task's rename breaks**

`grep -rn "build_pin\.\(pointer_path\|load_pointer\|resolve_pin\)" uedcli/` and fix every result:
- `uedcli/serve/app.py`'s `_bootstrap_geometry_if_empty` — change its `build_pin.load_pointer(project,
  level_name)` call to `build_pin.load_level_pointer(project, level_name)`, and its
  `build_pin.resolve_pin(project, level_name, pin)` call to `build_pin.resolve_level_pin(project,
  level_name)` (note the narrowed signature — `resolve_level_pin` re-derives the pin internally via
  `load_level_pointer` rather than taking one as an argument, so drop the now-redundant `pin` lookup
  this call site did before).
- `uedcli/tests/test_serve_build_pin.py` — re-key every existing test from `pointer_path`/
  `load_pointer`/`resolve_pin` to `level_pointer_path`/`load_level_pointer`/`resolve_level_pin`
  (same call shape, just the level-only ones — this file's existing coverage of the pointer
  concept becomes this task's level-pointer regression suite, not a fresh rewrite).
- `uedcli/tests/test_serve_load_rebuild.py` (lines 75, 107, 206) — same rename,
  `pointer_path` → `level_pointer_path`.

- [ ] **Step 5: Run to verify it passes**

Run: `bin/test -k test_build_pin or test_serve_load_rebuild or test_serve_app`
Expected: PASS — the new session-pointer tests (8), the re-keyed level-pointer tests in
`test_serve_build_pin.py` (unchanged count, new names), and no regression in `test_serve_load_rebuild.py`
or `test_serve_app.py`'s `_bootstrap_geometry_if_empty`-dependent paths.

- [ ] **Step 6: Commit**

```bash
git add uedcli/serve/build_pin.py uedcli/serve/app.py uedcli/tests/test_build_pin.py uedcli/tests/test_serve_build_pin.py uedcli/tests/test_serve_load_rebuild.py
git commit -m "Split build_pin into session pointer (raise-on-corrupt) and level pointer (unchanged)"
```

---

### Task 5: `snapshots.py` — re-key `StagingStore` to session id, atomic writes, blob eviction

**Files:**
- Modify: `uedcli/serve/snapshots.py`
- Modify: `uedcli/tests/test_serve_snapshots.py` (existing — re-key every test from `level` to
  `session_id`)

**Interfaces:**
- Consumes: `atomic_io.atomic_write_json` (Task 1), `Project.staging_blobs_max_bytes` (Task 2).
- Produces: `StagingStore(sessions_root: Path, blobs_root: Path)`, `stage(session_id, actor_name, *,
  actor_t3d_text, baseline_location, staged_location) -> None`, `read_staged(session_id) ->
  dict[str, StagedActor]`, `clear_actor(session_id, actor_name) -> None`, `discard(session_id) ->
  None`, `evict_unreferenced_blobs(*, live_hashes: set[str], max_bytes: int | None = None) -> dict`.
  `StagedActor` is unchanged.

- [ ] **Step 1: Read the current file in full**

`uedcli/serve/snapshots.py` — confirm every method body before rewriting (already summarized in this
plan's research digest, but read live).

- [ ] **Step 2: Write the failing tests** (rewrite `test_serve_snapshots.py`'s existing cases to use
  a session id instead of a level name, plus new eviction cases)

```python
from decimal import Decimal
from pathlib import Path
from uedcli.serve.snapshots import StagingStore

def test_stage_then_read_staged_round_trips_exact_decimal(tmp_path):
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "Light12", actor_t3d_text="Begin Actor...",
                baseline_location=(Decimal("1.5"), Decimal("2"), Decimal("3")),
                staged_location=(Decimal("1.5"), Decimal("2"), Decimal("4")))
    staged = store.read_staged("sess1")
    assert staged["Light12"].staged_location == (Decimal("1.5"), Decimal("2"), Decimal("4"))

def test_stage_writes_manifest_under_sessions_root_not_blobs_root(tmp_path):
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "Light12", actor_t3d_text="Begin Actor...",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    assert (tmp_path / "sessions" / "sess1" / "staged.json").exists()

def test_stage_manifest_write_is_atomic(tmp_path, monkeypatch):
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    import uedcli.serve.snapshots as mod
    calls = []
    real = mod.atomic_write_json
    monkeypatch.setattr(mod, "atomic_write_json", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    store.stage("sess1", "Light12", actor_t3d_text="x",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    assert calls == [1]

def test_clear_actor_removes_only_that_actor(tmp_path):
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "A", actor_t3d_text="x",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    store.stage("sess1", "B", actor_t3d_text="y",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(2)))
    store.clear_actor("sess1", "A")
    assert set(store.read_staged("sess1")) == {"B"}

def test_discard_removes_the_whole_manifest(tmp_path):
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "A", actor_t3d_text="x",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    store.discard("sess1")
    assert store.read_staged("sess1") == {}

def test_restaging_an_already_staged_actor_keeps_its_original_baseline(tmp_path):
    """Regression test carried over from the existing test_stage_read_restage_keeps_baseline_
    discard_clear in today's test_serve_snapshots.py: staging the SAME actor a second time (a second
    drag) must NOT overwrite its baseline_location with the caller's newly-supplied value -- the
    baseline is what Save's conflict check compares against the CURRENT trunk, so an overwritten
    baseline would silently corrupt conflict detection."""
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "Light12", actor_t3d_text="first",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    store.stage("sess1", "Light12", actor_t3d_text="second",
                baseline_location=(Decimal(9), Decimal(9), Decimal(9)),  # caller passes a DIFFERENT baseline
                staged_location=(Decimal(0), Decimal(0), Decimal(2)))
    staged = store.read_staged("sess1")
    assert staged["Light12"].baseline_location == (Decimal(0), Decimal(0), Decimal(0))  # original kept
    assert staged["Light12"].staged_location == (Decimal(0), Decimal(0), Decimal(2))  # new value used

def test_two_sessions_staging_the_same_content_share_one_blob(tmp_path):
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "A", actor_t3d_text="same text",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    store.stage("sess2", "B", actor_t3d_text="same text",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    h1 = store.read_staged("sess1")["A"].blob_hash
    h2 = store.read_staged("sess2")["B"].blob_hash
    assert h1 == h2
    blob_files = list((tmp_path / "blobs").rglob("*"))
    assert len([f for f in blob_files if f.is_file()]) == 1

def test_evict_unreferenced_blobs_keeps_blobs_named_in_live_hashes(tmp_path):
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "A", actor_t3d_text="keep me",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    keep_hash = store.read_staged("sess1")["A"].blob_hash
    store.discard("sess1")  # sess1 no longer references it, but pass it as still-live
    result = store.evict_unreferenced_blobs(live_hashes={keep_hash})
    assert result["evicted"] == 0
    assert (tmp_path / "blobs" / keep_hash[:2] / keep_hash).exists()

def test_evict_unreferenced_blobs_removes_blobs_named_in_no_manifest(tmp_path):
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sess1", "A", actor_t3d_text="drop me",
                baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
                staged_location=(Decimal(0), Decimal(0), Decimal(1)))
    h = store.read_staged("sess1")["A"].blob_hash
    store.discard("sess1")
    result = store.evict_unreferenced_blobs(live_hashes=set())
    assert result["evicted"] == 1
    assert not (tmp_path / "blobs" / h[:2] / h).exists()
```

- [ ] **Step 3: Run to verify it fails**

Run: `bin/test -k test_serve_snapshots`
Expected: FAIL — `StagingStore.__init__` still takes one `root` argument, methods still key on
`level`.

- [ ] **Step 4: Implement**

Rewrite the constructor and every method to take two roots and a `session_id` in place of `level`;
swap the manifest write from bare `write_text` to `atomic_write_json`; add `evict_unreferenced_blobs`.
Keep `StagedActor` and the blob-hashing logic (`hashlib.sha256` over the actor T3D text) unchanged.

```python
class StagingStore:
    def __init__(self, sessions_root: Path, blobs_root: Path) -> None:
        self.sessions_root = Path(sessions_root)
        self.blobs_root = Path(blobs_root)

    def _manifest_path(self, session_id: str) -> Path:
        return self.sessions_root / session_id / "staged.json"

    def _blob_path(self, blob_hash: str) -> Path:
        return self.blobs_root / blob_hash[:2] / blob_hash

    def stage(self, session_id: str, actor_name: str, *, actor_t3d_text: str,
              baseline_location: tuple[Decimal, Decimal, Decimal],
              staged_location: tuple[Decimal, Decimal, Decimal]) -> None:
        blob_hash = hashlib.sha256(actor_t3d_text.encode("utf-8")).hexdigest()
        blob_path = self._blob_path(blob_hash)
        if not blob_path.exists():
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_text(actor_t3d_text, encoding="utf-8")
        manifest = self._read_manifest(session_id)
        existing = manifest.get(actor_name)
        # Re-staging an already-staged actor keeps its ORIGINAL baseline -- the caller's
        # baseline_location argument is only used the first time this actor is staged in this
        # session. Overwriting it on every re-stage would corrupt Save's conflict check, which
        # compares this baseline against the trunk's CURRENT state, not against whatever the most
        # recent drag happened to load.
        effective_baseline = (
            [Decimal(c) for c in existing["baseline_location"]] if existing is not None
            else list(baseline_location)
        )
        manifest[actor_name] = {
            "baseline_location": [str(c) for c in effective_baseline],
            "staged_location": [str(c) for c in staged_location],
            "blob_hash": blob_hash,
        }
        atomic_write_json(self._manifest_path(session_id), manifest)

    def read_staged(self, session_id: str) -> dict[str, StagedActor]:
        manifest = self._read_manifest(session_id)
        return {
            name: StagedActor(
                baseline_location=tuple(Decimal(c) for c in v["baseline_location"]),
                staged_location=tuple(Decimal(c) for c in v["staged_location"]),
                blob_hash=v["blob_hash"],
            )
            for name, v in manifest.items()
        }

    def clear_actor(self, session_id: str, actor_name: str) -> None:
        manifest = self._read_manifest(session_id)
        manifest.pop(actor_name, None)
        atomic_write_json(self._manifest_path(session_id), manifest)

    def discard(self, session_id: str) -> None:
        self._manifest_path(session_id).unlink(missing_ok=True)

    def _read_manifest(self, session_id: str) -> dict:
        p = self._manifest_path(session_id)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def evict_unreferenced_blobs(self, *, live_hashes: set[str], max_bytes: int | None = None) -> dict:
        """Delete blobs no session's staged.json names, oldest-atime-first, over budget. Caller
        computes `live_hashes` by scanning every sessions/*/staged.json — see app.py's eviction
        orchestration (Task 9) for the lock scope this must run under."""
        candidates: list[tuple[float, int, Path]] = []
        total = 0
        if self.blobs_root.is_dir():
            for shard in self.blobs_root.iterdir():
                if not shard.is_dir():
                    continue
                for f in shard.iterdir():
                    if not f.is_file():
                        continue
                    st = f.stat()
                    total += st.st_size
                    if f.name not in live_hashes:
                        candidates.append((st.st_atime, st.st_size, f))
        evicted = freed = 0
        if max_bytes is not None and total > max_bytes:
            candidates.sort(key=lambda c: c[0])
            for _atime, size, path in candidates:
                if total <= max_bytes:
                    break
                try:
                    path.unlink()
                except OSError:
                    continue
                total -= size
                evicted += 1
                freed += size
        return {"evicted": evicted, "freed_bytes": freed, "kept_bytes": total}
```

Add `from .atomic_io import atomic_write_json` to the imports.

- [ ] **Step 5: Run to verify it passes**

Run: `bin/test -k test_serve_snapshots`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add uedcli/serve/snapshots.py uedcli/tests/test_serve_snapshots.py
git commit -m "Re-key StagingStore to session id, atomic writes, reference-aware blob eviction"
```

---

### Task 6: `sessions.py` — session lifecycle

**Files:**
- Create: `uedcli/serve/sessions.py`
- Test: `uedcli/tests/test_serve_sessions.py`

**Interfaces:**
- Consumes: `atomic_io.atomic_write_json` (Task 1).
- Produces: `SessionRecord` (frozen dataclass: `id`, `level`, `created_at`, `last_active_at`),
  `create_session(sessions_root, level) -> SessionRecord`, `get_session(sessions_root, session_id) ->
  SessionRecord | None` (returns `None`, not an exception, for a missing/never-created id — "does
  this exist" is a normal query, distinct from "this session's own files are corrupt"),
  `list_sessions(sessions_root) -> list[SessionRecord]`, `delete_session(sessions_root, session_id)
  -> None`, `touch_session(sessions_root, session_id) -> None` (throttled `last_active_at` update, no-op
  if the existing value is under 30s old), `SessionIndexCorruptError`.

- [ ] **Step 1: Write the failing tests**

```python
import time
import pytest
from uedcli.serve.sessions import (
    create_session, get_session, list_sessions, delete_session, touch_session,
    SessionIndexCorruptError,
)

def test_create_session_returns_a_record_with_a_uuid7_id(tmp_path):
    rec = create_session(tmp_path, "unatco")
    assert rec.level == "unatco"
    assert len(rec.id) >= 32  # the real uuid7() returns a dashed 8-4-4-4-12 string (36 chars); this
                              # loose bound holds either way, but confirm the exact format in Step 1

def test_create_session_writes_index_json_under_its_own_directory(tmp_path):
    rec = create_session(tmp_path, "unatco")
    assert (tmp_path / rec.id / "index.json").exists()

def test_get_session_returns_the_created_record(tmp_path):
    rec = create_session(tmp_path, "unatco")
    fetched = get_session(tmp_path, rec.id)
    assert fetched == rec

def test_get_session_missing_id_returns_none(tmp_path):
    assert get_session(tmp_path, "doesnotexist") is None

def test_get_session_corrupt_index_raises_named_error(tmp_path):
    rec = create_session(tmp_path, "unatco")
    (tmp_path / rec.id / "index.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionIndexCorruptError, match=rec.id):
        get_session(tmp_path, rec.id)

def test_list_sessions_returns_every_created_session(tmp_path):
    a = create_session(tmp_path, "unatco")
    b = create_session(tmp_path, "wanchai")
    ids = {s.id for s in list_sessions(tmp_path)}
    assert ids == {a.id, b.id}

def test_delete_session_removes_the_whole_directory(tmp_path):
    rec = create_session(tmp_path, "unatco")
    delete_session(tmp_path, rec.id)
    assert not (tmp_path / rec.id).exists()
    assert get_session(tmp_path, rec.id) is None

def test_touch_session_updates_last_active_at_when_stale(tmp_path):
    rec = create_session(tmp_path, "unatco")
    old_index = tmp_path / rec.id / "index.json"
    old_index.write_text(old_index.read_text().replace(rec.last_active_at, "2000-01-01T00:00:00Z"))
    touch_session(tmp_path, rec.id)
    assert get_session(tmp_path, rec.id).last_active_at != "2000-01-01T00:00:00Z"

def test_touch_session_is_a_noop_when_recently_touched(tmp_path):
    rec = create_session(tmp_path, "unatco")
    before = get_session(tmp_path, rec.id).last_active_at
    touch_session(tmp_path, rec.id)
    assert get_session(tmp_path, rec.id).last_active_at == before
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test -k test_serve_sessions`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
"""Session lifecycle: sessions/<sid>/index.json (id, level, created_at, last_active_at,
last_seen_generation). Corrupt-and-instruct on a bad read of an EXISTING session's own index.json --
this is a session's own record, closer to "work" than to a cache. A session id that was simply never
created is a normal miss (returns None), not corruption."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .atomic_io import atomic_write_json
from ..uuid7 import uuid7  # reuse the existing ephemeral-editor id generator (architecture.md D5/D7)

_TOUCH_THROTTLE = timedelta(seconds=30)


class SessionIndexCorruptError(Exception):
    pass


@dataclass(frozen=True, kw_only=True)
class SessionRecord:
    id: str
    level: str
    created_at: str
    last_active_at: str
    last_seen_generation: int = 0


def _index_path(sessions_root: Path, session_id: str) -> Path:
    return Path(sessions_root) / session_id / "index.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_session(sessions_root: Path, level: str) -> SessionRecord:
    now = _now()
    rec = SessionRecord(id=uuid7(), level=level, created_at=now, last_active_at=now)
    atomic_write_json(_index_path(sessions_root, rec.id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": rec.last_active_at, "last_seen_generation": rec.last_seen_generation,
    })
    return rec


def get_session(sessions_root: Path, session_id: str) -> SessionRecord | None:
    p = _index_path(sessions_root, session_id)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return SessionRecord(
            id=data["id"], level=data["level"], created_at=data["created_at"],
            last_active_at=data["last_active_at"],
            last_seen_generation=data.get("last_seen_generation", 0),
        )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SessionIndexCorruptError(
            f"session {session_id}: index.json at {p} is unreadable: {exc}"
        ) from exc


def list_sessions(sessions_root: Path) -> list[SessionRecord]:
    root = Path(sessions_root)
    if not root.is_dir():
        return []
    out = []
    for child in root.iterdir():
        if child.is_dir():
            rec = get_session(sessions_root, child.name)
            if rec is not None:
                out.append(rec)
    return out


def delete_session(sessions_root: Path, session_id: str) -> None:
    import shutil
    d = Path(sessions_root) / session_id
    shutil.rmtree(d, ignore_errors=True)


def touch_session(sessions_root: Path, session_id: str) -> None:
    rec = get_session(sessions_root, session_id)
    if rec is None:
        return
    last = datetime.strptime(rec.last_active_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - last < _TOUCH_THROTTLE:
        return
    atomic_write_json(_index_path(sessions_root, session_id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": _now(), "last_seen_generation": rec.last_seen_generation,
    })


def set_last_seen_generation(sessions_root: Path, session_id: str, generation: int) -> None:
    rec = get_session(sessions_root, session_id)
    if rec is None:
        return
    atomic_write_json(_index_path(sessions_root, session_id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": rec.last_active_at, "last_seen_generation": generation,
    })
```

Before writing this, run `grep -rn "def uuid7" uedcli/` to confirm the existing helper's real import
path and return format (dashed vs. bare hex) — adjust the import and the id-length assertion in the
tests to match exactly.

- [ ] **Step 4: Run to verify it passes**

Run: `bin/test -k test_serve_sessions`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/sessions.py uedcli/tests/test_serve_sessions.py
git commit -m "Add session lifecycle module: index.json CRUD, throttled touch"
```

---

### Task 7: `claims.py` — claim-token ownership

**Files:**
- Create: `uedcli/serve/claims.py`
- Test: `uedcli/tests/test_serve_claims.py`

**Interfaces:**
- Produces: `ClaimRegistry` (a class, one instance per running server — holds the in-memory map,
  never touches disk): `mint(session_id) -> str` (mints and records a fresh token, superseding any
  prior one for that session), `check(session_id, token) -> bool` (three-state: no record for this
  session → records `token` as current and returns `True`; matches current → `True`; anything else →
  `False`), `lock_for(session_id) -> threading.Lock` (one lock per session id, created on first use,
  reused thereafter — this is what makes `check`-then-write atomic in Task 9/11).

- [ ] **Step 1: Write the failing tests**

```python
import threading
from uedcli.serve.claims import ClaimRegistry

def test_mint_returns_a_token():
    registry = ClaimRegistry()
    token = registry.mint("sess1")
    assert isinstance(token, str) and len(token) > 8

def test_check_matching_token_returns_true():
    registry = ClaimRegistry()
    token = registry.mint("sess1")
    assert registry.check("sess1", token) is True

def test_check_stale_token_returns_false():
    registry = ClaimRegistry()
    old = registry.mint("sess1")
    registry.mint("sess1")  # a second window claims
    assert registry.check("sess1", old) is False

def test_check_with_no_claim_recorded_establishes_it_and_returns_true():
    registry = ClaimRegistry()
    assert registry.check("sess1", "whatever-token") is True
    assert registry.check("sess1", "whatever-token") is True
    assert registry.check("sess1", "a-different-token") is False

def test_mint_after_a_restart_equivalent_new_registry_does_not_see_old_token():
    registry = ClaimRegistry()
    old_token = registry.mint("sess1")
    fresh_registry = ClaimRegistry()  # simulates a server restart -- new process, empty map
    assert fresh_registry.check("sess1", old_token) is True  # no claim recorded -> establishes it

def test_lock_for_returns_the_same_lock_object_for_the_same_session():
    registry = ClaimRegistry()
    assert registry.lock_for("sess1") is registry.lock_for("sess1")

def test_lock_for_returns_different_locks_for_different_sessions():
    registry = ClaimRegistry()
    assert registry.lock_for("sess1") is not registry.lock_for("sess2")

def test_check_and_mint_are_thread_safe_under_concurrent_access():
    registry = ClaimRegistry()
    registry.mint("sess1")
    errors = []
    def hammer():
        try:
            for _ in range(200):
                registry.mint("sess1")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test -k test_serve_claims`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

```python
"""In-memory-only claim-token ownership, one per running process. Never written to disk -- a
restart wiping this is fine (spec's "restart safety" note): the three-state check treats an
unrecorded session the same as a legitimate first claim, not as a conflict."""
from __future__ import annotations

import threading
import uuid


class ClaimRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, str] = {}
        self._session_locks: dict[str, threading.Lock] = {}

    def mint(self, session_id: str) -> str:
        token = uuid.uuid4().hex
        with self._lock:
            self._tokens[session_id] = token
        return token

    def check(self, session_id: str, token: str) -> bool:
        with self._lock:
            current = self._tokens.get(session_id)
            if current is None:
                self._tokens[session_id] = token
                return True
            return current == token

    def lock_for(self, session_id: str) -> threading.Lock:
        with self._lock:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._session_locks[session_id] = lock
            return lock

    def forget(self, session_id: str) -> None:
        """Called on session close -- drops bookkeeping for an id that will never be reused."""
        with self._lock:
            self._tokens.pop(session_id, None)
            self._session_locks.pop(session_id, None)
```

- [ ] **Step 4: Run to verify it passes**

Run: `bin/test -k test_serve_claims`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/claims.py uedcli/tests/test_serve_claims.py
git commit -m "Add in-memory claim-token registry for same-session multi-window ownership"
```

---

### Task 8: OQ1 — `build_scene` returns its own computed hashes

**Files:**
- Modify: `uedcli/preview_native.py` (the `build_scene` function and its `return` statement, ~line
  1105 — **and** its own in-module caller around line 1205, backing `level photo`/`render_shots`,
  which is easy to miss since it's not in another file)
- Modify: every OTHER caller (`grep -rn "build_scene(" uedcli/` first). Expect roughly 50 results,
  the large majority in `uedcli/tests/test_preview_native.py` (`polys, _, _ = pn.build_scene(...)`
  style, mechanical to widen), plus `uedcli/tests/test_serve_textures.py` and
  `uedcli/tests/test_serve_scene.py`, plus `uedcli/serve/app.py`'s `_build_and_publish_geometry` (the
  one real consumer of the two new values). This task's actual diff size is dozens of near-identical
  one-line changes, not the single illustrative example below — budget for that, don't treat it as a
  small task because the code shown here is short.
- Modify: `uedcli/serve/scene.py` (`_BuiltGeometry` construction, and its docstring's "OQ1, deferred"
  note — remove it, this task resolves it)
- Test: extend whichever existing test file already covers `build_scene`'s return shape (find via
  `grep -rln "build_scene(" uedcli/tests/`)

**Interfaces:**
- Produces: `build_scene(...) -> tuple[polys, texture_table, actor_names_by_poly, geom_hash: str |
  None, light_hash: str | None]` — a 5-tuple, widened from today's 3-tuple. `geom_hash`/`light_hash`
  are `None` only when `cache` (or whatever param gates hash computation today — confirm the exact
  parameter name by reading the function) is falsy; otherwise they're the real values already
  computed internally by `_scene_hashes`.

- [ ] **Step 1: Read `build_scene`'s full current body**

`uedcli/preview_native.py`, the function starting near line 800 through its `return` at line 1105 —
confirm the exact local variable names (`geom_hash`, `light_hash` per this plan's research) and the
exact condition gating whether they're computed at all, before changing the return statement.

- [ ] **Step 2: Enumerate every caller**

Run: `grep -rn "build_scene(" uedcli/ | grep -v "\.pyc"`
List every result. For each, note whether it unpacks the return by position (needs updating) or by
some other means.

- [ ] **Step 3: Write/extend the failing test**

Add to whichever existing test file exercises `build_scene` directly:
```python
def test_build_scene_returns_its_own_computed_geom_and_light_hash(...):
    # `cache` is not a real parameter -- per Step 1's read, hash computation is gated by
    # `project is not None and level_name is not None`, so pass real values for both, matching
    # whatever the existing nearby test already does to exercise that path.
    polys, texture_table, actor_names_by_poly, geom_hash, light_hash = build_scene(
        ..., project=real_project, level_name="unatco")
    assert geom_hash is not None
    assert light_hash is not None
    assert len(geom_hash) >= 12
```
(Adapt the setup to match the real existing test's fixtures — read that test first; do not invent a
`cache=True` keyword, it doesn't exist.)

- [ ] **Step 4: Run to verify it fails**

Run: `bin/test -k build_scene`
Expected: FAIL — `ValueError: too many values to unpack` (old 3-tuple return).

- [ ] **Step 5: Implement — widen the return**

Change `return polys, texture_table, actor_names_by_poly` to
`return polys, texture_table, actor_names_by_poly, geom_hash, light_hash` — no other logic changes;
`geom_hash`/`light_hash` are already computed locally earlier in the function.

- [ ] **Step 6: Fix every caller found in Step 2**

For each, widen the unpacking to 5 values, using `_` for the two new ones where a caller doesn't need
them (most won't — only `app.py`'s `_build_and_publish_geometry` does). Example for an unrelated
caller:
```python
polys, texture_table, actor_names_by_poly, _, _ = build_scene(...)
```

For `uedcli/serve/app.py`'s `_build_and_publish_geometry` (the one real consumer), use the real
values instead of hardcoded `None`:
```python
polys, texture_table, actor_names_by_poly, geom_hash, light_hash = build_scene(...)
built = _BuiltGeometry(geom_hash=geom_hash, light_hash=light_hash,
                        polys=polys, texture_table=texture_table, owners=owners)
```
Remove the `# OQ1 -- see scene.py` comment on this call site — it's resolved.

Also update `_BuiltGeometry`'s docstring in `uedcli/serve/scene.py` (remove the "OQ1, deferred" note
— it's no longer deferred).

- [ ] **Step 7: Run to verify it passes**

Run: `bin/test -k build_scene or serve_app or serve_scene`
Expected: PASS, no regressions on any caller.

- [ ] **Step 8: Commit**

```bash
git add uedcli/preview_native.py uedcli/serve/app.py uedcli/serve/scene.py <every other touched caller>
git commit -m "Widen build_scene's return to include its own computed geom_hash/light_hash (OQ1)"
```

---

### Task 9: `app.py` — `LevelContext`, replacing the single holder-cell set

**Files:**
- Modify: `uedcli/serve/app.py` (the `create_app` closure body, lines ~90-201, and `switch_level`)
- Modify: `uedcli/tests/test_serve_app.py` (existing tests referencing `app.state.current_level` /
  `app.state.generation` etc. need updating to go through the new per-level structure)
- **Delete: `uedcli/tests/test_serve_switch_level.py`** — its entire subject (`PUT /api/level`,
  `switch_level`, `app.state.watcher[0]`) is deleted by this task; the file has nothing left to test.
- **Heavily trim: `uedcli/tests/test_serve_load_rebuild.py`** (17 tests, 571 lines) — its premise is
  that a Rebuild's result stays pinned in memory until the next Load/Rebuild, which this task removes
  (`_geometry_ref`/`_payload_ref`/`_build_status`/`solve_lock` are gone, not moved — Task 11 restores
  pinning, per-session, via disk; between this task and that one, `/rebuild` is deliberately
  memoryless). Keep whichever of the 17 tests exercise something still true after this task (e.g.
  pure conflict-detection-on-Load behavior, if any are that narrow); delete or rewrite the rest.
- **Fix one dependent test each in `uedcli/tests/test_serve_lightmap.py` and
  `uedcli/tests/test_serve_scene.py`** — both call `app.state.build_and_publish_geometry` directly to
  exercise the "real pinned geometry" path, which no longer exists after this task.

(This file list was originally just the first two entries — a real gap this plan didn't originally
account for, caught by the implementer cross-referencing Tasks 10-14's own text before writing any
code, rather than guessing. Widening it here rather than leaving the plan's own record inaccurate.)

**Interfaces:**
- Consumes: `sessions.py` (Task 6), `claims.py` (Task 7).
- Produces: a `LevelContext` dataclass (`level_name`, `trunk_ref: list`, `generation: list[int]`,
  `changes_available: list[bool]`, `trunk_lock: threading.Lock`, `watcher: TrunkWatcher`,
  `connections: set[WebSocket]`, `scene_inputs_ref: list`), and `_level_contexts: dict[str,
  LevelContext]` plus `_get_or_create_level_context(level_name: str) -> LevelContext` on the app
  closure — a **plain Python method** later tasks (10-15) can call directly in their own test setup,
  not only reachable through an HTTP endpoint. Later tasks read/write through this instead of the old
  flat `_trunk_ref`/`_generation`/etc. lists. **`scene_inputs_ref` stays level-scoped, not removed**:
  despite living next to the old `_geometry_ref`/`_payload_ref` in today's code, it caches the
  composed package search path and class-resolution machinery (`search_files`, `index`, `defaults`),
  which depends only on the level + project config, never on any session's staged edits — genuinely
  shared by every session on a level, exactly like `trunk_ref`/`generation`/`watcher`. Dropping it
  would silently reintroduce a real, already-fixed regression (today's own comments describe a
  WanChai-scale request that stayed ~28s even on a warm repeat before this cache existed). **Removed
  from level scope entirely**: `_geometry_ref`, `_payload_ref`, `_build_status`, `_current_level`,
  `solve_lock`, `_payload_lock` — solved-build state becomes per-session (Task 11);
  `_current_level`/`PUT /api/level` are deleted (Task 12 replaces them with session creation);
  `solve_lock`/`_payload_lock` are replaced by the per-session lock from `claims.py` since solves now
  run against independent copies (Task 11) and need no shared lock at all.

- [ ] **Step 1: Read the full current `create_app` body and every route handler**

`uedcli/serve/app.py` in full — this task touches its structural core; read it live before editing,
even though this plan's research already summarized it. Confirm `_scene_inputs_ref`'s exact
construction (what it caches, what invalidates it) before moving it into `LevelContext` unchanged.

- [ ] **Step 2: Write the failing tests**

Per this plan's "tests set up state via lower-level module functions" rule (`Global Constraints`):
these tests call `_get_or_create_level_context` directly, a plain function this task itself adds —
they do NOT go through `POST /api/level/{level}/sessions`, which doesn't exist until Task 12. This
also means `create_app`'s signature is untouched by this task (it still takes today's required
`level: str` — Task 12 is what makes it optional, when the concept of "a level with no session on it
yet" first matters).

```python
def test_two_different_levels_get_independent_level_contexts(tmp_path):
    app = create_app(_project(tmp_path), "unatco")  # unchanged signature, real existing startup level
    ctx_a = app.state.get_or_create_level_context("unatco")
    ctx_b = app.state.get_or_create_level_context("wanchai")
    assert ctx_a is not ctx_b
    assert ctx_a.watcher is not ctx_b.watcher

def test_the_same_level_returns_the_same_level_context_on_a_second_call(tmp_path):
    app = create_app(_project(tmp_path), "unatco")
    first = app.state.get_or_create_level_context("unatco")
    second = app.state.get_or_create_level_context("unatco")
    assert first is second

def test_level_context_has_no_geometry_payload_or_build_status_fields():
    import dataclasses
    from uedcli.serve.app import LevelContext
    fields = {f.name for f in dataclasses.fields(LevelContext)}
    assert "geometry_ref" not in fields
    assert "payload_ref" not in fields
    assert "build_status" not in fields

def test_level_context_keeps_scene_inputs_ref():
    import dataclasses
    from uedcli.serve.app import LevelContext
    fields = {f.name for f in dataclasses.fields(LevelContext)}
    assert "scene_inputs_ref" in fields
```

(Match `test_serve_app.py`'s real existing `_project()` helper and `app.state.*` exposure pattern —
read that file first and adapt; expose `get_or_create_level_context` on `app.state` the same way
today's code exposes `get_trunk`/`build_and_publish_geometry`/etc.)

- [ ] **Step 3: Run to verify it fails, implement, run to verify it passes, commit**

Follow the same test-first cycle as prior tasks. Given the structural size of this change, expect to
touch most of `switch_level` (delete it — Task 12 replaces its behavior), `_bootstrap_geometry_if_empty`
(remove entirely — replaced by Task 11's per-session build resolution), and every route handler that
currently closes over `_trunk_ref[0]`/`_generation[0]`/etc. directly (redirect each to
`_get_or_create_level_context(level_name).trunk_ref` etc.) — this touches nearly every handler in the
file, which is why this task is sequenced before Tasks 10-15 rewrite those handlers' bodies anyway.

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Replace single holder-cell set with per-level LevelContext dict"
```

---

### Task 10: `app.py` — in-memory build-result cache

**Files:**
- Modify: `uedcli/serve/app.py`
- Test: `uedcli/tests/test_serve_app.py`

**Interfaces:**
- Produces: a small process-wide `_BuildResultCache` (or a plain `OrderedDict`-based helper function)
  keyed by `(level_name, geom_hash, light_hash)`, capped at a fixed entry count (start at 8, matching
  the existing `PREVIEW_KEEP`-style precedent elsewhere in the codebase — confirm via `grep -rn
  "PREVIEW_KEEP" uedcli/` and match its value), with `get(key)`/`put(key, value)` — `get` moves a hit
  to most-recently-used; `put` evicts the least-recently-used entry once over the cap. Task 11's
  Rebuild path checks this before calling `build_cache.load_scene`/`load_geometry` (disk), and
  populates it after a disk load or a fresh solve.

- [ ] **Step 1: Write the failing tests**

```python
def test_build_result_cache_hit_returns_the_stored_value():
    cache = _BuildResultCache(max_entries=2)
    cache.put(("unatco", "g1", "l1"), "payload-a")
    assert cache.get(("unatco", "g1", "l1")) == "payload-a"

def test_build_result_cache_miss_returns_none():
    cache = _BuildResultCache(max_entries=2)
    assert cache.get(("unatco", "g1", "l1")) is None

def test_build_result_cache_evicts_least_recently_used_over_cap():
    cache = _BuildResultCache(max_entries=2)
    cache.put(("a", "g", "l"), 1)
    cache.put(("b", "g", "l"), 2)
    cache.put(("c", "g", "l"), 3)  # evicts "a", the LRU
    assert cache.get(("a", "g", "l")) is None
    assert cache.get(("b", "g", "l")) == 2
    assert cache.get(("c", "g", "l")) == 3

def test_build_result_cache_get_refreshes_recency():
    cache = _BuildResultCache(max_entries=2)
    cache.put(("a", "g", "l"), 1)
    cache.put(("b", "g", "l"), 2)
    cache.get(("a", "g", "l"))  # touch a, making b the LRU now
    cache.put(("c", "g", "l"), 3)  # evicts "b", not "a"
    assert cache.get(("a", "g", "l")) == 1
    assert cache.get(("b", "g", "l")) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test -k build_result_cache`
Expected: FAIL — class doesn't exist.

- [ ] **Step 3: Implement**

```python
from collections import OrderedDict

class _BuildResultCache:
    """In-memory LRU in front of build_cache's on-disk store, keyed by content hash -- shared
    across every session and level, since identical hashes mean identical content regardless of who
    asked. Without this, every /scene|/atlas|/lightmap call re-does disk I/O + deserialization on
    every request (a real, previously-fixed perf regression -- see the spec's Build cache section)."""
    def __init__(self, max_entries: int = 8) -> None:
        self._max = max_entries
        self._data: OrderedDict[tuple, object] = OrderedDict()

    def get(self, key: tuple):
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: tuple, value) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)
```

- [ ] **Step 4: Run to verify it passes**

Run: `bin/test -k build_result_cache`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Add in-memory LRU cache in front of build_cache's disk store"
```

---

### Task 11: Session-scoped Rebuild — solve on a copy, write session pin, register cache refs

**Files:**
- Modify: `uedcli/serve/app.py` (the Rebuild handler)
- Modify: `uedcli/serve/edits.py` (extract a pure overlay-building helper, if the current `save_staged`
  logic for applying staged locations onto a `Level` isn't already factored out separately from the
  trunk-writing logic — read the file first to decide whether this is a new function or a reused one)
- Test: `uedcli/tests/test_serve_app.py`, `uedcli/tests/test_serve_edits.py`

**Interfaces:**
- Consumes: `claims.py` (Task 7, for the per-session lock and check-then-write), `sessions.py`/
  `build_pin.py` (session pointer writer), `build_cache.py`, the `_BuildResultCache` (Task 10).
- Produces: `apply_staged_overlay(level: Level, staged: dict[str, StagedActor]) -> Level` — returns a
  **new** `Level` (or a shallow copy sufficient that mutating the returned object's actor dict entries
  never touches the original) with only the staged actors' `location` replaced; the original `level`
  object is never mutated. This is what Rebuild feeds into `build_scene` instead of the shared
  `LevelContext.trunk_ref`'s `Level` directly.

- [ ] **Step 1: Read `edits.py`'s `save_staged` in full**, confirm exactly how it currently mutates
  `actor.location` in place on the loaded `Level`, and read `preview_native.build_scene`'s parameter
  shape (what it expects for its "level"/actors argument) before writing the overlay helper — its
  exact interface must match what `build_scene` actually consumes.

- [ ] **Step 2: Write the failing tests**

```python
def test_apply_staged_overlay_does_not_mutate_the_original_level(tmp_path):
    level = _make_level_with_actor("Light12", location=(Decimal(0), Decimal(0), Decimal(0)))
    staged = {"Light12": StagedActor(
        baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
        staged_location=(Decimal(0), Decimal(0), Decimal(99)), blob_hash="x")}
    overlaid = apply_staged_overlay(level, staged)
    assert level.actors["Light12"].location == (Decimal(0), Decimal(0), Decimal(0))
    assert overlaid.actors["Light12"].location == (Decimal(0), Decimal(0), Decimal(99))

def test_apply_staged_overlay_leaves_unstaged_actors_untouched(tmp_path):
    level = _make_level_with_actor("Brush1", location=(Decimal(5), Decimal(5), Decimal(5)))
    overlaid = apply_staged_overlay(level, {})
    assert overlaid.actors["Brush1"].location == (Decimal(5), Decimal(5), Decimal(5))

def test_two_sessions_rebuilding_the_same_level_concurrently_do_not_corrupt_each_other(tmp_path):
    # Per the "tests set up state via lower-level module functions" rule: sessions and staged
    # edits are created directly, not through Task 12/13's not-yet-built HTTP endpoints -- only
    # the Rebuild route itself (this task's own deliverable) is exercised over HTTP.
    project = _project(tmp_path)
    app = create_app(project, "unatco")  # real level fixture, matching test_serve_app.py's existing pattern
    c = TestClient(app)
    sess_a = sessions.create_session(app.state.sessions_root, "unatco")
    sess_b = sessions.create_session(app.state.sessions_root, "unatco")
    app.state.staging_store.stage(
        sess_a.id, "Light12", actor_t3d_text="Begin Actor Class=Light Name=Light12\nEnd Actor",
        baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
        staged_location=(Decimal(0), Decimal(0), Decimal(50)))
    app.state.staging_store.stage(
        sess_b.id, "Brush1", actor_t3d_text="Begin Actor Class=Brush Name=Brush1\nEnd Actor",
        baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
        staged_location=(Decimal(0), Decimal(0), Decimal(75)))
    token_a = app.state.claims.mint(sess_a.id)
    token_b = app.state.claims.mint(sess_b.id)
    r_a = c.post(f"/api/session/{sess_a.id}/rebuild", headers={"X-Claim-Token": token_a})
    r_b = c.post(f"/api/session/{sess_b.id}/rebuild", headers={"X-Claim-Token": token_b})
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    pin_a = build_pin.load_session_pointer(app.state.sessions_root, sess_a.id)
    pin_b = build_pin.load_session_pointer(app.state.sessions_root, sess_b.id)
    assert pin_a != pin_b  # different staged content -> different hashes: neither solve saw the other's edit
    ctx = app.state.get_or_create_level_context("unatco")
    assert ctx.trunk_ref[0].level.actors["Light12"].location == (Decimal(0), Decimal(0), Decimal(0))
    assert ctx.trunk_ref[0].level.actors["Brush1"].location == (Decimal(0), Decimal(0), Decimal(0))
    # the shared trunk_ref's Level is untouched by either session's overlay -- both still at baseline

def test_rebuild_writes_the_sessions_own_build_json(tmp_path):
    project = _project(tmp_path)
    app = create_app(project, "unatco")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "unatco")
    token = app.state.claims.mint(sess.id)
    r = c.post(f"/api/session/{sess.id}/rebuild", headers={"X-Claim-Token": token})
    assert r.status_code == 200
    pin = build_pin.load_session_pointer(app.state.sessions_root, sess.id)
    assert pin is not None

def test_rebuild_superseded_mid_solve_drops_the_result_without_error(tmp_path, monkeypatch):
    project = _project(tmp_path)
    app = create_app(project, "unatco")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "unatco")
    app.state.staging_store.stage(
        sess.id, "Light12", actor_t3d_text="Begin Actor Class=Light Name=Light12\nEnd Actor",
        baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
        staged_location=(Decimal(0), Decimal(0), Decimal(50)))
    token = app.state.claims.mint(sess.id)

    import uedcli.serve.app as app_module
    real_build_scene = app_module.build_scene
    def build_scene_then_supersede(*args, **kwargs):
        result = real_build_scene(*args, **kwargs)
        app.state.claims.mint(sess.id)  # a second window "claims" while this solve was running
        return result
    monkeypatch.setattr(app_module, "build_scene", build_scene_then_supersede)

    r = c.post(f"/api/session/{sess.id}/rebuild", headers={"X-Claim-Token": token})
    assert r.status_code == 409  # superseded before the write-time check could land
    with pytest.raises(build_pin.SessionPointerCorruptError):
        build_pin.load_session_pointer(app.state.sessions_root, sess.id)  # never written
```

Claim-token transport, pinned here rather than left open: an `X-Claim-Token` request header, on
every mutating call. Chosen over a body field because `DELETE` (Task 12) has no conventional body,
and a header applies uniformly across every verb without a per-endpoint exception. Tasks 12, 13, 15,
and 17 all follow this same convention — see their own claim-token mentions.

- [ ] **Step 3: Implement `apply_staged_overlay`**

```python
def apply_staged_overlay(level: Level, staged: dict[str, StagedActor]) -> Level:
    """A new Level whose actor dict is a shallow copy of `level.actors`, with only staged actors
    replaced by a copy carrying the staged Location -- never mutates `level` itself. Two sessions
    (or two Rebuilds of the same session) can safely overlay the same shared trunk Level concurrently,
    since neither ever writes into the original."""
    import copy
    new_actors = dict(level.actors)
    for name, staged_actor in staged.items():
        if name not in new_actors:
            continue
        actor_copy = copy.copy(new_actors[name])
        actor_copy.location = staged_actor.staged_location
        new_actors[name] = actor_copy
    overlaid = copy.copy(level)
    overlaid.actors = new_actors
    return overlaid
```

(Adjust field/attribute names to match the real `Level`/`Actor` class shapes found in Step 1 — this
plan's research digest confirmed `actor.location` is the mutated field in `edits.py`, but did not
confirm `Level`'s exact attribute name for its actor dict; verify `level.actors` is correct before
using it.)

- [ ] **Step 4: Implement the Rebuild handler's use of it**, under the per-session claim lock:

```python
def rebuild(session_id: str):
    session = sessions.get_session(sessions_root, session_id)
    ctx = _get_or_create_level_context(session.level)
    staged = staging_store.read_staged(session_id)
    overlaid = apply_staged_overlay(ctx.trunk_ref[0].level, staged)
    result = build_scene(overlaid, ...)  # exact remaining args per Step 1's read of build_scene
    polys, texture_table, actor_names_by_poly, geom_hash, light_hash = result
    with claims.lock_for(session_id):
        if not claims.check(session_id, request_claim_token):
            return  # superseded mid-solve -- drop the result, log it, do not write
        cached = _BuildResultCache.get((session.level, geom_hash, light_hash))
        if cached is None:
            build_cache.store_geometry(project, session.level, geom_hash, ...)
            build_cache.store_scene(project, session.level, geom_hash, light_hash, ...)
        build_pin.write_session_pointer(sessions_root, session_id, geom_hash, light_hash)
    return {"geom_hash": geom_hash, "light_hash": light_hash}
```

(This is illustrative of the required shape — the exact response body and status codes should match
`test_serve_app.py`'s existing request conventions; the claim token itself is the `X-Claim-Token`
header pinned above, used identically in Tasks 12, 13, 15, and 17.)

- [ ] **Step 5: Run, verify, commit**

```bash
git add uedcli/serve/app.py uedcli/serve/edits.py uedcli/tests/test_serve_app.py uedcli/tests/test_serve_edits.py
git commit -m "Rebuild solves on a copy of the trunk, writes the session's own build pin"
```

---

### Task 12: New session endpoints — create, list, get, delete

**Files:**
- Modify: `uedcli/serve/app.py`
- Test: `uedcli/tests/test_serve_app.py`

**Interfaces:**
- Produces: `POST /api/level/{level}/sessions` → `201 {"id", "level", "created_at", "claim_token"}`;
  `GET /api/sessions` → `200 {"sessions": [...]}`; `GET /api/session/{id}` → `200 {..., "claim_token"}`
  or `404`; `DELETE /api/session/{id}` → `204`/`404`/`409` per the spec's confirm-if-staged rule,
  requiring a valid claim token, closing every open WS connection for that session, calling
  `claims.forget(session_id)`.

- [ ] **Step 1: Write the failing tests** (one per spec behavior — creation mints a token, list
  returns every session, get 404s on unknown id, delete requires a matching claim token and 409s on
  non-empty staged edits without `?force=true`, delete closes WS connections). Follow
  `test_serve_app.py`'s existing `TestClient` conventions exactly.

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement the four routes**, wiring `sessions.py` (Task 6) and `claims.py` (Task 7).
  `create_app`'s signature changes here too: the startup `level: str` parameter becomes optional
  (`level: str | None = None`) — with no startup level, the process starts with zero `LevelContext`s,
  and the first session created (via `POST /api/level/{level}/sessions`, or the CLI's own default
  level argument if still provided) is what creates the first one. Confirm with the CLI entry point
  (`grep -rn "create_app(" uedcli/cli/`) whether `uedcli serve <level>` should still eagerly create a
  session for `<level>` at startup, or just record it as the frontend's fallback default (per the
  spec's "stays the default level for a bare URL with no session id") without server-side eager
  creation — the spec implies the latter (only a real page load creates a session), so `create_app`
  should NOT eagerly call `POST /api/level/{level}/sessions`-equivalent logic at startup; it just
  remembers `level` as `app.state.default_level` for `GET /api/health` or similar to report if useful,
  and does no more than that.

- [ ] **Step 4: Run to verify it passes, commit**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Add session CRUD endpoints: create, list, get, delete"
```

---

### Task 13: Re-route existing per-level verbs to per-session; Save promotes the level pin

**Files:**
- Modify: `uedcli/serve/app.py`
- Test: `uedcli/tests/test_serve_app.py`
- **Update: `uedcli/tests/test_serve_load_rebuild.py`** (7 of 9 tests drive `/load`/`/scene`/`/atlas`/
  `/lightmap` over the old per-level paths — re-point at the new session-scoped paths, creating a
  session first via `sessions.create_session(...)` per the plan's own "tests set up state via
  lower-level module functions" rule).
- **Update or delete: `uedcli/tests/test_serve_edits_routes.py`** (its entire subject — `/stage`,
  `/discard`, `/save`, `/staged`, `/load` over the old per-level paths — is retired by this task; keep
  any sub-test that still exercises something true once re-pointed at the session-scoped routes,
  delete/rewrite the rest, using judgment and explaining the calls in the report, same as Task 9's
  own precedent for `test_serve_load_rebuild.py`).
- **Fix the one dependent call site each** in `uedcli/tests/test_serve_scene.py` (`/scene`),
  `uedcli/tests/test_serve_lightmap.py` (`/lightmap`/`/scene`), and `uedcli/tests/test_serve_textures.py`
  (`/atlas`) — each has exactly one test still calling an old per-level path for these verbs.

(This file list was originally just the first two entries — a real gap this plan didn't originally
account for, caught by the implementer reading every existing caller of the eight retired routes
before writing any code, rather than guessing. Widening it here rather than leaving the plan's own
record inaccurate — same pattern as Task 9's own widening, `afa16f60`.)

**Interfaces:**
- Produces: `GET /api/session/{id}/scene|atlas|lightmap`, `POST
  /api/session/{id}/load|stage|discard|save` (rebuild already done in Task 11), `GET
  /api/session/{id}/staged` — same response shapes as today's per-level versions. `save` additionally
  calls `build_pin.write_level_pointer(project, session.level, *session_pin)` sequenced after the
  trunk write, under `ctx.trunk_lock` (not the per-session claim lock — this is the existing per-level
  write serialization, unchanged in purpose). **`load`/`stage`/`discard`/`save` all require the
  `X-Claim-Token` header, same as Task 11's `rebuild`** — every one of them mutates this session's own
  state (`load` bumps `last_seen_generation`, `stage`/`discard` write `staged.json`, `save` writes the
  trunk plus the level pin), so a stale token gets the identical `409` `rebuild` already gives. `GET
  .../scene|atlas|lightmap|staged` stay ungated reads, per the spec's "only writes are gated" rule.

- [ ] **Step 1: Read every existing per-level handler for `scene`/`atlas`/`lightmap`/`load`/`stage`/
  `discard`/`save`/`staged` in full.**

- [ ] **Step 2: Write the failing tests** — one per re-routed endpoint, confirming the new path
  works and the old `/api/level/{level}/...` path for these eight verbs is gone (404 or removed
  route). Also: a save with a `build.json` present promotes to `build/pin/<level>/current.json`; a
  save with no prior Rebuild leaves the level's existing pin untouched (per the spec); each of
  `load`/`stage`/`discard`/`save` returns `409` given a stale `X-Claim-Token` and never performs its
  write in that case (mirror Task 11's `test_rebuild_superseded_mid_solve_drops_the_result_without_error`
  shape for at least one of the four, e.g. `save`, since it's the highest-stakes write here).

- [ ] **Step 3: Run to verify it fails, implement each handler by re-keying its body from
  `level_name` to `session_id` (resolving `session.level` where the underlying logic still needs the
  level name — e.g. `build_cache`/`staging_store` calls), run to verify it passes, commit.**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Re-route scene/atlas/lightmap/load/stage/discard/save/staged to per-session paths"
```

---

### Task 14: `/status` endpoint and `/api/health` fix

**Files:**
- Modify: `uedcli/serve/app.py`
- Test: `uedcli/tests/test_serve_app.py`
- **Fix dependent call sites: `uedcli/tests/test_serve_load_rebuild.py`** (4 calls to the old
  `/api/level/{level}/status`, including one comment that wrongly asserts "`/status` stays
  per-level, unaffected" — it isn't, this task retires that route) and
  **`uedcli/tests/test_serve_edits_routes.py`** (1 call site) — both call the per-level `/status`
  route this task deletes.

(Widened here before dispatch, having grepped every test file for the old route's literal path —
same pattern as Tasks 9/13's own widened scopes, caught up front this time instead of via a
NEEDS_CONTEXT round-trip.)

**Interfaces:**
- Produces: `GET /api/session/{id}/status` → `{"changes_available": bool, "geometry_pinned": bool,
  "build_status": str}`, computing `changes_available` as `ctx.generation[0] >
  session.last_seen_generation`. `GET /api/health` → `{"status": "ok"}` (drops the old `"level"`
  field).

- [ ] **Step 1: Write the failing tests** — status reflects a session's own `geometry_pinned`
  independent of another session's on the same level; `changes_available` is `False` right after
  create, becomes `True` after another session Saves on the same level (bumping `ctx.generation`),
  and a `load` call clears it back to `False` for that session only.

- [ ] **Step 2-5: Run, implement, run, commit** (same cycle as prior tasks).

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Add per-session /status endpoint; drop stale level field from /api/health"
```

---

### Task 15: WS claim-token handshake and `superseded` message

**Files:**
- Modify: `uedcli/serve/app.py` (`ws_endpoint`)
- Test: `uedcli/tests/test_serve_app.py` (FastAPI's `TestClient.websocket_connect`)
- **Fix the one dependent call site: `uedcli/tests/test_serve_ws_reload.py`** — its single test
  connects to `/ws` with no `session`/`claim` query params at all; once the handshake requires
  them, this connect needs a real session created first and its claim token passed in the URL.

(Widened here before dispatch, having grepped every test file for `websocket_connect` — same
proactive pattern as Task 14's own widening.)

**Interfaces:**
- Produces: `WS /ws?session={id}&claim={token}` — refuses the upgrade (closes immediately with a
  clear reason) if `claim` doesn't pass `claims.check`; on a later `claims.mint` superseding this
  connection's token, the server sends `{"type": "superseded"}` then closes this connection.

- [ ] **Step 1: Write the failing tests** — a valid claim connects fine; a stale claim's connect is
  refused; minting a new claim for a session with an open WS causes that WS to receive
  `{"type": "superseded"}` then close.

- [ ] **Step 2-5: Run, implement, run, commit.**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Add claim token to WS handshake; send superseded message before closing a stale connection"
```

---

### Task 16: Frontend — session id in URL, remove level-switch machinery, session dropdown

**Files:**
- Create: `web/src/session/SessionContext.tsx`, `web/src/session/SessionDropdown.tsx`,
  `web/src/session/SessionContext.test.tsx`, `web/src/session/SessionDropdown.test.tsx`
- Delete: `web/src/panels/LevelPicker.tsx`, `web/src/panels/LevelPicker.test.tsx` (its dedicated test
  file — deleting the component without it leaves a test file with nothing left to test).
- Modify: `web/src/App.tsx` (remove `handleSwitchLevel`/`levelSwitching`/`levelSwitchError`, mount
  `SessionContext`), `web/src/api.ts` (session-scoped endpoints), `web/src/App.test.tsx`

(Widened by one file before dispatch — same proactive pattern as Tasks 14/15's own widenings.)

**Interfaces:**
- Produces: `SessionContext` provides `{ sessionId, level, view: 'editing' | 'notfound' | 'closed',
  claimToken, createSession(level), reload() }` to the app tree. `SessionDropdown` lists every
  session from `GET /api/sessions`, grouped by level, with a "switch to" action that navigates
  (`window.location` or a router, matching whatever `App.tsx` already uses for URL state — read it
  first, there is currently no router per the earlier research, so this likely stays plain
  `history.replaceState`/`window.location.search` manipulation, not a new routing library).

- [ ] **Step 1: Read `App.tsx`, `api.ts`, `LevelPicker.tsx` in full.**

- [ ] **Step 2: Write the failing tests** for `SessionContext` (empty URL → auto-creates and updates
  URL; a bad `?session=` id → `notfound` view with the id shown, no auto-create; closing this tab's
  own session → `closed` view, no auto-navigate) and `SessionDropdown` (renders sessions grouped by
  level from a mocked fetch; clicking one navigates). Follow `App.test.tsx`'s existing `mockFetch`
  URL-router pattern and `vi.mock` style exactly.

- [ ] **Step 3: Run to verify it fails.**

- [ ] **Step 4: Implement** `SessionContext.tsx`, `SessionDropdown.tsx`; delete `LevelPicker.tsx`;
  remove `handleSwitchLevel`/`levelSwitching`/`levelSwitchError` and the `PUT /api/level` call from
  `App.tsx` and `api.ts`; update `api.ts`'s request functions to take a `sessionId` instead of
  `level` and hit `/api/session/{id}/...` paths.

- [ ] **Step 5: Update `App.test.tsx`**: remove/replace every test asserting on the old level-switch
  behavior (the "unload-then-block" and "restore-on-failure" cases named in this plan's research)
  with equivalent session-switch behavior through `SessionDropdown`.

- [ ] **Step 6: Run to verify it passes, commit.**

```bash
git add web/src/session/ web/src/App.tsx web/src/api.ts web/src/App.test.tsx
git rm web/src/panels/LevelPicker.tsx
git commit -m "Replace level-switch machinery with session id in URL + session dropdown"
```

---

### Task 17: Frontend — claim-token wiring, superseded takeover, per-session status/banner, unsaved copy

**Files:**
- Modify: `web/src/session/SessionContext.tsx`, `web/src/api.ts`, `web/src/reload.ts`, `web/src/App.tsx`
- Modify: `web/src/session/SessionContext.test.tsx`
- **Modify: `web/src/panels/SaveBar.tsx`** — the only two real user-facing "staged" copy violations
  left in the whole frontend (verified by grepping every `.tsx` file, excluding internal
  identifiers/comments): `{stagedNames.size} staged move{...}` and "Or discard one actor's staged
  edit, leaving the rest staged:". No literal "Stage"-labeled button exists anywhere in the current
  UI (also verified) — the brief's own "'Stage a move'-equivalent button" phrasing doesn't match any
  real button in this codebase; don't invent one, just fix these two real strings.

(Widened here before dispatch, having grepped every `.tsx` file for real "Stage"/"Staged" copy —
same proactive pattern as Tasks 14-16's own widenings.)

**Interfaces:**
- Produces: every mutating `api.ts` call attaches the current claim token as an `X-Claim-Token`
  request header (matching Task 11's backend convention); `reload.ts`'s WS subscription passes `claim`
  on the URL and
  treats `{"type": "superseded"}` — and only that message, never a bare `onclose` — as the trigger for
  `SessionContext`'s `view` to become `'superseded'`; `App.tsx` renders the full-page takeover ("This
  session is now open in another window. Reload to keep using it here." + a Reload button) for that
  view, and also treats any mutating call's `409` response the same way (the fallback path if the WS
  message was ever lost). All remaining "Staged"/"Stage" copy in the UI (button labels, counts, confirm
  dialogs) becomes "Unsaved"/the real action name, per the spec's naming decision.

- [ ] **Step 1: Write the failing tests** — a mutating call attaches the claim token; receiving
  `{"type":"superseded"}` over the mocked WS flips the view and shows the takeover; an ordinary WS
  close (no message) does NOT show the takeover and instead triggers a reconnect attempt; a `409` from
  any mutating call also shows the takeover; the "Stage a move"-equivalent button is now labeled with
  the real action, and any "Staged: N" label reads "Unsaved: N".

- [ ] **Step 2-5: Run, implement, run, commit.**

```bash
git add web/src/session/ web/src/api.ts web/src/reload.ts web/src/App.tsx
git commit -m "Wire claim tokens end-to-end; superseded takeover; unsaved copy throughout"
```

---

## Self-Review

**Spec coverage** — every numbered spec section has a task:
Problem/Goals → Tasks 6,7,9,12 (session existence, no auto-expiry, multi-level). Non-goals → nothing
to implement (deferred). Session identity & lifecycle (incl. claim tokens) → Tasks 6,7,12,15,16,17.
Storage layout (incl. build/pin restoration, atomic writes, corrupt-file posture) → Tasks 1,2,3,4,5,6.
Multi-level concurrent serving (incl. unthrottled Rebuild) → Tasks 9,11. Build cache & dedup (incl.
OQ1, in-memory cache, reference-aware eviction, config validation) → Tasks 2,3,8,10,11. Cleanup (no
auto-expiry) → Task 6 (no expiry logic exists at all — correctly, nothing to build). API surface (incl.
Save promoting the pin, DELETE's WS cleanup, /status, /api/health) → Tasks 12,13,14,15. Frontend
changes (incl. removing level-switch machinery, unsaved copy) → Tasks 16,17.

**Placeholder scan** — no "TBD"/"handle appropriately" strings. An earlier draft of this plan left two
decisions open (Task 9/Task 12's ordering; the claim-token transport). Both are now resolved outright
rather than deferred: the "tests set up state via lower-level module functions" rule
(`Global Constraints`) removes the Task 9/12 circular dependency structurally — Task 9's tests call
`_get_or_create_level_context` directly, never through Task 12's endpoint — and the claim token is
pinned as an `X-Claim-Token` header everywhere it appears (Tasks 11, 12, 13, 15, 17), not left as a
per-task choice.

**Type consistency** — checked `StagingStore.stage`'s parameter names (`session_id`, `actor_name`,
`actor_t3d_text`, `baseline_location`, `staged_location`) are used identically in Tasks 5, 11, 13;
`build_cache`'s `load_geometry`/`store_geometry`/`load_scene`/`store_scene` signatures are used
identically in Tasks 3, 4, 11; `SessionRecord`'s field names (`id`, `level`, `created_at`,
`last_active_at`, `last_seen_generation`) are used identically in Tasks 6, 12, 14; `ClaimRegistry`'s
`mint`/`check`/`lock_for`/`forget` are used identically in Tasks 7, 11, 12, 15.

---

## Execution

This plan uses **subagent-driven-development**: dispatch a fresh subagent per task in dependency
order (Tasks 1-8 have no cross-dependencies beyond earlier tasks in the list and can mostly proceed
sequentially; Tasks 9-15 are sequentially dependent on each other and on 1-8; Tasks 16-17 depend on
12-15 being merged first), review between tasks, fix findings before moving on.
