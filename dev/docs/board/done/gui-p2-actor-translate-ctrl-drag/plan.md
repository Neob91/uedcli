# GUI P2 slice 1 — move selected actors (staged, explicit Save) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Follow
> `dev/docs/rules/building-features.md` (worktree, verify, review, squash-merge). Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Let a person move the currently-selected actor(s) in any of the GUI's four viewports by
Ctrl/Cmd-dragging, stage the change, and commit it to the trunk with an explicit **Save** — per-
property merge, with mandatory explicit resolution on a real same-property conflict.

**Architecture:** A new backend staging store (`uedcli/serve/snapshots.py`) plus edit logic
(`uedcli/serve/edits.py`) sit between four new FastAPI routes (`/stage`, `/discard`, `/save`,
`/staged`) — plus a conflict check added to the EXISTING `/load` route, symmetric with Save — and
the existing model-side write path (`actor move`'s own load → mutate `.location` →
`TrunkLevelSource.save` pattern — see spec.md "Background", corrected 2026-09-20). On the frontend,
the existing `dragGesture.ts` hook gets a `ctrlKey`/`metaKey` signal threaded into its drag callback
so `Viewport3D.tsx`/`OrthoViewport.tsx` can add a new branch (move the selection along one axis per
button combo in perspective, both axes at once in ortho) alongside their existing camera-nav
branches. A new Save/Discard bar with a conflict-resolution UI drives Save/Discard; the same
conflict-resolution UI is reused for a Load-time conflict, wired to the existing Load action.

**Tech Stack:** Python (FastAPI, existing `uedcli/serve/` conventions); TypeScript/React
(`web/src/`, vitest).

**Spec:** `dev/docs/board/done/gui-p2-actor-translate-ctrl-drag/spec.md` — read it, this plan
argues from it. Also read `dev/docs/board/to-plan/uedcli-human-gui/spec.md`'s "Deferred" section
(the parent P2 ruling) and `dev/docs/rationale/gui-editing.md`.

## Global Constraints

- **Write path**: reuse `uedcli/cli/commands/actor/edit.py`'s `_move` pattern exactly — load the
  trunk via `TrunkLevelSource(trunk_dir).load()`, mutate `level.actors[name].location` (a plain
  `(Decimal, Decimal, Decimal)` tuple field), call `TrunkLevelSource(trunk_dir).save(verb="move",
  args={...}, level=level, touched=[...])`. **Do NOT invent a delete-then-readd path** — that's
  D1/D2, for live-editor-driving verbs only, not this one (spec.md "Background", corrected
  2026-09-20).
- **Flock**: `TrunkLevelSource.save` already takes the per-level `fcntl.flock` internally
  (`uedcli/cli/level_sources.py`, inline `with open(...) as lf: fcntl.flock(lf, fcntl.LOCK_EX)`
  wrapping the actual trunk write). Do not build a second locking mechanism — call `.save()` as-is.
  A narrow TOCTOU window exists between the conflict check's re-read and the eventual locked write —
  Task 2 narrows it with a pre-write re-check but does not close it; see "Known limitations" for the
  full, review-corrected severity assessment (a genuine silent-overwrite risk on a same-actor race,
  not merely a missed-warning gap, though still small-probability for this slice's single-local-user
  scope) — accepted, not fixed, for this slice.
- **No Python exception reaches the user** (`CLAUDE.md`): every new route returns a structured JSON
  error naming the offending value on failure, never a bare traceback.
- **No fallbacks, no back-compat** (`direction/conventions.md`): one code path; this is new
  functionality, no legacy shape to preserve.
- **Sync `def` for new content routes** (matches `app.py`'s existing convention, comment at
  `app.py:577-596`): FastAPI/Starlette runs sync handlers in a threadpool so a trunk read/write never
  blocks the event loop. Only routes that are inherently async (like the existing `switch_level`,
  `ws_endpoint`) use `async def`.
- **Modifier key**: `e.ctrlKey || e.metaKey` everywhere — matches the existing multi-select
  convention (`dragGesture.ts:166`), never an OS-specific swap.
- **Tests**: backend — `UEDCLI_SKIP_NATIVE=1 bin/test uedcli/tests/test_serve_<module>.py -s -q`
  scoped while iterating (per `dev/docs/rules/tests.md`, `TMPDIR` set to a repo-local scratch dir,
  never piped through `tail`); full `bin/test` once before merge. Frontend — `npm test` (`vitest
  run`) under `web/`, scoped to touched files while iterating; `npm run build` (`tsc -b`) and lint
  clean before merge (per `dev/docs/rules/building-features.md`).

---

## File structure

Backend (`uedcli/serve/`, new files):

| File | Responsibility |
|---|---|
| `uedcli/serve/snapshots.py` | Content-addressed staging store: stage/read/discard one level's staged-actor edits. Minimal scope (Task 1) — no LRU pruning, no audit history. |
| `uedcli/serve/edits.py` | Business logic: `stage_locations`, `discard_staged`, `save_staged` (per-actor conflict check + apply via the real write path), `check_load_conflicts` (Task 4). |
| `uedcli/serve/app.py` (modify) | Four new routes: `POST /stage`, `POST /discard`, `POST /save`, `GET /staged`; the existing `POST /load` gains a conflict check (Task 4). |

Frontend (`web/src/`, new + modified):

| File | Responsibility |
|---|---|
| `web/src/scene/dragGesture.ts` (modify) | Thread `ctrlKey`/`metaKey` into the `onDrag` callback so callers can branch before dispatching on `buttons`. |
| `web/src/scene/actorMove.ts` (new) | Pure functions: perspective one-axis-per-combo movement, ortho both-axes-at-once movement. |
| `web/src/scene/Viewport3D.tsx` (modify) | New Ctrl/Cmd-drag branch: live preview + stage-on-release. |
| `web/src/scene/OrthoViewport.tsx` (modify) | Same, ortho variant. |
| `web/src/api.ts` (modify) | `postStage`, `postDiscard`, `postSave`, `fetchStaged`; `postLoad`'s existing return type gains an optional `conflicts` field (Task 4's route change). |
| `web/src/panels/SaveBar.tsx` (new) | Save/Discard buttons + the required (non-dismissible) conflict-resolution UI, reused for BOTH a Save conflict and a Load conflict (Task 4). |
| `web/src/App.tsx` (modify) | Staged-position override state, wires `SaveBar` + the viewports' new move callbacks + the existing Load action's new conflict response. |

---

## Task 1: Backend staging store

