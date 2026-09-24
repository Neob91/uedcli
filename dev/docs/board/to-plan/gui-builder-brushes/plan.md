# GUI Builder Brushes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a UED22-style builder brush to the GUI — build a parametric shape, see it as the
scratch red brush (one ordinary actor under a reserved Name, always present in `/scene`), reposition/
rotate/re-shape it, then press Add or Subtract to clone it into a new placed brush with that CSG
operation, reaching the trunk only on the existing Save action.

**Architecture:** A new `uedcli/serve/builder_brush.py` module owns the builder brush's own state —
a per-session working-copy file and a per-level persisted file, neither the trunk nor `StagingStore`.
The existing `POST /stage`/`/discard`/`/save` routes each grow ONE dispatch branch recognizing the
reserved Name and routing to this module instead of `StagingStore`; every other Name's behavior is
byte-for-byte unchanged. `GET /scene` grows one narrow overlay appending the builder brush's own
`SceneActor` entry, built through the exact per-actor path every trunk actor already goes through.
Add/Subtract clone the builder brush into a brand-new actor staged in the *existing* `StagingStore`
(which gains one new "stage a whole new actor" capability), reaching the trunk only via the ordinary
Save flow.

**Tech Stack:** Python (FastAPI, `uedcli/serve/`), TypeScript/React (`web/src/`), Vitest.

**Spec:** `dev/docs/board/to-plan/gui-builder-brushes/spec.md`

## Global Constraints

- No new CLI verb, flag, or `--tree` kind — the CLI is never touched by this feature (spec
  "Non-goals").
- The reserved builder-brush Name is `*Builder` (illegal as a real UnrealEngine object name —
  FNames are alnum/underscore only; spec "Data model").
- `StagingStore`'s own code (`uedcli/serve/snapshots.py`, `uedcli/serve/edits.py`) must need ZERO new
  cases for real (non-`*Builder`) actors anywhere in this plan — the dispatch lives in the route
  handlers (`uedcli/serve/app.py`), never inside `StagingStore`/`edits.py` themselves (spec
  "Background").
- `POST /stage`'s generalized wire shape (`{"actors": {name: {prop: value, ...}}}`) is uniform for
  every actor; only `*Builder`'s map is applied generically. A real actor's map still only honors a
  `Location` key — any other key is a clean 422 (`CommandError`) naming the actor and the rejected
  property, all-or-nothing (spec "API surface").
- `POST /discard` is a true no-op for `*Builder`, both filtered and whole-session forms (spec "Data
  model").
- `.uedcli/` layout: `build/cache/` → `cache/build/`, `preview/` → `cache/preview/`,
  `build/pin/<level>/current.json` → `levels/<level>/build.json` (one file, `{geom_hash,
  light_hash}`), new `levels/<level>/builder-brush.json` and `sessions/<sid>/builder-brush.json`
  (spec "On-disk layout").
- No Python exception ever reaches an HTTP caller unclassified — raise `uedcli.cli.errors.
  CommandError` (already mapped to 422 by `uedcli/serve/errors.py::error_to_status`) for every
  user-facing validation failure this feature introduces; never a bare exception.
- `spiral` is excluded from the builder-brush shape registry (multi-actor output, no single-actor
  representation).

---

## File Structure

**Backend — create:**
- `uedcli/serve/builder_brush.py` — the builder brush's own state: reserved-Name constant, default
  shape, session-box read/write/seed, level-box read/write, build (shape rebuild), prop-set, and the
  Add/Subtract clone.
- `uedcli/serve/builder_registry.py` — `GET /api/builders`'s shape registry, introspected from
  `uedcli/cli/parsers/brush.py`'s argparse tree, plus the hand-authored icon table.
- `uedcli/tests/test_builder_brush.py`
- `uedcli/tests/test_builder_registry.py`

**Backend — modify:**
- `uedcli/build_cache.py` — `_dir()`'s path prefix (`build/cache` → `cache/build`).
- `uedcli/preview_game.py` — `_preview_dir()`'s path (`preview` → `cache/preview`).
- `uedcli/serve/build_pin.py` — `level_pointer_path()`'s path (`build/pin/<level>/current.json` →
  `levels/<level>/build.json`).
- `uedcli/builders.py` — add `swap_polys(target: Brush, incoming: Brush) -> None`, extracted from
  `uedcli/cli/commands/brush/edit.py`'s `_replace()`.
- `uedcli/cli/commands/brush/edit.py` — `_replace()` calls the extracted `builders.swap_polys`
  instead of inlining the swap (behavior unchanged).
- `uedcli/serve/snapshots.py` — `StagingStore` gains `stage_new`/`read_staged_new_actors`.
- `uedcli/serve/edits.py` — `save_staged` applies every staged new actor into the trunk.
- `uedcli/serve/scene.py` — extract `_build_one_actor` from `_build_actors`'s loop body (pure
  refactor, `_build_actors` unchanged in behavior); `session_scene` calls it once more for the
  overlay.
- `uedcli/serve/app.py` — new routes (`GET /api/builders`, `POST .../builder-brush/build`, `/add`,
  `/subtract`); `session_stage`/`session_discard`/`session_save`/`create_session_route` each gain one
  dispatch branch.
- `uedcli/tests/test_build_cache.py`, `uedcli/tests/test_serve_build_pin.py` — path assertions
  updated to the new layout.

**Frontend — create:**
- `web/src/panels/BuilderBrushPanel.tsx` — shape picker, param form, Location/Rotation controls,
  Add/Subtract buttons.
- `web/src/panels/BuilderBrushPanel.test.tsx`

**Frontend — modify:**
- `web/src/api.ts` — generalize `postStage`'s type from `Record<string, [number,number,number]>` to
  `Record<string, Record<string, string>>`; add `fetchBuilders`, `postBuilderBrushBuild`,
  `postBuilderBrushAdd`, `postBuilderBrushSubtract`.
- `web/src/scene/Viewport3D.tsx:560`, `web/src/scene/OrthoViewport.tsx:435` — the only two real
  `postStage(...)` call sites (confirmed via `grep -rn "postStage(" web/src` — `SaveBar.tsx` imports
  `postDiscard`/`postSave` only, never `postStage`) — migrate both to the new per-actor prop-map
  shape (Location-only payload, new wire shape).
- `web/src/App.tsx` — mounts `BuilderBrushPanel`, passes `sessionId`.

---

## Backend Tasks

### Task 1: Rename `.uedcli/` cache and pin paths

**Files:**
- Modify: `uedcli/build_cache.py:33-35` (`_dir`), module docstring lines 6-7.
- Modify: `uedcli/preview_game.py:143-146` (`_preview_dir`), line 96 comment, line 189 comment.
- Modify: `uedcli/serve/build_pin.py:45-46` (`level_pointer_path`), docstring line 3-4.
- Test: `uedcli/tests/test_build_cache.py`, `uedcli/tests/test_serve_build_pin.py`.

**Interfaces:**
- Produces: `build_cache._dir(project, level_name) -> Path` now under `cache/build/`;
  `preview_game._preview_dir(project) -> Path` now `cache/preview/`; `build_pin.level_pointer_path
  (project, level_name) -> Path` now `levels/<level>/build.json`.

- [ ] **Step 1: Write the failing tests**

In `uedcli/tests/test_build_cache.py`, find the existing test asserting `_dir`'s path (adjust the
existing assertion rather than adding a duplicate):

```python
def test_dir_uses_cache_build_prefix(tmp_path):
    project = _make_project(tmp_path)
    d = build_cache._dir(project, "MyLevel")
    assert d == tmp_path / ".uedcli" / "cache" / "build" / f"v{build_cache._CACHE_VERSION}" / "MyLevel"
```

In `uedcli/tests/test_serve_build_pin.py`:

```python
def test_level_pointer_path_uses_levels_prefix(tmp_path):
    project = _make_project(tmp_path)
    p = build_pin.level_pointer_path(project, "MyLevel")
    assert p == tmp_path / ".uedcli" / "levels" / "MyLevel" / "build.json"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "test_dir_uses_cache_build_prefix or test_level_pointer_path_uses_levels_prefix" -v`
Expected: FAIL — old paths still under `build/cache`/`build/pin`.

- [ ] **Step 3: Update the three path functions**

`uedcli/build_cache.py`:
```python
root = config.state_subdir(project.root, "cache/build", create=True)
```

`uedcli/preview_game.py`:
```python
return config.state_subdir(project.root, "cache/preview", create=True)
```

`uedcli/serve/build_pin.py`:
```python
return config.state_subdir(project.root, "levels", create=False) / level_name / "build.json"
```

Update each function's docstring/module comment to match (grep the file for the old path string
first — `build/cache`, `build/pin`, `preview/` — and fix every mention, not just the code).

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test -k "test_build_cache or test_serve_build_pin" -v`
Expected: PASS, full module.

- [ ] **Step 5: Commit**

```bash
git add uedcli/build_cache.py uedcli/preview_game.py uedcli/serve/build_pin.py \
  uedcli/tests/test_build_cache.py uedcli/tests/test_serve_build_pin.py
git commit -m "Rename .uedcli cache/pin paths to cache/build, cache/preview, levels/<level>/build.json"
```

---

### Task 2: Extract `builders.swap_polys`

**Files:**
- Modify: `uedcli/builders.py` (add `swap_polys` near `make_brush_actor`).
- Modify: `uedcli/cli/commands/brush/edit.py:537-541` (`_replace`).
- Test: `uedcli/tests/test_builders.py` (confirmed to exist — `builders.py`'s existing test file).

**Interfaces:**
- Produces: `builders.swap_polys(target: Brush, incoming: Brush) -> None` — mutates `target.polys`
  in place to `incoming.polys`; leaves `target.model_name` and every other field untouched.

- [ ] **Step 1: Write the failing test**

```python
def test_swap_polys_replaces_only_polys():
    target = builders.cube(100.0, 100.0, 100.0)
    target_model_name = target.model_name
    incoming = builders.cylinder(200.0, 50.0, sides=6)
    builders.swap_polys(target, incoming)
    assert target.polys == incoming.polys
    assert target.model_name == target_model_name   # untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test -k test_swap_polys_replaces_only_polys -v`
Expected: FAIL — `AttributeError: module 'builders' has no attribute 'swap_polys'`.

- [ ] **Step 3: Add `swap_polys` to `uedcli/builders.py`**

```python
def swap_polys(target: Brush, incoming: Brush) -> None:
    """In-place SHAPE SWAP: replace ONLY `target.polys` with `incoming.polys`. `target.model_name`
    and every other Brush field are untouched — the caller is responsible for validating the result
    (`geometry.validate_brush`) before persisting it."""
    target.polys = incoming.polys
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test -k test_swap_polys_replaces_only_polys -v`
Expected: PASS.

- [ ] **Step 5: Wire `_replace()` to call it (behavior-preserving refactor)**

In `uedcli/cli/commands/brush/edit.py`, replace the inline swap at lines 537-541:

```python
target.brush.polys = incoming[0].brush.polys
validate_brush(target.brush)
```

with:

```python
builders.swap_polys(target.brush, incoming[0].brush)
validate_brush(target.brush)
```

Add `from ... import builders` (or the correct relative import — check the file's existing import
block for the established alias) if not already imported.

- [ ] **Step 6: Run the full brush-replace test suite to confirm no behavior change**

Run: `bin/test -k test_brush_replace -v`
Expected: PASS, identical to before this change (this is a pure refactor).

- [ ] **Step 7: Commit**

```bash
git add uedcli/builders.py uedcli/cli/commands/brush/edit.py uedcli/tests/test_builders.py
git commit -m "Extract builders.swap_polys from brush replace's inline poly swap"
```

---

### Task 3: `builder_brush.py` — reserved Name, default shape, level-box store

**Files:**
- Create: `uedcli/serve/builder_brush.py`.
- Test: `uedcli/tests/test_builder_brush.py`.

**Interfaces:**
- Consumes: `builders.cube`, `builders.make_brush_actor`, `normalize.canonical_actor_t3d`,
  `model.parse_t3d_actors`, `config.state_subdir`, `uedcli.serve.atomic_io.atomic_write_json`.
- Produces:
  - `RESERVED_NAME: str = "*Builder"`
  - `default_actor() -> Actor` — a fresh `Actor` for a level with no persisted builder brush yet.
  - `class LevelBoxCorruptError(Exception)`
  - `level_box_path(project, level_name: str) -> Path`
  - `load_level_box(project, level_name: str) -> Actor | None` — `None` when no file exists yet
    (a brand-new level); raises `LevelBoxCorruptError` on a malformed/unreadable existing file
    (corrupt-and-instruct, per spec "Error handling" — NOT silent-degrade).
  - `write_level_box(project, level_name: str, actor: Actor) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# uedcli/tests/test_builder_brush.py
from decimal import Decimal
from uedcli import builder_brush


def _make_project(tmp_path):
    ... # match the fixture pattern in test_build_cache.py / test_serve_build_pin.py exactly


def test_default_actor_is_a_solid_cube_csg_add():
    actor = builder_brush.default_actor()
    assert actor.brush is not None
    assert dict(actor.props).get("CsgOper", "CSG_Add") in (None, "CSG_Add")


def test_load_level_box_returns_none_when_absent(tmp_path):
    project = _make_project(tmp_path)
    assert builder_brush.load_level_box(project, "MyLevel") is None


def test_write_then_load_level_box_round_trips(tmp_path):
    project = _make_project(tmp_path)
    actor = builder_brush.default_actor()
    builder_brush.write_level_box(project, "MyLevel", actor)
    loaded = builder_brush.load_level_box(project, "MyLevel")
    assert loaded.brush.polys == actor.brush.polys


def test_load_level_box_corrupt_file_raises(tmp_path):
    project = _make_project(tmp_path)
    p = builder_brush.level_box_path(project, "MyLevel")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not json", encoding="utf-8")
    import pytest
    with pytest.raises(builder_brush.LevelBoxCorruptError):
        builder_brush.load_level_box(project, "MyLevel")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k test_builder_brush -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uedcli.builder_brush'`.

