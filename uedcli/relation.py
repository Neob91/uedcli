"""Cross-brush geometric relationships — `brush measure relation`. Pure Python, model-side, no
editor, no native CSG. See docs/superpowers/specs/2026-08-29-brush-measure-design.md."""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from . import polyalign
from .preview import _poly_centroid_2d

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class PlaneRelation:
    plane: str  # "coplanar" | "parallel"
    normal_a: Vec3
    normal_b: Vec3
    distance: float  # signed, along normal_a; 0 only if actually measured as ~0


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def plane_relationship(actor_a, poly_a, actor_b, poly_b) -> PlaneRelation | None:
    """Compare two (possibly different-brush, possibly-rotated) polys' planes. Returns None if
    their normals aren't parallel or anti-parallel within `polyalign._PARALLEL_EPS`."""
    try:
        normal_a = polyalign._world_normal(actor_a, poly_a, ref=f"{actor_a.name}")
        normal_b = polyalign._world_normal(actor_b, poly_b, ref=f"{actor_b.name}")
    except polyalign.PolyAlignError:
        return None  # a degenerate (zero-area) poly can't participate in a plane comparison

    alignment = _dot(normal_a, normal_b)  # +1 same direction, -1 opposite, 0 perpendicular
    if abs(abs(alignment) - 1.0) > polyalign._PARALLEL_EPS:
        return None  # not parallel (in either direction) -> "neither"

    point_a = polyalign._world_verts(actor_a, poly_a)[0]
    point_b = polyalign._world_verts(actor_b, poly_b)[0]
    distance = _dot(_sub(point_b, point_a), normal_a)

    plane = "coplanar" if abs(distance) <= polyalign._PLANE_EPS else "parallel"
    return PlaneRelation(plane=plane, normal_a=normal_a, normal_b=normal_b, distance=distance)


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v: Vec3) -> Vec3:
    length = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5
    return (v[0] / length, v[1] / length, v[2] / length)


