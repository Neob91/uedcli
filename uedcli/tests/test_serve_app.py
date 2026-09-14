"""`uedcli serve`'s FastAPI app skeleton (plan Task 1): the health route, and the structured-error
exception handler (no Python exception reaches the user — CLAUDE.md)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from uedcli.serve.app import create_app


def _project(tmp_path):
    return SimpleNamespace(root=str(tmp_path), maps=None)


def test_health_reports_the_served_level(tmp_path):
    app = create_app(_project(tmp_path), "TestLevel")
    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "level": "TestLevel"}


def test_fault_route_is_absent_by_default(tmp_path):
    app = create_app(_project(tmp_path), "TestLevel")
    c = TestClient(app)
    assert c.get("/api/_boom").status_code == 404


def test_fault_route_renders_a_structured_error_not_a_traceback(tmp_path):
    app = create_app(_project(tmp_path), "TestLevel", fault_route=True)
    # `raise_server_exceptions=False`: a bare-`Exception` handler DOES produce the real HTTP
    # response in production, but `TestClient` re-raises server exceptions for debugging by
    # default even when a handler caught them — this is what the flag turns off, per Starlette's
    # own documented caveat, not a change to how the app itself behaves.
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/_boom")
    assert r.status_code == 422
    assert r.json() == {"error": "Actor not found: Foo"}


def test_broadcast_reload_survives_a_connection_change_mid_broadcast(tmp_path):
    """Regression (review finding): `_broadcast_reload` used to iterate the live `connections` set
    while `await`ing each send — a client connecting mid-broadcast (the multi-viewer scenario the
    spec explicitly allows) grows the set's size during iteration and raises `RuntimeError: Set
    changed size during iteration`, silently dropping the whole reload push for every connected
    client. (A discard+add pair that returns the set to its ORIGINAL size doesn't reliably trigger
    CPython's check — a net size CHANGE, as a real new connection causes, does.)"""
    app = create_app(_project(tmp_path), "TestLevel")

    class FakeWS:
        def __init__(self):
            self.sent = []
            self.on_send = None

        async def send_json(self, data):
            self.sent.append(data)
            if self.on_send:
                self.on_send()

    ws_a, ws_b = FakeWS(), FakeWS()
    app.state.connections.add(ws_a)

    def connect_mid_broadcast():
        # Simulate a second viewer's WebSocket connecting while ws_a's send is in flight.
        app.state.connections.add(ws_b)

    ws_a.on_send = connect_mid_broadcast

    asyncio.run(app.state.broadcast_reload())  # must not raise

    assert ws_a.sent == [{"type": "reload", "level": "TestLevel"}]
    assert app.state.connections == {ws_a, ws_b}
