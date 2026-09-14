"""End-to-end: `uedcli serve`'s `/ws` route pushes a `{"type": "reload", ...}` message when the
served level's trunk dir changes on disk — the real `TrunkWatcher` wired into `create_app` (Task 4),
not just its debounce unit (`test_serve_watch.py`). Real `watchfiles` filesystem watching has its
own settle latency on top of `TrunkWatcher`'s own debounce, so this waits a few seconds — acceptable
for one scoped, infrequently-run test."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from uedcli.serve.app import create_app


def test_a_trunk_write_pushes_a_ws_reload_message(tmp_path):
    root = tmp_path / "proj"
    level_dir = root / "maps" / "TestLevel"
    level_dir.mkdir(parents=True)
    (level_dir / "seed.txt").write_text("x")
    project = SimpleNamespace(root=str(root), maps=None)

    app = create_app(project, "TestLevel")
    with TestClient(app) as client:                       # runs startup/shutdown -> starts the watcher
        with client.websocket_connect("/ws") as ws:
            (level_dir / "seed.txt").write_text("y")       # a real trunk-dir change
            msg = ws.receive_json(mode="text")              # blocks (with the client's own timeout)
            assert msg == {"type": "reload", "level": "TestLevel"}
