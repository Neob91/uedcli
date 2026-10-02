#!/usr/bin/env python3
"""SPIKE PROTOTYPE — `brush poly align --run [--turn UU]`.

Walks a CONNECTED RUN of faces and lays one continuous texture along it: U follows the run, V runs
across it, and the phase accumulates by arc length so the pattern does not restart at each facet.
This is the generalisation of today's `--ring` (which is cylinder-only and rejects coplanar sets) to
any turning run, including the FLAT ANNULUS of a revolved track bed.

    run_align.py --trunk <maps/<level>> --brush NAME [--facing +Z] [--turn UU]
                 [--density-u F] [--density-v F] [--dry-run]

DERIVES, does not preserve. Each face's frame comes from the run geometry, so the caller does not
pre-rotate anything — that is the 2026-07-26 owner ruling that `--run` derives rather than preserves.

`--turn` is in UNREAL ROTATION UNITS (16384 = 90 degrees), matching every other angle in the CLI. It
is applied uniformly in each face's own RUN FRAME, not in world space, which is what keeps the seams
matching: every face receives the same transform relative to the run, so continuity is computed WITH
the turn rather than broken by it afterwards.

THE MATH
--------
Per face, let `d` = unit run direction (entry seam midpoint -> exit seam midpoint), `a` = unit across
direction (`n x d`), `s` = arc length accumulated before this face, `P0` = entry seam midpoint.
Define the run parameter of a point P as `(u,v) = ((P-P0).d + s, (P-P0).a)`, then rotate that 2D
frame by the turn and scale by the texel densities. Working the T3D convention
`U = (P - Origin).TextureU + PanU` backwards gives, for ANY turn angle:

    TextureU = du * rot(d, theta)      TextureV = dv * rot(a, theta)      Origin = P0 - s*d

Note `Origin` is independent of theta — the turn changes only the axes. Pan stays (0,0): the
continuity offset lives in the float Origin, so an author's later integer `poly pan` nudge cannot
collide with it.

ARC LENGTH IS MEASURED ON THE CENTRELINE (the seam midpoints), which is one of the three answers the
owner deferred on 2026-07-26 (per-strip / one reference radius / per-facet). Centreline is the
"one reference radius" option: sleepers stay in lockstep across the track width, at the cost of
slight stretch on the outer rail and squeeze on the inner. This spike does NOT settle that question,
it just has to pick one to render.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli import rotation                                     # noqa: E402
from uedcli.cli.level_sources import TrunkLevelSource                    # noqa: E402
from uedcli.polyalign import (_cross, _dot, _len, _scale, _sub, _unit,   # noqa: E402
                              _world_verts, resolve_actor_name, find_faces)
from uedcli.texframe import world_uv_frame                      # noqa: E402

_WELD = 0.5             # world points closer than this are the same point
UU = 65536.0            # unreal rotation units in a full turn


def _key(p):
    return (round(p[0] / _WELD), round(p[1] / _WELD), round(p[2] / _WELD))


def _edges(wv):
    """The face's edges as (key_pair, midpoint, index)."""
    out = []
    for i in range(len(wv)):
        a, b = wv[i], wv[(i + 1) % len(wv)]
        ka, kb = _key(a), _key(b)
        mid = tuple((a[j] + b[j]) / 2.0 for j in range(3))
        out.append((frozenset((ka, kb)), mid, i))
    return out