- [ ] **Step 3: Write `uedcli/serve/builder_brush.py` (Part 1 of 3 — this task's slice)**

```python
"""The builder brush's own state — a scratch, not-yet-placed brush actor exposed to the GUI as one
ordinary reserved-Name actor. Neither the trunk nor `StagingStore`: `levels/<level>/
builder-brush.json` is the per-level persisted copy (this module), `sessions/<sid>/
builder-brush.json` is a session's own working copy (Task 4). See `dev/docs/board/to-plan/
gui-builder-brushes/spec.md` "Data model"."""
from __future__ import annotations

import json
from pathlib import Path

from .. import builders, config, model, normalize
from .atomic_io import atomic_write_json

RESERVED_NAME = "*Builder"


def default_actor() -> object:
    """A fresh builder brush for a level with no persisted state yet: a small cube at the world
    origin, `CsgOper` defaulted to `CSG_Add` (an inert default — never shown or settable through
    `prop`, see spec "Non-goals"; irrelevant once Add/Subtract stamps its own value on the clone)."""
    brush = builders.cube(256.0, 256.0, 256.0)
    return builders.make_brush_actor(RESERVED_NAME, brush, location=(0.0, 0.0, 0.0), csg="add")


class LevelBoxCorruptError(Exception):
    pass


def level_box_path(project, level_name: str) -> Path:
    return config.state_subdir(project.root, "levels", create=False) / level_name / \
        "builder-brush.json"


def load_level_box(project, level_name: str):
    """`None` when the level has never had a builder brush persisted (a brand-new level) — the
    caller (session creation, Task 4) falls back to `default_actor()`. Raises
    `LevelBoxCorruptError` on any read/parse failure of an EXISTING file — corrupt-and-instruct,
    deliberately NOT silent-degrade (spec "Error handling": a persisted builder brush is the user's
    actual placed shape, not a regenerable cache entry)."""
    p = level_box_path(project, level_name)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        actors = model.parse_t3d_actors(data["actor_t3d"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise LevelBoxCorruptError(
            f"level {level_name!r}: builder brush at {p} is missing or unreadable: {exc}") from exc
    if len(actors) != 1:
        raise LevelBoxCorruptError(
            f"level {level_name!r}: builder brush at {p} does not decode to exactly one actor")
    return actors[0]


def write_level_box(project, level_name: str, actor) -> None:
    atomic_write_json(level_box_path(project, level_name),
                       {"actor_t3d": normalize.canonical_actor_t3d(actor)})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test -k test_builder_brush -v`
Expected: PASS for all four Task-3 tests.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/builder_brush.py uedcli/tests/test_builder_brush.py
git commit -m "builder_brush: reserved Name, default shape, level-box store"
```

---

### Task 4: `builder_brush.py` — session-box store and seeding

**Files:**
- Modify: `uedcli/serve/builder_brush.py`.
- Modify: `uedcli/tests/test_builder_brush.py`.

**Interfaces:**
- Consumes: Task 3's `default_actor`, `load_level_box`.
- Produces:
  - `class SessionBoxCorruptError(Exception)`
  - `session_box_path(sessions_root: Path, session_id: str) -> Path`
  - `load_session_box(sessions_root: Path, session_id: str) -> Actor` — raises
    `SessionBoxCorruptError` if the file exists but is unreadable; raises the same if the file is
    simply MISSING (a session must always have been seeded — see `seed_session_box`) — this mirrors
    `build_pin.SessionPointerCorruptError`'s corrupt-and-instruct posture for "this session's own
    unsaved work" (spec "Error handling").
  - `write_session_box(sessions_root: Path, session_id: str, actor) -> None`.
  - `seed_session_box(project, level_name: str, sessions_root: Path, session_id: str) -> None` —
    called once at session creation (Task 12) and by `reset` (the `/discard` no-op path is Task 12;
    this function is also reused there in a later task's dispatch, but is defined here as the pure
    "seed from level box or default" operation).

- [ ] **Step 1: Write the failing tests**

```python
def test_load_session_box_missing_raises(tmp_path):
    import pytest
    with pytest.raises(builder_brush.SessionBoxCorruptError):
        builder_brush.load_session_box(tmp_path / "sessions", "sid1")


def test_seed_session_box_uses_level_box_when_present(tmp_path):
    project = _make_project(tmp_path)
    level_actor = builder_brush.default_actor()
    level_actor.brush.polys = builders.cylinder(50.0, 20.0).polys   # distinguishable from default
    builder_brush.write_level_box(project, "MyLevel", level_actor)
    builder_brush.seed_session_box(project, "MyLevel", tmp_path / "sessions", "sid1")
    seeded = builder_brush.load_session_box(tmp_path / "sessions", "sid1")
    assert seeded.brush.polys == level_actor.brush.polys


def test_seed_session_box_uses_default_when_level_box_absent(tmp_path):
    project = _make_project(tmp_path)
    builder_brush.seed_session_box(project, "MyLevel", tmp_path / "sessions", "sid1")
    seeded = builder_brush.load_session_box(tmp_path / "sessions", "sid1")
    assert seeded.brush.polys == builder_brush.default_actor().brush.polys
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "test_load_session_box or test_seed_session_box" -v`
Expected: FAIL — functions don't exist.

- [ ] **Step 3: Add the session-box functions to `uedcli/serve/builder_brush.py`**

```python
class SessionBoxCorruptError(Exception):
    pass


def session_box_path(sessions_root: Path, session_id: str) -> Path:
    return Path(sessions_root) / session_id / "builder-brush.json"


def load_session_box(sessions_root: Path, session_id: str):
    """Corrupt-and-instruct, same posture as `build_pin.SessionPointerCorruptError` — this is the
    session's own unsaved work, not a regenerable cache. A MISSING file is treated the same as
    corrupt: every session must be seeded (`seed_session_box`) before this is ever called, so an
    absent file means the seeding step was skipped, a real bug to surface rather than paper over."""
    p = session_box_path(sessions_root, session_id)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        actors = model.parse_t3d_actors(data["actor_t3d"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SessionBoxCorruptError(
            f"session {session_id!r}: builder brush at {p} is missing or unreadable: {exc}") from exc
    if len(actors) != 1:
        raise SessionBoxCorruptError(
            f"session {session_id!r}: builder brush at {p} does not decode to exactly one actor")
    return actors[0]


def write_session_box(sessions_root: Path, session_id: str, actor) -> None:
    atomic_write_json(session_box_path(sessions_root, session_id),
                       {"actor_t3d": normalize.canonical_actor_t3d(actor)})


def seed_session_box(project, level_name: str, sessions_root: Path, session_id: str) -> None:
    """Seed a session's builder-brush working copy from the level's persisted box, or a fresh
    default cube when the level has none yet. Called ONCE, at session creation — never again for
    that session's lifetime (session-pinned, spec "Data model"; `/discard` is a no-op for the
    builder brush, it does NOT re-seed)."""
    actor = load_level_box(project, level_name)
    if actor is None:
        actor = default_actor()
    write_session_box(sessions_root, session_id, actor)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test -k "test_load_session_box or test_seed_session_box" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/builder_brush.py uedcli/tests/test_builder_brush.py
git commit -m "builder_brush: session-box store and one-time creation seeding"
```

---

### Task 5: `builder_brush.py` — build (shape rebuild)

**Files:**
- Modify: `uedcli/serve/builder_brush.py`.
- Modify: `uedcli/tests/test_builder_brush.py`.

**Interfaces:**
- Consumes: Task 2's `builders.swap_polys`, Task 4's `load_session_box`/`write_session_box`,
  `geometry.validate_brush`, `builders.<shape>` functions.
- Produces: `build(sessions_root: Path, session_id: str, shape: str, params: dict) -> Actor` —
  rebuilds the session box's `PolyList` only; raises `CommandError` for an unknown `shape` or invalid
  `params` (bad type/missing required key). A degenerate result raises `geometry.GeometryError`
  (`uedcli/geometry.py:20`, `class GeometryError(ValueError)`) UNWRAPPED — same as `_replace()`'s own
  `validate_brush(target.brush)` call (`edit.py:541`) — not `CommandError`; both are already
  classified to a clean 422 by `uedcli/serve/errors.py::error_to_status`, so no new exception
  handling is needed here, but a test must `pytest.raises(GeometryError)` for this case, not
  `CommandError`.

- [ ] **Step 1: Write the failing tests**

```python
def test_build_replaces_only_polys_leaves_location(tmp_path):
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    moved = builder_brush.load_session_box(sessions_root, "sid1")
    moved.location = (Decimal(100), Decimal(200), Decimal(300))
    builder_brush.write_session_box(sessions_root, "sid1", moved)

    result = builder_brush.build(sessions_root, "sid1", "cylinder",
                                 {"height": 128.0, "radius": 64.0, "sides": 12})
    assert result.location == (Decimal(100), Decimal(200), Decimal(300))
    reloaded = builder_brush.load_session_box(sessions_root, "sid1")
    assert reloaded.brush.polys == result.brush.polys


def test_build_unknown_shape_raises_command_error(tmp_path):
    from uedcli.cli.errors import CommandError
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    import pytest
    with pytest.raises(CommandError):
        builder_brush.build(sessions_root, "sid1", "nonexistent_shape", {})


def test_build_cylinder_align_to_side_becomes_angle_offset(tmp_path):
    # Regression: builders.cylinder has no align_to_side kwarg at all -- an earlier version of this
    # function passed the registry's raw params straight through and raised TypeError for every
    # align_to_side=True request. Confirm it now builds successfully and actually rotates the
    # cross-section (half a segment = 180/sides degrees), matching build.py's own
    # _align_offset_degrees.
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    aligned = builder_brush.build(sessions_root, "sid1", "cylinder",
                                  {"height": 100.0, "radius": 50.0, "sides": 8,
                                   "align_to_side": True})
    unaligned = builders.cylinder(100.0, 50.0, sides=8, angle_offset=0.0)
    aligned_direct = builders.cylinder(100.0, 50.0, sides=8, angle_offset=180.0 / 8)
    assert aligned.brush.polys == aligned_direct.polys
    assert aligned.brush.polys != unaligned.polys


def test_build_cylinder_rejects_fewer_than_3_sides(tmp_path):
    from uedcli.cli.errors import CommandError
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    import pytest
    with pytest.raises(CommandError):
        builder_brush.build(sessions_root, "sid1", "cylinder",
                            {"height": 100.0, "radius": 50.0, "sides": 2})


def test_build_sheet_direct_pass_no_flags_param(tmp_path):
    # sheet's --flag/flags is excluded from the registry entirely (owner ruling: GUI builder
    # brushes dictate shape only) -- confirm the direct-pass path builds correctly with just its
    # shape params, and that build() never needs to accept a "flags" key for sheet at all.
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    result = builder_brush.build(sessions_root, "sid1", "sheet",
                                 {"width": 100.0, "height": 100.0, "plane": "xz"})
    direct = builders.sheet(100.0, 100.0, "xz")
    assert result.brush.polys == direct.polys
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k test_build -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Add `build` to `uedcli/serve/builder_brush.py`**

**Real per-shape adapters, not blind `fn(**params)`.** The registry's params come straight off each
shape's argparse subparser (Task 11) — but the CLI itself doesn't call `builders.<shape>(**args)`
directly either; `uedcli/cli/commands/brush/build.py`'s `_build_brushes()` (lines 160-201) does real
adapter work first for 2 of these 5 shapes, which this function must replicate exactly (verified
against that real code):

- **cylinder/cone**: `--sides` is validated `>= 3` BEFORE use (`build.py:176-178` — an unchecked
  `sides` of 0 or 1 would divide-by-zero in the very next line); the boolean `align_to_side` becomes
  a computed `angle_offset` (`_align_offset_degrees`, `build.py:71-79`: `180.0 / sides if
  align_to_side else 0.0`) — `builders.cylinder`/`cone` have NO `align_to_side` parameter at all.
- **cube/sheet/staircase**: no adapter needed. The CLI passes `args.width`/`args.breadth`/
  `args.height` (cube), `args.width`/`args.height`/`args.plane` (sheet — `args.flags`/`--flag` is
  EXCLUDED from the registry entirely per the owner's "GUI builder brushes dictate shape only" ruling,
  spec "Builder registry"; sheet's `extra_flags` kwarg is simply never set here), and
  `args.steps`/`args.depth`/`args.rise`/`args.breadth` (staircase) straight through (`build.py:
  167-168, 183, 184-185`), and the registry's params for these three shapes are exactly those same
  names — a direct `fn(**params)` call is correct for all three.

```python
from ..cli.errors import CommandError
from ..geometry import validate_brush

_DIRECT_SHAPES = {"cube", "sheet", "staircase"}   # no CLI-side adapter needed, `fn(**params)` is correct


def _build_incoming(shape: str, params: dict):
    if shape in _DIRECT_SHAPES:
        fn = getattr(builders, shape)
        return fn(**params)
    if shape in ("cylinder", "cone"):
        p = dict(params)
        sides = p.get("sides", 8)
        if sides < 3:
            raise CommandError(f"builder-brush build {shape}: sides must be at least 3, got {sides}")
        align_to_side = p.pop("align_to_side", False)
        p["angle_offset"] = 180.0 / sides if align_to_side else 0.0
        fn = builders.cylinder if shape == "cylinder" else builders.cone
        return fn(**p)
    raise CommandError(f"unknown builder-brush shape: {shape!r}")


def build(sessions_root: Path, session_id: str, shape: str, params: dict):
    try:
        incoming = _build_incoming(shape, params)
    except TypeError as exc:
        raise CommandError(f"invalid params for shape {shape!r}: {exc}") from exc
    actor = load_session_box(sessions_root, session_id)
    swap_polys(actor.brush, incoming)
    validate_brush(actor.brush)
    write_session_box(sessions_root, session_id, actor)
    return actor
```

(`builders.swap_polys` is imported at module scope already from Task 2's addition — reuse the
existing `from .. import builders` import, calling it as `builders.swap_polys`; the snippet above
uses the bare name for brevity, adjust to `builders.swap_polys(actor.brush, incoming)` to match this
module's actual import style.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test -k test_build -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/builder_brush.py uedcli/tests/test_builder_brush.py
git commit -m "builder_brush: build (shape rebuild, poly-swap only)"
```

---

### Task 6: `builder_brush.py` — prop set

**Files:**
- Modify: `uedcli/serve/builder_brush.py`.
- Modify: `uedcli/tests/test_builder_brush.py`.

**Interfaces:**
- Consumes: `uedcli.propedit` (`parse_token`, `plan_edit`, `PropEditError`, `TYPED_FIELDS`),
  `uedcli.serve.scene._class_ctx_for`, `uprops.SchemaError`.
- Produces: `set_props(sessions_root: Path, session_id: str, index, props: dict[str, str]) -> Actor`
  — sets one or more properties (any property — `Location`, `Rotation`, or a plain prop) on the
  session box's actor via `propedit`'s plan/apply, the same path `actor prop set` uses. **Batched,
  not one call per property**: builds every token first and calls `plan_edit` ONCE with the whole
  list, matching `actor prop set`'s own two-phase validate-before-mutate pattern exactly (real
  `uedcli/cli/commands/actor/prop.py:104-107`: `toks = [propedit.parse_token(t, ...) for t in
  args.tokens]; plans = [propedit.plan_edit(actor, toks, mode, ...) for actor in actors]` — ALL
  tokens for one actor go into ONE `plan_edit` call). A single-property `/stage` request (the common
  case — one Location move) is just the one-element case of this same function; a multi-property
  request (Location AND Rotation in one call) stays atomic: an invalid SECOND property must not
  leave the FIRST already applied. Raises `CommandError` on any `PropEditError`/`SchemaError`,
  before any property is applied.

- [ ] **Step 1: Write the failing tests**

```python
def test_set_props_location(tmp_path, real_index):
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    result = builder_brush.set_props(sessions_root, "sid1", real_index, {"Location": "100,200,300"})
    assert result.location == (Decimal(100), Decimal(200), Decimal(300))


def test_set_props_rotation(tmp_path, real_index):
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    result = builder_brush.set_props(sessions_root, "sid1", real_index,
                                     {"Rotation": "(Pitch=0,Yaw=16384,Roll=0)"})
    assert dict(result.props).get("Rotation") is not None


def test_set_props_multiple_at_once_is_atomic(tmp_path, real_index):
    # Regression: an earlier version called set_prop once per property in a loop -- a second,
    # invalid property left the first one already persisted. One call with two properties, the
    # second invalid, must leave BOTH unapplied (validate-before-mutate, like actor prop set).
    from uedcli.cli.errors import CommandError
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    import pytest
    with pytest.raises(CommandError):
        builder_brush.set_props(sessions_root, "sid1", real_index,
                                {"Location": "100,200,300", "NotAReal Prop!": "x"})
    unchanged = builder_brush.load_session_box(sessions_root, "sid1")
    assert unchanged.location != (Decimal(100), Decimal(200), Decimal(300))


def test_set_props_bad_token_raises_command_error(tmp_path, real_index):
    from uedcli.cli.errors import CommandError
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    import pytest
    with pytest.raises(CommandError):
        builder_brush.set_props(sessions_root, "sid1", real_index, {"NotAReal Prop!": "x"})
```

`real_index` — check `uedcli/tests/test_serve_scene.py` (or wherever `_class_ctx_for` is already
exercised) for the exact fixture name/construction this codebase already uses for a real/offline
`ClassIndex` in a test; reuse it rather than inventing a new one.

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k test_set_props -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Add `set_props` to `uedcli/serve/builder_brush.py`**

```python
from .. import propedit
from ..uprops import SchemaError
from .scene import _class_ctx_for


def set_props(sessions_root: Path, session_id: str, index, props: dict[str, str]):
    """Set one or more properties on the session box's actor, through the exact `propedit` plan/
    apply path `actor prop set` uses (`uedcli/cli/commands/actor/prop.py`'s `run()`), so `Location`'s
    typed-field validation and any struct-typed prop's grammar are enforced identically, with zero
    reimplementation. Each value is the T3D-literal text form (e.g. `"100,200,300"` for Location,
    `"(Pitch=0,Yaw=16384,Roll=0)"` for a struct prop) — the SAME text a CLI `--prop` token or
    `actor prop set KEY=VALUE` argument would carry. ALL properties are validated (planned) before
    ANY is applied — one `plan_edit` call over every token, not one call per property, so a bad
    second property can never leave a valid first property already persisted."""
    actor = load_session_box(sessions_root, session_id)
    ctx = _class_ctx_for(actor.cls, index)
    try:
        toks = [propedit.parse_token(f"{name}={value}", expect_value=True)
                for name, value in props.items()]
        plan = propedit.plan_edit(actor, toks, "set", ctx, propedit.TYPED_FIELDS)
    except (propedit.PropEditError, SchemaError) as exc:
        raise CommandError(str(exc)) from exc
    actor.props = plan.props
    for attr, val in plan.typed_updates.items():
        setattr(actor, attr, val)
    write_session_box(sessions_root, session_id, actor)
    return actor
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test -k test_set_props -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/builder_brush.py uedcli/tests/test_builder_brush.py
git commit -m "builder_brush: batched prop set via propedit's generic plan/apply"
```

---

### Task 7: `builder_brush.py` — Add/Subtract clone

**Files:**
- Modify: `uedcli/serve/builder_brush.py`.
- Modify: `uedcli/tests/test_builder_brush.py`.

**Interfaces:**
- Consumes: Task 4's `load_session_box`, `t3dtree.alloc_name`, `normalize.canonical_actor_t3d`,
  `copy.deepcopy`.
- Produces: `clone_for_csg(sessions_root: Path, session_id: str, existing_names: set[str], *, csg:
  str) -> Actor` — `csg` is `"add"` or `"subtract"`. Returns a NEW `Actor` (deep-copied from the
  session box's current actor) with a freshly `alloc_name`d Name (stem `"Builder"`) and `CsgOper`
  stamped to `CSG_Add`/`CSG_Subtract`. Does NOT touch the session box.

- [ ] **Step 1: Write the failing tests**

```python
def test_clone_for_csg_add_stamps_csg_and_new_name(tmp_path):
    sessions_root = tmp_path / "sessions"
    original = builder_brush.default_actor()
    original.location = (Decimal(1), Decimal(2), Decimal(3))
    builder_brush.write_session_box(sessions_root, "sid1", original)

    clone = builder_brush.clone_for_csg(sessions_root, "sid1", set(), csg="add")
    assert clone.name != builder_brush.RESERVED_NAME
    assert dict(clone.props).get("CsgOper") == "CSG_Add"
    assert clone.location == (Decimal(1), Decimal(2), Decimal(3))
    # session box untouched:
    still_there = builder_brush.load_session_box(sessions_root, "sid1")
    assert still_there.name == builder_brush.RESERVED_NAME
    assert still_there.location == (Decimal(1), Decimal(2), Decimal(3))


def test_clone_for_csg_subtract_stamps_csg_subtract(tmp_path):
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    clone = builder_brush.clone_for_csg(sessions_root, "sid1", set(), csg="subtract")
    assert dict(clone.props).get("CsgOper") == "CSG_Subtract"


def test_clone_for_csg_avoids_name_collision(tmp_path):
    sessions_root = tmp_path / "sessions"
    builder_brush.write_session_box(sessions_root, "sid1", builder_brush.default_actor())
    clone = builder_brush.clone_for_csg(sessions_root, "sid1", {"Builder_ab12"}, csg="add")
    assert clone.name != "Builder_ab12"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k test_clone_for_csg -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Add `clone_for_csg` to `uedcli/serve/builder_brush.py`**

```python
import copy

from .. import t3dtree

def clone_for_csg(sessions_root: Path, session_id: str, existing_names: set[str], *, csg: str):
    """Clone the session's builder-brush actor into a NEW actor with a freshly allocated Name
    (invariant D6, `t3dtree.alloc_name`) and `CsgOper` stamped per `csg` (`"add"` or `"subtract"`).
    The session box itself is NOT modified — the builder brush stays exactly as it was, ready for
    another Add/Subtract (spec "Data model")."""
    if csg not in builders.CSG_OPER:
        raise CommandError(f"invalid csg operation: {csg!r} (must be 'add' or 'subtract')")
    original = load_session_box(sessions_root, session_id)
    clone = copy.deepcopy(original)
    clone.name = t3dtree.alloc_name("Builder", existing_names)
    clone.props = [(k, v) for k, v in clone.props if k.casefold() != "csgoper"]
    clone.props.append(("CsgOper", builders.CSG_OPER[csg]))
    return clone
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test -k test_clone_for_csg -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/builder_brush.py uedcli/tests/test_builder_brush.py
git commit -m "builder_brush: Add/Subtract clone (fresh name, stamped CsgOper)"
```

---

### Task 8: `StagingStore` — stage a brand-new actor

**Files:**
- Modify: `uedcli/serve/snapshots.py`.
- Modify: `uedcli/tests/test_serve_snapshots.py` (confirmed to exist — `StagingStore`'s existing
  test file).

**Interfaces:**
- Consumes: nothing new — same `hashlib`/`atomic_write_json`/blob-path machinery `stage()` already
  uses.
- Produces:
  - `@dataclass(frozen=True, kw_only=True) class StagedNewActor: actor_t3d_text: str`
  - `StagingStore.stage_new(self, session_id: str, actor_name: str, *, actor_t3d_text: str) -> None`
  - `StagingStore.read_staged_new_actors(self, session_id: str) -> dict[str, StagedNewActor]`

**Existing behavior this task must NOT change** (regression-test it explicitly in Step 1): `stage()`,
`read_staged()`, `clear_actor()`, `discard()`, `evict_unreferenced_blobs()` — all unchanged for
existing (move-staging) manifest entries. The manifest format grows one discriminator: an entry with
`"kind": "new"` is read by `read_staged_new_actors` only; an entry with `"kind": "move"` (or missing
`"kind"`, for backward compatibility with an in-flight session's existing `staged.json`) is read by
`read_staged` only. Neither method surfaces the other kind's entries.

- [ ] **Step 1: Write the failing tests, plus one regression test**

```python
def test_stage_new_actor_readable_via_read_staged_new_actors(tmp_path):
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage_new("sid1", "Builder_ab12", actor_t3d_text="Begin Actor Class=Brush Name=Builder_ab12\nEnd Actor\n")
    new_actors = store.read_staged_new_actors("sid1")
    assert set(new_actors) == {"Builder_ab12"}
    assert "Builder_ab12" in new_actors["Builder_ab12"].actor_t3d_text


def test_stage_new_actor_not_visible_via_read_staged(tmp_path):
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage_new("sid1", "Builder_ab12", actor_t3d_text="...")
    assert store.read_staged("sid1") == {}


def test_existing_stage_move_unaffected_by_new_actor_staging(tmp_path):
    # Regression: stage() a real actor's move, ALSO stage_new() a new actor in the same session,
    # confirm read_staged() sees only the move and read_staged_new_actors() sees only the new one.
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    store.stage("sid1", "RealActor1", actor_t3d_text="...",
               baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
               staged_location=(Decimal(1), Decimal(0), Decimal(0)))
    store.stage_new("sid1", "Builder_ab12", actor_t3d_text="...")
    assert set(store.read_staged("sid1")) == {"RealActor1"}
    assert set(store.read_staged_new_actors("sid1")) == {"Builder_ab12"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "stage_new or read_staged_new" -v`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Add to `uedcli/serve/snapshots.py`**

```python
@dataclass(frozen=True, kw_only=True)
class StagedNewActor:
    """A staged brand-new actor — no baseline, nothing to conflict against (a fresh, never-before-
    seen Name). `actor_t3d_text` is the actor's full T3D body, applied verbatim into the trunk on
    Save (`edits.save_staged`, Task 9)."""
    actor_t3d_text: str
```

```python
    def stage_new(self, session_id: str, actor_name: str, *, actor_t3d_text: str) -> None:
        """Stage a brand-new actor (no trunk baseline). Distinguished from `stage()`'s move-staging
        entries by the manifest's `"kind": "new"` discriminator."""
        blob_hash = hashlib.sha256(actor_t3d_text.encode("utf-8")).hexdigest()
        blob_path = self._blob_path(blob_hash)
        if not blob_path.exists():
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_text(actor_t3d_text, encoding="utf-8")
        manifest = self._read_manifest(session_id)
        manifest[actor_name] = {"kind": "new", "blob_hash": blob_hash}
        atomic_write_json(self._manifest_path(session_id), manifest)

    def read_staged_new_actors(self, session_id: str) -> dict:
        manifest = self._read_manifest(session_id)
        out = {}
        for name, entry in manifest.items():
            if entry.get("kind") != "new":
                continue
            blob_path = self._blob_path(entry["blob_hash"])
            out[name] = StagedNewActor(actor_t3d_text=blob_path.read_text(encoding="utf-8"))
        return out
```

- [ ] **Step 4: Update `read_staged` to skip `"kind": "new"` entries**

In `StagingStore.read_staged`, the dict comprehension currently iterates every manifest entry — add
a filter so a `"kind": "new"` entry is skipped (an entry with no `"kind"` key, or `"kind": "move"`,
is still a move — `entry.get("kind", "move") == "move"`):

```python
    def read_staged(self, session_id: str) -> dict[str, StagedActor]:
        manifest = self._read_manifest(session_id)
        return {
            name: StagedActor(
                baseline_location=tuple(Decimal(c) for c in v["baseline_location"]),
                staged_location=tuple(Decimal(c) for c in v["staged_location"]),
                blob_hash=v["blob_hash"],
            )
            for name, v in manifest.items()
            if v.get("kind", "move") == "move"
        }
```

- [ ] **Step 5: Run tests to verify they pass, then the FULL existing StagingStore suite**

Run: `bin/test -k "stage_new or read_staged_new or snapshots" -v`
Expected: PASS, including every pre-existing `StagingStore`/`snapshots.py` test (the regression
check from Step 1).

- [ ] **Step 6: Commit**

```bash
git add uedcli/serve/snapshots.py uedcli/tests/test_serve_snapshots.py
git commit -m "StagingStore: stage a brand-new actor, separate from move-staging"
```

---

### Task 9: `edits.save_staged` applies staged new actors

**Files:**
- Modify: `uedcli/serve/edits.py`.
- Modify: `uedcli/tests/test_serve_edits.py` (or wherever `save_staged` is already tested).

**Interfaces:**
- Consumes: Task 8's `StagingStore.read_staged_new_actors`, `model.parse_t3d_actors`,
  `t3dtree.alloc_name`.
- Produces: `save_staged`'s existing signature UNCHANGED
  (`save_staged(project, level_name, *, store, resolutions=None) -> SaveResult`) — its BEHAVIOR
  grows a second, independent phase: apply every staged new actor. `SaveResult.applied` includes
  applied new-actor Names alongside applied moves; new actors never appear in `SaveResult.conflicts`
  (spec: "cannot conflict at Save").

- [ ] **Step 1: Write the failing test**

```python
def test_save_staged_applies_new_actor_to_trunk(tmp_path, real_project_with_level):
    project, level_name = real_project_with_level
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    new_actor_t3d = (
        "Begin Actor Class=Brush Name=Builder_ab12\n"
        "  CsgOper=CSG_Add\n"
        "  Begin Brush Name=Model_Builder_ab12\n"
        "  End Brush\n"
        "  Brush=Brush'MyLevel.Model_Builder_ab12'\n"
        "End Actor\n"
    )   # adjust to a real, valid minimal brush T3D snippet -- check an existing fixture for the
        # exact minimal valid form this codebase's tests already use (e.g. builders.cube() piped
        # through make_brush_actor + normalize.canonical_actor_t3d, rather than hand-typed T3D)
    store.stage_new(level_name, "Builder_ab12", actor_t3d_text=new_actor_t3d)

    result = save_staged(project, level_name, store=store)

    assert "Builder_ab12" in result.applied
    assert result.conflicts == []
    trunk_dir = _trunk_dir(project, level_name)
    level, *_ = trunk.read_level_with_bodies(trunk_dir)
    assert "Builder_ab12" in level.actors


def test_save_staged_new_actor_name_collision_raises_command_error(tmp_path, real_project_with_level):
    # An extremely rare race (the D6-allocated Name collided with something added to the trunk
    # between Add/Subtract-click-time and Save-time) -- must be a clean, named error, never a
    # silent overwrite.
    ...


def test_save_staged_applies_new_actor_with_no_staged_moves(tmp_path, real_project_with_level):
    # THE common real workflow -- build a shape, press Add, press Save, with NOTHING else staged.
    # Regression test: save_staged's early-return guard (real edits.py:126-127, `if not staged:
    # return SaveResult(applied=[], conflicts=[])`) fires on `store.read_staged(...)` alone -- a
    # naive read of the spec could miss that this guard must also account for
    # `read_staged_new_actors`, silently making Add/Subtract-then-Save a no-op whenever no REAL
    # actor move is also staged. Confirmed this is the actual common case: Add/Subtract alone
    # stages nothing via `store.stage()`, only via `store.stage_new()`.
    project, level_name = real_project_with_level
    store = StagingStore(tmp_path / "sessions", tmp_path / "blobs")
    new_actor_t3d = normalize.canonical_actor_t3d(
        builders.make_brush_actor("Builder_ab12", builders.cube(50.0, 50.0, 50.0), csg="add"))
    store.stage_new(level_name, "Builder_ab12", actor_t3d_text=new_actor_t3d)
    assert store.read_staged(level_name) == {}   # confirms the "no staged moves" precondition

    result = save_staged(project, level_name, store=store)

    assert "Builder_ab12" in result.applied
```


Use `normalize.canonical_actor_t3d(builders.make_brush_actor("Builder_ab12", builders.cube(50.0,
50.0, 50.0), csg="add"))` to build a real, valid T3D snippet for the first test rather than hand-
typing one — match whatever pattern `uedcli/tests/test_builders.py` or `test_cli_brush_build.py`
already uses for constructing test brush actors.

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k test_save_staged_applies_new_actor -v`
Expected: FAIL — the new actor never reaches the trunk (no such logic exists yet).

- [ ] **Step 3: Extend `save_staged` in `uedcli/serve/edits.py`**

**Critical placement note, found by review**: the real `save_staged` has an EARLY RETURN before any
of this — `staged = store.read_staged(level_name); if not staged: return SaveResult(applied=[],
conflicts=[])` (real `edits.py:125-127`). This guard checks ONLY move-staged entries. Add/Subtract's
output is staged exclusively via `store.stage_new()` — `store.stage()` (moves) is never touched by
it — so the COMMON real workflow (build a shape, press Add, press Save, nothing else staged) hits
this guard with `staged == {}` and returns immediately, before ever reaching new-actor logic placed
after the move-apply block. **This guard must change first**, to a two-part check:

```python
    resolutions = resolutions or {}
    staged = store.read_staged(level_name)
    new_actors_staged = store.read_staged_new_actors(level_name)
    if not staged and not new_actors_staged:
        return SaveResult(applied=[], conflicts=[])
```

(This replaces the real current `staged = store.read_staged(level_name)` / `if not staged: return
SaveResult(applied=[], conflicts=[])` pair — `resolutions = resolutions or {}` above it is unchanged,
just shown for placement context.) The rest of the function's move-handling body is UNCHANGED and
already tolerates an empty `staged` gracefully: `for name, entry in staged.items():` is simply a
no-op loop, `touched`/`conflicts` stay `[]`, and `if touched: src.save(...)` already guards the
move-side trunk write — none of that needs editing.

Then, after the existing move-staging apply logic (the `if touched: src.save(...)` block), before
the `return SaveResult(...)`, add:

```python
    applied_new: list[str] = []
    if new_actors_staged:
        # A fresh TrunkLevelSource, LOADED before use -- TrunkLevelSource.save() hard-requires a
        # prior load() (uedcli/cli/level_sources.py:77-78: "raise RuntimeError" otherwise, since it
        # preserves the existing order_values from that load). Reloading here (rather than reusing
        # `src` from the move-apply above) means the collision check below is against the CURRENT
        # trunk, not the stale snapshot this function started with -- the move-apply, if any, may
        # have already saved once.
        fresh_src = TrunkLevelSource(trunk_dir)
        fresh_level = fresh_src.load()
        for name, staged_new in new_actors_staged.items():
            if name in fresh_level.actors:
                raise CommandError(
                    f"builder-brush add/subtract: actor name {name!r} already exists in the "
                    f"trunk (rare allocation-time race) -- discard and retry")
            incoming = model.parse_t3d_actors(staged_new.actor_t3d_text)
            if len(incoming) != 1 or incoming[0].name != name:
                raise CommandError(f"staged new actor {name!r}: malformed T3D snippet")
            fresh_level.actors[name] = incoming[0]
            fresh_level.order.append(name)
            applied_new.append(name)
        fresh_src.save(verb="add", args={"names": applied_new}, level=fresh_level,
                       touched=applied_new)
        for name in applied_new:
            store.clear_actor(level_name, name)
```

Then update the function's final return (the existing `return SaveResult(applied=touched,
conflicts=conflicts)`, real `edits.py:186`) to include the new names too:

```python
    return SaveResult(applied=touched + applied_new, conflicts=conflicts)
```

**Verified against `edits.py`'s real current imports**: `CommandError` and `TrunkLevelSource` are
already imported (`edits.py:28-29`). Only `model` needs adding — `from .. import model` (used as
`model.parse_t3d_actors`), alongside the existing `from ..model import Level` on line 30.

`StagingStore.clear_actor` (from Task 8) already removes a `"kind": "new"` entry the same as a move
entry — it does `manifest.pop(actor_name, None)`, kind-agnostic by construction, so no change needed
there.

- [ ] **Step 4: Run tests to verify they pass, then the full edits.py suite**

Run: `bin/test -k "test_save_staged or test_serve_edits" -v`
Expected: PASS, including every pre-existing `save_staged` test (moves, conflicts, discard) —
unaffected by this addition.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/edits.py uedcli/tests/test_serve_edits.py
git commit -m "edits.save_staged: apply staged new actors (Add/Subtract's output) to the trunk"
```

---

### Task 10: `scene.py` — extract `_build_one_actor`, add the `/scene` overlay hook

**Files:**
- Modify: `uedcli/serve/scene.py:635-696` (`_build_actors`).
- Modify: `uedcli/tests/test_serve_scene.py`.

**Interfaces:**
- Produces: `_build_one_actor(name: str, actor, csg_rank: int, *, ranks: dict, actor_sprites: dict,
  tex_offset: int, ctx_cache: dict, index, radii_map: dict, arrow_map: dict) -> tuple[SceneActor,
  dict[str, list[str]]]` — the exact per-iteration body `_build_actors`'s loop already runs, callable
  standalone for ONE actor not in any trunk. `_build_actors` itself is refactored to call this in its
  loop; ITS OWN behavior and return value (`tuple[list[SceneActor], dict[str, list[str]]]`) are
  UNCHANGED — this is a pure extraction, not a behavior change.

**This task does NOT wire the overlay into `session_scene` yet** — that's Task 12, once
`builder_brush.load_session_box` exists to read from (already true after Task 4) and the route
handler has access to `sessions_root`/`session_id`. This task only makes the per-actor path
independently callable.

- [ ] **Step 1: Write the failing test — extraction produces identical output**

```python
def test_build_one_actor_matches_build_actors_output(real_trunk_fixture):
    trunk = real_trunk_fixture   # whatever fixture test_serve_scene.py already uses to build a
                                  # real _LoadedTrunk with at least one actor
    hidden_ed = {}
    radii_map, arrow_map = {}, {}   # or the fixture's real precomputed maps
    index = ...                     # the fixture's real ClassIndex
    full_actors, full_enums = _build_actors(trunk, hidden_ed, tex_offset=0, index=index,
                                            radii_map=radii_map, arrow_map=arrow_map)
    # Pick the first real actor and rebuild it standalone via _build_one_actor with the same inputs
    name = trunk.level.order[0] if trunk.level.order[0] != "LevelInfo" else trunk.level.order[1]
    actor = trunk.level.actors[name]
    csg_rank = next(i for i, n in enumerate(trunk.level.order, start=1) if n == name)
    single, single_enums = _build_one_actor(
        name, actor, csg_rank, ranks=trunk.ranks, actor_sprites=trunk.actor_sprites,
        tex_offset=0, ctx_cache={}, index=index, radii_map=radii_map, arrow_map=arrow_map)
    expected = next(a for a in full_actors if a.name == name)
    assert single == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test -k test_build_one_actor_matches -v`
Expected: FAIL — `_build_one_actor` doesn't exist.

- [ ] **Step 3: Extract `_build_one_actor` in `uedcli/serve/scene.py`**

Replace the loop body inside `_build_actors` (the code between `for csg_rank, name in
enumerate(level.order, start=1):` and the `for line in notes:` after the loop) with a call to a new
function carrying that exact body:

`_build_one_actor` takes a `notes: list[str] | None = None` parameter from the start: appends to it
when the caller supplies one (`_build_actors`'s own loop, which needs to keep its EXISTING
print-batching behavior — collect every actor's note, print them all once after the loop, to stay
behavior-identical) and prints immediately only when `None` (the standalone `/scene`-overlay caller,
Task 12, which has no batch to join and only ever calls this once per request):

```python
def _build_one_actor(name: str, actor, csg_rank: int, *, ranks: dict, actor_sprites: dict,
                     tex_offset: int, ctx_cache: dict, index, radii_map: dict, arrow_map: dict,
                     notes: list[str] | None = None
                     ) -> tuple["SceneActor", dict[str, list[str]]]:
    """One iteration of `_build_actors`'s loop, extracted so it is independently callable for an
    actor that is NOT part of any trunk (the builder-brush `/scene` overlay, Task 12). `ctx_cache`
    is mutated in place (per-class `ClassCtx` memo) — callers iterating many actors should share one
    dict across calls, exactly as `_build_actors`'s own loop does. `notes`: pass the caller's own
    batch list to APPEND a resolution note to it (keeps `_build_actors`' existing print-once-after-
    the-loop behavior); leave it `None` to print immediately instead (the standalone overlay case,
    which has no batch)."""
    lo, hi = actor_bounds(actor)
    loc = actor.location or _ZERO3
    sprite = None
    if (raw := actor_sprites.get(name)) is not None:
        local_idx, width, height = raw
        sprite = ActorSprite(tex_index=tex_offset + local_idx, width=width, height=height)
    cls = actor.cls or ""
    if cls not in ctx_cache:
        ctx_cache[cls] = _class_ctx_for(cls, index)
    props, actor_enum_types, note = effective_props.resolve_actor_props(actor, ctx_cache[cls])
    if note:
        if notes is not None:
            notes.append(note)
        else:
            print(note, file=sys.stderr)
    is_mover_flag = is_mover(actor, index) if actor.brush is not None else False
    scene_actor = SceneActor(
        name=name, cls=cls,
        bbox_lo=tuple(float(c) for c in lo), bbox_hi=tuple(float(c) for c in hi),
        location=tuple(float(c) for c in loc), rotation=actor_rotation_uu(actor),
        folder=actor.folder, labels=sorted(actor.labels), order_value=ranks.get(name, ""),
        csg_rank=csg_rank, props=props,
        brush=_brush_highlight(actor, is_mover_flag=is_mover_flag), sprite=sprite,
        radii=radii_map.get(name), is_mover=is_mover_flag,
        directional_arrow=arrow_map.get(name))
    return scene_actor, actor_enum_types
```

`_build_actors`'s own refactored loop passes its `notes` list through, so its behavior is unchanged:

```python
    notes: list[str] = []
    ctx_cache: dict[str, propedit.ClassCtx] = {}
    payload_enums: dict[str, list[str]] = {}
    actors = []
    for csg_rank, name in enumerate(level.order, start=1):
        actor = level.actors.get(name)
        if actor is None or hidden_ed.get(name):
            continue
        scene_actor, actor_enum_types = _build_one_actor(
            name, actor, csg_rank, ranks=ranks, actor_sprites=actor_sprites,
            tex_offset=tex_offset, ctx_cache=ctx_cache, index=index,
            radii_map=radii_map, arrow_map=arrow_map, notes=notes)
        payload_enums.update(actor_enum_types)
        actors.append(scene_actor)
    for line in notes:
        print(line, file=sys.stderr)
    return actors, payload_enums
```

Task 12's two standalone callers (`builder_brush_build`'s response and the `/scene` overlay) call
`_build_one_actor` WITHOUT a `notes` argument, so a resolution note for the builder brush's own class
(rare — it prints only when `effective_props.resolve_actor_props` can't fully resolve the class
schema) prints immediately rather than joining a batch that doesn't exist for those call sites.

- [ ] **Step 4: Run the extraction test, then the FULL existing scene.py suite**

Run: `bin/test -k "test_build_one_actor or test_serve_scene" -v`
Expected: PASS — `test_build_one_actor_matches_build_actors_output` passes, and every pre-existing
`_build_actors`/`/scene`/`/rebuild` test is unaffected (this is a pure refactor).

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/scene.py uedcli/tests/test_serve_scene.py
git commit -m "scene.py: extract _build_one_actor from _build_actors, behavior unchanged"
```

---

### Task 11: `builder_registry.py` — `GET /api/builders`

**Files:**
- Create: `uedcli/serve/builder_registry.py`.
- Test: `uedcli/tests/test_builder_registry.py`.

**Interfaces:**
- Produces: `shape_registry() -> list[dict]` — introspects `uedcli.cli.parsers.brush`'s `build`
  subparsers, returns one entry per shape (excluding `spiral`): `{"id": str, "label": str, "icon":
  str, "params": [{"name": str, "type": str, "required": bool, "default": Any, "choices":
  list[str] | None, "help": str}]}`. Excludes every argument `_common_build_opts` adds (`--at`,
  `--base-name`, `--csg`, `--solidity`, `--folder`, `--label`, `--texture`, `--mover-class`,
  `--prop`, `--rotate` — spec "Builder registry").

- [ ] **Step 1: Write the failing test**

```python
def test_shape_registry_excludes_spiral_extrude_revolve_and_common_opts():
    reg = builder_registry.shape_registry()
    ids = {s["id"] for s in reg}
    assert ids == {"cube", "cylinder", "cone", "sheet", "staircase"}
    cylinder = next(s for s in reg if s["id"] == "cylinder")
    param_names = {p["name"] for p in cylinder["params"]}
    assert param_names == {"height", "radius", "sides", "align_to_side", "axis"}
    assert "at" not in param_names and "csg" not in param_names and "rotate" not in param_names

    # sheet's --flag (dest "flags") is excluded too, even though it isn't part of
    # _common_build_opts -- material, not shape (owner ruling).
    sheet = next(s for s in reg if s["id"] == "sheet")
    sheet_param_names = {p["name"] for p in sheet["params"]}
    assert sheet_param_names == {"width", "height", "plane"}


def test_shape_registry_param_carries_real_help_text():
    reg = builder_registry.shape_registry()
    cylinder = next(s for s in reg if s["id"] == "cylinder")
    radius = next(p for p in cylinder["params"] if p["name"] == "radius")
    assert radius["help"] == "circumscribed radius"
    assert radius["type"] == "float"
    assert radius["required"] is True


def test_shape_registry_label_is_the_shape_subparser_help_text():
    # Regression: add_parser(name, help=...) does NOT set subparser.description -- an earlier
    # version of this registry read subparser.description (always None) and silently fell back to
    # the shape id itself, so every label was just "cylinder"/"cube"/etc. instead of the real
    # help= text (spec.md "its own help= as the label").
    reg = builder_registry.shape_registry()
    cylinder = next(s for s in reg if s["id"] == "cylinder")
    assert cylinder["label"] == "n-gon prism (height, radius, sides)"


def test_shape_registry_every_entry_has_an_icon():
    reg = builder_registry.shape_registry()
    assert all(s["icon"] for s in reg)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k test_shape_registry -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write `uedcli/serve/builder_registry.py`**

Build the argparse parser tree the same way the CLI itself does (find how `uedcli/cli/parsers/
brush.py`'s `build_parser` — or whatever the top-level parser-construction entry point is called;
grep `uedcli/cli/dispatch.py` or `uedcli/cli/__init__.py` for how the full parser gets assembled —
and reuse THAT to reach the real `bbuild` subparsers object, rather than re-implementing
`_common_build_opts`'s argument list by hand:

```python
"""GET /api/builders' shape registry — introspected from the SAME argparse subparsers the CLI's
`brush build <shape>` uses (`uedcli/cli/parsers/brush.py`), so a new shape lands in the GUI's shape
picker automatically. See spec "Builder registry"."""
from __future__ import annotations

import argparse

# Every arg name _common_build_opts adds to EVERY shape subparser (uedcli/cli/parsers/
# brush.py:121-179), PLUS sheet's own --flag (dest "flags", not part of _common_build_opts, but
# excluded for the same reason: material, not shape -- owner ruling, spec "Builder registry"). None
# of these are build-time params for the GUI's builder brush (spec "Non-goals" / "Builder registry").
_COMMON_OPT_DESTS = {"at", "base_name", "csg", "solidity", "folder", "label", "texture",
                     "mover_class", "prop", "rotate", "flags"}

_EXCLUDED_SHAPES = {
    "spiral",    # multi-actor output, spec "Non-goals"
    "extrude",   # repeated 2D point-list param, no flat-form representation, spec "Non-goals"
    "revolve",   # same as extrude, plus a computed sweep angle/segment count
}

_ICONS = {
    "cube": "cube",
    "cylinder": "cylinder",
    "cone": "cone",
    "sheet": "sheet",
    "staircase": "staircase",
}


def _param_type_name(action: argparse.Action) -> str:
    if action.choices:
        return "enum"
    if action.type is float:
        return "float"
    if action.type is int:
        return "integer"
    if isinstance(action, argparse._StoreTrueAction):
        return "boolean"
    return "string"


def _shape_entry(shape_id: str, subparser: argparse.ArgumentParser, label: str) -> dict:
    params = []
    for action in subparser._actions:
        if action.dest in ("help",) or action.dest in _COMMON_OPT_DESTS:
            continue
        if not action.option_strings:              # positional, none expected here
            continue
        params.append({
            "name": action.dest,
            "type": _param_type_name(action),
            "required": bool(getattr(action, "required", False)),
            "default": action.default,
            "choices": list(action.choices) if action.choices else None,
            "help": action.help or "",
        })
    return {
        "id": shape_id,
        "label": label,
        "icon": _ICONS.get(shape_id, shape_id),
        "params": params,
    }


def _find_subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))


_registry_cache: list[dict] | None = None


def shape_registry() -> list[dict]:
    """Memoized (module-level cache — the argparse tree is pure/static per process, same
    "resolve once" convention as `classindex.ClassIndex`). Reuses `uedcli.cli.main.build_parser()`
    verbatim — the SAME function `uedcli.cli.main.main()` calls to build the real top-level CLI
    parser (`uedcli/cli/main.py:35-60`) — rather than re-registering `brush.register` in isolation,
    so this registry can never drift from what the CLI itself actually exposes."""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache
    from ..cli.main import build_parser

    top = build_parser()
    brush_sub = _find_subparsers_action(top).choices["brush"]
    build_sub = _find_subparsers_action(brush_sub).choices["build"]
    shape_sub = _find_subparsers_action(build_sub)

    # `add_parser(name, help=...)` does NOT set `.description` on the created subparser -- argparse
    # stores `help` on the PARENT subparsers action's own `_choices_actions` list instead (each a
    # `dest`/`help` pair keyed by shape id), never on the subparser object itself. Verified directly:
    # `bcyl.description` is `None` even though `bshape.add_parser("cylinder", help="n-gon prism...")`
    # was called. Build the label lookup from there.
    labels = {a.dest: (a.help or a.dest) for a in shape_sub._choices_actions}

    entries = []
    for shape_id, subparser in shape_sub.choices.items():
        if shape_id in _EXCLUDED_SHAPES:
            continue
        entries.append(_shape_entry(shape_id, subparser, labels.get(shape_id, shape_id)))
    _registry_cache = entries
    return entries
```

**Verified against the real parser-construction code**: `uedcli/cli/main.py:35-60`'s `build_parser()`
is the exact function `main()` itself calls — `brush.register(sub)` (line 44) registers the whole
`brush` verb tree, including `build` and every shape subparser, through `uedcli/cli/parsers/
brush.py:17`'s `register(sub)`. `argparse._SubParsersAction.choices` is a `{name: ArgumentParser}`
dict at every level (`top`'s choices include `"brush"`; `brush_sub`'s include `"build"`;
`build_sub`'s (found the same way, since `build` itself has `bshape = bbuild.add_subparsers(...)`)
include every shape id, `"cube"`/`"cylinder"`/etc.) — the walk above reaches the real per-shape
subparsers with no guessing.

Import `argparse` at the top of the file (already assumed above). `_registry_cache` gives the
"resolve once, memoize" behavior this codebase already uses elsewhere (`classindex.ClassIndex`,
`schema_cache`) — built on first call, not per request.

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test -k test_shape_registry -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/builder_registry.py uedcli/tests/test_builder_registry.py
git commit -m "builder_registry: GET /api/builders introspects the real CLI argparse tree"
```

---

### Task 12: Wire everything into `uedcli/serve/app.py`

**Files:**
- Modify: `uedcli/serve/app.py`.
- Modify: `uedcli/tests/test_serve_app.py`.

**Interfaces:**
- Consumes: every function from Tasks 3-11.
- Produces the final route surface (spec "API surface"):
  - `GET /api/builders`
  - `POST /api/session/{id}/builder-brush/build`
  - `POST /api/session/{id}/builder-brush/add`, `/subtract`
  - `POST /api/session/{id}/stage` — dispatch branch for `RESERVED_NAME`
  - `POST /api/session/{id}/discard` — no-op branch for `RESERVED_NAME`
  - `POST /api/session/{id}/save` — extra flush for the session box
  - `GET /api/session/{id}/scene` — the builder-brush overlay entry
  - `POST /api/level/{level_name}/sessions` — one-time seeding call

This is the largest task in the plan — split it into sub-steps by route, each independently testable,
but land it as ONE task/commit since the routes share the same dispatch seam and a partial wire-up
leaves the feature non-functional.

- [ ] **Step 1: Write the failing route tests**

Add to `uedcli/tests/test_serve_app.py`, following its existing `TestClient` fixture pattern (check
an existing `/scene`/`/stage` test for the exact session-creation boilerplate and reuse it):

```python
def test_get_builders_lists_shapes(client, ...):
    resp = client.get("/api/builders")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.json()}
    assert "cylinder" in ids and "spiral" not in ids


def test_scene_includes_builder_brush_entry(client, session_id, ...):
    resp = client.get(f"/api/session/{session_id}/scene")
    names = {a["name"] for a in resp.json()["actors"]}
    assert "*Builder" in names


def test_builder_brush_build_rebuilds_shape_only(client, session_id, ...):
    resp = client.post(f"/api/session/{session_id}/builder-brush/build",
                       json={"shape": "cylinder", "params": {"height": 100.0, "radius": 50.0}})
    assert resp.status_code == 200
    scene = client.get(f"/api/session/{session_id}/scene").json()
    builder = next(a for a in scene["actors"] if a["name"] == "*Builder")
    assert builder["location"] == [0.0, 0.0, 0.0]   # unchanged by build


def test_stage_builder_brush_prop_dispatches_to_own_store(client, session_id, ...):
    resp = client.post(f"/api/session/{session_id}/stage",
                       json={"actors": {"*Builder": {"Location": "10,20,30"}}})
    assert resp.status_code == 200


def test_stage_real_actor_rejects_non_location_prop(client, session_id, real_actor_name, ...):
    resp = client.post(f"/api/session/{session_id}/stage",
                       json={"actors": {real_actor_name: {"Rotation": "(Yaw=16384)"}}})
    assert resp.status_code == 422
    assert real_actor_name in resp.json()["error"] and "Rotation" in resp.json()["error"]


def test_discard_is_noop_for_builder_brush(client, session_id, ...):
    client.post(f"/api/session/{session_id}/stage",
               json={"actors": {"*Builder": {"Location": "10,20,30"}}})
    resp = client.post(f"/api/session/{session_id}/discard", json={"actors": ["*Builder"]})
    assert resp.status_code == 200
    scene = client.get(f"/api/session/{session_id}/scene").json()
    builder = next(a for a in scene["actors"] if a["name"] == "*Builder")
    assert builder["location"] == [10.0, 20.0, 30.0]   # untouched by discard


def test_add_stages_new_actor_leaves_builder_brush_unchanged(client, session_id, ...):
    resp = client.post(f"/api/session/{session_id}/builder-brush/add")
    assert resp.status_code == 200
    new_name = resp.json()["name"]
    assert new_name != "*Builder"

    # The builder brush's own /scene entry is untouched by Add.
    scene = client.get(f"/api/session/{session_id}/scene").json()
    builder = next(a for a in scene["actors"] if a["name"] == "*Builder")
    assert builder["location"] == [0.0, 0.0, 0.0]

    # `GET /staged` (session_staged, real app.py:918-926 -- a bare {name: {...}} dict via
    # StagingStore.read_staged) deliberately does NOT surface the new actor: Task 8's manifest-kind
    # split keeps "kind": "new" entries out of read_staged() on purpose, so this staged clone is
    # invisible there BY DESIGN, not a bug -- assert that explicitly rather than assuming otherwise.
    staged = client.get(f"/api/session/{session_id}/staged").json()
    assert new_name not in staged and "*Builder" not in staged

    # The real, meaningful check: Save actually applies the new actor to the trunk (the HTTP-layer
    # counterpart of Task 9's direct save_staged() test).
    save_resp = client.post(f"/api/session/{session_id}/save", json={})
    assert new_name in save_resp.json()["applied"]


def test_save_flushes_builder_brush_to_level_box_without_clearing(client, session_id, project,
                                                                   level_name, ...):
    client.post(f"/api/session/{session_id}/stage",
               json={"actors": {"*Builder": {"Location": "10,20,30"}}})
    resp = client.post(f"/api/session/{session_id}/save", json={})
    assert resp.status_code == 200
    level_actor = builder_brush.load_level_box(project, level_name)
    assert level_actor.location == (Decimal(10), Decimal(20), Decimal(30))
    scene = client.get(f"/api/session/{session_id}/scene").json()
    builder = next(a for a in scene["actors"] if a["name"] == "*Builder")
    assert builder["location"] == [10.0, 20.0, 30.0]   # still there, not cleared


def test_new_session_inherits_saved_level_builder_brush(client, session_id, level_name, ...):
    client.post(f"/api/session/{session_id}/stage",
               json={"actors": {"*Builder": {"Location": "5,5,5"}}})
    client.post(f"/api/session/{session_id}/save", json={})
    new_session = client.post(f"/api/level/{level_name}/sessions").json()
    scene = client.get(f"/api/session/{new_session['id']}/scene").json()
    builder = next(a for a in scene["actors"] if a["name"] == "*Builder")
    assert builder["location"] == [5.0, 5.0, 5.0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "builder_brush or builders or scene_includes_builder" -v`
Expected: FAIL — no routes exist yet.

- [ ] **Step 3: Add the new routes and dispatch branches to `uedcli/serve/app.py`**

Imports (top of file). **Verified against the real current import block
(`uedcli/serve/app.py:6-43`)** — `asdict` is already imported (line 13, `from dataclasses import
asdict, dataclass` — use the bare `asdict(...)` everywhere below, NOT `dataclasses.asdict(...)`,
since the `dataclasses` module itself is never imported). `Decimal` is imported (line 14) but
`InvalidOperation` is not — add it to that same line. `TrunkLevelSource` and `normalize` are NOT
currently imported anywhere in `app.py` — add both. `_build_one_actor` needs adding to the existing
`from .scene import (...)` block (line 33-40) rather than referenced as `scene._build_one_actor`,
since `app.py` never imports the `scene` module by its own name, only specific symbols from it.
**`builder_brush`/`builder_registry` are SIBLING modules** — both created directly in `uedcli/serve/`
(same package as `app.py` itself, per "File Structure"), the same relationship `build_pin`/`edits`/
`sessions` already have (real `app.py:28`: `from . import build_pin, edits, sessions`) — they need
the ONE-DOT sibling-import form, NOT the two-dot parent-package form `normalize` needs (`normalize`
is a real top-level `uedcli/` module, matching `app.py:22`'s existing `from .. import build_cache,
config, packages, trunk`). Getting this wrong (`from .. import builder_brush`) raises `ImportError`
at server startup, since `uedcli.builder_brush` doesn't exist — only `uedcli.serve.builder_brush`
does:

```python
from decimal import Decimal, InvalidOperation          # extend the existing line 14 import
from ..cli.level_sources import TrunkLevelSource        # new
from .. import normalize                                # new (top-level uedcli/ module)
from . import builder_brush, builder_registry           # new (sibling modules in uedcli/serve/)
from .scene import _build_one_actor                     # add to the existing `from .scene import (...)` block
```

New standalone routes (place near the other `/api/session/{id}/...` routes):
```python
    @app.get("/api/builders")
    def get_builders() -> list[dict]:
        return builder_registry.shape_registry()

    @app.post("/api/session/{session_id}/builder-brush/build")
    def builder_brush_build(session_id: str, body: dict, request: Request) -> dict:
        # Claim-token gated like every other session-mutating route (`load`/`stage`/`discard`/
        # `save`) — this writes the session's builder-brush store, so it needs the same protection
        # against a stale/superseded client mutating a session it no longer owns. ALSO carries the
        # same deleted-session re-check `session_stage`/`session_discard`/`session_save` each do
        # under their lock ("Fix round 1, Finding 1", real `app.py:752-765`) — a DELETE racing this
        # request's entry-to-lock window would otherwise resurrect `sessions/<sid>/` via
        # `write_session_box`'s unconditional `mkdir` (same footgun `atomic_write_json` has
        # elsewhere in this codebase).
        session = _require_session(session_id)
        token = request.headers.get("X-Claim-Token", "")
        with _claims.lock_for(session_id):
            if not _claims.check(session_id, token):
                return _claim_conflict_response(session_id)
            if sessions.get_session(_sessions_root, session_id) is None:
                logger.info("builder_brush_build_dropped_session_deleted",
                            extra={"session_id": session_id})
                return JSONResponse(status_code=409, content={"error": "session deleted"})
            actor = builder_brush.build(_sessions_root, session_id, body["shape"],
                                        body.get("params", {}))
        search_files, index, defaults = _current_scene_inputs(session.level)
        scene_actor, _ = _build_one_actor(
            actor.name, actor, 0, ranks={}, actor_sprites={}, tex_offset=0, ctx_cache={},
            index=index, radii_map={}, arrow_map={})
        return asdict(scene_actor)

    @app.post("/api/session/{session_id}/builder-brush/add")
    def builder_brush_add(session_id: str, request: Request) -> dict:
        return _builder_brush_csg(session_id, "add", request)

    @app.post("/api/session/{session_id}/builder-brush/subtract")
    def builder_brush_subtract(session_id: str, request: Request) -> dict:
        return _builder_brush_csg(session_id, "subtract", request)

    def _builder_brush_csg(session_id: str, csg: str, request: Request) -> dict:
        session = _require_session(session_id)
        token = request.headers.get("X-Claim-Token", "")
        with _claims.lock_for(session_id):
            if not _claims.check(session_id, token):
                return _claim_conflict_response(session_id)
            if sessions.get_session(_sessions_root, session_id) is None:
                logger.info("builder_brush_csg_dropped_session_deleted",
                            extra={"session_id": session_id})
                return JSONResponse(status_code=409, content={"error": "session deleted"})
            trunk_dir = edits._trunk_dir(project, session.level)   # reuse, don't reimplement (edits.py:51-52)
            level = TrunkLevelSource(trunk_dir).load()
            existing = set(level.actors)
            clone = builder_brush.clone_for_csg(_sessions_root, session_id, existing, csg=csg)
            _staging_store.stage_new(session_id, clone.name,
                                     actor_t3d_text=normalize.canonical_actor_t3d(clone))
        search_files, index, defaults = _current_scene_inputs(session.level)
        scene_actor, _ = _build_one_actor(
            clone.name, clone, 0, ranks={}, actor_sprites={}, tex_offset=0, ctx_cache={},
            index=index, radii_map={}, arrow_map={})
        return {"name": clone.name, "actor": asdict(scene_actor)}
```

`session_stage` dispatch (edit the existing handler body — the loop that today unconditionally
builds `moves` and calls `edits.stage_locations` must split `actors` by whether the name is
`builder_brush.RESERVED_NAME`):

```python
    @app.post("/api/session/{session_id}/stage")
    def session_stage(session_id: str, body: dict, request: Request) -> dict:
        session = _require_session(session_id)
        token = request.headers.get("X-Claim-Token", "")
        with _claims.lock_for(session_id):
            if not _claims.check(session_id, token):
                return _claim_conflict_response(session_id)
            if sessions.get_session(_sessions_root, session_id) is None:
                logger.info("session_stage_dropped_session_deleted", extra={"session_id": session_id})
                return JSONResponse(status_code=409, content={"error": "session deleted"})
            actors = body.get("actors") or {}
            search_files, index, defaults = _current_scene_inputs(session.level)
            staged: list[str] = []
            real_actor_moves: dict[str, str] = {}
            for name, props in actors.items():
                if name == builder_brush.RESERVED_NAME:
                    # ONE batched call, not one per property (Task 6) -- an invalid second
                    # property must never leave a valid first property already persisted.
                    builder_brush.set_props(_sessions_root, session_id, index, props)
                    staged.append(name)
                    continue
                extra = set(props) - {"Location"}
                if extra:
                    raise CommandError(
                        f"actor {name!r}: only Location is staged for a real actor "
                        f"(rejected: {', '.join(sorted(extra))})")
                if "Location" in props:
                    real_actor_moves[name] = props["Location"]
            if real_actor_moves:
                moves = {name: _parse_location_string(loc) for name, loc in real_actor_moves.items()}
                staged.extend(edits.stage_locations(
                    project, session.level, moves,
                    store=_SessionKeyedStore(_staging_store, session_id)))
            _staging_store.evict_unreferenced_blobs(live_hashes=_live_blob_hashes(),
                                                    max_bytes=_staging_blobs_max_bytes)
            return {"staged": staged}
```

**Confirmed against `uedcli/serve/app.py:736-737`**: the EXISTING `_parse_location(arr) -> tuple[
Decimal, Decimal, Decimal]` takes a JSON array `[x, y, z]` (`Decimal(str(v)) for v in arr`) — but the
generalized wire shape sends `"Location"` as a comma-separated STRING (`"10,20,30"`), the same text
form `propedit`'s token grammar takes for the builder-brush's `set_props` call, so the two paths stay
uniform. `_parse_location` itself must NOT be changed (it's still used verbatim, unreached by this
new string case, by nothing else in this diff — leave it exactly as-is to avoid touching an
unrelated, already-tested function). Add a small SIBLING helper next to it instead:

```python
    def _parse_location_string(text: str) -> tuple[Decimal, Decimal, Decimal]:
        parts = text.split(",")
        if len(parts) != 3:
            raise CommandError(f"invalid Location value: {text!r} (expected \"X,Y,Z\")")
        try:
            return tuple(Decimal(p.strip()) for p in parts)
        except InvalidOperation as exc:
            raise CommandError(f"invalid Location value: {text!r}: {exc}") from exc
```

(`Decimal`/`InvalidOperation` are already imported at the top of `app.py` for `_parse_location`'s own
use — reuse that same import, add `InvalidOperation` to it if not already present.)

`session_discard` dispatch (one added filter before the existing `edits.discard_staged` call):

```python
            actors = (body or {}).get("actors")
            real_actors = ([a for a in actors if a != builder_brush.RESERVED_NAME]
                          if actors is not None else None)
            if actors is None or real_actors:
                edits.discard_staged(project, session_id, store=_staging_store, actors=real_actors)
```

(When `actors` is `None` — whole-session discard — `StagingStore`'s own manifest never contains
`*Builder` in the first place, per Task 8's `stage()`/`stage_new()` split, so the existing
`discard_staged(..., actors=None)` call is ALREADY a no-op for the builder brush with no change
needed there; only the FILTERED case above needs the explicit skip.)

`_SessionKeyedStore` (`app.py:79-104`) extension — **required**: `session_save` calls
`edits.save_staged(..., store=_SessionKeyedStore(_staging_store, session_id))`
(real `app.py:889-891`), and Task 9's extended `save_staged` now calls
`store.read_staged_new_actors(level_name)`. The real `_SessionKeyedStore` only proxies `stage`/
`read_staged`/`clear_actor` — without this addition, ANY Save after an Add/Subtract raises
`AttributeError` (unclassified by `error_to_status`, so it would escape as a raw 500, violating "no
Python exception reaches the user"). Add one more proxy method, same shape as the other three:

```python
    def read_staged_new_actors(self, _level_name: str):
        return self._store.read_staged_new_actors(self._session_id)
```

`session_save` extension (after the existing `edits.save_staged` call and blob eviction, before the
pin-promotion block):

```python
            session_actor = builder_brush.load_session_box(_sessions_root, session_id)
            builder_brush.write_level_box(project, session.level, session_actor)
```

`create_session_route` extension (after `rec = sessions.create_session(...)`):

```python
        builder_brush.seed_session_box(project, level_name, _sessions_root, rec.id)
```

`session_scene` extension (`GET /scene`, after building `payload` from `build_wireframe_payload`/
`build_scene_payload`, before the `return`):

```python
        builder_actor = builder_brush.load_session_box(_sessions_root, session_id)
        builder_scene_actor, builder_enum_types = _build_one_actor(
            builder_actor.name, builder_actor, 0, ranks={}, actor_sprites={}, tex_offset=0,
            ctx_cache={}, index=index, radii_map={}, arrow_map={})
        enums = dict(payload.enums)
        enums.update(builder_enum_types)
        return {
            "polys": [asdict(p) for p in payload.polys],
            "actors": [asdict(a) for a in payload.actors] + [asdict(builder_scene_actor)],
            "enums": enums,
            "geometry_pinned": geometry is not None,
        }
```

**Fixes a real regression an earlier draft of this task had**: the REAL current `session_scene`
(`app.py:659-664`) already returns `"enums": payload.enums` — an earlier version of this snippet
dropped that field entirely, which would have silently broken enum-typed prop editing for every
actor, level-wide, not just the builder brush. The version above keeps it, and additionally folds in
`_build_one_actor`'s own second return value (the builder brush's own enum types, previously
discarded as `_` at the call site above) via a dict update — matching the exact pattern `_build_
actors`'s own loop uses (`payload_enums.update(actor_enum_types)`, Task 10).

- [ ] **Step 4: Run all new tests, then the FULL app.py suite**

Run: `bin/test -k test_serve_app -v`
Expected: PASS — every new test from Step 1, and every pre-existing `test_serve_app.py` test
unaffected (real-actor Location staging, save/discard/conflict behavior, session creation/deletion).

- [ ] **Step 5: Run the ENTIRE backend suite once**

Run: `bin/test`
Expected: PASS, full suite — this is the last backend task, per `dev/docs/rules/tests.md`'s "run the
whole suite once, before merge" rule.

- [ ] **Step 6: Commit**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Wire builder-brush routes: registry, build/add/subtract, stage/discard/save dispatch, scene overlay"
```

---

## Frontend Tasks

### Task 13: `api.ts` — generalize `postStage`, add builder-brush calls

**Files:**
- Modify: `web/src/api.ts:458-464` (`postStage`), and its 2 real call sites: `web/src/scene/
  Viewport3D.tsx:560`, `web/src/scene/OrthoViewport.tsx:435` (verified via `grep -rn "postStage("
  web/src` — `SaveBar.tsx` does NOT call `postStage`, it only imports `postDiscard`/`postSave`).
- Modify: `web/src/api.test.ts` (confirmed to exist — `postStage`'s existing test file).

**Interfaces:**
- Produces:
  - `postStage(sessionId: string, actors: Record<string, Record<string, string>>):
    Promise<{staged: string[]}>` — BREAKING change to the existing exported type (was `Record<string,
    [number, number, number]>`).
  - `fetchBuilders(): Promise<BuilderShape[]>` with `interface BuilderShape { id: string; label:
    string; icon: string; params: BuilderParam[] }` / `interface BuilderParam { name: string; type:
    string; required: boolean; default: unknown; choices: string[] | null; help: string }`.
  - `postBuilderBrushBuild(sessionId: string, shape: string, params: Record<string, unknown>):
    Promise<SceneActor>`.
  - `postBuilderBrushAdd(sessionId: string): Promise<{name: string; actor: SceneActor}>`.
  - `postBuilderBrushSubtract(sessionId: string): Promise<{name: string; actor: SceneActor}>`.

- [ ] **Step 1: Write the failing tests**

```typescript
// web/src/api.test.ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { postStage, fetchBuilders, postBuilderBrushBuild, postBuilderBrushAdd } from './api';

describe('postStage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends a prop-map per actor, not a bare location tuple', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ staged: ['*Builder'] }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await postStage('sid1', { '*Builder': { Location: '10,20,30' } });
    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ actors: { '*Builder': { Location: '10,20,30' } } });
  });
});

describe('fetchBuilders', () => {
  afterEach(() => vi.restoreAllMocks());

  it('GETs /api/builders and returns the shape list', async () => {
    const shapes = [{ id: 'cylinder', label: 'cylinder', icon: 'cylinder', params: [] }];
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(shapes), { status: 200 })));
    const result = await fetchBuilders();
    expect(result).toEqual(shapes);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/api.test.ts`
Expected: FAIL — `postStage` still sends `[number,number,number]`; `fetchBuilders` doesn't exist.

- [ ] **Step 3: Update `web/src/api.ts`**

Change `postStage`'s type and body construction (matching the existing function's exact
`request`/`withClaimToken` pattern from `api.ts:458-464`):

```typescript
export function postStage(
  sessionId: string,
  actors: Record<string, Record<string, string>>,
): Promise<{ staged: string[] }> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/stage`, withClaimToken({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actors }),
  }));
}
```

Add the new functions (same file, near `postStage`):

```typescript
export interface BuilderParam {
  name: string;
  type: string;
  required: boolean;
  default: unknown;
  choices: string[] | null;
  help: string;
}

export interface BuilderShape {
  id: string;
  label: string;
  icon: string;
  params: BuilderParam[];
}

export function fetchBuilders(): Promise<BuilderShape[]> {
  return request('/api/builders');
}

export function postBuilderBrushBuild(
  sessionId: string,
  shape: string,
  params: Record<string, unknown>,
): Promise<SceneActor> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/builder-brush/build`, withClaimToken({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ shape, params }),
  }));
}

export function postBuilderBrushAdd(sessionId: string): Promise<{ name: string; actor: SceneActor }> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/builder-brush/add`, withClaimToken({ method: 'POST' }));
}

