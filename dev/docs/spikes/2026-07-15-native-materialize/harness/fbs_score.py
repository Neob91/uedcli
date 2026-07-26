#!/usr/bin/env python3
"""Faithful Python port of UnrealEd `FindBestSplit` (Editor.dll 0x335d0) scoring, to compare the
root-splitter CHOICE our native tree-builder makes against the decoded editor algorithm on a GIVEN
FPoly soup.  Isolates method-1: given the same soup, does the decoded scoring pick the editor's root?

split_with_plane mirrors uedcli-native/src/fpoly.rs (THRESH=0.25).  Score = Balance*|F-B| +
(100-Balance)*Splits, Balance=50/PortalBias=70, OPTIMAL stride 1, no SPLIT_WEIGHT.  STRICT-less
tie-break keeps the earliest candidate.
"""
from __future__ import annotations

THRESH = 0.25
BALANCE = 50
PF_PORTAL = 0x04000000


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def classify(verts, base, normal):
    """Return 'front'|'back'|'coplanar'|'split' per fpoly.rs split_with_plane (count-only use)."""
    dists = [_dot(_sub(v, base), normal) for v in verts]
    mx = max(dists)
    mn = min(dists)
    if mx < THRESH and mn > -THRESH:
        return "coplanar"
    if mx < THRESH and mn <= -THRESH:
        return "back"
    if mx >= THRESH and mn > -THRESH:
        return "front"
    return "split"


class Poly:
    __slots__ = ("base", "normal", "verts", "poly_flags", "tag")

    def __init__(self, base, normal, verts, poly_flags=0, tag=""):
        self.base = base
        self.normal = normal
        self.verts = verts
        self.poly_flags = poly_flags
        self.tag = tag


def _inc(num_polys, opt):
    """FindBestSplit candidate stride: OPTIMAL(2)->1, GOOD(1)->NumPolys/10, else NumPolys/4; max 1."""
    if opt == 2:
        inc = 1
    elif opt == 1:
        inc = num_polys // 10
    else:
        inc = num_polys // 4
    return max(inc, 1)


def find_best_split(polys, balance=12, portal_bias=0, opt=1, verbose=False):
    """Faithful FindBestSplit.  Repartition params (byte-verified this spike): Balance=12,
    PortalBias=0, Opt=GOOD(1) -> stride NumPolys/10.  BOTH candidate and inner loops stride by Inc."""
    structural = lambda pf: (pf & 0x28) != 0 and (pf & PF_PORTAL) == 0
    all_structural = all(structural(p.poly_flags) for p in polys)
    if len(polys) == 1:
        return 0, []
    inv_bal = 100 - balance
    pbias = portal_bias / 100.0
    inc = _inc(len(polys), opt)
    best = -1
    best_score = float("inf")
    rows = []
    for i in range(0, len(polys), inc):
        cand = polys[i]
        if structural(cand.poly_flags) and not all_structural:
            rows.append((i, cand.tag, None, None, None, None, "SKIP"))
            continue
        front = back = 0
        splits = 0.0
        for j in range(0, len(polys), inc):
            if j == i:
                continue
            p = polys[j]
            r = classify(p.verts, cand.base, cand.normal)
            if r == "front":
                front += 1
            elif r == "back":
                back += 1
            elif r == "split":
                splits += 16.0 if (p.poly_flags & PF_PORTAL) else 1.0
        score2 = inv_bal * splits
        score = abs(front - back) * balance + score2
        if cand.poly_flags & PF_PORTAL:
            score -= score2 * pbias
        rows.append((i, cand.tag, front, back, int(splits), score, ""))
        if best == -1 or score < best_score:
            best_score = score
            best = i
    if verbose:
        print(f"{'idx':>3} {'tag':<26} {'F':>4} {'B':>4} {'Spl':>4} {'score':>9}")
        for (i, tag, f, b, s, sc, note) in sorted(rows, key=lambda r: (r[5] if r[5] is not None else 9e9)):
            if note == "SKIP":
                print(f"{i:>3} {tag:<26} {'--- structural skip ---'}")
            else:
                mark = "  <== BEST" if i == best else ""
                print(f"{i:>3} {tag:<26} {f:>4} {b:>4} {s:>4} {sc:>9.1f}{mark}")
    return best, rows
