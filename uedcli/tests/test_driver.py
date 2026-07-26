import struct
from unittest import mock

import pytest

from uedcli import driver as _driver
from uedcli.driver import Driver, DriverError, package_header_problem
from uedcli.tests.conftest import install_system_root


def test_exec_shells_out_to_wine_ctl():
    d = Driver(container="test-ctr")
    with mock.patch("uedcli.driver.subprocess.run") as run:
        run.return_value = mock.Mock(stdout="", returncode=0)
        d.exec("MAP GRID X=1 Y=1 Z=1")
    cmd = run.call_args[0][0]
    assert cmd[:3] == ["docker", "exec", "test-ctr"]
    assert "MAP GRID X=1 Y=1 Z=1" in cmd


def test_set_grid_one_issues_map_grid():
    d = Driver(container="test-ctr")
    with mock.patch.object(d, "exec") as ex:
        d.set_grid(1, 1, 1)
    ex.assert_called_once_with("MAP GRID X=1 Y=1 Z=1")


def test_map_importadd_uses_z_drive_path():
    d = Driver(container="test-ctr")
    with mock.patch.object(d, "exec") as ex:
        d.map_importadd("/repo/Temp/x.t3d")
    assert ex.call_args[0][0] == r"MAP IMPORTADD FILE=Z:\repo\Temp\x.t3d"


def test_screenshot_shoots_into_work_then_cps_out_to_the_host_path():
    d = Driver(container="test-ctr")
    calls = []

    def fake_run(cmd, *a, **kw):
        calls.append(cmd)
        return mock.Mock(stdout="", returncode=0, stderr="")

    # Patch the subprocess MODULE's run so xfer.cp_out/remove (same shared module) is caught too.
    with mock.patch("uedcli.driver.subprocess.run", autospec=True, side_effect=fake_run):
        d.screenshot("/host/out/shot.png")

    shot = next(c for c in calls if "shot" in c)              # wine_ctl shot <work>
    work = shot[-1]
    assert work.startswith("/work/") and work.endswith(".png")
    # the /work png was docker cp'd OUT to the host destination
    assert any(c[:2] == ["docker", "cp"] and c[2] == f"test-ctr:{work}"
               and c[3] == "/host/out/shot.png" for c in calls)
    # and THAT /work png was cleaned up (not merely some rm -rf)
    assert any(c[:3] == ["docker", "exec", "test-ctr"] and c[3:5] == ["rm", "-rf"] and work in c
               for c in calls)


def test_map_load_dx_issues_map_load_with_z_path():
    from unittest import mock
    from uedcli.driver import Driver
    d = Driver(container="c")
    with mock.patch.object(d, "exec", autospec=True) as ex:
        d.map_load_dx("/repo/Maps/downtown.dx")
    ex.assert_called_once_with("MAP LOAD FILE=Z:\\repo\\Maps\\downtown.dx")


# --- map_save: finished vs stalled vs container-dead -------------------------------------------
#
# These exercise the three outcomes `map_save` must keep apart, at the REAL default timeout/poll/
# settle values. Two things make that possible without a slow test:
#   * `_FakeClock` — time only moves when the driver SLEEPS, so a 600 s poll loop costs nothing and
#     the settle window is exercised for real (the retired versions passed `timeout=0.0`, which made
#     the deadline fire on iteration one so the logic under test never ran).
#   * `_FakeContainer` — answers the driver's `stat`/`od` probes the way a real container does,
#     including a dead one, which answers with docker exit 1 and NOTHING on stdout.

# A complete 4096-byte map's header: magic, version, flags, then (count, offset) for the name,
# export and import tables — every offset inside the file.
_GOOD_HEADER = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 40, 3000, 12, 3600, 8, 3400)


class _FakeClock:
    """A `monotonic`/`sleep` pair where SLEEPING is what advances time. Lets a poll loop run at its
    real configured `timeout`/`poll`/`settle` in zero wall-clock seconds."""

    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class _FakeContainer:
    """`subprocess.run` stand-in for `docker exec` against the editor container.

    `timeline` is the successive answers to the file-`stat` probe — `None` (file absent) or a
    `(size, mtime)` pair; the last entry repeats forever. The FIRST entry answers `map_save`'s
    pre-`MAP SAVE` stat. `header` is what the `od` header probe reports. `alive_for` (if set) is how
    many probes succeed before the container dies."""

    def __init__(self, timeline, header=_GOOD_HEADER, alive_for=None):
        self.timeline = list(timeline)
        self.header = header
        self.alive_for = alive_for
        self.stats = 0
        self.heads = 0
        self.scripts: list[str] = []
        self.kwargs: list[dict] = []

    @property
    def probes(self):
        return self.stats + self.heads

    def run(self, cmd, *a, **kw):
        assert cmd[:5] == ["docker", "exec", "c", "sh", "-c"], cmd
        script = cmd[5]
        assert script.startswith(f"printf '{_driver.PROBE_TAG} '; "), script
        self.scripts.append(script)
        self.kwargs.append(kw)
        if self.alive_for is not None and self.probes >= self.alive_for:
            # How a stopped/missing container really answers: exit 1 (the SAME code `stat` uses for
            # "no such file"), an error on stderr, and nothing at all on stdout.
            return mock.Mock(stdout="", returncode=1,
                             stderr="Error response from daemon: Container c is not running")
        if "od -An" in script:
            self.heads += 1
            # `header=None` stands for "od could not read it" — what a real container answers when
            # the file is unlinked between the stat and the read.
            body = "odfail" if self.header is None else " ".join(str(b) for b in self.header)
            return mock.Mock(stdout=f"{_driver.PROBE_TAG} {body}\n", stderr="", returncode=0)
        self.stats += 1
        entry = self.timeline[min(self.stats - 1, len(self.timeline) - 1)]
        if entry is None:
            return mock.Mock(stdout=f"{_driver.PROBE_TAG} missing", stderr="", returncode=0)
        size, mtime = entry
        return mock.Mock(stdout=f"{_driver.PROBE_TAG} {size} {mtime}\n", stderr="", returncode=0)