export function postBuilderBrushSubtract(sessionId: string): Promise<{ name: string; actor: SceneActor }> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/builder-brush/subtract`, withClaimToken({ method: 'POST' }));
}
```

- [ ] **Step 4: Migrate the 2 existing `postStage` call sites**

**Both real call sites pass a `locations: Record<string, Vec3>` built by `stagedLocationsFor`**
(`web/src/scene/dragStage.ts:86-95`, `Vec3 = [number, number, number]` per `web/src/scene/camera.ts:
13`) — potentially MULTIPLE actor names at once (the current multi-select drag), not a single `{name,
x, y, z}` triple. `Viewport3D.tsx:557-560`:
```typescript
const locations = stagedLocationsFor(stagedOffsetsRef.current, selectedNames)
if (Object.keys(locations).length > 0) {
  postStage(sessionId, locations)
```
`OrthoViewport.tsx:432-435` is the same shape. At BOTH call sites, transform the whole `locations`
record into the new per-actor prop-map form — every entry, not just one:

```typescript
// before:
postStage(sessionId, locations)
// after:
postStage(sessionId, Object.fromEntries(
  Object.entries(locations).map(([name, [x, y, z]]) => [name, { Location: `${x},${y},${z}` }])
))
```

Also update `web/src/api.test.ts`'s existing `describe('postStage', ...)` block
(`api.test.ts:170-184`), which asserts the OLD bare-tuple body shape
(`postStage('sess-1', { Light0: [1, 2, 3], Light1: [4, 5, 6] })` →
`body: JSON.stringify({ actors: { Light0: [1, 2, 3], ... } })`). **A SECOND, separate stale
`postStage` call also exists** — inside `describe('claim token header', ...)` at
`api.test.ts:379-390`, functionally identical to the first (`postStage('sess-1', { Light0: [1, 2,
3] })`). Both would keep passing at runtime even after the real signature changes (JS doesn't
enforce the TS type), silently testing a shape `postStage` no longer produces — fix BOTH, not just
the first. Rewrite the `describe('postStage', ...)` block to the new call shape:

