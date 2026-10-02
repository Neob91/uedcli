"""Engine-facts regressions for what each brush CSG KIND contributes to the resolved world.

Pins the findings of `dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/` (harness:
`kind_semantics.py`), which `actor survey`'s `crosses`/`carves` rules are built on. Same
"pin it or it rots" rule as `test_engine_facts.py`, against a third artifact class: the faithful
native CSG core (`uedcli_native.build_geometry_bspcsg`), which the parity campaign holds to
byte-identity with UED22.

The scenario is one level, three brushes, in trunk order:

    Room (1024^3 Subtract)  ->  Pillar (128 x 128 x 512, THE KIND UNDER TEST)  ->  Cutter (Subtract)

The Cutter spans x in [0, 256], y/z in [-128, 128] — it covers the pillar's RIGHT half over the
middle of its height and nothing else, so "was the pillar carved?" is answerable by looking at the
pillar's own surviving face area and at whether its right half is still solid.
"""
from __future__ import annotations

import dataclasses

import pytest

from uedcli import preview_native as pn
from uedcli.builders import cube, make_brush_actor
from uedcli.native.umodel import parse_model_body

uedcli_native = pytest.importorskip("uedcli_native")

PF_NOTSOLID = 0x08
PF_SEMISOLID = 0x20

LEFT = (-40.0, 0.0, 0.0)        # inside the pillar, OUTSIDE the cutter
RIGHT = (40.0, 0.0, 0.0)        # inside the pillar, INSIDE the cutter

PILLAR_FULL_AREA = 294912.0     # 6 faces of a 128 x 128 x 512 box
PILLAR_CARVED_AREA = 229376.0   # what survives once the cutter takes its bite


# --------------------------------------------------------------- the engine's own solidity walk

def _plane_dot(plane, v) -> float:
    return plane[0] * v[0] + plane[1] * v[1] + plane[2] * v[2] - plane[3]


def point_is_solid(model, p) -> bool:
    """`p` is in SOLID space. A direct port of the zero-extent form of the engine's collision walk
    — `uedcli-native/src/linecheck.rs`'s `is_csg`/`combine_state`/`child` plus `collision.rs`'s
    `CollisionModel::point_check` entry state. Going FRONT of a CSG-solid node proves open space,
    BACK of one proves solid, a non-CSG node passes the state through.

    Deliberately NOT `native/materialize._model_point_region`: that answers "which zone leaf", and
    a semisolid's nodes are added after the zone pass, so it reports a semisolid's interior as void
    (pinned by `test_point_region_is_not_a_solidity_oracle_for_semisolid` below)."""
    if not model.nodes:
        return not model.root_outside
    state = bool(model.root_outside)
    i = 0
    while i != -1:
        n = model.nodes[i]
        side_front = _plane_dot(n.plane, p) >= 0.0
        csg = n.num_vertices > 0 and (n.node_flags & 0x21) == 0
        state = (state or csg) if side_front else (state and not csg)
        i = n.i_back if side_front else n.i_front
    return not state


# --------------------------------------------------------------- scenario construction

def _brush(name, size, location, oper, poly_flags=0):
    a = make_brush_actor(name, cube(*size), location=location)
    props = list(a.props) + [("CsgOper", oper)]
    if poly_flags:
        props.append(("PolyFlags", str(poly_flags)))
    return dataclasses.replace(a, props=props)


