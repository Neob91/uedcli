#!/usr/bin/env python3
"""SPIKE — the SHEARED-FRAME alternative to `align --run`'s orthogonal frame.

QUESTION: `run_align.py` writes an ORTHOGONAL texture frame and pays a seam shear of
`2*sin(dtheta/2)*half_width` texels (measured, and predictive across segment counts). T3D stores
TextureU and TextureV as INDEPENDENT FVectors with no orthogonality requirement, so a deliberately
sheared frame is representable. Does one exist that makes the seams match EXACTLY, and what does it
cost?

THE CONSTRUCTION
----------------
Work in polar coordinates about the bend centre C. The ideal "every radial strip advances by its own
arc length" mapping is

    U = du * r * psi        V = dv * r          (psi = angle along the run, r = radius)

which is NOT affine in P, so no texture frame reproduces it over a whole facet. But a texture frame
only has to agree with its NEIGHBOUR, and neighbours meet on a SEAM — a radial edge at fixed psi,
where `r*psi` is linear in r. So match the ideal on both of a facet's seams:

  * gradient along the entry seam's radial direction  u_a:  tu . u_a = du * psi_a
  * gradient along the exit  seam's radial direction  u_b:  tu . u_b = du * psi_b
  * value at the bend centre (r = 0):                       U(C) = 0

Three conditions, three degrees of freedom (two in-plane gradient components plus the constant), and
they are CONSISTENT because both seams independently want U = 0 at r = 0 — which is why this works
at all. Setting Origin = C satisfies the third condition for both axes at once. Face k's exit
condition is identical to face k+1's entry condition, so adjacent frames agree on their shared seam
exactly, by construction rather than by tuning.

`tv` is solved the same way against a constant gradient (V = dv*r), and the resulting `tu`/`tv` are
NOT perpendicular — that is the point, and the cost: texels are sheared within each facet.

    shear_align.py --trunk <maps/<level>> --brush NAME [--centre X,Y] [--facing +Z]
                   [--density-u F] [--density-v F]
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli import rotation                                     # noqa: E402
from uedcli.dispatch import TrunkLevelSource                    # noqa: E402
from uedcli.polyalign import (_cross, _dot, _len, _scale, _sub, _unit,   # noqa: E402
                              _world_verts, resolve_actor_name, find_faces)
from uedcli.texframe import world_uv_frame                      # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_align import _edges, order_run                         # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trunk", required=True)
    ap.add_argument("--brush", required=True)
    ap.add_argument("--centre", default="0,0")
    ap.add_argument("--facing", default="+Z")
    ap.add_argument("--density-u", type=float, default=None)
    ap.add_argument("--density-v", type=float, default=None)
    args = ap.parse_args(argv)

    cx, cy = (float(v) for v in args.centre.split(","))
    src = TrunkLevelSource(Path(args.trunk))
    level = src.load()
    name = resolve_actor_name(level, args.brush)
    actor = level.actors[name]
    idxs = find_faces(actor, name, facing=args.facing)
    faces = [(i, _world_verts(actor, actor.brush.polys[i])) for i in idxs]
    run = order_run(faces)

    _, tu0, tv0, _ = world_uv_frame(actor, actor.brush.polys[run[0][0]])
    du = args.density_u if args.density_u is not None else (_len(tu0) or 1.0)
    dv = args.density_v if args.density_v is not None else (_len(tv0) or 1.0)

    n = _unit(_cross(_sub(run[0][1][1], run[0][1][0]), _sub(run[0][1][2], run[0][1][0])))
    C = (cx, cy, run[0][1][0][2])                     # bend centre, in the faces' plane

    def bearing(p):
        return math.atan2(p[1] - cy, p[0] - cx)

    # psi must INCREASE along the run; take the sign from the first face's two seams.
    e0 = _edges(run[0][1])
    b_a0, b_b0 = bearing(e0[run[0][2]][1]), bearing(e0[run[0][3]][1])
    sign = 1.0 if (b_b0 - b_a0) > 0 else -1.0
    psi0 = b_a0

    R = rotation.actor_matrix(actor)
    pp = tuple(float(c) for c in rotation.actor_prepivot(actor))
    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    rinv = rotation.inverse(R) if R is not None else None

    for idx, wv, entry_i, exit_i in run:
        eds = _edges(wv)
        pa, pb = eds[entry_i][1], eds[exit_i][1]
        psi_a = sign * (bearing(pa) - psi0)
        psi_b = sign * (bearing(pb) - psi0)
        ua = _unit(_sub(pa, C))                        # radial direction at the entry seam
        ub = _unit(_sub(pb, C))                        # ... and at the exit seam

        # In-plane basis (ua, n x ua); ub = (cos D, sin D).
        b1, b2 = ua, _unit(_cross(n, ua))
        D = math.atan2(_dot(_cross(ua, ub), n), _dot(ua, ub))
        if abs(math.sin(D)) < 1e-9:
            print(f"face {idx}: seams are parallel — no bend to solve", file=sys.stderr)
            return 2

        def solve(c_a, c_b):
            """The in-plane vector g with g.ua = c_a and g.ub = c_b."""
            x = c_a
            y = (c_b - c_a * math.cos(D)) / math.sin(D)
            return tuple(x * b1[j] + y * b2[j] for j in range(3))

        tu_w = solve(du * psi_a, du * psi_b)
        tv_w = solve(dv, dv)

        cosang = _dot(_unit(tu_w), _unit(tv_w))
        print(f"{name}:{idx}  psi=[{math.degrees(psi_a):6.2f},{math.degrees(psi_b):6.2f}]deg  "
              f"|tu|={_len(tu_w):7.3f}  |tv|={_len(tv_w):6.3f}  "
              f"tu^tv={math.degrees(math.acos(max(-1,min(1,cosang)))):6.2f}deg")

        poly = actor.brush.polys[idx]
        rel = _sub(C, loc)
        if rinv is None:
            org, tu, tv = (rel[0] + pp[0], rel[1] + pp[1], rel[2] + pp[2]), tu_w, tv_w
        else:
            ro = rotation.matvec(rinv, rel)
            org = (ro[0] + pp[0], ro[1] + pp[1], ro[2] + pp[2])
            tu = rotation.matvec(rinv, tu_w)
            tv = rotation.matvec(rinv, tv_w)
        poly.origin = tuple(float(v) for v in org)
        poly.texture_u = tuple(float(v) for v in tu)
        poly.texture_v = tuple(float(v) for v in tv)
        poly.pan = (0, 0)

    src.save(verb="spike-shear", args={}, level=level, touched=[name])
    print(f"sheared frame written to {len(run)} face(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
