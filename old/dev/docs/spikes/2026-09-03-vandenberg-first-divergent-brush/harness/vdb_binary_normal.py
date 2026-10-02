#!/usr/bin/env python3
"""Read the ORIGINAL `12_Vandenberg_Gas.dx` binary UPolys and print the full-precision normal
bits of polys matching a given local-vert signature -- checks whether the editor's stored node
plane equals the binary authored normal that the T3D export (6 decimals) truncates.

Usage: vdb_binary_normal.py [x,y,z of any vert to match ...]
"""
import struct
import sys
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[5]
H = WORKTREE / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"
sys.path.insert(0, str(H))
import upolys_decode as UP           # noqa: E402
from utexture_decode import load_package  # noqa: E402

DX = "/workspace/uedcli/dev/games/deusex/Maps/12_Vandenberg_Gas.dx"


def bits(x):
    return f"{struct.unpack('<I', struct.pack('<f', x))[0]:08x}"


def main() -> int:
    want = {tuple(float(c) for c in a.split(",")) for a in sys.argv[1:]} or {
        (56.0, -24.0, -20.0)}
    pkg = load_package(DX)
    for i in range(len(pkg.exports)):
        if pkg.class_of_export(i) != "Polys":
            continue
        e = pkg.exports[i]
        try:
            polys, ok = UP.decode_upolys(pkg.buf, e["soff"], e["ssize"])
        except Exception:
            continue
        for pi, p in enumerate(polys):
            if any(tuple(v) in want for v in p["verts"]):
                n = p["normal"]
                print(f"export {i} ({pkg.names[pkg.exports[i]["nm"]]}) poly {pi}: "
                      f"normal=({n[0]:.9g},{n[1]:.9g},{n[2]:.9g}) "
                      f"bits={bits(n[0])},{bits(n[1])},{bits(n[2])} "
                      f"base_bits={','.join(bits(c) for c in p['base'])} verts={p['verts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
