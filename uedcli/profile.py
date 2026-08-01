"""The shared 2D **profile** layer for the `brush build extrude` / `brush build revolve`
generators.

A **profile** is the closed 2D polygon an author draws with the repeatable `--point U,V`
flag; each of the two verbs sweeps it into one brush (extrude: straight along `--axis`;
revolve: around an in-plane axis). Everything here is purely two-dimensional — token
parsing, cleanup, a validity test, winding normalization, and the decomposition of a
concave/oversized ring into convex pieces. There is deliberately no `Brush`, no `Polygon`,
no world coordinate and no T3D in this module, so it is testable against plain pairs of
numbers.

A "point" is any pair `(u, v)` of numbers. `parse_point` produces `Decimal` pairs (exact,
so the error text and the zero-area test are exact); the builders convert to `float` at
their own boundary, because `builders._newell`/`_tex_basis` are float-only and a revolve is
trigonometric anyway. Nothing is lost: `emit.clean` re-Decimalizes via `Decimal(str(value))`,
so an authored `12.5` round-trips unchanged.

Cleanup mirrors what the engine does to every `FPoly` at `FPoly::Fix` /
`FPoly::RemoveColinears` (`dev/docs/unrealed/leveldesign/kb/csg-bsp.md` §5.2), so uedcli
rejects offline what the editor would otherwise silently mangle — and the emitted face count
matches what actually gets built.
"""
from __future__ import annotations

import decimal
import math
from decimal import Decimal

from .geometry import GeometryError

# Two profile points closer than WELD collapse to one (a zero-length ring edge). This constant
# LIVES HERE and `builders.py` imports it — never the other way round: `builders.WELD` is defined
# BELOW that module's import block, so a `profile` → `builders` import while `builders` imports
# `profile` is a load-time cycle that breaks every uedcli invocation (decisions.md 2026-07-25
# 02:30 UTC). Same value/meaning as the tolerance `builders._dedup_ring` has always used.
WELD = 1e-3

# A vertex whose two incident edges are parallel to within this (the sine of the angle between
# them) is redundant: it splits one flat side in two, and the engine's own `RemoveColinears`
# deletes it at build time regardless. Same magnitude as the engine literal decoded into
# `doctor.COLINEAR_NORMAL_EPS` (kept as a separate constant rather than imported, so this module
# stays free of any uedcli dependency but `geometry`).
COLLINEAR_EPS = 1e-4

# An engine `FPoly` holds at most 16 vertices (`FPoly::VERTEX_THRESHOLD`; decoded in
# spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md), so a cap ring longer than this must be
# tiled even when it is perfectly convex.
MAX_FPOLY_VERTS = 16


class ProfileError(GeometryError):
    """An unusable profile (bad token, too few points, self-intersecting, zero area, …).

    Subclassing `geometry.GeometryError` is what buys the clean CLI exit: `dispatch()` already
    catches `GeometryError` and prints it without a traceback, while it has no bare `ValueError`
    arm — so a plain `ValueError` subclass would traceback at the user (decisions.md 2026-07-25
    02:30 UTC).
    """


# --- parsing -----------------------------------------------------------------------------------


def parse_point(token: str) -> tuple[Decimal, Decimal]:
    """Parse one `--point U,V` token into an exact `(u, v)` Decimal pair.

    Called from the dispatch handler, NOT as an argparse `type=`: argparse catches `ValueError`
    and replaces the message with its own `invalid parse_point value: '128'`, which would destroy
    the wording below (`parse_coord` sidesteps that by raising `ArgumentTypeError`; here the
    exact message is the contract).
    """
    fields = token.split(",")
    if len(fields) != 2 or not all(f.strip() for f in fields):
        raise ProfileError(
            f"--point needs U,V (two comma-separated numbers), got: {token!r}")
    try:
        u = Decimal(fields[0].strip())
        v = Decimal(fields[1].strip())
    except decimal.InvalidOperation:
        raise ProfileError(f"--point U,V must be numbers, got: {token!r}") from None
    # `nan`/`inf` parse as valid Decimals but are not coordinates: they would build unbounded or
    # comparison-immune geometry that fails much later, naming neither the flag nor the value.
    if not (u.is_finite() and v.is_finite()):
        raise ProfileError(f"--point U,V must be numbers, got: {token!r}")
    return (u, v)


