#!/usr/bin/env python3
"""Scan captured `points_hitN.bin` dumps (raw `FVector` arrays, 12 bytes/entry) for OceanLab N=203's
two divergent-point coordinates.  See `capture_bspoptgeom_points.py`'s docstring for the setup.

Target coordinates (x differs by 2 ULP between native and UED22; y/z identical either side):
  A: (x in {-256.0001220703125, -256.00006103515625}, y=600.000244140625, z=-1800.0)
  B: (x in {-256.0001220703125, -256.00006103515625}, y=504.000244140625, z=-1704.0)

Usage: analyze.py [logs_dir=logs]
"""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "logs"

X_BITS = {0xC3800002, 0xC3800004}  # UED's surviving value, native's added value
TARGETS = [
    ("A", struct.unpack("<I", struct.pack("<f", 600.000244140625))[0],
          struct.unpack("<I", struct.pack("<f", -1800.0))[0]),
    ("B", struct.unpack("<I", struct.pack("<f", 504.000244140625))[0],
          struct.unpack("<I", struct.pack("<f", -1704.0))[0]),
]


def scan(path: Path):
    data = path.read_bytes()
    n = len(data) // 12
    hits = []
    for i in range(n):
        xb, yb, zb = struct.unpack_from("<III", data, i * 12)
        if xb not in X_BITS:
            continue
        for label, yt, zt in TARGETS:
            if yb == yt and zb == zt:
                x = struct.unpack("<f", struct.pack("<I", xb))[0]
                y = struct.unpack("<f", struct.pack("<I", yb))[0]
                z = struct.unpack("<f", struct.pack("<I", zb))[0]
                hits.append((i, label, x, y, z, xb))
    return n, hits


def main():
    bins = sorted(LOGS.glob("points_hit*.bin"))
    if not bins:
        print(f"no points_hit*.bin under {LOGS}")
        return 1
    for p in bins:
        n, hits = scan(p)
        print(f"{p.name}: {n} points")
        for idx, label, x, y, z, xb in hits:
            tag = "native-added (0xc3800004)" if xb == 0xC3800004 else "UED-surviving (0xc3800002)"
            print(f"  idx={idx} target={label} ({x!r}, {y!r}, {z!r})  x-bits={xb:#010x}  {tag}")
        if not hits:
            print("  (neither target coordinate present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
