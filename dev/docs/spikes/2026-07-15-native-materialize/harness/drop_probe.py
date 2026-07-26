#!/usr/bin/env python3
"""Offline PointRegion + downward-LineCheck probe against a level Model.

Answers the "fell out of the world" question: for a spawn point, does the native BSP
(a) resolve it to an EMPTY leaf (not solid), and (b) have a SOLID floor below it that a
downward sweep hits?  If (a) fails the pawn is embedded in solid (zone 0 -> fell out); if
(b) fails the pawn PHYS_Falls to the world bottom -> fell out.

Uses the proven descent convention (spike 60): side = PlaneDot>=0 ? FRONT(iChild[1]=i_back)
: BACK(iChild[0]=i_front); iLeaf[side] is the terminal leaf. Solidity for LineCheck is
IsCsg: NumVertices>0 && (NodeFlags & (NF_NotCsg|NF_IsNew)) == 0.

Usage: python drop_probe.py Map.dx X,Y,Z [X,Y,Z ...]
"""
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
import utexture_decode as UT  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402


def load_model(path):
    pkg = UT.load_package(path)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def point_region(m, p):
    """Descend to the terminal; return (leaf_index or -1 for solid, iZone, path_len)."""
    ni = 0
    depth = 0
    while True:
        depth += 1
        n = m.nodes[ni]
        nx, ny, nz, w = n.plane
        pd = nx * p[0] + ny * p[1] + nz * p[2] - w
        side = 1 if pd >= 0 else 0
        child = n.i_back if side == 1 else n.i_front
        if child == -1:
            leaf = n.i_leaf[side]
            izone = n.i_zone[side]
            return leaf, izone, depth
        ni = child


def is_csg(n):
    return n.num_vertices > 0 and (n.node_flags & (0x01 | 0x20)) == 0


def floor_below(m, start, dz=-4096.0, step=2.0):
    """Sample PointRegion straight down from `start`; return the Z of the first empty->solid
    transition (the collision floor), else None (empty all the way down = falls forever)."""
    z = start[2]
    prev_solid = (point_region(m, start)[0] == -1)
    zi = z
    while zi > start[2] + dz:
        zi -= step
        solid = (point_region(m, (start[0], start[1], zi))[0] == -1)
        if solid and not prev_solid:
            return zi
        prev_solid = solid
    return None


def main():
    path = sys.argv[1]
    pts = []
    for tok in sys.argv[2:]:
        pts.append(tuple(float(x) for x in tok.split(",")))
    m = load_model(path)
    print(f"== {Path(path).name}: nodes={len(m.nodes)} leaves={len(m.leaves)} "
          f"zones={len(m.zones)}")
    for p in pts:
        leaf, izone, depth = point_region(m, p)
        floor = floor_below(m, p)
        tag = "SOLID(embedded->fellout)" if leaf == -1 else f"empty leaf {leaf} zone {izone}"
        fl = f"floor@z={floor:.1f}" if floor is not None else "NO FLOOR (falls forever)"
        print(f"  {p} -> {tag}; downward {fl}  (descent depth {depth})")


if __name__ == "__main__":
    main()
