#!/usr/bin/env python3
"""Progressive build: solidity of the 42 golden-Brush323 face points as the native world grows.

For each prefix [0..k] of the CSG brush order, build and report how many of the 42 dome-face
probe points (face centroid slightly into the face) are classified SOLID.  The k where a big
flip to void occurs is the carving brush that voids the dome region."""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance"
ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli import trunk
from uedcli.native import brush_marshal as BM
from uedcli.native import umodel as UM
import uedcli_native
from uedcli.utexture import load_package
from spike_classindex import class_index

GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"
TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"


def golden_dome_points():
    pkg = load_package(GOLDEN)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    g = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    pts = []
    for si, s in enumerate(g.surfs):
        if pkg.name_of_ref(s.i_actor) != "Brush323":
            continue
        N = tuple(g.vectors[s.v_normal][:3])
        rings = []
        for n in g.nodes:
            if n.i_surf != si:
                continue
            ring = [tuple(g.points[g.verts[n.i_vert_pool + k].i_vertex][:3])
                    for k in range(n.num_vertices)]
            rings.append(ring)
        if not rings:
            continue
        c = [sum(v[i] for v in rings[0]) / len(rings[0]) for i in range(3)]
        pts.append((c, N))
    return pts


def point_solid(m, p):
    ni = 0
    while True:
        n = m.nodes[ni]
        nx, ny, nz, w = n.plane
        pd = nx*p[0] + ny*p[1] + nz*p[2] - w
        side = 1 if pd >= 0 else 0
        child = n.i_back if side == 1 else n.i_front
        if child == -1:
            return n.i_leaf[side] == 0xFFFF
        ni = child


def build(b):
    built = uedcli_native.build_geometry_bspcsg(b)
    body = uedcli_native.serialize_model(built)
    return UM.parse_model_body(body, 0, len(body))


def main():
    pts = golden_dome_points()
    print(f"dome probe points: {len(pts)}")
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]

    # solid points after each prefix to the dome's index+1
    upto = min(len(names), 60)
    prev_solid = 0
    for k in range(0, upto):
        m = build(ins[:k+1])
        solid = sum(1 for c, N in pts if point_solid(m, [c[i]+N[i]*1e-3 for i in range(3)]))
        if solid != prev_solid:
            mark = "*" if solid < prev_solid else " "
            print(f"k={k:3d} {names[k]:14s} nodes={len(m.nodes):5d} surfs={len(m.surfs):4d} solid_pts={solid:2d} {mark}")
        prev_solid = solid
    # also full
    m = build(ins)
    solid = sum(1 for c, N in pts if point_solid(m, [c[i]+N[i]*1e-3 for i in range(3)]))
    print(f"FULL solid_pts={solid}")


if __name__ == "__main__":
    main()