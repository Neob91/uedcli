"""`uedcli_native`'s point-in-solid query, against the SAME scenario and the SAME expected answers
that `test_csg_kind_facts.py` already pins with its own Python port of the walk.

That file's `point_is_solid` is the reference: it is a direct port of the zero-extent form of the
engine's collision walk (`linecheck.rs`'s `is_csg`/`combine_state`/`child` plus `collision.rs`'s
entry state), it is what the spike's 1522-actor clearance measurement used, and it is already
committed and green. The native query must agree with it exactly — that is what makes this a real
regression rather than a restatement.
"""
from __future__ import annotations

import pytest

from uedcli.tests.test_csg_kind_facts import LEFT, RIGHT, _solve, point_is_solid

uedcli_native = pytest.importorskip("uedcli_native")


@pytest.mark.parametrize("kind,left,right", [
    ("add", True, False),            # an Add contributes solid; a later Subtract carves it
    ("semisolid", True, True),       # contributes solid, and no Subtract can carve it
    ("nonsolid", False, False),      # contributes no solid at all
])
def test_native_point_is_solid_matches_the_committed_python_walk(kind, left, right):
    _, _, model = _solve(kind)
    built = _built(kind)
    sol = built.solidity()
    assert sol.point_is_solid(LEFT) is left
    assert sol.point_is_solid(RIGHT) is right
    # ...and agrees with the reference walk over the same parsed model, not just with the table.
    assert sol.point_is_solid(LEFT) == point_is_solid(model, LEFT)
    assert sol.point_is_solid(RIGHT) == point_is_solid(model, RIGHT)


def test_any_point_solid_is_true_when_any_sample_is_inside_solid():
    built = _built("add")
    sol = built.solidity()
    assert sol.any_point_solid([RIGHT, LEFT]) is True     # LEFT is solid
    assert sol.any_point_solid([RIGHT]) is False          # the carved half is not
    assert sol.any_point_solid([]) is False


def test_solidity_is_not_point_check_negated():
    """`CollisionModel::point_check` answers the BOX question via the terminal leaf's collision
    hull, and returns true for FREE space (`collision.rs:236`). This query is the zero-extent NODE
    walk instead — the one the spike measured with. Pinned so a later 'simplification' to
    `not point_check(...)` trips here."""
    import inspect
    src = (_repo_root() / "uedcli-native" / "src" / "lib.rs").read_text()
    assert "point_is_solid" in src
    assert "point_check" not in src, "lib.rs must not expose the free-space box query"
    del inspect


def _repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[2]


def _built(kind):
    """The same three-brush scenario `test_csg_kind_facts._solve` builds, but returning the native
    `Built` handle rather than the parsed model. Uses that module's own `_brush` so the geometry can
    never drift from the committed regression's."""
    import dataclasses  # noqa: F401  (kept in sync with test_csg_kind_facts' own imports)
    from uedcli import preview_native as pn
    from uedcli.tests.test_csg_kind_facts import PF_NOTSOLID, PF_SEMISOLID, _brush
    oper, flags = {
        "add": ("CSG_Add", 0),
        "semisolid": ("CSG_Add", PF_SEMISOLID),
        "nonsolid": ("CSG_Add", PF_NOTSOLID),
    }[kind]
    actors = [_brush("Room", (1024, 1024, 1024), (0, 0, 0), "CSG_Subtract"),
              _brush("Pillar", (128, 128, 512), (0, 0, 0), oper, flags),
              _brush("Cutter", (256, 256, 256), (128, 0, 0), "CSG_Subtract")]
    return uedcli_native.build_geometry_bspcsg([pn._marshal_brush(a) for a in actors])
