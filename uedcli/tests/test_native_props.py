"""Offline tests for the N-3 typed-property conversion.

Seed a synthetic class schema (no game `.u` needed) and assert `props.convert_actor_props`
emits correctly-TYPED `FPropertyTag`s.  Pure-Python (no Rust ext, no editor).
"""
from __future__ import annotations

import struct

import pytest

from uedcli.native import actor_write as AW
from uedcli.native.props import (convert_actor_props, convert_prop, ImportRef, PropError,
                                 _CallableSchema, _parse_struct_fields)


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
    schema = _CallableSchema(_lookup)
    p = convert_prop(schema, _SP("MultiSkins", "ByteProperty"), "3", 2, "x")
    assert p.array_index == 2 and p.value == 3


def test_bad_byte_enum_raises_named_error():
    sp = _SP("CsgOper", "ByteProperty", "ECsgOper", ("CSG_Add", "CSG_Subtract"))
    with pytest.raises(PropError, match="CSG_Bogus"):
        convert_prop(_CallableSchema(_lookup), sp, "CSG_Bogus", None, "Engine.Brush.CsgOper=CSG_Bogus")



# --- struct / array value serialization (actor_write), round-tripped through the real reader ------

from uedcli.native.codec import write_ci, read_ci                            # noqa: E402
from uedcli import upackage as UP                                            # noqa: E402


def _rt(prop):
    """write_prop -> read_property_tags: return the decoded PropertyTag. A fresh name table per call
    keeps name indices deterministic; the writer registers any name it needs."""
    names = ["None"]
    idx = {"None": 0}

    def name_index(s):
        if s not in idx:
            idx[s] = len(names)
            names.append(s)
        return idx[s]

    body = AW.write_prop(name_index, prop)
    buf = body + write_ci(name_index("None"))
    pkg = UP.Package(name="T", version=68, names=names, imports=[], exports=[], buf=buf)
    tags, _ = UP.read_property_tags(pkg, 0, len(buf))
    assert len(tags) == 1
    return tags[0], names


def test_nonatomic_struct_serializes_member_wise():
    # sUserInfo = { Str accountNumber; Str PIN; Int balance } -> raw member-wise, no None terminator
    sv = AW.StructValue("sUserInfo", [
        AW.Prop("accountNumber", AW.PT_STR, "446009"),
        AW.Prop("PIN", AW.PT_STR, "3124"),
        AW.Prop("balance", AW.PT_INT, 250),
    ])
    tag, _ = _rt(AW.Prop("userList", AW.PT_STRUCT, sv))
    assert tag.name == "userList" and tag.ptype == 10 and tag.struct_name == "sUserInfo"
    # decode the raw: fstring, fstring, i32
    from uedcli.upackage import read_fstring
    a, p = read_fstring(tag.raw, 0)
    b, p = read_fstring(tag.raw, p)
    bal = struct.unpack_from("<i", tag.raw, p)[0]
    assert (a, b, bal) == ("446009", "3124", 250)


def test_struct_bool_member_is_a_full_byte():
    # InitialAllianceInfo = { Name AllianceName; Float AllianceLevel; Bool bPermanent }
    sv = AW.StructValue("InitialAllianceInfo", [
        AW.Prop("AllianceName", AW.PT_NAME, "BarPatrons"),
        AW.Prop("AllianceLevel", AW.PT_FLOAT, 1.0),
        AW.Prop("bPermanent", AW.PT_BOOL, True),
    ])
    tag, names = _rt(AW.Prop("InitialAlliances", AW.PT_STRUCT, sv, array_index=1))
    assert tag.array_index == 1                              # size-before-index order
    ni, p = read_ci(tag.raw, 0)
    assert names[ni] == "BarPatrons"
    assert struct.unpack_from("<f", tag.raw, p)[0] == 1.0
    assert tag.raw[p + 4] == 1                               # in-struct bool = a full 1 byte


def test_static_array_struct_element_index_after_size():
    # a 12-byte struct value at array index 1 must NOT mis-decode (the size/array-index order bug)
    sv = AW.StructValue("Vector", [AW.Prop("X", AW.PT_FLOAT, 1.0),
                                   AW.Prop("Y", AW.PT_FLOAT, 2.0),
                                   AW.Prop("Z", AW.PT_FLOAT, 3.0)])
    tag, _ = _rt(AW.Prop("KeyPos", AW.PT_STRUCT, sv, array_index=1))
    assert tag.array_index == 1 and len(tag.raw) == 12
    assert struct.unpack("<3f", tag.raw) == (1.0, 2.0, 3.0)


def test_big_struct_uses_wide_size_code():
    # a struct value > 255 bytes needs size_code 6/7, not the 1-byte size the old writer hardcoded
    members = [AW.Prop(f"f{i}", AW.PT_INT, i) for i in range(100)]   # 400 bytes
    tag, _ = _rt(AW.Prop("Big", AW.PT_STRUCT, AW.StructValue("S", members)))
    assert len(tag.raw) == 400
    assert struct.unpack_from("<i", tag.raw, 4 * 42)[0] == 42


def test_dynamic_array_is_count_then_elements():
    av = AW.ArrayValue([AW.Prop("e", AW.PT_INT, v) for v in (10, 20, 30)])
    tag, _ = _rt(AW.Prop("arr", AW.PT_ARRAY, av))
    assert tag.ptype == 9
    n, p = read_ci(tag.raw, 0)
    assert n == 3
    assert [struct.unpack_from("<i", tag.raw, p + 4 * i)[0] for i in range(3)] == [10, 20, 30]
