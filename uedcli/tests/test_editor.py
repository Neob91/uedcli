# tests/test_editor.py
from unittest import mock

import pytest

from uedcli import editor as editormod
from uedcli.editor import editor_container


def _status_run(stdout):
    return mock.Mock(returncode=0, stdout=stdout, stderr="")


def test_wait_ready_ignores_the_unresolved_window_line_then_returns_on_a_real_handle(monkeypatch):
    # For the first seconds status prints `window=<unresolved...>` — a bare `window=` substring
    # check would false-positive and the next `exec` would fail "could not find an UnrealEd window".
    unresolved = "pid=36 alive=True display=:99\nwindow=<unresolved: could not find an UnrealEd window>"
    resolved = "pid=36 alive=True display=:99 window=29360129 name='Unreal Editor 2.2 for Deus Ex'"
    calls = iter([unresolved, unresolved, resolved])
    monkeypatch.setattr(editormod.subprocess, "run", lambda *a, **k: _status_run(next(calls)))
    monkeypatch.setattr(editormod.time, "sleep", lambda s: None)
    editormod._wait_ready("uned-x", timeout=10)                 # returns (no TimeoutError) once resolved


def test_wait_ready_times_out_if_the_window_never_resolves(monkeypatch):
    unresolved = "pid=36 alive=True display=:99\nwindow=<unresolved: could not find an UnrealEd window>"
    monkeypatch.setattr(editormod.subprocess, "run", lambda *a, **k: _status_run(unresolved))
    monkeypatch.setattr(editormod.time, "sleep", lambda s: None)
    clock = iter([0.0, 0.5, 1.0, 5.0, 11.0])
    monkeypatch.setattr(editormod.time, "monotonic", lambda: next(clock))
    with pytest.raises(TimeoutError, match="not ready within"):
        editormod._wait_ready("uned-x", timeout=10)


def test_editor_container_derives_from_the_uuid_dropping_the_slug():
    # A legacy `session/`-prefixed id is still accepted (prefix stripped); production now passes a bare uuid7.
    assert editor_container("session/0193abcd-0000-7000-8000-000000000001-downtown") == \
        "uned-0193abcd-0000-7000-8000-000000000001"


def test_editor_container_handles_no_slug_and_bare_id():
    assert editor_container("0193abcd-0000-7000-8000-000000000001") == \
        "uned-0193abcd-0000-7000-8000-000000000001"
    assert editor_container("0193abcd-0000-7000-8000-000000000001-downtown") == \
        "uned-0193abcd-0000-7000-8000-000000000001"


def test_ensure_editor_reuses_a_running_container(monkeypatch):
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-q"]:
            return mock.Mock(returncode=0, stdout="abc123\n")     # already running
        return mock.Mock(returncode=0, stdout="")
    monkeypatch.setattr(editormod.subprocess, "run", fake_run)
    monkeypatch.setattr(editormod, "_wait_ready", lambda c, t: None)
    container = editormod.ensure_editor("session/0193abcd-0000-7000-8000-000000000001",
                                        state_dir="/tmp/unused-state")
    assert container == "uned-0193abcd-0000-7000-8000-000000000001"
    assert not any(c[:3] == ["docker", "compose"] and "run" in c for c in calls)  # NOT re-created


def test_ensure_editor_creates_when_absent(monkeypatch):
    created = {}
    def fake_run(cmd, **kw):
        if cmd[:3] == ["docker", "ps", "-q"]:
            return mock.Mock(returncode=0, stdout="")             # not running
        if "run" in cmd:
            created["cmd"] = cmd
        return mock.Mock(returncode=0, stdout="")
    monkeypatch.setattr(editormod.subprocess, "run", fake_run)
    monkeypatch.setattr(editormod, "_wait_ready", lambda c, t: None)
    monkeypatch.setattr(editormod, "_write_engine_ini", lambda c, m, sd: f"/host/{c}.paths.ini")
    editormod.ensure_editor("session/0193abcd-0000-7000-8000-000000000001",
                            state_dir="/tmp/unused-state")
    assert "uned-0193abcd-0000-7000-8000-000000000001" in created["cmd"]   # named per session