# --- small 2D helpers (float; these are tolerance comparisons, not stored values) ---------------


def _dist(a, b) -> float:
    return math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))


def _cross(o, a, b) -> float:
    """2D cross product of (a − o) × (b − o): > 0 when o→a→b turns counter-clockwise."""
    return ((float(a[0]) - float(o[0])) * (float(b[1]) - float(o[1]))
            - (float(a[1]) - float(o[1])) * (float(b[0]) - float(o[0])))


def _fmt(p) -> str:
    return f"({p[0]},{p[1]})"


# --- cleanup -----------------------------------------------------------------------------------


def _is_collinear(a, b, c) -> bool:
    """Is `b` redundant — do its two incident edges a→b and b→c run parallel?"""
    la, lc = _dist(a, b), _dist(b, c)
    if la == 0.0 or lc == 0.0:
        return True
    return abs(_cross(a, b, c)) / (la * lc) < COLLINEAR_EPS


def clean_profile(points):
    """Weld near-duplicates, drop redundant collinear vertices, and require ≥3 survivors.

    Steps 1–3 of the shared cleanup: welding covers consecutive AND wrap-around duplicates (so a
    caller who repeated the first point as the last is simply tidied up, not rejected), then any
    vertex whose two edges are parallel is dropped, never below 3. Returns a NEW list of the
    surviving points (the originals, untouched — nothing is rounded).
    """
    welded: list = []
    for p in points:
        if not welded or _dist(p, welded[-1]) > WELD:
            welded.append(p)
    if len(welded) > 1 and _dist(welded[0], welded[-1]) <= WELD:
        welded.pop()
    ring = _drop_collinear(welded)
    # The post-cleanup arity check (spec step 3) lives here, where the drop happens, and uses the
    # same wording as the dispatch-side pre-cleanup check.
    if len(ring) < 3:
        raise ProfileError(f"a profile needs at least 3 points, got {len(ring)} after welding "
                           f"duplicate and collinear vertices")
    return ring


def _drop_collinear(ring: list) -> list:
    out = list(ring)
    while len(out) > 3:
        n = len(out)
        for i in range(n):
            if _is_collinear(out[(i - 1) % n], out[i], out[(i + 1) % n]):
                del out[i]
                break
        else:
            break
    return out


# --- validity ----------------------------------------------------------------------------------


def _on_segment(p, q, r) -> bool:
    """Is `r` — already known to be collinear with p→q — inside that segment's span?"""
    return (min(float(p[0]), float(q[0])) - WELD <= float(r[0]) <= max(float(p[0]), float(q[0])) + WELD
            and min(float(p[1]), float(q[1])) - WELD <= float(r[1]) <= max(float(p[1]), float(q[1])) + WELD)


def _segments_intersect(p1, p2, p3, p4) -> bool:
    """Do segments p1→p2 and p3→p4 meet AT ALL — crossing, touching at an endpoint, or overlapping
    collinearly? (Deliberately not the strict "proper crossing" test: a mere touch between two
    non-adjacent edges is a pinch, which has no consistent inside either.)"""
    d1, d2 = _cross(p3, p4, p1), _cross(p3, p4, p2)
    d3, d4 = _cross(p1, p2, p3), _cross(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) \
            and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0:
        return True
    # Touching / collinear-overlapping: a zero turn plus containment in the other segment's span.
    return ((d1 == 0 and _on_segment(p3, p4, p1)) or (d2 == 0 and _on_segment(p3, p4, p2))
            or (d3 == 0 and _on_segment(p1, p2, p3)) or (d4 == 0 and _on_segment(p1, p2, p4)))


