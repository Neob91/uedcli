"""Editor-golden CSG capture tests.

Two layers:
  * OFFLINE (default suite) — load the frozen fixtures under
    `fixtures/csg_golden/`, assert they parse, are non-empty, and are
    self-consistent through the comparator. Validates the fixtures exist and are
    well-formed WITHOUT the editor (so CI catches a missing/corrupt freeze).
  * INTEGRATION (`-m integration`) — mint an ephemeral editor, build each corpus
    case live, and assert the capture is non-empty and matches the frozen fixture.
    This is also the re-bless path (`python -m uedcli.native.csg_golden`).
"""
from __future__ import annotations

import uuid

import pytest

from uedcli.native import csg_golden as g

FIXTURES = sorted(g.FIXTURE_DIR.glob("*.json")) if g.FIXTURE_DIR.exists() else []
FIXTURE_CASES = [p.stem for p in FIXTURES]


# --- offline -----------------------------------------------------------------

def test_at_least_one_fixture_is_frozen():
    assert FIXTURE_CASES, (
        "no csg_golden fixtures frozen yet — run `python -m uedcli.native.csg_golden` "
        "against a live editor to capture them")


@pytest.mark.parametrize("case", FIXTURE_CASES)
def test_frozen_fixture_parses_and_is_non_empty(case):
    golden = g.load_fixture(case)
    assert golden["case"] == case
    counts = golden["counts"]
    assert counts["surfs"] > 0, f"{case}: fixture has no surfs"
    assert counts["nodes"] > 0, f"{case}: fixture has no nodes"
    assert counts["leaves"] > 0, f"{case}: fixture has no leaves"
    assert len(golden["surfs"]) == counts["surfs"], f"{case}: surf list vs count mismatch"
    for s in golden["surfs"]:
        assert len(s["normal"]) == 3
        assert s["verts"], f"{case}: a surf has no vertices"


@pytest.mark.parametrize("case", FIXTURE_CASES)
def test_comparator_is_reflexive(case):
    golden = g.load_fixture(case)
    ok, diff = g.compare(golden, golden)
    assert ok, f"{case}: comparator not reflexive:\n{diff}"


def test_comparator_flags_a_count_difference():
    a = {"counts": {"nodes": 6, "leaves": 2, "surfs": 6}, "surfs": []}
    b = {"counts": {"nodes": 7, "leaves": 2, "surfs": 6}, "surfs": []}
    ok, diff = g.compare(a, b)
    assert not ok and "nodes" in diff


# --- integration -------------------------------------------------------------

@pytest.fixture(scope="module")
def ephemeral_driver():
    from uedcli.driver import Driver
    from uedcli import editor as editor_mod

    editor_id = str(uuid.uuid4())
    container = editor_mod.ensure_editor(editor_id)
    try:
        yield Driver(container=container)
    finally:
        editor_mod.stop_editor(editor_id)


@pytest.mark.integration
@pytest.mark.parametrize("case", sorted(g.CORPUS))
def test_live_capture_matches_frozen_fixture(ephemeral_driver, case):
    live = g.capture_case(ephemeral_driver, g.CORPUS[case](), case=case)
    assert live["counts"]["surfs"] > 0, f"{case}: live capture produced no surfs"
    if not g.fixture_path(case).exists():
        pytest.skip(f"{case}: no frozen fixture to compare against yet")
    ok, diff = g.compare(live, g.load_fixture(case))
    assert ok, f"{case}: live capture drifted from frozen fixture:\n{diff}"
