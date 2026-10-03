"""`/status`'s `changes_available` -- the yellow "trunk changed -- Reload to see it" banner's only
source of truth (`web/src/App.tsx` renders it from `/status` and nothing else; the WS push merely
triggers a refetch).

Board `changes-available-banner-dies-after-a-serve`, owner ruling 2026-10-03: the signal is derived
from trunk CONTENT (`t3dtree.stamp_digest` of the current tree vs. the digest of what this session
last Loaded), not from counting watcher events. These tests pin the three things only a
content-derived signal gets right -- a `serve` restart, a change that lands while the server is
down, and a level whose watcher never fired -- each of which the in-memory generation counter this
replaced reported as "no changes"."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from uedcli import trunk
from uedcli.model import Level
from uedcli.serve import app as serve_app, sessions
from uedcli.tests.conftest import cube_room


def _require_ued22():
    pytest.importorskip("uedcli_native")
    from uedcli.tests.test_serve_scene import UED22
    if not (UED22 / "Engine.u").is_file():
        pytest.skip("committed UED22/Engine.u not present")


@pytest.fixture
def level(tmp_path, monkeypatch):
    """A project with one actor, plus a `boot()` that stands up a FRESH app over the same on-disk
    state -- the stand-in for restarting `serve` -- and a `change()` that writes one more actor."""
    _require_ued22()
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    first = cube_room(name="Room0")
    trunk.write_level(maps_dir, Level(actors={first.name: first}, order=[first.name]),
                      {first.name: "n000"})
    project = SimpleNamespace(root=str(root), maps=None)
    index = _ued22_index()
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], index, DEFAULTS))

    counter = [0]

    def boot():
        serve_app._scene_inputs_cache.clear()        # a genuinely cold process, no carried memo
        app = serve_app.create_app(project, "TestLevel")
        return app, TestClient(app)

    def change():
        counter[0] += 1
        extra = cube_room(name=f"Extra{counter[0]}")
        trunk.write_level(maps_dir, Level(actors={extra.name: extra}, order=[extra.name]),
                          {extra.name: f"n{counter[0]:03d}"}, only={extra.name})

    return SimpleNamespace(boot=boot, change=change, maps_dir=maps_dir)


def _open_session(c):
    """A session created the way a real page load creates one -- through the route, which seeds its
    baseline digest."""
    created = c.post("/api/level/TestLevel/sessions").json()
    return created["id"], created["claim_token"]


def _changes(c, sid: str) -> bool:
    return c.get(f"/api/session/{sid}/status").json()["changes_available"]


def _drop_digest_cache(app) -> None:
    """What `_on_trunk_settled` does to the cached digest. These tests are synchronous and have no
    event loop running the watcher, so they drop it by hand rather than wait out `_DIGEST_TTL_S`."""
    app.state.get_or_create_level_context("TestLevel").digest_ref[0] = None


def test_a_freshly_opened_session_shows_no_banner(level):
    app, c = level.boot()
    sid, _token = _open_session(c)
    assert _changes(c, sid) is False


def test_a_trunk_change_raises_the_banner_and_a_load_clears_it(level):
    app, c = level.boot()
    sid, token = _open_session(c)

    level.change()
    _drop_digest_cache(app)
    assert _changes(c, sid) is True

    assert c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token}).status_code == 200
    assert _changes(c, sid) is False


def test_the_banner_survives_a_serve_restart(level):
    """The reported bug. The old signal compared an in-memory counter that restarted at 0 against a
    per-session mark persisted across restarts, so a session reused after a restart saw NO banner
    until the counter climbed back past its own history -- and the blackout grew the longer that
    session had been used. Here the session Loads three times first, which is what used to build up
    that history."""
    app, c = level.boot()
    sid, token = _open_session(c)
    for _ in range(3):
        level.change()
        _drop_digest_cache(app)
        assert _changes(c, sid) is True
        c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token})
    assert _changes(c, sid) is False

    app2, c2 = level.boot()
    token2 = app2.state.claims.mint(sid)

    assert _changes(c2, sid) is False            # nothing changed yet: still current
    level.change()
    _drop_digest_cache(app2)
    assert _changes(c2, sid) is True             # the FIRST post-restart change, not the 4th

    assert c2.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token2}).status_code == 200
    assert _changes(c2, sid) is False


def test_a_change_made_while_serve_was_down_is_noticed(level):
    """No watcher ran for this change at all -- there was no process. An event counter could never
    see it; asking the disk does."""
    app, c = level.boot()
    sid, token = _open_session(c)
    c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token})
    assert _changes(c, sid) is False

    level.change()                               # the "server is down" window
    _app2, c2 = level.boot()

    assert _changes(c2, sid) is True


def test_the_banner_does_not_need_the_watcher_to_have_fired(level):
    """`_on_trunk_settled` is never called here. The TTL expiry re-reads the disk on its own, so a
    dropped or missed watcher event delays the banner rather than suppressing it."""
    app, c = level.boot()
    sid, token = _open_session(c)
    c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token})

    level.change()
    _drop_digest_cache(app)                      # stands in for the TTL having expired
    assert _changes(c, sid) is True


def test_a_session_that_never_loaded_is_stale_by_definition(level):
    """`last_loaded_digest is None` means "has never Loaded", which cannot be showing the current
    trunk. `create_session_route` seeds the digest precisely so a real window never lands here --
    `test_a_freshly_opened_session_shows_no_banner` is the other side of this."""
    app, c = level.boot()
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    assert sess.last_loaded_digest is None
    assert _changes(c, sess.id) is True


def test_load_makes_the_digest_match_the_tree_on_disk(level):
    from uedcli import t3dtree

    app, c = level.boot()
    sid, token = _open_session(c)
    level.change()
    c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token})

    rec = sessions.get_session(app.state.sessions_root, sid)
    assert rec.last_loaded_digest == t3dtree.stamp_digest(
        t3dtree.stamp_actor_tree(level.maps_dir))


def test_the_digest_is_read_once_per_ttl_not_once_per_poll(level, monkeypatch):
    """Every open window polls `/status` every 3s and a stamp pass costs ~0.08s warm on a big level,
    so the read is shared across them for `_DIGEST_TTL_S`."""
    app, c = level.boot()
    sid, _token = _open_session(c)

    reads = []
    real = serve_app.t3dtree.stamp_actor_tree

    def spy(d):
        reads.append(d)
        return real(d)

    monkeypatch.setattr(serve_app.t3dtree, "stamp_actor_tree", spy)
    _drop_digest_cache(app)                      # the session's own seeding already warmed it
    for _ in range(5):
        _changes(c, sid)
    assert len(reads) == 1

    _drop_digest_cache(app)                      # what a settled change does
    _changes(c, sid)
    assert len(reads) == 2


def test_the_settle_hook_drops_the_cached_digest(level):
    app, c = level.boot()
    sid, _token = _open_session(c)
    _changes(c, sid)                             # populates the cache
    ctx = app.state.get_or_create_level_context("TestLevel")
    assert ctx.digest_ref[0] is not None

    asyncio.run(app.state.on_trunk_settled())

    assert ctx.digest_ref[0] is None


def test_an_unreadable_actor_dir_does_not_wedge_the_banner_on(level):
    """Review finding: a dir that STATS but never READS -- an empty `actor.t3d`, or one that is a
    directory where a file belongs (both rejected by `_read_actor_dir`) -- used to leave the Load
    digest a permanent strict subset of the disk digest. The banner then stayed up forever on an
    otherwise healthy level: Reload paid a full Load and cleared nothing, every time."""
    app, c = level.boot()
    sid, token = _open_session(c)

    ghost = level.maps_dir / "actors" / "Ghost"
    ghost.mkdir(parents=True)
    (ghost / "actor.t3d").write_text("")           # zero length: stats fine, never parses
    _drop_digest_cache(app)

    assert c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token}).status_code == 200
    _drop_digest_cache(app)
    assert _changes(c, sid) is False                # clearable, not wedged
    assert "Ghost" not in {a["name"] for a in c.get(f"/api/session/{sid}/scene").json()["actors"]}


def test_an_actor_dir_whose_body_is_a_directory_does_not_wedge_the_banner_on(level):
    """The other persistent rejection `_read_actor_dir` makes, same consequence as above."""
    app, c = level.boot()
    sid, token = _open_session(c)

    (level.maps_dir / "actors" / "Conflict" / "actor.t3d").mkdir(parents=True)
    _drop_digest_cache(app)

    assert c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token}).status_code == 200
    _drop_digest_cache(app)
    assert _changes(c, sid) is False


def test_scene_records_the_trunk_it_served_so_the_banner_clears(level):
    """Review finding: the window renders the level-shared trunk slot, and that slot also advances
    under `_get_trunk`'s own automatic initial Load, which belongs to no session. Recording only on
    `/load` left the banner up over content already on screen -- exactly on the restart path this
    whole change is about."""
    app, c = level.boot()
    sid, token = _open_session(c)
    c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token})

    level.change()                                  # the "serve is down" window
    _app2, c2 = level.boot()

    assert _changes(c2, sid) is True                # before the window has fetched anything
    shown = {a["name"] for a in c2.get(f"/api/session/{sid}/scene").json()["actors"]}
    assert "Extra1" in shown                        # the bootstrap Load handed over the change
    assert _changes(c2, sid) is False               # ...so the banner must not still be up


def test_a_sibling_load_does_not_clear_a_window_that_has_not_refetched(level):
    """The flip side: `/scene` is the acknowledgement, not the shared slot moving. Another
    session's Load advances the slot, but a window that has not re-fetched is still displaying the
    old scene and must keep its banner."""
    app, c = level.boot()
    sid_a, token_a = _open_session(c)
    sid_b, _token_b = _open_session(c)
    for sid in (sid_a, sid_b):
        c.get(f"/api/session/{sid}/scene")
    assert _changes(c, sid_a) is False and _changes(c, sid_b) is False

    level.change()
    _drop_digest_cache(app)
    assert _changes(c, sid_a) is True and _changes(c, sid_b) is True

    c.post(f"/api/session/{sid_a}/load", headers={"X-Claim-Token": token_a})
    c.get(f"/api/session/{sid_a}/scene")

    assert _changes(c, sid_a) is False
    assert _changes(c, sid_b) is True                # B never refetched: still showing the old one


def test_within_the_ttl_the_cached_digest_is_reused(level, monkeypatch):
    """A long TTL so there is no wall-clock budget to lose: the answer must come from the cache,
    not the disk. Paired with the expiry test below -- together they pin both halves without
    either depending on timing."""
    monkeypatch.setattr(serve_app, "_DIGEST_TTL_S", 3600.0)
    app, c = level.boot()
    sid, token = _open_session(c)
    c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token})
    c.get(f"/api/session/{sid}/scene")
    assert _changes(c, sid) is False

    level.change()                                  # no settle hook, no cache drop

    assert _changes(c, sid) is False                # still the cached answer


def test_once_the_ttl_expires_the_disk_is_read_again(level, monkeypatch):
    """The TTL is the self-healing half of a content-derived signal: a watcher event that never
    arrives must delay the banner, not suppress it. Nothing else in this file proves the expiry --
    the other tests drop the cache by hand, which is what the settle hook does, not the TTL.

    Only the sleep has to exceed the TTL, so a slow or loaded host makes this MORE likely to pass,
    never less."""
    import time

    monkeypatch.setattr(serve_app, "_DIGEST_TTL_S", 0.01)
    app, c = level.boot()
    sid, token = _open_session(c)
    c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token})
    c.get(f"/api/session/{sid}/scene")
    assert _changes(c, sid) is False

    level.change()                                  # no settle hook, no cache drop
    time.sleep(0.2)

    assert _changes(c, sid) is True                 # expired, re-read from disk


def test_scene_records_in_memory_and_never_writes_the_session_record(level):
    """The `/scene` acknowledgement is per-process on purpose: a GET writing `index.json` would
    recreate the directory of a session deleted mid-request and clobber a concurrent rename. The
    banner must still clear, so the record has to be in memory rather than merely absent."""
    app, c = level.boot()
    sid, token = _open_session(c)
    c.post(f"/api/session/{sid}/load", headers={"X-Claim-Token": token})

    level.change()
    _app2, c2 = level.boot()
    on_disk_before = sessions.get_session(_app2.state.sessions_root, sid).last_loaded_digest
    assert _changes(c2, sid) is True

    c2.get(f"/api/session/{sid}/scene")

    assert _changes(c2, sid) is False                           # cleared...
    assert sessions.get_session(_app2.state.sessions_root, sid).last_loaded_digest \
        == on_disk_before                                       # ...without touching the record


def test_interleaved_loads_leave_the_trunk_and_its_cache_consistent(level, monkeypatch):
    """Review finding: `session_load` published `trunk_cache_ref` under `ctx.trunk_lock` but
    `trunk_ref` after releasing it, so two interleaved Loads could leave B's cache paired with A's
    trunk -- permanently. `/scene`'s `is`-match then reads that as "not the trunk this cache
    describes" and stops recording for good, so every window keeps its banner over content it is
    already displaying.

    Interleaved deterministically rather than with threads: the inner Load runs from inside the
    outer one's `check_load_conflicts`, which is exactly the window the defect lived in."""
    from uedcli.serve import edits

    app, c = level.boot()
    sid_a, token_a = _open_session(c)
    sid_b, token_b = _open_session(c)
    c.get(f"/api/session/{sid_a}/scene")
    level.change()
    _drop_digest_cache(app)

    real = edits.check_load_conflicts
    nested = []

    def reentrant(*a, **k):
        if not nested:                               # once, from A's Load only
            nested.append(True)
            c.post(f"/api/session/{sid_b}/load", headers={"X-Claim-Token": token_b})
        return real(*a, **k)

    monkeypatch.setattr(edits, "check_load_conflicts", reentrant)
    assert c.post(f"/api/session/{sid_a}/load",
                  headers={"X-Claim-Token": token_a}).status_code == 200
    assert nested, "the inner Load never ran -- the interleaving was not exercised"

    ctx = app.state.get_or_create_level_context("TestLevel")
    assert ctx.trunk_cache_ref[0].read.level is ctx.trunk_ref[0].level

    # ...and the consequence that made it matter: `/scene` still records, so the banner clears.
    _drop_digest_cache(app)
    c.get(f"/api/session/{sid_a}/scene")
    assert _changes(c, sid_a) is False
