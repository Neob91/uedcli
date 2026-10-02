# Session Management UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a session-picker landing screen, path-based `/session/<id>/` URLs, session renaming,
session delete-with-confirmation, and a fix distinguishing "session deleted" from "session
superseded" in every place that distinction currently gets flattened.

**Architecture:** A new dependency-free `route.ts` module owns pathname parsing + navigation.
`App.tsx` splits into a thin `App` (route dispatch: picker vs. editor) and the renamed
`SessionEditor` (today's whole `App` body, now taking `sessionId` as a prop instead of reading the
URL itself). `SessionContext.tsx`'s `useSession` hook is redesigned to take that id as an argument
and drop its own auto-create/URL-write logic entirely — the picker now owns session creation.
Three new frontend components (`SessionPicker`, `SessionLabel`, `InlineRename`) and one shared
backend helper (`_claim_conflict_response`) do the rest.

**Tech Stack:** FastAPI/Starlette (backend), React + TypeScript + vitest (frontend), `bin/test`
(Python), `npx vitest run` / `npx tsc -b` (frontend).

**Spec:** `docs/superpowers/specs/2026-09-23-session-management-ui-design.md` — read it in full
before starting; this plan argues from it and does not repeat its rationale.

## Global Constraints

- No back-compat cruft: `?session=<id>` support is deleted outright, not kept alongside the new
  path-based routing (spec, "Old bookmarks break, deliberately").
- No fallbacks: a claim-check failure must resolve to exactly one of "deleted" or "superseded" —
  never a generic/ambiguous third state.
- Run Python tests via `bin/test`, never bare `pytest` (`dev/docs/rules/tests.md`).
- Run the frontend suite via `npx vitest run` inside `web/`, and `npx tsc -b` before committing any
  task that touches `.ts`/`.tsx` files. `web/node_modules` may need `npm install
  --prefer-offline --no-audit --no-fund` first if missing in this worktree.
- Every new/changed backend route error follows this codebase's structured-error convention:
  `{"error": "<message>"}`, never a bare traceback (`uedcli/serve/errors.py`).
- Commit after each task, one commit per task, following this repo's existing terse commit-message
  style (see recent commits on this branch for tone).
- `uedcli/serve/app.py` is large; every task touching it gives exact anchor text for `Edit`-shaped
  changes rather than reproducing the whole file.

## File Structure

**Backend:**
- Modify `uedcli/serve/sessions.py`: `SessionRecord` gains `name`; `get_session` reads it back;
  `touch_session`/`set_last_seen_generation` carry it forward; new `set_name`.
- Modify `uedcli/serve/app.py`: new `_claim_conflict_response` helper, applied to 6 routes; new
  `rename_session_route`; `list_sessions_route`/`get_session_route` responses gain `name`; new
  `spa_session_route`; `ws_endpoint`'s mid-poll loop splits `closed` vs `superseded`.

**Frontend:**
- Modify `web/src/api.ts`: `reason` on the thrown Error, `isClosedError`, `ClosedMessage`,
  `SessionSummary`/`SessionDetail` gain `name`, `openChangesAvailableSocket` gains `onClosed`, new
  `renameSession`/`deleteSession` calls.
- Modify `web/src/reload.ts`: `subscribeChangesAvailable` gains `onClosed`.
- Create `web/src/session/route.ts`: pathname parsing, `navigate`, `useRoute` hook.
- Modify `web/src/session/SessionContext.tsx`: `useSession(sessionId)` redesign, `markClosed`.
- Create `web/src/session/InlineRename.tsx`: shared click-to-edit component.
- Modify `web/src/session/SessionDropdown.tsx`: name-or-level + `title`.
- Create `web/src/session/SessionLabel.tsx`: toolbar identity label + rename + back-to-picker.
- Create `web/src/session/SessionPicker.tsx`: the landing screen.
- Modify `web/src/panels/SaveBar.tsx`: `onClosed` prop.
- Modify `web/src/App.tsx`: split into `App` (routing) + `SessionEditor` (today's body), wire
  `onClosed` everywhere `onSuperseded` is wired.

---

### Task 1: Backend — `name` field, and the name-erasure hazard

**Files:**
- Modify: `uedcli/serve/sessions.py`
- Test: `uedcli/tests/test_serve_sessions.py`

**Interfaces:**
- Produces: `SessionRecord.name: str | None`, `set_name(sessions_root: Path, session_id: str, name:
  str | None) -> None`.

- [ ] **Step 1: Write the failing tests**

Add to `uedcli/tests/test_serve_sessions.py`:

```python
def test_create_session_defaults_name_to_none(tmp_path):
    rec = create_session(tmp_path, "unatco")
    assert rec.name is None


def test_set_name_persists_and_is_read_back(tmp_path):
    rec = create_session(tmp_path, "unatco")
    set_name(tmp_path, rec.id, "My Session")
    assert get_session(tmp_path, rec.id).name == "My Session"


def test_set_name_to_none_clears_it(tmp_path):
    rec = create_session(tmp_path, "unatco")
    set_name(tmp_path, rec.id, "My Session")
    set_name(tmp_path, rec.id, None)
    assert get_session(tmp_path, rec.id).name is None


def test_set_name_on_unknown_session_is_a_noop(tmp_path):
    set_name(tmp_path, "doesnotexist", "whatever")  # must not raise


def test_touch_session_preserves_name(tmp_path):
    rec = create_session(tmp_path, "unatco")
    set_name(tmp_path, rec.id, "My Session")
    old_index = tmp_path / rec.id / "index.json"
    old_index.write_text(old_index.read_text().replace(rec.last_active_at, "2000-01-01T00:00:00Z"))
    touch_session(tmp_path, rec.id)
    assert get_session(tmp_path, rec.id).name == "My Session"


def test_set_last_seen_generation_preserves_name(tmp_path):
    rec = create_session(tmp_path, "unatco")
    set_name(tmp_path, rec.id, "My Session")
    set_last_seen_generation(tmp_path, rec.id, 5)
    assert get_session(tmp_path, rec.id).name == "My Session"
```

Update the test file's import line to add `set_name`:
```python
from uedcli.serve.sessions import (
    create_session, get_session, list_sessions, delete_session, touch_session, set_name,
    SessionIndexCorruptError,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test uedcli/tests/test_serve_sessions.py -k "name" -v`
Expected: FAIL — `ImportError: cannot import name 'set_name'` (or `AttributeError: 'SessionRecord'
object has no attribute 'name'`).

- [ ] **Step 3: Implement**

In `uedcli/serve/sessions.py`:

Edit the `SessionRecord` dataclass — add one field after `last_seen_generation`:
```python
@dataclass(frozen=True, kw_only=True)
class SessionRecord:
    id: str
    level: str
    created_at: str
    last_active_at: str
    last_seen_generation: int = 0
    name: str | None = None
```

Edit `get_session`'s reconstruction to read it back, same backward-compatible pattern
`last_seen_generation` already uses:
```python
        return SessionRecord(
            id=data["id"], level=data["level"], created_at=data["created_at"],
            last_active_at=data["last_active_at"],
            last_seen_generation=data.get("last_seen_generation", 0),
            name=data.get("name"),
        )
```

Edit `touch_session`'s write dict — add `"name": rec.name`:
```python
    atomic_write_json(_index_path(sessions_root, session_id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": _now(), "last_seen_generation": rec.last_seen_generation,
        "name": rec.name,
    })
```

Edit `set_last_seen_generation`'s write dict — add `"name": rec.name`:
```python
    atomic_write_json(_index_path(sessions_root, session_id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": rec.last_active_at, "last_seen_generation": generation,
        "name": rec.name,
    })
```

Add a new function, right after `set_last_seen_generation`:
```python
def set_name(sessions_root: Path, session_id: str, name: str | None) -> None:
    """Empty/whitespace-only persists as `None` -- the caller (`app.py`'s rename route) is
    responsible for that normalization; this just writes whatever it's given."""
    rec = get_session(sessions_root, session_id)
    if rec is None:
        return
    atomic_write_json(_index_path(sessions_root, session_id), {
        "id": rec.id, "level": rec.level, "created_at": rec.created_at,
        "last_active_at": rec.last_active_at, "last_seen_generation": rec.last_seen_generation,
        "name": name,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test uedcli/tests/test_serve_sessions.py -v`
Expected: PASS, all tests including the pre-existing ones.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/sessions.py uedcli/tests/test_serve_sessions.py
git commit -m "Add a name field to SessionRecord, carried through touch/generation writes"
```

---

### Task 2: Backend — `_claim_conflict_response`, applied to the 5 existing routes

**Files:**
- Modify: `uedcli/serve/app.py`
- Test: `uedcli/tests/test_serve_app.py`

**Interfaces:**
- Produces: `_claim_conflict_response(session_id: str, *, suffix: str = "") -> JSONResponse` (a
  closure inside `create_app`, alongside `_require_session`/`_require_level`).
- Consumes: `sessions.get_session`, `JSONResponse` (already imported).

- [ ] **Step 1: Write the failing tests**

Add to `uedcli/tests/test_serve_app.py` (uses `_write_fixture_trunk`/`SimpleNamespace`/`create_app`,
already imported at the top of this file):

```python
def test_claim_check_fails_reports_deleted_when_the_session_is_actually_gone(tmp_path):
    """The bug this task fixes: a stale token on a session that's genuinely gone used to always
    say "superseded" -- `_claims.check` fails first, and the existence check only ever ran on the
    SUCCESS branch. `forget()` (called by delete) removes the registry entry outright, so a plain
    stale token here still needs a DIFFERENT token to prove it's the claim check that's failing,
    not an auto-accept."""
    from uedcli.serve import sessions

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("Brush1")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)

    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)
    sessions.delete_session(app.state.sessions_root, sess.id)

    r = c.post(f"/api/session/{sess.id}/discard", json={}, headers={"X-Claim-Token": token})

    assert r.status_code == 409
    assert r.json()["error"] == "session deleted"


def test_claim_check_fails_reports_superseded_when_the_session_still_exists(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("Brush1")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)

    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    stale_token = app.state.claims.mint(sess.id)
    app.state.claims.mint(sess.id)  # a second mint supersedes the first, session still exists

    r = c.post(f"/api/session/{sess.id}/discard", json={}, headers={"X-Claim-Token": stale_token})

    assert r.status_code == 409
    assert r.json()["error"] == "session superseded"
