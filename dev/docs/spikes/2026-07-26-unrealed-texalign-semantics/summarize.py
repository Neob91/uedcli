#!/usr/bin/env python3
"""Compact cross-mode table: one row per (face, mode) for a chosen face set."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import faces, fmt                                             # noqa: E402
from uedcli.polyalign import _dot, _len, _sub                              # noqa: E402

MODES = ["NONE", "DEFAULT", "FLOOR", "WALLDIR", "WALLX", "WALLY", "WALLPAN", "WALLCOLUMN",
         "ONETILE", "CLAMP"]


def main():
    outdir = Path(sys.argv[1])
    want = sys.argv[2:] or None
    data = {}
    for m in MODES:
        p = outdir / f"{m}.t3d"
        if not p.exists():
            continue
        for name, i, n, wv, base, tu, tv, pan, tex in faces(p):
            data.setdefault((name, i), {})[m] = (n, wv, base, tu, tv, pan, tex)

    for key in sorted(data):
        name, i = key
        if want and name not in want:
            continue
        n = data[key]["NONE"][0]
        print(f"\n=== {name}:{i}  n={fmt(n)}  tex={data[key]['NONE'][6]}")
        print(f"{'mode':<11}{'base (world)':<32}{'TextureU':<30}{'|TU|':>9}"
              f"  {'TextureV':<30}{'|TV|':>9}  pan       U-range            V-range")
        for m in MODES:
            if m not in data[key]:
                continue
            _n, wv, base, tu, tv, pan, _t = data[key][m]
            us = [_dot(_sub(v, base), tu) + pan[0] for v in wv]
            vs = [_dot(_sub(v, base), tv) + pan[1] for v in wv]
            print(f"{m:<11}{fmt(base, 9, 2):<32}{fmt(tu, 7, 4):<30}{_len(tu):9.5f}"
                  f"  {fmt(tv, 7, 4):<30}{_len(tv):9.5f}  ({pan[0]:g},{pan[1]:g})"
                  f"  [{min(us):8.2f},{max(us):8.2f}] [{min(vs):8.2f},{max(vs):8.2f}]")


if __name__ == "__main__":
    main()
