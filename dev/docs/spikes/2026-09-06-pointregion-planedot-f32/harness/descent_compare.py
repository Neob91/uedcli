#!/usr/bin/env python3
"""Walk one point down a built world BSP twice -- native's old f64 plane dot and the engine's f32
`FPlane::PlaneDot` -- and print both trails. Written for Island `Brush1359` / NYC_Bar `Brush69`.

Usage:  descent_compare.py <package.dx> <X> <Y> <Z>
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli.native import umodel as UM              # noqa: E402
from uedcli.native.csg_golden import _find_model_export  # noqa: E402
from uedcli.native.materialize import _plane_dot     # noqa: E402


def dot_f64(plane, p) -> float:
    """What native did before 2026-09-06: full double precision, left-to-right."""
    x, y, z, w = plane
    return x * p[0] + y * p[1] + z * p[2] - w


def descend(model, p, dotfn):
    trail = []
    i_node, i_parent, is_front = 0, 0, 0
    while i_node != -1:
        n = model.nodes[i_node]
        pd = dotfn(n.plane, p)
        is_front = 1 if pd >= 0 else 0
        trail.append((i_node, n.plane, pd, is_front))
        i_parent, i_node = i_node, (n.i_back if is_front == 1 else n.i_front)
    leaf = model.nodes[i_parent].i_leaf[is_front]
    zone = model.leaves[leaf].i_zone if 0 <= leaf < len(model.leaves) else 0
    return leaf, zone, trail


def main() -> int:
    buf = Path(sys.argv[1]).read_bytes()
    off, size = _find_model_export(buf)
    model = UM.parse_model_body(buf, off, size)
    p = tuple(struct.unpack("<f", struct.pack("<f", float(v)))[0] for v in sys.argv[2:5])
    print(f"nodes={len(model.nodes)} leaves={len(model.leaves)} point={p}")
    for label, fn in (("f64 (old native)", dot_f64), ("f32 (engine)", _plane_dot)):
        leaf, zone, trail = descend(model, p, fn)
        print(f"{label}: iLeaf={leaf} zone={zone} depth={len(trail)}")
        for i_node, plane, pd, is_front in trail:
            print(f"   node {i_node:5d} plane={plane} dot={pd!r} IsFront={is_front}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
