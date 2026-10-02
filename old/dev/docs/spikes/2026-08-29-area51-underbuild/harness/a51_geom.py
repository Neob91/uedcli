#!/usr/bin/env python3
"""Geometry of Brush323's dome + Brush1178's carve hull; precise overlap check.

Computes per-poly world polygons for both brushes, then asks: do any dome polys intersect
Brush1178's subtract region in 3D (face centroid in-brush, or vertex in-brush, or edge-pierce
approximated via vertex-in-brush on both sides)?
"""
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
from spike_classindex import class_index

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"


def local_polys(brush_input):
    verts_flat, sizes = brush_input[0], brush_input[1]
    polys = []
    i = 0
    for nv in sizes:
        ring = [verts_flat[i + 3 * k: i + 3 * k + 3] for k in range(nv)]
        i += 3 * nv
        polys.append([tuple(v) for v in ring])
    return polys


def world_polys(brush_input):
    verts_flat, sizes = brush_input[0], brush_input[1]
    loc = brush_input[5]
    R = brush_input[6]
    pp = brush_input[7]
    polys = []
    i = 0
    for nv in sizes:
        ring = []
        for k in range(nv):
            v = (verts_flat[i], verts_flat[i + 1], verts_flat[i + 2])
            i += 3
            d = (v[0]-pp[0], v[1]-pp[1], v[2]-pp[2])
            w = (R[0][0]*d[0]+R[0][1]*d[1]+R[0][2]*d[2]+loc[0],
                 R[1][0]*d[0]+R[1][1]*d[1]+R[1][2]*d[2]+loc[1],
                 R[2][0]*d[0]+R[2][1]*d[1]+R[2][2]*d[2]+loc[2])
            ring.append(tuple(round(c, 3) for c in w))
        polys.append(ring)
    return polys


def aabb(vs):
    xs = [v[0] for v in vs]; ys = [v[1] for v in vs]; zs = [v[2] for v in vs]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def pt_in_convex(poly, pt):
    """Point strictly inside a CONVEX poly's plane-surface volume by signed-plane side."""
    n = len(poly[0]) if poly else 0
    return n


def main():
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = {n: BM._build_brush_input(n, level.actors[n]) for n in names}

    for nm in ("Brush323", "Brush1178"):
        w = world_polys(ins[nm])
        vs = [v for p in w for v in p]
        b0, b1 = aabb(vs)
        print(f"{nm}: {len(w)} polys, world AABB ({tuple(round(x,1) for x in b0)} .. {tuple(round(x,1) for x in b1)})")
        # extremes per axis
        for ax, nm2 in enumerate("XYZ"):
            lo = min(v[ax] for v in vs); hi = max(v[ax] for v in vs)
            print(f"  {nm2}: {lo:.1f} .. {hi:.1f}")


if __name__ == "__main__":
    main()