**Files:**
- Create: `uedcli/serve/snapshots.py`
- Test: `uedcli/tests/test_serve_snapshots.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True, kw_only=True)
  class StagedActor:
      baseline_location: tuple[Decimal, Decimal, Decimal]
      staged_location: tuple[Decimal, Decimal, Decimal]
      blob_hash: str

  class StagingStore:
      def __init__(self, root: Path) -> None: ...
      def stage(self, level: str, actor_name: str, *, actor_t3d_text: str,
                baseline_location: tuple[Decimal, Decimal, Decimal],
                staged_location: tuple[Decimal, Decimal, Decimal]) -> None: ...
      def read_staged(self, level: str) -> dict[str, StagedActor]: ...
      def clear_actor(self, level: str, actor_name: str) -> None: ...
      def discard(self, level: str) -> None: ...
  ```
  **Decimal throughout, never `float` (Critical fix, review round 1).** `level.actors[name].location`
  is a `(Decimal, Decimal, Decimal)` field (`uedcli/cli/commands/actor/edit.py:69,74-75`), and real
  trunk `Location` values are fractional (e.g. `Location=(X=-1729.945068,...)` — a real fixture,
  `dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers/golden/.../PoolTableLight0/actor.t3d:7`).
  `Decimal('-1729.945068') == float(-1729.945068)` is **`False`** in Python — comparing a captured
  baseline against a freshly-reloaded trunk value must never cross the Decimal/float boundary, or
  Task 2's conflict check spuriously fires on nearly every real Save. `StagingStore` therefore works
  in `Decimal` end to end; only the HTTP boundary (Task 3) converts to/from JSON-native numbers, via
  `Decimal(str(x))` (never `Decimal(x)` on a `float` — that imports float's own binary-representation
  error, e.g. `Decimal(0.1) != Decimal("0.1")`).

  `root` is the project's `.uedcli/snapshots` directory — resolve it with
  `config.state_subdir(project.root, "snapshots", create=True)`, the established idiom for a
  `.uedcli/<name>` project-state subdir (used identically by `preview_cache.py:44`,
  `stash_register.py:40`, `serve/build_pin.py:16`) — **not** `level_sources.py`'s
  `self_ignoring_dir(trunk_dir.parent / ".locks", ...)`, which is a different, trunk-adjacent
  convention for the lock file specifically, not project state.

  Layout: `<root>/blobs/<hash[:2]>/<hash>` (raw actor T3D text, content-addressed, sha256, written
  once — a second `stage()` call with identical text is a no-op on the blob, matching the dedup
  the spec's audit-snapshot design calls for); `<root>/staged/<level>.json` (manifest, each Decimal
  serialized as its exact string form — `{"<actor_name>": {"baseline_location": ["-1729.945068",
  "0", "0"], "staged_location": [...], "blob_hash": "..."}}`).
  **Re-staging an already-staged actor keeps its ORIGINAL `baseline_location`** (only
  `staged_location`/`blob_hash` update) — this is what makes re-dragging an actor not reset its own
  conflict-detection baseline.

- [ ] **Step 1: Failing test** — stage writes a blob + manifest entry; a second `stage()` call for
  the SAME actor with a NEW `staged_location` keeps the original `baseline_location`; `read_staged`
  returns it; `discard` clears the whole level's manifest; `clear_actor` clears just one entry; a
  fractional Decimal round-trips through the JSON manifest EXACTLY (the regression the Critical fix
  above guards against).

```python
import hashlib
from decimal import Decimal
from pathlib import Path
from uedcli.serve.snapshots import StagingStore

def test_stage_read_rebstage_keeps_baseline_discard_clear(tmp_path: Path) -> None:
    store = StagingStore(tmp_path)
    frac = (Decimal("-1729.945068"), Decimal("0"), Decimal("512.5"))
    store.stage(
        "TestLevel", "Brush1",
        actor_t3d_text="Begin Actor Class=Brush Name=Brush1\nEnd Actor\n",
        baseline_location=frac,
        staged_location=(Decimal("10"), Decimal("0"), Decimal("0")),
    )
    staged = store.read_staged("TestLevel")
    assert staged["Brush1"].baseline_location == frac  # exact Decimal round-trip, not `== float(...)`
    assert staged["Brush1"].staged_location == (Decimal("10"), Decimal("0"), Decimal("0"))
    blob_path = tmp_path / "blobs" / staged["Brush1"].blob_hash[:2] / staged["Brush1"].blob_hash
    assert blob_path.is_file()

    # re-stage the SAME actor with a further move: baseline must not move
    store.stage(
        "TestLevel", "Brush1",
        actor_t3d_text="Begin Actor Class=Brush Name=Brush1\nEnd Actor\n",
        baseline_location=(Decimal("999"), Decimal("999"), Decimal("999")),  # a caller bug, by mistake
        staged_location=(Decimal("20"), Decimal("0"), Decimal("0")),
    )
    staged = store.read_staged("TestLevel")
    assert staged["Brush1"].baseline_location == frac  # unchanged
    assert staged["Brush1"].staged_location == (Decimal("20"), Decimal("0"), Decimal("0"))  # updated

    store.stage(
        "TestLevel", "Brush2",
        actor_t3d_text="Begin Actor Class=Brush Name=Brush2\nEnd Actor\n",
        baseline_location=(Decimal("1"), Decimal("1"), Decimal("1")),
        staged_location=(Decimal("2"), Decimal("2"), Decimal("2")),
    )
    store.clear_actor("TestLevel", "Brush1")
    staged = store.read_staged("TestLevel")
    assert "Brush1" not in staged
    assert "Brush2" in staged

    store.discard("TestLevel")
    assert store.read_staged("TestLevel") == {}
```

- [ ] **Step 2:** run it, verify FAIL (`ModuleNotFoundError`/`ImportError`).
- [ ] **Step 3:** implement `StagingStore`. `stage()`: compute
  `hashlib.sha256(actor_t3d_text.encode("utf-8")).hexdigest()`; write the blob only if the path
  doesn't already exist (`Path.mkdir(parents=True, exist_ok=True)` then a plain write, no fsync
  needed — this is a convenience cache, not a durability-critical store, consistent with
  `safety.md`'s framing of the audit-snapshot store as "an editor convenience... not a recovery
  mechanism"); read/write the manifest as plain JSON (`json.load`/`json.dump`, UTF-8, creating the
  file fresh if absent — `{}` on first read) — serialize each `Decimal` as `str(d)`, deserialize as
  `Decimal(s)` (never through `float`). **Keep the "re-stage keeps baseline" logic in `stage()`
  itself**: read the existing manifest entry for `actor_name` first; if present, carry its
  `baseline_location` forward instead of the caller's argument.
- [ ] **Step 4:** run, verify PASS.
- [ ] **Step 5:** commit `feat: staging store for GUI actor edits`.

## Task 2: Backend edit logic — stage/discard/save with per-property conflict check

**Files:**
- Create: `uedcli/serve/edits.py`
- Test: `uedcli/tests/test_serve_edits.py`

**Interfaces:**
- Consumes: `StagingStore` (Task 1); `uedcli.cli.level_sources.TrunkLevelSource` (`.load()` /
  `.save(*, verb, args, level, touched)`); `level.actors[name]` (has a `.location` field, a
  `(Decimal, Decimal, Decimal)` tuple, or `None` if unset — see `uedcli/cli/commands/actor/edit.py`'s
  `_move`, whose OWN `--by` path guards `a.location or (Decimal(0), Decimal(0), Decimal(0))`,
  `edit.py:74`); `uedcli.cli.errors.CommandError` (the actual domain error to raise — see below);
  the actor's stored T3D text (needed for `stage()`'s blob) — find this via whatever the trunk model
  already exposes for one actor's source text (check `uedcli/trunk.py`/`t3dtree.py` for an existing
  per-actor text accessor before writing a new one; if none exists cheaply, serialize a minimal
  round-trip yourself — do not add a new public trunk-writing API for this, only a read).