def _plane_basis(normal: Vec3) -> tuple[Vec3, Vec3]:
    """An arbitrary, deterministic orthonormal (U, V) basis for the plane perpendicular to
    `normal`. Not meaningful in isolation -- only used to compare two projections of the SAME
    normal, so any consistent choice is correct."""
    helper = (0.0, 0.0, 1.0) if abs(normal[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = _norm(_cross(helper, normal))
    v = _cross(normal, u)  # already unit length: normal and u are both unit and orthogonal
    return u, v


def project_to_plane(world_verts: list[Vec3], normal: Vec3, *, origin: Vec3 | None = None) -> list[Vec2]:
    """Project `world_verts` into the (U, V) frame for `normal`. Defaults `origin` to
    `world_verts[0]` -- fine for inspecting one poly's own shape in isolation, but a caller
    comparing TWO different polys' footprints (`classify_footprint_2d`, `compute_deltas`) MUST
    pass the SAME `origin` to both calls: each call's default is that poly's own first vertex, an
    arbitrary and unrelated point between the two polys, so two independently-defaulted
    projections land in unrelated coordinate frames and any overlap/containment/delta computed
    across them would be measuring a meaningless synthetic offset instead of true relative
    position (caught via `brush measure relation` on a real Leg/Floor pair: an 8x8 corner overlap
    was misreported as one poly fully `contains`-ing the other)."""
    if origin is None:
        origin = world_verts[0]
    u_axis, v_axis = _plane_basis(_norm(normal))
    out = []
    for p in world_verts:
        rel = _sub(p, origin)
        out.append((_dot(rel, u_axis), _dot(rel, v_axis)))
    return out


_AREA_EPS = 1e-6   # relative area-equality tolerance for contains/coincident
_TOUCH_EPS = 1e-3  # vertex/edge coincidence tolerance, in the same units as the (U, V) coordinates


def _shoelace_area(poly: list[Vec2]) -> float:
    area = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    return area / 2.0


def _edge_intersect(p1: Vec2, p2: Vec2, ex: float, ey: float, edx: float, edy: float) -> Vec2:
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    denom = dx * edy - dy * edx
    if abs(denom) < 1e-12:
        return p2
    t = ((ex - x1) * edy - (ey - y1) * edx) / denom
    return (x1 + t * dx, y1 + t * dy)


def _clip_2d(subject: list[Vec2], clip_poly: list[Vec2]) -> list[Vec2]:
    """Sutherland-Hodgman: clip `subject` against the convex, CCW-wound `clip_poly`. Returns the
    intersection polygon's vertices (possibly empty)."""
    output = list(subject)
    n = len(clip_poly)
    for i in range(n):
        if not output:
            break
        cx0, cy0 = clip_poly[i]
        cx1, cy1 = clip_poly[(i + 1) % n]
        edx, edy = cx1 - cx0, cy1 - cy0

        def inside(p: Vec2) -> bool:
            return edx * (p[1] - cy0) - edy * (p[0] - cx0) >= -1e-9

        input_list = output
        output = []
        m = len(input_list)
        for j in range(m):
            cur = input_list[j]
            prev = input_list[j - 1]
            cur_in, prev_in = inside(cur), inside(prev)
            if cur_in:
                if not prev_in:
                    output.append(_edge_intersect(prev, cur, cx0, cy0, edx, edy))
                output.append(cur)
            elif prev_in:
                output.append(_edge_intersect(prev, cur, cx0, cy0, edx, edy))
    return output


def _close(x: float, y: float) -> bool:
    return abs(x - y) <= _AREA_EPS * max(1.0, abs(x), abs(y))


def _edges(poly: list[Vec2]):
    n = len(poly)
    return [(poly[i], poly[(i + 1) % n]) for i in range(n)]


def _point_on_segment(p: Vec2, s0: Vec2, s1: Vec2) -> bool:
    dx, dy = s1[0] - s0[0], s1[1] - s0[1]
    seg_len = (dx * dx + dy * dy) ** 0.5
    if seg_len < 1e-12:
        return abs(p[0] - s0[0]) <= _TOUCH_EPS and abs(p[1] - s0[1]) <= _TOUCH_EPS
    if abs(dx * (p[1] - s0[1]) - dy * (p[0] - s0[0])) / seg_len > _TOUCH_EPS:
        return False  # not on the segment's line
    t = ((p[0] - s0[0]) * dx + (p[1] - s0[1]) * dy) / (seg_len * seg_len)
    slack = _TOUCH_EPS / seg_len
    return -slack <= t <= 1 + slack


def _shares_vertex(a: list[Vec2], b: list[Vec2]) -> bool:
    # A vertex of one poly landing on an EDGE of the other (a T-junction -- e.g. a beam's corner
    # resting against a wall face with no vertex at that exact point) is still a single-point
    # touch, not "none". Checking point-on-segment (not just vertex-to-vertex coincidence)
    # subsumes the plain-coincidence case too: a shared vertex is trivially "on" its own edges.
    return (
        any(_point_on_segment(pa, b0, b1) for pa in a for b0, b1 in _edges(b))
        or any(_point_on_segment(pb, a0, a1) for pb in b for a0, a1 in _edges(a))
    )


def _segments_overlap(a0: Vec2, a1: Vec2, b0: Vec2, b1: Vec2) -> bool:
    def cross(o: Vec2, p: Vec2, q: Vec2) -> float:
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    if abs(cross(a0, a1, b0)) > _TOUCH_EPS or abs(cross(a0, a1, b1)) > _TOUCH_EPS:
        return False  # not collinear with edge A
    dx, dy = a1[0] - a0[0], a1[1] - a0[1]

    def t(p: Vec2) -> float:
        return (p[0] - a0[0]) * dx + (p[1] - a0[1]) * dy

    lo_a, hi_a = sorted((t(a0), t(a1)))
    lo_b, hi_b = sorted((t(b0), t(b1)))
    # Overlap must have positive length -- two collinear segments touching only at a shared
    # endpoint (e.g. two squares meeting at one corner) is a "vertex" touch, not an "edge" one.
    return min(hi_a, hi_b) - max(lo_a, lo_b) > _TOUCH_EPS


def _shares_edge(a: list[Vec2], b: list[Vec2]) -> bool:
    return any(_segments_overlap(a0, a1, b0, b1) for a0, a1 in _edges(a) for b0, b1 in _edges(b))


def _ensure_ccw(poly: list[Vec2]) -> list[Vec2]:
    return list(reversed(poly)) if _shoelace_area(poly) < 0 else poly


def classify_footprint_2d(poly_a: list[Vec2], poly_b: list[Vec2]) -> str:
    """`poly_a`/`poly_b` are re-wound CCW here rather than trusted from the caller: a poly's own
    vertex winding faces ITS OWN outward normal, so a coplanar pair with anti-parallel normals
    (e.g. a floor's top face and a leg's bottom face resting on it -- the central motivating case
    for this whole verb) projects into the SAME (normal_a-based) 2-D frame with opposite winding.
    `_clip_2d`'s half-plane test assumes its clip polygon is CCW; an un-normalized CW poly_b
    clips against the wrong half-plane and silently produces an empty intersection, misreporting
    a genuine overlap as `footprint_2d: none` (caught by hand-verifying a Leg/Floor smoke case)."""
    poly_a = _ensure_ccw(poly_a)
    poly_b = _ensure_ccw(poly_b)
    area_a = abs(_shoelace_area(poly_a))
    area_b = abs(_shoelace_area(poly_b))
    inter = _clip_2d(poly_a, poly_b)
    area_i = abs(_shoelace_area(inter)) if len(inter) >= 3 else 0.0

    if area_i > _AREA_EPS:
        if _close(area_i, area_a) and _close(area_i, area_b):
            return "coincident"
        if _close(area_i, area_a):
            return "contains_a_in_b"
        if _close(area_i, area_b):
            return "contains_b_in_a"
        return "partial"

    if _shares_edge(poly_a, poly_b):
        return "edge"
    if _shares_vertex(poly_a, poly_b):
        return "vertex"
    return "none"


@dataclass(frozen=True)
class Deltas:
    centroid_u: float
    centroid_v: float
    edge_u_label: str
    edge_u: float
    edge_v_label: str
    edge_v: float


def _closer_edge(a_lo: float, a_hi: float, b_lo: float, b_hi: float, axis: str) -> tuple[str, float]:
    d_min = b_lo - a_lo
    d_max = b_hi - a_hi
    if abs(d_min) <= abs(d_max):
        return f"{axis}-min", d_min
    return f"{axis}-max", d_max


def compute_deltas(poly_a: list[Vec2], poly_b: list[Vec2]) -> Deltas:
    ca = _poly_centroid_2d(poly_a)
    cb = _poly_centroid_2d(poly_b)
    us_a = [p[0] for p in poly_a]
    vs_a = [p[1] for p in poly_a]
    us_b = [p[0] for p in poly_b]
    vs_b = [p[1] for p in poly_b]
    u_label, u_delta = _closer_edge(min(us_a), max(us_a), min(us_b), max(us_b), "U")
    v_label, v_delta = _closer_edge(min(vs_a), max(vs_a), min(vs_b), max(vs_b), "V")
    return Deltas(
        centroid_u=cb[0] - ca[0], centroid_v=cb[1] - ca[1],
        edge_u_label=u_label, edge_u=u_delta,
        edge_v_label=v_label, edge_v=v_delta,
    )


class RelationError(ValueError):
    pass


@dataclass(frozen=True)
class PairFace:
    brush_a: str
    poly_a: int
    brush_b: str
    poly_b: int
    plane: PlaneRelation
    footprint_2d: str
    deltas: Deltas


@dataclass(frozen=True)
class PairGroup:
    brush_a: str
    brush_b: str
    shown: list  # list[PairFace], ranked best-first, at most `top` entries
    candidate_count: int


@dataclass(frozen=True)
class RelationReport:
    groups: list  # list[PairGroup]
    disjoint: list  # list[str]
    brush_count: int
    pair_count: int


_FOOTPRINT_2D_RANK = {
    "coincident": 0,
    "contains_a_in_b": 1,
    "contains_b_in_a": 1,
    "partial": 2,
    "edge": 3,
    "vertex": 4,
    "none": 5,
}


def _centroid_delta_magnitude(deltas: Deltas) -> float:
    return (deltas.centroid_u ** 2 + deltas.centroid_v ** 2) ** 0.5


def _candidate_sort_key(pair: PairFace) -> tuple:
    return (
        _FOOTPRINT_2D_RANK[pair.footprint_2d],
        abs(pair.plane.distance),
        _centroid_delta_magnitude(pair.deltas),
        pair.poly_a,
        pair.poly_b,
    )


def compute(level, names: list[str], *, top: int | None = 1) -> RelationReport:
    if top is not None and top < 1:
        raise RelationError(f"--top must be a positive integer or 'all', got {top!r}")

    actors = []
    for name in names:
        actor = level.actors.get(name)
        if actor is None:
            raise RelationError(f"no such actor: {name!r}")
        if actor.brush is None:
            raise RelationError(f"{name!r} is not a brush actor (no PolyList)")
        actors.append(actor)

    groups: list[PairGroup] = []
    involved: set[str] = set()
    for actor_a, actor_b in itertools.combinations(actors, 2):
        candidates: list[PairFace] = []
        for idx_a, poly_a in enumerate(actor_a.brush.polys):
            for idx_b, poly_b in enumerate(actor_b.brush.polys):
                rel = plane_relationship(actor_a, poly_a, actor_b, poly_b)
                if rel is None:
                    continue
                world_a = polyalign._world_verts(actor_a, poly_a)
                world_b = polyalign._world_verts(actor_b, poly_b)
                # Shared origin (poly_a's own first vertex) -- see project_to_plane's docstring:
                # two independently-defaulted origins would compare unrelated coordinate frames.
                uv_a = project_to_plane(world_a, rel.normal_a)
                uv_b = project_to_plane(world_b, rel.normal_a, origin=world_a[0])
                footprint_2d = classify_footprint_2d(uv_a, uv_b)
                deltas = compute_deltas(uv_a, uv_b)
                candidates.append(PairFace(
                    brush_a=actor_a.name, poly_a=idx_a,
                    brush_b=actor_b.name, poly_b=idx_b,
                    plane=rel, footprint_2d=footprint_2d, deltas=deltas,
                ))

        if not candidates:
            continue
        candidates.sort(key=_candidate_sort_key)
        shown = candidates if top is None else candidates[:top]
        groups.append(PairGroup(
            brush_a=actor_a.name, brush_b=actor_b.name,
            shown=shown, candidate_count=len(candidates),
        ))
        involved.add(actor_a.name)
        involved.add(actor_b.name)

    disjoint = [a.name for a in actors if a.name not in involved]
    n = len(actors)
    return RelationReport(
        groups=groups, disjoint=disjoint, brush_count=n, pair_count=n * (n - 1) // 2,
    )


def _fmt(v: float) -> str:
    return f"{v + 0.0:.3f}uu"  # + 0.0 folds -0.0 to 0.0 -- a genuine 0 must never print as "-0.000"


def _fmt_vec(v: Vec3) -> str:
    return f"({v[0] + 0.0:.3f}, {v[1] + 0.0:.3f}, {v[2] + 0.0:.3f})"


_FOOTPRINT_2D_LABELS = {
    "none": "none",
    "vertex": "vertex",
    "edge": "edge",
    "partial": "partial",
    "coincident": "coincident",
}


def _footprint_2d_text(pair: PairFace) -> str:
    sel_a = f"{pair.brush_a}:{pair.poly_a}"
    sel_b = f"{pair.brush_b}:{pair.poly_b}"
    if pair.footprint_2d == "contains_a_in_b":
        return f"contains ({sel_a} in {sel_b})"
    if pair.footprint_2d == "contains_b_in_a":
        return f"contains ({sel_b} in {sel_a})"
    return _FOOTPRINT_2D_LABELS[pair.footprint_2d]


def _format_group(group: PairGroup) -> list[str]:
    if all(p.footprint_2d == "none" for p in group.shown):
        best = group.shown[0]
        return [
            f"{group.brush_a} <-> {group.brush_b}: no overlapping face pairs "
            f"({group.candidate_count} candidates, nearest {_fmt(abs(best.plane.distance))} apart)"
        ]

    count_note = (
        "" if group.candidate_count == len(group.shown)
        else f"  ({len(group.shown)} of {group.candidate_count} candidates shown)"
    )
    lines = [f"{group.brush_a} <-> {group.brush_b}{count_note}"]
    for pair in group.shown:
        sel_a = f"{pair.brush_a}:{pair.poly_a}"
        sel_b = f"{pair.brush_b}:{pair.poly_b}"
        lines.append(f"  {sel_a} <-> {sel_b}")
        lines.append(f"    plane: {pair.plane.plane}")
        lines.append("    normals:")
        lines.append(f"      {sel_a}: {_fmt_vec(pair.plane.normal_a)}")
        lines.append(f"      {sel_b}: {_fmt_vec(pair.plane.normal_b)}")
        lines.append(f"    distance: {_fmt(pair.plane.distance)}")
        lines.append(f"    footprint_2d: {_footprint_2d_text(pair)}")
        lines.append("    deltas:")
        d = pair.deltas
        lines.append(f"      centroid: U={_fmt(d.centroid_u)} V={_fmt(d.centroid_v)}")
        lines.append(f"      edge: {d.edge_u_label}={_fmt(d.edge_u)} {d.edge_v_label}={_fmt(d.edge_v)}")
    return lines


def format_report(report: RelationReport) -> str:
    lines: list[str] = []
    for i, group in enumerate(report.groups):
        if i > 0:
            lines.append("")
        lines.extend(_format_group(group))

    if report.disjoint:
        if lines:
            lines.append("")
        names = ", ".join(report.disjoint)
        lines.append(f"disjoint: {{{names}}} shares no plane and has no parallel-facing "
                      f"relationship with anything else named")

    lines.append("")
    lines.append(f"checked: {report.brush_count} brushes, {report.pair_count} pairs, every face")
    return "\n".join(lines)
