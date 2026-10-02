"""Model-side brush clipping — Sutherland-Hodgman halfspace clip.

Clip a brush (closed convex polyhedron) by a plane, keeping one half. Each face
polygon is clipped against the half-space; a new CAP face is built from the edge-
intersection points so the solid stays closed. The result is validated (planarity
/ coincidence / degeneracy) before use, then materialized via the EDIT PASTE modify
path (so the clipped brush stays ACTOR-SELECT-INSIDE-selectable; see
uned-brush-selectability). This replaces the editor-native `BRUSH CLIP` tool, which
needs GUI-set clip markers and isn't console-drivable (see dev/docs/spikes/2026-06-17-brush-clip.md).

Coordinates are the brush's own vertex space (local to the actor Location); the
caller converts a world-space plane to local before calling.
"""
from __future__ import annotations

import copy
import math

from .emit import clean
from .geometry import GeometryError, validate_brush
from .model import Brush, Polygon, Vec3

# Plane tolerance: a vertex within EPS of the plane is treated as ON it (kept).
EPS = 1e-4
# Two cut points closer than WELD are the same cap vertex (faces share cut points).
WELD = 1e-3


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])
def _len(a): return math.sqrt(_dot(a, a))


def _normalize(a: Vec3) -> Vec3:
    n = _len(a)
    if n < 1e-9:
        raise GeometryError("clip plane normal is zero-length")
    return (a[0] / n, a[1] / n, a[2] / n)


def _signed_dist(v: Vec3, point: Vec3, normal: Vec3) -> float:
    return _dot(_sub(v, point), normal)


def _clip_polygon(verts, point, normal):
    """Sutherland-Hodgman: keep the part of the polygon on the side where
    signed_dist <= 0 (the half-space OPPOSITE the normal). Returns
    (kept_verts, cut_points) — cut_points are intersections introduced on the plane.
    Winding/order of the original polygon is preserved in kept_verts.
    """
    out, cuts = [], []
    n = len(verts)
    for i in range(n):
        a, b = verts[i], verts[(i + 1) % n]
        da, db = _signed_dist(a, point, normal), _signed_dist(b, point, normal)
        a_in, b_in = da <= EPS, db <= EPS
        if b_in:
            if not a_in:                                  # entering: add crossing
                ip = _add(a, _mul(_sub(b, a), da / (da - db)))
                out.append(ip); cuts.append(ip)
            out.append(b)
        elif a_in:                                        # leaving: add crossing
            ip = _add(a, _mul(_sub(b, a), da / (da - db)))
            out.append(ip); cuts.append(ip)
    return out, cuts


def _dedup_ring(verts):
    """Drop consecutive (and wrap-around) near-duplicate vertices."""
    out = []
    for v in verts:
        if not out or _len(_sub(v, out[-1])) > WELD:
            out.append(v)
    if len(out) > 1 and _len(_sub(out[0], out[-1])) <= WELD:
        out.pop()
    return out


def _weld_points(points):
    """Collapse points within WELD to a single representative (cap vertices are
    shared by the two faces whose edges produced them)."""
    uniq = []
    for p in points:
        if not any(_len(_sub(p, q)) <= WELD for q in uniq):
            uniq.append(p)
    return uniq


def _order_cap(points, normal):
    """Order cap points CCW about +normal (so the face's winding-derived normal
    points OUT of the kept solid), with an explicit winding check + flip."""
    c = _mul((sum(p[0] for p in points), sum(p[1] for p in points),
              sum(p[2] for p in points)), 1.0 / len(points))
    # in-plane basis
    ref = _sub(points[0], c)
    if _len(ref) < 1e-6:
        ref = _sub(points[1], c)
    u = _normalize(_sub(ref, _mul(normal, _dot(ref, normal))))
    v = _cross(normal, u)
    ordered = sorted(points, key=lambda p: math.atan2(_dot(_sub(p, c), v),
                                                       _dot(_sub(p, c), u)))
    # winding check: Newell normal should align with +normal, else reverse
    nrm = (0.0, 0.0, 0.0)
    m = len(ordered)
    for i in range(m):
        a, b = ordered[i], ordered[(i + 1) % m]
        nrm = _add(nrm, _cross(a, b))
    if _dot(nrm, normal) < 0:
        ordered.reverse()
    return ordered, c, u, v


