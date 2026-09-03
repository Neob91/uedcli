"""`assemble_unbuilt` ALWAYS synthesizes the simple builder brush (`DefaultBrush` + shape `Brush`
+ `Polys4`; owner ruling 2026-09-03 -- UED22 adopts Actors[1] as its builder and excludes it from
CSG at every rebuild, so without a sacrificial builder the first content brush's geometry is
silently lost). A trunk actor colliding with a reserved name must raise `_reserve`'s
duplicate-name error (clean exit 2), never be silently dropped. Install-free: engine-only probe,
no schema/pkg_dirs."""
from __future__ import annotations

import pytest

from uedcli import model
from uedcli.native.pkg_write import parse_package
from uedcli.native.unbuilt import assemble_unbuilt
from uedcli.normalize import level_order, normalize_level

_POLY = ("         Begin Polygon\n"
         "            Origin   +0.0,+0.0,+0.0\n"
         "            Normal   +0.0,+0.0,+1.0\n"
         "            TextureU +1.0,+0.0,+0.0\n"
         "            TextureV +0.0,+1.0,+0.0\n"
         "            Vertex   +0.0,+0.0,+0.0\n"
         "            Vertex   +128.0,+0.0,+0.0\n"
         "            Vertex   +128.0,+128.0,+0.0\n"
         "            Vertex   +0.0,+128.0,+0.0\n"
         "         End Polygon\n")


def _level_with_brush(name: str) -> model.Level:
    t3d = ("Begin Map\n"
           "Begin Actor Class=Engine.LevelInfo Name=LevelInfo0\n    Name=\"LevelInfo0\"\nEnd Actor\n"
           f"Begin Actor Class=Engine.Brush Name={name}\n    CsgOper=CSG_Subtract\n"
           f"    Begin Brush Name=Model_{name}\n       Begin PolyList\n{_POLY}       End PolyList\n"
           f"    End Brush\n    Brush=Model'MyLevel.Model_{name}'\n    Name=\"{name}\"\nEnd Actor\n"
           "End Map\n")
    lv = model.parse_t3d(t3d)
    lv.order = level_order(lv)
    normalize_level(lv)
    return lv


def test_defaultbrush_named_trunk_actor_is_rejected_not_dropped():
    with pytest.raises(ValueError, match="DefaultBrush"):
        assemble_unbuilt(_level_with_brush("DefaultBrush"), schema=None, pkg_dirs=None)


def test_normal_brush_name_assembles_with_synthesized_builder():
    dx_bytes, _warnings = assemble_unbuilt(_level_with_brush("Room_1"), schema=None, pkg_dirs=None)
    p = parse_package(dx_bytes)
    names = {p.names[e["nm"]] for e in p.exports}
    assert {"Room_1", "DefaultBrush", "Brush", "Polys4"} <= names
