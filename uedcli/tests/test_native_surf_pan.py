"""The world surf carries the authored texture pan (`PanU`/`PanV`).

A polygon's `Pan U=/V=` is a texture-space offset: the texture starts `PanU`/`PanV` texels in from
the surface's texture origin. `FBspSurf` stores it as two SWORDs, and the native build dropped it —
the marshaller never passed it and the zone pass zeroed the slot, which it read as a zone pair. Every
surface with a non-zero authored pan then built with the texture slid across it: 408 of the 3570
surfaces of retail `01_NYC_UNATCOHQ.dx`, whose own editor-built surfs each hold exactly the authored
pan of the polygon they came from.
"""
from __future__ import annotations

import pytest

from uedcli import model as trunk_model
from uedcli.builders import cube, make_brush_actor
from uedcli.native import brush_marshal
from uedcli.native import umodel as UMO
from uedcli.transform import FScale

pytest.importorskip("uedcli_native")

# Distinct per-face pans, one negative per axis (a negative pan is stored two's-complement in the
# u16 slot — `Pan V=-152` ships as 0xff68 in every retail map that uses it).
_PANS = [(0, 0), (16, 0), (0, 26), (128, 64), (-64, 0), (0, -152)]
_WANT = {i: (u & 0xFFFF, v & 0xFFFF) for i, (u, v) in enumerate(_PANS)}


def _pan_brush(pans=_PANS, size=(512.0, 512.0, 256.0)):
    brush = cube(*size)
    assert len(brush.polys) == len(pans), "one pan per cube face"
    for poly, pan in zip(brush.polys, pans):
        poly.pan = pan
    return brush


def _pan_level(*, csg="add", name="Room", **kw):
    lvl = trunk_model.Level()
    lvl.actors[name] = make_brush_actor(name, _pan_brush(), csg=csg)
    for attr, val in kw.items():
        setattr(lvl.actors[name], attr, val)
    lvl.order.append(name)
    return lvl


def _build(lvl):
    """The FULL native world path: marshal -> CSG -> serialize -> re-parse the written body."""
    import uedcli_native
    tuples = [brush_marshal._build_brush_input(n, lvl.actors[n]) for n in lvl.order]
    body = bytes(uedcli_native.serialize_model(uedcli_native.build_geometry_bspcsg(tuples)))
    return UMO.parse_model_body(body, 0, len(body))


def test_authored_poly_pan_reaches_the_world_surf():
    """Each surf's stored pan is its source polygon's authored `Pan U=/V=`, negatives wrapped into
    the unsigned slot. Before the fix every surf came out (0, 0)."""
    assert {s.i_brush_poly: s.pan for s in _build(_pan_level()).surfs} == _WANT


def test_a_scaled_brush_keeps_its_pan_unscaled():
    """The pan is in texture space, so the brush's linear map must not touch it — unlike the texture
    axes, which the scaled path maps covariantly."""
    lvl = _pan_level(post_scale=FScale(scale=(2.0, 0.5, 1.0)))
    assert {s.i_brush_poly: s.pan for s in _build(lvl).surfs} == _WANT


def test_a_split_face_keeps_its_pan_on_every_fragment():
    """A face cut by another brush must carry its pan on every surf and node it produces — the pan
    rides the `FPoly` through the CSG splits and through the surf reconstruction `bspRepartition`
    re-allocs from, it is not re-derived per fragment."""
    lvl = _pan_level(csg="subtract")
    pillar = cube(64.0, 64.0, 256.0)
    for poly in pillar.polys:
        poly.pan = (7, 9)
    lvl.actors["Pillar"] = make_brush_actor("Pillar", pillar, csg="add")
    lvl.order.append("Pillar")
    m = _build(lvl)

    room = [s for s in m.surfs if s.i_actor == 0]
    assert {(s.i_brush_poly, s.pan) for s in room} == set(_WANT.items())
    assert {s.pan for s in m.surfs if s.i_actor == 1} == {(7, 9)}
    # The pillar really does split room faces, so the pans above survived a split: some room surf
    # backs more than one node.
    nodes_per_surf = {}
    for n in m.nodes:
        nodes_per_surf[n.i_surf] = nodes_per_surf.get(n.i_surf, 0) + 1
    assert max(nodes_per_surf[m.surfs.index(s)] for s in room) > 1


def test_the_pan_survives_into_the_written_package():
    """The last hop: `assemble_unbuilt` re-encodes the built model with the Python writer, so the pan
    has to reach the `.dx` too, not just the Rust body."""
    from pathlib import Path
    from uedcli.bsp.builtmodel import load_model_from_dx
    from uedcli.classindex import ClassIndex
    from uedcli.native.materialize import build_world_model, resolve_zone_actors
    from uedcli.native.unbuilt import assemble_unbuilt, substrate_schema

    ued22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
    if not (ued22 / "Engine.u").is_file():
        pytest.skip("committed UED22/Engine.u not present (the writer needs class schemas)")
    paths = {p.stem.casefold(): str(p) for p in ued22.glob("*.u")}
    index = ClassIndex(_paths=paths, _stems={k: Path(v).stem for k, v in paths.items()})

    lvl = _pan_level(csg="subtract")
    for poly in lvl.actors["Room"].brush.polys:
        poly.texture = "CoreTexMetal.Area51Wall_A"
    lvl.actors["LevelInfo0"] = trunk_model.Actor(name="LevelInfo0", cls="Engine.LevelInfo")
    lvl.order.insert(0, "LevelInfo0")

    built, csg_brushes = build_world_model(lvl, index=index)
    dx_bytes, _warnings = assemble_unbuilt(
        lvl, schema=substrate_schema(str(ued22)), pkg_dirs=[str(ued22)], world_model=built,
        csg_brushes=csg_brushes, zone_actors=resolve_zone_actors(lvl, built))
    saved = load_model_from_dx(dx_bytes)
    assert {s.i_brush_poly: s.pan for s in saved.surfs} == _WANT


def test_engine_fact_a_retail_built_model_stores_a_non_zero_pan():
    """The two u16s after `iBrushPoly` are not an always-zero field: the committed built `Model1` of
    retail `99_Endgame4.dx` (editor output) carries a non-zero pan on 4 of its 31 surfs. Reading them
    as a zone pair and forcing (0, 0) is what erased the pan."""
    from pathlib import Path
    golden = (Path(__file__).resolve().parents[2]
              / "dev/docs/spikes/bspspike/fixtures/endgame4_model1.bin").read_bytes()
    m = UMO.parse_model_body(golden, 0, len(golden))
    assert sorted(s.pan for s in m.surfs if s.pan != (0, 0)) == [(0, 18)] * 4