def test_ensure_editor_mounts_no_resources_and_baseline_paths_when_mounts_none(monkeypatch):
    created = {}
    def fake_run(cmd, **kw):
        if cmd[:3] == ["docker", "ps", "-q"]:
            return mock.Mock(returncode=0, stdout="")
        if "run" in cmd:
            created["cmd"] = cmd
        return mock.Mock(returncode=0, stdout="")
    monkeypatch.setattr(editormod.subprocess, "run", fake_run)
    monkeypatch.setattr(editormod, "_wait_ready", lambda c, t: None)
    monkeypatch.setattr(editormod, "_write_engine_ini", lambda c, m, sd: f"/host/{c}.paths.ini")
    editormod.ensure_editor("0193abcd-0000-7000-8000-000000000001", mounts=None,
                            state_dir="/tmp/unused-state")
    cmd = created["cmd"]
    ctr = "uned-0193abcd-0000-7000-8000-000000000001"
    # engine ini bind-mounted PRE-LAUNCH read-write (entrypoint no longer touches Paths — the
    # `/deusex` sed block + the `UED_DEUSEX_ASSETS_DIR` stopgap were removed in asset-wiring Part C).
    assert f"/host/{ctr}.paths.ini:/opt/UED22/unrealtournament.ini" in cmd
    assert not any("UED_DEUSEX_ASSETS_DIR" in a for a in cmd)             # stopgap env is gone
    assert not any(":/resources/" in a for a in cmd)                      # no content mounts


def test_ensure_editor_adds_resource_mount_args_for_each_content_dir(monkeypatch):
    created = {}
    def fake_run(cmd, **kw):
        if cmd[:3] == ["docker", "ps", "-q"]:
            return mock.Mock(returncode=0, stdout="")
        if "run" in cmd:
            created["cmd"] = cmd
        return mock.Mock(returncode=0, stdout="")
    monkeypatch.setattr(editormod.subprocess, "run", fake_run)
    monkeypatch.setattr(editormod, "_wait_ready", lambda c, t: None)
    monkeypatch.setattr(editormod, "_write_engine_ini", lambda c, m, sd: f"/host/{c}.paths.ini")
    from uedcli.container_assets import resource_mounts
    mounts = resource_mounts(["/host/Textures", "/host/Maps"])
    editormod.ensure_editor("0193abcd-0000-7000-8000-000000000001", mounts=mounts,
                            state_dir="/tmp/unused-state")
    cmd = created["cmd"]
    flat = " ".join(cmd)
    assert "/host/Textures:/resources/r000:ro" in flat
    assert "/host/Maps:/resources/r001:ro" in flat


def test_replace_core_system_paths_is_byte_exact_and_crlf_preserving():
    base = (b"[FirstRun]\r\nX=1\r\n"
            b"[Core.System]\r\nSuppress=DevLoad\r\n"
            b"Paths=../UED22/*.u\r\nPaths=../Textures/*.utx\r\n"
            b"Suppress=DevMusic\r\n"
            b"[Engine.GameEngine]\r\nCacheSizeMegs=4\r\n")
    out = editormod.replace_core_system_paths(base, ["Paths=/stubs/*", "Paths=/opt/UED22/*",
                                                     "Paths=/resources/r000/*"])
    # New Paths block sits where the first old Paths was; CRLF everywhere; other keys byte-exact.
    assert out == (b"[FirstRun]\r\nX=1\r\n"
                   b"[Core.System]\r\nSuppress=DevLoad\r\n"
                   b"Paths=/stubs/*\r\nPaths=/opt/UED22/*\r\nPaths=/resources/r000/*\r\n"
                   b"Suppress=DevMusic\r\n"
                   b"[Engine.GameEngine]\r\nCacheSizeMegs=4\r\n")
    assert b"\r\n" in out and out.count(b"Paths=") == 3   # only the new set, nothing bare-LF


def test_replace_core_system_paths_appends_when_section_has_no_paths():
    base = b"[Core.System]\r\nSuppress=DevLoad\r\n[Next]\r\nY=2\r\n"
    out = editormod.replace_core_system_paths(base, ["Paths=/stubs/*"])
    assert out == b"[Core.System]\r\nSuppress=DevLoad\r\nPaths=/stubs/*\r\n[Next]\r\nY=2\r\n"


def test_replace_core_system_paths_last_section_no_paths_stays_wellformed():
    # [Core.System] is the LAST section and has no Paths= line, file ends in a trailing newline:
    # the block must land after the last real content line, CRLF-terminated, no stray blank line.
    base = b"[Core.System]\r\nSuppress=DevLoad\r\n"
    out = editormod.replace_core_system_paths(base, ["Paths=/stubs/*", "Paths=/opt/UED22/*"])
    assert out == b"[Core.System]\r\nSuppress=DevLoad\r\nPaths=/stubs/*\r\nPaths=/opt/UED22/*\r\n"


