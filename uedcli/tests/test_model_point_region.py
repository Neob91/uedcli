"""`materialize._model_point_region` BSP descent — a pure-Python check over a synthesized
`umodel.Model`, needing NO UED22 schema (so it lives outside `test_native_roundtrip.py`'s
`Engine.u` skip-gate, which would otherwise silently skip it on a stripped checkout)."""
from __future__ import annotations


def test_model_point_region_solid_vs_air_leaf():
    """`SetActorZone`'s BSP descent (`materialize._model_point_region`): a point in a carved leaf
    takes that leaf's `(iLeaf, zone)`; a point in solid (no leaf on its side) and the empty world
    both resolve to `(-1, 0)`. Grounds the WanChai N=2 fix (subtract-carved origin -> (0, 1))."""
    from uedcli.native import umodel as UM
    from uedcli.native.materialize import _model_point_region
    assert _model_point_region(UM.Model(), (0.0, 0.0, 0.0)) == (-1, 0)  # empty world
    m = UM.Model(
        nodes=[UM.BspNode(plane=(0.0, 0.0, 1.0, 0.0), i_front=-1, i_back=-1, i_leaf=(-1, 0))],
        leaves=[UM.BspLeaf(i_zone=1)])
    assert _model_point_region(m, (0.0, 0.0, 10.0)) == (0, 1)   # above z=0 -> air leaf 0, zone 1
    assert _model_point_region(m, (0.0, 0.0, -10.0)) == (-1, 0)  # below -> solid
