#!/usr/bin/env python3
"""Read the per-mode `MAP EXPORT`s the probe captured and print, per face, everything needed to
infer the rule TEXALIGN applied: the world texture frame, the texel densities, the in-plane axis
directions, the (U,V) range the face spans, and where the anchor point sits.

    analyze.py <outdir> [MODE ...]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli.model import parse_t3d                                        # noqa: E402
from uedcli.polyalign import _cross, _dot, _len, _sub, _world_verts       # noqa: E402
from uedcli.preview import _face_normal                                   # noqa: E402
from uedcli.preview_native import _world_uv_frame                         # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture import TEXTURES                                              # noqa: E402

SKIP = {"LevelInfo", "Brush"}


def faces(path: Path):
    lvl = parse_t3d(path.read_text())
    for name, a in lvl.actors.items():
        if a.brush is None or a.cls.split(".")[-1] == "LevelInfo":
            continue
        if a.props and any(k == "CsgOper" for k, _ in a.props) is False:
            continue                                   # the red builder brush
        for i, p in enumerate(a.brush.polys):
            wv = _world_verts(a, p)
            if len(wv) < 3:
                continue
            n = _face_normal(wv)
            m = _len(n)
            if m < 1e-9:
                continue
            n = (n[0] / m, n[1] / m, n[2] / m)
            base, tu, tv, pan = _world_uv_frame(a, p)
            yield name, i, n, wv, base, tu, tv, pan, (p.texture or "")


def fmt(v, w=8, p=3):
    return "(" + ",".join(f"{c:+{w}.{p}f}" for c in v) + ")"


def report(path: Path):
    print(f"\n########## {path.stem}")
    for name, i, n, wv, base, tu, tv, pan, tex in faces(path):
        lu, lv = _len(tu), _len(tv)
        us = [_dot(_sub(v, base), tu) + pan[0] for v in wv]
        vs = [_dot(_sub(v, base), tv) + pan[1] for v in wv]
        # face extent along the texture axes, in world units
        eu = (max(us) - min(us)) / lu if lu else 0.0
        ev = (max(vs) - min(vs)) / lv if lv else 0.0
        tsize = TEXTURES.get(tex if "." in tex else "GameMisc." + tex, (0, 0))
        handed = _dot(_cross(tu, tv), n)
        print(f"{name:9s}:{i} n={fmt(n)} tex={tex:16s}{tsize}")
        print(f"           base={fmt(base, 9, 2)} pan=({pan[0]:g},{pan[1]:g})")
        print(f"           TU={fmt(tu, 8, 4)} |TU|={lu:9.5f}   TV={fmt(tv, 8, 4)} |TV|={lv:9.5f}")
        print(f"           U:[{min(us):9.2f},{max(us):9.2f}] span={max(us)-min(us):9.2f}  "
              f"V:[{min(vs):9.2f},{max(vs):9.2f}] span={max(vs)-min(vs):9.2f}")
        print(f"           face size along TU/TV (uu) = {eu:.2f} x {ev:.2f}   "
              f"cross(TU,TV).n = {handed:+.4f}")


def main():
    outdir = Path(sys.argv[1])
    modes = sys.argv[2:]
    for p in sorted(outdir.glob("*.t3d")):
        if p.stem == "pasted":
            continue
        if modes and p.stem not in modes:
            continue
        report(p)


if __name__ == "__main__":
    main()
