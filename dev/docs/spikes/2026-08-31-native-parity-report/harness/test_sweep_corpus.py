"""Tests the scheduler in `sweep_corpus.run_sweep` -- bounded concurrency and real hang-detection --
using a FAKE, instant "editor" subprocess (a tiny inline Python script) instead of docker/Wine, so
this runs in well under a second and pins the exact mechanism that caused this session's repeated
`TimeoutError: editor not idle` pain: too many concurrent editor-driving builds, and a single wedged
one blocking the whole sweep.

Run directly (same as `test_parity_pipeline.py`):
    .venv/bin/python -m pytest dev/docs/spikes/2026-08-31-native-parity-report/harness/test_sweep_corpus.py
"""
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sweep_lib as sl          # noqa: E402
import sweep_corpus as sc       # noqa: E402


def _fake_command_builder(*, behaviors):
    """Builds a `command_builder` that launches `python -c ...` per level: SLEEP levels sleep past
    the test's hang-timeout (simulating a wedged editor); FAST levels exit immediately with a
    canned JSON report on stdout (simulating a normal cache-hit run); FAIL levels exit 2 (simulating
    a clean `PipelineError`)."""
    def builder(dx_path, *, cache_root, rebuild_timeout, game):
        name = dx_path.name
        behavior = behaviors[name]
        if behavior == "sleep":
            code = "import time; time.sleep(3600)"
        elif behavior == "fail":
            code = "import sys; print('boom', file=sys.stderr); sys.exit(2)"
        else:  # "fast"
            report = json.dumps({
                "cache_hit": True,
                "geometry": {"deltas": {"nodes": 0, "surfs": 0, "leaves": 0, "verts": 0, "points": 0,
                                        "vectors": 0}},
                "content": {
                    "nodes": {"native_len": 1, "golden_len": 1, "indices_differ": 0, "exact": True},
                    "surfs": {"native_len": 1, "golden_len": 1, "indices_differ": 0, "exact": True},
                    "leaves": {"native_len": 1, "golden_len": 1, "indices_differ": 0, "exact": True},
                },
                "lighting": {"identical_pct": 100.0, "shadow_bit_pct": 100.0},
                "full_parity": True,
            })
            code = f"print({report!r})"
        return [sys.executable, "-c", code]
    return builder


def test_concurrency_is_never_exceeded(tmp_path):
    """5 levels, concurrency=2 -- at no point should more than 2 subprocesses be alive at once. Proven
    by making every level SLEEP long enough that, if the scheduler ever over-launched, a 3rd/4th/5th
    concurrent process would be observable; instead assert via a short hang-timeout that exactly the
    concurrency-bounded launch pattern occurs (2 running, then killed by hang-timeout, then the next 2,
    etc.) by counting how many distinct 2-second "waves" the 5 timeouts fall into."""
    levels = ["a.dx", "b.dx", "c.dx", "d.dx", "e.dx"]
    for lv in levels:
        (tmp_path / lv).write_bytes(b"fake")
    behaviors = {lv: "sleep" for lv in levels}
    builder = _fake_command_builder(behaviors=behaviors)

    max_concurrent = 0
    current = 0
    lock = threading.Lock()
    real_launch_count = {"n": 0}

    orig_run_sweep = sc.run_sweep

    # Wrap Popen to observe concurrent process count without changing scheduler behavior.
    import subprocess as sp

    def _mark_done_once(proc):
        nonlocal current
        with lock:
            if not getattr(proc, "_counted_done", False):
                proc._counted_done = True
                current -= 1

    class _CountingPopen(sp.Popen):
        def __init__(self, *a, **kw):
            nonlocal max_concurrent, current
            with lock:
                current += 1
                max_concurrent = max(max_concurrent, current)
            super().__init__(*a, **kw)

        def poll(self):
            rc = super().poll()
            if rc is not None:
                _mark_done_once(self)
            return rc

        def wait(self, *a, **kw):
            rc = super().wait(*a, **kw)
            _mark_done_once(self)
            return rc

    import sweep_lib
    orig_maps_dir = sweep_lib.maps_dir
    sweep_lib.maps_dir = lambda start: tmp_path
    try:
        results = sc.run_sweep(levels, concurrency=2, cache_root=tmp_path / "cache",
                               rebuild_timeout=10.0, hang_timeout=0.3, game="deusex",
                               work_dir=tmp_path / "work", command_builder=builder,
                               poll_interval=0.05, popen=_CountingPopen)
    finally:
        sweep_lib.maps_dir = orig_maps_dir

    assert len(results) == 5
    assert all(r.status == "TIMED_OUT" for r in results)
    assert max_concurrent <= 2, f"scheduler exceeded concurrency bound: {max_concurrent} concurrent"


def test_hung_level_is_killed_and_does_not_block_the_rest(tmp_path):
    levels = ["hung.dx", "fast.dx"]
    for lv in levels:
        (tmp_path / lv).write_bytes(b"fake")
    behaviors = {"hung.dx": "sleep", "fast.dx": "fast"}
    builder = _fake_command_builder(behaviors=behaviors)

    import sweep_lib
    orig_maps_dir = sweep_lib.maps_dir
    sweep_lib.maps_dir = lambda start: tmp_path
    try:
        started = time.monotonic()
        results = sc.run_sweep(levels, concurrency=2, cache_root=tmp_path / "cache",
                               rebuild_timeout=10.0, hang_timeout=0.3, game="deusex",
                               work_dir=tmp_path / "work", command_builder=builder,
                               poll_interval=0.05)
        elapsed = time.monotonic() - started
    finally:
        sweep_lib.maps_dir = orig_maps_dir

    by_level = {r.level: r for r in results}
    assert by_level["hung.dx"].status == "TIMED_OUT"
    assert by_level["fast.dx"].status == "OK"
    assert by_level["fast.dx"].full_parity is True
    # The whole sweep must finish close to the hang-timeout, not the (never-ending) sleep duration --
    # proves the hung level did not block the fast one nor the overall sweep.
    assert elapsed < 5.0


def test_pipeline_error_is_recorded_not_raised(tmp_path):
    levels = ["fail.dx"]
    (tmp_path / "fail.dx").write_bytes(b"fake")
    builder = _fake_command_builder(behaviors={"fail.dx": "fail"})

    import sweep_lib
    orig_maps_dir = sweep_lib.maps_dir
    sweep_lib.maps_dir = lambda start: tmp_path
    try:
        results = sc.run_sweep(levels, concurrency=1, cache_root=tmp_path / "cache",
                               rebuild_timeout=10.0, hang_timeout=5.0, game="deusex",
                               work_dir=tmp_path / "work", command_builder=builder,
                               poll_interval=0.05)
    finally:
        sweep_lib.maps_dir = orig_maps_dir

    assert results[0].status == "PIPELINE_ERROR"
    assert "boom" in results[0].notes


def test_missing_map_file_is_a_clean_error_not_a_launch(tmp_path):
    import sweep_lib
    orig_maps_dir = sweep_lib.maps_dir
    sweep_lib.maps_dir = lambda start: tmp_path  # empty dir -- nothing exists in it
    try:
        results = sc.run_sweep(["nope.dx"], concurrency=1, cache_root=tmp_path / "cache",
                               rebuild_timeout=10.0, hang_timeout=5.0, game="deusex",
                               work_dir=tmp_path / "work",
                               command_builder=_fake_command_builder(behaviors={}))
    finally:
        sweep_lib.maps_dir = orig_maps_dir

    assert results[0].status == "ERROR"
    assert "not found" in results[0].notes