def _drive_map_save(ctr, clock, **kw):
    """Run `map_save` against a `_FakeContainer` on a `_FakeClock`, returning (driver, exec mock)."""
    d = Driver(container="c")
    with mock.patch.object(d, "exec", autospec=True) as ex, \
            mock.patch("uedcli.driver.time.sleep", clock.sleep), \
            mock.patch("uedcli.driver.time.monotonic", clock.monotonic), \
            mock.patch("uedcli.driver.subprocess.run", autospec=True, side_effect=ctr.run):
        return d.map_save("/work/out.dx", **kw), ex


def test_map_save_accepts_a_file_only_once_it_is_stable_AND_structurally_complete():
    """`exec` is fire-and-forget and MAP SAVE answers nothing over the console, so the file is the
    only signal. Accepting it takes `stable_reads` equal readings spanning `settle` seconds AND a
    package header whose object tables lie inside the file."""
    clock = _FakeClock()
    ctr = _FakeContainer([None,                       # pre-MAP SAVE: nothing there
                          None, (1024, "t1"), (4096, "t2"), (4096, "t2")])
    size, ex = _drive_map_save(ctr, clock)
    assert size == 4096
    ex.assert_called_once_with("MAP SAVE FILE=Z:\\work\\out.dx")
    # Exactly the readings the rule demands: 1 pre-save + absent + 1024 + four equal 4096 readings
    # (the fourth is where the 3 s settle window since the first 4096 closes, at the 1 s poll).
    assert ctr.stats == 7
    assert clock.t - 1000.0 == 5.0
    assert ctr.heads == 1                             # the header is read once, at the accept point


def test_map_save_needs_the_settle_WINDOW_not_just_equal_readings():
    """`stable_reads` equal readings are not enough on their own — they must also span `settle`
    seconds of wall clock, or a writer that pauses briefly between two fast polls passes. Driving the
    same frozen timeline at a poll far shorter than the window: it is refused; widen the window to
    one poll and the very same timeline is accepted."""
    frozen = [None, (4096, "t1")]
    with pytest.raises(DriverError) as e:             # 6 equal readings, but only 1.5 s of clock
        _drive_map_save(_FakeContainer(frozen), _FakeClock(),
                        timeout=1.5, poll=0.25, stable_reads=3)
    assert "still being written (at 4096 byte(s))" in str(e.value)
    size, _ = _drive_map_save(_FakeContainer(frozen), _FakeClock(),
                              timeout=1.5, poll=0.25, stable_reads=3, settle=0.5)
    assert size == 4096


def test_map_save_needs_stable_reads_EQUAL_readings_not_just_the_window():
    """The other half: with the settle window switched off, the default `stable_reads` still forces
    three equal readings before the header is even looked at."""
    ctr = _FakeContainer([None, (4096, "t1")])        # stable from the very first post-save reading
    size, _ = _drive_map_save(ctr, _FakeClock(), settle=0.0)
    assert size == 4096
    assert ctr.stats == 4                             # 1 pre-save + THREE equal readings, not one


def test_map_save_waits_out_a_file_that_is_still_empty():
    """A created-but-empty file is not a save. (`stat` answers, the size is 0, and the rule must not
    treat 'stable at zero bytes' as finished.)"""
    with pytest.raises(DriverError) as e:
        _drive_map_save(_FakeContainer([None, (0, "t1")]), _FakeClock(), timeout=10.0)
    assert "still empty (0 bytes)" in str(e.value)


