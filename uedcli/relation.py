"""Cross-brush geometric relationships — `brush relation measure|find|set`. Pure Python, model-side,
no editor, no native CSG. See dev/docs/superpowers/specs/2026-09-05-brush-relation-family-design.md."""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from . import polyalign
from . import query
from . import surface
from .preview import _poly_centroid_2d

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]

_PARALLEL_EPS = 1e-3   # 1 - |n.n'| below this => same plane orientation
_PLANE_EPS = 0.5       # |distance| below this => coplanar rather than merely parallel
_GAP_EPS = 1e-6        # float-dust tolerance on --max-gap/--min-gap comparisons (not a semantic
                        # threshold like _PLANE_EPS -- absorbs residual noise so a genuinely flush
                        # pair, e.g. -0.000uu from a rotated placement, still passes --max-gap 0)


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
    their normals aren't parallel or anti-parallel within `_PARALLEL_EPS`."""
    try:
        normal_a = polyalign._world_normal(actor_a, poly_a, ref=f"{actor_a.name}")
        normal_b = polyalign._world_normal(actor_b, poly_b, ref=f"{actor_b.name}")
    except polyalign.PolyAlignError:
        return None  # a degenerate (zero-area) poly can't participate in a plane comparison

    alignment = _dot(normal_a, normal_b)  # +1 same direction, -1 opposite, 0 perpendicular
    if abs(abs(alignment) - 1.0) > _PARALLEL_EPS:
        return None  # not parallel (in either direction) -> "neither"

    point_a = polyalign._world_verts(actor_a, poly_a)[0]
    point_b = polyalign._world_verts(actor_b, poly_b)[0]
    distance = _dot(_sub(point_b, point_a), normal_a)

    plane = "coplanar" if abs(distance) <= _PLANE_EPS else "parallel"
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
    footprint_gap: float   # 2-D bbox-to-bbox gap between the projected footprints; 0 whenever
                            # footprint_2d != "none" (they already overlap/touch). For "none", the
                            # true in-plane separation -- NOT the same axis as `plane.distance`
                            # (perpendicular to the shared plane), so a pair can read
                            # `plane.distance == 0` yet be footprint_gap == 900 (parallel faces
                            # that happen to align on the perpendicular axis but sit far apart
                            # in-plane). See find_candidates' near_miss_count.


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


