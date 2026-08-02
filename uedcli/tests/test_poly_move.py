"""`brush poly move --by` — translate whole faces (all a face's welded corners at once), model-side.

Model-level tests exercise `surface.apply_move` directly; CLI-level tests drive the verb through the
real parser + `dispatch` with a mocked level source, mirroring `test_vertex.py`.
"""
import io
from decimal import Decimal
from unittest import mock

import pytest

from uedcli.builders import cube, make_brush_actor
from uedcli.geometry import GeometryError
from uedcli.model import Actor, Level
from uedcli.surface import apply_move
from uedcli.vertex import weld_vertices

# Cube face indices (builders.cube order): 0 +X, 1 -X, 2 +Y, 3 -Y, 4 +Z (top), 5 -Z.


def _D(*xyz):
    return tuple(Decimal(str(c)) for c in xyz)


def _cube_level(*names: str) -> Level:
    lvl = Level()
    for name in names:
        lvl.actors[name] = make_brush_actor(name, cube(64, 64, 64), location=_D(0, 0, 0))
    lvl.order = list(names)
    return lvl


def _corner_zs(actor: Actor) -> set:
    return {w.coord[2] for w in weld_vertices(actor.brush)}


# --- model: apply_move -----------------------------------------------------------


def test_apply_move_raises_a_cube_top_face_and_stays_watertight():
    lvl = _cube_level("B1")
    assert _corner_zs(lvl.actors["B1"]) == {Decimal(-32), Decimal(32)}   # precondition
    touched = apply_move(lvl, ["B1:4"], by=_D(0, 0, 64))
    assert touched == ["B1"]
    welds = weld_vertices(lvl.actors["B1"].brush)
    assert len(welds) == 8                                    # still 8 corners: closed solid
    assert all(len(w.refs) == 3 for w in welds)              # each still shared by 3 faces
    # the four top corners rose +64 (to +96), the four bottom stayed put — sides are now taller
    assert _corner_zs(lvl.actors["B1"]) == {Decimal(-32), Decimal(96)}


def test_apply_move_in_plane_delta_shears_the_brush_and_stays_valid():
    # A whole-face move by a constant delta keeps every quad neighbour a planar TRAPEZOID, so an
    # in-plane (non-normal) shear of a cube face is VALID — it deforms the cube into a parallelepiped,
    # it is not rejected. This contradicts the spec's "most non-axis moves rejected"; see board item
    # `brush-poly-move-spec-help-most-non-axis-moves`.
    lvl = _cube_level("B1")
    apply_move(lvl, ["B1:4"], by=_D(32, 0, 0))               # slide the top face along +X
    welds = weld_vertices(lvl.actors["B1"].brush)
    assert len(welds) == 8 and all(len(w.refs) == 3 for w in welds)
    top = {w.coord for w in welds if w.coord[2] == Decimal(32)}
    assert top == {_D(0, -32, 32), _D(0, 32, 32), _D(64, -32, 32), _D(64, 32, 32)}


def test_apply_move_that_collapses_the_solid_is_rejected():
    # The rejection path: dropping the top face onto the bottom coincides corners / zeroes the side
    # faces' area, which `validate_brush` (inside move_vertices) rejects as degenerate.
    lvl = _cube_level("B1")
    with pytest.raises(GeometryError):
        apply_move(lvl, ["B1:4"], by=_D(0, 0, -64))


def test_apply_move_maps_the_world_delta_through_the_brushs_rotation():
    # Yaw 90°: local +X → world +Y, so a world (0,64,0) delta becomes local (64,0,0), which moves the
    # +X face along its OWN normal (the safe case). The mapping is what makes that valid, not an
    # in-plane shear — assert the local delta differs from the world one, then assert the geometry.
    from uedcli.rotation import world_to_local_delta
    lvl = _cube_level("B1")
    lvl.actors["B1"].props.append(("Rotation", "(Yaw=16384)"))
    local = world_to_local_delta(lvl.actors["B1"], _D(0, 64, 0))
    assert abs(float(local[0]) - 64.0) < 1e-4 and abs(float(local[1])) < 1e-4   # != world (0,64,0)
    apply_move(lvl, ["B1:0"], by=_D(0, 64, 0))
    welds = weld_vertices(lvl.actors["B1"].brush)
    assert len(welds) == 8
    xs = {w.coord[0] for w in welds}
    assert xs == {Decimal(-32), Decimal(96)}                 # +X face pushed from local x=32 to 96


def test_apply_move_translates_each_brush_in_a_multi_brush_set_independently():
    lvl = _cube_level("B1", "B2")
    touched = apply_move(lvl, ["B1:4", "B2:4"], by=_D(0, 0, 64))
    assert touched == ["B1", "B2"]
    assert _corner_zs(lvl.actors["B1"]) == {Decimal(-32), Decimal(96)}
    assert _corner_zs(lvl.actors["B2"]) == {Decimal(-32), Decimal(96)}