def test_map_save_bounds_every_probe_and_reports_the_elapsed_time():
    """Two promises of the failure path: each `docker exec` carries `PROBE_TIMEOUT` (so a hung
    dockerd cannot park the poll loop past its own deadline), and the message reports how long it
    actually waited, not just the configured bound."""
    clock = _FakeClock()
    ctr = _FakeContainer([None])
    # A poll coarser than the remaining budget overshoots the deadline — which is exactly why the
    # message must report what really elapsed (6 s here) and not just the 4 s that was asked for.
    with pytest.raises(DriverError) as e:
        _drive_map_save(ctr, clock, timeout=4.0, poll=3.0)
    assert "after 6s, bound 4s" in str(e.value)
    assert ctr.kwargs and all(kw.get("timeout") == _driver.PROBE_TIMEOUT for kw in ctr.kwargs)


def test_map_save_probe_scripts_are_the_ones_the_container_can_answer():
    """The probes are shell text sent into the container, so their exact spelling IS the contract:
    quoted path, existence test before `stat`, the `%.9Y` nanosecond mtime, and a 36-byte `od` dump
    of unambiguous decimal bytes. A silent change here degrades every signal above it."""
    ctr = _FakeContainer([None, (4096, "t1")])
    _drive_map_save(ctr, _FakeClock(), settle=0.0)
    stat_script = next(s for s in ctr.scripts if "stat -c" in s)
    head_script = next(s for s in ctr.scripts if "od -An" in s)
    assert stat_script == (
        f"printf '{_driver.PROBE_TAG} '; if [ -e /work/out.dx ]; then "
        f"stat -c '%s %.9Y' -- /work/out.dx 2>/dev/null || printf statfail; else printf missing; fi")
    assert head_script == (
        f"printf '{_driver.PROBE_TAG} '; od -An -v -tu1 -N {_driver.PKG_HEADER_BYTES} -- "
        f"/work/out.dx 2>/dev/null || printf odfail")


def test_container_probes_quote_a_hostile_path():
    """The path reaches a shell, so it is `shlex.quote`d — a name with a space or a `;` must not
    become extra shell words."""
    d = Driver(container="c")
    ctr = _FakeContainer([None])
    with mock.patch("uedcli.driver.subprocess.run", autospec=True, side_effect=ctr.run):
        d.container_stat("/work/a b;rm -rf /.dx")
    assert "'/work/a b;rm -rf /.dx'" in ctr.scripts[0]


def test_map_save_stats_the_file_BEFORE_issuing_map_save():
    """The pre-save reading is what makes "the file changed" checkable, so it has to be taken before
    the command is typed — afterwards it would already include the editor's own write."""
    clock, seen = _FakeClock(), []
    ctr = _FakeContainer([None, (4096, "t2"), (4096, "t2")])
    d = Driver(container="c")
    with mock.patch.object(d, "exec", autospec=True, side_effect=lambda _l: seen.append(ctr.stats)), \
            mock.patch("uedcli.driver.time.sleep", clock.sleep), \
            mock.patch("uedcli.driver.time.monotonic", clock.monotonic), \
            mock.patch("uedcli.driver.subprocess.run", autospec=True, side_effect=ctr.run):
        d.map_save("/work/out.dx")
    assert seen == [1]                                # exactly one stat had run when MAP SAVE fired


def test_map_save_rejects_a_stale_file_the_editor_never_rewrote():
    """A complete map left at that path by an EARLIER run must not be mistaken for this save's
    output: a reading identical to the pre-save one means the editor wrote nothing."""
    clock = _FakeClock()
    ctr = _FakeContainer([(4096, "t0")])              # same size AND mtime, before and after
    with pytest.raises(DriverError) as e:
        _drive_map_save(ctr, clock, timeout=10.0)
    assert "unchanged from before MAP SAVE" in str(e.value) and "/work/out.dx" in str(e.value)
    assert clock.t - 1000.0 >= 10.0                   # it really polled for the whole timeout


def test_map_save_ACCEPTS_a_fixed_path_resave_that_really_changed():
    """The other half of the pre-save-stat rule, and the only half that fires in production for a
    fixed-path caller: a file that DID change since the pre-save reading must be accepted. Without
    this, `elif before is not None:` (reject every save into a pre-existing path) passes the suite."""
    ctr = _FakeContainer([(4096, "t0"),               # pre-MAP SAVE: a complete map already there
                          (4096, "t1")])              # same SIZE, new mtime ⇒ the editor rewrote it
    size, _ = _drive_map_save(ctr, _FakeClock(), settle=0.0)
    assert size == 4096


def test_map_save_refuses_a_reading_identical_to_the_pre_save_one():
    """The reject half of the pre-save rule. (It does NOT on its own pin that the mtime is part of
    the comparison — `test_map_save_ACCEPTS_a_fixed_path_resave_that_really_changed` is what kills a
    size-only compare, because there the size is deliberately unchanged. Don't delete that one
    thinking this covers it.)"""
    ctr = _FakeContainer([(4096, "t0"), (4096, "t0")])
    with pytest.raises(DriverError) as e:
        _drive_map_save(ctr, _FakeClock(), timeout=5.0, settle=0.0)
    assert "unchanged from before MAP SAVE" in str(e.value)


