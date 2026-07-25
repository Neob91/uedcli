"""Integration tests against the live dx-lum-uned container.

Deselected by default (pytest.ini: addopts = -m "not integration").
Run with: pytest uedctl -m integration -v

These tests require the container to be running:
    docker ps | grep dx-lum-uned
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

from uedctl import xfer
from uedctl.driver import Driver, to_z_path
from uedctl.model import parse_t3d
from uedctl.normalize import normalize_level

CONTAINER = "dx-lum-uned"


@pytest.fixture(scope="module")
def driver():
    return Driver(container=CONTAINER)


@pytest.mark.integration
def test_map_export_round_trip_has_actors(driver):
    """MAP EXPORT → parse → normalize: the level must contain at least one actor.

    This proves the driver's map_export path works end-to-end:
    - console exec reaches UnrealEd
    - T3D text is readable from the container
    - parse_t3d + normalize_level produce a non-empty level
    """
    export_path = xfer.work_path("t3d")
    driver.set_grid(1, 1, 1)
    driver.map_export(export_path)
    txt = subprocess.run(
        ["docker", "exec", CONTAINER, "cat", export_path],
        text=True, capture_output=True, check=True,
    ).stdout
    xfer.remove(CONTAINER, export_path)
    level = parse_t3d(txt)
    normalize_level(level)
    assert len(level.actors) >= 1, (
        "MAP EXPORT returned a level with no actors — "
        "either the map is empty or the export path is wrong"
    )


@pytest.mark.integration
def test_exec_file_runs_script_and_continues_past_errors(driver):
    """Engine-fact regression (spike 2026-07-18-exec-file-console-batch): the console `EXEC
    Z:\\work\\<file>` verb runs a command-script file — lines execute in order, an unrecognized
    verb does NOT abort the rest, and LF line endings are accepted. Pins the batching contract
    an exec-file drive would rely on; a UED22 substrate/image change that breaks any of it must
    trip this red, not drift."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, newline="\n") as f:
        host_script = f.name
    out_a = xfer.work_path("t3d")
    out_b = xfer.work_path("t3d")
    script = None
    try:
        Path(host_script).write_text(
            f"MAP EXPORT FILE={to_z_path(out_a)}\n"
            "TOTALLYBOGUSVERB FOO=1\n"
            f"MAP EXPORT FILE={to_z_path(out_b)}\n")
        script = xfer.cp_in(driver.container, host_script, ext="txt")
        driver.exec(f"EXEC {to_z_path(script)}")
        # The typed EXEC returns immediately; completion = the LAST line's marker appearing.
        import time
        deadline = 30
        for _ in range(deadline * 2):
            probe = subprocess.run(
                ["docker", "exec", driver.container, "sh", "-c",
                 f"test -s {out_a} -a -s {out_b}"],
                capture_output=True)
            if probe.returncode == 0:
                break
            time.sleep(0.5)
        else:
            pytest.fail(f"EXEC script did not produce both exports within {deadline}s "
                        "(script batching broken, or the bogus verb aborted the script)")
    finally:
        Path(host_script).unlink(missing_ok=True)
        xfer.remove(driver.container, *(p for p in (script, out_a, out_b) if p))
