#!/usr/bin/env python3
"""Per-brush property table for Vandenberg's world-CSG list: structural index k (the trace's
alignment key), actor index bi, name, CsgOper, PolyFlags, poly count, scaled/mirrored(det<0)/
sheared/rotated -- so a divergent k from the count trace maps straight to brush properties.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vdb_lib as V  # noqa: E402

from uedcli import rotation as ROT       # noqa: E402
from uedcli.transform import det3        # noqa: E402


def main() -> int:
    level, names = V.world_csg_names()
    k = 0
    for bi, nm in enumerate(names):
        a = level.actors[nm]
        raw = dict(a.props)
        pf = int(raw.get("PolyFlags", "0") or 0)
        # bspcsg.rs eff_flags: Portal forces NotSolid + clears Semisolid before the pass split.
        eff = ((pf & ~0x20) | 0x08) if pf & 0x0400_0000 else pf
        semisolid = bool(eff & 0x20)
        ms, ps = ROT.actor_main_scale(a), ROT.actor_post_scale(a)
        scaled = not (ms.is_identity() and ps.is_identity())
        det = mirrored = sheer = None
        if scaled:
            L = ROT.actor_linear(a)
            det = det3(L)
            mirrored = det < 0.0
            sheer = float(ms.sheer_rate) != 0.0 or float(ps.sheer_rate) != 0.0
        row_k = "-" if semisolid else str(k)
        if not semisolid:
            k += 1
        print(f"k={row_k:>4} bi={bi:4d} {nm:14s} oper={raw.get('CsgOper', '-'):13s} "
              f"pf={pf:#8x} npolys={len(a.brush.polys):3d} scaled={int(scaled)} "
              f"mirror={'-' if mirrored is None else int(mirrored)} "
              f"sheer={'-' if sheer is None else int(sheer)} "
              f"det={'-' if det is None else f'{det:.6g}'} "
              f"rot={raw.get('Rotation', '-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