```

Add `from uedcli.serve import sessions` to this test file's imports if not already present at the
top (check first — `test_serve_app.py` already imports `sessions` in several test bodies via local
imports; add a top-level import only if there isn't one already, matching the file's existing
style of importing per-test where that's the pattern).

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test uedcli/tests/test_serve_app.py -k "claim_check_fails" -v`
Expected: FAIL — the deleted-session case reports `"session superseded"` instead of `"session
deleted"`.

- [ ] **Step 3: Implement**

In `uedcli/serve/app.py`, add `_claim_conflict_response` right after `_require_session`'s own
definition (both are small shared helpers used by every session-scoped route below them):

```python
    def _claim_conflict_response(session_id: str, *, suffix: str = "") -> JSONResponse:
        """A claim-token check that just failed can mean one of two different things, and until
        now every call site here defaulted to the wrong one whenever the session was ALSO gone:
        `ClaimRegistry.check` fails on a genuine takeover (another window minted a fresher claim,
        session still exists), but it does NOT fail once `forget()` (called after a delete) has
        cleared the registry entry -- `check`'s own restart-safety rule auto-accepts any token for
        an id it doesn't recognize. So the misleading case is the narrow window BEFORE `forget()`
        runs: a stale token still fails the claim check, and until this helper, that branch never
        looked at whether the session still existed before answering "superseded". `suffix` lets
        `session_rebuild`'s mid-solve variant keep its own wording."""
        if sessions.get_session(_sessions_root, session_id) is None:
            return JSONResponse(status_code=409, content={"error": f"session deleted{suffix}"})
        return JSONResponse(status_code=409, content={"error": f"session superseded{suffix}"})
```

Then replace the bare 409 at each of the five sites. Each is currently:
```python
            if not _claims.check(session_id, token):
                return JSONResponse(status_code=409, content={"error": "session superseded"})
```
inside `session_load`, `session_stage`, `session_discard`, `session_save` — replace each with:
```python
            if not _claims.check(session_id, token):
                return _claim_conflict_response(session_id)
```

And in `session_rebuild`'s post-solve check, currently:
```python
            if not _claims.check(session_id, token):
                # Superseded mid-solve (a newer claim minted while the solve above was running):
                # drop the result, write nothing.
                logger.info("session_rebuild_superseded", extra={"session_id": session_id})
                return JSONResponse(status_code=409,
                                    content={"error": "session superseded mid-solve"})
```
replace the `return` line only:
```python
            if not _claims.check(session_id, token):
                # Superseded mid-solve (a newer claim minted while the solve above was running):
                # drop the result, write nothing.
                logger.info("session_rebuild_superseded", extra={"session_id": session_id})
                return _claim_conflict_response(session_id, suffix=" mid-solve")
```

Do NOT touch the WS pre-accept rejection (`ws_endpoint`, before the poll loop) or
`delete_session_route`'s own claim check — both already confirmed existence a few lines earlier in
the same request, so a mismatch there is never actually a deletion (spec, "Distinguishing
'deleted' from 'superseded'").

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test uedcli/tests/test_serve_app.py -v`
Expected: PASS, including every pre-existing test in this file (this touches 5 shared routes —
the full-file run matters here, not just the new tests).

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Distinguish deleted from superseded when the claim check itself fails"
```

---

### Task 3: Backend — rename route, and `name` in the two read routes

**Files:**
- Modify: `uedcli/serve/app.py`
- Test: `uedcli/tests/test_serve_app.py`

**Interfaces:**
- Consumes: `sessions.set_name` (Task 1), `_require_session`, `_claim_conflict_response` (Task 2).
- Produces: `POST /api/session/{id}/rename` → `{"id", "level", "created_at", "last_active_at",
  "name"}`; `GET /api/sessions` and `GET /api/session/{id}` both gain `"name"` in their response.

- [ ] **Step 1: Write the failing tests**

```python
def test_rename_session_sets_the_name(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("Brush1")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)

    r = c.post(f"/api/session/{sess.id}/rename", json={"name": "My Session"},
              headers={"X-Claim-Token": token})

    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "My Session"
    assert "claim_token" not in body
    assert sessions.get_session(app.state.sessions_root, sess.id).name == "My Session"


def test_rename_session_with_empty_name_clears_it(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("Brush1")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)
    sessions.set_name(app.state.sessions_root, sess.id, "My Session")

    r = c.post(f"/api/session/{sess.id}/rename", json={"name": "   "},
              headers={"X-Claim-Token": token})

    assert r.status_code == 200
    assert r.json()["name"] is None
    assert sessions.get_session(app.state.sessions_root, sess.id).name is None


def test_rename_session_unknown_id_is_422(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("Brush1")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)

    r = c.post("/api/session/doesnotexist/rename", json={"name": "x"},
              headers={"X-Claim-Token": "whatever"})

    assert r.status_code == 422


def test_rename_session_stale_token_reports_superseded(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("Brush1")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    stale_token = app.state.claims.mint(sess.id)
    app.state.claims.mint(sess.id)

    r = c.post(f"/api/session/{sess.id}/rename", json={"name": "x"},
              headers={"X-Claim-Token": stale_token})

    assert r.status_code == 409
    assert r.json()["error"] == "session superseded"


def test_list_sessions_route_includes_name(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("Brush1")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    sessions.set_name(app.state.sessions_root, sess.id, "My Session")

    r = c.get("/api/sessions")

    assert r.status_code == 200
    [entry] = [s for s in r.json()["sessions"] if s["id"] == sess.id]
    assert entry["name"] == "My Session"


def test_get_session_route_includes_name(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("Brush1")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    sessions.set_name(app.state.sessions_root, sess.id, "My Session")

    r = c.get(f"/api/session/{sess.id}")

    assert r.status_code == 200
    assert r.json()["name"] == "My Session"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test uedcli/tests/test_serve_app.py -k "rename or includes_name" -v`
Expected: FAIL — `404 Not Found` for the new route (doesn't exist yet), `KeyError: 'name'` for the
two read-route tests.

- [ ] **Step 3: Implement**

Find `list_sessions_route` (the `GET /api/sessions` handler) and `get_session_route` (`GET
/api/session/{id}`) in `uedcli/serve/app.py`. Each currently builds its response dict from a
`SessionRecord`/summary without `name` — add `"name": rec.name` (or the loop variable's own name,
matching whatever local name each route already uses for the record) to each response dict they
build.

Add the new route right after `get_session_route`'s definition:

```python
    @app.post("/api/session/{session_id}/rename")
    def rename_session_route(session_id: str, body: dict, request: Request) -> dict:
        # Claim-gated and mutating like load/stage/discard/save/rebuild -- resolved through
        # `_require_session` (422 on an unknown id), not GET/DELETE's own bare 404.
        session = _require_session(session_id)
        token = request.headers.get("X-Claim-Token", "")
        with _claims.lock_for(session_id):
            if not _claims.check(session_id, token):
                return _claim_conflict_response(session_id)
            raw_name = (body or {}).get("name") or ""
            name = raw_name.strip() or None
            sessions.set_name(_sessions_root, session_id, name)
        return {"id": session.id, "level": session.level, "created_at": session.created_at,
                "last_active_at": session.last_active_at, "name": name}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test uedcli/tests/test_serve_app.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Add the session rename route, and surface name in the two read routes"
```

---

### Task 4: Backend — the new `/session/{id}` SPA route

**Files:**
- Modify: `uedcli/serve/app.py`
- Test: `uedcli/tests/test_serve_app.py`

**Interfaces:**
- Produces: `GET /session/{session_id}` → `index.html`'s bytes, gated on `frontend_dist is not
  None`, registered before the existing `StaticFiles` mount.

- [ ] **Step 1: Write the failing test**

Find where `create_app` mounts `StaticFiles` (search for `frontend_dist` in `app.py`) — that's the
gating pattern to mirror. Add:

```python
def test_session_path_route_serves_index_html(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("Brush1")])
    project = SimpleNamespace(root=str(root), maps=None)
    frontend_dist = tmp_path / "dist"
    frontend_dist.mkdir()
    (frontend_dist / "index.html").write_text("<!doctype html><title>t</title>")
    app = create_app(project, "TestLevel", frontend_dist=frontend_dist)
    c = TestClient(app)

    r = c.get("/session/some-id")

    assert r.status_code == 200
    assert "<!doctype html>" in r.text


def test_session_path_route_absent_without_a_built_frontend(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("Brush1")])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")  # no frontend_dist
    c = TestClient(app)

    r = c.get("/session/some-id")

    assert r.status_code == 404
