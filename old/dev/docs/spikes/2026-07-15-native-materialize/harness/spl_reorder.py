#!/usr/bin/env python3
"""Reimplement SplitPolyList (Editor 0x34530) + FindBestSplit in Python and test whether the
soup ORDER (not content) is what flips the root choice at N=2.  Runs SplitPolyList on native's
reconstructed repartition soup in several orders and reports the resulting node count + root plane,
comparing to the editor's 14-node tree (root plane = floor z=0).

This isolates: is native's over-fragmentation caused purely by the tie-break/soup ORDER feeding
FindBestSplit (=> reorder reproduces the editor), or by soup CONTENT (=> no reorder helps)?
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fbs_score as F  # noqa: E402

THRESH = 0.25


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def split_poly(poly, base, normal):
    """Full split (returns ('front'|'back'|'coplanar', None) or ('split', frontPoly, backPoly))."""
    verts = poly.verts
    dists = [_dot(_sub(v, base), normal) for v in verts]
    mx, mn = max(dists), min(dists)
    if mx < THRESH and mn > -THRESH:
        return ("coplanar", None, None)
    if mx < THRESH and mn <= -THRESH:
        return ("back", None, None)
    if mx >= THRESH and mn > -THRESH:
        return ("front", None, None)
    n = len(verts)
    fv, bv = [], []
    side = lambda d: 0 if d > THRESH else (1 if d < -THRESH else 2)
    for i in range(n):
        prev = verts[(i + n - 1) % n]
        cur = verts[i]
        pd, td = dists[(i + n - 1) % n], dists[i]
        ps, cs = side(pd), side(td)
        if (ps == 0 and cs == 1) or (ps == 1 and cs == 0):
            f = pd / (pd - td)
            inter = tuple(prev[k] + (cur[k] - prev[k]) * f for k in range(3))
            fv.append(inter)
            bv.append(inter)
        if cs == 0:
            fv.append(cur)
        elif cs == 1:
            bv.append(cur)
        else:
            fv.append(cur)
            bv.append(cur)
    fp = F.Poly(poly.base, poly.normal, fv, poly.poly_flags, poly.tag)
    bp = F.Poly(poly.base, poly.normal, bv, poly.poly_flags, poly.tag)
    return ("split", fp, bp)


class Node:
    __slots__ = ("plane", "tag", "coplanars")

    def __init__(self, plane, tag):
        self.plane = plane
        self.tag = tag
        self.coplanars = 0


def split_poly_list(polys, nodes, depth=0):
    if not polys or depth > 200:
        return
    best, _ = F.find_best_split(polys)
    splitter = polys[best]
    plane = tuple(round(c, 1) for c in splitter.normal) + (round(_dot(splitter.normal, splitter.base), 1),)
    nd = Node(plane, splitter.tag)
    nodes.append(nd)
    front, back = [], []
    for j, p in enumerate(polys):
        if j == best:
            continue
        r = split_poly(p, splitter.base, splitter.normal)
        if r[0] == "front":
            front.append(p)
        elif r[0] == "back":
            back.append(p)
        elif r[0] == "coplanar":
            nodes.append(Node(plane, p.tag))  # NODE_Plane coplanar chain
            nd.coplanars += 1
        else:
            _, fp, bp = r
            if len(fp.verts) >= 3:
                front.append(fp)
            if len(bp.verts) >= 3:
                back.append(bp)
    split_poly_list(front, nodes, depth + 1)
    split_poly_list(back, nodes, depth + 1)


def run(polys, label):
    nodes = []
    split_poly_list(list(polys), nodes)
    from collections import Counter
    pc = Counter(n.plane for n in nodes)
    print(f"[{label}] -> {len(nodes)} nodes; root={nodes[0].plane} ({nodes[0].tag})")
    return nodes, pc


def build_soup():
    import subset_diff as S
    import os
    os.environ["UEDCLI_BSPCSG_NOREPART"] = "1"
    nat = S.build_native_subset(2)
    polys = []
    for n in nat.nodes:
        if n.num_vertices == 0:
            continue
        s = nat.surfs[n.i_surf]
        base = nat.points[s.p_base]
        normal = nat.vectors[s.v_normal]
        verts = [nat.points[nat.verts[n.i_vert_pool + k].i_vertex] for k in range(n.num_vertices)]
        pk = tuple(round(c, 1) for c in n.plane)
        polys.append(F.Poly(base, normal, verts, s.poly_flags, tag=f"surf{n.i_surf}{pk}"))
    return polys


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    soup = build_soup()
    print(f"native soup: {len(soup)} polys (order = incremental node-array order)")
    n1, c1 = run(soup, "native-order")
    # Hypothesis A: World faces (World subtract = first brush; its faces + re-added floor frags)
    # before the WallBack Add faces.  World faces = surf 0-5; Add faces = surf 6-11.
    def surf_id(p):
        return int(p.tag[4:p.tag.index("(")])
    world = [p for p in soup if surf_id(p) <= 5]
    add = [p for p in soup if surf_id(p) > 5]
    n2, c2 = run(world + add, "world-first")
    n3, c3 = run(add + world, "add-first")
