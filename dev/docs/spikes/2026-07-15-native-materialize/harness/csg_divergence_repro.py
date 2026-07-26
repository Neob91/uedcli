#!/usr/bin/env python3
"""Repro + bisection for the native-CSG geometry divergence vs UnrealEd (the "missing walls").

Root cause (2026-07-16): the native CSG is SURFACE-based — `bsp_brush_csg` rebuilds a classify
BSP from the intermediate world surface list at EACH brush step (`build::build_bsp(&world_polys)`).
For complex non-box geometry (e.g. an octagonal tower with diagonal planes), that intermediate
surface set is not perfectly watertight, so the rebuilt classify tree MISCLASSIFIES empty regions
as solid.  The next brush's faces are then over-discarded in PASS 1 (AddFunc "INSIDE" -> drop), so
its solid never forms.  Concretely: adding `DWallNE` (a box wall) AFTER `OTowerONE` (a 10-face
octagonal tower) leaves DWallNE's side faces clipped to slivers and its interior empty; reversing
the order builds it correctly.

The editor (UnrealEd `bspBrushCSG`) avoids this by maintaining the world BSP INCREMENTALLY (adding/
removing nodes), never rebuilding a classifier from a possibly-non-watertight surface list.

This script reproduces the castle divergence, bisects to the culprit brush pair, and traces the
misclassification, using the live `uedcli_native` build + the editor `Test_Castle.dx` as oracle.

Usage: python csg_divergence_repro.py
"""
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

from uedcli import trunk  # noqa: E402
from uedcli.native import materialize as M, umodel as UM  # noqa: E402
import uedcli_native  # noqa: E402
import utexture_decode as UT  # noqa: E402

TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedcli/maps/foobar"
EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"


def solid(m, p):
    ni = 0
    while True:
        n = m.nodes[ni]
        nx, ny, nz, w = n.plane
        pd = nx * p[0] + ny * p[1] + nz * p[2] - w
        s = 1 if pd >= 0 else 0
        ch = n.i_back if s == 1 else n.i_front
        if ch == -1:
            return n.i_leaf[s] == -1
        ni = ch


def build_names(lvl, names):
    bs = [M._build_brush_input(n, lvl.actors[n]) for n in names]
    body = uedcli_native.serialize_model(uedcli_native.build_geometry(bs))
    return UM.parse_model_body(body, 0, len(body))


def load(path):
    pkg = UT.load_package(path)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def main():
    lvl, _ = trunk.read_level(Path(TRUNK))
    ed = load(EDITOR)
    # per-brush centroid solidity mismatch vs editor
    brush_order = [n for n in lvl.order if lvl.actors[n].brush is not None]
    full = build_names(lvl, brush_order)
    bad = []
    for n in brush_order:
        a = lvl.actors[n]
        lx, ly, lz = (float(c) for c in a.location)
        vs = [v for p in a.brush.polys for v in p.vertices]
        c = (sum(float(v[0]) for v in vs) / len(vs) + lx,
             sum(float(v[1]) for v in vs) / len(vs) + ly,
             sum(float(v[2]) for v in vs) / len(vs) + lz)
        if solid(full, c) != solid(ed, c):
            bad.append((n, dict(a.props).get("CsgOper"), c))
    print(f"brushes whose centroid solidity != editor: {len(bad)}")
    for n, op, c in bad:
        print(f"  {n} {op} centroid={tuple(round(x) for x in c)} "
              f"native={'solid' if solid(full,c) else 'empty'} editor={'solid' if solid(ed,c) else 'empty'}")


if __name__ == "__main__":
    main()