```

Check `create_app`'s real signature first (`def create_app(project, level: str | None = None, *,
fault_route: bool = False) -> FastAPI`) — if it doesn't already take a `frontend_dist` parameter,
find how the existing `StaticFiles` mount gets its `frontend_dist` value (likely a module-level
default or a separate call site outside tests) and adjust the two tests above to match however this
codebase's OTHER tests already exercise the `StaticFiles` mount's gating — search
`test_serve_app.py` for `frontend_dist` or `StaticFiles` first; mirror whatever pattern already
exists there rather than inventing a new one.

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test uedcli/tests/test_serve_app.py -k "session_path_route" -v`
Expected: FAIL with a 404 on the first test (route doesn't exist).

- [ ] **Step 3: Implement**

Find the existing `StaticFiles` mount in `create_app` (search for `StaticFiles(`). Immediately
before it, gated by the same condition that guards the mount:

```python
    if frontend_dist is not None:
        @app.get("/session/{session_id}")
        def spa_session_route(session_id: str) -> FileResponse:
            # Deliberately no validation of session_id -- serves index.html unconditionally, same
            # as the SPA's own client routing already treats an unknown ?session= id today. A
            # bogus id resolves client-side, once the JS loads and calls GET /api/session/{id}.
            return FileResponse(frontend_dist / "index.html")
```

(`FileResponse` needs importing from `fastapi.responses` if not already imported — check the top of
`app.py` first.) Match the exact variable name/scoping the existing `StaticFiles` mount uses for
`frontend_dist` — do not introduce a second, differently-named binding for the same value.

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test uedcli/tests/test_serve_app.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Add the /session/{id} SPA route for path-based session URLs"
```

---

### Task 5: Backend — WS mid-poll loop splits `closed` vs `superseded`

**Files:**
- Modify: `uedcli/serve/app.py`
- Test: `uedcli/tests/test_serve_app.py` (find the existing WS tests — search for `ws_endpoint`,
  `websocket_connect`, or `4004`/`4003` in this file to locate them and match their exact style)

**Interfaces:**
- Changes: the two `await websocket.send_json({"type": "superseded"})` calls inside
  `ws_endpoint`'s mid-poll timeout branch (one before `code=4004`, one before `code=4003`).

- [ ] **Step 1: Write the failing test**

Locate the existing test(s) exercising the mid-poll 4004/4003 close codes (search
`test_serve_app.py` for `4004` and `4003`) and read them fully to match their exact WS-testing
style (likely `TestClient(app).websocket_connect(...)`, a session created then deleted, then
advancing past `_WS_CLAIM_POLL_INTERVAL_S`). Add two tests alongside them, same style:

```python
def test_ws_mid_poll_deleted_session_sends_closed_not_superseded(...):
    # ... same setup as the existing 4004 test, but additionally:
    msg = ws.receive_json()
    assert msg == {"type": "closed"}


def test_ws_mid_poll_claimed_elsewhere_still_sends_superseded(...):
    # ... same setup as the existing 4003 test, but additionally:
    msg = ws.receive_json()
    assert msg == {"type": "superseded"}
```

Fill in the `...` with the REAL setup the existing 4004/4003 tests already use (session creation,
websocket connect, the other-claim-mint or delete step, the timer advance) — do not guess at it;
read those tests first and copy their exact fixture shape.

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test uedcli/tests/test_serve_app.py -k "ws_mid_poll" -v`
Expected: FAIL — both currently receive `{"type": "superseded"}`.

- [ ] **Step 3: Implement**

In `ws_endpoint`'s mid-poll timeout branch, currently:
```python
                    if sessions.get_session(_sessions_root, session_id) is None:
                        await websocket.send_json({"type": "superseded"})
                        await websocket.close(code=4004, reason="session deleted")
                        return
                    if not _claims.check(session_id, claim_token):
                        await websocket.send_json({"type": "superseded"})
                        await websocket.close(code=4003, reason="session claimed by another connection")
                        return
```
change the FIRST `send_json` call only:
```python
                    if sessions.get_session(_sessions_root, session_id) is None:
                        await websocket.send_json({"type": "closed"})
                        await websocket.close(code=4004, reason="session deleted")
                        return
                    if not _claims.check(session_id, claim_token):
                        await websocket.send_json({"type": "superseded"})
                        await websocket.close(code=4003, reason="session claimed by another connection")
                        return
```

Also update the doc comment immediately above this block (it currently explains why BOTH cases send
the same message — that reasoning is what this task overrides; rewrite it to state the new split
plainly, in this codebase's own terse comment style, rather than leaving the old rationale in place
contradicting the code beneath it).

Do NOT change the pre-accept rejection path (`if not _claims.check(session_id, claim_token):` right
after the initial `sessions.get_session` call, before `websocket.accept()`) — that path always
means "claimed," never "deleted" (existence was just confirmed a few lines above), so it correctly
stays `{"type": "superseded"}`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test uedcli/tests/test_serve_app.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "Send a distinct WS closed message for a deleted session, not superseded"
```

---

### Task 6: Frontend — `api.ts`: `reason`, `isClosedError`, `name` fields, new calls

**Files:**
- Modify: `web/src/api.ts`
- Test: `web/src/api.test.ts`

**Interfaces:**
- Produces: `isClosedError(e: unknown): boolean`; `ClosedMessage` type; `SessionSummary`/
  `SessionDetail` gain `name: string | null`; `renameSession(sessionId: string, name: string):
  Promise<{id, level, created_at, last_active_at, name: string | null}>`; `deleteSession(sessionId:
  string, opts?: {force?: boolean}): Promise<void>`.
- Changes: `request()`'s thrown Error gains `.reason`; `isSupersededError` excludes `reason ===
  'deleted'`; `openChangesAvailableSocket` gains an `onClosed` parameter.

- [ ] **Step 1: Write the failing tests**

Add to `web/src/api.test.ts`, in the same style as the existing `isSupersededError` block:

```typescript
describe('isClosedError', () => {
  it('is true for a 409 whose body says "session deleted"', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: 'session deleted' }), { status: 409 }),
    ) as unknown as typeof fetch

    try {
      await postSave('sess-1')
      expect.unreachable('postSave should have rejected on the 409 response')
    } catch (e) {
      expect(isClosedError(e)).toBe(true)
      expect(isSupersededError(e)).toBe(false)
    }
  })

  it('is true for the mid-solve suffix variant too', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: 'session deleted mid-solve' }), { status: 409 }),
    ) as unknown as typeof fetch

    try {
      await postRebuild('sess-1')
      expect.unreachable('postRebuild should have rejected on the 409 response')
    } catch (e) {
      expect(isClosedError(e)).toBe(true)
    }
  })

  it('is false for "session superseded", and for any other 409/non-409', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: 'session superseded' }), { status: 409 }),
    ) as unknown as typeof fetch

    try {
      await postSave('sess-1')
      expect.unreachable('postSave should have rejected on the 409 response')
    } catch (e) {
      expect(isClosedError(e)).toBe(false)
      expect(isSupersededError(e)).toBe(true)
    }
    expect(isClosedError(null)).toBe(false)
    expect(isClosedError(new Error('plain error'))).toBe(false)
  })
})

describe('fetchSessions/fetchSession carry name', () => {
  it('fetchSessions passes through a session entry\'s name', async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({
      sessions: [{ id: 's1', level: 'L', created_at: 'c', last_active_at: 'a', name: 'My Session' }],
    }), { status: 200 })) as unknown as typeof fetch

    const { sessions } = await fetchSessions()
    expect(sessions[0].name).toBe('My Session')
  })

  it('fetchSession passes through name: null', async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({
      id: 's1', level: 'L', created_at: 'c', last_active_at: 'a', claim_token: 't', name: null,
    }), { status: 200 })) as unknown as typeof fetch

    const rec = await fetchSession('s1')
    expect(rec.name).toBeNull()
  })
})

describe('renameSession', () => {
  it('POSTs {name} to the rename route with the claim-token header and returns the result', async () => {
    setClaimToken('tok-1')
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      id: 's1', level: 'L', created_at: 'c', last_active_at: 'a', name: 'New Name',
    }), { status: 200 }))
    globalThis.fetch = fetchMock as unknown as typeof fetch

    const result = await renameSession('s1', 'New Name')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/session/s1/rename',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'X-Claim-Token': 'tok-1' }),
        body: JSON.stringify({ name: 'New Name' }),
      }),
    )
    expect(result.name).toBe('New Name')
    setClaimToken(null)
  })
})

describe('deleteSession', () => {
  it('DELETEs the session with the claim-token header, no ?force by default', async () => {
    setClaimToken('tok-1')
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }))
    globalThis.fetch = fetchMock as unknown as typeof fetch

    await deleteSession('s1')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/session/s1',
      expect.objectContaining({ method: 'DELETE', headers: expect.objectContaining({ 'X-Claim-Token': 'tok-1' }) }),
    )
    setClaimToken(null)
  })

  it('appends ?force=true when opts.force is true', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }))
    globalThis.fetch = fetchMock as unknown as typeof fetch

    await deleteSession('s1', { force: true })

    expect(fetchMock).toHaveBeenCalledWith('/api/session/s1?force=true', expect.anything())
  })
})
```

Add `renameSession`, `deleteSession`, `isClosedError` to the top-of-file import list in this test
file (find the existing `import { ... } from './api'` line and extend it).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/api.test.ts`
Expected: FAIL — `renameSession`/`deleteSession`/`isClosedError` don't exist yet.

- [ ] **Step 3: Implement**

In `web/src/api.ts`:

Edit `request()` — currently:
```typescript
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await (init ? fetch(url, init) : fetch(url))
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = (await res.json()) as ErrorBody
      if (body.error) message = body.error
    } catch {
      // The error body wasn't JSON -- fall back to the HTTP status text.
    }
    const err = new Error(`${url}: ${message}`) as Error & { status: number }
    err.status = res.status
    throw err
  }
  return (await res.json()) as T
}
```
becomes:
```typescript
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await (init ? fetch(url, init) : fetch(url))
  if (!res.ok) {
    let message = res.statusText
    // Derived from `body.error` directly, BEFORE it's folded into `message`/the Error -- deriving
    // this from the thrown Error's own `.message` would never match, since that has the url
    // prefixed onto it (`${url}: ${message}` below).
    let reason: 'deleted' | 'superseded' | undefined
    try {
      const body = (await res.json()) as ErrorBody
      if (body.error) {
        message = body.error
        if (body.error.startsWith('session deleted')) reason = 'deleted'
        else if (body.error.startsWith('session superseded')) reason = 'superseded'
      }
    } catch {
      // The error body wasn't JSON -- fall back to the HTTP status text.
    }
    const err = new Error(`${url}: ${message}`) as Error & { status: number; reason?: 'deleted' | 'superseded' }
    err.status = res.status
    err.reason = reason
    throw err
  }
  return (await res.json()) as T
}
```

Edit `isSupersededError` and add `isClosedError` right after it:
```typescript
export function isSupersededError(e: unknown): boolean {
  return typeof e === 'object' && e !== null && (e as { status?: number }).status === 409
    && (e as { reason?: string }).reason !== 'deleted'
}

/** True for a mutating call's 409 whose body says the session was actually deleted (Task 6), not
 * merely claimed elsewhere -- the distinction `isSupersededError` alone can't make. */
export function isClosedError(e: unknown): boolean {
  return typeof e === 'object' && e !== null && (e as { status?: number }).status === 409
    && (e as { reason?: string }).reason === 'deleted'
}
```

Add `name: string | null` to `SessionSummary` and `SessionDetail` (NOT `SessionRecord`, which
`createSession`'s response never carries it on):
```typescript
export interface SessionSummary {
  id: string
  level: string
  created_at: string
  last_active_at: string
  name: string | null
}
```
```typescript
export interface SessionDetail {
  id: string
  level: string
  created_at: string
  last_active_at: string
  claim_token: string
  name: string | null
}
```

Add `ClosedMessage` right after `SupersededMessage`:
```typescript
/** The session was actually deleted (Task 6) -- distinct from `SupersededMessage`, which means it
 * still exists but another connection now holds its claim. */
export interface ClosedMessage {
  type: 'closed'
}
```

Edit `openChangesAvailableSocket` to add the new callback and dispatch on it:
```typescript
export function openChangesAvailableSocket(
  sessionId: string,
  claimToken: string,
  onChanged: (msg: ChangesAvailableMessage) => void,
  onSuperseded: () => void,
  onClosed: () => void,
): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/ws?session=${encodeURIComponent(sessionId)}&claim=${encodeURIComponent(claimToken)}`
  const ws = new WebSocket(url)
  ws.addEventListener('message', (event: MessageEvent<string>) => {
    const msg = JSON.parse(event.data) as ChangesAvailableMessage | SupersededMessage | ClosedMessage
    if (msg.type === 'changes_available') onChanged(msg)
    else if (msg.type === 'superseded') onSuperseded()
    else if (msg.type === 'closed') onClosed()
  })
  return ws
}
```

Add a new response interface and `renameSession`/`deleteSession` near the other session-scoped
calls (after `fetchSession`):
```typescript
export interface SessionRenameResult {
  id: string
  level: string
  created_at: string
  last_active_at: string
  name: string | null
}