```typescript
describe('postStage', () => {
  it('POSTs a JSON body {actors} with a prop-map per actor to the stage route', async () => {
    const payload = { staged: ['Light0'] }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    const got = await postStage('sess-1', { Light0: { Location: '1,2,3' } })

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actors: { Light0: { Location: '1,2,3' } } }),
    })
  })
})
```

And the second block, `api.test.ts:379-390` (`'postStage attaches X-Claim-Token when a token is
set'`, inside the `describe('claim token header', ...)` group — untouched otherwise, only this one
`it` block's body and assertion change):

```typescript
  it('postStage attaches X-Claim-Token when a token is set', async () => {
    setClaimToken('tok-2')
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ staged: ['Light0'] }), { status: 200 })) as unknown as typeof fetch

    await postStage('sess-1', { Light0: { Location: '1,2,3' } })

    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Claim-Token': 'tok-2' },
      body: JSON.stringify({ actors: { Light0: { Location: '1,2,3' } } }),
    })
  })
```

- [ ] **Step 5: Run the frontend test suite for these 3 files**

Run: `cd web && npx vitest run src/api.test.ts src/scene/Viewport3D.test.ts src/scene/OrthoViewport.test.ts`
Expected: PASS — including each file's EXISTING tests that exercise `postStage`, updated to the new
call shape (check each test file's own mocked `postStage` assertions and update them to match, same
migration as the real call sites).

- [ ] **Step 6: Commit**

```bash
git add web/src/api.ts web/src/api.test.ts \
  web/src/scene/Viewport3D.tsx web/src/scene/Viewport3D.test.ts \
  web/src/scene/OrthoViewport.tsx web/src/scene/OrthoViewport.test.ts
git commit -m "api.ts: generalize postStage to a prop-map, add builder-brush API calls"
```

---

### Task 14: `BuilderBrushPanel` — shape picker and param form

**Files:**
- Create: `web/src/panels/BuilderBrushPanel.tsx`.
- Create: `web/src/panels/BuilderBrushPanel.test.tsx`.

**Interfaces:**
- Consumes: Task 13's `fetchBuilders`, `postBuilderBrushBuild`.
- Produces: `BuilderBrushPanel({ sessionId, onBuilderBrushChanged }: { sessionId: string;
  onBuilderBrushChanged: (actor: SceneActor) => void })` — a panel component (props/state pattern
  matching `ConflictResolver.tsx`'s shape: local `useState`, no global store).

- [ ] **Step 1: Write the failing tests**

```typescript
// web/src/panels/BuilderBrushPanel.test.tsx
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { BuilderBrushPanel } from './BuilderBrushPanel';

vi.mock('../api', () => ({
  fetchBuilders: vi.fn(),
  postBuilderBrushBuild: vi.fn(),
  postBuilderBrushAdd: vi.fn(),
  postBuilderBrushSubtract: vi.fn(),
}));
import { fetchBuilders, postBuilderBrushBuild } from '../api';

afterEach(() => { cleanup(); vi.mocked(fetchBuilders).mockReset(); vi.mocked(postBuilderBrushBuild).mockReset(); });

describe('BuilderBrushPanel', () => {
  it('renders a shape option for each registry entry with no per-shape code', async () => {
    vi.mocked(fetchBuilders).mockResolvedValue([
      { id: 'cylinder', label: 'n-gon prism (height, radius, sides)', icon: 'cylinder', params: [
        { name: 'height', type: 'float', required: true, default: null, choices: null, help: 'prism height' },
      ] },
    ]);
    render(<BuilderBrushPanel sessionId="sid1" onBuilderBrushChanged={() => {}} />);
    await waitFor(() => screen.getByText('n-gon prism (height, radius, sides)'));
  });

  it('renders a generic field for an arbitrary registry param (no hardcoded field list)', async () => {
    vi.mocked(fetchBuilders).mockResolvedValue([
      { id: 'cylinder', label: 'cylinder', icon: 'cylinder', params: [
        { name: 'totally_novel_param', type: 'float', required: true, default: null, choices: null, help: 'a made-up param' },
      ] },
    ]);
    render(<BuilderBrushPanel sessionId="sid1" onBuilderBrushChanged={() => {}} />);
    fireEvent.click(await screen.findByText('cylinder'));
    await waitFor(() => screen.getByLabelText('totally_novel_param'));
  });

  it('calls postBuilderBrushBuild with the shape id and form values on submit', async () => {
    vi.mocked(fetchBuilders).mockResolvedValue([
      { id: 'cylinder', label: 'cylinder', icon: 'cylinder', params: [
        { name: 'radius', type: 'float', required: true, default: null, choices: null, help: 'radius' },
      ] },
    ]);
    vi.mocked(postBuilderBrushBuild).mockResolvedValue({ name: '*Builder' } as any);
    render(<BuilderBrushPanel sessionId="sid1" onBuilderBrushChanged={() => {}} />);
    fireEvent.click(await screen.findByText('cylinder'));
    fireEvent.change(await screen.findByLabelText('radius'), { target: { value: '50' } });
    fireEvent.click(screen.getByText('Build'));
    await waitFor(() => expect(postBuilderBrushBuild).toHaveBeenCalledWith('sid1', 'cylinder', { radius: 50 }));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/panels/BuilderBrushPanel.test.tsx`
Expected: FAIL — component doesn't exist.

- [ ] **Step 3: Write `web/src/panels/BuilderBrushPanel.tsx`**

```typescript
import { useEffect, useState } from 'react';
import { fetchBuilders, postBuilderBrushBuild, type BuilderShape, type SceneActor } from '../api';

interface Props {
  sessionId: string;
  onBuilderBrushChanged: (actor: SceneActor) => void;
}

export function BuilderBrushPanel({ sessionId, onBuilderBrushChanged }: Props) {
  const [shapes, setShapes] = useState<BuilderShape[]>([]);
  const [selected, setSelected] = useState<BuilderShape | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBuilders().then(setShapes).catch((e) => setError(String(e)));
  }, []);

  function selectShape(shape: BuilderShape) {
    setSelected(shape);
    const initial: Record<string, string> = {};
    for (const p of shape.params) {
      if (p.default !== null && p.default !== undefined) initial[p.name] = String(p.default);
    }
    setValues(initial);
  }

  function submitBuild() {
    if (!selected) return;
    const params: Record<string, unknown> = {};
    for (const p of selected.params) {
      const raw = values[p.name];
      if (raw === undefined || raw === '') continue;
      params[p.name] = p.type === 'float' ? parseFloat(raw)
        : p.type === 'integer' ? parseInt(raw, 10)
        : p.type === 'boolean' ? raw === 'true'
        : raw;
    }
    postBuilderBrushBuild(sessionId, selected.id, params)
      .then(onBuilderBrushChanged)
      .catch((e) => setError(String(e)));
  }

  return (
    <div className="builder-brush-panel">
      {error && <div className="builder-brush-error">{error}</div>}
      <div className="builder-brush-shape-list">
        {shapes.map((shape) => (
          <button key={shape.id} onClick={() => selectShape(shape)}>{shape.label}</button>
        ))}
      </div>
      {selected && (
        <div className="builder-brush-param-form">
          {selected.params.map((p) => (
            <label key={p.name}>
              {p.name}
              {p.choices ? (
                <select
                  aria-label={p.name}
                  value={values[p.name] ?? ''}
                  onChange={(e) => setValues((v) => ({ ...v, [p.name]: e.target.value }))}
                >
                  {p.choices.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              ) : p.type === 'boolean' ? (
                <input
                  aria-label={p.name}
                  type="checkbox"
                  checked={values[p.name] === 'true'}
                  onChange={(e) => setValues((v) => ({ ...v, [p.name]: String(e.target.checked) }))}
                  title={p.help}
                />
              ) : (
                <input
                  aria-label={p.name}
                  type={p.type === 'float' || p.type === 'integer' ? 'number' : 'text'}
                  value={values[p.name] ?? ''}
                  onChange={(e) => setValues((v) => ({ ...v, [p.name]: e.target.value }))}
                  title={p.help}
                />
              )}
            </label>
          ))}
          <button onClick={submitBuild}>Build</button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/panels/BuilderBrushPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/panels/BuilderBrushPanel.tsx web/src/panels/BuilderBrushPanel.test.tsx
git commit -m "BuilderBrushPanel: shape picker with a generic, registry-driven param form"
```

---

### Task 15: `BuilderBrushPanel` — Location/Rotation controls and Add/Subtract

**Files:**
- Modify: `web/src/panels/BuilderBrushPanel.tsx`.
- Modify: `web/src/panels/BuilderBrushPanel.test.tsx`.

**Interfaces:**
- Consumes: Task 13's `postStage` (generalized), `postBuilderBrushAdd`, `postBuilderBrushSubtract`.
- Produces: the panel additionally accepts `builderBrushActor: SceneActor | null` (the CURRENT
  builder-brush entry, read by the parent from `/scene` — Task 16 wires this) and renders
  Location/Rotation number inputs plus Add/Subtract buttons.

- [ ] **Step 1: Write the failing tests**

```typescript
it('stages a Location edit through postStage, not a bespoke endpoint', async () => {
  const actor = { name: '*Builder', location: [0, 0, 0], rotation: [0, 0, 0] } as any;
  render(<BuilderBrushPanel sessionId="sid1" builderBrushActor={actor} onBuilderBrushChanged={() => {}} />);
  fireEvent.change(screen.getByLabelText('Location X'), { target: { value: '10' } });
  fireEvent.click(screen.getByText('Move'));
  await waitFor(() => expect(postStage).toHaveBeenCalledWith(
    'sid1', { '*Builder': { Location: '10,0,0' } }));
});

it('Add calls postBuilderBrushAdd and reports the new actor name', async () => {
  vi.mocked(postBuilderBrushAdd).mockResolvedValue({ name: 'Builder_ab12', actor: {} as any });
  const onAdded = vi.fn();
  render(<BuilderBrushPanel sessionId="sid1" builderBrushActor={null} onBuilderBrushChanged={() => {}}
                            onActorAdded={onAdded} />);
  fireEvent.click(screen.getByText('Add'));
  await waitFor(() => expect(onAdded).toHaveBeenCalledWith('Builder_ab12'));
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/panels/BuilderBrushPanel.test.tsx`
Expected: FAIL — no Location controls, no Add/Subtract buttons yet.

- [ ] **Step 3: Extend `BuilderBrushPanel.tsx`**

```typescript
import { postStage, postBuilderBrushAdd, postBuilderBrushSubtract } from '../api';

interface Props {
  sessionId: string;
  builderBrushActor: SceneActor | null;
  onBuilderBrushChanged: (actor: SceneActor) => void;
  onActorAdded?: (name: string) => void;
}

// inside the component, alongside the existing shape-picker state:
function moveTo(x: number, y: number, z: number) {
  postStage(sessionId, { '*Builder': { Location: `${x},${y},${z}` } })
    .catch((e) => setError(String(e)));
}

function addOrSubtract(csg: 'add' | 'subtract') {
  const call = csg === 'add' ? postBuilderBrushAdd : postBuilderBrushSubtract;
  call(sessionId).then((r) => onActorAdded?.(r.name)).catch((e) => setError(String(e)));
}
```

```tsx
{builderBrushActor && (
  <div className="builder-brush-transform">
    {(['X', 'Y', 'Z'] as const).map((axis, i) => (
      <label key={axis}>
        {`Location ${axis}`}
        <input
          aria-label={`Location ${axis}`}
          type="number"
          defaultValue={builderBrushActor.location[i]}
          onChange={(e) => {
            const loc = [...builderBrushActor.location] as [number, number, number];
            loc[i] = parseFloat(e.target.value);
            (BuilderBrushPanel as any)._pendingLocation = loc;   // see note below
          }}
        />
      </label>
    ))}
    <button onClick={() => {
      const loc = (BuilderBrushPanel as any)._pendingLocation ?? builderBrushActor.location;
      moveTo(loc[0], loc[1], loc[2]);
    }}>Move</button>
  </div>
)}
<div className="builder-brush-csg-buttons">
  <button onClick={() => addOrSubtract('add')}>Add</button>
  <button onClick={() => addOrSubtract('subtract')}>Subtract</button>
</div>
```

The `(BuilderBrushPanel as any)._pendingLocation` line is a placeholder for "track the three axis
inputs' pending values before Move is clicked" — replace it with a proper `useState<[number, number,
number]>` tuple seeded from `builderBrushActor.location` (reset via a `useEffect` keyed on
`builderBrushActor.name` changing) rather than a static property hack; the sketch above exists only
to show the wiring shape, not to be pasted verbatim — implement it with real component state.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/panels/BuilderBrushPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/panels/BuilderBrushPanel.tsx web/src/panels/BuilderBrushPanel.test.tsx
git commit -m "BuilderBrushPanel: Location controls via the shared postStage, Add/Subtract buttons"
```

---

### Task 16: Wire `BuilderBrushPanel` into `App.tsx`

**Files:**
- Modify: `web/src/App.tsx`.
- Modify: `web/src/App.test.tsx`.

**Interfaces:**
- Consumes: Task 14/15's `BuilderBrushPanel`; the existing `/scene` poll already in `App.tsx` (read
  its current shape first — this task's ONLY job is finding the builder-brush entry in the existing
  scene-actors state and passing it down, NOT adding a second fetch).

