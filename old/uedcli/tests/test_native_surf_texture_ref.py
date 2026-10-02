"""An untextured world surf ships `Texture = None`, not the marshaller's dedup ordinal.

`brush_marshal` gives each of a brush's polys a per-brush texture dedup ordinal (0, 1, 2, ... in
first-appearance order) so the Rust core can compare "same texture?" between two polys. The core
copies that ordinal into `FBspSurf.Texture`, where the real editor holds a `UTexture*`, so the
assembly step must ASSIGN every surf's `texture_ref` from the source poly, never merge into it.
It merged, so a poly with no `Texture=` whose ordinal happened to be non-zero shipped the ordinal
as an object ref -- UNATCO N=29's `Brush516` poly 2 got ordinal 2, which serialized as the builder
brush's `Polys`. See board item `unatco-n-29-world-model2-vert-rings-reference`.
"""
from __future__ import annotations

import pytest

from uedcli.builders import cube
from uedcli.model import Actor
from uedcli.native import brush_marshal
from uedcli.native import umodel as UMO
from uedcli.native.unbuilt import _patch_native_surf_refs

pytest.importorskip("uedcli_native")

_TEX0 = "UNATCO.Stone.MedAreaWall_B"
_TEX1 = "UNATCO.Stone.LowrLevFloor_B"
_REFS = {_TEX0: -7, _TEX1: -9}                   # any non-zero import refs; the resolver is stubbed


class _Asm:
    """The one method the patch calls on the assembler."""
    def eref(self, name):
        return 4


def _mixed_brush():
    """A cube whose first two faces are textured and whose third names no texture -- the shape that
    hands the untextured face a non-zero dedup ordinal."""
    brush = cube(512.0, 512.0, 256.0)
    brush.polys[0].texture = _TEX0
    brush.polys[1].texture = _TEX1
    return brush


def _world_surfs(brush):
    import uedcli_native
    actor = Actor(name="Room", cls="Brush", brush=brush)
    actor.props = [("CsgOper", "CSG_Add")]
    tuples = [brush_marshal._build_brush_input("Room", actor)]
    body = bytes(uedcli_native.serialize_model(uedcli_native.build_geometry_bspcsg(tuples)))
    return UMO.parse_model_body(body, 0, len(body)).surfs


def test_the_core_leaves_a_non_ref_value_in_the_surf_texture_slot():
    """Why the patch must assign rather than merge: the untextured face's slot is not already 0."""
    by_poly = {s.i_brush_poly: s.texture_ref for s in _world_surfs(_mixed_brush())}
    assert by_poly[2] != 0, by_poly


def test_an_untextured_poly_ships_a_none_texture_ref():
    brush = _mixed_brush()
    model = UMO.Model(surfs=_world_surfs(brush))
    for s in model.surfs:
        s.i_actor = 0
    _patch_native_surf_refs(_Asm(), model, [("Room", brush.polys)], _REFS.__getitem__)
    by_poly = {s.i_brush_poly: s.texture_ref for s in model.surfs}
    assert by_poly[0] == _REFS[_TEX0], by_poly
    assert by_poly[1] == _REFS[_TEX1], by_poly
    assert by_poly[2] == 0, by_poly


def test_a_surf_with_no_owner_brush_ships_a_none_texture_ref():
    """The out-of-range `iActor` branch clears the slot too, rather than leaving the ordinal."""
    model = UMO.Model(surfs=_world_surfs(_mixed_brush()))
    for s in model.surfs:
        s.i_actor = 99
    _patch_native_surf_refs(_Asm(), model, [], _REFS.__getitem__)
    assert {s.texture_ref for s in model.surfs} == {0}
    assert {s.i_actor for s in model.surfs} == {0}