export function renameSession(sessionId: string, name: string): Promise<SessionRenameResult> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/rename`, withClaimToken({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  }))
}

export function deleteSession(sessionId: string, opts: { force?: boolean } = {}): Promise<void> {
  const qs = opts.force ? '?force=true' : ''
  return request(`/api/session/${encodeURIComponent(sessionId)}${qs}`, withClaimToken({ method: 'DELETE' }))
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/api.test.ts && npx tsc -b`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/api.ts web/src/api.test.ts
git commit -m "api.ts: distinguish deleted from superseded, add rename/delete calls"
```

---

### Task 7: Frontend — `reload.ts`: thread `onClosed` through

**Files:**
- Modify: `web/src/reload.ts`
- Test: `web/src/reload.test.ts`

**Interfaces:**
- Consumes: `openChangesAvailableSocket`'s new `onClosed` param (Task 6).
- Changes: `subscribeChangesAvailable` gains a 5th parameter, `onClosed: () => void`.

- [ ] **Step 1: Write the failing tests**

Update the mock at the top of `reload.test.ts` — the `openChangesAvailableSocketMock`'s
implementation currently destructures 4 args; add the 5th and capture it in `Call`:
```typescript
type Call = {
  sessionId: string
  claimToken: string
  onChanged: () => void
  onSuperseded: () => void
  onClosed: () => void
  socket: ReturnType<typeof makeFakeSocket>
}
let calls: Call[]

beforeEach(() => {
  vi.useFakeTimers()
  calls = []
  openChangesAvailableSocketMock.mockReset()
  openChangesAvailableSocketMock.mockImplementation(
    (sessionId: string, claimToken: string, onChanged: () => void, onSuperseded: () => void, onClosed: () => void) => {
      const socket = makeFakeSocket()
      calls.push({ sessionId, claimToken, onChanged, onSuperseded, onClosed, socket })
      return socket
    },
  )
})
```

Add a new test alongside the existing `'an explicit "superseded" push calls onSuperseded...'` one:
```typescript
  it('an explicit "closed" push calls onClosed and does not reconnect', () => {
    const onClosed = vi.fn()
    subscribeChangesAvailable('sess-1', 'tok-1', vi.fn(), vi.fn(), onClosed)

    calls[0].onClosed()
    expect(onClosed).toHaveBeenCalledTimes(1)

    calls[0].socket.fireClose()
    vi.advanceTimersByTime(10_000)
    expect(openChangesAvailableSocketMock).toHaveBeenCalledTimes(1)
  })
```

Update every OTHER existing `subscribeChangesAvailable(...)` call in this test file to pass a 5th
argument (`vi.fn()` where the test doesn't care about it) — this is a required signature change,
not optional; every existing call site in this file needs it or `subscribeChangesAvailable`'s real
new signature won't compile against the mock.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/reload.test.ts`
Expected: FAIL — the new test's `onClosed` never gets wired, and/or a TS arity mismatch once Step 3
below changes the real signature.

- [ ] **Step 3: Implement**

In `web/src/reload.ts`, edit `subscribeChangesAvailable`'s signature and `connect()`:

```typescript
export function subscribeChangesAvailable(
  sessionId: string,
  claimToken: string,
  onChangesAvailable: () => void,
  onSuperseded: () => void,
  onClosed: () => void,
): ReloadSubscription {
  let stopped = false
  let ws: WebSocket
  let pendingReconnect: ReturnType<typeof setTimeout> | undefined

  function connect(): void {
    ws = openChangesAvailableSocket(
      sessionId,
      claimToken,
      onChangesAvailable,
      () => {
        stopped = true
        onSuperseded()
      },
      () => {
        stopped = true
        onClosed()
      },
    )
    ws.addEventListener('close', (event: CloseEvent) => {
      if (stopped) return
      if (event.code === 4001) {
        stopped = true
        return
      }
      pendingReconnect = setTimeout(() => {
        if (!stopped) connect()
      }, RECONNECT_DELAY_MS)
    })
  }
  connect()

  return {
    unsubscribe: () => {
      stopped = true
      clearTimeout(pendingReconnect)
      ws.close()
    },
  }
}
```

(Only the two new lines — the `onClosed` parameter and its wrapper closure — actually change; the
`close`-event listener body itself is untouched, unchanged from today.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/reload.test.ts && npx tsc -b`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/reload.ts web/src/reload.test.ts
git commit -m "reload.ts: thread the WS closed signal through, alongside superseded"
```

---

### Task 8: Frontend — `route.ts` (new module)

**Files:**
- Create: `web/src/session/route.ts`
- Test: `web/src/session/route.test.ts`

**Interfaces:**
- Produces: `parseRoute(pathname: string): Route` (`Route = { screen: 'picker' } | { screen:
  'session', id: string }`); `navigate(path: string): void`; `useRoute(): Route`.

- [ ] **Step 1: Write the failing tests**

```typescript
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { navigate, parseRoute, useRoute } from './route'

beforeEach(() => {
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  window.history.replaceState(null, '', '/')
})

describe('parseRoute', () => {
  it('a bare "/" is the picker screen', () => {
    expect(parseRoute('/')).toEqual({ screen: 'picker' })
  })

  it('/session/<id> is the session screen', () => {
    expect(parseRoute('/session/abc-123')).toEqual({ screen: 'session', id: 'abc-123' })
  })

  it('/session/<id>/ (trailing slash) is the same session screen', () => {
    expect(parseRoute('/session/abc-123/')).toEqual({ screen: 'session', id: 'abc-123' })
  })

  it('anything else falls back to the picker screen', () => {
    expect(parseRoute('/unknown/path')).toEqual({ screen: 'picker' })
  })
})

describe('useRoute', () => {
  it('reflects the initial pathname on mount', () => {
    window.history.replaceState(null, '', '/session/abc-123/')
    const { result } = renderHook(() => useRoute())
    expect(result.current).toEqual({ screen: 'session', id: 'abc-123' })
  })

  it('navigate() updates the route synchronously for every mounted subscriber', () => {
    const { result } = renderHook(() => useRoute())
    expect(result.current).toEqual({ screen: 'picker' })

    act(() => navigate('/session/new-id/'))

    expect(result.current).toEqual({ screen: 'session', id: 'new-id' })
    expect(window.location.pathname).toBe('/session/new-id/')
  })

  it('a real popstate (browser back/forward) also updates the route', () => {
    window.history.replaceState(null, '', '/session/first/')
    const { result } = renderHook(() => useRoute())
    window.history.pushState(null, '', '/session/second/')

    act(() => window.dispatchEvent(new PopStateEvent('popstate')))

    expect(result.current).toEqual({ screen: 'session', id: 'second' })
  })

  it('unmounting stops updating on navigate()', () => {
    const { result, unmount } = renderHook(() => useRoute())
    unmount()
    act(() => navigate('/session/late/'))
    // No assertion on `result.current` after unmount (React forbids reading it) -- this test's
    // only job is proving `navigate()` doesn't throw once every subscriber has unsubscribed.
    expect(window.location.pathname).toBe('/session/late/')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/session/route.test.ts`
Expected: FAIL — the module doesn't exist yet.

- [ ] **Step 3: Implement**

```typescript
// Dependency-free routing (spec decision 2): two screens don't justify a router library. `navigate`
// uses `pushState` (not `replaceState` -- the picker and the editor are genuinely different
// screens; back/forward should move between them) and notifies every mounted `useRoute` subscriber
// synchronously, since `pushState` itself fires no browser event. `popstate` (real back/forward)
// is handled the ordinary way, through the same listener set.
import { useEffect, useState } from 'react'

export type Route = { screen: 'picker' } | { screen: 'session'; id: string }

const SESSION_PATH = /^\/session\/([^/]+)\/?$/

export function parseRoute(pathname: string): Route {
  const match = SESSION_PATH.exec(pathname)
  if (match) return { screen: 'session', id: decodeURIComponent(match[1]) }
  return { screen: 'picker' }
}

type Listener = () => void
const listeners = new Set<Listener>()

/** Pushes a new path and notifies every mounted `useRoute` immediately -- `pushState` alone fires
 * no event, so without this, navigating would only ever be visible after the NEXT unrelated
 * re-render. */
export function navigate(path: string): void {
  window.history.pushState(null, '', path)
  listeners.forEach((listener) => listener())
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.pathname))

  useEffect(() => {
    const listener = () => setRoute(parseRoute(window.location.pathname))
    listeners.add(listener)
    window.addEventListener('popstate', listener)
    return () => {
      listeners.delete(listener)
      window.removeEventListener('popstate', listener)
    }
  }, [])

  return route
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/session/route.test.ts && npx tsc -b`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/session/route.ts web/src/session/route.test.ts
git commit -m "Add route.ts: dependency-free pathname parsing and navigation"
```

---

### Task 9: Frontend — `SessionContext.tsx` redesign

**Files:**
- Modify: `web/src/session/SessionContext.tsx`
- Test: `web/src/session/SessionContext.test.tsx` (this task REPLACES the existing test file's
  contents wholesale — the current tests exercise the auto-create-on-bare-URL flow, which no
  longer exists after this task)

**Interfaces:**
- Changes: `useSession(sessionId: string): UseSessionResult` — was `useSession(): UseSessionResult`.
  `UseSessionResult` DROPS `createSession`. Gains `markClosed: () => void`.
- Consumes: `fetchSession` (unchanged signature).

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `web/src/session/SessionContext.test.tsx` with:

```typescript
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useSession } from './SessionContext'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

