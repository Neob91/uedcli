"""Offline tests for the N-3 typed-property conversion + import/name synthesis.

Seed a synthetic class schema (no game `.u` needed) and assert `props.convert_actor_props`
emits correctly-TYPED `FPropertyTag`s, and that assembly synthesizes real texture/class imports
and a self-check-passing multi-actor `.dx`.  Pure-Python (no Rust ext, no editor).
"""
from __future__ import annotations

import struct

import pytest

from uedcli.native import assemble as ASM
from uedcli.native import materialize as M
from uedcli.native import umodel as UM
from uedcli.native import actor_write as AW
from uedcli.native.actor_write import Prop, PT_STRUCT, struct_vector
from uedcli.native.props import (convert_actor_props, convert_prop, ImportRef, PropError,
                                 _parse_struct_fields)
from uedcli.native.pkg_write import parse_package
from uedcli.native.codec import deref

from uedcli.tests.conftest import StubClassIndex

IDX = StubClassIndex()          # the offline class resolver `movers.is_mover` needs


class _SP:
    """A stand-in for `uprops.Prop` carrying only what the converter reads."""
    def __init__(self, name, kind, type_name=None, enum=()):
        self.name = name
        self.kind = kind
        self.type_name = type_name
        self.enum_value_names = enum


_SCHEMA = {
    "engine.brush": {
        "csgoper": _SP("CsgOper", "ByteProperty", "ECsgOper",
                       ("CSG_Active", "CSG_Add", "CSG_Subtract", "CSG_Intersect",
                        "CSG_Deintersect")),
        "polyflags": _SP("PolyFlags", "IntProperty"),
        "mainscale": _SP("MainScale", "StructProperty", "Scale"),
    },
    "engine.light": {
        "lightbrightness": _SP("LightBrightness", "ByteProperty"),
        "lightradius": _SP("LightRadius", "ByteProperty"),
        "bstatic": _SP("bStatic", "BoolProperty"),
        "tag": _SP("Tag", "NameProperty"),
        "event": _SP("Event", "NameProperty"),
        "skin": _SP("Skin", "ObjectProperty", "Texture"),
        "rotation": _SP("Rotation", "StructProperty", "Rotator"),
        "ambientglow": _SP("AmbientGlow", "ByteProperty"),
        "brightness": _SP("Brightness", "FloatProperty"),
        "info": _SP("Info", "StrProperty"),
    },
}


def _lookup(fqcn):
    return _SCHEMA.get(fqcn.casefold(), {})


def test_struct_field_parse_nested():
    f = _parse_struct_fields("(Scale=(X=2.0,Y=1.0,Z=1.0),SheerRate=0.0,SheerAxis=SHEER_ZX)")
    assert f["Scale"] == "(X=2.0,Y=1.0,Z=1.0)"
    assert f["SheerRate"] == "0.0" and f["SheerAxis"] == "SHEER_ZX"


def test_typed_conversion_covers_scalar_types():
    raw = [("PolyFlags", "8"), ("CsgOper", "CSG_Subtract"), ("MainScale", "(SheerAxis=SHEER_ZX)")]
    props, warns = convert_actor_props("Engine.Brush", raw, _lookup)
    by = {p.name: p for p in props}
    assert by["PolyFlags"].ptype == AW.PT_INT and by["PolyFlags"].value == 8
    assert by["CsgOper"].ptype == AW.PT_BYTE and by["CsgOper"].value == 2   # enum ordinal
    ms = by["MainScale"]
    assert ms.ptype == AW.PT_STRUCT and ms.struct_name == "Scale"
    # Scale body: X,Y,Z default to identity (1,1,1), SheerRate 0, SheerAxis SHEER_ZX(5)
    x, y, z, rate = struct.unpack_from("<ffff", ms.value, 0)
    assert (x, y, z, rate) == (1.0, 1.0, 1.0, 0.0) and ms.value[16] == 5
    assert warns == []


def test_typed_conversion_light_types_and_skips():
    raw = [("LightBrightness", "220"), ("bStatic", "True"), ("Tag", "MyLight"),
           ("Brightness", "0.5"), ("Info", '"hello"'), ("Skin", "Texture'CoreTexMetal.Wall'"),
           ("NotInSchema", "5"), ("Skin2", "None")]
    props, warns = convert_actor_props("Engine.Light", raw, _lookup)
    by = {p.name: p for p in props}
    assert by["LightBrightness"].value == 220 and by["LightBrightness"].ptype == AW.PT_BYTE
    assert by["bStatic"].ptype == AW.PT_BOOL and by["bStatic"].value is True
    assert by["Tag"].ptype == AW.PT_NAME and by["Tag"].value == "MyLight"
    assert by["Brightness"].ptype == AW.PT_FLOAT and abs(by["Brightness"].value - 0.5) < 1e-6
    assert by["Info"].ptype == AW.PT_STR and by["Info"].value == "hello"
    # Object value -> a late-bound ImportRef the assembler resolves
    assert by["Skin"].ptype == AW.PT_OBJECT and isinstance(by["Skin"].value, ImportRef)
    assert by["Skin"].value.object_class == "Texture"
    assert by["Skin"].value.qualified == "CoreTexMetal.Wall"
    # NotInSchema skipped (warned); Skin2=None omitted (no import)
    assert any("NotInSchema" in w for w in warns)