- Produces (all locations `Decimal`, matching Task 1 — see that task's Critical fix note; a
  `SaveConflict` returned to the FastAPI layer is converted to JSON-native numbers only at the route,
  Task 3, never inside this module):
  ```python
  @dataclass(frozen=True, kw_only=True)
  class SaveConflict:
      name: str
      staged_location: tuple[Decimal, Decimal, Decimal]
      trunk_location: tuple[Decimal, Decimal, Decimal]

  @dataclass(frozen=True, kw_only=True)
  class SaveResult:
      applied: list[str]
      conflicts: list[SaveConflict]

  def stage_locations(
      project, level_name: str, moves: dict[str, tuple[Decimal, Decimal, Decimal]], *,
      store: StagingStore,
  ) -> list[str]: ...

  def discard_staged(project, level_name: str, *, store: StagingStore) -> None: ...

  def save_staged(
      project, level_name: str, *, store: StagingStore,
      resolutions: dict[str, str] | None = None,  # values: "staged" | "trunk"
  ) -> SaveResult: ...
  ```
  `stage_locations`: for each `(name, location)` in `moves`, loads the trunk ONCE (not once per
  actor), reads that actor's CURRENT `.location` as the baseline candidate — **`a.location or
  (Decimal(0), Decimal(0), Decimal(0))`, the exact same default `_move`'s own `--by` path uses**
  (`edit.py:74`), so an unset Location is treated as `(0,0,0)` consistently on both the baseline
  capture and the later Save-time comparison — (only used if the actor isn't already staged —
  `StagingStore.stage` itself keeps an existing baseline, see Task 1) and its T3D text, calls
  `store.stage(...)`. Returns the list of staged names. **Raises `CommandError(f"actor not found:
  {name!r}")`** (`uedcli.cli.errors.CommandError` — the SAME class `app.py`'s own `_require_level`,
  `app.py:117`, and `TrunkLevelSource.load()`, `level_sources.py:60`, already raise, already
  classified 422 by `error_to_status`, `errors.py`'s `isinstance` chain) if a name in `moves` doesn't
  resolve to a real actor. **Do not let a bare `KeyError` from `query.resolve_actor_names`
  propagate** — `error_to_status` does not classify it, and it would fall into the generic
  `except TypeError` 500 branch (`app.py:445-457`) instead of a structured 4xx; catch it and re-raise
  as `CommandError`.

  `save_staged`: reads `store.read_staged(level_name)`; if empty, returns
  `SaveResult(applied=[], conflicts=[])` immediately (no trunk load needed). Otherwise loads the
  trunk ONCE, and for each staged actor: reads `level.actors[name].location or (Decimal(0),
  Decimal(0), Decimal(0))` (same None-default as the baseline capture above); if it **exactly**
  equals the staged entry's `baseline_location` — safe Decimal-to-Decimal `==`, never crossing
  through `float` (Task 1's Critical fix; a value that round-tripped through the trunk unmodified is
  bit-identical Decimal, and an actual modification is never a no-op Decimal artifact) → apply
  (`level.actors[name].location = staged.staged_location`, add to `touched`/`applied`,
  `store.clear_actor(level_name, name)`); if it differs → this is a conflict UNLESS `resolutions`
  names it: `"staged"` applies `staged.staged_location` anyway (same as no-conflict path); `"trunk"`
  applies the CURRENT trunk value (a no-op write, but still clears the stage — the user explicitly
  chose to drop their staged edit); with no resolution entry, leave the actor staged (do NOT call
  `clear_actor`) and add a `SaveConflict` to the result. **Immediately before the final `.save()`
  call**, re-read each about-to-be-applied actor's CURRENT trunk `.location` one more time and
  re-compare against its baseline — narrows (does not eliminate) the TOCTOU window between the
  conflict check above and the locked write (see "Known limitations"); a re-check failure here moves
  that actor from `applied` back to `conflicts` rather than writing over a change that landed in the
  gap. After the loop, if `touched` is non-empty, call `TrunkLevelSource(
  trunk_dir).save(verb="move", args={"names": touched, ...}, level=level, touched=touched)` ONCE
  (not per-actor — one flock acquisition, one trunk write, matching `_move`'s own batch shape when
  `args.names` has multiple entries). Return `SaveResult(applied=touched, conflicts=[...])`.

  `discard_staged`: `store.discard(level_name)`. No trunk interaction.

- [ ] **Step 1: Failing test** — no-conflict Save applies AND preserves an unrelated property (the
  silent-loss regression this whole feature exists to prevent — spec.md "Testing"); a same-property
  conflict is reported, not applied, until a resolution is supplied; `"trunk"` resolution clears the
  stage without changing the trunk; multiple staged actors resolve independently in one Save call.

```python
from decimal import Decimal
from pathlib import Path
from uedcli.serve.edits import discard_staged, save_staged, stage_locations
from uedcli.serve.snapshots import StagingStore
# follow test_preview_native.py's / test_serve_scene.py's existing fixture pattern for a small
# real trunk level under tmp_path (a StubClassIndex + a couple of committed-fixture actors) --
# read that pattern before writing this test's fixture, do not invent a new one

def test_save_no_conflict_preserves_other_property(project, level_name, store: StagingStore) -> None:
    stage_locations(project, level_name, {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)
    # simulate an external (AI/terminal) edit to a DIFFERENT property on the same actor between
    # staging and Save -- e.g. change Brush1's label/folder via the real model-side path, NOT its
    # Location -- then assert Save both applies the staged Location and the external property
    # survives (read the actor back from a fresh trunk load and check both).
    result = save_staged(project, level_name, store=store)
    assert result.applied == ["Brush1"]
    assert result.conflicts == []
    # ... assert the actor's Location == (Decimal("10"), Decimal("0"), Decimal("0")) AND its
    # unrelated property still shows the external edit ...

def test_save_same_property_conflict_blocks_until_resolved(project, level_name, store) -> None:
    stage_locations(project, level_name, {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)
    # simulate an external Location change to Brush1 between staging and Save (e.g. call the real
    # actor-move model path directly against the trunk, bypassing the staging store)
    result = save_staged(project, level_name, store=store)
    assert result.applied == []
    assert len(result.conflicts) == 1
    assert result.conflicts[0].name == "Brush1"
    assert store.read_staged(level_name)  # still staged -- not cleared

    result2 = save_staged(project, level_name, store=store, resolutions={"Brush1": "staged"})
    assert result2.applied == ["Brush1"]
    assert not store.read_staged(level_name)

def test_discard_clears_stage_without_touching_trunk(project, level_name, store) -> None:
    stage_locations(project, level_name, {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)
    discard_staged(project, level_name, store=store)
    assert store.read_staged(level_name) == {}
    # assert the trunk's actual Brush1 Location is unchanged from before staging
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implement per the Interfaces block above. For the "T3D text of one actor" need in
  `stage_locations`, grep `uedcli/trunk.py` and `uedcli/t3dtree.py` for the read side of
  `read_level_with_bodies` (already used by `uedcli/serve/scene.py`) — it very likely already holds
  each actor's raw block text somewhere in the returned `bodies` structure; use that rather than
  re-serializing.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** commit `feat: stage/save/discard edit logic with per-property conflict check`.

## Task 3: Backend FastAPI routes

**Files:**
- Modify: `uedcli/serve/app.py`
- Test: `uedcli/tests/test_serve_edits_routes.py`

**Interfaces:**
- Consumes: `edits.stage_locations`/`discard_staged`/`save_staged` (Task 2); `StagingStore` (Task 1,
  constructed once per app the same way other per-level state is — check how `app.py` already
  constructs/caches per-project state such as the texture/scene cache and follow that convention,
  not a fresh `StagingStore` per request); `errors.error_to_status`.
- **Decimal/JSON boundary lives HERE, only here.** JSON has no `Decimal` type — every route parses
  an incoming `[x, y, z]` JSON array into `tuple(Decimal(str(v)) for v in arr)` (never `Decimal(v)`
  directly on the parsed float — `Decimal(str(v))` avoids importing binary-float representation
  error) before calling into `edits.py`, and serializes an outgoing `Decimal` tuple back to
  `[float(d) for d in loc]` for the response body. `edits.py`/`snapshots.py` never see a `float`.
- Produces (all under the existing `/api/level/{level_name}/...` prefix, sync `def` handlers):
  - `POST /api/level/{level_name}/stage` — body `{"actors": {"<name>": [x, y, z]}}` → `{"staged":
    ["<name>", ...]}`.
  - `POST /api/level/{level_name}/discard` → `{"status": "ok"}`.
  - `POST /api/level/{level_name}/save` — body `{"resolutions": {"<name>": "staged"|"trunk"}}`
    (default `{}`) → `{"applied": [...], "conflicts": [{"name":..., "staged_location":[x,y,z],
    "trunk_location":[x,y,z]}]}`.
  - `GET /api/level/{level_name}/staged` → `{"<name>": {"staged_location":[x,y,z],
    "baseline_location":[x,y,z]}}` — lets a client that reloaded the page recover in-flight staged
    edits instead of silently losing them.

- [ ] **Step 1: Failing test** — using the same `TestClient(create_app(...))` pattern
  `test_serve_app.py` already establishes: stage → GET staged shows it → save with no external
  change → applied, staged now empty; a malformed body (unknown actor name) returns a structured 4xx
  error (`{"error": "...name..."}`), never a 500 traceback — reuse the `fault_route`-style pattern
  already proven for structured-error testing.

```python
def test_stage_save_roundtrip_and_bad_actor_name_is_structured_error(tmp_path):
    app = create_app(fake_project, "TestLevel")
    c = TestClient(app)
    r = c.post("/api/level/TestLevel/stage", json={"actors": {"Brush1": [10.0, 0.0, 0.0]}})
    assert r.status_code == 200 and r.json()["staged"] == ["Brush1"]
    r = c.get("/api/level/TestLevel/staged")
    assert "Brush1" in r.json()
    r = c.post("/api/level/TestLevel/save", json={})
    assert r.json()["applied"] == ["Brush1"] and r.json()["conflicts"] == []
    r = c.get("/api/level/TestLevel/staged")
    assert r.json() == {}

    r = c.post("/api/level/TestLevel/stage", json={"actors": {"NoSuchActor999": [0, 0, 0]}})
    assert r.status_code // 100 == 4
    assert "NoSuchActor999" in r.json()["error"]
```

- [ ] **Step 2:** FAIL. **Step 3:** wire the four routes, each a thin adapter parsing the request
  body into the Task-2 function's arguments and serializing its return value — no business logic in
  `app.py` itself, matching the existing routes' shape (`scene`/`atlas`/etc. are all thin wrappers
  over `uedcli/serve/scene.py`/`textures.py`). **Step 4:** PASS. **Step 5:** commit `feat: stage/
  discard/save/staged HTTP routes`.

## Task 4: Backend — Load-side symmetric conflict check

**Added in review round 2** (Critical finding #2): spec.md's "Persistence" section and Data-flow
step 5 require the existing P1 explicit **Load** action to get the SAME never-silently-overwrite
treatment as Save, in the reverse direction — if Load would pull in an external `Location` change
for an actor with an unsaved staged `Location` edit, it must not silently discard the staged edit.
Round 1 of this plan had no task for this at all.

**Files:**
- Modify: `uedcli/serve/app.py`'s existing `load()` handler (currently `app.py:537-570` — re-read it
  fresh before editing, since Tasks 1–3 land first and line numbers may drift)
- Modify: `uedcli/serve/edits.py` (add one function)
- Test: extend `uedcli/tests/test_serve_edits.py` (the new function) and
  `uedcli/tests/test_serve_edits_routes.py` (the route-level behavior)

**Interfaces:**
- Consumes: `StagingStore` (Task 1); the real `load()` handler's own `lvl` value (a freshly
  `trunk.read_level_with_bodies(...)`-loaded `Level`, already computed BEFORE `_trunk_ref[0]` is
  overwritten — reuse that exact object, do not load the trunk a second time).
- Produces:
  ```python
  def check_load_conflicts(
      level_name: str, incoming_level, *, store: StagingStore,
      resolutions: dict[str, str] | None = None,  # only meaningful value: "accept-load"
  ) -> list[SaveConflict]: ...
  ```
  **Load is a pure read — it never blocks or fails on a conflict, it only reports one.** Unlike
  Save, completing the trunk refresh carries no data-loss risk (nothing is written), so `load()`
  keeps working exactly as it does today (swap `_trunk_ref[0]`, etc.) regardless of what this
  function finds. For each staged actor: read `incoming_level.actors[name].location or
  (Decimal(0), Decimal(0), Decimal(0))` and compare against the staged entry's `baseline_location`
  (identical Decimal-exact comparison to Task 2's `save_staged`). Equal → no conflict, nothing to do
  (the staged edit's own baseline is still valid, since nothing about that actor's Location changed
  externally). Different → **deliberately simplified resolution model** (documented here, not a
  silent choice): the only real action available is `resolutions[name] == "accept-load"`, which
  calls `store.clear_actor(level_name, name)` (the user chose to drop their staged edit and accept
  the external change). **There is no separate "keep-staged" resolution value** — declining to
  resolve (omitting the name from `resolutions`, the default) already IS "keep staged": the staged
  entry is left completely untouched, so the staged edit remains visible client-side and Save will
  re-surface the SAME conflict later if the user tries to Save it — this is correct, not a gap, since
  the trunk genuinely still differs from what the staged edit assumed. Every actor without a
  resolution, whether or not it conflicted, is returned as a `SaveConflict` in the result IF it
  conflicted (an actor with no conflict is never included, resolved or not).

  Called from `load()` right after computing `lvl`/before overwriting `_trunk_ref[0]`. The route
  gains an optional JSON body (today it takes none) — `{"resolutions": {"<name>": "accept-load"}}`,
  default `{}` — and its response gains a `conflicts` field, additive to the existing `{"status":
  "ok"}` shape: `{"status": "ok", "conflicts": [{"name":..., "staged_location":[x,y,z],
  "trunk_location":[x,y,z]}]}` (empty list in the overwhelming common case — no staged edits, or no
  actual clash). **Update the handler's own stale comment** (`app.py:539`, "P1: a plain refresh, no
  staging to conflict with") — that was true before this task, not after.

- [ ] **Step 1: Failing test** — a Load with no staged edits behaves exactly as before (empty
  `conflicts`, trunk refreshes); a Load where the incoming trunk's Location for a staged actor
  MATCHES the staged baseline reports no conflict and does not clear the stage; a Load where it
  DIFFERS reports a conflict and leaves the stage untouched when `resolutions` doesn't name that
  actor; a Load with `resolutions={"<name>": "accept-load"}` for a conflicting actor clears that
  actor's stage and reports no lingering conflict for it.

```python
def test_load_reports_but_never_blocks_on_conflict_and_accept_load_clears_stage(
    project, level_name, store: StagingStore,
) -> None:
    stage_locations(project, level_name, {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)
    # simulate an external Location change to Brush1 in the trunk (bypassing the staging store),
    # then call check_load_conflicts against a fresh trunk.read_level_with_bodies(...) result
    from uedcli.serve.edits import check_load_conflicts
    lvl, *_ = trunk.read_level_with_bodies(maps_root / level_name)  # the real signature Task 4 reuses
    conflicts = check_load_conflicts(level_name, lvl, store=store)
    assert len(conflicts) == 1 and conflicts[0].name == "Brush1"
    assert store.read_staged(level_name)  # untouched -- default is "keep staged"

    conflicts2 = check_load_conflicts(
        level_name, lvl, store=store, resolutions={"Brush1": "accept-load"})
    assert conflicts2 == []
    assert not store.read_staged(level_name)  # cleared
```

- [ ] **Step 2:** FAIL. **Step 3:** implement `check_load_conflicts` in `edits.py`; wire it into
  `load()` per the Interfaces block, reading the real current handler first (cited above) so the
  insertion point and the `_trunk_ref[0]`-write ordering invariant it already documents (a review
  finding from P1: never let a concurrent `/scene` observe a new trunk paired with old
  `_scene_inputs_ref`) stay intact — this task only adds a read-only check before that existing
  sequence, it must not reorder it. **Step 4:** PASS. **Step 5:** commit `feat: Load-side symmetric
  staged-edit conflict check`.

## Task 5: Frontend — thread the Ctrl/Cmd signal into drag events

**Files:**
- Modify: `web/src/scene/dragGesture.ts`
- Test: `web/src/scene/dragGesture.test.ts` (extend the existing file)

**Interfaces:**
- Modifies `DragGestureCallbacks.onDrag`'s signature from `(dx, dy, buttons, altKey) => void` to
  `(dx, dy, buttons, altKey, ctrlOrMeta) => void` (name the 5th param to match `onTap`'s existing
  `additive` naming convention for the same concept, e.g. `additive: boolean`), computed the same
  way `onTap`'s `additive` already is at `dragGesture.ts:166` (`e.ctrlKey || e.metaKey`), but read
  from the pointer-MOVE event inside whatever internal state `onPointerMove` already tracks per drag
  (read the current file to find exactly where to add this — do not change `onTap`'s existing
  behavior or signature).

- [ ] **Step 1: Failing test** — extend the existing `dragGesture.test.ts` `setup()` helper's
  `onDrag` mock assertion to check the 5th argument; a synthetic pointermove event with
  `ctrlKey: true` set reports `additive: true` on the `onDrag` call; one without reports `false`;
  Cmd (`metaKey: true`) also reports `true` (matching the `ctrlKey || metaKey` convention).
- [ ] **Step 2:** FAIL (wrong arg count / undefined). **Step 3:** implement — thread the modifier
  read into the existing pointer-move handler, forwarding it alongside `dx`/`dy`/`buttons`/`altKey`.
  **Do not add a new event listener** — the info is already on the same pointer event `dx`/`dy` come
  from. **Step 4:** PASS. **Step 5:** commit `feat: thread ctrl/cmd modifier into drag callback`.

## Task 6: Frontend — pure axis-movement math

**Files:**
- Create: `web/src/scene/actorMove.ts`
- Test: `web/src/scene/actorMove.test.ts`

**Interfaces:**
- Consumes: `CameraPose`, `cameraBasis` (`web/src/scene/camera.ts`) for the perspective case;
  `OrthoAxis`, `orthoBasis(axis: OrthoAxis): {right, up}` (`web/src/scene/orthoCamera.ts`) for the
  ortho case — **call `orthoBasis` directly, do not reimplement axis selection with a narrower
  `'x'|'y'|'z'` pair** (review round 1 flagged this as risking a silent divergence from the real,
  centralized ortho axis convention `orthoPan` already uses, `orthoCamera.ts:56-61`).
- Produces:
  ```ts
  export type MoveAxis = 'x' | 'y' | 'z'

  // Perspective: ONE axis per combo (owner ruling — spec.md "Interaction design"). Uses dx only.
  export function moveAlongAxis(
    dx: number, axis: MoveAxis, worldUnitsPerPixel: number,
  ): [number, number, number]  // a delta vector with only `axis`'s component non-zero

  // Ortho: ONE combo, BOTH visible axes at once, in the pane's own real basis.
  export function moveInPlane(
    dx: number, dy: number, axis: OrthoAxis, worldUnitsPerPixel: number,
  ): [number, number, number]
  ```
  `PERSPECTIVE_AXIS_BY_BUTTONS: Record<number, MoveAxis>` — a `buttons`-bitmask-keyed lookup (1→'x',
  2→'y', 3→'z', matching LMB/RMB/LMB+RMB per spec.md's "Resolved at plan time" section) — export
  this too, since `Viewport3D.tsx` (Task 8) needs the same combo→axis mapping `Viewport3D.tsx`'s
  existing camera dispatch already keys off `buttons`.

  **`moveInPlane`'s sign is a DELIBERATE, EXPLICIT decision — not "reuse pan's math" (review round
  1 flagged this as a real risk, not a formality).** `orthoPan`'s own doc comment
  (`orthoCamera.ts:50-55`) states the VIEW moves WITH the drag, so on-screen content appears to slide
  OPPOSITE the drag direction — correct feel for panning the camera, but wrong for "grab this actor
  and move it," where the actor should visually follow the cursor (same direction as the drag, not
  opposite). `moveInPlane` therefore calls `orthoBasis(axis)` for the real `{right, up}` vectors
  (getting the axis assignment right) but applies them with the **opposite sign convention from
  `orthoPan`** (`delta = right * dx * worldUnitsPerPixel + up * -dy * worldUnitsPerPixel`, or
  whatever exact sign combination makes the moved actor track the cursor when tested against a real
  drag in-app — pin the exact sign with the same kind of explicit test `moveAlongAxis` already gets
  below, verified in-app during Step 5, not assumed from reading `orthoPan`'s code alone).

- [ ] **Step 1: Failing test** — `moveAlongAxis(10, 'x', 0.1)` returns `[1, 0, 0]` (positive dx →
  positive axis direction — pin this sign convention explicitly, since "drag right = move which
  way" is a real UX choice, not a math accident); `'z'` and `'y'` put the delta in the right slot
  with the other two exactly `0`; `moveInPlane` for the Top pane uses `orthoBasis('top')`'s real
  `right`/`up` vectors (assert against THOSE vectors directly, read from `orthoCamera.ts`, not a
  hand-guessed X/Y pair) and produces a delta whose direction, when added to an actor's position and
  reprojected, moves the actor toward where the cursor dragged — not away from it.

```ts
import { describe, expect, it } from 'vitest'
import { moveAlongAxis, moveInPlane, PERSPECTIVE_AXIS_BY_BUTTONS } from './actorMove'
import { orthoBasis } from './orthoCamera'

describe('moveAlongAxis', () => {
  it('places the delta on the requested axis only, positive dx = positive axis direction', () => {
    expect(moveAlongAxis(10, 'x', 0.1)).toEqual([1, 0, 0])
    expect(moveAlongAxis(10, 'y', 0.1)).toEqual([0, 1, 0])
    expect(moveAlongAxis(10, 'z', 0.1)).toEqual([0, 0, 1])
    expect(moveAlongAxis(-10, 'x', 0.1)).toEqual([-1, 0, 0])
  })
})

describe('PERSPECTIVE_AXIS_BY_BUTTONS', () => {
  it('maps LMB/RMB/LMB+RMB to X/Y/Z', () => {
    expect(PERSPECTIVE_AXIS_BY_BUTTONS[1]).toBe('x')
    expect(PERSPECTIVE_AXIS_BY_BUTTONS[2]).toBe('y')
    expect(PERSPECTIVE_AXIS_BY_BUTTONS[3]).toBe('z')
  })
})

describe('moveInPlane', () => {
  it('moves the actor WITH the drag direction (opposite of orthoPan\'s camera-follows-drag sign)', () => {
    const { right } = orthoBasis('top')  // Vec3 = [number, number, number], NOT {x,y,z}
    const delta = moveInPlane(10, 0, 'top', 0.1)
    // a positive-dx drag must move the actor along +right, not -right (which is what a literal
    // copy of orthoPan's sign would produce) -- assert the dot product is positive, not the exact
    // numbers, so this test doesn't silently encode a wrong sign as "correct" by construction
    const dot = delta[0] * right[0] + delta[1] * right[1] + delta[2] * right[2]
    expect(dot).toBeGreaterThan(0)
  })
})
```

- [ ] **Step 2:** FAIL. **Step 3:** implement, referencing `camera.ts`'s `pan`/`cameraBasis` for the
  perspective sign/scale convention and `orthoCamera.ts`'s `orthoBasis` for the ortho axis vectors
  (with the deliberately-inverted sign described above). **Step 4:** PASS. **Step 5:** commit
  `feat: pure axis-movement math for actor drag-move`; when wired into `OrthoViewport.tsx` (Task 9),
  visually confirm in-app that dragging right moves the actor right on screen, not left — if the
  sign guess above is wrong, fix it there, since that's the real ground truth, not the unit test's
  own dot-product assertion (which only proves internal consistency, not the actual on-screen feel).

## Task 7: Frontend — API client functions

**Files:**
- Modify: `web/src/api.ts`
- Test: `web/src/api.test.ts` (extend the existing file, following its established mock-fetch
  pattern)

**Interfaces:**
- Produces:
  ```ts
  export interface ConflictPayload {
    name: string
    staged_location: [number, number, number]
    trunk_location: [number, number, number]
  }
  export interface SaveResult { applied: string[]; conflicts: ConflictPayload[] }
  export interface StagedActorPayload {
    staged_location: [number, number, number]
    baseline_location: [number, number, number]
  }

  export function postStage(level: string, actors: Record<string, [number, number, number]>): Promise<{ staged: string[] }>
  export function postDiscard(level: string): Promise<{ status: string }>
  export function postSave(level: string, resolutions?: Record<string, 'staged' | 'trunk'>): Promise<SaveResult>
  export function fetchStaged(level: string): Promise<Record<string, StagedActorPayload>>
  ```
  `SaveResult`/`ConflictPayload`/`StagedActorPayload` match Task 3's JSON shapes exactly (field
  names, tuple-vs-array — TypeScript has no tuple/list distinction here, use
  `[number, number, number]`). All four go through the existing `request<T>` helper (`api.ts:174`).
  For the body-serializing POSTs (`postStage`/`postSave`), follow `switchLevel`'s existing pattern
  (`api.ts:221-227` — a `PUT` with `JSON.stringify`), the actual body-serialization precedent in
  this file (`postLoad`/`postRebuild`, `api.ts:231-239`, take no body at all, so they are NOT the
  right template for these two, despite calling the same `request<T>` helper).

  **Also modify the EXISTING `postLoad`** (`api.ts:231`, Task 4's backend change): its return type
  gains `conflicts: ConflictPayload[]` (reuse the same interface Save's conflicts use — identical
  shape), and it gains an optional second parameter,
  `postLoad(level: string, resolutions?: Record<string, 'accept-load'>): Promise<{ status: string;
  conflicts: ConflictPayload[] }>`, serializing `resolutions` into the POST body the same way
  `postSave` does (default `{}` when omitted, matching Task 4's backend default).

- [ ] **Step 1: Failing test** — each function calls the right URL/method/body and returns the
  parsed JSON, following the exact shape of an existing test for e.g. `postRebuild` (no body) and
  `switchLevel` (body) in `api.test.ts` (mock `global.fetch`, assert call args, assert return
  value); `postLoad`'s existing test (if one exists — check before assuming) is extended to also
  assert the new `resolutions` param and `conflicts` field, not just re-tested for the old shape.
- [ ] **Step 2:** FAIL. **Step 3:** implement using `request<T>`. **Step 4:** PASS. **Step 5:**
  commit `feat: api client for stage/discard/save/staged/load-conflicts`.

## Task 8: Frontend — perspective viewport wiring

**Files:**
- Modify: `web/src/scene/Viewport3D.tsx`
- Test: extend whichever test file already covers `Viewport3D`'s camera-dispatch logic in isolation
  (check for one before assuming none exists — the camera math itself is already unit-tested via
  `camera.test.ts`, so this task's own test should focus on the NEW branch-selection logic, not
  re-test `camera.ts`/`actorMove.ts`'s math)

**Interfaces:**
- Consumes: Task 5's extended `onDrag` signature; Task 6's `moveAlongAxis`/
  `PERSPECTIVE_AXIS_BY_BUTTONS`; the component's existing `selectedNames: ReadonlySet<string>` prop
  and actor-position data it already has for rendering; Task 7's `postStage`.
- Produces: a new branch in the existing `onDrag` closure (`Viewport3D.tsx:339-347`), inserted
  BEFORE the existing `altKey`/`buttons` camera-dispatch chain (an actor-move drag must never also
  move the camera):
  ```ts
  onDrag: (dx, dy, buttons, altKey, additive) => {
    if (additive && selectedNames.size > 0) {
      const axis = PERSPECTIVE_AXIS_BY_BUTTONS[buttons]
      if (axis) {
        const delta = moveAlongAxis(dx, axis, worldUnitsPerPixelAt(/* existing camera-distance
          helper this file already has for other screen-space-constant sizing, e.g. the one
          SelectionMarkers.tsx's VertexDot uses — reuse it, don't reinvent world-units-per-pixel */))
        setStagedOffsets((prev) => applyDelta(prev, selectedNames, delta))  // local preview only
        return
      }
    }
    setPose((prev) => { /* existing camera-dispatch chain, unchanged */ })
  },
  ```
  On drag-END (the existing `onPointerUp`/tap-vs-drag boundary this hook already has — do not add a
  second pointer-up listener), if an actor-move drag just finished (accumulated a non-zero total
  delta under the `additive` branch), call `postStage(level, computedNewLocationsForSelection)` and
  clear the local preview accumulator into "confirmed staged" visual state (rendered positions stay
  at the staged location, not the original trunk location, until Save/Discard).

- [ ] **Step 1: Failing test** — a Ctrl-held LMB drag with one selected actor computes the expected
  moved position and does NOT also move the camera (assert `setPose` was never called for that
  gesture); an unmodified drag still moves the camera as before (regression guard); on release,
  `postStage` is called once with the final position (mock it).
- [ ] **Step 2:** FAIL. **Step 3:** implement per the Interfaces block, reading the real current file
  for exact prop names, the real `worldUnitsPerPixel`-style helper's exact name/import, and where
  drag-end already lives. **Step 4:** PASS. **Step 5:** verify by exercising the app (per
  `building-features.md`): load a fixture level, Ctrl-drag a selected actor in the perspective pane,
  watch it move. Commit `feat: perspective-pane Ctrl/Cmd-drag actor move`.

## Task 9: Frontend — ortho viewport wiring

**Files:**
- Modify: `web/src/scene/OrthoViewport.tsx`
- Test: same pattern as Task 8, ortho-specific

**Interfaces:**
- Same shape as Task 8, but the new branch uses `moveInPlane(dx, dy, axis, worldUnitsPerPixel)`
  (Task 6) — `axis` is whichever `OrthoAxis` this pane already is (`'top'`/`'front'`/`'side'`, read
  from wherever `OrthoViewport.tsx` already knows its own pane kind for `orthoPan`'s own calls) — no
  `buttons`-keyed lookup needed, ortho only has ONE combo. Inserted before
  `OrthoViewport.tsx:214-221`'s existing pan/zoom dispatch.

- [ ] **Step 1: Failing test** — mirrors Task 8's, ortho-specific (a Ctrl-held drag moves along both
  of the pane's visible axes and does not pan the camera; unmodified drag still pans; release
  stages).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS. **Step 5:** verify in-app (all three
  ortho panes). Commit `feat: ortho-pane Ctrl/Cmd-drag actor move`.

## Task 10: Frontend — Save/Discard bar + conflict resolution UI (Save AND Load)

**Files:**
- Create: `web/src/panels/SaveBar.tsx`, `web/src/panels/ConflictResolver.tsx` (shared by both the
  Save path and the Load path — same row shape, different resolution vocabulary)
- Test: `web/src/panels/SaveBar.test.tsx`, `web/src/panels/ConflictResolver.test.tsx`
- Modify: `web/src/App.tsx` (mount `SaveBar`, own the "is anything staged" state, wire Save/Discard
  handlers, wire the new per-viewport move callbacks from Tasks 8–9 to update this state; find the
  EXISTING Load button's click handler — the current `postLoad(level)` call site — and wire Task 7's
  extended `postLoad` return value into `ConflictResolver` there too)

**Interfaces:**
- Consumes: Task 7's `postSave`/`postDiscard`/`fetchStaged`/extended-`postLoad`; `App.tsx`'s
  existing selection state shape (`selectedNames`, `Set<string>`) for deciding when anything is
  staged (a simple `hasStaged: boolean` / `stagedNames: Set<string>` piece of state is enough — do
  not duplicate the backend's full staged-actor bookkeeping client-side, re-derive display info from
  `fetchStaged` when needed).
- Produces:
  ```ts
  // shared by both call sites -- same row shape, different resolution vocabulary
  export function ConflictResolver(props: {
    conflicts: ConflictPayload[]
    resolutionLabels: { mine: string; theirs: string }  // "Keep my move"/"Keep trunk value" for
                                                          // Save; "Keep my move"/"Accept trunk" for Load
    onResolve: (resolutions: Record<string, string>) => void  // 'staged'|'trunk' for Save,
                                                                // 'accept-load' for Load (mine-only)
  }): JSX.Element | null  // null when conflicts is empty
  ```
  `<SaveBar level stagedNames onSaved onDiscarded />` — renders nothing when
  `stagedNames.size === 0`; otherwise a Save button, a Discard button, and — when a `postSave` call
  returns non-empty `conflicts` — mounts `<ConflictResolver conflicts=... resolutionLabels={{mine:
  "Keep my move", theirs: "Keep trunk value"}} onResolve={(r) => postSave(level, r)} />`; nothing
  else on the page is a substitute action — Save cannot be pressed again for the still-conflicting
  actors until every row in the current conflict set is resolved (or the whole conflict dismissed as
  "discard just this actor" — which needs `POST /discard` to accept an optional `actors: string[]`
  to discard a subset, since `stage_locations` has no equivalent partial-drop; extend Task 3's
  `/discard` route this way rather than inventing a second mechanism, and note the extension in this
  task's commit message since Task 3 didn't originally call for it).

  At the existing Load button's click handler: call the extended `postLoad(level)`; if the response's
  `conflicts` is non-empty, mount the SAME `<ConflictResolver conflicts=... resolutionLabels={{mine:
  "Keep my move", theirs: "Accept trunk"}} onResolve={(r) => postLoad(level,
  mapToAcceptLoadOnly(r))} />` — `theirs`/`mine` picks on the Load path only ever produce the single
  real `"accept-load"` resolution value (Task 4/7's deliberate simplification: a "mine" pick is a
  no-op, since declining to resolve already keeps the staged edit) — `mapToAcceptLoadOnly` filters
  the resolver's generic `Record<string,string>` down to just the `theirs`-picked names, each mapped
  to `"accept-load"`.

- [ ] **Step 1: Failing test** — `SaveBar`: renders nothing with no staged names; renders Save/
  Discard with staged names; clicking Save calls `postSave`; a `postSave` response with `conflicts`
  mounts `ConflictResolver` and does NOT let Save be clicked again without resolving.
  `ConflictResolver`: renders one row per conflict with both locations shown; picking a resolution
  per row and confirming calls `onResolve` with the right map; renders nothing (`null`) for an empty
  `conflicts` array. A THIRD test at the `App.tsx`/Load level (or a focused test of the new Load
  click handler in isolation): a `postLoad` response with conflicts mounts the SAME
  `ConflictResolver`, and choosing "Accept trunk" on a row calls `postLoad` again with
  `{"<name>": "accept-load"}`.
- [ ] **Step 2:** FAIL. **Step 3:** implement (plain conditional-render React — no dialog/modal
  library exists in this codebase, confirmed by research; do not add one for this). **Step 4:**
  PASS. **Step 5:** wire into `App.tsx`; verify end-to-end in-app: stage a move, Save with no
  conflict (applies, bar disappears), stage another move, externally change the same actor's
  Location via the CLI (`bin/uedcli actor move <name> --to ...`) before Save, click Save, confirm
  the conflict UI appears and blocks, resolve it, confirm it applies; separately, stage a move,
  externally change the same actor via the CLI, click the existing Load button, confirm the SAME
  conflict UI appears there too, resolve it, confirm the staged edit's fate matches the pick.
  Commit `feat: Save/Discard bar + shared Save/Load conflict resolution UI`.

---

## Known limitations (explicitly out of scope for this slice, not silently omitted)

- **TOCTOU race in the conflict check — re-scoped after review round 2.** `save_staged`'s initial
  "read current Location, compare to baseline" step is not itself lock-protected against a write
  landing in the gap before the eventual `TrunkLevelSource.save()` call takes its own flock. This is
  **not** merely "a conflict that should have been caught isn't" — `t3dtree.py`'s `write_actor_tree`
  is last-writer-wins per actor with no lock held from `load()` through the eventual flocked
  `write_level()`, so two concurrent writers to the SAME actor can genuinely interleave such that one
  process's real, already-committed write is silently clobbered by the other's stale-load-based
  write — a real silent loss, not just a missed warning, and it directly undercuts this feature's own
  headline guarantee ("never a blanket confirm-and-overwrite"). Task 2's pre-write re-check
  (immediately before the final `.save()`) narrows this window from "the whole conflict-check +
  round-trip" to "the gap between that re-check and the flock acquisition a few lines later" — it
  does not close it. For a single local human user (no auth, localhost-only GUI) racing against an
  occasional AI verb, the remaining window is small and the trigger requires a genuine same-actor,
  same-property collision in that narrow gap — accepted for this slice, not fixed, and explicitly
  NOT equivalent in severity to "today's CLI has no compare-before-write at all" (the CLI's gap is a
  baseline absence of a feature; this feature's residual gap is a narrowed-but-real hole in a
  guarantee it explicitly claims to provide). A full fix needs the SAME lock held across the whole
  read-compare-write sequence, which requires understanding `TrunkLevelSource.save`'s complete body
  (this plan only confirmed its flock-wrapped tail, not what precedes it) — out of scope here, filed
  as a follow-up concern rather than silently accepted as equivalent to the status quo.
- **No cross-page-refresh recovery of IN-PROGRESS drag preview** — only committed-to-stage (i.e.
  post drag-release) edits survive a refresh, via `GET /staged`. A drag interrupted mid-gesture by a
  page reload loses that one gesture's preview, same as any other unsaved interaction.
- **`Ctrl/Cmd+Alt+LMB`** behavior is unspecified (spec.md "Open") — whichever of the Ctrl-move or
  Alt-orbit branch the implementation happens to check first in Task 8 (perspective) wins; revisit
  if this reads as broken once built.
- **Rotate/scale, property edits, create/delete** are out of scope (spec.md "Non-goals").

## Verification (pre-merge, per `building-features.md` + `tests.md`)

- Backend: `UEDCLI_SKIP_NATIVE=1 bin/test uedcli/tests/test_serve_snapshots.py
  uedcli/tests/test_serve_edits.py uedcli/tests/test_serve_edits_routes.py -s -q` while iterating;
  full `bin/test` once before merge.
- Frontend (under `web/`): `npm test` scoped to touched files while iterating; `npm run build`
  (`tsc -b`) and lint clean; full `npm test` once before merge.
- Exercise the app per `building-features.md`: `uedcli serve <fixture-level>`, Ctrl/Cmd-drag a
  selected actor in each of the four panes, Save with no conflict, Save with a manufactured conflict
  (externally move the same actor via the CLI mid-stage) and resolve it, Discard a staged edit.

## Self-review

- **Spec coverage**: interaction design (Ctrl/Cmd-drag, 3 perspective combos, 1 ortho combo, moves
  the whole selection) → Tasks 5/6/8/9. Persistence (staging, per-property merge, mandatory
  resolution, per-actor apply) → Tasks 1/2/10. **Load's symmetric conflict check (spec.md
  "Persistence" + Data-flow step 5 + Testing) → Task 4 — genuinely missing from round-1 of this
  plan, added in round 2 after review caught the gap; the previous version of this line claimed
  coverage via `GET /staged` (Task 3), which is a DIFFERENT mechanism (page-refresh recovery, not
  the Load-button conflict check) and was a wrong claim, not just an omission.** Data flow's 5 steps
  → Task 4 (Load), Task 3 (stage/save/discard routes), Task 10 (the UI driving all of them). Error
  handling (structured errors) → Task 2/3/4. Testing section → each task's own Step 1. ✔
- **Placeholders**: every task has concrete test code and a named implementation approach; no
  "TBD"/"handle edge cases" left bare. Two deliberately-deferred choices are flagged as build-time
  picks with named options rather than left silently unresolved: Task 10's "discard one conflicting
  actor" mechanism, and Task 4's "keep-staged is the default (no resolution needed), only
  'accept-load' is a real resolution value" simplification. ✔
- **Type consistency**: `StagedActor`/`SaveConflict`/`SaveResult` (Task 1/2) are consumed by name in
  Task 3's and Task 4's routes and Task 7/10's frontend types; `PERSPECTIVE_AXIS_BY_BUTTONS`/
  `moveAlongAxis`/`moveInPlane` (Task 6) are consumed by name in Tasks 8/9; the `additive` 5th
  `onDrag` param (Task 5) is consumed by name in Tasks 8/9. ✔
- **Review-round-2 fixes verified applied**: Decimal end-to-end in Tasks 1/2/3 (no float crossing);
  `CommandError` (not a guessed exception) in Task 2; `config.state_subdir` (not the lock-dir helper)
  in Task 1; the pre-write re-check narrowing the TOCTOU window in Task 2; `moveInPlane` taking a
  real `OrthoAxis` and calling `orthoBasis` directly, with an explicit sign decision, in Task 6. ✔