def check_simple(points) -> None:
    """Reject a profile that is not a simple (non-self-intersecting) ring.

    Two independent faults, both fatal, because a non-simple ring has no consistent inside: the
    convex decomposition would emit overlapping or inverted pieces with no error at all, and the
    brush built from them is a self-intersecting solid — a guaranteed BSP defect and a plausible
    editor crash.

    1. **A vertex repeated ANYWHERE in the ring** (not just consecutively — `clean_profile` welds
       only neighbours, so `A B C A D E` survives it while being a figure-eight).
    2. **Any two NON-ADJACENT edges that meet at all** — crossing, touching at an endpoint (a
       pinch), or overlapping collinearly. Adjacent edges legitimately share their endpoint.
    """
    n = len(points)
    for i in range(n):
        for j in range(i + 1, n):
            if _dist(points[i], points[j]) <= WELD:
                raise ProfileError(
                    f"profile is not simple: points {i} and {j} are the same vertex "
                    f"{_fmt(points[i])} — a ring that revisits a vertex has no consistent inside")
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue                       # adjacent edges share an endpoint by construction
            if _segments_intersect(points[i], points[(i + 1) % n],
                                   points[j], points[(j + 1) % n]):
                raise ProfileError(
                    f"profile is not simple: edge {i} ({_fmt(points[i])}→"
                    f"{_fmt(points[(i + 1) % n])}) and edge {j} ({_fmt(points[j])}→"
                    f"{_fmt(points[(j + 1) % n])}) intersect")


# --- winding -----------------------------------------------------------------------------------


def signed_area(points):
    """Twice-the-shoelace / 2 — positive for a counter-clockwise ring in `(u, v)`. Computed in the
    caller's own number type, so an exact `Decimal` profile gives an exact zero for a degenerate
    ring rather than float residue."""
    n = len(points)
    total = None                        # seeded from the first term, so the sum keeps the input's
    for i in range(n):                  # own numeric type (Decimal stays exact; float stays float)
        (x1, y1), (x2, y2) = points[i], points[(i + 1) % n]
        term = x1 * y2 - x2 * y1
        total = term if total is None else total + term
    return total / 2


def normalize_winding(points) -> list:
    """Return the ring wound COUNTER-CLOCKWISE in `(u, v)`, reversing a clockwise input.

    Downstream face construction can then assume CCW — which, under the right-handed `(u, v, axis)`
    mapping, means the profile's own 2D normal points along `+axis` for every `--axis`. The author
    never has to think about winding: either order is accepted. A ring of exactly zero signed area
    encloses nothing and is rejected.
    """
    area = signed_area(points)
    if area == 0:
        raise ProfileError("profile encloses zero area (its points are collinear or it doubles "
                           "back on itself) — there is nothing to sweep")
    return list(reversed(points)) if area < 0 else list(points)


# --- convex decomposition ----------------------------------------------------------------------


def is_convex(points) -> bool:
    """Does the ring turn the same way at every vertex (collinear turns ignored)?"""
    signs = set()
    n = len(points)
    for i in range(n):
        s = _cross(points[(i - 1) % n], points[i], points[(i + 1) % n])
        if abs(s) > 1e-9:
            signs.add(s > 0)
    return len(signs) <= 1