function mockFetch(extra: (url: string, init?: RequestInit) => Response | undefined) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const overridden = extra(url)
    if (overridden) return overridden
    throw new Error(`unexpected fetch: ${url}`)
  }) as unknown as typeof fetch
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useSession(sessionId)', () => {
  it('resolves the given id on mount and reaches view "editing"', async () => {
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) {
        return jsonResponse({ id: 'sess-1', level: 'Beta', created_at: 'c', last_active_at: 'a', claim_token: 'tok-1', name: null })
      }
      return undefined
    })

    const { result } = renderHook(() => useSession('sess-1'))

    await waitFor(() => expect(result.current.view).toBe('editing'))
    expect(result.current.sessionId).toBe('sess-1')
    expect(result.current.level).toBe('Beta')
    expect(result.current.claimToken).toBe('tok-1')
  })

  it('a session id the server has never seen resolves to "notfound"', async () => {
    mockFetch((url) => {
      if (url.endsWith('/api/session/bad-id')) return jsonResponse({ error: 'session not found' }, 404)
      return undefined
    })

    const { result } = renderHook(() => useSession('bad-id'))

    await waitFor(() => expect(result.current.view).toBe('notfound'))
  })

  it('re-resolving an id this hook already knew was good, and now 404s, is "closed" not "notfound"', async () => {
    let shouldFail = false
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) {
        return shouldFail
          ? jsonResponse({ error: 'gone' }, 404)
          : jsonResponse({ id: 'sess-1', level: 'Beta', created_at: 'c', last_active_at: 'a', claim_token: 'tok-1', name: null })
      }
      return undefined
    })

    const { result } = renderHook(() => useSession('sess-1'))
    await waitFor(() => expect(result.current.view).toBe('editing'))

    shouldFail = true
    act(() => result.current.reload())

    await waitFor(() => expect(result.current.view).toBe('closed'))
  })

  it('re-resolves automatically when the sessionId argument itself changes', async () => {
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) return jsonResponse({ id: 'sess-1', level: 'A', created_at: 'c', last_active_at: 'a', claim_token: 't1', name: null })
      if (url.endsWith('/api/session/sess-2')) return jsonResponse({ id: 'sess-2', level: 'B', created_at: 'c', last_active_at: 'a', claim_token: 't2', name: null })
      return undefined
    })

    const { result, rerender } = renderHook(({ id }) => useSession(id), { initialProps: { id: 'sess-1' } })
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    rerender({ id: 'sess-2' })

    await waitFor(() => expect(result.current.sessionId).toBe('sess-2'))
    expect(result.current.level).toBe('B')
  })

  it('markSuperseded flips view to "superseded" without touching sessionId/level/claimToken', async () => {
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) return jsonResponse({ id: 'sess-1', level: 'Beta', created_at: 'c', last_active_at: 'a', claim_token: 'tok-1', name: null })
      return undefined
    })
    const { result } = renderHook(() => useSession('sess-1'))
    await waitFor(() => expect(result.current.view).toBe('editing'))

    act(() => result.current.markSuperseded())

    expect(result.current.view).toBe('superseded')
    expect(result.current.sessionId).toBe('sess-1')
  })

  it('markClosed flips view to "closed"', async () => {
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) return jsonResponse({ id: 'sess-1', level: 'Beta', created_at: 'c', last_active_at: 'a', claim_token: 'tok-1', name: null })
      return undefined
    })
    const { result } = renderHook(() => useSession('sess-1'))
    await waitFor(() => expect(result.current.view).toBe('editing'))

    act(() => result.current.markClosed())

    expect(result.current.view).toBe('closed')
  })

  it('does not write anything into the URL -- that is route.ts/App.tsx\'s job now', async () => {
    window.history.replaceState(null, '', '/session/sess-1/')
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) return jsonResponse({ id: 'sess-1', level: 'Beta', created_at: 'c', last_active_at: 'a', claim_token: 'tok-1', name: null })
      return undefined
    })

    renderHook(() => useSession('sess-1'))
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())

    expect(window.location.pathname).toBe('/session/sess-1/')
    window.history.replaceState(null, '', '/')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/session/SessionContext.test.tsx`
Expected: FAIL — `useSession()` still takes no argument and still auto-creates.

- [ ] **Step 3: Implement**

Replace `web/src/session/SessionContext.tsx` in full:

```typescript
// Session identity (persistent-GUI-editing-sessions plan, Task 16; redesigned for path-based
// routing, session-management-UI spec). Follows this codebase's existing plain-hook convention
// (theme/useTheme.ts, layout/useSidebar.ts) rather than React's Context API -- App.tsx mounts
// `useSession(sessionId)` once per mounted `SessionEditor` and threads the result down as props.
//
// The session id is now an ARGUMENT, not something this hook reads from the URL itself: `App.tsx`
// already parses the route (`route.ts`) to decide whether to render the picker or the editor, so it
// already has the id in hand by the time it mounts a `SessionEditor`. This hook owns none of the
// URL -- creating a session (the picker) and switching between them (the dropdown) both navigate
// via `route.ts`'s own `navigate()`, never through here.
import { useCallback, useEffect, useRef, useState } from 'react'

import type { SessionDetail } from '../api'
import { fetchSession } from '../api'

export type SessionView = 'editing' | 'notfound' | 'closed' | 'superseded'

export interface SessionState {
  sessionId: string | null
  level: string | null
  view: SessionView
  claimToken: string | null
}

export interface UseSessionResult extends SessionState {
  // Re-resolves the CURRENT sessionId argument: mints a FRESH claim token, re-claiming the session
  // for THIS window (superseding whichever window is holding it now), and flips `view` back to
  // 'editing' on success. Fires on mount, whenever `sessionId` itself changes, and from the
  // superseded-takeover banner's own Reload button.
  reload: () => void
  // Flips `view` to 'superseded' -- fired by the `/ws` "superseded" push (reload.ts) or a mutating
  // call's 409 (`isSupersededError`). Leaves `sessionId`/`level`/`claimToken` untouched: nothing is
  // wrong with them, the session just isn't this window's to edit until `reload()` reclaims it.
  markSuperseded: () => void
  // Flips `view` to 'closed' -- fired by the `/ws` "closed" push or a mutating call's 409
  // (`isClosedError`). The session is genuinely gone; there is nothing to reclaim.
  markClosed: () => void
}

const INITIAL_STATE: SessionState = { sessionId: null, level: null, view: 'editing', claimToken: null }

/** `resolvedIdsRef` tells apart a `sessionId` that has NEVER resolved (a bad/garbage id -- `view:
 * 'notfound'`) from one that resolved fine before and has now started failing (this tab's own
 * session was closed elsewhere -- `view: 'closed'`, reached by `reload()` re-resolving an id this
 * hook already knew was good and finding it 404 now). */