def test_map_save_rejects_a_write_that_stalls_truncated():
    """The stall case the size-only rule accepted: a wedged editor's part-written map holds a steady
    non-zero size forever. Only the structural check can tell it from a finished one."""
    clock = _FakeClock()
    ctr = _FakeContainer([None, (12, "t1")], header=b"\x00" * 12)
    with pytest.raises(DriverError) as e:
        _drive_map_save(ctr, clock, timeout=10.0)
    msg = str(e.value)
    assert "stalled at 12 byte(s)" in msg and "smaller than a package header" in msg


def test_map_save_rethrottles_the_header_probe_without_caching_a_verdict_forever():
    """A stable-but-incomplete file is polled to the deadline, and re-probing its header every second
    would cost 600 extra `docker exec`s (each with its own 60 s bound). But the verdict must NOT be
    cached permanently either: the destination's header is not known to be immutable once written
    (rename vs copy is undetermined), so a permanently-cached pre-patch verdict could fail a file
    that has since become valid. Hence `recheck`: at most one header read per window, per size."""
    truncated = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 40, 3000, 12, 99999, 8, 3400)
    ctr = _FakeContainer([None, (4096, "t1")], header=truncated)
    with pytest.raises(DriverError):
        _drive_map_save(ctr, _FakeClock(), timeout=30.0, recheck=10.0)
    assert ctr.stats > 25                             # it really polled for the whole timeout
    # ~30 s of polling at a 10 s recheck window: re-probed, but a handful of times, not 25+.
    assert 2 <= ctr.heads <= 5, ctr.heads


def test_map_save_forgets_a_header_verdict_when_the_file_disappears():
    """The cache is keyed on size, so a file that vanishes and comes back at the SAME size with a
    different header must be re-probed, not answered from the stale verdict."""
    good = _GOOD_HEADER
    bad = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 40, 3000, 12, 99999, 8, 3400)
    ctr = _FakeContainer([None, (4096, "t1"), (4096, "t1"), (4096, "t1"), (4096, "t1"),
                          None,                                   # ...the file is replaced...
                          (4096, "t2")], header=bad)
    # Once the bad-header reading has been rejected, swap in a good header behind the disappearance.
    original_run = ctr.run

    def run(cmd, *a, **kw):
        if ctr.stats >= 6:
            ctr.header = good
        return original_run(cmd, *a, **kw)

    ctr.run = run
    size, _ = _drive_map_save(ctr, _FakeClock(), timeout=60.0, recheck=1e9)
    assert size == 4096                               # re-probed after the gap, despite the same size
    assert ctr.heads >= 2


def test_map_save_reprobes_immediately_when_the_SIZE_changes():
    """The cache is keyed on (size, when), and the SIZE half must not be lost: a file that stalls at
    one size with a bad header and then grows to a new size has to be re-probed at once, not after
    `recheck` expires. With `recheck` effectively infinite, only the size key can trigger the
    re-read — so this fails if the key is dropped."""
    bad = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 40, 3000, 12, 99999, 8, 3400)
    ctr = _FakeContainer([None,
                          (4096, "t1"), (4096, "t1"), (4096, "t1"), (4096, "t1"),  # stalls, bad
                          (8192, "t2")],                                            # ...then grows
                         header=bad)
    original_run = ctr.run

    def run(cmd, *a, **kw):
        if ctr.stats >= 6:                            # once the bigger size is being reported
            ctr.header = _GOOD_HEADER
        return original_run(cmd, *a, **kw)

    ctr.run = run
    size, _ = _drive_map_save(ctr, _FakeClock(), timeout=60.0, recheck=1e9)
    assert size == 8192


def test_map_save_rejects_a_big_file_whose_tables_were_never_written():
    """The other truncation shape: enough bytes to look plausible, but the header's object tables
    start past EOF — the serializer never got to them."""
    clock = _FakeClock()
    truncated = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 40, 3000, 12, 99999, 8, 3400)
    ctr = _FakeContainer([None, (4096, "t1")], header=truncated)
    with pytest.raises(DriverError) as e:
        _drive_map_save(ctr, clock, timeout=10.0)
    assert "export table at offset 99999, outside the 4096-byte file" in str(e.value)


def test_map_save_raises_when_the_editor_never_wrote_the_file():
    # A wedged editor writes NOTHING; without this check it surfaced much later as an opaque
    # `docker cp` failure blaming the wrong subsystem.
    clock = _FakeClock()
    ctr = _FakeContainer([None])
    with pytest.raises(DriverError) as e:
        _drive_map_save(ctr, clock, timeout=10.0)
    assert "/work/out.dx" in str(e.value) and "no file appeared" in str(e.value)
    assert ctr.stats > 2                              # the poll loop really ran, not one iteration