def test_replace_core_system_paths_no_section_leaves_bytes_untouched():
    base = b"[Only]\r\nZ=9\r\n"                     # no [Core.System] → returned unchanged (never corrupt)
    assert editormod.replace_core_system_paths(base, ["Paths=/stubs/*"]) == base


def test_write_engine_ini_crafts_paths_from_mounts_over_the_base_ini(tmp_path, monkeypatch):
    # The glue: read the baked base ini bytes → regenerate [Core.System] Paths from the mounts →
    # write byte-exact to a deterministic host path.
    base = tmp_path / "unrealtournament.ini"
    base.write_bytes(b"[Core.System]\r\nPaths=../UED22/*.u\r\nSavePath=../Save\r\n")
    monkeypatch.setattr(editormod, "_base_engine_ini_path", lambda: base)
    # A real content dir holding a .utx: per-ext Paths emit one line per (dir × present ext), so the
    # r000 line only appears because the dir actually holds a .utx (decisions.md 2026-07-14 12:00).
    tex = tmp_path / "Textures"
    tex.mkdir()
    (tex / "Foo.utx").write_bytes(b"x")
    from uedcli.container_assets import resource_mounts
    mounts = resource_mounts([str(tex)])
    written = editormod._write_engine_ini("uned-x", mounts, tmp_path)  # engine ini under tmp/tmp/
    data = open(written, "rb").read()
    assert data == (b"[Core.System]\r\n"
                    b"Paths=/stubs/*.u\r\nPaths=/opt/UED22/*.u\r\nPaths=/resources/r000/*.utx\r\n"
                    b"SavePath=../Save\r\n")


def test_stop_editor_removes_container_and_volume(monkeypatch, tmp_path):
    removed = []
    monkeypatch.setattr(editormod.subprocess, "run",
                        lambda cmd, **kw: removed.append(cmd) or mock.Mock(returncode=0, stdout=""))
    editormod.stop_editor("session/0193abcd-0000-7000-8000-000000000001", tmp_path / ".uedcli")
    flat = [" ".join(c) for c in removed]
    assert any("rm -f uned-0193abcd-0000-7000-8000-000000000001" in f for f in flat)
    assert any("volume rm" in f and "uned-wp-0193abcd-0000-7000-8000-000000000001" in f for f in flat)


def _ensure_editor_runner(created, reaps):
    """A `subprocess.run` fake for `ensure_editor` tests: `docker ps -q` → not running, records each
    `docker compose run` and `docker rm -f` invocation, everything else a benign success."""
    def fake_run(cmd, **kw):
        if cmd[:3] == ["docker", "ps", "-q"]:
            return mock.Mock(returncode=0, stdout="")          # not running → (re)create each spin
        if cmd[:3] == ["docker", "rm", "-f"]:
            reaps.append(cmd[3])                               # container name reaped
        if "run" in cmd and cmd[:2] == ["docker", "compose"]:
            created.append(cmd)
        return mock.Mock(returncode=0, stdout="")
    return fake_run


def test_ensure_editor_retries_after_a_readiness_timeout_then_succeeds(monkeypatch):
    # First readiness wait times out (crash-prone editor); ensure_editor reaps the wedged container,
    # re-spins, and the second wait succeeds — no error surfaces to the caller.
    created, reaps = [], []
    monkeypatch.setattr(editormod.subprocess, "run", _ensure_editor_runner(created, reaps))
    monkeypatch.setattr(editormod, "_write_engine_ini", lambda c, m, sd: f"/host/{c}.paths.ini")
    waits = iter([TimeoutError("boom"), None])                # timeout, then ready
    def fake_wait(c, t):
        r = next(waits)
        if isinstance(r, Exception):
            raise r
    monkeypatch.setattr(editormod, "_wait_ready", fake_wait)
    ctr = editormod.ensure_editor("0193abcd-0000-7000-8000-000000000010",
                                  state_dir="/tmp/unused-state")
    assert ctr == "uned-0193abcd-0000-7000-8000-000000000010"
    assert reaps == [ctr]                    # exactly one reap, between the failed and retried spin
    assert len(created) == 2                 # spun up twice (initial + retry)


