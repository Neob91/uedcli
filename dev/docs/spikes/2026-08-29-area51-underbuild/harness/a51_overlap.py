#!/usr/bin/env python3
"""Find brushes whose world AABB overlaps Brush323's world AABB (the solid the dome carves into)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance"
ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli import trunk
from uedcli.native import brush_marshal as BM
from uedcli import rotation as ROT
from spike_classindex import class_index

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"
FOCUS = sys.argv[1] if len(sys.argv) > 1 else "Brush323"


def world_verts(brush_input):
    """Transform every poly's verts to world via the baked R (L) + loc. BrushInput tuple:
    (verts_flat, poly_sizes, normals, oper, poly_flags, loc, R, prepivot, scale, ...)."""
    verts_flat = brush_input[0]
    sizes = brush_input[1]
    loc = brush_input[5]
    R = brush_input[6]
    pp = brush_input[7]
    out = []
    i = 0
    for nv in sizes:
        for _ in range(nv):
            v = (verts_flat[i], verts_flat[i + 1], verts_flat[i + 2])
            i += 3
            # world = R·(v-pp) + loc
            d = (v[0] - pp[0], v[1] - pp[1], v[2] - pp[2])
            w = (
                R[0][0] * d[0] + R[0][1] * d[1] + R[0][2] * d[2] + loc[0],
                R[1][0] * d[0] + R[1][1] * d[1] + R[1][2] * d[2] + loc[1],
                R[2][0] * d[0] + R[2][1] * d[1] + R[2][2] * d[2] + loc[2],
            )
            out.append(w)
    return out


def aabb(vs):
    xs = [v[0] for v in vs]; ys = [v[1] for v in vs]; zs = [v[2] for v in vs]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def overlap(a0, a1, b0, b1):
    return all(a0[i] <= b1[i] and b0[i] <= a1[i] for i in range(3))


def main():
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    inputs = [BM._build_brush_input(n, level.actors[n]) for n in names]

    fi = names.index(FOCUS)
    fv = world_verts(inputs[fi])
    f0, f1 = aabb(fv)
    print(f"{FOCUS}: loc={level.actors[FOCUS].location} world AABB=({tuple(round(x,1) for x in f0)} .. {tuple(round(x,1) for x in f1)})")

    rows = []
    for i, n in enumerate(names):
        if i == fi:
            continue
        v = world_verts(inputs[i])
        b0, b1 = aabb(v)
        if not overlap(f0, f1, b0, b1):
            continue
        act = level.actors[n]
        scaled = not (ROT.actor_main_scale(act).is_identity() and ROT.actor_post_scale(act).is_identity())
        oper = act.props.get("CsgOper", None) if hasattr(act.props, 'get') else dict(act.props).get("CsgOper")
        vol = (b1[0]-b0[0])*(b1[1]-b0[1])*(b1[2]-b0[2])
        rows.append((vol, n, oper, scaled, tuple(round(x,1) for x in b0), tuple(round(x,1) for x in b1)))
    rows.sort(reverse=True)
    print(f"{len(rows)} brushes overlap the dome AABB (by volume desc):")
    for vol, n, oper, scaled, b0, b1 in rows:
        print(f"  {n}: oper={oper} scaled={scaled} vol={vol:,.0f} bb=({b0} .. {b1})")


if __name__ == "__main__":
    main()