def test_static_array_index_carried():
    schema = {"multiskins": _SP("MultiSkins", "ByteProperty")}
    p = convert_prop(schema["multiskins"], "3", 2, "x")
    assert p.array_index == 2 and p.value == 3


def test_bad_byte_enum_raises_named_error():
    sp = _SP("CsgOper", "ByteProperty", "ECsgOper", ("CSG_Add", "CSG_Subtract"))
    with pytest.raises(PropError, match="CSG_Bogus"):
        convert_prop(sp, "CSG_Bogus", None, "Engine.Brush.CsgOper=CSG_Bogus")


def test_object_prop_resolves_to_import_in_assembly():
    """An Object property carrying an ImportRef becomes a real package import in the .dx."""
    model = M.carved_box_model()
    ps = ASM.ActorSpec(name="PlayerStart0", qualified_class="Engine.PlayerStart",
                       props=[Prop("Location", PT_STRUCT, struct_vector(0, 0, 0),
                                   struct_name="Vector")], is_player_start=True)
    lite = ASM.ActorSpec(name="Deco0", qualified_class="Engine.Light",
                         props=[Prop("Skin", AW.PT_OBJECT,
                                     ImportRef("Texture", "CoreTexMetal.Wall1"))])
    pkg_bytes = ASM.assemble_level(level_model=model, actors=[ps, lite], brush_shapes=[])
    M.self_check(pkg_bytes)
    pkg = parse_package(pkg_bytes)
    imp_names = [pkg.names[im[3]] for im in pkg.imports]
    assert "Wall1" in imp_names and "CoreTexMetal" in imp_names


def test_texture_imported_never_embedded_on_surf():
    """A poly texture resolves to an IMPORT ref on the level-Model surf (§30.6)."""
    from uedcli.model import Actor, Level
    from uedcli import builders
    from decimal import Decimal
    pytest.importorskip("uedcli_native")

    lvl = Level()
    room = builders.cube(512.0, 512.0, 256.0, texture="CoreTexMetal.Area51Wall_A")
    ra = Actor(name="Room0", cls="Engine.Brush")
    ra.brush = room
    for p in room.polys:
        p.texture = "CoreTexMetal.Area51Wall_A"
    ra.props = [("CsgOper", "CSG_Subtract")]
    lvl.actors["Room0"] = ra
    ps = Actor(name="PS0", cls="Engine.PlayerStart")
    ps.location = (Decimal(0), Decimal(0), Decimal(-64))
    lvl.actors["PS0"] = ps
    lvl.order = ["Room0", "PS0"]

    model, csg_brushes, _light_names, _zone_actors = M._build_level_model(lvl, index=IDX)
    assert len(model.surfs) >= 6            # a carved room = 6 walls
    # assemble via a minimal schema (Subtract only) and assert the surf texture is an import
    schema = {"engine.brush": {"csgoper": _SP("CsgOper", "ByteProperty", "ECsgOper",
                                              ("CSG_Active", "CSG_Add", "CSG_Subtract"))}}
    warns = []
    actors, brushes, _ = M._trunk_to_actorspecs(lvl, lambda c: schema.get(c.casefold(), {}))
    pkg_bytes = ASM.assemble_level(level_model=model, actors=actors + brushes,
                                   brush_shapes=[], csg_brushes=csg_brushes)
    M.self_check(pkg_bytes)
    pkg = parse_package(pkg_bytes)
    lvl_model_i = max((i for i in range(len(pkg.exports))
                       if pkg.class_of_export(i) == "Model"),
                      key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[lvl_model_i]
    m = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])
    tex_surfs = [s for s in m.surfs if s.texture_ref != 0]
    assert tex_surfs, "no surf carried a texture ref"
    d = deref(tex_surfs[0].texture_ref)
    assert d[0] == "import", "texture must be IMPORTED, never embedded"
    assert pkg.name_of_ref(tex_surfs[0].texture_ref) == "Area51Wall_A"


