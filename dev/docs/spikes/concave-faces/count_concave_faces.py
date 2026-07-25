"""Spike harness: count CONCAVE brush faces in exported UE1/Deus Ex maps.

Question: are UnrealEd brush faces always convex? (The on-face decal placement, `preview.
_max_inscribed_box`, has a fast exact path for convex faces and a fallback for concave ones — this
measures how often the fallback is actually needed.) Finding: convex is the strong norm but NOT a hard
invariant — a small fraction of faces in real exported maps are concave (arbitrary vertex editing in
UnrealEd can produce them). See findings.md.

Run:  cd Tools/uedctl && env PYTHONPATH=. .venv/bin/python \
        dev/docs/spikes/concave-faces/count_concave_faces.py <map.t3d> [<map.t3d> ...]
"""
import math
import os
import sys


def _find_pkg_root(start):
    d = os.path.dirname(os.path.abspath(start))
    while d != os.path.dirname(d):
        if os.path.isfile(os.path.join(d, "uedctl", "__init__.py")):
            return d
        d = os.path.dirname(d)
    raise RuntimeError("could not locate the uedctl package root above " + start)


sys.path.insert(0, _find_pkg_root(__file__))

from uedctl.model import parse_t3d
from uedctl.rotation import actor_linear, actor_prepivot, local_offset


def is_face_convex(v3) -> bool:
    """Cross-product turn-sign consistency of the face's vertices, projected to its own plane."""
    if len(v3) < 4:
        return True
    ax = [v3[1][i] - v3[0][i] for i in range(3)]
    bx = [v3[2][i] - v3[0][i] for i in range(3)]
    n = [ax[1] * bx[2] - ax[2] * bx[1], ax[2] * bx[0] - ax[0] * bx[2], ax[0] * bx[1] - ax[1] * bx[0]]
    nl = math.sqrt(sum(c * c for c in n)) or 1.0
    n = [c / nl for c in n]
    u = ax
    ul = math.sqrt(sum(c * c for c in u)) or 1.0
    u = [c / ul for c in u]
    w = [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]
    p2 = [(sum(v[i] * u[i] for i in range(3)), sum(v[i] * w[i] for i in range(3))) for v in v3]
    signs = set()
    m = len(p2)
    for i in range(m):
        a, b, c = p2[i], p2[(i + 1) % m], p2[(i + 2) % m]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cr) > 1e-6:
            signs.add(cr > 0)
    return len(signs) <= 1


def main(paths):
    for path in paths:
        lvl = parse_t3d(open(path).read())
        total = concave = big = 0
        for a in lvl.actors.values():
            if a.brush is None:
                continue
            R, pp = actor_linear(a), actor_prepivot(a)
            loc = a.location or (0, 0, 0)
            for poly in a.brush.polys:
                v3 = [(float(loc[0] + w[0]), float(loc[1] + w[1]), float(loc[2] + w[2]))
                      for w in (local_offset(R, pp, v) for v in poly.vertices)]
                total += 1
                if len(v3) > 4:
                    big += 1
                if not is_face_convex(v3):
                    concave += 1
        pct = 100.0 * concave / total if total else 0.0
        print(f"{os.path.basename(path)}: {total} faces, {big} with >4 verts, "
              f"{concave} concave ({pct:.2f}%)")


if __name__ == "__main__":
    main(sys.argv[1:] or ["Temp/hexagon.t3d"])
