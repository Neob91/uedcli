#!/usr/bin/env python3
"""SPIKE driver — rotate each top facet of the revolved track bed BY ITS OWN ANGULAR POSITION
around the bend, so the texture follows the curve instead of running dead straight across it.

This is the "does per-face rotate alone solve curved track?" experiment. For each facet it computes
the facet centroid's bearing about the bend centre (phi = atan2(y, x)) and rotates that facet's
texture frame by -(phi - phi_ref), i.e. relative to the seed facet, so the seed keeps the frame the
builder gave it and every other facet fans around with the arc.

    apply_bend.py --trunk <maps/<level>> --brush <NAME> [--centre X,Y] [--sign +1|-1] [--dry-run]

Rotation ONLY — no pan. That is deliberate: the question is what rotation alone buys.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli import polyalign                                    # noqa: E402
from uedcli.cli.level_sources import TrunkLevelSource                    # noqa: E402
from uedcli.polyalign import _centroid, _world_verts            # noqa: E402
from poly_rotate import rotate_face                             # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trunk", required=True)
    ap.add_argument("--brush", required=True)
    ap.add_argument("--centre", default="0,0", help="bend centre in world XY (default the origin)")
    ap.add_argument("--sign", type=float, default=-1.0, choices=[1.0, -1.0],
                    help="which way the texture must turn to follow the bend (default -1)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    cx, cy = (float(v) for v in args.centre.split(","))
    src = TrunkLevelSource(Path(args.trunk))
    level = src.load()

    name = polyalign.resolve_actor_name(level, args.brush)
    actor = level.actors[name]
    idxs = polyalign.find_faces(actor, name, facing="+Z")
    if not idxs:
        print(f"no +Z faces on {name}", file=sys.stderr)
        return 2

    # Bearing of each facet's centroid about the bend centre, and the seed to measure against.
    bearings = {}
    for i in idxs:
        c = _centroid(_world_verts(actor, actor.brush.polys[i]))
        bearings[i] = math.degrees(math.atan2(c[1] - cy, c[0] - cx))
    ref = min(bearings, key=lambda i: bearings[i])          # the theta ~ 0 end of the arc

    for i in sorted(idxs, key=lambda i: bearings[i]):
        delta = args.sign * (bearings[i] - bearings[ref])
        print(f"{name}:{i}  bearing={bearings[i]:7.2f}deg  rotate_by={delta:8.2f}deg")
        if not args.dry_run:
            rotate_face(actor, actor.brush.polys[i], f"{name}:{i}", delta, "centroid")

    if args.dry_run:
        return 0
    src.save(verb="spike-bend", args={}, level=level, touched=[name])
    print(f"rotated {len(idxs)} facet(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
