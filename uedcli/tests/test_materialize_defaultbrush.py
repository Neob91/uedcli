"""`assemble_unbuilt` ALWAYS synthesizes the simple builder brush (`DefaultBrush` + shape `Brush`
+ `Polys4`; owner ruling 2026-09-03 -- UED22 adopts Actors[1] as its builder and excludes it from
CSG at every rebuild, so without a sacrificial builder the first content brush's geometry is
silently lost). A trunk actor colliding with a reserved name must raise `_reserve`'s
duplicate-name error (clean exit 2), never be silently dropped. Install-free: engine-only probe,
no schema/pkg_dirs."""
from __future__ import annotations

import struct

import pytest

from uedcli import model
from uedcli.native.pkg_write import parse_package
from uedcli.native.unbuilt import assemble_unbuilt
from uedcli.normalize import level_order, normalize_level
from uedcli.upackage import _parse_package, read_compact_index, read_property_tags

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


def _export(pk, name: str):
    return next(e for i, e in enumerate(pk.exports) if pk.names[e["nm"]] == name)


def _actor_tags(pk, name: str):
    """The property tags of an actor export, past its StateFrame."""
    e = _export(pk, name)
    pos, end = e["soff"], e["soff"] + e["ssize"]
    node, pos = read_compact_index(pk.buf, pos)         # StateFrame (RF_HasStack)
    _sn, pos = read_compact_index(pk.buf, pos)
    pos += 12
    if node != 0:
        _off, pos = read_compact_index(pk.buf, pos)
    return read_property_tags(pk, pos, end)[0]


def test_synthesized_builder_carries_editor_import_stamps():
    """The synthesized builder brush matches the editor's imported builder byte-for-byte (owner
    ruling 2026-09-04, N=1 gate): the `DefaultBrush` actor carries `Tag=Brush` + a `Region`
    PointRegion (Zone=the LevelInfo); the `Brush` shape model ships the cube's computed bbox and
    RootOutside=Linked=1; and the `Polys4` cube polys carry CalcNormal-recomputed normals (winding
    flips the authored (0,0,1) to (0,0,-1))."""
    dx_bytes, _w = assemble_unbuilt(_level_with_brush("Room_1"), schema=None, pkg_dirs=None)
    pk = _parse_package(dx_bytes, "t.dx", None)

    tags = {t.name: t for t in _actor_tags(pk, "DefaultBrush")}
    assert "Tag" in tags and pk.names[read_compact_index(tags["Tag"].raw, 0)[0]] == "Brush"
    assert "Region" in tags and tags["Region"].struct_name == "PointRegion"
    li = _export(pk, "LevelInfo0")
    zone_ref, off = read_compact_index(tags["Region"].raw, 0)
    assert pk.object_path(zone_ref).endswith("LevelInfo0")
    assert struct.unpack_from("<i", tags["Region"].raw, off)[0] == -1        # iLeaf

    # The builder shape model: cube bbox computed + valid (read raw -- FBox is min/max/valid right
    # after the empty-prop None terminator). An empty model (the pre-fix bug) has all-zero, valid=0.
    e = _export(pk, "Brush")
    pos = e["soff"]
    _none, pos = read_compact_index(pk.buf, pos)
    bbox_min = struct.unpack_from("<3f", pk.buf, pos); pos += 12
    bbox_max = struct.unpack_from("<3f", pk.buf, pos); pos += 12
    assert pk.buf[pos] == 1                              # FBox IsValid
    assert bbox_min == (-128.0, -128.0, -128.0) and bbox_max == (128.0, 128.0, 128.0)

    e = _export(pk, "Polys4")
    pos = e["soff"]
    _none, pos = read_compact_index(pk.buf, pos)
    pos += 8                                            # poly count (i32) + Max (i32)
    _nv, pos = read_compact_index(pk.buf, pos)          # vertex count
    _base = struct.unpack_from("<3f", pk.buf, pos); pos += 12
    normal = struct.unpack_from("<3f", pk.buf, pos)
    assert normal == (0.0, 0.0, -1.0)                   # CalcNormal-recomputed, not authored (0,0,1)


def _level_no_levelinfo() -> model.Level:
    """A trunk with a placed actor but NO LevelInfo -- the editor always has one, so native must
    synthesize it (the Island-N=1 case, where the LevelInfo is not among the first-N actors)."""
    t3d = ("Begin Map\n"
           "Begin Actor Class=Engine.PathNode Name=PathNode0\n    Name=\"PathNode0\"\nEnd Actor\n"
           "End Map\n")
    lv = model.parse_t3d(t3d)
    lv.order = level_order(lv)
    normalize_level(lv)
    return lv


def test_synthesized_levelinfo_carries_tag_and_solid_region():
    """A trunk without a LevelInfo makes native synthesize one, matching what the editor spawns:
    `Tag=LevelInfo` (class-default) + a solid `Region` (Zone=self, iLeaf=-1, ZoneNumber=0). The
    editor never spatially zones the LevelInfo, so the Region stays solid (Island N=1 golden)."""
    dx_bytes, _w = assemble_unbuilt(_level_no_levelinfo(), schema=None, pkg_dirs=None)
    pk = _parse_package(dx_bytes, "t.dx", None)
    tags = {t.name: t for t in _actor_tags(pk, "LevelInfo0")}
    assert "Tag" in tags and pk.names[read_compact_index(tags["Tag"].raw, 0)[0]] == "LevelInfo"
    assert "Region" in tags and tags["Region"].struct_name == "PointRegion"
    zone_ref, off = read_compact_index(tags["Region"].raw, 0)
    assert pk.object_path(zone_ref).endswith("LevelInfo0")          # Zone=self
    assert struct.unpack_from("<i", tags["Region"].raw, off)[0] == -1   # iLeaf solid
    assert tags["Region"].raw[off + 4] == 0                            # ZoneNumber solid


def test_levelinfo_region_not_zoned_in_built_world(monkeypatch):
    """`_trunk_to_actorspecs` recomputes every PLACED actor's Region from the built BSP EXCEPT the
    LevelInfo, which the editor never zones (byte-measured OceanLab N=3: builder + LevelInfo both at
    the origin, golden zones the builder but leaves the LevelInfo solid)."""
    from uedcli.native import materialize
    from uedcli.native.actor_write import StructValue

    monkeypatch.setattr(materialize, "_model_point_region", lambda _m, _p: (99, 7))
    t3d = ("Begin Map\n"
           "Begin Actor Class=Engine.LevelInfo Name=LevelInfo0\n    Name=\"LevelInfo0\"\nEnd Actor\n"
           "Begin Actor Class=Engine.PathNode Name=PathNode0\n    Name=\"PathNode0\"\nEnd Actor\n"
           "End Map\n")
    lv = model.parse_t3d(t3d)
    lv.order = level_order(lv)
    normalize_level(lv)

    class _FakeWorld:                                    # truthy .nodes triggers the recompute path
        nodes = [1]

    actors, _brushes, _w = materialize._trunk_to_actorspecs(
        lv, lambda _fqcn: {}, world_model=_FakeWorld())
    region = {a.name: next(p for p in a.props if p.name == "Region") for a in actors}

    def leaf_zone(prop):
        m: StructValue = prop.value
        return m.members[1].value, m.members[2].value

    assert leaf_zone(region["LevelInfo0"]) == (-1, 0)   # NOT zoned
    assert leaf_zone(region["PathNode0"]) == (99, 7)    # zoned from the BSP
