"""End-to-end: `uedcli serve`'s `/ws` route pushes a `{"type": "changes_available", ...}` message
when the served level's trunk dir changes on disk — the real `TrunkWatcher` wired into `create_app`
(Task 4), not just its debounce unit (`test_serve_watch.py`). Real `watchfiles` filesystem watching
has its own settle latency on top of `TrunkWatcher`'s own debounce, so this waits a few seconds —
acceptable for one scoped, infrequently-run test.

gui-explicit-rebuild plan Task 3: the message `type` changed from `"reload"` (the client silently
auto-refetching) to `"changes_available"` (a banner the client shows on an explicit Load) — the
watcher no longer clears the trunk/geometry cache slots either, see `test_serve_app.py`.

persistent-GUI-editing-sessions plan Task 15: `/ws` now requires a real `?session=<id>&claim=
<token>` in the connect URL (no back-compat no-params legacy mode) -- this test creates a real
session on the startup level first and mints its claim directly off `app.state.claims`/
`app.state.sessions_root`, the same pattern `test_serve_app.py`'s own session tests use."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from uedcli.serve import sessions
from uedcli.serve.app import create_app


def test_a_trunk_write_pushes_a_ws_changes_available_message(tmp_path):
    root = tmp_path / "proj"
    level_dir = root / "maps" / "TestLevel"
    level_dir.mkdir(parents=True)
    (level_dir / "seed.txt").write_text("x")
    project = SimpleNamespace(root=str(root), maps=None)

    app = create_app(project, "TestLevel")
    with TestClient(app) as client:                       # runs startup/shutdown -> starts the watcher
        sess = sessions.create_session(app.state.sessions_root, "TestLevel")
        token = app.state.claims.mint(sess.id)
        with client.websocket_connect(f"/ws?session={sess.id}&claim={token}") as ws:
            (level_dir / "seed.txt").write_text("y")       # a real trunk-dir change
            msg = ws.receive_json(mode="text")              # blocks (with the client's own timeout)
            assert msg == {"type": "changes_available", "level": "TestLevel"}


def test_a_trunk_write_pushes_a_ws_message_for_a_lazily_created_non_startup_level(tmp_path):
    """final-review fix round, Finding 5: `_get_or_create_level_context` builds a lazily-created
    (non-startup) level's `TrunkWatcher` but never used to START it -- so a session opened on any
    level other than the process's own startup level silently never got a `changes_available` push.
    `ws_endpoint` now starts it on connect (`TrunkWatcher.started` guards against a double-start).
    `create_app(project, None)`: no startup level at all, so `OtherLevel`'s watcher can ONLY ever be
    started lazily -- proving this isn't just piggybacking on `_lifespan`'s own startup-level start."""
    root = tmp_path / "proj"
    level_dir = root / "maps" / "OtherLevel"
    level_dir.mkdir(parents=True)
    (level_dir / "seed.txt").write_text("x")
    project = SimpleNamespace(root=str(root), maps=None)

    app = create_app(project, None)
    with TestClient(app) as client:
        sess = sessions.create_session(app.state.sessions_root, "OtherLevel")
        token = app.state.claims.mint(sess.id)
        assert app.state.get_or_create_level_context("OtherLevel").watcher.started is False
        with client.websocket_connect(f"/ws?session={sess.id}&claim={token}") as ws:
            assert app.state.get_or_create_level_context("OtherLevel").watcher.started is True
            (level_dir / "seed.txt").write_text("y")       # a real trunk-dir change
            msg = ws.receive_json(mode="text")
            assert msg == {"type": "changes_available", "level": "OtherLevel"}
