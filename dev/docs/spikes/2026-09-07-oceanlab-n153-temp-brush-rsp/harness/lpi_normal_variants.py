#!/usr/bin/env python3
"""Which plane normal produces UED22's OceanLab N=153 cut vertex, and which produces native's.

`FLinePlaneIntersection` (`Engine.dll 0x1506f0`) in f32, on the exact edge and plane base the
divergence rides on: `Brush147`'s world edge (-12, 96, -1856) -> (-12, 160, -1856) cut by
`Brush431`'s 45° face through (0, -0.000244140625, -1704).

Every SYMMETRIC +/-1/sqrt(2) normal gives the editor's `0x4317fff0` (151.999755859375). Only the
asymmetric `(0, 0.707106, 0.707108)` -- an authored TEXTURE axis of a coplanar sibling face that
native's temp brush BSP let into the Vectors pool -- gives native's `0x4318000d` (152.0001983642578).

Run: `lpi_normal_variants.py` (needs numpy).
"""
from __future__ import annotations

import struct

import numpy as np


def f32(bits: int) -> np.float32:
    return np.float32(struct.unpack("<f", struct.pack("<I", bits))[0])


def bits_of(x) -> int:
    return struct.unpack("<I", struct.pack("<f", np.float32(x)))[0]


def line_plane_intersection(p1, p2, base, normal):
    """`t = ((Base-P1).N) / ((P2-P1).N)`, dots reduced left-to-right, all f32."""
    p1, p2, base, normal = ([np.float32(v) for v in t] for t in (p1, p2, base, normal))
    d = [np.float32(p2[i] - p1[i]) for i in range(3)]
    bp = [np.float32(base[i] - p1[i]) for i in range(3)]

    def dot(a, b):
        return np.float32(np.float32(np.float32(a[0] * b[0]) + np.float32(a[1] * b[1]))
                          + np.float32(a[2] * b[2]))

    t = np.float32(dot(bp, normal) / dot(d, normal))
    return [np.float32(p1[i] + np.float32(d[i] * t)) for i in range(3)]


P1 = (-12.0, 96.0, -1856.0)
P2 = (-12.0, 160.0, -1856.0)
BASE = (0.0, f32(0xB9800000), -1704.0)          # Brush431 poly 8's Origin, world space

VARIANTS = {
    "CalcNormal(local)        3f3504f4": (0, 0x3F3504F4, 0x3F3504F4),
    "authored Normal=         3f3504f7": (0, 0x3F3504F7, 0x3F3504F7),
    "world Vectors[449]       3f3504f3": (0, 0x3F3504F3, 0x3F3504F3),
    "the opposite face       -3f3504f7": (0, 0xBF3504F7, 0xBF3504F7),
    "sibling TextureU  3f3504e6/350508": (0, 0x3F3504E6, 0x3F350508),
}

if __name__ == "__main__":
    for name, nb in VARIANTS.items():
        out = line_plane_intersection(P1, P2, BASE, [f32(b) for b in nb])
        print(f"{name}  ->  y = {bits_of(out[1]):08x}  ({out[1]!r})")
