"""Offline tests for the in-container batch driver `uedctl/game/preview_batch.py` (the ONE
`docker exec` that runs the whole `--game` batch). The link socket and the X-grab subprocess are
faked — nothing here needs docker or a game. Loaded by path (it's a baked container script, not a
package module)."""
from __future__ import annotations

import importlib.util
import io
import json
import struct
import sys
from pathlib import Path

import pytest

_BATCH = Path(__file__).resolve().parents[1] / "game" / "preview_batch.py"
sys.path.insert(0, str(_BATCH.parents[1]))              # so `import preview_shots` (baked alongside) resolves
_spec = importlib.util.spec_from_file_location("preview_batch", _BATCH)
pb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pb)


class FakeSock:
    """A canned link: frames each command's scripted reply with the request id it was sent."""
    def __init__(self, replies):
        self.replies = replies
        self.sent = []
        self._buf = b""

    def settimeout(self, t):
        pass

    def sendall(self, data):
        self.sent.append(data)
        line = data.decode().strip()                       # "#<id> <cmd> <rest>"
        rid = line.split(" ", 1)[0]
        cmd = line.split(" ", 1)[1] if " " in line else ""
        key = cmd.split(" ", 1)[0] if cmd else ""
        reply = self.replies.get(key, "OK " + key)
        self._buf += ("\n".join(rid + " " + r for r in reply.split("\n") if r) + "\n").encode()

    def recv(self, n):
        d, self._buf = self._buf[:n], self._buf[n:]
        return d

    def close(self):
        pass


def _install(monkeypatch, replies, png=b"PNGDATA", grab_rc=0):
    monkeypatch.setattr(pb.socket, "create_connection", lambda addr, timeout=8: FakeSock(replies))
    monkeypatch.setattr(pb.time, "sleep", lambda s: None)  # skip the real frame-settle wait
    monkeypatch.setattr(pb, "deliver", lambda m: None)
    monkeypatch.setattr(pb.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": grab_rc,
                                                       "stdout": png, "stderr": b""})())


def _run_main(monkeypatch, req):
    monkeypatch.setattr(pb.sys, "stdin", io.StringIO(json.dumps(req)))
    outbuf = io.BytesIO()
    monkeypatch.setattr(pb.sys, "stdout", type("O", (), {"buffer": outbuf})())
    rc = pb.main()
    return rc, outbuf.getvalue()


def test_stem_strips_dx_and_unr_and_dirs():
    assert pb._stem("materialized__lvl__abc.dx") == "materialized__lvl__abc"
    assert pb._stem("/x/y/Foo.unr") == "Foo"


def test_levelname_parse():
    assert pb._levelname([b"#1 LevelName copied__abc__dx", b"#1 OK GetCurrentLevelName"]) \
        == "copied__abc__dx"
    assert pb._levelname([b"#1 OK Ping"]) == ""


def _frames(data):
    out, i = [], 0
    while i < len(data):
        nl = data.index(b"\n", i)
        status = json.loads(data[i:nl])
        i = nl + 1
        if not status.get("ok"):
            out.append((False, status.get("err")))
            continue
        (ln,) = struct.unpack(">I", data[i:i + 4])
        i += 4
        out.append((True, data[i:i + ln]))
        i += ln
    return out


def test_main_skips_travel_when_on_stem(monkeypatch):
    replies = {"GetCurrentLevelName": "LevelName copied__abc__dx\nOK GetCurrentLevelName",
               "PrepareCamera": "OK PrepareCamera"}
    _install(monkeypatch, replies, png=b"PNGDATA")
    called = {"travel": False}
    monkeypatch.setattr(pb, "travel", lambda *a, **k: called.__setitem__("travel", True))
    req = {"deliver": None, "stem": "copied__abc__dx", "rebuild": False,
           "window_title": "deus ex", "window_exclude": [], "shots": [[1, 2, 3, 0, 0]]}
    rc, data = _run_main(monkeypatch, req)
    assert rc == 0 and called["travel"] is False           # already on the map → no travel
    assert _frames(data) == [(True, b"PNGDATA")]


def test_main_travels_when_off_stem(monkeypatch):
    replies = {"GetCurrentLevelName": "LevelName UedPreviewBoot\nOK GetCurrentLevelName",
               "PrepareCamera": "OK PrepareCamera"}
    _install(monkeypatch, replies)
    called = {"stem": None}
    monkeypatch.setattr(pb, "travel", lambda stem, **k: called.__setitem__("stem", stem))
    req = {"deliver": "copied__abc__dx.dx", "stem": "copied__abc__dx", "rebuild": False,
           "window_title": "deus ex", "window_exclude": [], "shots": [[0, 0, 0, 0, 0]]}
    rc, data = _run_main(monkeypatch, req)
    assert rc == 0 and called["stem"] == "copied__abc__dx"   # off the map → travel
    assert _frames(data) == [(True, b"PNGDATA")]