def _make_cap(points, normal, source: Polygon) -> Polygon:
    ordered, centroid, u, v = _order_cap(points, normal)
    cap = Polygon()
    cap.flags = source.flags
    cap.texture = source.texture                 # inherit the brush's texture
    cap.origin = centroid
    cap.normal = normal                          # advisory; editor recomputes from winding
    cap.texture_u = u                            # unit in-plane vectors — non-degenerate
    cap.texture_v = v                            # (zero-length texU/V would crash REBUILD)
    cap.pan = (0, 0)
    cap.vertices = ordered
    return cap


def clip_brush(brush: Brush, point: Vec3, normal: Vec3, keep_negative: bool = True) -> Brush:
    """Clip `brush` by the plane (point, normal), keeping one half.

    keep_negative=True keeps the half-space OPPOSITE the normal (signed_dist <= 0);
    False keeps the normal side. Returns a NEW Brush (clipped faces + cap). Raises
    GeometryError if the plane removes the whole brush, or the result is degenerate.
    The plane is in the brush's vertex coordinate space.
    """
    # Sutherland-Hodgman runs in float and finalizes to Decimal via `clean` below; callers pass a
    # mix — builders/axis_plane give float, but model brushes carry Decimal vertices and the `--plane`
    # CLI gives Decimal point/normal. Coerce all inputs to float up front, or the geometry math hits
    # `Decimal op float` TypeErrors (clip used to crash on every real model brush / --plane call).
    point = tuple(float(c) for c in point)
    normal = _normalize(tuple(float(c) for c in normal))
    if not keep_negative:
        normal = _mul(normal, -1.0)

    new_polys, all_cuts = [], []
    for poly in brush.polys:
        verts = [(float(x), float(y), float(z)) for x, y, z in poly.vertices]
        kept, cuts = _clip_polygon(verts, point, normal)
        all_cuts.extend(cuts)
        kept = _dedup_ring(kept)
        if len(kept) >= 3:                       # face survives (whole or truncated)
            np = copy.deepcopy(poly)
            np.vertices = kept
            new_polys.append(np)
        # len(kept) == 0 → face fully on the discarded side → dropped

    if not new_polys:
        raise GeometryError("clip removed the entire brush (plane discards every face)")

    cap_pts = _weld_points(all_cuts)
    if len(cap_pts) >= 3:                         # the plane actually cut through → cap it
        new_polys.append(_make_cap(cap_pts, normal, brush.polys[0]))
    # < 3 cut points → plane was tangent/outside; brush kept whole, no cap needed.

    # Sutherland-Hodgman runs in float; finalize vertices to the Decimal grid model.
    # clean PRESERVES genuine fractions, so a clipped SLANTED face keeps its true
    # (fractional) cut points instead of being grid-snapped off-plane (the old cone
    # non-planar failure — see dev/unrealed/quirks).
    for p in new_polys:
        p.vertices = [(clean(x), clean(y), clean(z)) for x, y, z in p.vertices]
    result = Brush(model_name=brush.model_name, polys=new_polys)
    validate_brush(result)                        # post-clean planarity/coincidence/degeneracy
    return result


def classify_clip(brush: Brush, point: Vec3, normal: Vec3, keep_negative: bool = True) -> str:
    """Where `brush` sits relative to the clip plane, using the SAME orientation `clip_brush` uses:
    'clips' — vertices on both sides, so the plane really cuts the interior; 'whole' — every vertex
    is on the KEPT side, so a clip is a silent no-op (report it instead of leaving it unchanged with
    no message); 'empty' — every vertex is on the discarded side, so a clip would remove the brush
    (clip_brush raises for this). Pure float geometry, no mutation."""
    point = tuple(float(c) for c in point)
    normal = _normalize(tuple(float(c) for c in normal))
    if not keep_negative:
        normal = _mul(normal, -1.0)
    kept = discarded = False
    for poly in brush.polys:
        for v in poly.vertices:
            d = _signed_dist(tuple(float(c) for c in v), point, normal)
            if d > EPS:
                discarded = True
            elif d < -EPS:
                kept = True
    if kept and discarded:
        return "clips"
    return "empty" if discarded else "whole"


def axis_plane(axis: str, coord: float):
    """Convenience: an axis-aligned plane. Returns (point, normal) with the normal
    along +axis, so keep_negative=True keeps the side BELOW `coord` on that axis."""
    i = {"x": 0, "y": 1, "z": 2}[axis.lower()]
    point = [0.0, 0.0, 0.0]; point[i] = float(coord)
    normal = [0.0, 0.0, 0.0]; normal[i] = 1.0
    return tuple(point), tuple(normal)
