"""Measure, against the faithful native CSG core, what each brush CSG kind actually contributes to
the resolved world — the evidence behind this spike's `crosses`/`carves` rulings for Semisolid,
Nonsolid, Intersect and Deintersect.

Three synthetic levels, identical but for the middle brush's kind:

    Room (1024^3 Subtract)  ->  Pillar (128x128x1024, KIND)  ->  Cutter (Subtract, right half)

and for each we report:
  * `solid_left`  — is a point inside the pillar's LEFT (uncut) half solid?      -> does the kind
                    contribute solid matter to the world at all?
  * `solid_right` — is a point inside the pillar's RIGHT (cut) half solid?       -> did the later
                    Subtract actually remove this kind's matter?
  * `faces`       — how many surviving world faces the pillar owns.

Solid/void is the engine's own `UModel::PointRegion` port (`native/materialize._model_point_region`,
`(-1, 0)` == solid). The regression test pinning these numbers is
`uedcli/tests/test_engine_facts_csg_kinds.py`.

Usage:  .venv/bin/python dev/docs/spikes/<slug>/harness/kind_semantics.py
"""
from __future__ import annotations

import json

import corpus  # noqa: F401  — sets sys.path to the repo root

PF_NOTSOLID = 0x08
PF_SEMISOLID = 0x20

# Room x,y,z in [-512, 512]. Pillar x,y in [-64, 64], z in [-256, 256].
# Cutter x in [0, 256], y,z in [-128, 128] -- it takes the pillar's RIGHT half over the middle
# third of its height, leaving the left half and both ends untouched.
ROOM = (1024.0, 1024.0, 1024.0)
PILLAR = (128.0, 128.0, 512.0)
CUTTER = (256.0, 256.0, 256.0)
CUTTER_AT = (128.0, 0.0, 0.0)
LEFT_PROBE = (-40.0, 0.0, 0.0)      # inside the pillar, OUTSIDE the cutter
RIGHT_PROBE = (40.0, 0.0, 0.0)      # inside the pillar, INSIDE the cutter


def _actor(name, size, location, oper, poly_flags=0):
    """A box brush actor of the given world size at the given location, carrying `oper` and (for
    semisolid/nonsolid) the actor-level `PolyFlags` bit — `dataclasses.replace`, so the `location`
    field `make_brush_actor` set is preserved rather than silently dropped."""
    import dataclasses
    from uedcli.builders import cube, make_brush_actor
    a = make_brush_actor(name, cube(*size), location=location)
    props = list(a.props) + [("CsgOper", oper)]
    if poly_flags:
        props.append(("PolyFlags", str(poly_flags)))
    return dataclasses.replace(a, props=props)


def _solve(actors):
    from uedcli.native.umodel import parse_model_body
    from uedcli.native_ext import import_native
    from uedcli import preview_native as pn
    native = import_native()
    built = native.build_geometry_bspcsg([pn._marshal_brush(a) for a in actors])
    body = native.serialize_model(built)
    return built, parse_model_body(body, 0, len(body))


def _pillar_area(built) -> float:
    """Total surviving world-soup face area owned by brush index 1 (the pillar)."""
    from bounded_cost import poly_area
    total = 0.0
    for p in built.world_soup():
        if p[6] != 1:                                     # p[6] == i_actor
            continue
        verts = [tuple(p[0][i:i + 3]) for i in range(0, len(p[0]), 3)]
        total += poly_area(verts)
    return total


def scenario(kind: str) -> dict:
    """Build `Room -> Pillar(kind) -> Cutter` and report the pillar's contribution."""
    from solidity import point_is_solid
    from uedcli.native.materialize import _model_point_region as point_region

    oper, flags = {
        "add": ("CSG_Add", 0),
        "semisolid": ("CSG_Add", PF_SEMISOLID),
        "nonsolid": ("CSG_Add", PF_NOTSOLID),
        "subtract": ("CSG_Subtract", 0),
        "intersect": ("CSG_Intersect", 0),
        "deintersect": ("CSG_Deintersect", 0),
    }[kind]

    room = _actor("Room", ROOM, (0.0, 0.0, 0.0), "CSG_Subtract")
    pillar = _actor("Pillar", PILLAR, (0.0, 0.0, 0.0), oper, flags)
    cutter = _actor("Cutter", CUTTER, CUTTER_AT, "CSG_Subtract")

    uncut_built, _ = _solve([room, pillar])
    built, model = _solve([room, pillar, cutter])

    return {
        "kind": kind,
        # `solid_*` is the engine's collision walk (`solidity.point_is_solid`); `region_*` is
        # `UModel::PointRegion` alongside it, to show where the two disagree (semisolid).
        "solid_left": point_is_solid(model, LEFT_PROBE),
        "solid_right": point_is_solid(model, RIGHT_PROBE),
        "region_left_solid": point_region(model, LEFT_PROBE)[0] < 0,
        "region_right_solid": point_region(model, RIGHT_PROBE)[0] < 0,
        "pillar_faces_uncut": sum(1 for p in uncut_built.world_soup() if p[6] == 1),
        "pillar_faces_cut": sum(1 for p in built.world_soup() if p[6] == 1),
        "pillar_area_uncut": round(_pillar_area(uncut_built), 1),
        "pillar_area_cut": round(_pillar_area(built), 1),
        "nodes": built.num_nodes,
    }


def main() -> int:
    rows = [scenario(k) for k in
            ("add", "semisolid", "nonsolid", "subtract", "intersect", "deintersect")]
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