def order_run(faces):
    """Order `faces` [(idx, world_verts), …] into a connected run by shared edges, and return
    [(idx, wv, entry_edge_i, exit_edge_i), …]. Raises on a fork or a disconnected set."""
    edge_owners: dict = {}
    for idx, wv in faces:
        for ek, _, _ in _edges(wv):
            edge_owners.setdefault(ek, []).append(idx)

    nbrs: dict = {idx: {} for idx, _ in faces}
    for ek, owners in edge_owners.items():
        if len(owners) == 2:
            a, b = owners
            nbrs[a][b] = ek
            nbrs[b][a] = ek
        elif len(owners) > 2:
            raise SystemExit(f"run: edge shared by {len(owners)} faces — not a simple run")

    ends = [i for i, m in nbrs.items() if len(m) <= 1]
    if any(len(m) > 2 for m in nbrs.values()):
        raise SystemExit("run: a face has more than 2 neighbours — the set forks, not a run")
    if not ends:
        raise SystemExit("run: the set is a closed loop — pick a seam and exclude one join")
    start = min(ends)

    by_idx = dict(faces)
    order, prev = [], None
    cur = start
    while True:
        order.append(cur)
        nxt = next((n for n in nbrs[cur] if n != prev), None)
        if nxt is None:
            break
        prev, cur = cur, nxt
    if len(order) != len(faces):
        raise SystemExit(f"run: only {len(order)} of {len(faces)} faces form a connected run")

    out = []
    for pos, idx in enumerate(order):
        wv = by_idx[idx]
        eds = _edges(wv)
        exit_i = entry_i = None
        if pos + 1 < len(order):
            ek = nbrs[idx][order[pos + 1]]
            exit_i = next(e[2] for e in eds if e[0] == ek)
        if pos > 0:
            ek = nbrs[idx][order[pos - 1]]
            entry_i = next(e[2] for e in eds if e[0] == ek)
        # A run end has only one seam; the other end of the face is the OPPOSITE edge of the quad.
        if len(wv) != 4:
            raise SystemExit(f"run: face {idx} has {len(wv)} vertices — this spike handles quads")
        if entry_i is None:
            entry_i = (exit_i + 2) % 4
        if exit_i is None:
            exit_i = (entry_i + 2) % 4
        out.append((idx, wv, entry_i, exit_i))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trunk", required=True)
    ap.add_argument("--brush", required=True)
    ap.add_argument("--facing", default="+Z")
    ap.add_argument("--only", default=None,
                    help="comma-separated poly indices to restrict the run to (e.g. to open a "
                         "closed cylinder loop by dropping one face)")
    ap.add_argument("--turn", type=float, default=0.0,
                    help="uniform turn in UNREAL ROTATION UNITS (16384 = 90 degrees)")
    ap.add_argument("--density-u", type=float, default=None)
    ap.add_argument("--density-v", type=float, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    src = TrunkLevelSource(Path(args.trunk))
    level = src.load()
    name = resolve_actor_name(level, args.brush)
    actor = level.actors[name]
    idxs = find_faces(actor, name, facing=None if args.facing == "any" else args.facing)
    if args.only:
        keep = {int(v) for v in args.only.split(",")}
        idxs = [i for i in idxs if i in keep]
    if len(idxs) < 2:
        print(f"need >= 2 faces, got {len(idxs)}", file=sys.stderr)
        return 2

    faces = [(i, _world_verts(actor, actor.brush.polys[i])) for i in idxs]
    run = order_run(faces)

    # Texel density: adopt the seed face's, unless overridden.
    _, tu0, tv0, _ = world_uv_frame(actor, actor.brush.polys[run[0][0]])
    du = args.density_u if args.density_u is not None else (_len(tu0) or 1.0)
    dv = args.density_v if args.density_v is not None else (_len(tv0) or 1.0)
    theta = args.turn / UU * 2.0 * math.pi

    R = rotation.actor_matrix(actor)
    pp = tuple(float(c) for c in rotation.actor_prepivot(actor))
    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    rinv = rotation.inverse(R) if R is not None else None

    s = 0.0
    for idx, wv, entry_i, exit_i in run:
        eds = _edges(wv)
        p0 = eds[entry_i][1]
        p1 = eds[exit_i][1]
        seg = _sub(p1, p0)
        length = _len(seg)
        if length < 1e-9:
            print(f"face {idx}: zero-length run segment", file=sys.stderr)
            return 2
        d = _scale(seg, 1.0 / length)
        n = _unit(_cross(_sub(wv[1], wv[0]), _sub(wv[2], wv[0])))
        a = _unit(_cross(n, d))

        # Rotate the (d, a) run basis by theta about the face normal.
        c_, s_ = math.cos(theta), math.sin(theta)
        tu_dir = tuple(d[j] * c_ + a[j] * s_ for j in range(3))
        tv_dir = tuple(-d[j] * s_ + a[j] * c_ for j in range(3))
        tu_w = _scale(tu_dir, du)
        tv_w = _scale(tv_dir, dv)
        base_w = _sub(p0, _scale(d, s))

        print(f"{name}:{idx}  s={s:8.2f}  len={length:7.2f}  d=({d[0]:+.3f},{d[1]:+.3f},{d[2]:+.3f})")

        if not args.dry_run:
            poly = actor.brush.polys[idx]
            rel = _sub(base_w, loc)
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
        s += length

    print(f"run of {len(run)} face(s), total {s:.2f} uu, turn {args.turn} uu", file=sys.stderr)
    if args.dry_run:
        return 0
    src.save(verb="spike-run", args={}, level=level, touched=[name])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