def test_ensure_editor_raises_named_error_when_every_attempt_times_out(monkeypatch):
    # Every readiness wait times out: ensure_editor exhausts its bound and raises the CLEAR named
    # EditorNotReadyError (never a bare TimeoutError traceback), having reaped the container.
    created, reaps = [], []
    monkeypatch.setattr(editormod.subprocess, "run", _ensure_editor_runner(created, reaps))
    monkeypatch.setattr(editormod, "_write_engine_ini", lambda c, m, sd: f"/host/{c}.paths.ini")
    def always_timeout(c, t):
        raise TimeoutError("never ready")
    monkeypatch.setattr(editormod, "_wait_ready", always_timeout)
    with pytest.raises(editormod.EditorNotReadyError, match="not ready within"):
        editormod.ensure_editor("0193abcd-0000-7000-8000-000000000011",
                                state_dir="/tmp/unused-state", start_attempts=2)
    ctr = "uned-0193abcd-0000-7000-8000-000000000011"
    assert len(created) == 2                 # exactly start_attempts spin-ups, no more
    # A reap before each retry (1) plus a final reap on give-up (1) = 2 for start_attempts=2.
    assert reaps == [ctr, ctr]


def test_ensure_editor_no_retry_path_single_attempt(monkeypatch):
    # start_attempts=1: the single readiness wait times out → EditorNotReadyError with exactly ONE
    # spin-up and exactly ONE reap (the final give-up reap only; no pre-retry reap since there is no
    # retry). Pins the no-retry boundary of the bounded-retry loop.
    created, reaps = [], []
    monkeypatch.setattr(editormod.subprocess, "run", _ensure_editor_runner(created, reaps))
    monkeypatch.setattr(editormod, "_write_engine_ini", lambda c, m, sd: f"/host/{c}.paths.ini")
    def always_timeout(c, t):
        raise TimeoutError("never ready")
    monkeypatch.setattr(editormod, "_wait_ready", always_timeout)
    with pytest.raises(editormod.EditorNotReadyError, match="not ready within"):
        editormod.ensure_editor("0193abcd-0000-7000-8000-000000000012",
                                state_dir="/tmp/unused-state", start_attempts=1)
    ctr = "uned-0193abcd-0000-7000-8000-000000000012"
    assert len(created) == 1                 # exactly one spin-up, no retry
    assert reaps == [ctr]                     # only the final give-up reap (no pre-retry reap)


def test_ensure_editor_start_attempts_zero_clamps_to_one(monkeypatch):
    # `max(1, start_attempts)` clamps a 0 (or negative) request to a single attempt — same shape as
    # start_attempts=1: one spin-up, one final reap, EditorNotReadyError.
    created, reaps = [], []
    monkeypatch.setattr(editormod.subprocess, "run", _ensure_editor_runner(created, reaps))
    monkeypatch.setattr(editormod, "_write_engine_ini", lambda c, m, sd: f"/host/{c}.paths.ini")
    def always_timeout(c, t):
        raise TimeoutError("never ready")
    monkeypatch.setattr(editormod, "_wait_ready", always_timeout)
    with pytest.raises(editormod.EditorNotReadyError, match="not ready within"):
        editormod.ensure_editor("0193abcd-0000-7000-8000-000000000013",
                                state_dir="/tmp/unused-state", start_attempts=0)
    ctr = "uned-0193abcd-0000-7000-8000-000000000013"
    assert len(created) == 1                 # clamped to a single attempt
    assert reaps == [ctr]                     # one final give-up reap


def test_editor_not_ready_error_subclasses_timeout_and_os_error():
    # Load-bearing fact: dispatch.py needs NO change because EditorNotReadyError IS a TimeoutError,
    # so the existing top-level `(DriverError, TimeoutError)` handler catches it.
    # It is also an OSError subclass (TimeoutError subclasses OSError) — which is why dispatch
    # ordering matters. Pin both so a later refactor of the base class trips a red test.
    assert issubclass(editormod.EditorNotReadyError, TimeoutError)
    assert issubclass(editormod.EditorNotReadyError, OSError)


