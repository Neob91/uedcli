"""Faithful, self-contained Python reference for UnrealEd 2.2's BSP partition-plane heuristic
`FindBestSplit` (Editor.dll 0x335d0) and the classifier `SplitWithPlaneFast` (Engine.dll
0x151f90) it drives. Decoded + byte-verified by `verify_heuristic.py` in this dir.

This is the SCORING + CANDIDATE-SELECTION step only — NOT the full `SplitPolyList` recursion
or the CSG world-surface build (those are the larger, separately-tracked engine-port slices,
see `../../2026-06-24-offline-bsp-engine-slices1b-2-3-parity.md`). It exists so the offline
BSP engine has a verified, drop-in-faithful reference for the one heuristic the whole tree
shape hinges on.

Geometry is in double here; the SCORE is computed float32-faithfully (`_f32`), matching the
SSE `movss/subss/mulss/addss` the editor uses — Splits/Front/Back/Balance are all integers, so
the only fractional term is the PortalBias bonus, and a float32 score keeps tie boundaries
identical to the binary.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# Thresholds + flags, all byte-verified against the DLLs (see verify_heuristic.py).
SPLIT_BAND = 0.25            # THRESH_SPLIT_POLY_WITH_PLANE (Engine 0x10206780 / -0.25 @0x1020b580)
COPLANAR, FRONT, BACK, SPLIT = 0, 1, 2, 3
LAME, GOOD, OPTIMAL = 0, 1, 2
PF_PORTAL = 0x04000000       # tested at [poly+0x1b0]
PF_STRUCTURAL = 0x28         # PF_Semisolid|PF_NotSolid — the structural mask

# MAP REBUILD defaults, byte-verified at the exec parser Editor.dll 0x65220.
DEFAULT_BALANCE = 50         # 0x32
DEFAULT_PORTAL_BIAS = 70     # 0x46 (raw; divided by 100 inside FindBestSplit)
DEFAULT_OPTIMIZATION = OPTIMAL  # bare MAP REBUILD resolves to OPTIMAL(2) -> Inc=1 (exact)


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


@dataclass
class FPoly:
    verts: list           # list of (x, y, z)
    flags: int = 0
    tag: str | None = None

    def normal(self):
        b = self.verts[0]
        n = (0.0, 0.0, 0.0)
        for i in range(2, len(self.verts)):
            c = _cross(_sub(self.verts[i - 1], b), _sub(self.verts[i], b))
            n = (n[0] + c[0], n[1] + c[1], n[2] + c[2])
        m = _dot(n, n) ** 0.5 or 1.0
        return (n[0] / m, n[1] / m, n[2] / m)

    def plane(self):
        nx, ny, nz = self.normal()
        return (nx, ny, nz, _dot(self.verts[0], (nx, ny, nz)))

    def is_portal(self) -> bool:
        return bool(self.flags & PF_PORTAL)

    def is_structural(self) -> bool:
        return bool(self.flags & PF_STRUCTURAL)


def _plane_dot(plane, v):
    return plane[0] * v[0] + plane[1] * v[1] + plane[2] * v[2] - plane[3]


def split_with_plane_fast(poly: FPoly, plane) -> int:
    """Engine.dll 0x151f90 classification (no fragment output). A vertex sets the FRONT flag
    only when its signed distance d > +0.25, the BACK flag only when d < -0.25; |d| <= 0.25 is
    'on' and sets neither. Return: 0=Coplanar 1=Front 2=Back 3=Split."""
    has_front = has_back = False
    for v in poly.verts:
        d = _plane_dot(plane, v)
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


def _inc_for(optimization: int, num: int) -> int:
    """The candidate/classify step. OPTIMAL(2)->1 (exact); GOOD(1)->num/10; LAME(0)->num/4;
    floored at 1. Both the candidate loop AND the classify loop step by this (so non-OPTIMAL
    scores a subsample). Editor 0x3369e-0x336c8."""
    if optimization == OPTIMAL:
        inc = 1
    elif optimization == GOOD:
        inc = num // 10
    else:
        inc = num // 4
    return max(inc, 1)


def find_best_split(
    polys: list[FPoly],
    *,
    optimization: int = DEFAULT_OPTIMIZATION,
    balance: int = DEFAULT_BALANCE,
    portal_bias: int = DEFAULT_PORTAL_BIAS,
) -> int:
    """Editor.dll 0x335d0. Returns the index of the chosen splitter poly.

    Candidate selection (the structural-splitter skip, fully decoded):
      - A pre-pass sets `all_structural` = (every poly has PF_Semisolid|PF_NotSolid set).
      - A candidate that IS structural is SKIPPED unless it's a portal, OR unless
        `all_structural` (then everything is a fair candidate). Non-structural polys and
        portals are always eligible.

    Score (float32): (100 - Balance)*Splits + Balance*|Front - Back|.
      A portal poly being SPLIT counts as 16 splits (not 1).
      A portal CANDIDATE gets a bonus: Score -= (100 - Balance)*Splits*PortalBias.
      Strict `<` keeps the EARLIEST candidate on ties — fully deterministic.
    """
    num = len(polys)
    if num <= 1:
        return 0
    inc = _inc_for(optimization, num)
    pbias = _f32(portal_bias / 100.0)
    all_structural = all(p.is_structural() for p in polys)

    # The candidate loop is NOT a plain `range(0, num, inc)`. The binary (Editor 0x336ff-0x33772,
    # loop-back 0x338c1) processes consecutive "slots" k=0,1,2,...: slot k spans candidate indices
    # [k*inc, (k+1)*inc) and the candidate USED is the FIRST eligible poly in that window. A
    # structural non-portal poly is skipped, advancing within the window; if the whole window is
    # skipped (or runs off the end), the slot yields no candidate and the next slot opens. The
    # loop ends when a slot's start index reaches `num`. So for inc>1 (GOOD/LAME) the candidate
    # positions are the first eligible poly at-or-after each inc-boundary, NOT the inc-boundary
    # itself, and a fully-structural window contributes no candidate. For OPTIMAL (inc=1) each
    # window is a single poly and this reduces to "every eligible poly".
    best_i, best_score = None, None
    slot_start = 0
    while slot_start < num:
        window_end = slot_start + inc
        cand_i = None
        for k in range(slot_start, min(window_end, num)):
            p = polys[k]
            if p.is_structural() and not p.is_portal() and not all_structural:
                continue                 # skip within the window
            cand_i = k
            break
        slot_start = window_end          # next slot regardless of whether this one yielded
        if cand_i is None:
            continue
        i = cand_i
        cand = polys[i]
        plane = cand.plane()
        front = back = splits = 0
        for j in range(0, num, inc):
            if j == i:
                continue
            c = split_with_plane_fast(polys[j], plane)
            if c == FRONT:
                front += 1
            elif c == BACK:
                back += 1
            elif c == SPLIT:
                splits += 16 if polys[j].is_portal() else 1
            # else: COPLANAR — counted by the editor but not part of the score.
        split_term = _f32(_f32(100.0 - balance) * splits)
        score = _f32(split_term + _f32(balance * abs(front - back)))
        if cand.is_portal():
            score = _f32(score - _f32(split_term * pbias))
        if best_score is None or score < best_score:
            best_i, best_score = i, score
    # The binary asserts here if no candidate was selected (`Best`, UnBsp.cpp:476); that is
    # unreachable for num>1 with at least one eligible poly, so return 0 defensively.
    return best_i if best_i is not None else 0


if __name__ == "__main__":
    # Sanity: a cube's 6 faces — with default Balance=50 every face splits nothing and is
    # balanced, so all score 0 and the EARLIEST (index 0) wins.
    def box(h=256.0):
        x = y = z = h
        c = lambda a, b, d: (a, b, d)
        return [
            FPoly([c(x, -y, -z), c(x, y, -z), c(x, y, z), c(x, -y, z)], tag="+X"),
            FPoly([c(-x, y, -z), c(-x, -y, -z), c(-x, -y, z), c(-x, y, z)], tag="-X"),
            FPoly([c(x, y, -z), c(-x, y, -z), c(-x, y, z), c(x, y, z)], tag="+Y"),
            FPoly([c(-x, -y, -z), c(x, -y, -z), c(x, -y, z), c(-x, -y, z)], tag="-Y"),
            FPoly([c(-x, -y, z), c(x, -y, z), c(x, y, z), c(-x, y, z)], tag="+Z"),
            FPoly([c(-x, y, -z), c(x, y, -z), c(x, -y, -z), c(-x, -y, -z)], tag="-Z"),
        ]
    b = box()
    i = find_best_split(b)
    print(f"cube best splitter = index {i} ({b[i].tag}); expect 0 (+X, earliest on a tie)")
