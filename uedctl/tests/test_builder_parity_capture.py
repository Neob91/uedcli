"""LIVE builder world-geometry parity (integration, gated).

Deselected by default (pytest.ini: addopts = -m "not integration"). Run with:
    pytest uedctl/tests/test_builder_parity_capture.py -m integration -v

For each registered builder case, drives the real editor (DEINTERSECTION cavity
readout) and asserts the editor's reconstructed world vertices match BOTH the
builder's claimed world vertices (the live parity check on emit/winding/CSG) AND
the committed golden (the fixture is still valid). Re-bless the golden with:
    python -m uedctl.tests.builder_parity_cases

See builder_parity_cases.py for the capture method and the honest scope of what
this proves (it does NOT compare our builder algorithm to UED's GUI-only one).
"""
import pytest

from uedctl.driver import Driver
from uedctl.tests.builder_parity_cases import (
    CASES, CONTAINER, OFFLINE_ONLY, PARITY_TOL, builder_world_verts,
    capture_world_verts, load_fixture, worst_err)

pytestmark = pytest.mark.integration

# OFFLINE_ONLY cases (the single non-convex staircase brush) can't be editor-reconstructed via
# DEINTERSECTION (the combined cavity invents interior vertices); they keep only offline value
# goldens (test_builder_parity). See builder_parity_cases.OFFLINE_ONLY.
LIVE_CASES = sorted(set(CASES) - OFFLINE_ONLY)


@pytest.fixture(scope="module")
def driver():
    return Driver(container=CONTAINER)


@pytest.mark.parametrize("name", LIVE_CASES)
def test_it_reconstructs_the_builder_world_geometry_live(driver, name):
    expected = builder_world_verts(CASES[name]())
    golden = [tuple(v) for v in load_fixture()["cases"][name]["verts"]]
    assert expected, f"{name}: builder produced no world vertices (precondition)"

    editor = capture_world_verts(driver, name)

    # The editor reconstructs the same vertex set the builder emits ...
    assert len(editor) == len(expected), (
        f"{name}: editor reconstructed {len(editor)} verts, builder claims {len(expected)} "
        f"— winding/CSG faithfulness broken")
    live_err = max(worst_err(expected, editor), worst_err(editor, expected))
    assert live_err <= PARITY_TOL, (
        f"{name}: editor vs builder worst {live_err:.6f}uu > {PARITY_TOL}uu")
    # ... and that set still equals the committed golden.
    gold_err = max(worst_err(golden, editor), worst_err(editor, golden))
    assert len(editor) == len(golden) and gold_err <= PARITY_TOL, (
        f"{name}: editor drifted from golden (worst {gold_err:.6f}uu) — re-bless if intended")
