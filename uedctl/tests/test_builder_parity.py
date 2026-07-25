"""OFFLINE builder world-geometry parity (default suite — no editor needed).

Asserts every builder still emits the world vertices the live editor reconstructed
when the golden fixture was blessed. This is the continuous regression guard on
builders.py geometry; the live editor side (emit/winding/CSG faithfulness + re-bless)
lives in test_builder_parity_capture.py. See builder_parity_cases.py for what the
fixture proves and how it was captured.
"""
import pytest

from uedctl.tests.builder_parity_cases import (
    CASES, PARITY_TOL, builder_poly_count, builder_world_verts, load_fixture,
    worst_err)


def test_it_covers_exactly_the_registered_cases():
    # The fixture and the live registry must not drift apart silently.
    assert set(load_fixture()["cases"]) == set(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_it_matches_the_golden_world_geometry(name):
    golden = load_fixture()["cases"][name]
    expected_verts = [tuple(v) for v in golden["verts"]]
    assert expected_verts, f"{name}: empty golden fixture (precondition)"

    result = CASES[name]()
    observed = builder_world_verts(result)

    # Same vertex set (count + bidirectional nearest-neighbour within tolerance): a
    # missing/extra vertex or a moved corner fails. Both directions catch a builder
    # vertex that drifted away from every golden corner, not just the reverse. NOTE:
    # the set is winding-invariant — a flipped face is caught only on the live path
    # (test_builder_parity_capture), never here. See builder_parity_cases for scope.
    assert len(observed) == len(expected_verts), (
        f"{name}: builder has {len(observed)} world verts, golden has {len(expected_verts)}")
    err = max(worst_err(expected_verts, observed), worst_err(observed, expected_verts))
    assert err <= PARITY_TOL, (
        f"{name}: builder world geometry drifted from golden "
        f"(worst {err:.6f}uu > {PARITY_TOL}uu) — re-bless or a builders.py regression")

    # Structural guard the vertex set can't give: a dropped/duplicated face that moves
    # no unique corner changes the face count but not the set.
    assert builder_poly_count(result) == golden["polys"], (
        f"{name}: builder emits {builder_poly_count(result)} faces, golden has {golden['polys']}")