def _poly_area(verts) -> float:
    """Newell's method — correct for any planar polygon."""
    nx = ny = nz = 0.0
    for i in range(len(verts)):
        a, b = verts[i], verts[(i + 1) % len(verts)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return 0.5 * (nx * nx + ny * ny + nz * nz) ** 0.5


def _solve(kind, *, with_cutter=True):
    """Returns `(pillar face count, pillar face area, parsed model)` for the scenario."""
    oper, flags = {
        "add": ("CSG_Add", 0),
        "semisolid": ("CSG_Add", PF_SEMISOLID),
        "nonsolid": ("CSG_Add", PF_NOTSOLID),
        "intersect": ("CSG_Intersect", 0),
        "deintersect": ("CSG_Deintersect", 0),
    }[kind]
    actors = [_brush("Room", (1024, 1024, 1024), (0, 0, 0), "CSG_Subtract"),
              _brush("Pillar", (128, 128, 512), (0, 0, 0), oper, flags)]
    if with_cutter:
        actors.append(_brush("Cutter", (256, 256, 256), (128, 0, 0), "CSG_Subtract"))
    built = uedcli_native.build_geometry_bspcsg([pn._marshal_brush(a) for a in actors])
    faces = [p for p in built.world_soup() if p[6] == 1]                 # p[6] == i_actor
    area = sum(_poly_area([tuple(p[0][i:i + 3]) for i in range(0, len(p[0]), 3)]) for p in faces)
    body = uedcli_native.serialize_model(built)
    return len(faces), area, parse_model_body(body, 0, len(body))


# --------------------------------------------------------------- the facts

def test_add_contributes_solid_and_a_later_subtract_carves_it():
    faces, area, model = _solve("add")
    assert point_is_solid(model, LEFT) and not point_is_solid(model, RIGHT)
    assert _solve("add", with_cutter=False)[1] == pytest.approx(PILLAR_FULL_AREA)
    assert area == pytest.approx(PILLAR_CARVED_AREA)
    assert faces == 11


def test_semisolid_contributes_solid_and_is_never_carved_by_a_later_subtract():
    """The editor runs every Add/Subtract in its LOOP 2 and only then, after the repartition, the
    semisolid brushes in LOOP 3 (`uedcli-native/src/bspcsg.rs`'s `detail_pass`) — so no Subtract
    in the trunk can ever remove a semisolid's matter, whatever the trunk order says. This is what
    makes `csg carves <a semisolid>` an impossible fact while raw `carves` will happily claim it."""
    faces, area, model = _solve("semisolid")
    assert point_is_solid(model, LEFT), "a semisolid contributes real solid matter"
    assert point_is_solid(model, RIGHT), "a later Subtract does not carve a semisolid"
    assert (faces, area) == (6, pytest.approx(PILLAR_FULL_AREA))
    assert _solve("semisolid", with_cutter=False)[:2] == (6, pytest.approx(PILLAR_FULL_AREA))


def test_nonsolid_contributes_no_solid_but_its_own_faces_are_carved():
    """`derive_nf` sets `NF_NotCsg` from `PF_NotSolid`, so a nonsolid node never bounds solid space
    — nothing can intrude on it. Its FACES are still real world surfaces and a later Subtract does
    remove them, exactly as it would an Add's."""
    faces, area, model = _solve("nonsolid")
    assert not point_is_solid(model, LEFT) and not point_is_solid(model, RIGHT)
    assert _solve("nonsolid", with_cutter=False)[1] == pytest.approx(PILLAR_FULL_AREA)
    assert area == pytest.approx(PILLAR_CARVED_AREA)
    assert faces == 11


@pytest.mark.parametrize("kind", ["intersect", "deintersect"])
def test_a_placed_intersect_or_deintersect_contributes_nothing_to_the_world(kind):
    """`CSG_Intersect`/`CSG_Deintersect` are builder-brush operations: `bspBrushCSG` dispatches them
    to a tail that rewrites the BRUSH's own model and never touches the world. A placed actor
    carrying one therefore adds no face, no solid, and no node — the world is exactly the world
    without it."""
    faces, area, model = _solve(kind)
    assert (faces, area) == (0, 0.0)
    assert not point_is_solid(model, LEFT) and not point_is_solid(model, RIGHT)
    bare = uedcli_native.build_geometry_bspcsg(
        [pn._marshal_brush(_brush("Room", (1024, 1024, 1024), (0, 0, 0), "CSG_Subtract")),
         pn._marshal_brush(_brush("Cutter", (256, 256, 256), (128, 0, 0), "CSG_Subtract"))])
    assert model.nodes and len(model.nodes) == bare.num_nodes


def test_point_region_is_not_a_solidity_oracle_for_semisolid():
    """Guards the trap that this spike's first measurement fell into: `UModel::PointRegion` reports
    a semisolid's interior as VOID, because a semisolid's nodes are added after `TestVisibility`
    assigned leaves. Anything asking "is this point in solid" must use the collision walk instead.
    If a later change gives semisolid nodes their own leaves, this test goes red on purpose — the
    caveat would no longer apply and the code that works around it should be revisited."""
    from uedcli.native.materialize import _model_point_region
    _, _, model = _solve("semisolid")
    assert point_is_solid(model, LEFT)
    assert _model_point_region(model, LEFT)[0] >= 0, "PointRegion still calls it a carved leaf"
