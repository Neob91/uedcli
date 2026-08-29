#!/usr/bin/env python3
"""Grid solidity map of the dome AABB in native vs golden; report coarse solid cells each."""
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
from uedcli.native import umodel as UM
import uedcli_native
from uedcli.utexture import load_package

GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"
TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"
LO = (-576, -2656, -1312)
HI = (384, -960, 384)
STEP = 128


def point_solid(m, p):
    if not m.nodes:
        return False
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


def golden_model():
    pkg = load_package(GOLDEN)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    return UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])


def native_model():
    level, _ranks = trunk.read_level(Path(TRUNK))
    ins = [BM._build_brush_input(n, level.actors[n]) for n in
           [n for n in level.order if level.actors[n].brush is not None]]
    built = uedcli_native.build_geometry_bspcsg(ins)
    body = uedcli_native.serialize_model(built)
    return UM.parse_model_body(body, 0, len(body))


def grid_pts():
    x0, y0, z0 = LO
    x1, y1, z1 = HI
    pts = []
    x = x0 + 64
    while x <= x1:
        y = y0 + 64
        while y <= y1:
            z = z0 + 64
            while z <= z1:
                pts.append((round(x, 1), round(y, 1), round(z, 1)))
                z += STEP
            y += STEP
        x += STEP
    return pts


def main():
    g = golden_model()
    m = native_model()
    print(f"golden nodes={len(g.nodes)} native nodes={len(m.nodes)}")
    pts = grid_pts()
    print(f"grid points: {len(pts)}")

    gs = [point_solid(g, p) for p in pts]
    ns = [point_solid(m, p) for p in pts]

    nsolid = sum(gs)
    nsolid_n = sum(ns)
    print(f"solid cells: golden={nsolid}/{len(pts)} native={nsolid_n}/{len(pts)}")

    # native-missing solid cells (golden solid, native void)
    missing = [(p, None) for p, (a, b) in zip(pts, zip(gs, ns)) if a and not b]
    extra = [(p, None) for p, (a, b) in zip(pts, zip(gs, ns)) if b and not a]
    print(f"missing-solid cells: {len(missing)}; extra-solid cells: {len(extra)}")
    if missing:
        print("  first 25 missing (golden-solid, native-void):")
        for p, _ in missing[:25]:
            print("   ", p)
    if extra:
        print("  first 25 extra (native-solid, golden-void):")
        for p, _ in extra[:25]:
            print("   ", p)


if __name__ == "__main__":
    main()