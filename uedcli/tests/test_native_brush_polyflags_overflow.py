"""Regression: an actor-level `PolyFlags` whose top bit(s) are set decodes as a NEGATIVE Python
int (`mapimport.py`'s `decode_fpoly` reads the DWORD as a signed i32, matched to the write side —
a real value on an original-format Unreal map, e.g. `PF_Occlude`). `brush_marshal._build_brush_input`
threaded that raw int straight into the Rust `BrushTuple`'s `poly_flags: u32` slot, so
`build_geometry`/`build_geometry_bspcsg` would raise `OverflowError: out of range integral type
conversion attempted` crossing the FFI — the same bug class already fixed for `poly_flags_flat`/
`pans_flat` in the same function, just missed for the brush-level field.
"""
from __future__ import annotations

import pytest

from uedcli import model as trunk_model
from uedcli.builders import cube, make_brush_actor
from uedcli.native import brush_marshal
from uedcli.tests.conftest import set_prop

pytest.importorskip("uedcli_native")


def _level(name="Room"):
    lvl = trunk_model.Level()
    lvl.actors[name] = make_brush_actor(name, cube(128.0, 128.0, 128.0), csg="add")
    lvl.order.append(name)
    return lvl


def test_negative_actor_polyflags_masked_not_overflowed():
    lvl = _level()
    set_prop(lvl.actors["Room"], "PolyFlags", "-1073741824")   # 0xC0000000 as a signed i32
    tup = brush_marshal._build_brush_input("Room", lvl.actors["Room"])
    assert tup[4] == 0xC0000000                                # masked to unsigned, not negative


def test_negative_actor_polyflags_does_not_overflow_build_geometry():
    import uedcli_native
    lvl = _level()
    set_prop(lvl.actors["Room"], "PolyFlags", "-1073741824")
    tup = brush_marshal._build_brush_input("Room", lvl.actors["Room"])
    uedcli_native.build_geometry_bspcsg([tup])                 # must not raise OverflowError
