"""`level photo --native --faces wire` — the perspective brush wireframe.

Deliberately NO `importorskip("uedcli_native")`: wire needs no native extension (no CSG solve),
and that these tests run and render with the extension absent is itself the guarantee."""
from __future__ import annotations

from decimal import Decimal

import pytest
from PIL import Image

from uedcli import preview_wire as pw
from uedcli.cli import dispatch
from uedcli.cli import main as cli
from uedcli.model import Actor, Level
from uedcli.preview import MARKER, _CSG_PALETTE
from uedcli.preview_shots import parse_shot
from uedcli.tests.conftest import cube_room

SUBTRACT = _CSG_PALETTE["subtract"][0]
BG = pw.BACKGROUND


def _level(*actors: Actor) -> Level:
    lvl = Level()
    for a in actors:
        lvl.actors[a.name] = a
        lvl.order.append(a.name)
    return lvl


def _pixels(path):
    im = Image.open(path).convert("RGB")
    data = im.tobytes()
    return im.size, [tuple(data[i:i + 3]) for i in range(0, len(data), 3)]


def test_wire_writes_pngs_at_requested_size(tmp_path):
    shots = [parse_shot("at:0,0,0;rot:0,0"), parse_shot("at:0,0,0;rot:0,90;name:east")]
    n = pw.render_shots(level=_level(cube_room()), shots=shots, out_dir=tmp_path / "out",
                        points={}, size=(160, 120), fov=75.0)
    assert n == 2
    for stem in ("shot-01", "east"):
        size, _ = _pixels(tmp_path / "out" / f"{stem}.png")
        assert size == (160, 120)


def test_wire_draws_csg_coloured_edges(tmp_path):
    """A subtract cube seen from inside draws gold (subtract-palette) edges over the background —
    pins the classify -> palette -> render wiring, not literal RGBs."""
    pw.render_shots(level=_level(cube_room()), shots=[parse_shot("at:0,0,0;rot:0,0")],
                    out_dir=tmp_path / "out", points={}, size=(160, 120), fov=75.0)
    _, px = _pixels(tmp_path / "out" / "shot-01.png")
    assert sum(1 for p in px if p != BG) > 0            # something drew
    assert SUBTRACT in set(px)                          # and in the subtract hue


def test_wire_projection_matches_render_rs():
    """The projector reproduces render.rs EXACTLY (focal = (w/2)/tan(fov/2), y down), so a wire shot
    frames identically to a textured shot at the same pose. render.rs's own round-trip: 90° hfov,
    200x100 -> focal 100; a point 10 right / 5 up at depth 100 lands at (110, 45)."""
    cam = pw._Camera((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), 90.0, (200, 100))
    assert cam.focal == pytest.approx(100.0)
    assert cam.to_px(cam.to_cam((100, 10, 5))) == (110, 45)


def test_wire_near_clips_geometry_behind_the_camera():
    """A segment wholly behind the near plane is dropped; one straddling it is clipped, not wrapped."""
    assert pw._clip_near((10.0, 0, 0), (20.0, 1, 1)) == ((10.0, 0, 0), (20.0, 1, 1))
    assert pw._clip_near((-5.0, 0, 0), (-1.0, 0, 0)) is None
    clipped = pw._clip_near((-6.0, 0, 0), (10.0, 0, 0))     # straddles depth=NEAR (4.0)
    assert clipped is not None and clipped[0][0] == pw.NEAR


def test_wire_draws_point_marker(tmp_path):
    """A point actor with no sprite draws a neutral marker at its projected Location."""
    node = Actor(name="Node", cls="Engine.PathNode",
                 location=(Decimal(200), Decimal(0), Decimal(0)))
    from uedcli.preview import PointRender
    pw.render_shots(level=_level(node), shots=[parse_shot("at:0,0,0;rot:0,0")],
                    out_dir=tmp_path / "out", points={"Node": PointRender(label="Node")},
                    size=(160, 120), fov=75.0)
    _, px = _pixels(tmp_path / "out" / "shot-01.png")
    assert MARKER in set(px)                            # the '+' marker landed


def test_wire_draws_point_sprite_billboard(tmp_path):
    """A point actor WITH a resolved sprite draws a perspective-sized billboard at its Location."""
    from uedcli.preview import PointRender
    red = PointRender(label="Lamp", sprite=(2, 2, b"\xff\x00\x00" * 4, b"\x01" * 4),
                      sprite_world=(48.0, 48.0))
    node = Actor(name="Lamp", cls="Engine.Light",
                 location=(Decimal(200), Decimal(0), Decimal(0)))
    pw.render_shots(level=_level(node), shots=[parse_shot("at:0,0,0;rot:0,0")],
                    out_dir=tmp_path / "out", points={"Lamp": red}, size=(160, 120), fov=75.0)
    _, px = _pixels(tmp_path / "out" / "shot-01.png")
    assert (255, 0, 0) in set(px)                       # the billboard blitted


def test_wire_empty_world_renders_blank_frame(tmp_path):
    """An empty trunk is a truthful blank schematic (exit 0), not an error — wire draws whatever
    geometry exists, brushes and/or point actors."""
    n = pw.render_shots(level=_level(), shots=[parse_shot("at:0,0,0;rot:0,0")],
                        out_dir=tmp_path / "out", points={}, size=(64, 48), fov=75.0)
    assert n == 1
    _, px = _pixels(tmp_path / "out" / "shot-01.png")
    assert set(px) == {BG}


def test_faces_rejected_under_game(tmp_path, capsys):
    """--faces is --native only; under --game (the default backend) it exits 2 naming it."""
    args = cli.build_parser().parse_args(
        ["level", "photo", "--faces", "wire", "--out-dir", str(tmp_path / "o"),
         "at:0,0,0;rot:0,0"])
    assert dispatch.dispatch(args) == 2
    assert "--faces requires --native" in capsys.readouterr().err
