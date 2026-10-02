#!/usr/bin/env python3
"""SPIKE CHECK — measure texture continuity across every shared edge of a face run.

A screenshot can suggest the seams match; this proves it. For each pair of faces sharing an edge, it
takes the edge's two endpoints and computes the (U,V) each face's own stored frame maps them to,
via the canonical T3D convention `U = (P - Origin).TextureU + PanU`. If the run is continuous, both
faces agree at every shared point, so the differences are zero to float precision.

    seam_check.py --trunk <maps/<level>> --brush NAME [--facing +Z]

Reports max |dU| and |dV| over all seams. This is the assertion a committed regression test should
make about `align --run`, at any --turn.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli.cli.level_sources import TrunkLevelSource                    # noqa: E402
from uedcli.polyalign import (_world_verts, face_uv,            # noqa: E402
                              resolve_actor_name, find_faces)

_WELD = 0.5


def _key(p):
    return (round(p[0] / _WELD), round(p[1] / _WELD), round(p[2] / _WELD))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trunk", required=True)
    ap.add_argument("--brush", required=True)
    ap.add_argument("--facing", default="+Z")
    args = ap.parse_args(argv)

    level = TrunkLevelSource(Path(args.trunk)).load()
    name = resolve_actor_name(level, args.brush)
    actor = level.actors[name]
    idxs = find_faces(actor, name, facing=None if args.facing == "any" else args.facing)

    verts = {i: _world_verts(actor, actor.brush.polys[i]) for i in idxs}
    edges: dict = {}
    for i, wv in verts.items():
        for k in range(len(wv)):
            a, b = wv[k], wv[(k + 1) % len(wv)]
            edges.setdefault(frozenset((_key(a), _key(b))), []).append((i, a, b))

    worst_u = worst_v = 0.0
    seams = 0
    for ek, owners in sorted(edges.items(), key=lambda kv: str(sorted(str(x) for x in kv[0]))):
        if len(owners) != 2:
            continue
        (ia, a0, a1), (ib, _, _) = owners
        seams += 1
        for p in (a0, a1):
            ua, va = face_uv(actor, actor.brush.polys[ia], p)
            ub, vb = face_uv(actor, actor.brush.polys[ib], p)
            du, dv = abs(ua - ub), abs(va - vb)
            worst_u, worst_v = max(worst_u, du), max(worst_v, dv)
        print(f"  seam {ia:>3}|{ib:<3}  dU={du:12.6f}  dV={dv:12.6f}")

    print(f"\n{seams} seam(s)   max |dU| = {worst_u:.6f}   max |dV| = {worst_v:.6f}")
    ok = worst_u < 1e-3 and worst_v < 1e-3
    print("CONTINUOUS" if ok else "DISCONTINUOUS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
