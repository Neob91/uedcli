"""Offline tests for `preview_game` — the `--game` backend host side. Every container/
link/materialize seam is mocked; nothing here boots docker (the live path is the SP-1..6
spike, spec §8)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from uedcli import preview_game as pg
from uedcli.builders import cube, make_brush_actor
from uedcli.model import Actor, Level
from uedcli.preview_shots import parse_shot


def _level(*actors):
    lvl = Level()
    for a in actors:
        lvl.actors[a.name] = a
        lvl.order.append(a.name)
    return lvl


def _start(name):
    return Actor(name=name, cls="Engine.PlayerStart",
                 location=(Decimal(0), Decimal(0), Decimal(0)))


# ----------------------------------------------------------------- substrate table


def test_unknown_game_named_error():
    with pytest.raises(pg.GamePreviewError, match="game 'quake'.*substrate"):
        pg._substrate_row("quake")


def test_deusex_row_present():
    row = pg._substrate_row("deusex")
    assert row["exe"] == "DeusEx.exe" and row["boot_map"]


# ----------------------------------------------------------------- delivered-map naming (D5)


def _proj(tmp_path):
    return SimpleNamespace(root=str(tmp_path), game="deusex", paths="")


def _resources(*, dirs=(), schema=None):
    return pg.MaterializeResources(composed_dirs=list(dirs), schema_resolver=schema)


class _Provider:
    """A counting zero-argument resource provider — records whether the cache-miss materialize
    path actually resolved the project inputs (a cache hit / `--map` must leave `calls == 0`)."""

    def __init__(self, res=None):
        self.res = res if res is not None else _resources()
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.res


def _never_provider():
    raise AssertionError("resource provider must not be invoked")


def _mat_ok(monkeypatch, body=b"m"):
    """Wire a fake run_materialize that writes `body`; the composed dirs/schema now arrive through the
    provider, so nothing here patches `dispatch`."""
    hits = []

    def fake(**kw):
        hits.append(kw)
        Path(kw["out_path"]).write_bytes(body)
        return SimpleNamespace(rc=0, message="ok")

    monkeypatch.setattr("uedcli.apply.run_materialize", fake)
    return hits


def test_compose_stem_dotfree_prefixed_lowercased():
    s = pg._compose_stem("materialized", "MyLevel", "abcdef123456")
    assert s == "materialized__mylevel__abcdef123456"
    assert "." not in s and s == s.lower()


def test_compose_stem_caps_length_keeping_hash_and_nonce():
    s = pg._compose_stem("materialized", "x" * 300, "abcdef123456", "nonce123")
    assert len(s) <= pg.STEM_MAX
    assert s.endswith("__abcdef123456__nonce123")          # hash+nonce always survive
    assert "." not in s and s == s.lower()


def test_materialized_dx_hash_named_and_reuses_fresh(tmp_path, monkeypatch):
    lvl = _level(_start("Start"))
    proj = _proj(tmp_path)
    _mat_ok(monkeypatch)
    miss = _Provider()
    first = pg.materialized_dx(proj, "lvl", lvl, rebuild=False, provide_resources=miss)
    assert first.name.startswith("materialized__lvl__") and first.suffix == ".dx"
    assert "." not in first.stem                            # dot-free stem
    assert miss.calls == 1                                  # cache MISS resolved the inputs once
    # a second call reuses (materialize must NOT run again, and the provider stays untouched)
    monkeypatch.setattr("uedcli.apply.run_materialize",
                        lambda **kw: (_ for _ in ()).throw(AssertionError("rebuilt!")))
    hit = _Provider()
    assert pg.materialized_dx(proj, "lvl", lvl, rebuild=False, provide_resources=hit) == first
    assert hit.calls == 0                                   # cache HIT never invokes the provider


def test_materialized_dx_rebuild_forces_fresh_nonced_name(tmp_path, monkeypatch):
    lvl = _level(_start("Start"))
    proj = _proj(tmp_path)
    _mat_ok(monkeypatch)
    first = pg.materialized_dx(proj, "lvl", lvl, rebuild=False, provide_resources=_Provider())
    hits = _mat_ok(monkeypatch, b"fresh")
    second = pg.materialized_dx(proj, "lvl", lvl, rebuild=True, provide_resources=_Provider())
    assert hits                                             # materialized despite the cache
    assert second != first and second.read_bytes() == b"fresh"   # nonce'd distinct name


def test_materialized_dx_prunes_to_keep(tmp_path, monkeypatch):
    import os
    lvl = _level(_start("Start"))
    proj = _proj(tmp_path)
    _mat_ok(monkeypatch)
    d = pg._preview_dir(proj)
    for i in range(pg.PREVIEW_KEEP + 3):                    # extra siblings, distinctly OLDER
        f = d / f"materialized__old{i}__000000000000.dx"
        f.write_bytes(b"x")
        os.utime(f, (1000 + i, 1000 + i))                  # the fresh materialize is unambiguously newest
    pg.materialized_dx(proj, "lvl", lvl, rebuild=True, provide_resources=_Provider())
    assert len(list(d.glob("materialized__*"))) <= pg.PREVIEW_KEEP


def test_copied_map_hash_named_dx_and_unr(tmp_path):
    proj = _proj(tmp_path)
    src = tmp_path / "MyMap.dx"
    src.write_bytes(b"hello")
    got = pg.copied_map(proj, str(src))
    assert got.name.startswith("copied__") and got.suffix == ".dx"
    assert got.read_bytes() == b"hello" and "." not in got.stem
    unr = tmp_path / "Other.unr"
    unr.write_bytes(b"world")
    assert pg.copied_map(proj, str(unr)).suffix == ".unr"   # .unr accepted (D7)


def test_copied_map_rejects_non_map_ext(tmp_path):
    src = tmp_path / "notamap.txt"
    src.write_bytes(b"x")
    with pytest.raises(pg.GamePreviewError, match=".dx or .unr"):
        pg.copied_map(_proj(tmp_path), str(src))


def test_materialize_failure_is_named(tmp_path, monkeypatch):
    lvl = _level(_start("Start"))
    monkeypatch.setattr("uedcli.apply.run_materialize",
                        lambda **kw: SimpleNamespace(rc=2, message="editor wedge"))
    with pytest.raises(pg.GamePreviewError, match="editor wedge"):
        pg.materialized_dx(_proj(tmp_path), "lvl", lvl, rebuild=False,
                           provide_resources=_Provider())


# ----------------------------------------------------------------- D8 pre-check


def test_trunk_playerstart_precheck():
    assert pg.trunk_has_playerstart(_level(_start("S")))
    room = make_brush_actor("Room", cube(64, 64, 64), csg="subtract")
    assert not pg.trunk_has_playerstart(_level(room))


def test_render_shots_no_playerstart_errors_before_any_boot(tmp_path, monkeypatch):
    room = make_brush_actor("Room", cube(64, 64, 64), csg="subtract")
    monkeypatch.setattr(pg, "ensure_image",
                        lambda *a: (_ for _ in ()).throw(AssertionError("built image")))
    monkeypatch.setattr(pg, "acquire_warm_container",
                        lambda *a: (_ for _ in ()).throw(AssertionError("booted")))
    monkeypatch.setattr(pg, "_acquire_lock",
                        lambda: (_ for _ in ()).throw(AssertionError("locked")))
    with pytest.raises(pg.GamePreviewError, match="no PlayerStart"):
        pg.render_shots(shots=[parse_shot("at:0,0,0;rot:0,0")], out_dir=tmp_path,
                        size=(320, 240), project=_proj(tmp_path), user_config=object(),
                        game="deusex", provide_resources=_never_provider,   # refused before any resolve
                        level=_level(room), level_name="lvl")


# ----------------------------------------------------------------- @actor with --map (game-resolved)


def test_map_actor_shots_go_unresolved_to_batch(monkeypatch, tmp_path):
    """`@actor` poses with --map are NO LONGER rejected — they pass through UNRESOLVED so the batch
    resolves them against the running game (retail maps have no trunk)."""
    dx = tmp_path / "m.dx"
    dx.write_bytes(b"X")
    cap = {}
    _install_render(monkeypatch, cap)
    n = pg.render_shots(
        shots=[parse_shot("at:@PathNode3;rot:0,90"), parse_shot("orbit:@K;radius:5;azimuth:0")],
        out_dir=tmp_path / "o", size=(320, 240), project=_proj(tmp_path), user_config=object(),
        game="deusex", provide_resources=_never_provider, map_path=str(dx))   # --map: never resolves
    assert n == 2 and "unresolved" in cap["req"] and "shots" not in cap["req"]
    assert cap["req"]["unresolved"][0]["at"] == "PathNode3"      # @actor forwarded, not resolved host-side
    assert cap["req"]["unresolved"][1]["orbit"] == "K"


def test_missing_map_file_named(tmp_path, monkeypatch):
    with pytest.raises(pg.GamePreviewError, match="--map file not found"):
        pg.render_shots(shots=[parse_shot("at:0,0,0;rot:0,0")], out_dir=tmp_path,
                        size=(320, 240), project=_proj(tmp_path), user_config=object(),
                        game="deusex", provide_resources=_never_provider,
                        map_path=str(tmp_path / "nope.dx"))


def test_no_trunk_and_no_map_named(tmp_path):
    with pytest.raises(pg.GamePreviewError, match="no trunk level"):
        pg.render_shots(shots=[parse_shot("at:0,0,0;rot:0,0")], out_dir=tmp_path,
                        size=(320, 240), project=_proj(tmp_path), user_config=object(),
                        game="deusex", provide_resources=_never_provider)


# ----------------------------------------------------------------- toolchain / image


def test_missing_toolchain_named(tmp_path, monkeypatch):
    monkeypatch.setattr(pg.Path, "is_file", lambda self: False)
    with pytest.raises(pg.GamePreviewError, match="UCC toolchain is not provisioned"):
        pg.ensure_image(_proj(tmp_path), object(), pg.SUBSTRATES["deusex"])


def test_game_system_dir_requires_exe(tmp_path):
    (tmp_path / "textures").mkdir()
    with pytest.raises(pg.GamePreviewError, match="DeusEx.exe"):
        pg._game_system_dir([str(tmp_path / "textures")], pg.SUBSTRATES["deusex"])
    sysdir = tmp_path / "System"
    sysdir.mkdir()
    (sysdir / "DeusEx.exe").write_bytes(b"MZ")
    assert pg._game_system_dir([str(sysdir)], pg.SUBSTRATES["deusex"]) == str(sysdir)


# ----------------------------------------------------------------- one-exec batch drive (§2/§6)
# Travel/link/xgrab now live IN the container batch script (preview_batch.py, tested separately);
# the host side is ONE `docker inspect` (reuse gate) + ONE `docker exec` (run_batch) + the framed
# PNG parse + reboot-retry. Every docker seam is mocked.


def test_inspect_parses_running_and_label(monkeypatch):
    monkeypatch.setattr(pg, "_run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout="true\tFP123", stderr=""))
    assert pg._inspect("c") == (True, "FP123")


def test_inspect_none_when_absent(monkeypatch):
    monkeypatch.setattr(pg, "_run",
                        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="No such object"))
    assert pg._inspect("c") is None


def test_parse_frames_roundtrip():
    import json as _json
    import struct as _struct
    blob = (_json.dumps({"ok": True}).encode() + b"\n" + _struct.pack(">I", 3) + b"PNG"
            + _json.dumps({"ok": True}).encode() + b"\n" + _struct.pack(">I", 2) + b"GO")
    assert pg._parse_frames(blob, 2) == [b"PNG", b"GO"]


def test_parse_frames_ok_false_raises():
    import json as _json
    blob = _json.dumps({"ok": False, "err": "no window"}).encode() + b"\n"
    with pytest.raises(pg.GamePreviewError, match="no window"):
        pg._parse_frames(blob, 1)


def test_parse_frames_short_count_raises():
    import json as _json
    import struct as _struct
    blob = _json.dumps({"ok": True}).encode() + b"\n" + _struct.pack(">I", 3) + b"PNG"
    with pytest.raises(pg.GamePreviewError, match="1 of 2"):     # asked 2, got 1 (L1)
        pg._parse_frames(blob, 2)


def test_parse_frames_malformed_is_named():
    with pytest.raises(pg.GamePreviewError, match="malformed"):  # garbage → named, not traceback
        pg._parse_frames(b"not json\n\x00\x00", 1)


# ----------------------------------------------------------------- reuse gate (one inspect)


class _Warm:
    """Fake warm-container state driven through the mocked docker helpers.
    up: None = no such container; True/False = exists, running or not."""
    def __init__(self, up=None, fp="FP", pinned=False):
        self.up, self.fp, self.pinned = up, fp, pinned
        self.booted = self.stopped = 0


def _install_warm(monkeypatch, w, tmp_path):
    monkeypatch.setattr(pg, "_fingerprint", lambda *a, **k: "FP")
    monkeypatch.setattr(pg, "_preview_dir", lambda p: tmp_path)
    monkeypatch.setattr("uedcli.container_assets.resource_mounts", lambda d: [])
    monkeypatch.setattr(pg.config, "composed_search_dirs", lambda p, u: [])
    monkeypatch.setattr(pg, "_inspect", lambda n: None if w.up is None else (w.up, w.fp))
    monkeypatch.setattr(pg, "_is_pinned", lambda n: w.pinned)
    monkeypatch.setattr(pg, "_novnc", lambda n: "1")

    def boot(name, fp, *a):
        w.booted += 1; w.up = True; w.fp = fp; w.pinned = False
    monkeypatch.setattr(pg, "_boot_warm", boot)

    def stop(n):
        w.stopped += 1; w.up = None
    monkeypatch.setattr(pg, "stop_game", stop)
    monkeypatch.setattr(pg, "_pin", lambda n: setattr(w, "pinned", True))


def _acq(tmp_path):
    return pg.acquire_warm_container(_proj(tmp_path), object(), pg.SUBSTRATES["deusex"], (640, 480))


def test_acquire_boots_fresh_when_absent(monkeypatch, tmp_path):
    w = _Warm(up=None); _install_warm(monkeypatch, w, tmp_path)
    name, _ = _acq(tmp_path)
    assert w.booted == 1 and w.stopped == 0 and name == pg._warm_name()


def test_acquire_reuses_on_fingerprint_match(monkeypatch, tmp_path):
    w = _Warm(up=True, fp="FP"); _install_warm(monkeypatch, w, tmp_path)
    _acq(tmp_path)
    assert w.booted == 0 and w.stopped == 0                 # reused — the whole hot path


def test_acquire_reboots_on_fingerprint_mismatch(monkeypatch, tmp_path):
    w = _Warm(up=True, fp="OLD", pinned=False); _install_warm(monkeypatch, w, tmp_path)
    _acq(tmp_path)
    assert w.stopped == 1 and w.booted == 1


def test_acquire_reboots_when_exists_but_stopped(monkeypatch, tmp_path):
    w = _Warm(up=False, fp="FP"); _install_warm(monkeypatch, w, tmp_path)
    _acq(tmp_path)
    assert w.stopped == 1 and w.booted == 1


def test_acquire_pinned_mismatch_errors(monkeypatch, tmp_path):
    w = _Warm(up=True, fp="OLD", pinned=True); _install_warm(monkeypatch, w, tmp_path)
    with pytest.raises(pg.GamePreviewError, match="pinned"):
        _acq(tmp_path)
    assert w.stopped == 0                                   # never clobbers a pinned other-config


def test_acquire_lock_timeout_named(monkeypatch, tmp_path):
    import fcntl
    import os
    monkeypatch.setattr(pg, "WARM_LOCK_TIMEOUT_S", 0)
    # The lock now lives under config._user_home() → honors $UEDCLI_HOME (spec 2026-07-17 §5);
    # point it at a tmp home and pre-hold the flock there.
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    held = os.open(str(tmp_path / "home" / "game-preview.lock"), os.O_RDWR | os.O_CREAT)
    fcntl.flock(held, fcntl.LOCK_EX)
    try:
        with pytest.raises(pg.GamePreviewError, match="lock"):
            pg._acquire_lock()
    finally:
        fcntl.flock(held, fcntl.LOCK_UN); os.close(held)


def test_fingerprint_deterministic_and_size_sensitive(monkeypatch, tmp_path):
    monkeypatch.setattr(pg, "_image_id", lambda: "img")
    monkeypatch.setattr(pg, "_overlay_stat", lambda p, u: [])
    a = pg._fingerprint(["s:d"], (640, 480), _proj(tmp_path), object())
    b = pg._fingerprint(["s:d"], (640, 480), _proj(tmp_path), object())
    c = pg._fingerprint(["s:d"], (800, 600), _proj(tmp_path), object())
    assert a == b and a != c


# ----------------------------------------------------------------- delivered-map naming (retained)


def test_compose_stem_empty_and_nonalnum_ident():
    assert pg._compose_stem("materialized", "", "abc") == "materialized__x__abc"
    assert pg._compose_stem("materialized", "!!!", "abc") == "materialized__x__abc"


def test_compose_stem_room_lt1_is_loud_error(monkeypatch):
    monkeypatch.setattr(pg, "STEM_MAX", 10)                 # < prefix+hash overhead
    with pytest.raises(pg.GamePreviewError, match="budget exhausted"):
        pg._compose_stem("materialized", "lvl", "abcdef123456")


def test_prune_prefix_protects_current_even_if_oldest(tmp_path):
    import os
    files = []
    for i in range(pg.PREVIEW_KEEP + 3):
        f = tmp_path / f"materialized__x{i}__000000000000.dx"; f.write_bytes(b"x"); files.append(f)
    oldest = files[0]; os.utime(oldest, (1, 1))
    pg._prune_prefix(tmp_path, "materialized", protect=oldest)
    assert oldest.exists()


def test_copied_map_dx_and_unr_get_distinct_stems(tmp_path):
    proj = _proj(tmp_path)
    (tmp_path / "a.dx").write_bytes(b"SAME")
    (tmp_path / "a.unr").write_bytes(b"SAME")               # byte-identical, different ext
    p1 = pg.copied_map(proj, str(tmp_path / "a.dx"))
    p2 = pg.copied_map(proj, str(tmp_path / "a.unr"))
    assert p1.stem != p2.stem and p1 != p2 and "." not in p1.stem


# ----------------------------------------------------------------- render_shots (one-exec drive)


def _install_render(monkeypatch, captured):
    monkeypatch.setattr(pg, "ensure_image", lambda *a, **k: None)
    monkeypatch.setattr(pg, "_acquire_lock", lambda: -1)
    monkeypatch.setattr(pg, "_release_lock", lambda fd: None)
    monkeypatch.setattr(pg, "acquire_warm_container", lambda *a, **k: ("c", "1"))

    def run_batch(name, req):
        captured["req"] = req
        return [b"png"] * len(req.get("shots") or req.get("unresolved") or [])
    monkeypatch.setattr(pg, "run_batch", run_batch)


def test_render_shots_pitch_clamped_and_uu_in_request(monkeypatch, tmp_path):
    """The batch request carries UU ints; host clamps pitch to ±89.9° (the engine's own clamp
    picks the wrong pole headless — spec §3)."""
    lvl = _level(_start("Start"))
    dxfile = tmp_path / "materialized__lvl__000000000000.dx"; dxfile.write_bytes(b"x")
    monkeypatch.setattr(pg, "materialized_dx", lambda *a, **k: dxfile)
    cap = {}
    _install_render(monkeypatch, cap)
    n = pg.render_shots(shots=[parse_shot("at:10,20,30;rot:-17294,32768")], out_dir=tmp_path / "o",  # UU in → -95° (clamps), 180°
                        size=(320, 240), project=_proj(tmp_path), user_config=object(),
                        game="deusex", provide_resources=_never_provider,   # materialized_dx is mocked
                        level=lvl, level_name="lvl")
    from uedcli.rotation import deg_to_uu
    assert n == 1
    x, y, z, pitch, yaw = cap["req"]["shots"][0]
    assert [x, y, z] == [10, 20, 30]
    assert pitch == deg_to_uu(-89.9) and yaw == deg_to_uu(180)      # clamped, in UU
    assert cap["req"]["deliver"] == dxfile.name and cap["req"]["stem"] == dxfile.stem


def test_render_shots_trunk_cache_miss_invokes_provider(monkeypatch, tmp_path):
    """A trunk preview with no cached map resolves the project inputs THROUGH the threaded provider
    (never a reach-back into dispatch) and feeds them to run_materialize."""
    lvl = _level(_start("Start"))
    hits = _mat_ok(monkeypatch)                              # real materialized_dx → run_materialize
    cap = {}
    _install_render(monkeypatch, cap)
    prov = _Provider(_resources(dirs=["/g/Textures"], schema="RESOLVER"))
    n = pg.render_shots(shots=[parse_shot("at:0,0,0;rot:0,0")], out_dir=tmp_path / "o",
                        size=(320, 240), project=_proj(tmp_path), user_config=object(),
                        game="deusex", provide_resources=prov, level=lvl, level_name="lvl")
    assert n == 1 and prov.calls == 1                        # cache miss → provider invoked once
    assert hits[0]["search_dirs"] == ["/g/Textures"]
    assert hits[0]["schema_resolver"] == "RESOLVER"          # threaded straight into materialize


def test_render_shots_unr_map_end_to_end(monkeypatch, tmp_path):
    unr = tmp_path / "m.unr"; unr.write_bytes(b"UNR")
    cap = {}
    _install_render(monkeypatch, cap)
    n = pg.render_shots(shots=[parse_shot("at:0,0,0;rot:0,0")], out_dir=tmp_path / "o",
                        size=(320, 240), project=_proj(tmp_path), user_config=object(),
                        game="deusex", provide_resources=_never_provider, map_path=str(unr))
    assert n == 1 and cap["req"]["deliver"].endswith(".unr") and (tmp_path / "o" / "shot-01.png").exists()


def test_render_shots_reboot_retry_then_succeeds(monkeypatch, tmp_path):
    dx = tmp_path / "m.dx"; dx.write_bytes(b"X")
    calls = {"n": 0, "stopped": 0}
    monkeypatch.setattr(pg, "ensure_image", lambda *a, **k: None)
    monkeypatch.setattr(pg, "_acquire_lock", lambda: -1)
    monkeypatch.setattr(pg, "_release_lock", lambda fd: None)
    monkeypatch.setattr(pg, "acquire_warm_container", lambda *a, **k: ("c", "1"))
    monkeypatch.setattr(pg, "stop_game", lambda n: calls.__setitem__("stopped", calls["stopped"] + 1))

    def run_batch(name, req):
        calls["n"] += 1
        if calls["n"] == 1:
            raise pg.GamePreviewError("wedged")
        return [b"png"]
    monkeypatch.setattr(pg, "run_batch", run_batch)
    n = pg.render_shots(shots=[parse_shot("at:0,0,0;rot:0,0")], out_dir=tmp_path / "o",
                        size=(320, 240), project=_proj(tmp_path), user_config=object(),
                        game="deusex", provide_resources=_never_provider, map_path=str(dx))
    assert n == 1 and calls["n"] == 2 and calls["stopped"] == 1     # rebooted once, then ok


# ----------------------------------------------------------------- actor-relative host wiring (§)


def test_first_batch_error_extracts_stdout_err():
    import json as _j
    blob = _j.dumps({"ok": False, "err": "actor not found (unresolved @actor pose)"}).encode() + b"\n"
    assert "actor not found" in pg._first_batch_error(blob)
    assert pg._first_batch_error(_j.dumps({"ok": True}).encode() + b"\n") == ""
    assert pg._first_batch_error(b"not json at all") == ""


def test_run_batch_surfaces_actor_not_found_from_stdout(monkeypatch):
    import json as _j
    frame = _j.dumps({"ok": False, "err": "actor not found (unresolved @actor pose)"}).encode() + b"\n"
    monkeypatch.setattr(pg, "_exec_batch",
                        lambda n, r, t: SimpleNamespace(returncode=1, stdout=frame, stderr=b""))
    with pytest.raises(pg.GamePreviewError, match="actor not found"):     # not "no output" (H1/H2)
        pg.run_batch("c", {"unresolved": [{}]})


def test_render_shots_actor_not_found_does_not_reboot(monkeypatch, tmp_path):
    """A bad @actor fails LOUD — the host must NOT burn the reboot budget on it (H2)."""
    dx = tmp_path / "m.dx"; dx.write_bytes(b"X")
    calls = {"n": 0, "stopped": 0}
    monkeypatch.setattr(pg, "ensure_image", lambda *a, **k: None)
    monkeypatch.setattr(pg, "_acquire_lock", lambda: -1)
    monkeypatch.setattr(pg, "_release_lock", lambda fd: None)
    monkeypatch.setattr(pg, "acquire_warm_container", lambda *a, **k: ("c", "1"))
    monkeypatch.setattr(pg, "stop_game", lambda n: calls.__setitem__("stopped", calls["stopped"] + 1))

    def run_batch(name, req):
        calls["n"] += 1
        raise pg.GamePreviewError("preview batch failed: actor not found (unresolved @actor pose)")
    monkeypatch.setattr(pg, "run_batch", run_batch)
    with pytest.raises(pg.GamePreviewError, match="actor not found"):
        pg.render_shots(shots=[parse_shot("at:@Ghost;rot:0,0")], out_dir=tmp_path / "o",
                        size=(320, 240), project=_proj(tmp_path), user_config=object(),
                        game="deusex", provide_resources=_never_provider, map_path=str(dx))
    assert calls["n"] == 1 and calls["stopped"] == 0            # failed once, NO reboot


def test_host_list_actors_returns_stdout(monkeypatch, tmp_path):
    cp = tmp_path / "copied__x__dx.dx"; cp.write_bytes(b"X")
    monkeypatch.setattr(pg, "copied_map", lambda p, m: cp)
    monkeypatch.setattr(pg, "ensure_image", lambda *a, **k: None)
    monkeypatch.setattr(pg, "_acquire_lock", lambda: -1)
    monkeypatch.setattr(pg, "_release_lock", lambda fd: None)
    monkeypatch.setattr(pg, "acquire_warm_container", lambda *a, **k: ("c", "1"))
    monkeypatch.setattr(pg, "_exec_batch",
                        lambda n, r, t: SimpleNamespace(returncode=0, stdout=b"PathNode0 1 2 3\n",
                                                        stderr=b""))
    out = pg.list_actors(project=_proj(tmp_path), user_config=object(), game="deusex",
                         map_path="x.dx", cls="Engine.PathNode", sample=0)
    assert out == "PathNode0 1 2 3\n"


def test_host_list_actors_never_raw_traceback(monkeypatch, tmp_path):
    monkeypatch.setattr(pg, "copied_map",
                        lambda p, m: (_ for _ in ()).throw(FileNotFoundError("gone")))
    with pytest.raises(pg.GamePreviewError):                    # not a raw FileNotFoundError (M1)
        pg.list_actors(project=_proj(tmp_path), user_config=object(), game="deusex",
                       map_path="x.dx", cls="Engine.PathNode", sample=0)


def test_resolve_all_trunk_at_actor_still_host_side(monkeypatch):
    """Trunk @actor resolution (the 'unchanged' path) must keep working host-side (M4)."""
    lvl = _level(_start("Spawn"))
    monkeypatch.setattr("uedcli.preview_native.actor_aim_point", lambda level, n: (5, 6, 7))
    rs = pg._resolve_all([parse_shot("at:@Spawn;rot:0,8192")], lvl)   # UU in → yaw 45°
    assert rs[0].eye == (5, 6, 7) and rs[0].yaw == 45.0


def test_host_list_actors_unknown_class_no_reboot(monkeypatch, tmp_path):
    cp = tmp_path / "copied__x__dx.dx"; cp.write_bytes(b"X")
    calls = {"n": 0, "stopped": 0}
    monkeypatch.setattr(pg, "copied_map", lambda p, m: cp)
    monkeypatch.setattr(pg, "ensure_image", lambda *a, **k: None)
    monkeypatch.setattr(pg, "_acquire_lock", lambda: -1)
    monkeypatch.setattr(pg, "_release_lock", lambda fd: None)
    monkeypatch.setattr(pg, "acquire_warm_container", lambda *a, **k: ("c", "1"))
    monkeypatch.setattr(pg, "stop_game", lambda n: calls.__setitem__("stopped", calls["stopped"] + 1))

    def _exec(n, r, t):
        calls["n"] += 1
        return SimpleNamespace(returncode=2, stdout=b"", stderr=b"ListActors 'Engine.Nope' failed (unknown class?)")
    monkeypatch.setattr(pg, "_exec_batch", _exec)
    with pytest.raises(pg.GamePreviewError, match="unknown class"):
        pg.list_actors(project=_proj(tmp_path), user_config=object(), game="deusex",
                       map_path="x.dx", cls="Engine.Nope", sample=0)
    assert calls["n"] == 1 and calls["stopped"] == 0       # rc 2 = permanent → NO reboot