def test_map_save_reports_a_dead_container_at_once_instead_of_polling_a_corpse():
    """A container that dies mid-save must be named immediately. Measured 2026-07-25: docker exec
    exits 1 for a stopped container — the same code as "no such file" — so the driver must decide
    liveness by the probe sentinel, not the exit code, or it polls a corpse for the full timeout and
    then blames the editor."""
    clock = _FakeClock()
    ctr = _FakeContainer([None, (1024, "t1")], alive_for=3)
    with pytest.raises(DriverError) as e:
        _drive_map_save(ctr, clock, timeout=600.0)
    msg = str(e.value)
    assert "container c" in msg and "is not running" in msg
    assert "did not run the probe" in msg
    assert clock.t - 1000.0 < 600.0                   # it did NOT wait out the ten-minute timeout


def test_container_stat_returns_size_and_mtime_or_none():
    d = Driver(container="c")
    ctr = _FakeContainer([(4096, "1753440000.123456789"), None])
    with mock.patch("uedcli.driver.subprocess.run", autospec=True, side_effect=ctr.run):
        assert d.container_stat("/work/out.dx") == (4096, "1753440000.123456789")
        assert d.container_stat("/work/out.dx") is None


def test_container_stat_trusts_the_sentinel_not_the_docker_exit_code():
    """Exit 1 means BOTH "no such file" and "container is gone", so the exit code decides nothing:
    a reply carrying the sentinel is a real answer whatever docker exited with, and a reply without
    it is a container failure whatever docker exited with."""
    d = Driver(container="c")
    with mock.patch("uedcli.driver.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(stdout=f"{_driver.PROBE_TAG} 4096 t1\n", stderr="",
                                     returncode=1)
        assert d.container_stat("/work/out.dx") == (4096, "t1")        # answered ⇒ exit code moot
        run.return_value = mock.Mock(stdout="", returncode=0,
                                     stderr="Error: No such container: c")
        with pytest.raises(DriverError) as e:
            d.container_stat("/work/out.dx")
    assert "container c" in str(e.value) and "No such container" in str(e.value)


def test_container_stat_bounds_the_docker_call_instead_of_hanging():
    """A hung dockerd would otherwise park the caller forever INSIDE map_save's own timeout — the
    "never an open-ended wait" rule. The bound has to be PASSED to subprocess (asserted here, since
    catching `TimeoutExpired` proves nothing about asking for one), and a timeout has to surface as a
    DriverError, never as a `subprocess.TimeoutExpired` traceback."""
    import subprocess as sp
    d = Driver(container="c")
    with mock.patch("uedcli.driver.subprocess.run", autospec=True,
                    side_effect=sp.TimeoutExpired(cmd="docker", timeout=_driver.PROBE_TIMEOUT)) as run:
        with pytest.raises(DriverError) as e:
            d.container_stat("/work/out.dx")
    assert "did not answer within" in str(e.value) and "container c" in str(e.value)
    assert run.call_args.kwargs["timeout"] == _driver.PROBE_TIMEOUT