def _interval_gap(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> float:
    """0 if [a_lo,a_hi] and [b_lo,b_hi] overlap, else the positive separation between them."""
    return max(0.0, b_lo - a_hi, a_lo - b_hi)


def _footprint_bbox_gap(poly_a: list[Vec2], poly_b: list[Vec2]) -> float:
    """The exact closest-point distance between the two footprints' axis-aligned bounding boxes
    in the shared U/V plane -- 0 when they overlap on both axes (footprint_2d != "none"), else the
    real in-plane separation. Deliberately NOT `plane.distance` (that's perpendicular to this
    plane and can read near-zero for a pair that is actually far apart in-plane, e.g. two parallel
    walls on perpendicular-aligned but far-apart brushes)."""
    us_a = [p[0] for p in poly_a]
    vs_a = [p[1] for p in poly_a]
    us_b = [p[0] for p in poly_b]
    vs_b = [p[1] for p in poly_b]
    u_gap = _interval_gap(min(us_a), max(us_a), min(us_b), max(us_b))
    v_gap = _interval_gap(min(vs_a), max(vs_a), min(vs_b), max(vs_b))
    return math.hypot(u_gap, v_gap)


def _pairs_between(actor_a, idxs_a: set, actor_b, idxs_b: set) -> list:
    """Every (idx_a, idx_b) poly pair between `actor_a`'s `idxs_a` and `actor_b`'s `idxs_b` with a
    defined plane relationship, as `PairFace` objects ranked best-first (`_candidate_sort_key`).
    Skips the identical `(actor, idx)` pairing when `actor_a is actor_b` -- a poly compared to
    itself is never a meaningful relation, independent of any actor-level self-comparison guard a
    caller applies."""
    same_brush = actor_a is actor_b
    candidates: list[PairFace] = []
    for idx_a in idxs_a:
        poly_a = actor_a.brush.polys[idx_a]
        for idx_b in idxs_b:
            if same_brush and idx_a == idx_b:
                continue
            poly_b = actor_b.brush.polys[idx_b]
            rel = plane_relationship(actor_a, poly_a, actor_b, poly_b)
            if rel is None:
                continue
            world_a = polyalign._world_verts(actor_a, poly_a)
            world_b = polyalign._world_verts(actor_b, poly_b)
            uv_a = project_to_plane(world_a, rel.normal_a)
            uv_b = project_to_plane(world_b, rel.normal_a, origin=world_a[0])
            footprint_2d = classify_footprint_2d(uv_a, uv_b)
            deltas = compute_deltas(uv_a, uv_b)
            footprint_gap = _footprint_bbox_gap(uv_a, uv_b) if footprint_2d == "none" else 0.0
            candidates.append(PairFace(
                brush_a=actor_a.name, poly_a=idx_a, brush_b=actor_b.name, poly_b=idx_b,
                plane=rel, footprint_2d=footprint_2d, deltas=deltas, footprint_gap=footprint_gap,
            ))
    candidates.sort(key=_candidate_sort_key)
    return candidates


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
        candidates = _pairs_between(
            actor_a, set(range(len(actor_a.brush.polys))),
            actor_b, set(range(len(actor_b.brush.polys))),
        )
        if not candidates:
            continue
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


# --------------------------------------------------------------------- brush relation measure

def _resolve_measure_selector(level, token: str):
    """Bare `Name` (all its polys) or `Name:SELECTOR` -> (canonical_name, actor, index set).
    Raises `RelationError` naming the offender for every failure path."""
    if ":" in token:
        brush_name, selector = surface.parse_poly_selector(token)
    else:
        brush_name, selector = token, "all"
    try:
        canonical = query.resolve_actor_name(level, brush_name)
    except KeyError as e:
        raise RelationError(e.args[0]) from e
    actor = level.actors[canonical]
    if actor.brush is None:
        raise RelationError(f"{canonical!r} is not a brush actor (no PolyList)")
    try:
        indices = surface.resolve_polys(selector, actor, brush_name=canonical)
    except ValueError as e:
        raise RelationError(str(e)) from e
    return canonical, actor, indices


def compute_pairs(level, ref_token: str, target_tokens: list[str], *, top: int | None = 1,
                   allow_self: bool = False) -> RelationReport:
    """`brush relation measure REF TARGET...` -- one ref selector against one or more target
    selectors (each a bare brush Name, all its polys, or `Name:SELECTOR`). Repeated target tokens
    naming the SAME brush have their poly-index sets UNIONED into one group rather than producing
    duplicates -- e.g. piping `Near:5` and `Near:3` (two rows of one `find --top all` candidate)
    compares both indices against ref together. Returns a `RelationReport` with one `PairGroup`
    per distinct target brush that has a qualifying pair (`format_report` already iterates
    multiple groups), reusing the same "disjoint" model as `compute`'s N-actor sweep: a name is
    disjoint only if it never appears in ANY group, ref included. Raises `RelationError` naming
    the offender for every failure path, including a target naming ref's own brush unless
    `allow_self`."""
    if top is not None and top < 1:
        raise RelationError(f"--top must be a positive integer or 'all', got {top!r}")
    ref_name, ref_actor, ref_idxs = _resolve_measure_selector(level, ref_token)

    merged: dict[str, tuple] = {}   # canonical target name -> (actor, unioned idx set)
    order: list[str] = []           # first-seen order
    for tok in target_tokens:
        target_name, target_actor, target_idxs = _resolve_measure_selector(level, tok)
        if target_name == ref_name and not allow_self:
            raise RelationError(
                f"brush relation measure: target {target_name!r} is the reference's own brush "
                f"-- pass --allow-self to compare two faces of one brush")
        if target_name in merged:
            merged[target_name] = (target_actor, merged[target_name][1] | target_idxs)
        else:
            merged[target_name] = (target_actor, set(target_idxs))
            order.append(target_name)

    groups = []
    involved: set[str] = set()
    for target_name in order:
        target_actor, idxs = merged[target_name]
        candidates = _pairs_between(ref_actor, ref_idxs, target_actor, idxs)
        if candidates:
            shown = candidates if top is None else candidates[:top]
            groups.append(PairGroup(brush_a=ref_name, brush_b=target_name,
                                     shown=shown, candidate_count=len(candidates)))
            involved.add(ref_name)
            involved.add(target_name)

    disjoint = sorted(name for name in {ref_name, *order} if name not in involved)
    brush_count = len({ref_name, *order})
    return RelationReport(groups=groups, disjoint=disjoint, brush_count=brush_count,
                           pair_count=len(order))


# --------------------------------------------------------------------- brush relation find

_FOOTPRINT_FILTER_ALIASES = {"contains": {"contains_a_in_b", "contains_b_in_a"}}


@dataclass(frozen=True)
class FindMatch:
    candidate: str
    poly: int
    pair: PairFace   # REF is always pair.brush_a/poly_a; the candidate is pair.brush_b/poly_b


def _passes_gap_and_plane(pair: PairFace, *, max_gap, min_gap, plane) -> bool:
    """The `--max-gap`/`--min-gap`/`--plane` predicates only -- footprint is a separate concern
    (see `_passes_predicates`), split out so the near-miss count in `find_candidates` can ask
    "would this pair qualify on gap/plane alone?" independent of the implicit footprint=none
    exclusion."""
    if plane is not None and pair.plane.plane != plane:
        return False
    gap = abs(pair.plane.distance)
    if max_gap is not None and gap > max_gap + _GAP_EPS:
        return False
    if min_gap is not None and gap < min_gap - _GAP_EPS:
        return False
    return True


def _passes_predicates(pair: PairFace, *, max_gap, min_gap, footprint, plane) -> bool:
    if not _passes_gap_and_plane(pair, max_gap=max_gap, min_gap=min_gap, plane=plane):
        return False
    if footprint is not None:
        allowed: set = set()
        for f in footprint:
            allowed |= _FOOTPRINT_FILTER_ALIASES.get(f, {f})
        return pair.footprint_2d in allowed
    return pair.footprint_2d != "none"   # a same-plane pair with NO footprint overlap is never a
                                          # meaningful match unless the caller explicitly asked for
                                          # footprint=none (see find_candidates' near_miss_count for
                                          # surfacing that this rule fired)


@dataclass(frozen=True)
class FindResult:
    matches: list          # list[FindMatch], best pair first per candidate
    near_miss_count: int   # pairs that qualify on gap/plane alone but were excluded ONLY by the
                            # implicit footprint=none rule (0 whenever --footprint was given
                            # explicitly, since then there's no implicit rule to surface)


def find_candidates(level, ref_token: str, candidate_names: list, *,
                     max_gap: float | None = None, min_gap: float | None = None,
                     footprint: set | None = None, plane: str | None = None,
                     top: int | None = 1) -> FindResult:
    """`brush relation find` -- rank every brush in `candidate_names` (already resolved to
    canonical brush-actor names by the caller) against `ref_token` (bare `Name` or `Name:idx`),
    keeping only poly pairs that satisfy every given predicate. `top` caps how many pairs per
    candidate are kept. Raises `RelationError` naming the offender for a bad `ref_token`, a bad
    `top`, or an inverted gap range."""
    if top is not None and top < 1:
        raise RelationError(f"--top must be a positive integer or 'all', got {top!r}")
    if min_gap is not None and max_gap is not None and min_gap > max_gap:
        raise RelationError(f"--min-gap ({min_gap}) must not exceed --max-gap ({max_gap})")
    ref_name, ref_actor, ref_idxs = _resolve_measure_selector(level, ref_token)
    results = []
    near_miss_faces: set[tuple[str, int]] = set()   # (candidate, poly_b) -- a FACE can be the
                                                      # near side of several ref-face pairings; the
                                                      # reported count is distinct faces, not pairs
    for cand_name in candidate_names:
        cand_actor = level.actors[cand_name]
        cand_idxs = set(range(len(cand_actor.brush.polys)))
        pairs = _pairs_between(ref_actor, ref_idxs, cand_actor, cand_idxs)
        kept = [p for p in pairs
                if _passes_predicates(p, max_gap=max_gap, min_gap=min_gap,
                                       footprint=footprint, plane=plane)]
        if footprint is None and max_gap is not None:
            # Near-miss detection needs a distance to call "close" -- with no --max-gap there is
            # no such bound to judge the in-plane footprint gap against, so it stays off rather
            # than inventing one.
            near_miss_faces.update(
                (cand_name, p.poly_b) for p in pairs
                if p.footprint_2d == "none"
                # satisfied all OTHER params (plane, perpendicular gap)...
                and _passes_gap_and_plane(p, max_gap=max_gap, min_gap=min_gap, plane=plane)
                # ...AND almost satisfied the one it's failing (footprint): the footprints
                # themselves are actually close in-plane, not just aligned on the unrelated
                # perpendicular axis.
                and p.footprint_gap <= max_gap + _GAP_EPS)
        shown = kept if top is None else kept[:top]
        results.extend(FindMatch(candidate=cand_name, poly=p.poly_b, pair=p) for p in shown)
    return FindResult(matches=results, near_miss_count=len(near_miss_faces))


# --------------------------------------------------------------------- brush relation set

def _resolve_exact_face(level, token: str, label: str):
    """`BRUSH:idx` only -- a bare name or a comma/`all` selector is rejected, since a translation
    target or reference can't be ambiguous. Raises `RelationError` naming the offender."""
    if ":" not in token:
        raise RelationError(f"{label} must be BRUSH:idx (a bare brush name is not allowed): {token!r}")
    brush_name, selector = surface.parse_poly_selector(token)
    try:
        canonical = query.resolve_actor_name(level, brush_name)
    except KeyError as e:
        raise RelationError(e.args[0]) from e
    actor = level.actors[canonical]
    if actor.brush is None:
        raise RelationError(f"{canonical!r} is not a brush actor (no PolyList)")
    try:
        indices = surface.resolve_polys(selector, actor, brush_name=canonical)
    except ValueError as e:
        raise RelationError(str(e)) from e
    if len(indices) != 1:
        raise RelationError(f"{label} must select exactly one poly, got {len(indices)}: {token!r}")
    return canonical, actor, next(iter(indices))


def _edge_extent(poly_ref, poly_target, *, axis: int, mode: str) -> float:
    """The offset between TARGET's `mode` (`'min'`/`'max'`) extent on `axis` (0=U, 1=V) and REF's
    corresponding extent, in the shared UV frame. `compute_deltas` only reports whichever of
    min/max is currently CLOSER; `brush relation set` needs either one, explicitly picked."""
    ref_vals = [p[axis] for p in poly_ref]
    target_vals = [p[axis] for p in poly_target]
    pick = min if mode == "min" else max
    return pick(target_vals) - pick(ref_vals)


def compute_set_translation(level, target_token: str, ref_token: str, *,
                             gap: float | None = None,
                             centroid_u: float | None = None, centroid_v: float | None = None,
                             edge_u=None, edge_v=None):
    """`brush relation set TARGET --relative-to REF` -- resolves both exact faces, checks they
    share a plane relationship, and returns `(target_name, ref_name, move)` where `move` is the
    world-space `(dx, dy, dz)` delta to add to TARGET's Location so the requested degree(s) of
    freedom land exactly on their target value(s); an omitted degree of freedom's delta is 0.
    `edge_u`/`edge_v`, when given, are `(mode, value)` with `mode` `'min'`/`'max'`. Raises
    `RelationError` naming the offender for every failure path, including no flag given at all."""
    if (gap is None and centroid_u is None and centroid_v is None
            and edge_u is None and edge_v is None):
        raise RelationError(
            "brush relation set: at least one of --gap/--centroid-u/--centroid-v/--edge-u-min/"
            "--edge-u-max/--edge-v-min/--edge-v-max is required")
    target_name, target_actor, target_idx = _resolve_exact_face(level, target_token, "TARGET")
    ref_name, ref_actor, ref_idx = _resolve_exact_face(level, ref_token, "--relative-to")
    if target_name == ref_name:
        raise RelationError(
            f"brush relation set: TARGET and REF must be different brushes, both are {target_name!r}")
    ref_poly = ref_actor.brush.polys[ref_idx]
    target_poly = target_actor.brush.polys[target_idx]
    rel = plane_relationship(ref_actor, ref_poly, target_actor, target_poly)
    if rel is None:
        raise RelationError(
            f"brush relation set: {target_name}:{target_idx} and {ref_name}:{ref_idx} are not "
            f"parallel/coplanar -- no defined normal direction or in-plane frame to move along")
    normal = rel.normal_a
    u_axis, v_axis = _plane_basis(normal)
    ref_world = polyalign._world_verts(ref_actor, ref_poly)
    target_world = polyalign._world_verts(target_actor, target_poly)
    uv_ref = project_to_plane(ref_world, normal)
    uv_target = project_to_plane(target_world, normal, origin=ref_world[0])
    deltas = compute_deltas(uv_ref, uv_target)

    delta_n = (gap - rel.distance) if gap is not None else 0.0
    if centroid_u is not None:
        delta_u = centroid_u - deltas.centroid_u
    elif edge_u is not None:
        mode, want = edge_u
        delta_u = want - _edge_extent(uv_ref, uv_target, axis=0, mode=mode)
    else:
        delta_u = 0.0
    if centroid_v is not None:
        delta_v = centroid_v - deltas.centroid_v
    elif edge_v is not None:
        mode, want = edge_v
        delta_v = want - _edge_extent(uv_ref, uv_target, axis=1, mode=mode)
    else:
        delta_v = 0.0

    move = tuple(delta_n * normal[i] + delta_u * u_axis[i] + delta_v * v_axis[i] for i in range(3))
    return target_name, ref_name, move


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
                      f"relationship with any brush it was checked against here")

    lines.append("")
    lines.append(f"checked: {report.brush_count} brushes, {report.pair_count} pairs, every face")
    return "\n".join(lines)