- [ ] **Step 1: Write the failing test**

```typescript
it('renders BuilderBrushPanel with the *Builder entry from the existing scene state', async () => {
  // Follow App.test.tsx's existing pattern for seeding a mocked /scene response containing a
  // "*Builder" actor, then assert BuilderBrushPanel receives it via a rendered child element
  // unique to the panel (e.g. its shape-list container) rather than re-asserting api.ts's own
  // fetch call (App.tsx already fetches /scene for other reasons; this task adds no new fetch).
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/App.test.tsx`
Expected: FAIL — `BuilderBrushPanel` not rendered.

- [ ] **Step 3: Wire it into `App.tsx`**

Read `App.tsx`'s existing scene-state variable (whatever holds the last-fetched `SceneActor[]`) and
its session-id variable first. Add, near wherever other panels are already rendered:

```tsx
<BuilderBrushPanel
  sessionId={sessionId}
  builderBrushActor={sceneActors.find((a) => a.name === '*Builder') ?? null}
  onBuilderBrushChanged={() => refetchScene()}
  onActorAdded={() => refetchScene()}
/>
```

`refetchScene` should be whatever function `App.tsx` already uses to re-poll `/scene` after a mutating
action (check how it currently refreshes after `postStage`/`postSave` and reuse that exact function —
do not add a parallel refetch mechanism).