def test_ensure_editor_passes_stub_cache_env_for_the_compose_mount(monkeypatch, tmp_path):
    """The compose `/stubs` volume source is `${UEDCLI_STUB_CACHE:-…}` — ensure_editor must pass
    the resolved `config.stub_cache_root()` (which honors $UEDCLI_HOME) in the subprocess env, so
    a non-default home never mounts an empty default-path stub cache (board chore, 2026-07-18)."""
    from uedcli import config
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path / "custom-home"))
    seen = {}
    def fake_run(cmd, **kw):
        if cmd[:3] == ["docker", "ps", "-q"]:
            return mock.Mock(returncode=0, stdout="")
        if "run" in cmd:
            seen["env"] = kw.get("env")
        return mock.Mock(returncode=0, stdout="")
    monkeypatch.setattr(editormod.subprocess, "run", fake_run)
    monkeypatch.setattr(editormod, "_wait_ready", lambda c, t: None)
    monkeypatch.setattr(editormod, "_write_engine_ini", lambda c, m, sd: f"/host/{c}.paths.ini")
    editormod.ensure_editor("0193abcd-0000-7000-8000-000000000002",
                            state_dir="/tmp/unused-state")
    expect = str(config.stub_cache_root())
    assert seen["env"]["UEDCLI_STUB_CACHE"] == expect
    assert (tmp_path / "custom-home" / "cache" / "stubs").is_dir()   # mount source created
    # The env must be a SUPERSET of os.environ, never a clean env — compose needs PATH/HOME/
    # DOCKER_* to run at all (review fix: pin the {**os.environ, …} shape, 2026-07-18).
    import os as _os
    assert seen["env"]["PATH"] == _os.environ["PATH"]


# ── every docker call is BOUNDED (dev/docs/rules/background-work.md) ──────────────


def test_every_lifecycle_docker_call_passes_a_timeout(monkeypatch, tmp_path):
    """A `docker` subprocess with no `timeout=` parks the whole verb when dockerd hangs — and in
    `_wait_ready`'s case it does so INSIDE the readiness deadline loop, so the deadline can never
    expire and `ensure_editor`'s retry never fires. Pinned as a property of the module, so a new
    call site cannot slip through unbounded."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(kw)
        if cmd[:3] == ["docker", "ps", "-q"]:
            return mock.Mock(returncode=0, stdout="")             # not running → spin up
        return mock.Mock(returncode=0, stdout="alive=True window=29360129")

    monkeypatch.setattr(editormod.subprocess, "run", fake_run)
    monkeypatch.setattr(editormod.time, "sleep", lambda s: None)
    editormod.ensure_editor("0193abcd-0000-7000-8000-000000000001", state_dir=tmp_path)
    editormod.stop_editor("0193abcd-0000-7000-8000-000000000001", tmp_path)
    assert calls, "no docker call was made"
    for kw in calls:
        assert kw.get("timeout"), kw


def test_is_running_turns_a_hung_docker_ps_into_a_named_error(monkeypatch):
    import subprocess
    from uedcli.driver import DriverError
    monkeypatch.setattr(editormod.subprocess, "run",
                        mock.Mock(side_effect=subprocess.TimeoutExpired(cmd="docker ps",
                                                                        timeout=1)))
    with pytest.raises(DriverError, match="docker ps"):
        editormod._is_running("uned-x")


def test_reap_and_stop_swallow_a_hung_docker(monkeypatch, tmp_path):
    """Teardown runs from a `finally:`, so a wedged `docker rm` must not replace the real error
    with a hang — the timeout is swallowed, exactly like `preview_game.stop_game`."""
    import subprocess
    monkeypatch.setattr(editormod.subprocess, "run",
                        mock.Mock(side_effect=subprocess.TimeoutExpired(cmd="docker rm",
                                                                        timeout=1)))
    editormod._reap_container("uned-x")                            # must not raise
    editormod.stop_editor("0193abcd-0000-7000-8000-000000000001", tmp_path)   # must not raise


def test_wait_ready_treats_a_hung_probe_as_not_ready_and_still_times_out(monkeypatch):
    """A `docker exec` that never answers is "not ready yet", not an error — but it must not stop
    the deadline from being reached, which is exactly what an unbounded call did."""
    import subprocess
    monkeypatch.setattr(editormod.subprocess, "run",
                        mock.Mock(side_effect=subprocess.TimeoutExpired(cmd="docker exec",
                                                                        timeout=1)))
    monkeypatch.setattr(editormod.time, "sleep", lambda s: None)
    clock = iter([0.0, 0.5, 1.0, 11.0])
    monkeypatch.setattr(editormod.time, "monotonic", lambda: next(clock))
    with pytest.raises(TimeoutError, match="not ready within"):
        editormod._wait_ready("uned-x", timeout=10)