def test_container_stat_raises_when_the_file_is_there_but_stat_failed():
    """"Absent" and "`stat` itself failed" are different answers and only the first is `None`. If a
    permission error or a coreutils without `%.9Y` collapsed into "not there", `map_save` would poll a
    perfectly good file for its whole timeout and then blame the editor."""
    d = Driver(container="c")
    with mock.patch("uedcli.driver.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(stdout=f"{_driver.PROBE_TAG} statfail", stderr="", returncode=0)
        with pytest.raises(DriverError) as e:
            d.container_stat("/work/out.dx")
        assert "`stat` did not answer with a size" in str(e.value)
        run.return_value = mock.Mock(stdout=f"{_driver.PROBE_TAG} nonsense\n", stderr="",
                                     returncode=0)
        with pytest.raises(DriverError) as e:
            d.container_stat("/work/out.dx")
    assert "'nonsense'" in str(e.value)


def test_container_probe_reports_a_missing_docker_binary_as_a_driver_error():
    """`subprocess.run` raising OSError (no docker on PATH) must not reach the user as a traceback."""
    d = Driver(container="c")
    with mock.patch("uedcli.driver.subprocess.run", autospec=True,
                    side_effect=OSError("No such file or directory: 'docker'")):
        with pytest.raises(DriverError) as e:
            d.container_stat("/work/out.dx")
    assert "cannot run docker" in str(e.value) and "container c" in str(e.value)


def test_container_file_head_separates_a_vanished_file_from_a_broken_probe():
    """Neither may pass for "the file is empty" (downstream that reads as a truncated package), but
    they are different events: `odfail` means the file could not be read AT ALL — in a poll loop,
    overwhelmingly "it was unlinked between the stat and the read", a transient the next poll
    recovers from, so it returns None rather than aborting the wait. A reply that is neither bytes
    nor the sentinel is a broken probe and raises."""
    d = Driver(container="c")
    with mock.patch("uedcli.driver.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(stdout=f"{_driver.PROBE_TAG} odfail\n", stderr="",
                                     returncode=0)
        assert d.container_file_head("/work/out.dx", 36) is None
        run.return_value = mock.Mock(stdout=f"{_driver.PROBE_TAG} 999\n", stderr="", returncode=0)
        with pytest.raises(DriverError) as e:
            d.container_file_head("/work/out.dx", 36)
    assert "not a list of byte values" in str(e.value)


def test_map_save_keeps_polling_when_the_file_vanishes_under_the_header_read():
    """The whole point of returning None above: a save wait must survive the stat/read race instead
    of aborting on it. Here the file is gone exactly when the header is read, then comes back."""
    ctr = _FakeContainer([None, (4096, "t1")], header=None)   # header=None ⇒ the od probe says odfail
    original_run = ctr.run

    def run(cmd, *a, **kw):
        if ctr.heads >= 1:                            # after the first (failed) header read, restore
            ctr.header = _GOOD_HEADER
        return original_run(cmd, *a, **kw)

    ctr.run = run
    size, _ = _drive_map_save(ctr, _FakeClock(), timeout=60.0, recheck=0.0)
    assert size == 4096
    assert ctr.heads >= 2


def test_container_file_head_decodes_the_od_dump():
    d = Driver(container="c")
    ctr = _FakeContainer([None], header=b"\x01\x02\xff")
    with mock.patch("uedcli.driver.subprocess.run", autospec=True, side_effect=ctr.run):
        assert d.container_file_head("/work/out.dx", 3) == b"\x01\x02\xff"


def test_package_header_problem_accepts_a_complete_package_and_names_every_defect():
    assert package_header_problem(_GOOD_HEADER, 4096) is None
    # too small to hold a header at all
    assert "smaller than a package header" in package_header_problem(b"", 12)
    # fewer header bytes came back than the file's stat'd size implies (it shrank under us)
    assert "read back only 8 of 36 bytes" in package_header_problem(b"\x00" * 8, 4096)
    # not a package: the magic was never written
    assert "bad package magic" in package_header_problem(b"\x00" * 36, 4096)
    # header written but never filled in
    zero_counts = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 0, 3000, 12, 3600, 8, 3400)
    assert "0 name table entries" in package_header_problem(zero_counts, 4096)
    # tables declared past EOF (a truncated write)
    past_eof = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 40, 3000, 12, 3600, 8, 9999)
    assert "import table at offset 9999, outside the 4096-byte file" in \
        package_header_problem(past_eof, 4096)
    # a table declared INSIDE the header itself is impossible too (the header is the first 36 bytes)
    into_header = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 40, 4, 12, 3600, 8, 3400)
    assert "name table at offset 4" in package_header_problem(into_header, 4096)


def test_package_header_problem_catches_a_truncation_INSIDE_the_last_table():
    """An offsets-only rule (every table STARTS inside the file) is nearly blind at the tail: real
    maps put their export/import tables at ~97-99 % of the file, so a copy that stalls just after the
    export table begins would pass. Each table must therefore also have ROOM for the entries the
    header claims, at their minimum encoded size."""
    # 900 exports declared at offset 3600 need >= 10800 bytes, so a 4096-byte file cannot hold them...
    crowded = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 40, 3000, 900, 3600, 8, 3400)
    problem = package_header_problem(crowded, 4096)
    assert "export table needs at least 10800 byte(s) from offset 3600" in problem
    # ...while the same header against a file long enough to hold them is complete.
    assert package_header_problem(crowded, 3600 + 10800 + 1) is None
    # All THREE tables carry the rule, at their own minimum entry size (name 5, import 7, export 12).
    many_names = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 900, 3000, 12, 3600, 8, 3400)
    assert "name table needs at least 4500 byte(s) from offset 3000" in \
        package_header_problem(many_names, 4096)
    many_imports = struct.pack("<9I", _driver.PKG_MAGIC, 69, 0, 40, 3000, 12, 3600, 900, 3400)
    assert "import table needs at least 6300 byte(s) from offset 3400" in \
        package_header_problem(many_imports, 4096)


def test_the_drivers_package_magic_matches_the_one_package_core():
    """`driver.py` keeps its own copy of the magic so it depends on nothing but a container. Pin the
    two spellings equal, or the copy drifts and the completeness check starts rejecting real maps."""
    from uedcli.upackage import MAGIC
    assert _driver.PKG_MAGIC == MAGIC


_REAL_CODE = sorted(install_system_root().glob("*.u"))[:8]
_REAL_MAPS = sorted((install_system_root().parent / "Maps").glob("*.dx"))[:4]
# The per-entry minimums are tightest on MUSIC and TEXTURE packages, not on code or maps (the whole
# corpus's slimmest margin is 4 bytes, in a `.umx`), so sampling only `.u`/`.dx` would pin the rule
# exactly where it is loosest. Take a few of each — and `Quotes_Music.umx` by name, since it is the
# measured worst case the driver docstring quotes.
_REAL_CONTENT = sorted((install_system_root().parent / "Music").glob("*.umx"))[:4] + \
    sorted((install_system_root().parent / "Music").glob("Quotes_Music.umx")) + \
    sorted((install_system_root().parent / "Textures").glob("*.utx"))[:4]
