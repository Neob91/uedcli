"""Offline tests for the N-3 typed-property conversion.

Seed a synthetic class schema (no game `.u` needed) and assert `props.convert_actor_props`
emits correctly-TYPED `FPropertyTag`s.  Pure-Python (no Rust ext, no editor).
"""
from __future__ import annotations

import struct

import pytest

from uedcli.native import actor_write as AW
from uedcli.native.props import (convert_actor_props, convert_prop, ImportRef, PropError,
                                 _parse_struct_fields)


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