def test_brush_actor_emits_no_mylevel_self_import(tmp_path):
    """Regression (game-load blocker, live 2026-07-15): a brush actor's trunk `Brush=
    Model'MyLevel.<shape>'` string prop must NOT become a package IMPORT.  `make_brush_actor`
    sets that ref; if materialize types it as an ObjectProperty it invents an import of a
    nonexistent "MyLevel" package, whose name collides with the ULevel export (also "MyLevel")
    and aborts game-load ("Failed to find object 'Level None.MyLevel'").  Assembly re-synthesizes
    the brush-shape link as a LOCAL export ref, so the trunk string must be dropped.  Assert the
    materialized package carries NO import naming a "MyLevel" package/object."""
    pytest.importorskip("uedcli_native")
    from uedcli.model import Level
    from uedcli import builders
    from decimal import Decimal

    lvl = Level()
    room = builders.make_brush_actor("RoomA", builders.cube(512.0, 512.0, 256.0),
                                     location=(Decimal(0), Decimal(0), Decimal(0)),
                                     csg="subtract")
    lvl.actors["RoomA"] = room
    from uedcli.model import Actor
    ps = Actor(name="PS0", cls="Engine.PlayerStart")
    ps.location = (Decimal(0), Decimal(0), Decimal(-88))
    lvl.actors["PS0"] = ps
    lvl.order = ["RoomA", "PS0"]

    # a schema where Brush IS a known ObjectProperty (so an un-dropped ref WOULD import)
    schema = {"engine.brush": {"csgoper": _SP("CsgOper", "ByteProperty", "ECsgOper",
                                              ("CSG_Active", "CSG_Add", "CSG_Subtract")),
                               "brush": _SP("Brush", "ObjectProperty", "Model"),
                               "mainscale": _SP("MainScale", "StructProperty", "Scale"),
                               "postscale": _SP("PostScale", "StructProperty", "Scale")}}
    out = tmp_path / "brush.dx"
    M.run_materialize_native(level=lvl, class_index=IDX, out_path=str(out), version=68,
                             schema_lookup=lambda c: schema.get(c.casefold(), {}))
    pkg = parse_package(out.read_bytes())
    # NO import may name a "MyLevel" package or object (the bogus self-import).
    bad = [i for i, im in enumerate(pkg.imports)
           if pkg.names[im[3]] == "MyLevel"
           or (im[2] < 0 and pkg.names[pkg.imports[-im[2] - 1][3]] == "MyLevel")]
    assert not bad, f"materialize invented a MyLevel self-import: {bad}"


def test_native_materialize_bsp_is_a_connected_tree(tmp_path):
    """Regression: the real-CSG materialize must build a GENUINE BSP tree (nodes wired by
    iFront/iBack), not a flat disconnected node list.  The retired `carved_box_model` M0
    placeholder left every node's front/back = -1, which the engine cannot bring up for play."""
    pytest.importorskip("uedcli_native")
    from uedcli.model import Actor, Level
    from uedcli import builders
    from decimal import Decimal

    lvl = Level()
    room = builders.make_brush_actor("RoomA", builders.cube(512.0, 512.0, 256.0),
                                     location=(Decimal(0), Decimal(0), Decimal(0)),
                                     csg="subtract")
    lvl.actors["RoomA"] = room
    ps = Actor(name="PS0", cls="Engine.PlayerStart")
    ps.location = (Decimal(0), Decimal(0), Decimal(-88))
    lvl.actors["PS0"] = ps
    lvl.order = ["RoomA", "PS0"]
    model, *_ = M._build_level_model(lvl, index=IDX)
    # a single subtracted box -> a connected chain: at least one node has a real child link.
    assert any(n.i_front != -1 or n.i_back != -1 for n in model.nodes), \
        "BSP is a flat disconnected node list (the degenerate placeholder), not a real tree"


def test_full_native_materialize_multibrush(tmp_path):
    """End-to-end: a multi-brush trunk materializes to a self-check-passing, re-parsing .dx."""
    pytest.importorskip("uedcli_native")
    from uedcli.model import Actor, Level
    from uedcli import builders
    from decimal import Decimal

    lvl = Level()
    room = builders.cube(768.0, 768.0, 384.0, texture="CoreTexMetal.Area51Wall_A")
    ra = Actor(name="Room0", cls="Engine.Brush")
    ra.brush = room
    for p in room.polys:
        p.texture = "CoreTexMetal.Area51Wall_A"
    ra.props = [("CsgOper", "CSG_Subtract"), ("PolyFlags", "0")]
    lvl.actors["Room0"] = ra
    ps = Actor(name="PS0", cls="Engine.PlayerStart")
    ps.location = (Decimal(0), Decimal(0), Decimal(-120))
    lvl.actors["PS0"] = ps
    lvl.order = ["Room0", "PS0"]

    out = tmp_path / "out.dx"
    schema = {"engine.brush": {"csgoper": _SP("CsgOper", "ByteProperty", "ECsgOper",
                                              ("CSG_Active", "CSG_Add", "CSG_Subtract")),
                               "polyflags": _SP("PolyFlags", "IntProperty")}}
    warns = M.run_materialize_native(level=lvl, class_index=IDX, out_path=str(out), version=68,
                                     schema_lookup=lambda c: schema.get(c.casefold(), {}))
    assert out.exists()
    pkg = parse_package(out.read_bytes())
    classes = [pkg.class_of_export(i) for i in range(len(pkg.exports))]
    assert classes[0] == "LevelInfo" and "PlayerStart" in classes and "Level" in classes
    assert isinstance(warns, list)