# BOTH code and maps are required, not concatenated: with `System/*.u` present but no `Maps/`, a
# single combined list would let the test run without one `.dx` — "the only thing map_save ever
# writes" — and still report a pass.
_REAL_PACKAGES = _REAL_CODE + _REAL_MAPS + _REAL_CONTENT


@pytest.mark.skipif(not (_REAL_CODE and _REAL_MAPS),
                    reason="game install (BOTH System/*.u and Maps/*.dx) not present")
def test_real_packages_pass_the_completeness_check():
    """The engine fact the accept rule rests on, against real files instead of a synthetic header: a
    FINISHED Unreal package always has non-zero table counts, every table offset inside the file, and
    room for the entry counts it declares. Without this the check is only ever tested against headers
    this suite wrote itself — and a too-strict rule would reject every real save, at a 600 s timeout
    each. (The full-corpus sweep lives in `spikes/2026-07-25-map-save-mechanism/`.)"""
    for path in _REAL_PACKAGES:
        blob = path.read_bytes()
        assert package_header_problem(blob[:_driver.PKG_HEADER_BYTES], len(blob)) is None, path
        # ...and a truncation of that same real file is caught (the copy-phase wedge shape).
        half = len(blob) // 2
        assert package_header_problem(blob[:_driver.PKG_HEADER_BYTES], half) is not None, path


def test_map_new_issues_map_new():
    from unittest import mock
    from uedcli.driver import Driver
    d = Driver(container="c")
    with mock.patch.object(d, "exec", autospec=True) as ex:
        d.map_new()
    ex.assert_called_once_with("MAP NEW")


def test_jumpto_rmode_light_apply_emit_expected_console_verbs():
    from unittest import mock
    from uedcli.driver import Driver
    d = Driver(container="c")
    with mock.patch.object(d, "exec", autospec=True) as ex:
        d.jumpto(100, -50, 200)
        d.rmode(6)
        d.light_apply()
    assert ex.call_args_list == [
        mock.call("JUMPTO 100,-50,200"),
        mock.call("RMODE 6"),
        mock.call("LIGHT APPLY"),
    ]


# --- log read primitives + OBJ DEPENDENCIES (export_and_qualify support) ----

