"""Regression: `unbuilt._marshal_brush_polys` used to thread a poly's `poly_flags` straight into
the Rust `BrushPolyTuple` unmasked. A DWORD `PolyFlags` with the top bit(s) set (e.g. `PF_Occlude`
on an original-format Unreal map) decodes as a NEGATIVE Python int (`mapimport.py`'s signed
`decode_fpoly`, matched to the write side), and the Rust side's `poly_flags` field is `u32` — an
unmasked negative value is `OverflowError: out of range integral type conversion attempted`
crossing the FFI. This is the `level materialize --native` sibling of the `level photo --native`
crash on SkyTown/Vortex2 (a Mover's shape-model build and lightmap-index build both go through
`_marshal_brush_polys`).
"""
from __future__ import annotations

import pytest

from uedcli.builders import cube
from uedcli.native import unbuilt

pytest.importorskip("uedcli_native")


def _brush_with_polyflags(flags: int):
    brush = cube(64.0, 64.0, 64.0)
    for poly in brush.polys:
        poly.flags = flags
    return brush


def test_negative_poly_flags_masked_in_marshal_brush_polys():
    fpolys = unbuilt._fpolys(_brush_with_polyflags(-1073741824), actor="Door")  # 0xC0000000 signed
    tuples = unbuilt._marshal_brush_polys(fpolys)
    assert all(t[5] == 0xC0000000 for t in tuples)          # masked to unsigned, not negative


def test_negative_poly_flags_does_not_overflow_build_mover_shape_model():
    fpolys = unbuilt._fpolys(_brush_with_polyflags(-1073741824), actor="Door")
    unbuilt.build_mover_shape_model(fpolys)                 # must not raise OverflowError