def test_main_grab_failure_emits_ok_false(monkeypatch):
    replies = {"GetCurrentLevelName": "LevelName s\nOK GetCurrentLevelName",
               "PrepareCamera": "OK PrepareCamera"}
    _install(monkeypatch, replies, png=b"", grab_rc=1)     # xgrab finds no window
    monkeypatch.setattr(pb, "travel", lambda *a, **k: None)
    req = {"deliver": None, "stem": "s", "rebuild": False,
           "window_title": "deus ex", "window_exclude": [], "shots": [[0, 0, 0, 0, 0]]}
    rc, data = _run_main(monkeypatch, req)
    assert rc == 1
    frames = _frames(data)
    assert len(frames) == 1 and frames[0][0] is False       # {ok:false}, no binary frame


def test_main_prepare_camera_failure_emits_ok_false(monkeypatch):
    replies = {"GetCurrentLevelName": "LevelName s\nOK GetCurrentLevelName",
               "PrepareCamera": "ERR something"}
    _install(monkeypatch, replies)
    monkeypatch.setattr(pb, "travel", lambda *a, **k: None)
    req = {"deliver": None, "stem": "s", "rebuild": False,
           "window_title": "deus ex", "window_exclude": [], "shots": [[0, 0, 0, 0, 0]]}
    rc, data = _run_main(monkeypatch, req)
    assert rc == 1 and _frames(data)[0][0] is False


# ----------------------------------------------------------------- engine-path coverage (reviewer H2)


class StatefulLink:
    """A fake link whose current level CHANGES after a TravelToLevel — exercises the real 3-phase
    travel() and the persistent multi-shot connection. ONE instance is returned for every connect
    (so state persists across phases/shots)."""
    def __init__(self, start="UedPreviewBoot", fail_prepare_after=None, actors=None):
        self.level = start
        self.fail_prepare_after = fail_prepare_after
        self.actors = actors or {}                          # name -> (x, y, z), for @actor resolution
        self.travels = 0
        self.prep = 0
        self._buf = b""

    def settimeout(self, t):
        pass

    def sendall(self, data):
        line = data.decode().strip()
        rid = line.split(" ", 1)[0]
        cmd = line.split(" ", 1)[1] if " " in line else ""
        key = cmd.split(" ", 1)[0]
        if key == "GetCurrentLevelName":
            reply = "LevelName %s\nOK GetCurrentLevelName" % self.level
        elif key == "TravelToLevel":
            self.travels += 1
            self.level = cmd.split(" ", 1)[1].strip()
            reply = "OK TravelToLevel " + self.level
        elif key == "PrepareCamera":
            self.prep += 1
            reply = ("ERR wedged" if self.fail_prepare_after and self.prep > self.fail_prepare_after
                     else "OK PrepareCamera")
        elif key == "GetActorLocation":
            nm = cmd.split(" ", 1)[1].strip()
            reply = ("Location %d %d %d\nOK GetActorLocation" % self.actors[nm]
                     if nm in self.actors else "ERR actor-not-found " + nm)
        elif key == "ListActors":
            reply = "\n".join("Actor %s %d %d %d" % (n, x, y, z)
                              for n, (x, y, z) in self.actors.items()) + "\nOK ListActors"
        else:
            reply = "OK " + key
        self._buf += ("\n".join(rid + " " + r for r in reply.split("\n") if r) + "\n").encode()

    def recv(self, n):
        d, self._buf = self._buf[:n], self._buf[n:]
        return d

    def close(self):
        pass


def _install_stateful(monkeypatch, link):
    monkeypatch.setattr(pb.socket, "create_connection", lambda addr, timeout=8: link)
    monkeypatch.setattr(pb.time, "sleep", lambda s: None)
    monkeypatch.setattr(pb, "deliver", lambda m: None)
    monkeypatch.setattr(pb, "_actor_cache", {})            # reset the module-global @actor cache
    monkeypatch.setattr(pb.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 0, "stdout": b"PNG",
                                                       "stderr": b""})())


def _shot_dict(**kw):
    base = dict(at=None, rot=None, look=None, orbit=None, radius=None, azimuth=None, elev=0.0, name=None)
    base.update(kw)
    return base


