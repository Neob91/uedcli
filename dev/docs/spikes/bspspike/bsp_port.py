"""Slice 1 of the offline BSP engine (SPIKE-GRADE — parity vs editor not yet locked).

Faithful Python port of the pieces decoded in the 2026-06-24 BSP spikes:
  - FPoly classify/split against a plane (the ±0.25 THRESH_SPLIT_POLY_WITH_PLANE band,
    SplitWithPlaneFast @Engine 0x151f90: per-vertex d>=0 front / d<0 back; return
    0=Coplanar 1=Front 2=Back 3=Split).
  - FindBestSplit (@Editor 0x335d0): score (100-Balance)*Splits + Balance*|Front-Back|,
    portal candidate bonus + x16 portal-split penalty, candidate/classify step by
    optimization, strict-< earliest tie-break.
  - SplitPolyList: the textbook UE1 recursion (pick best plane, partition front/back,
    coplanar-same become the node surface, recurse) — to be diffed against the editor and
    refined where it diverges from Editor.dll 0x34530/0x34020.

Geometry is in double for now; float32 discipline at the thresholds is a later refinement
(the 0.25 band dwarfs float error for grid-aligned inputs, so cube/box parity is unaffected).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

SPLIT_BAND = 0.25          # THRESH_SPLIT_POLY_WITH_PLANE (Engine 0x10206780)
COPLANAR, FRONT, BACK, SPLIT = 0, 1, 2, 3
LAME, GOOD, OPTIMAL = 0, 1, 2
PF_PORTAL = 0x04000000
PF_STRUCTURAL_MASK = 0x28  # PF_Semisolid|PF_NotSolid


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def _norm(a): return _dot(a, a) ** 0.5


@dataclass
class FPoly:
    verts: list                      # list of (x,y,z) floats
    flags: int = 0
    tag: str | None = None           # debugging label

    def normal(self):
        # fan-sum (CalcNormal @Engine 0x150510), then normalize
        b = self.verts[0]
        n = (0.0, 0.0, 0.0)
        for i in range(2, len(self.verts)):
            c = _cross(_sub(self.verts[i - 1], b), _sub(self.verts[i], b))
            n = (n[0] + c[0], n[1] + c[1], n[2] + c[2])
        m = _norm(n) or 1.0
        return (n[0] / m, n[1] / m, n[2] / m)

    def plane(self):
        n = self.normal()
        return (n[0], n[1], n[2], _dot(self.verts[0], n))   # (nx,ny,nz,w), w=Base·N

    def is_portal(self): return bool(self.flags & PF_PORTAL)


def _pdot(plane, v):
    return plane[0] * v[0] + plane[1] * v[1] + plane[2] * v[2] - plane[3]


def classify(poly: FPoly, plane) -> int:
    """SplitWithPlaneFast classification (no fragment output)."""
    has_front = has_back = False
    for v in poly.verts:
        d = _pdot(plane, v)
        if d > SPLIT_BAND:
            has_front = True
        elif d < -SPLIT_BAND:
            has_back = True
    if has_front and has_back:
        return SPLIT
    if has_front:
        return FRONT
    if has_back:
        return BACK
    return COPLANAR


def split(poly: FPoly, plane):
    """Cut poly by plane → (front_poly, back_poly). Vertex side by sign of d (>=0 front),
    intersections inserted at d==0 crossings (Sutherland-Hodgman, both sides)."""
    front, back = [], []
    n = len(poly.verts)
    for i in range(n):
        a = poly.verts[i]
        b = poly.verts[(i + 1) % n]
        da, db = _pdot(plane, a), _pdot(plane, b)
        if da >= 0:
            front.append(a)
        else:
            back.append(a)
        if (da >= 0) != (db >= 0):
            t = da / (da - db)
            x = tuple(a[k] + t * (b[k] - a[k]) for k in range(3))
            front.append(x)
            back.append(x)
    fp = FPoly(front, poly.flags, poly.tag) if len(front) >= 3 else None
    bp = FPoly(back, poly.flags, poly.tag) if len(back) >= 3 else None
    return fp, bp


def find_best_split(polys: list[FPoly], optimization=OPTIMAL, balance=15, portal_bias=70) -> int:
    """Editor 0x335d0. Returns the index of the chosen splitter poly."""
    num = len(polys)
    inc = {OPTIMAL: 1, GOOD: num // 10}.get(optimization, num // 4)
    inc = max(inc, 1)
    pbias = portal_bias / 100.0
    best_i, best_score = None, None
    for i in range(0, num, inc):
        cand = polys[i]
        plane = cand.plane()
        front = back = splits = 0
        for j in range(0, num, inc):
            if j == i:
                continue
            c = classify(polys[j], plane)
            if c == FRONT:
                front += 1
            elif c == BACK:
                back += 1
            elif c == SPLIT:
                splits += 16 if polys[j].is_portal() else 1
        score = _f32(_f32((100.0 - balance) * splits) + _f32(balance * abs(front - back)))
        if cand.is_portal():
            score = _f32(score - _f32(_f32((100.0 - balance) * splits) * pbias))
        if best_score is None or score < best_score:    # strict < → earliest wins ties
            best_i, best_score = i, score
    return best_i


@dataclass
class Node:
    plane: tuple
    surf: list = field(default_factory=list)   # coplanar-same polys on this node
    front: "Node|None" = None
    back: "Node|None" = None


def split_poly_list(polys: list[FPoly], optimization=OPTIMAL, balance=15, portal_bias=70) -> Node | None:
    if not polys:
        return None
    best = polys[find_best_split(polys, optimization, balance, portal_bias)]
    plane = best.plane()
    surf, front, back = [], [], []
    for p in polys:
        c = classify(p, plane)
        if c == COPLANAR:
            # bspAddNode chains ALL coplanar polys onto this node (both facings) as its
            # coplanar surface list — they are NOT recursed (doing so loops forever).
            surf.append(p)
        elif c == FRONT:
            front.append(p)
        elif c == BACK:
            back.append(p)
        else:
            fp, bp = split(p, plane)
            if fp:
                front.append(fp)
            if bp:
                back.append(bp)
    node = Node(plane=plane, surf=surf)
    node.front = split_poly_list(front, optimization, balance, portal_bias) if front else None
    node.back = split_poly_list(back, optimization, balance, portal_bias) if back else None
    return node


def count_nodes(node: Node | None) -> int:
    """Editor node count = number of FPolys hung on the tree. Each coplanar poly at a node is
    its own node in the iPlane chain (bspAddNode), so count the surf list, not 1-per-plane."""
    if node is None:
        return 0
    here = max(1, len(node.surf))
    return here + count_nodes(node.front) + count_nodes(node.back)


def planes(node: Node | None, out=None):
    out = [] if out is None else out
    if node is not None:
        out.append(tuple(round(c, 4) for c in node.plane))
        planes(node.front, out)
        planes(node.back, out)
    return out


# --- hand brushes for parity checks ---------------------------------------------------------

def box(cx, cy, cz, hx, hy, hz, flags=0) -> list[FPoly]:
    """6 CCW-from-outside quad faces of an axis-aligned box centered at (cx,cy,cz)."""
    x0, x1 = cx - hx, cx + hx
    y0, y1 = cy - hy, cy + hy
    z0, z1 = cz - hz, cz + hz
    c = lambda x, y, z: (float(x), float(y), float(z))
    faces = {
        "+X": [c(x1, y0, z0), c(x1, y1, z0), c(x1, y1, z1), c(x1, y0, z1)],
        "-X": [c(x0, y1, z0), c(x0, y0, z0), c(x0, y0, z1), c(x0, y1, z1)],
        "+Y": [c(x1, y1, z0), c(x0, y1, z0), c(x0, y1, z1), c(x1, y1, z1)],
        "-Y": [c(x0, y0, z0), c(x1, y0, z0), c(x1, y0, z1), c(x0, y0, z1)],
        "+Z": [c(x0, y0, z1), c(x1, y0, z1), c(x1, y1, z1), c(x0, y1, z1)],
        "-Z": [c(x0, y1, z0), c(x1, y1, z0), c(x1, y0, z0), c(x0, y0, z0)],
    }
    return [FPoly(v, flags, tag) for tag, v in faces.items()]


if __name__ == "__main__":
    b = box(0, 0, 0, 256, 256, 256)
    tree = split_poly_list(b)
    print("single box -> nodes:", count_nodes(tree), "(expect 6 — convex, linear back-chain)")
    two = box(0, 0, 0, 128, 128, 128) + box(1024, 0, 0, 128, 128, 128)
    print("two disjoint boxes -> nodes:", count_nodes(split_poly_list(two)))
