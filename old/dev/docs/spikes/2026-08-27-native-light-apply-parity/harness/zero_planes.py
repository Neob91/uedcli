#!/usr/bin/env python3
"""Does the editor keep a light on a surface's run when NO lumel of that surface is lit by it?

The native bake drops a light from a surface's run unless at least one lumel came out lit, which
makes the run "lights that actually contribute". If the editor instead lists whatever its visibility
gather returned and stores an all-zero plane for a light that reaches nothing, that difference alone
accounts for run entries native is missing. This counts, per map, how many of the per-(surface,
light) bit-planes are entirely zero.

Usage: zero_planes.py MAP.dx [MAP.dx ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lightparity import _load, level_model, light_names, runs  # noqa: E402


def main() -> int:
    repo = str(Path(__file__).resolve().parents[5])
    upackage, umodel = _load(repo)
    for path in sys.argv[1:]:
        pkg, m = level_model(upackage, umodel, path)
        r = runs(m, light_names(pkg, m))
        planes = zero = 0
        recs_all_zero = 0
        for k, rec in enumerate(m.light_map):
            n = len(r[k])
            if not n:
                continue
            per = ((rec.u_size + 7) // 8) * rec.v_size
            lit_here = 0
            for i in range(n):
                off = rec.data_offset + i * per
                planes += 1
                if not any(m.light_bits[off:off + per]):
                    zero += 1
                else:
                    lit_here += 1
            if not lit_here:
                recs_all_zero += 1
        print(f"{path}\n  per-(surf,light) planes: {planes}, entirely ZERO: {zero} "
              f"({100.0 * zero / (planes or 1):.1f}%)")
        print(f"  records with a non-empty run but NO lit lumel at all: {recs_all_zero}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
