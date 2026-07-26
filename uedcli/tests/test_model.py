from decimal import Decimal

from uedcli.model import parse_t3d, parse_t3d_actors
from uedcli.tests.conftest import read_fixture


def _named(name):
    return f"Begin Actor Class=Light Name={name}\n    Name=\"{name}\"\nEnd Actor\n"


def test_parse_t3d_actors_preserves_duplicate_names():
    # parse_t3d_actors keeps every actor in order, even when Names collide — the ingest boundary
    # relies on this to uniquify (parse_t3d itself still collapses, by design, for stored levels).
    text = _named("Merlon") + _named("Merlon") + _named("Merlon")
    actors = parse_t3d_actors(text)
    assert [a.name for a in actors] == ["Merlon", "Merlon", "Merlon"]


def test_parse_t3d_still_collapses_duplicate_names():
    # The Name-keyed dict is correct for a stored (unique-Name) level; document that it collapses.
    level = parse_t3d(_named("Merlon") + _named("Merlon"))
    assert len(level.actors) == 1


def test_parse_vertices_are_exact_decimal():
    level = parse_t3d(read_fixture("brush_subtract.t3d"))
    p = level.actors["Brush938"].brush.polys[0]
    assert all(isinstance(c, Decimal) for c in p.vertices[0])


def test_parse_preserves_fractional_vertex_exactly():
    # Fractional vertices (semisolids, editor CSG float-noise) parse with no binary drift.
    level = parse_t3d(
        "Begin Map\nBegin Actor Class=Brush Name=B1\n"
        "   Begin Brush Name=M\n     Begin PolyList\n"
        "      Begin Polygon\n"
        "       Vertex   -00479.999969,+00032.500000,+00192.000000\n"
        "      End Polygon\n     End PolyList\n   End Brush\n"
        '   Name="B1"\nEnd Actor\nEnd Map'
    )
    v = level.actors["B1"].brush.polys[0].vertices[0]
    assert v == (Decimal("-479.999969"), Decimal("32.5"), Decimal("192"))


def test_parse_location_as_decimal():
    level = parse_t3d(
        "Begin Map\nBegin Actor Class=Brush Name=B1\n"
        "   Location=(X=32.500000,Y=2000.000000,Z=0.000000)\n"
        '   Name="B1"\nEnd Actor\nEnd Map'
    )
    loc = level.actors["B1"].location
    assert loc == (Decimal("32.5"), Decimal("2000"), Decimal("0"))
    assert all(isinstance(c, Decimal) for c in loc)


def test_parse_single_light():
    level = parse_t3d(read_fixture("add_light.t3d"))
    assert list(level.actors) == ["SpikeProbeLight999"]
    a = level.actors["SpikeProbeLight999"]
    assert a.cls == "Light"
    assert a.location == (12345.0, 6789.0, 4242.0)
    assert a.brush is None
    # raw property lines preserved (order, verbatim values)
    assert ("LightBrightness", "200") in a.props
    assert ("Tag", "SpikeProbe") in a.props


def test_parse_subtract_brush():
    level = parse_t3d(read_fixture("brush_subtract.t3d"))
    a = level.actors["Brush938"]
    assert a.cls == "Brush"
    assert a.brush is not None
    assert a.brush.model_name == "Model823"
    assert len(a.brush.polys) == 6
    p0 = a.brush.polys[0]
    assert p0.item == "OUTSIDE"
    assert p0.texture_u == (1.0, 0.0, 0.0)
    assert p0.vertices[0] == (96.0, 192.0, 192.0)
    assert len(p0.vertices) == 4


def test_split_face_cube_has_seven_polys():
    # a 7-poly split-face cube must parse as 7 (no coplanar merge)
    level = parse_t3d(read_fixture("split7.t3d"))
    (a,) = level.actors.values()
    assert len(a.brush.polys) == 7


def test_parse_location_with_omitted_zero_component():
    # UnrealEd omits zero Location components on export (Z=0 dropped). The parser
    # must still read the actor's position, defaulting the absent axis to 0.0.
    level = parse_t3d(
        "Begin Map\nBegin Actor Class=Brush Name=B1\n"
        "   Location=(X=2000.000000,Y=2000.000000)\n"
        '   Name="B1"\nEnd Actor\nEnd Map'
    )
    assert level.actors["B1"].location == (2000.0, 2000.0, 0.0)


def test_level_order_field_survives_normalize_resort():
    from uedcli.model import parse_t3d
    from uedcli.normalize import normalize_level, level_order
    from uedcli.tests.test_normalize import _TWO_BRUSHES
    lv = parse_t3d(_TWO_BRUSHES)
    lv.order = level_order(lv)            # capture BEFORE normalize re-sorts actors
    normalize_level(lv)                   # re-sorts level.actors by Name
    assert lv.order == ["B_first", "Lamp", "B_second"]   # order preserved on the Level


def test_it_parses_indexed_array_props_verbatim():
    t3d = (
        "Begin Map\n"
        "Begin Actor Class=Mover Name=Door1\n"
        "    KeyPos(1)=(Z=256.000000)\n"
        "    KeyRot(1)=(Yaw=16384)\n"
        "    MultiSkins(2)=Texture'Pkg.Skin'\n"
        "    NumKeys=3\n"
        '    Name="Door1"\n'
        "End Actor\n"
        "End Map\n"
    )
    level = parse_t3d(t3d)
    props = dict(level.actors["Door1"].props)
    assert props["KeyPos(1)"] == "(Z=256.000000)"
    assert props["KeyRot(1)"] == "(Yaw=16384)"
    assert props["MultiSkins(2)"] == "Texture'Pkg.Skin'"
    assert props["NumKeys"] == "3"