- [ ] **Step 4: Run test to verify it passes, then the full frontend suite**

Run: `cd web && npx vitest run`
Expected: PASS — every test in `web/`, including this new one.

- [ ] **Step 5: Commit**

```bash
git add web/src/App.tsx web/src/App.test.tsx
git commit -m "App.tsx: mount BuilderBrushPanel, wired to the existing scene poll"
```

---

## Self-Review Notes (for whoever executes this plan)

- **Task 11** (`builder_registry.py`) and **Task 12**'s `_builder_brush_csg`/`session_stage`/
  `session_scene` bodies reference a couple of exact call shapes (`add_parser` for the CLI's parser
  tree, `Path(config.project_maps_dir(project))`, `TrunkLevelSource`, `_parse_location`) that must be
  confirmed against the real current source at implementation time — each is flagged inline with
  "read X first, don't guess." This plan was written against `origin/master` at
  `35bc041475a16a6971221b5651db8b7fc9d78f8c`; re-verify line numbers/signatures if master has moved
  further by the time a task starts, the same way this plan's own spec citations were refreshed
  mid-session (see `dev/docs/board/to-plan/gui-builder-brushes/spec.md`'s commit history).
- **`SceneActor.props`'s exact current shape** (flat list vs. `EffectiveProp` tree) has a discrepancy
  between the Python backend (`uedcli/serve/scene.py`'s docstring: `EffectiveProp` tree) and the TS
  type (`web/src/api.ts`: `[string, string][]`, "raw stored T3D property list") noted during this
  plan's research. This is PRE-EXISTING drift from the separate, unrelated `gui-inspector-*` effort,
  not something this feature's tasks touch or need to resolve — `_build_one_actor`'s reuse (Task 10)
  produces whatever shape the current pipeline already produces, automatically, with no assumption
  baked into this plan about what that shape is. Flag it to whoever owns that other effort if it
  hasn't already been caught.