def test_apply_move_moves_a_shared_corner_once_when_all_faces_are_selected():
    # Every corner of a cube is touched by 3 faces; selecting all 6 lists each shared corner 3 times.
    # `move_vertices` rejects a repeated selector, so apply_move MUST weld-dedupe first — otherwise
    # this valid whole-brush translation would exit 2 on `duplicate --at selector`.
    lvl = _cube_level("B1")
    apply_move(lvl, ["B1:all"], by=_D(0, 0, 64))             # pure translation of the whole brush
    welds = weld_vertices(lvl.actors["B1"].brush)
    assert len(welds) == 8 and all(len(w.refs) == 3 for w in welds)
    assert _corner_zs(lvl.actors["B1"]) == {Decimal(32), Decimal(96)}   # every corner +64


def test_apply_move_dedupes_a_corner_two_selected_adjacent_faces_share():
    # +X (0) and +Z (4) share the edge (32,±32,32). The naive concatenation lists each shared corner
    # twice, and move_vertices rejects a repeated selector (`duplicate --at selector`). apply_move
    # weld-dedupes first, so this valid move succeeds instead of exiting 2 on a spurious duplicate.
    lvl = _cube_level("B1")
    touched = apply_move(lvl, ["B1:0", "B1:4"], by=_D(0, 0, 64))   # no raise
    assert touched == ["B1"]
    welds = weld_vertices(lvl.actors["B1"].brush)
    assert len(welds) == 8 and all(len(w.refs) == 3 for w in welds)  # watertight


def test_apply_move_rejects_an_out_of_range_poly_index_naming_the_brush():
    lvl = _cube_level("B1")
    with pytest.raises(ValueError, match="B1.*out of range"):
        apply_move(lvl, ["B1:99"], by=_D(0, 0, 64))


def test_apply_move_rejects_a_non_brush_actor():
    lvl = Level()
    lvl.actors["P1"] = Actor(name="P1", cls="Light")         # point actor: no brush
    lvl.order = ["P1"]
    with pytest.raises(ValueError, match="P1.*not a brush"):
        apply_move(lvl, ["P1:0"], by=_D(0, 0, 64))


# --- CLI: brush poly move --------------------------------------------------------


def _dispatch(argv, src):
    from uedcli.cli import dispatch as dispatch_mod
    from uedcli.cli import level_sources
    from uedcli.cli.main import build_parser
    args = build_parser().parse_args(argv)
    with mock.patch.object(level_sources, "resolve_level_source", return_value=src):
        return dispatch_mod.dispatch(args)


def test_cli_move_empty_stdin_is_a_clean_no_op():
    src = mock.Mock()
    src.load.return_value = _cube_level("B1")
    with mock.patch("sys.stdin", io.StringIO("")):
        rc = _dispatch(["brush", "poly", "move", "-", "--by", "0,0,64"], src)
    assert rc == 0
    src.save.assert_not_called()


def test_cli_move_out_of_range_index_is_a_clean_exit2_naming_the_brush(capsys):
    src = mock.Mock()
    src.load.return_value = _cube_level("B1")
    rc = _dispatch(["brush", "poly", "move", "B1:99", "--by", "0,0,64"], src)
    err = capsys.readouterr().err
    assert rc == 2 and "B1" in err and "out of range" in err
    assert "Traceback" not in err
    src.save.assert_not_called()


def test_cli_move_non_brush_actor_is_a_clean_exit2(capsys):
    lvl = Level()
    lvl.actors["P1"] = Actor(name="P1", cls="Light")
    lvl.order = ["P1"]
    src = mock.Mock()
    src.load.return_value = lvl
    rc = _dispatch(["brush", "poly", "move", "P1:0", "--by", "0,0,64"], src)
    err = capsys.readouterr().err
    assert rc == 2 and "P1" in err and "not a brush" in err
    assert "Traceback" not in err


def test_cli_move_degenerate_result_is_a_clean_exit2(capsys):
    # A collapsing move raises GeometryError (a ValueError) inside apply_move; _move catches it and
    # exits 2 cleanly, never a traceback, and writes nothing.
    src = mock.Mock()
    src.load.return_value = _cube_level("B1")
    rc = _dispatch(["brush", "poly", "move", "B1:4", "--by", "0,0,-64"], src)
    err = capsys.readouterr().err
    assert rc == 2 and "Traceback" not in err
    src.save.assert_not_called()


def test_cli_poly_find_piped_into_move_raises_the_top_face_end_to_end(capsys):
    lvl = _cube_level("B1")
    src = mock.Mock()
    src.load.return_value = lvl
    # `brush poly find --facing +Z` prints the top face as a BRUSH:idx selector on stdout.
    rc = _dispatch(["brush", "poly", "find", "B1", "--facing", "+Z"], src)
    found = capsys.readouterr().out
    assert rc == 0 and found.strip() == "B1:4"
    # feed that stdout into `brush poly move -` and confirm the top rose and the selector echoed.
    with mock.patch("sys.stdin", io.StringIO(found)):
        rc = _dispatch(["brush", "poly", "move", "-", "--by", "0,0,64"], src)
    out = capsys.readouterr().out
    assert rc == 0 and out.strip() == "B1:4"                  # touched selectors on stdout
    assert _corner_zs(lvl.actors["B1"]) == {Decimal(-32), Decimal(96)}
    src.save.assert_called_once()
    assert src.save.call_args.kwargs["verb"] == "poly-move"
    assert src.save.call_args.kwargs["args"] == {"targets": ["B1:4"], "by": ["0", "0", "64"]}