def test_resolve_shots_resolves_at_actor(monkeypatch):
    link = StatefulLink(actors={"PathNode3": (100, 200, 50)})
    _install_stateful(monkeypatch, link)
    rows = pb.resolve_shots([_shot_dict(at="PathNode3", rot=[0.0, 90.0])])
    assert rows[0][:3] == [100, 200, 50]                   # eye = the actor's Location
    assert rows[0][4] == pb._deg_to_uu(90.0)               # yaw carried through as UU


def test_resolve_shots_missing_actor_is_none(monkeypatch):
    link = StatefulLink(actors={})
    _install_stateful(monkeypatch, link)
    rows = pb.resolve_shots([_shot_dict(at="Ghost", rot=[0.0, 0.0])])
    assert rows == [None]                                  # unresolved → None (caller fails loudly)


def test_resolve_shots_look_at_actor_pitches_up(monkeypatch):
    link = StatefulLink(actors={"Sky": (0, 0, 1000)})
    _install_stateful(monkeypatch, link)
    rows = pb.resolve_shots([_shot_dict(at=[0.0, 0.0, 0.0], look="Sky")])
    assert rows[0][3] == pb._deg_to_uu(89.9)               # look straight up → clamped to +89.9°


def test_list_actors_sampled(monkeypatch):
    link = StatefulLink(actors={"N%d" % i: (i, i, i) for i in range(10)})
    _install_stateful(monkeypatch, link)
    got = pb.list_actors("Engine.PathNode", sample=4)
    assert len(got) == 4 and all(len(t) == 4 for t in got)  # evenly-indexed 4 of 10


def test_main_list_mode_prints_actors(monkeypatch):
    link = StatefulLink(start="s", actors={"A": (1, 2, 3), "B": (4, 5, 6)})
    _install_stateful(monkeypatch, link)
    req = {"deliver": None, "stem": "s", "rebuild": False, "list_class": "Engine.PathNode"}
    monkeypatch.setattr(pb.sys, "stdin", io.StringIO(json.dumps(req)))
    outbuf = io.BytesIO()
    monkeypatch.setattr(pb.sys, "stdout", type("O", (), {"buffer": outbuf})())
    rc = pb.main()
    assert rc == 0 and outbuf.getvalue() == b"A 1 2 3\nB 4 5 6\n"    # plain lines, no PNG framing


def test_main_unresolved_at_actor_end_to_end(monkeypatch):
    link = StatefulLink(start="s", actors={"PathNode5": (10, 20, 30)})
    _install_stateful(monkeypatch, link)
    req = {"deliver": None, "stem": "s", "rebuild": False, "window_title": "deus ex",
           "window_exclude": [], "unresolved": [_shot_dict(at="PathNode5", rot=[0.0, 45.0])]}
    rc, data = _run_main(monkeypatch, req)
    assert rc == 0 and _frames(data) == [(True, b"PNG")]   # @actor resolved + posed + grabbed


def test_travel_3phase_reaches_target(monkeypatch):
    link = StatefulLink(start="UedPreviewBoot")
    _install_stateful(monkeypatch, link)
    pb.travel("08_nyc_bar")                                # must not raise
    assert link.level == "08_nyc_bar" and link.travels == 1


def test_travel_raises_if_never_reaches(monkeypatch):
    link = StatefulLink(start="UedPreviewBoot")
    link.sendall = lambda data: None                       # link never answers → phase-1 times out
    link._buf = b""
    _install_stateful(monkeypatch, link)
    clk = [0.0]                                             # fast fake clock so the 25s deadline is hit at once

    def _tick():
        clk[0] += 10.0
        return clk[0]
    monkeypatch.setattr(pb.time, "time", _tick)
    with pytest.raises(RuntimeError, match="no possessed link"):
        pb.travel("nope")


def test_main_three_shots_one_connection_skip_travel(monkeypatch):
    link = StatefulLink(start="copied__abc__dx")           # already on stem → NO travel
    _install_stateful(monkeypatch, link)
    req = {"deliver": None, "stem": "copied__abc__dx", "rebuild": False,
           "window_title": "deus ex", "window_exclude": [], "shots": [[0, 0, 0, 0, i] for i in range(3)]}
    rc, data = _run_main(monkeypatch, req)
    frames = _frames(data)
    assert rc == 0 and len(frames) == 3 and all(f[0] for f in frames) and link.travels == 0
    assert link.prep == 3                                  # all three posed on the ONE connection


