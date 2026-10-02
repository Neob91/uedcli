#!/usr/bin/env python3
"""Golden-tree solidity at each golden Brush323 face centroid (mirror of a51_faceprobe).

Runs the identical point-region descent over the GOLDEN retail model and reports, for each dome
face: solid/void, zone, and raw i_leaf.  Contrasts with a51_faceprobe's native result (all void).
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

from uedcli.native import umodel as UM
from uedcli.utexture import load_package

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


def point_region(m, p):
    ni = 0
    while True:
        n = m.nodes[ni]
        nx, ny, nz, w = n.plane
        pd = nx*p[0] + ny*p[1] + nz*p[2] - w
        side = 1 if pd >= 0 else 0
        child = n.i_back if side == 1 else n.i_front
        if child == -1:
            return n.i_leaf[side], n.i_zone[side]
        ni = child


def main():
    pkg = load_package(GOLDEN)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    g = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    fm = [si for si, s in enumerate(g.surfs) if pkg.name_of_ref(s.i_actor) == "Brush323"]
    print(f"golden model: nodes={len(g.nodes)} surfs={len(g.surfs)} zones={len(g.zones)}" if hasattr(g, "zones") else f"golden model: nodes={len(g.nodes)} surfs={len(g.surfs)}")
    print(f"golden Brush323: {len(fm)} surfs; probes at centroid, centroid±2u along normal")

    per_side = Counter()
    for si in sorted(fm):
        rings = ring_verts(g, si)
        c = [sum(v[i] for v in rings[0]) / len(rings[0]) for i in range(3)]
        N = tuple(g.vectors[g.surfs[si].v_normal][:3])
        for off, lab in ((0.0, "on"), (2.0, "pN"), (-2.0, "nN")):
            p = [c[i] + off*N[i] for i in range(3)]
            leaf, zone = point_region(g, p)
            per_side[(lab, leaf == 0xFFFF, zone, leaf)] += 1
    print("side solidity (side, solid, zone, leaf):count")
    for k, v in sorted(per_side.items(), key=lambda kv: kv[0][0]):
        print("  ", k, v)


if __name__ == "__main__":
    main()