def _point_in_triangle(p, a, b, c) -> bool:
    """Is `p` inside triangle a-b-c, boundary included? (Used to reject a candidate ear that would
    swallow another vertex of the ring.)"""
    d1, d2, d3 = _cross(a, b, p), _cross(b, c, p), _cross(c, a, p)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def _ear_clip(ring: list) -> list[list[int]]:
    """Triangulate a simple, counter-clockwise ring by ear clipping; returns triangles as INDEX
    triples into `ring` (indices, so the merge step below can tell an original ring edge from a
    diagonal by identity rather than by coordinate comparison)."""
    idx = list(range(len(ring)))
    tris: list[list[int]] = []
    while len(idx) > 3:
        n = len(idx)
        for i in range(n):
            prev, cur, nxt = idx[(i - 1) % n], idx[i], idx[(i + 1) % n]
            a, b, c = ring[prev], ring[cur], ring[nxt]
            if _cross(a, b, c) <= 0:
                continue                       # reflex or collinear corner — not an ear
            if any(_point_in_triangle(ring[k], a, b, c) for k in idx
                   if k not in (prev, cur, nxt)):
                continue                       # the candidate ear swallows another vertex
            tris.append([prev, cur, nxt])
            del idx[i]
            break
        else:
            # Unreachable for a ring that passed `check_simple` (every simple polygon has an ear);
            # a clean refusal beats an infinite loop if that invariant is ever broken.
            raise ProfileError("profile could not be decomposed into convex pieces — is it a "
                               "simple, non-self-intersecting ring?")
    tris.append(list(idx))
    return tris


def _merge_across_shared_edge(ring: list, p1: list[int], p2: list[int]) -> list[int] | None:
    """Fuse two index rings that share a diagonal, if the result is still convex and short enough.

    `p1` and `p2` are both counter-clockwise, so a shared edge appears as `a→b` in one and `b→a` in
    the other. The fused ring walks `p1` from `b` all the way round to `a`, then continues through
    `p2`'s vertices strictly between `a` and `b` — i.e. the shared diagonal is deleted and nothing
    else changes. Returns `None` when the two do not share an edge, or when fusing them would make
    a concave piece or one longer than the engine's `FPoly` bound.
    """
    n1, n2 = len(p1), len(p2)
    for i in range(n1):
        a, b = p1[i], p1[(i + 1) % n1]
        for j in range(n2):
            if not (p2[j] == b and p2[(j + 1) % n2] == a):
                continue
            fused = [p1[(i + 1 + k) % n1] for k in range(n1)]          # p1 rotated to start at b
            fused += [p2[(j + 2 + k) % n2] for k in range(n2 - 2)]     # p2's vertices between a, b
            if len(fused) > MAX_FPOLY_VERTS:
                return None
            if not is_convex([ring[k] for k in fused]):
                return None
            return fused
    return None


def convex_pieces(points) -> list[list]:
    """Decompose a CCW profile ring into convex pieces of at most `MAX_FPOLY_VERTS` vertices each.

    Both caps of a swept brush are built from the result — one `Polygon` per piece — because the
    engine's `FPoly` must be convex and holds at most 16 vertices, while the BRUSH as a whole may
    be non-convex (the `staircase` precedent: a non-convex brush of convex faces, which `level
    doctor` accepts and UnrealEd builds correctly).

    **A convex ring of ≤16 vertices comes back as exactly ONE piece**, so a plain box or hexagonal
    prism still emits exactly two cap faces and nothing changes for the simple case. Anything else
    is ear-clipped into triangles and then merged back across shared diagonals for as long as each
    fused piece stays convex and within the vertex bound (Hertel–Mehlhorn) — merging matters,
    because every extra face is BSP nodes and rendering cost, and plain triangles would emit `n−2`
    of them per cap.

    **The decomposition adds only DIAGONALS of the original ring** — never a new vertex on the
    boundary — so every cap boundary edge still matches its side quad's edge exactly and the solid
    stays watertight with no T-junctions.
    """
    ring = list(points)
    if is_convex(ring) and len(ring) <= MAX_FPOLY_VERTS:
        return [ring]
    pieces = _ear_clip(ring)
    fused = True
    while fused:
        fused = False
        for i in range(len(pieces)):
            for j in range(i + 1, len(pieces)):
                merged = _merge_across_shared_edge(ring, pieces[i], pieces[j])
                if merged is not None:
                    pieces[i] = merged
                    del pieces[j]
                    fused = True
                    break
            if fused:
                break
    return [[ring[k] for k in piece] for piece in pieces]
