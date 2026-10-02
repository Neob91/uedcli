import copy
from unittest import mock

import pytest

from uedcli.model import Actor, parse_t3d
from uedcli.tests.conftest import read_fixture
from uedcli.writes import (
    actor_bounds,
    add_actor,
    allocate_name,
)


def test_add_actor_sets_grid_then_importadds():
    drv = mock.Mock()
    a = Actor(name="NewLight1", cls="Light", location=(100.0, 200.0, 300.0),
              props=[("LightBrightness", "200")])
    with mock.patch("uedcli.writes._write_container_file", return_value="/repo/Temp/x.t3d") as wf:
        add_actor(drv, a)
    drv.set_grid.assert_called_once_with(1, 1, 1)
    drv.map_importadd.assert_called_once_with("/repo/Temp/x.t3d")
    # the written snippet is a Begin Map block naming the actor
    written = wf.call_args[0][1]
    assert "Begin Actor Class=Light Name=NewLight1" in written


def test_add_brush_uses_paste_with_drift_compensation():
    """Brushes must enter via EDIT PASTE (not IMPORTADD — those are unselectable),
    pre-shifted -32uu on every axis to cancel the paste drift, with Brush= after
    the block."""
    drv = mock.Mock()
    a = parse_t3d(read_fixture("brush_subtract.t3d")).actors["Brush938"]
    a = copy.deepcopy(a)
    a.name = "UedcliBrush0"
    a.location = (100.0, 200.0, 300.0)
    add_actor(drv, a)
    drv.map_importadd.assert_not_called()          # NOT the importadd path
    drv.set_clipboard.assert_called_once()
    drv.edit_paste.assert_called_once()
    pasted = drv.set_clipboard.call_args[0][0]
    # location pre-shifted by -32 on each axis (100->68, 200->168, 300->268)
    assert "Location=(X=68.000000,Y=168.000000,Z=268.000000)" in pasted
    # Brush= reference present and AFTER the End Brush block (selectability fix)
    assert "Brush=Model'MyLevel" in pasted
    assert pasted.index("End Brush") < pasted.index("Brush=Model'MyLevel")


def test_allocate_name_avoids_existing():
    level = parse_t3d(
        "Begin Map\nBegin Actor Class=Light Name=UedcliLight0\n    Name=\"UedcliLight0\"\nEnd Actor\nEnd Map")
    name = allocate_name(level, "Light")
    assert name == "UedcliLight1"           # skips the taken UedcliLight0
    assert name not in level.actors


def test_add_actor_rejects_live_name_collision():
    drv = mock.Mock()
    level = parse_t3d(
        "Begin Map\nBegin Actor Class=Light Name=L1\n    Name=\"L1\"\nEnd Actor\nEnd Map")
    a = Actor(name="L1", cls="Light", location=(0.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="collision|exists"):
        add_actor(drv, a, level=level)      # IMPORTADD on a live name would DUPLICATE — refuse
    drv.map_importadd.assert_not_called()


def test_add_actor_updates_level_on_success():
    drv = mock.Mock()
    level = parse_t3d("Begin Map\nEnd Map")
    a = Actor(name="UedcliLight0", cls="Light", location=(0.0, 0.0, 0.0))
    with mock.patch("uedcli.writes._write_container_file", return_value="/repo/Temp/x.t3d"):
        add_actor(drv, a, level=level)
    assert "UedcliLight0" in level.actors


def test_actor_bounds_of_brush():
    a = parse_t3d(read_fixture("brush_subtract.t3d")).actors["Brush938"]
    (lo, hi) = actor_bounds(a)
    assert lo[0] <= hi[0] and lo[1] <= hi[1] and lo[2] <= hi[2]


def test_actor_bounds_honours_prepivot():
    from decimal import Decimal
    from uedcli.builders import cube, make_brush_actor
    a = make_brush_actor("B", cube(64, 64, 64), location=(Decimal(100), Decimal(0), Decimal(0)))
    lo0, hi0 = actor_bounds(a)
    a.props.append(("PrePivot", "(X=10.000000,Y=0.000000,Z=0.000000)"))
    lo1, hi1 = actor_bounds(a)
    # PrePivot=(10,0,0): world = Location + (v − PrePivot) → bounds shift −10 in X, Y/Z unchanged.
    assert (lo1[0], hi1[0]) == (lo0[0] - 10, hi0[0] - 10)
    assert (lo1[1], hi1[1], lo1[2], hi1[2]) == (lo0[1], hi0[1], lo0[2], hi0[2])


