#!/usr/bin/env python3
"""Evaluate native-tree solidity at each golden Brush323 face centroid (and its solid/void sides).

For each golden Brush323 surf, gather its ring verts from the golden model, compute the ring centroid,
then descend that point through the NATIVE tree. Report whether native classifies the face's two
half-spaces as solid (`i_leaf==-1`) and the i_zone.  Shows WHERE native lost the dome.
"""
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

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"
GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"


def ring_verts(m, si):
    out = []
    for n in m.nodes:
        if n.i_surf != si:
            continue
        ring = []
        for k in range(n.num_vertices):
            vi = m.verts[n.i_vert_pool + k].i_vertex
            ring.append(tuple(m.points[vi][:3]))
        out.append(ring)
    return out


def centroid(ring):
    c = [sum(v[i] for v in ring) / len(ring) for i in range(3)]
    return c


def point_region(m, p):
    ni = 0
    while True:
        n = m.nodes[ni]
        nx, ny, nz, w = n.plane
        pd = nx*p[0] + ny*p[1] + nz*p[2] - w
        side = 1 if pd >= 0 else 0
        child = n.i_back if side == 1 else n.i_front
        if child == -1:
            return -1 if n.i_leaf[side] == 0xFFFF else n.i_leaf[side], n.i_zone[side]
        ni = child


def native_model():
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    brushes = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(brushes)
    body = uedcli_native.serialize_model(built)
    return UM.parse_model_body(body, 0, len(body))


def main():
    pkg = load_package(GOLDEN)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    g = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    fm = [si for si, s in enumerate(g.surfs) if pkg.name_of_ref(s.i_actor) == "Brush323"]
    print(f"golden Brush323: {len(fm)} surfs")

    m = native_model()
    print(f"native: nodes={len(m.nodes)} surfs={len(m.surfs)}")

    per_side = Counter()
    nring = Counter()
    rows = []
    for si in sorted(fm):
        rings = ring_verts(g, si)
        nring[len(rings)] += 1
        c = centroid(rings[0])
        N = tuple(g.vectors[g.surfs[si].v_normal][:3])
        for off, lab in ((0.0, "on"), (2.0, "pN"), (-2.0, "nN")):
            p = [c[i] + off*N[i] for i in range(3)]
            leaf, zone = point_region(m, p)
            per_side[(lab, leaf == -1, zone)] += 1
        rows.append((si, tuple(round(x,1) for x in c), tuple(round(x,3) for x in N)))
    print("rings-per-surf dist:", dict(nring))
    print("side solidity  (side, solid, zone):count")
    for k, v in sorted(per_side.items()):
        print("  ", k, v)
    print("sample faces:")
    for r in rows[:6]:
        print("  surf", r)


if __name__ == "__main__":
    main()