def test_log_size_reads_the_editor_log_byte_count():
    d = Driver(container="c")
    with mock.patch("uedcli.driver.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(stdout="12345\n", returncode=0)
        assert d.log_size() == 12345
    run.assert_called_once_with(
        ["docker", "exec", "c", "stat", "-c", "%s", "/opt/UED22/Editor.log"],
        capture_output=True, text=True, check=True)


def test_read_log_since_tails_from_the_given_offset_and_strips_nuls():
    d = Driver(container="c")
    with mock.patch("uedcli.driver.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(stdout="hello\x00world", returncode=0)
        text = d.read_log_since(100)
    assert text == "helloworld"
    run.assert_called_once_with(
        ["docker", "exec", "c", "tail", "-c", "+101", "/opt/UED22/Editor.log"],
        capture_output=True, text=True, check=True)


def test_obj_dependencies_execs_the_console_verb():
    d = Driver(container="c")
    with mock.patch.object(d, "exec", autospec=True) as ex:
        d.obj_dependencies("MyLevel")
    ex.assert_called_once_with("OBJ DEPENDENCIES PACKAGE=MyLevel")


def test_obj_load_uses_z_drive_path():
    d = Driver(container="c")
    with mock.patch.object(d, "exec", autospec=True) as ex:
        d.obj_load("CoreTexMetal", "/repo/Textures/CoreTexMetal.utx")
    ex.assert_called_once_with(
        "OBJ LOAD FILE=Z:\\repo\\Textures\\CoreTexMetal.utx PACKAGE=CoreTexMetal")


# --- dismiss_blocking_dialog (the stuck "Cleaning up..." GC dialog, 2026-06-20) -------------

_WMCTRL_WITH_DIALOG = (
    "0x0100001d  0 38304795729b xmessage\n"
    "0x01a00001  0 38304795729b Unreal Editor 2.2 for Deus Ex\n"
    "0x01a0000b  0 38304795729b Unreal Editor 2.2 for Deus Ex Log Window\n"
    "0x01a0001d  0 38304795729b Textures\n"
)
_WMCTRL_NO_DIALOG = (
    "0x01a00001  0 38304795729b Unreal Editor 2.2 for Deus Ex\n"
    "0x01a0000b  0 38304795729b Unreal Editor 2.2 for Deus Ex Log Window\n"
    "0x01a0001d  0 38304795729b Textures\n"
)


def test_dismiss_blocking_dialog_finds_and_dismisses_the_xmessage_window():
    d = Driver(container="c")
    with mock.patch("uedcli.driver.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(stdout=_WMCTRL_WITH_DIALOG, returncode=0)
        found = d.dismiss_blocking_dialog()
    assert found is True
    calls = run.call_args_list
    assert calls[0].args[0] == ["docker", "exec", "c", "wmctrl", "-l"]
    assert calls[1].args[0] == ["docker", "exec", "-e", "DISPLAY=:99", "c",
                               "xdotool", "windowactivate", "--sync", "0x0100001d"]
    assert calls[2].args[0] == ["docker", "exec", "-e", "DISPLAY=:99", "c",
                               "xdotool", "key", "Return"]


def test_dismiss_blocking_dialog_is_a_noop_when_none_present():
    d = Driver(container="c")
    with mock.patch("uedcli.driver.subprocess.run", autospec=True) as run:
        run.return_value = mock.Mock(stdout=_WMCTRL_NO_DIALOG, returncode=0)
        found = d.dismiss_blocking_dialog()
    assert found is False
    run.assert_called_once()      # only the wmctrl -l probe, no activate/key calls

def test_selectname_issues_selectname_with_actor_name():
    from unittest import mock
    from uedcli.driver import Driver
    d = Driver(container="c")
    with mock.patch.object(d, "exec", autospec=True) as ex:
        d.selectname("UedcliLight0")
    ex.assert_called_once_with("SELECTNAME NAME=UedcliLight0")


def test_camera_align_with_no_name_issues_bare_align():
    from unittest import mock
    from uedcli.driver import Driver
    d = Driver(container="c")
    with mock.patch.object(d, "exec", autospec=True) as ex:
        d.camera_align()
    ex.assert_called_once_with("CAMERA ALIGN")


def test_camera_align_with_name_issues_align_name():
    from unittest import mock
    from uedcli.driver import Driver
    d = Driver(container="c")
    with mock.patch.object(d, "exec", autospec=True) as ex:
        d.camera_align(name="UedcliLight0")
    ex.assert_called_once_with("CAMERA ALIGN NAME=UedcliLight0")


def test_click_shells_to_wine_ctl_click():
    d = Driver(container="test-ctr")
    with mock.patch("uedcli.driver.subprocess.run") as run:
        run.return_value = mock.Mock(stdout="", returncode=0)
        d.click(760, 598)
    cmd = run.call_args[0][0]
    assert cmd[:3] == ["docker", "exec", "test-ctr"]
    assert cmd[-5:] == ["click", "760", "598", "--button", "1"]   # x,y are POSITIONAL in wine_ctl


def test_dexec_bash_runs_bash_c_and_returns_stdout():
    d = Driver(container="test-ctr")
    with mock.patch("uedcli.driver.subprocess.run") as run:
        run.return_value = mock.Mock(stdout="swept\n", returncode=0)
        out = d.dexec_bash("wmctrl -l | awk '{print $1}'")
    cmd = run.call_args[0][0]
    assert cmd == ["docker", "exec", "test-ctr", "bash", "-c", "wmctrl -l | awk '{print $1}'"]
    assert out == "swept\n"


def test_the_per_entry_minimums_bound_what_upackage_actually_parses():
    """The 5/12/7 minimums in `package_header_problem` are derived from `upackage._parse_package`'s
    field order, but nothing else ties the two together — a field added to any table entry there
    would silently invalidate the driver's arithmetic. Pin them against the REAL parser: for each
    table, the bytes `upackage` consumes per entry must be >= the driver's assumed minimum.

    (This also documents why `name` is 5 and not 6: `read_fstring` accepts a zero-length name, so
    the v>=64 form's floor is 1 + 0 + 4, the same as the v<64 form's NUL + u32.)"""
    from uedcli import upackage
    # Smallest legal encodings, built by hand against upackage's readers.
    name_v64 = bytes([0]) + struct.pack("<I", 0)              # compact len 0, no chars, u32 flags
    assert len(name_v64) == 5
    _s, pos = upackage.read_fstring(name_v64, 0)
    assert pos + 4 == len(name_v64) == 5

    smallest_import = bytes([0, 0]) + struct.pack("<i", 0) + bytes([0])
    assert len(smallest_import) == 7
    pos = 0
    for _ in range(2):                                        # ClassPackage, ClassName
        _v, pos = upackage.read_compact_index(smallest_import, pos)
    pos += 4                                                  # PackageIndex (i32)
    _v, pos = upackage.read_compact_index(smallest_import, pos)   # ObjectName
    assert pos == 7

    smallest_export = bytes([0, 0]) + struct.pack("<i", 0) + bytes([0]) + struct.pack("<I", 0) + \
        bytes([0])
    assert len(smallest_export) == 12
    pos = 0
    for _ in range(2):                                        # class, super
        _v, pos = upackage.read_compact_index(smallest_export, pos)
    pos += 4                                                  # outer (i32)
    _v, pos = upackage.read_compact_index(smallest_export, pos)   # name
    pos += 4                                                  # flags (u32)
    _v, pos = upackage.read_compact_index(smallest_export, pos)   # serial size
    assert pos == 12