export function useSession(sessionId: string): UseSessionResult {
  const [state, setState] = useState<SessionState>(INITIAL_STATE)
  const resolvedIdsRef = useRef<Set<string>>(new Set())
  // Per-call sequence guard: `reload()` is a fire-and-forget promise chain with no cancellation --
  // calling it twice in quick succession (a rapid `sessionId` change, or a slow response arriving
  // after a newer one already landed) could otherwise let the SLOWER response commit AFTER the
  // faster one and overwrite fresher state with stale data.
  const seqRef = useRef(0)

  const activate = useCallback((rec: SessionDetail) => {
    resolvedIdsRef.current.add(rec.id)
    setState({ sessionId: rec.id, level: rec.level, claimToken: rec.claim_token, view: 'editing' })
  }, [])

  const reload = useCallback(() => {
    const mySeq = ++seqRef.current
    fetchSession(sessionId)
      .then((rec) => {
        if (seqRef.current !== mySeq) return
        activate(rec)
      })
      .catch(() => {
        if (seqRef.current !== mySeq) return
        setState({
          sessionId,
          level: null,
          claimToken: null,
          view: resolvedIdsRef.current.has(sessionId) ? 'closed' : 'notfound',
        })
      })
  }, [sessionId, activate])

  // Re-fires on mount AND whenever the `sessionId` argument itself changes (e.g. a session switch
  // via the dropdown, which navigates and re-renders this hook's caller with a new id) -- no
  // separate "switch" method is needed on top of this.
  useEffect(() => {
    reload()
  }, [reload])

  const markSuperseded = useCallback(() => {
    setState((s) => ({ ...s, view: 'superseded' }))
  }, [])

  const markClosed = useCallback(() => {
    setState((s) => ({ ...s, view: 'closed' }))
  }, [])

  return { ...state, reload, markSuperseded, markClosed }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/session/SessionContext.test.tsx && npx tsc -b`
Expected: FAIL on `tsc -b` at this point — `App.tsx` still calls `useSession()` with no argument and
still reads `createSession` off the result; that's expected and fixed in Task 15. Confirm the
vitest run itself passes; `tsc -b`'s new errors are all in `App.tsx`, not this file.

- [ ] **Step 5: Commit**

```bash
git add web/src/session/SessionContext.tsx web/src/session/SessionContext.test.tsx
git commit -m "Redesign useSession to take sessionId as an argument, drop auto-create"
```

---

### Task 10: Frontend — `InlineRename.tsx` (new shared component)

**Files:**
- Create: `web/src/session/InlineRename.tsx`
- Test: `web/src/session/InlineRename.test.tsx`

**Interfaces:**
- Produces: `InlineRename({ value, placeholder, onRename }: InlineRenameProps)`.

- [ ] **Step 1: Write the failing tests**

```typescript
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { InlineRename } from './InlineRename'

afterEach(cleanup)

describe('InlineRename', () => {
  it('shows the current value as plain text, with an edit trigger', () => {
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={vi.fn()} />)
    expect(screen.getByText('My Session')).toBeTruthy()
  })

  it('falls back to the placeholder when value is null', () => {
    render(<InlineRename value={null} placeholder="TestLevel" onRename={vi.fn()} />)
    expect(screen.getByText('TestLevel')).toBeTruthy()
  })

  it('clicking the display text enters edit mode with the current value pre-filled', () => {
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={vi.fn()} />)
    fireEvent.click(screen.getByText('My Session'))
    expect(screen.getByRole('textbox')).toHaveValue('My Session')
  })

  it('confirming (the tick button) calls onRename with the edited value and exits edit mode', () => {
    const onRename = vi.fn()
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={onRename} />)
    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'New Name' } })
    fireEvent.click(screen.getByRole('button', { name: /confirm|✓/i }))
    expect(onRename).toHaveBeenCalledWith('New Name')
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('confirming via Enter has the same effect as clicking the tick button', () => {
    const onRename = vi.fn()
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={onRename} />)
    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'New Name' } })
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' })
    expect(onRename).toHaveBeenCalledWith('New Name')
  })

  it('canceling (the X button) discards the edit and calls onRename never', () => {
    const onRename = vi.fn()
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={onRename} />)
    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Discarded' } })
    fireEvent.click(screen.getByRole('button', { name: /cancel|✗/i }))
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.getByText('My Session')).toBeTruthy()
  })

  it('canceling via Escape has the same effect as clicking the X button', () => {
    const onRename = vi.fn()
    render(<InlineRename value="My Session" placeholder="TestLevel" onRename={onRename} />)
    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Discarded' } })
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' })
    expect(onRename).not.toHaveBeenCalled()
    expect(screen.getByText('My Session')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/session/InlineRename.test.tsx`
Expected: FAIL — the module doesn't exist yet.

- [ ] **Step 3: Implement**

```typescript
// Shared click-to-edit-in-place control (session-management-UI spec, decision 4): a ✓/✗ button
// pair plus Enter/Esc confirms or cancels. Used by both SessionPicker's rows and SessionLabel.
import { useState } from 'react'
import type { KeyboardEvent } from 'react'

export interface InlineRenameProps {
  // The current name, or null when unnamed -- `placeholder` is shown instead in that case.
  value: string | null
  placeholder: string
  onRename: (name: string) => void
}

export function InlineRename({ value, placeholder, onRename }: InlineRenameProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  const startEditing = () => {
    setDraft(value ?? '')
    setEditing(true)
  }

  const confirm = () => {
    onRename(draft)
    setEditing(false)
  }

  const cancel = () => {
    setEditing(false)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') confirm()
    else if (e.key === 'Escape') cancel()
  }

  if (!editing) {
    return (
      <span className="inline-rename-display" onClick={startEditing}>
        {value ?? placeholder}
      </span>
    )
  }

  return (
    <span className="inline-rename-editing">
      <input
        type="text"
        value={draft}
        autoFocus
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button type="button" aria-label="confirm rename" onClick={confirm}>
        ✓
      </button>
      <button type="button" aria-label="cancel rename" onClick={cancel}>
        ✗
      </button>
    </span>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/session/InlineRename.test.tsx && npx tsc -b`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/session/InlineRename.tsx web/src/session/InlineRename.test.tsx
git commit -m "Add InlineRename: shared click-to-edit-in-place control"
```

---

### Task 11: Frontend — `SessionDropdown.tsx`: name-or-level + id on hover

**Files:**
- Modify: `web/src/session/SessionDropdown.tsx`
- Test: `web/src/session/SessionDropdown.test.tsx`

- [ ] **Step 1: Write the failing test**

Read the existing `SessionDropdown.test.tsx` in full first (it already exercises `fetchSessions`
mocking and grouping). Add:

```typescript
  it('shows name-or-level as the option text, with the raw id as a title/hover attribute', async () => {
    mockFetchSessions({
      sessions: [
        { id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', name: 'My Session' },
        { id: 's2', level: 'Alpha', created_at: 'c', last_active_at: 'a', name: null },
      ],
    })
    render(<SessionDropdown currentSessionId="s1" onSwitchSession={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    const named = screen.getByText('My Session') as HTMLOptionElement
    expect(named.title).toBe('s1')
    const unnamed = screen.getByText('Alpha') as HTMLOptionElement
    expect(unnamed.title).toBe('s2')
  })
```

Match whatever mocking helper (`mockFetchSessions` or similar) the existing test file already
defines — read it first and reuse it rather than inventing a second one; adjust the call above to
whatever that helper's real name/shape is.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/session/SessionDropdown.test.tsx`
Expected: FAIL — option text is currently the raw id, with no `title`.

- [ ] **Step 3: Implement**

In `web/src/session/SessionDropdown.tsx`, change the option-rendering line:
```tsx
              <option key={s.id} value={s.id}>
                {s.id}
              </option>
```
to:
```tsx
              <option key={s.id} value={s.id} title={s.id}>
                {s.name ?? s.level}
              </option>
```

Leave the pre-load fallback option (`{currentSessionId && !knownCurrent && <option
value={currentSessionId}>{currentSessionId}</option>}`) untouched — there's no `name` available for
it before the list has fetched (spec, "Routing" section).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/session/SessionDropdown.test.tsx && npx tsc -b`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/session/SessionDropdown.tsx web/src/session/SessionDropdown.test.tsx
git commit -m "SessionDropdown: show name-or-level, raw id on hover"
```

---

### Task 12: Frontend — `SessionLabel.tsx` (new toolbar component)

**Files:**
- Create: `web/src/session/SessionLabel.tsx`
- Test: `web/src/session/SessionLabel.test.tsx`

**Interfaces:**
- Produces: `SessionLabel({ sessionId, level, name, onRenamed }: SessionLabelProps)`.
- Consumes: `renameSession` (Task 6), `InlineRename` (Task 10), `navigate` (Task 8).

- [ ] **Step 1: Write the failing tests**

```typescript
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SessionLabel } from './SessionLabel'

const renameSession = vi.fn()
const navigate = vi.fn()

vi.mock('../api', () => ({ renameSession: (...args: unknown[]) => renameSession(...args) }))
vi.mock('./route', () => ({ navigate: (...args: unknown[]) => navigate(...args) }))

afterEach(() => {
  cleanup()
  renameSession.mockReset()
  navigate.mockReset()
})

describe('SessionLabel', () => {
  it('shows name-or-level with the raw id on hover', () => {
    render(<SessionLabel sessionId="s1" level="TestLevel" name="My Session" onRenamed={vi.fn()} />)
    const label = screen.getByText('My Session')
    expect(label.title).toBe('s1')
  })

  it('falls back to the level when unnamed', () => {
    render(<SessionLabel sessionId="s1" level="TestLevel" name={null} onRenamed={vi.fn()} />)
    expect(screen.getByText('TestLevel')).toBeTruthy()
  })

  it('clicking the label, editing, and confirming calls renameSession(sessionId, newName) and onRenamed', async () => {
    renameSession.mockResolvedValue({ id: 's1', level: 'TestLevel', created_at: 'c', last_active_at: 'a', name: 'New Name' })
    const onRenamed = vi.fn()
    render(<SessionLabel sessionId="s1" level="TestLevel" name="My Session" onRenamed={onRenamed} />)

    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'New Name' } })
    fireEvent.click(screen.getByRole('button', { name: /confirm|✓/i }))

    await waitFor(() => expect(renameSession).toHaveBeenCalledWith('s1', 'New Name'))
    await waitFor(() => expect(onRenamed).toHaveBeenCalledWith('New Name'))
  })

  it('the back-to-picker link navigates to "/" with no confirmation', () => {
    render(<SessionLabel sessionId="s1" level="TestLevel" name={null} onRenamed={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /sessions|picker|back/i }))
    expect(navigate).toHaveBeenCalledWith('/')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/session/SessionLabel.test.tsx`
Expected: FAIL — the module doesn't exist yet.

- [ ] **Step 3: Implement**

```typescript
// The toolbar's persistent session identity label (session-management-UI spec, decisions 4/5/6):
// always shows the current session's name-or-level, is itself the rename trigger, and carries a
// back-to-picker link. Renaming here uses the session's OWN already-held claim token (via
// renameSession -> api.ts's withClaimToken -> the module-level token App.tsx already pushed in) --
// never a fresh acquire-then-mutate GET, which SessionPicker's rows need instead (they hold no
// token at all for a session this tab never opened) but this component must not, or it would
// supersede its own window's claim.
import { renameSession } from '../api'
import { InlineRename } from './InlineRename'
import { navigate } from './route'

export interface SessionLabelProps {
  sessionId: string
  level: string
  name: string | null
  onRenamed: (name: string | null) => void
}

export function SessionLabel({ sessionId, level, name, onRenamed }: SessionLabelProps) {
  const handleRename = (draft: string) => {
    renameSession(sessionId, draft)
      .then((result) => onRenamed(result.name))
      .catch((e: unknown) => console.error('rename failed', e))
  }

  return (
    <div className="session-label">
      <span title={sessionId}>
        <InlineRename value={name} placeholder={level} onRename={handleRename} />
      </span>
      <button type="button" aria-label="back to sessions" onClick={() => navigate('/')}>
        ⌂ Sessions
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/session/SessionLabel.test.tsx && npx tsc -b`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/session/SessionLabel.tsx web/src/session/SessionLabel.test.tsx
git commit -m "Add SessionLabel: persistent toolbar identity + rename + back-to-picker"
```

---

### Task 13: Frontend — `SessionPicker.tsx` (new landing screen)

**Files:**
- Create: `web/src/session/SessionPicker.tsx`
- Test: `web/src/session/SessionPicker.test.tsx`

**Interfaces:**
- Produces: `SessionPicker()`.
- Consumes: `fetchLevels`, `createSession`, `fetchSessions`, `fetchSession`, `renameSession`,
  `deleteSession` (all `api.ts`), `InlineRename` (Task 10), `navigate` (Task 8).

- [ ] **Step 1: Write the failing tests**

```typescript
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SessionPicker } from './SessionPicker'

const navigate = vi.fn()
vi.mock('./route', () => ({ navigate: (...args: unknown[]) => navigate(...args) }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

afterEach(() => {
  cleanup()
  navigate.mockReset()
})

const LEVELS = { levels: [{ name: 'Alpha', active: true }, { name: 'Beta', active: false }], current: 'Alpha' }
const SESSIONS = {
  sessions: [
    { id: 's1', level: 'Alpha', created_at: 'c1', last_active_at: '2026-09-23T00:02:00Z', name: 'My Session' },
    { id: 's2', level: 'Alpha', created_at: 'c2', last_active_at: '2026-09-23T00:01:00Z', name: null },
  ],
}

function mockFetch(extra?: (url: string, init?: RequestInit) => Response | Promise<Response> | undefined) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const overridden = await extra?.(url, init)
    if (overridden) return overridden
    if (url.endsWith('/api/levels')) return jsonResponse(LEVELS)
    if (url.endsWith('/api/sessions')) return jsonResponse(SESSIONS)
    throw new Error(`unexpected fetch: ${url}`)
  }) as unknown as typeof fetch
}

describe('SessionPicker', () => {
  it('lists sessions sorted by last_active_at descending, name-or-level as the primary label', async () => {
    mockFetch()
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    const rows = screen.getAllByTestId('session-picker-row')
    expect(rows[0]).toHaveTextContent('My Session')
    expect(rows[1]).toHaveTextContent('Alpha')  // s2, unnamed, falls back to level
  })

  it('clicking a row (not the name or delete button) navigates to /session/<id>/', async () => {
    mockFetch()
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getAllByTestId('session-picker-row')[0])

    expect(navigate).toHaveBeenCalledWith('/session/s1/')
  })

  it('creating a session: pick a level, click Create, navigate to the new session', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/api/level/Beta/sessions') && init?.method === 'POST') {
        return jsonResponse({ id: 'new-id', level: 'Beta', created_at: 'c', claim_token: 't' }, 201)
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Beta' } })
    fireEvent.click(screen.getByRole('button', { name: /create session/i }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/session/new-id/'))
  })

  it('delete on a session with no unsaved edits shows the plain confirm copy', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mockFetch((url) => {
      if (url.endsWith('/api/session/s1/staged')) return jsonResponse({})
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0])

    await waitFor(() => expect(confirmSpy).toHaveBeenCalledWith('Delete this session?'))
    expect(navigate).not.toHaveBeenCalled()
  })

  it('delete on a session WITH unsaved edits shows the different confirm copy', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mockFetch((url) => {
      if (url.endsWith('/api/session/s1/staged')) {
        return jsonResponse({ Light0: { staged_location: [0, 0, 0], baseline_location: [0, 0, 0] } })
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0])

    await waitFor(() => expect(confirmSpy).toHaveBeenCalledWith('This session has unsaved edits. Delete anyway?'))
  })

  it('confirming delete acquires a fresh claim then DELETEs, and removes the row without a re-fetch', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    let deleteCalled = false
    mockFetch((url, init) => {
      if (url.endsWith('/api/session/s1/staged')) return jsonResponse({})
      if (url.endsWith('/api/session/s1') && (!init || init.method === undefined)) {
        return jsonResponse({ id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', claim_token: 'fresh-tok', name: 'My Session' })
      }
      if (url.endsWith('/api/session/s1') && init?.method === 'DELETE') {
        deleteCalled = true
        return new Response(null, { status: 204 })
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0])

    await waitFor(() => expect(deleteCalled).toBe(true))
    await waitFor(() => expect(screen.queryByText('My Session')).toBeNull())
  })

  it('inline-renaming a row calls renameSession via an acquired claim, and updates that row', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/api/session/s1') && (!init || init.method === undefined)) {
        return jsonResponse({ id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', claim_token: 'fresh-tok', name: 'My Session' })
      }
      if (url.endsWith('/api/session/s1/rename') && init?.method === 'POST') {
        return jsonResponse({ id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', name: 'Renamed' })
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Renamed' } })
    fireEvent.click(screen.getByRole('button', { name: /confirm|✓/i }))

    await waitFor(() => expect(screen.getByText('Renamed')).toBeTruthy())
    expect(navigate).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/session/SessionPicker.test.tsx`
Expected: FAIL — the module doesn't exist yet.

- [ ] **Step 3: Implement**

```typescript
// The landing screen (session-management-UI spec, decision 1): replaces auto-create-on-bare-URL
// entirely -- a bare "/" always shows this, and nothing is created without an explicit click here.
import { useEffect, useState } from 'react'

import type { SessionSummary } from '../api'
import { createSession, deleteSession, fetchLevels, fetchSession, fetchSessions, fetchStaged, renameSession } from '../api'
import { InlineRename } from './InlineRename'
import { navigate } from './route'

function sortByLastActiveDescending(sessions: readonly SessionSummary[]): SessionSummary[] {
  return [...sessions].sort((a, b) => b.last_active_at.localeCompare(a.last_active_at))
}

export function SessionPicker() {
  const [levels, setLevels] = useState<string[]>([])
  const [selectedLevel, setSelectedLevel] = useState('')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    fetchLevels()
      .then((payload) => {
        setLevels(payload.levels.map((l) => l.name))
        setSelectedLevel(payload.current || payload.levels[0]?.name || '')
      })
      .catch((e: unknown) => console.error('fetchLevels failed', e))
    fetchSessions()
      .then((payload) => setSessions(payload.sessions))
      .catch((e: unknown) => console.error('fetchSessions failed', e))
  }, [])

  const handleCreate = () => {
    if (!selectedLevel) return
    setCreating(true)
    createSession(selectedLevel)
      .then((rec) => navigate(`/session/${rec.id}/`))
      .catch((e: unknown) => console.error('createSession failed', e))
      .finally(() => setCreating(false))
  }

  const handleRowClick = (id: string) => {
    navigate(`/session/${id}/`)
  }

  // Both rename and delete from here need a claim token this tab has never held for most rows --
  // acquiring one first (GET, which mints a fresh one) is the deliberate, spec'd side effect: it
  // supersedes whatever window currently holds this session's claim, same as any other claim mint.
  const acquireClaim = (id: string): Promise<string> => fetchSession(id).then((rec) => rec.claim_token)

  const handleRename = (id: string, name: string) => {
    acquireClaim(id)
      .then(() => renameSession(id, name))
      .then((result) => {
        setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, name: result.name } : s)))
      })
      .catch((e: unknown) => console.error('rename failed', e))
  }

  const handleDelete = (id: string) => {
    fetchStaged(id)
      .then((staged) => {
        const hasUnsaved = Object.keys(staged).length > 0
        const message = hasUnsaved
          ? 'This session has unsaved edits. Delete anyway?'
          : 'Delete this session?'
        if (!window.confirm(message)) return
        acquireClaim(id)
          .then(() => deleteSession(id, { force: hasUnsaved }))
          .then(() => setSessions((prev) => prev.filter((s) => s.id !== id)))
          .catch((e: unknown) => console.error('delete failed', e))
      })
      .catch((e: unknown) => console.error('fetching staged state failed', e))
  }

  return (
    <div className="session-picker">
      <div className="session-picker-create">
        <select value={selectedLevel} onChange={(e) => setSelectedLevel(e.target.value)}>
          {levels.map((level) => (
            <option key={level} value={level}>
              {level}
            </option>
          ))}
        </select>
        <button type="button" onClick={handleCreate} disabled={creating || !selectedLevel}>
          Create session
        </button>
      </div>
      <div className="session-picker-list">
        {sortByLastActiveDescending(sessions).map((s) => (
          <div key={s.id} data-testid="session-picker-row" className="session-picker-row" onClick={() => handleRowClick(s.id)}>
            <span title={s.id} onClick={(e) => e.stopPropagation()}>
              <InlineRename value={s.name} placeholder={s.level} onRename={(name) => handleRename(s.id, name)} />
            </span>
            {s.name && <span className="session-picker-row-level">{s.level}</span>}
            <span className="session-picker-row-active">{s.last_active_at}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                handleDelete(s.id)
              }}
            >
              Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/session/SessionPicker.test.tsx && npx tsc -b`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/session/SessionPicker.tsx web/src/session/SessionPicker.test.tsx
git commit -m "Add SessionPicker: the session-management landing screen"
```

---

### Task 14: Frontend — `SaveBar.tsx`: `onClosed` prop

**Files:**
- Modify: `web/src/panels/SaveBar.tsx`
- Test: `web/src/panels/SaveBar.test.tsx`

**Interfaces:**
- Changes: `SaveBarProps` gains `onClosed?: () => void`.

- [ ] **Step 1: Write the failing tests**

Add to `web/src/panels/SaveBar.test.tsx`, inside the existing `describe('superseded (409)
handling', ...)` block (import `isClosedError`-equivalent behavior via the mocked `../api` module
at the top of this file — add `isClosedError` to that mock, mirroring the existing
`isSupersededError` mock exactly):

```typescript
    it('a "deleted" 409 from postSave calls onClosed, not onSuperseded', async () => {
      const closedError = Object.assign(new Error('sess-1: session deleted'), { status: 409 })
      postSave.mockRejectedValueOnce(closedError)
      const onSuperseded = vi.fn()
      const onClosed = vi.fn()
      render(
        <SaveBar level="TestLevel" stagedNames={new Set(['Light0'])} onSaved={vi.fn()} onDiscarded={vi.fn()} onSuperseded={onSuperseded} onClosed={onClosed} />,
      )

      fireEvent.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(onClosed).toHaveBeenCalledTimes(1))
      expect(onSuperseded).not.toHaveBeenCalled()
    })
```

Update the mock at the top of this file:
```typescript
vi.mock('../api', () => ({
  postSave: (...args: unknown[]) => postSave(...args),
  postDiscard: (...args: unknown[]) => postDiscard(...args),
  isSupersededError: (e: unknown) => typeof e === 'object' && e !== null && (e as { status?: number }).status === 409 && !String((e as Error).message).includes('deleted'),
  isClosedError: (e: unknown) => typeof e === 'object' && e !== null && (e as { status?: number }).status === 409 && String((e as Error).message).includes('deleted'),
}))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/panels/SaveBar.test.tsx`
Expected: FAIL — `onClosed` prop doesn't exist, `isClosedError` isn't imported by `SaveBar.tsx`.

- [ ] **Step 3: Implement**

In `web/src/panels/SaveBar.tsx`:

Edit the import line:
```typescript
import { isClosedError, isSupersededError, postDiscard, postSave } from '../api'
```

Add to `SaveBarProps`, right after `onSuperseded?: () => void`:
```typescript
  // Fires instead of onSuperseded when the 409 means the session was actually deleted, not merely
  // claimed elsewhere (Task 6's isClosedError). Optional, same convention as onSuperseded.
  onClosed?: () => void
```

Edit the function signature to destructure it:
```typescript
export function SaveBar({ level, stagedNames, onSaved, onDiscarded, onActorDiscarded, onSuperseded, onClosed }: SaveBarProps) {
```

In each of the three `.catch((e: unknown) => { ... })` blocks (Save, whole-level Discard, per-actor
conflict-discard), currently:
```typescript
        .catch((e: unknown) => {
          if (isSupersededError(e)) {
            onSuperseded?.()
            return
          }
          setError(String(e))
        })
```
change to:
```typescript
        .catch((e: unknown) => {
          if (isClosedError(e)) {
            onClosed?.()
            return
          }
          if (isSupersededError(e)) {
            onSuperseded?.()
            return
          }
          setError(String(e))
        })
```

Add `onClosed` to each of the three `useCallback` dependency arrays alongside `onSuperseded`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/panels/SaveBar.test.tsx && npx tsc -b`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/panels/SaveBar.tsx web/src/panels/SaveBar.test.tsx
git commit -m "SaveBar: route a deleted-session 409 to onClosed, not onSuperseded"
```

---

### Task 15: Frontend — `App.tsx`: wire routing, `useSession(id)`, and `onClosed` everywhere

**Files:**
- Modify: `web/src/App.tsx`
- Test: `web/src/App.test.tsx`

This is the integration task: every prior task's new piece gets mounted/wired here. Read the
CURRENT full contents of `web/src/App.tsx` and `web/src/App.test.tsx` before starting — this task
gives exact before/after text for the pieces that change, not a full reprint of either file.

**Interfaces:**
- Consumes: `useRoute`/`navigate` (Task 8), `useSession(sessionId)`/`markClosed` (Task 9),
  `SessionPicker` (Task 13), `SessionLabel` (Task 12), `isClosedError` (Task 6), `SaveBar`'s new
  `onClosed` prop (Task 14), `subscribeChangesAvailable`'s new `onClosed` param (Task 7).

- [ ] **Step 1: Write the failing tests**

In `web/src/App.test.tsx`:

Update the `./reload` mock to carry a 5th callback:
```typescript
const reloadSub: { current: { onChangesAvailable: () => void; onSuperseded: () => void; onClosed: () => void } | null } = { current: null }
vi.mock('./reload', () => ({
  subscribeChangesAvailable: (
    _sessionId: string,
    _claimToken: string,
    onChangesAvailable: () => void,
    onSuperseded: () => void,
    onClosed: () => void,
  ) => {
    reloadSub.current = { onChangesAvailable, onSuperseded, onClosed }
    return { unsubscribe: vi.fn() }
  },
}))
```

Change `beforeEach` to mount on a concrete session path instead of a bare `/` (the auto-create flow
is gone):
```typescript
beforeEach(() => {
  window.history.replaceState(null, '', `/session/${SESSION_ID}/`)
  reloadSub.current = null
})
```

Simplify `mockFetch`'s bootstrap: `useSession` no longer calls `/api/levels` or POSTs a new
session — it calls `GET /api/session/{id}` directly. Change:
```typescript
    if (url.endsWith('/api/levels')) return jsonResponse(LEVELS_PAYLOAD)
    if (url.endsWith(`/api/level/${LEVEL_NAME}/sessions`) && init?.method === 'POST') return jsonResponse(SESSION_RECORD, 201)
```
to:
```typescript
    if (url.endsWith(`/api/session/${SESSION_ID}`) && (!init || !init.method)) {
      return jsonResponse({ ...SESSION_RECORD, id: SESSION_ID, last_active_at: '2026-09-22T00:00:00Z', name: null })
    }
```
(`SESSION_RECORD` itself, still used elsewhere in this file for the create-session response shape
in `SessionPicker`-adjacent tests if any exist, can stay as is — this new branch is `useSession`'s
own read, a `SessionDetail` shape with `claim_token`/`last_active_at`/`name`, not the narrower
`SessionRecord` creation response.)

Every existing test in this file that currently sets a DIFFERENT `?session=` value via
`window.history.replaceState` before rendering must instead set `/session/<id>/` — search this file
for every `replaceState` call and update each to the path-based form. The "App: session switching"
describe block's own `mockFetchForSwitch` helper posts to `/api/level/{LEVEL}/sessions` today for
its OTHER-session fixture; leave that specific POST-based fixture alone if it's simulating
`SessionDropdown`'s switch-to-a-different-EXISTING-session flow via `GET /api/session/{otherId}`,
not creation — read that block fully before changing it, since it may not need any change at all
beyond the `beforeEach` fix above.

Add a new test proving the routing split:
```typescript
describe('App: routing', () => {
  it('a bare "/" renders the session picker, not the editor', async () => {
    window.history.replaceState(null, '', '/')
    mockFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByRole('combobox')).toBeTruthy())
    expect(screen.queryByTestId('viewport-stub')).toBeNull()
  })

  it('/session/<id>/ renders the editor', async () => {
    mockFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
  })
})

describe('App: deleted vs superseded', () => {
  it('a "closed" WS push shows the closed message, not the superseded takeover banner', async () => {
    mockFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())

    act(() => reloadSub.current?.onClosed())

    expect(screen.getByText(/this session was closed/i)).toBeTruthy()
  })

  it('a "deleted" 409 from Load/Rebuild shows the closed message too', async () => {
    mockFetch((url) => {
      if (url.endsWith('/load')) return jsonResponse({ error: 'session deleted' }, 409)
      return undefined
    })
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /rebuild/i }))

    await waitFor(() => expect(screen.getByText(/this session was closed/i)).toBeTruthy())
  })
})
```

(`act`/`fireEvent`/`waitFor` are already imported at the top of this file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/App.test.tsx`
Expected: FAIL — `App` still calls `useSession()` with no argument, doesn't render `SessionPicker`
for `/`, and has no `onClosed` wiring.

- [ ] **Step 3: Implement**

In `web/src/App.tsx`, add imports:
```typescript
import { isClosedError, ... } from './api'   // add isClosedError to the existing import line
import { SessionLabel } from './session/SessionLabel'
import { SessionPicker } from './session/SessionPicker'
import { useRoute } from './session/route'
```

Rename the existing `function App() {` to `function SessionEditor({ sessionId }: { sessionId:
string }) {`, and change its `useSession()` call:
```typescript
  const session = useSession(sessionId)
```
(was `const session = useSession()`).

Update the destructure right below it to also pull `markClosed` and `name`:
```typescript
  const { sessionId, level, view, claimToken, name, reload: reloadSession, markSuperseded, markClosed } = session
```
(only add `name`/`markClosed` if `UseSessionResult`/`SessionState` from Task 9 actually exposes
`name` — re-check Task 9's interface: it does NOT currently include `name`, only
`sessionId`/`level`/`view`/`claimToken`. `SessionLabel` needs the session's name to render, and
`useSession` never fetches it as a first-class field today. Add `name: string | null` to
`SessionState`/`UseSessionResult` in `SessionContext.tsx` as part of THIS task — `activate()` there
already receives the full `SessionDetail` (which Task 6 gave a `name` field), so change
`activate`'s `setState` call to include `name: rec.name`, and `INITIAL_STATE`/the `catch` branch's
`setState` calls to include `name: null`. This is a small addition to Task 9's file, done here
because `SessionLabel`'s own need for it wasn't visible until this integration task.)

Edit `handleSwitchSession`:
```typescript
  const handleSwitchSession = useCallback(
    (id: string) => {
      if (id === sessionId) return
      navigate(`/session/${id}/`)
    },
    [sessionId],
  )
```
(was: writing `?session=` into the URL and calling `reloadSession()` — both gone; navigating
changes the `sessionId` prop `SessionEditor` receives from the new outer `App` below, which
`useSession`'s own effect already re-fires on.)

Edit the WS subscription effect — find:
```typescript
    const sub = subscribeChangesAvailable(sessionId, claimToken, () => refreshStatus(sessionId), markSuperseded)
```
and its cleanup/deps below it — add `markClosed`:
```typescript
    const sub = subscribeChangesAvailable(sessionId, claimToken, () => refreshStatus(sessionId), markSuperseded, markClosed)
```
and add `markClosed` to that effect's own dependency array (`[sessionId, claimToken,
refreshStatus, markSuperseded]` → `..., markClosed]`).

Edit `runBuildAction`'s catch branch:
```typescript
        .catch((e: unknown) => {
          if (isClosedError(e)) {
            markClosed()
            return
          }
          if (isSupersededError(e)) {
            markSuperseded()
            return
          }
          setBuildError(String(e))
        })
```
and add `markClosed` to `runBuildAction`'s own `useCallback` dependency array.

Add `onClosed={markClosed}` to the `<SaveBar ...>` JSX, alongside the existing
`onSuperseded={markSuperseded}`.

Replace the toolbar's rendering to include `SessionLabel` next to `SessionDropdown` — find:
```tsx
          <SessionDropdown currentSessionId={sessionId} onSwitchSession={handleSwitchSession} />
```
and add, immediately before it:
```tsx
          <SessionLabel sessionId={sessionId} level={level} name={name} onRenamed={() => { /* SessionContext has no local name-refresh; a rename here just re-renders with the same session's next reload() -- fine for now, name display updates on next full reload */ }} />
```
(Simplify this once written: `SessionLabel` already receives `name` from `SessionEditor`'s own
`session.name`; its own `onRenamed` callback exists so a caller COULD update local state
immediately without waiting for a refetch. Since `SessionContext` has no setter for `name` alone,
the pragmatic, correct-enough implementation is a local `useState<string | null>` in `SessionEditor`
seeded from `session.name` and updated by `onRenamed`, passed to `SessionLabel` as `name` instead of
`session.name` directly — add this:
```typescript
  const [displayName, setDisplayName] = useState<string | null>(null)
  useEffect(() => setDisplayName(name), [name])
```
right after the `session` destructure, and use `name={displayName}` /
`onRenamed={setDisplayName}` on `SessionLabel` instead of the inline no-op above.)

Finally, add the new outer routing component and change the default export. At the VERY END of the
file, currently:
```typescript
export default App
```
change to:
```typescript
function App() {
  const route = useRoute()
  if (route.screen === 'picker') return <SessionPicker />
  return <SessionEditor sessionId={route.id} />
}

export default App
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/App.test.tsx && npx vitest run && npx tsc -b`
Expected: PASS — the targeted file, then the FULL frontend suite (this task touches the most
central file in the app; a full run matters here, not just the new tests), then a clean typecheck.

- [ ] **Step 5: Commit**

```bash
git add web/src/App.tsx web/src/App.test.tsx web/src/session/SessionContext.tsx
git commit -m "App.tsx: wire routing, SessionPicker/SessionLabel, and onClosed everywhere"
```

## Self-Review Notes (for whoever runs this plan)

- **Spec coverage**: every numbered decision in the spec maps to a task above — 1/2 (Task 15's
  routing split), 3 (Task 9's `name` display + Task 12), 4 (Task 10), 5 (Tasks 11/12/13's `title=`),
  6 (Task 12), 7 (Task 13's confirm-copy branch), 8 (Task 11 unchanged capabilities). The
  deleted-vs-superseded fix maps to Tasks 2/3/5/6/7/14/15.
- **Known risk, flagged rather than hidden**: Task 15 is large and touches the plan's most central,
  least-mechanical file. If the task reviewer finds the `SessionLabel`/`displayName` wiring or the
  `App`/`SessionEditor` split doesn't fit cleanly once the real current file is in hand, that's an
  expected outcome of integrating 14 prior tasks into one file — resolve it against this plan's
  stated intent (routing decides picker-vs-editor; `SessionEditor` owns everything `App` used to;
  `useSession` takes the id as a prop) rather than the literal before/after snippets if the two
  disagree once the real file is read.