def test_main_midstream_failure_stops_after_first(monkeypatch):
    link = StatefulLink(start="s", fail_prepare_after=1)   # shot 2 of 3 fails
    _install_stateful(monkeypatch, link)
    req = {"deliver": None, "stem": "s", "rebuild": False,
           "window_title": "deus ex", "window_exclude": [], "shots": [[0, 0, 0, 0, 0]] * 3}
    rc, data = _run_main(monkeypatch, req)
    frames = _frames(data)
    assert rc == 1 and frames[0][0] is True and frames[1][0] is False and len(frames) == 2


def test_cmd_ok_is_id_scoped(monkeypatch):
    """A STALE prior-request OK in the buffer must NOT count as THIS request's success (M1)."""
    class Sock:
        def settimeout(self, t):
            pass

        def sendall(self, d):
            rid = d.decode().strip().split(" ", 1)[0][1:]  # "#<rid>" → "<rid>"
            self._buf = ("#999 OK PrepareCamera\n#%s ERR nope\n" % rid).encode()

        def recv(self, n):
            b, self._buf = self._buf[:n], self._buf[n:]
            return b

        def close(self):
            pass
    pb._req = 0
    ok, lines = pb._cmd(Sock(), "PrepareCamera 0 0 0 0 0")
    assert ok is False                                     # this request ERR'd; #999's OK is stale


def test_resolve_shots_orbit_actor(monkeypatch):
    link = StatefulLink(actors={"Center": (0, 0, 0)})
    _install_stateful(monkeypatch, link)
    rows = pb.resolve_shots([_shot_dict(orbit="Center", radius=100.0, azimuth=0.0, elev=0.0)])
    assert rows[0] is not None and rows[0][:3] == [100, 0, 0]   # on +X of the centre at radius 100


def test_resolve_shots_asdict_json_roundtrip(monkeypatch):
    import dataclasses
    ps = pb.ps                                             # the baked shared shot model
    shot = ps.Shot(at=(1.0, 2.0, 3.0), rot=(0.0, 90.0))    # absolute --map shot also goes "unresolved"
    d = json.loads(json.dumps(dataclasses.asdict(shot)))   # tuples -> lists across the JSON wire
    link = StatefulLink(actors={})
    _install_stateful(monkeypatch, link)
    rows = pb.resolve_shots([d])
    assert rows[0][:3] == [1, 2, 3] and rows[0][4] == pb._deg_to_uu(90.0)


def test_resolve_shots_bad_dict_is_none(monkeypatch):
    _install_stateful(monkeypatch, StatefulLink())
    rows = pb.resolve_shots([{"at": [0, 0, 0], "bogus": 1}])   # unexpected key → TypeError → None (not a crash)
    assert rows == [None]


def test_list_actors_sampled_even_indices(monkeypatch):
    link = StatefulLink(actors={"N%d" % i: (i, 0, 0) for i in range(10)})
    _install_stateful(monkeypatch, link)
    names = [t[0] for t in pb.list_actors("X", sample=5)]
    assert names == ["N0", "N2", "N4", "N6", "N8"]         # evenly indexed (step 2), not "first 5"


def test_list_actors_unknown_class_raises(monkeypatch):
    class NoOk(StatefulLink):
        def sendall(self, data):
            rid = data.decode().strip().split(" ", 1)[0]
            self._buf += (rid + " ERR unknown-class\n").encode()
    _install_stateful(monkeypatch, NoOk())
    with pytest.raises(RuntimeError, match="unknown class"):
        pb.list_actors("Engine.Nope")


def test_main_list_mode_unknown_class_returns_2(monkeypatch):
    class NoOk(StatefulLink):
        def sendall(self, data):
            line = data.decode().strip()
            rid = line.split(" ", 1)[0]
            cmd = line.split(" ", 1)[1] if " " in line else ""
            if cmd.split(" ", 1)[0] == "ListActors":
                self._buf += (rid + " ERR unknown-class\n").encode()   # only ListActors errors
            else:
                super().sendall(data)                                  # level query etc. answer normally
    _install_stateful(monkeypatch, NoOk(start="s"))                    # already on stem → no travel
    req = {"deliver": None, "stem": "s", "rebuild": False, "list_class": "Engine.Nope"}
    monkeypatch.setattr(pb.sys, "stdin", io.StringIO(json.dumps(req)))
    outbuf = io.BytesIO()
    monkeypatch.setattr(pb.sys, "stdout", type("O", (), {"buffer": outbuf})())
    rc = pb.main()
    assert rc == 2 and outbuf.getvalue() == b""            # permanent-failure rc, no output
