"""Actor connectivity/containment graph -- `level graph`. Pure Python, model-side, no editor, no
native CSG. See dev/docs/superpowers/specs/2026-09-19-level-graph-design.md."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from . import polyalign, query
from .classindex import ClassRefError
from .movers import is_mover
from .texframe import newell

Vec3 = tuple[float, float, float]

# Solid-leaf BSP self-split: the same tolerance class as relation.py's _PARALLEL_EPS/_PLANE_EPS,
# named and documented rather than an implicit magic number (spec "Detection algorithm" -- a
# splitting plane's own coplanar/coincident polygons need a named classification rule; this is it,
# and it also bounds the vertex-triple-intersection tolerance in _cell_vertices below).
_SPLIT_EPS = 1e-4

# Tolerance for singular/degenerate 3x3 linear system detection in _intersect_three_planes.
_SINGULAR_EPS = 1e-9

# Tolerance for vertex extraction from half-space constraints. Looser than _SPLIT_EPS because
# vertex extraction (plane triple intersection + half-space validation) accumulates more float
# error than a single plane classification.
_VERTEX_EPS = _SPLIT_EPS * 10


class DegenerateBrushError(ValueError):
    """A brush whose PolyList doesn't bound a valid closed solid (self-intersecting/non-manifold) --
    the self-split has no well-defined 'inside' to decompose. Named after the actor; never a bare
    crash (spec: 'the one honest remaining edge case')."""


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _len(a: Vec3) -> float:
    return (a[0] ** 2 + a[1] ** 2 + a[2] ** 2) ** 0.5


def _norm(a: Vec3) -> Vec3:
    m = _len(a)
    return (a[0] / m, a[1] / m, a[2] / m)


def _neg(a: Vec3) -> Vec3:
    return (-a[0], -a[1], -a[2])


@dataclass(frozen=True)
class ConvexCell:
    """One convex piece of a brush's decomposed volume. `half_spaces`: `(outward_normal, d)` pairs;
    a point `p` is inside this cell iff `dot(n, p) <= d + _SPLIT_EPS` for every pair. `vertices`:
    every corner of the cell's boundary, deduped -- derived from `half_spaces` (see
    `_cell_vertices`), not tracked separately during the split, so the two can never disagree."""
    vertices: list[Vec3]
    half_spaces: list[tuple[Vec3, float]]


def _classify_poly(poly: list[Vec3], normal: Vec3, d: float) -> str:
    """'front' (strictly outside, all > d+eps), 'back' (strictly inside, all < d-eps), 'coplanar'
    (every vertex within eps of the plane), or 'span' (straddles -- needs clipping)."""
    signs = [_dot(normal, v) - d for v in poly]
    has_front = any(s > _SPLIT_EPS for s in signs)
    has_back = any(s < -_SPLIT_EPS for s in signs)
    if has_front and has_back:
        return "span"
    if has_front:
        return "front"
    if has_back:
        return "back"
    return "coplanar"


def _plane_intersect(a: Vec3, b: Vec3, normal: Vec3, d: float) -> Vec3:
    da, db = _dot(normal, a) - d, _dot(normal, b) - d
    t = da / (da - db)
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2]))


def _clip_polygon(poly: list[Vec3], normal: Vec3, d: float) -> list[Vec3]:
    """Sutherland-Hodgman clip of `poly` (assumed planar+convex, as every brush face is) to the
    half-space `dot(normal, p) <= d + eps` -- the 3-D generalisation of relation.py's `_clip_2d`."""
    out: list[Vec3] = []
    n = len(poly)
    for i in range(n):
        cur, prev = poly[i], poly[i - 1]
        cur_in = _dot(normal, cur) - d <= _SPLIT_EPS
        prev_in = _dot(normal, prev) - d <= _SPLIT_EPS
        if cur_in:
            if not prev_in:
                out.append(_plane_intersect(prev, cur, normal, d))
            out.append(cur)
        elif prev_in:
            out.append(_plane_intersect(prev, cur, normal, d))
    return out


@dataclass
class _BspNode:
    planes: list[tuple[Vec3, float]] = field(default_factory=list)   # only meaningful on a leaf
    solid: bool | None = None                                        # only meaningful on a leaf
    front: "_BspNode | None" = None
    back: "_BspNode | None" = None


def _build_solid_bsp(polys: list[list[Vec3]], planes_so_far: list[tuple[Vec3, float]],
                      *, inside: bool, ref: str) -> _BspNode:
    """Recursive solid-leaf BSP over `polys` (world-space polygons, initially a brush's own faces --
    each face's OWN outward normal, so 'front' of any one of them is genuinely outside the solid).
    A leaf (empty remaining poly set) is classified `inside` -- inherited from which side of its
    PARENT split it fell on, per the standard solid-leaf BSP construction this project's own native
    engine already applies at brush scale (`bspBrushCSG`'s temp-brush BSP, NATIVE-MATERIALIZE.md).
    `ref` (the owning actor's name) is threaded through purely so a degenerate face can be named in
    `DegenerateBrushError` -- this function has no other actor context."""
    if not polys:
        return _BspNode(planes=list(planes_so_far), solid=inside)
    plane_poly = polys[0]
    raw_normal = newell(plane_poly)
    if _len(raw_normal) < _SPLIT_EPS:
        # A zero-area/collinear face: _norm would ZeroDivisionError. Caught in this plan's own
        # self-review -- the pre-fix code had no guard here, so a genuinely malformed (but
        # >=3-vertex, so not already filtered by decompose_convex's len() check) brush face would
        # crash with a raw traceback instead of the spec-mandated named, skipped-node treatment.
        raise DegenerateBrushError(f"{ref}: brush face is degenerate (zero-area or collinear)")
    normal = _norm(raw_normal)
    d = _dot(normal, plane_poly[0])
    front_polys: list[list[Vec3]] = []
    back_polys: list[list[Vec3]] = []
    for poly in polys[1:]:
        cls = _classify_poly(poly, normal, d)
        if cls == "front":
            front_polys.append(poly)
        elif cls == "back":
            back_polys.append(poly)
        elif cls == "coplanar":
            # Named tie-break (spec-required): a coplanar face's OWN outward normal decides which
            # side it bounds -- agreeing with this plane's normal means it faces the same way as the
            # outside, so it belongs with the front (outside) branch; opposing means back (inside).
            raw_own = newell(poly)
            if _len(raw_own) < _SPLIT_EPS:
                raise DegenerateBrushError(f"{ref}: brush face is degenerate (zero-area or collinear)")
            own_normal = _norm(raw_own)
            (front_polys if _dot(own_normal, normal) > 0 else back_polys).append(poly)
        else:  # span
            # `_clip_polygon(p, n, d)` keeps `dot(n,p) <= d` -- the BACK (inside-this-face) side,
            # by this module's own convention -- regardless of variable name. `fp` is therefore the
            # BACK fragment, WITH the original (correct) winding, since it's a plain sub-slice of
            # `poly`. The FRONT fragment is obtained by clipping the SAME unreversed `poly` against
            # the negated plane (`_neg(normal), -d` keeps `dot(normal,p) >= d`) -- never reverse the
            # input polygon itself, which would corrupt its own outward-normal direction the next
            # time this fragment is chosen as a splitting plane one level deeper. (Caught in this
            # plan's own self-review: the pre-fix code both routed these two fragments to the WRONG
            # lists and additionally reversed the front fragment's winding via `reversed(poly)` --
            # either bug alone corrupts a non-convex decomposition; verified by hand-tracing the
            # L-shaped fixture's own actual split sequence, where this exact branch fires.)
            back_frag = _clip_polygon(poly, normal, d)
            front_frag = _clip_polygon(poly, _neg(normal), -d)
            if len(back_frag) >= 3:
                back_polys.append(back_frag)
            if len(front_frag) >= 3:
                front_polys.append(front_frag)
    front = _build_solid_bsp(front_polys, planes_so_far + [(_neg(normal), -d)], inside=False, ref=ref)
    back = _build_solid_bsp(back_polys, planes_so_far + [(normal, d)], inside=True, ref=ref)
    return _BspNode(front=front, back=back)


def _collect_solid_leaves(node: _BspNode) -> list[list[tuple[Vec3, float]]]:
    if node.front is None and node.back is None:
        return [node.planes] if node.solid else []
    return _collect_solid_leaves(node.front) + _collect_solid_leaves(node.back)


def _intersect_three_planes(pl1, pl2, pl3) -> Vec3 | None:
    """The unique point on all three planes (Cramer's rule on the 3x3 normal system), or None if
    the normals are linearly dependent (no unique intersection -- e.g. two parallel planes)."""
    n1, d1 = pl1
    n2, d2 = pl2
    n3, d3 = pl3
    c23, c31, c12 = _cross(n2, n3), _cross(n3, n1), _cross(n1, n2)
    det = _dot(n1, c23)
    if abs(det) < _SINGULAR_EPS:
        return None
    return tuple(
        (d1 * c23[i] + d2 * c31[i] + d3 * c12[i]) / det for i in range(3)
    )


def _cell_vertices(planes: list[tuple[Vec3, float]]) -> list[Vec3]:
    """Every vertex of the convex polytope `{p : dot(n,p) <= d + eps for all (n,d) in planes}`: the
    intersection of every plane TRIPLE, kept only when it also satisfies every OTHER plane --
    standard H-representation -> V-representation for a bounded convex region."""
    out: list[Vec3] = []
    for i, j, k in itertools.combinations(range(len(planes)), 3):
        p = _intersect_three_planes(planes[i], planes[j], planes[k])
        if p is None:
            continue
        if all(_dot(n, p) <= d + _VERTEX_EPS for n, d in planes):
            if not any(_len(_sub(p, q)) < _VERTEX_EPS for q in out):
                out.append(p)
    return out


def decompose_convex(actor, *, cache: dict[str, list[ConvexCell]] | None = None) -> list[ConvexCell]:
    """`actor`'s brush volume as a list of convex cells (world space). An already-convex brush
    decomposes to exactly ONE cell -- the trivial case of this same recursion, not a separate code
    path. Raises `DegenerateBrushError` naming the actor if no solid leaf survives (a malformed,
    self-intersecting/non-manifold PolyList -- no well-defined 'inside' to decompose).

    `cache`, when given, is a plain `{actor_name: cells}` dict the CALLER owns and reuses across every
    call for the lifetime of one `build_graph` run (spec: "computed ONCE per brush and memoized ...
    not a function of level size" -- caught missing in this plan's own self-review: without this,
    `build_graph` was recomputing every brush's decomposition on EVERY pair it participates in,
    O(N) -> O(N^2) recomputations for an N-brush level). `Actor` is an unfrozen dataclass (not
    hashable), so this is a caller-supplied dict keyed by name, not `functools.lru_cache` on the
    actor itself. A raised `DegenerateBrushError` is NOT cached -- `build_graph`'s own `_safe()`
    wrapper (Task 6) is what remembers a bad brush so it isn't re-probed."""
    if cache is not None and actor.name in cache:
        return cache[actor.name]
    polys = [polyalign._world_verts(actor, p) for p in actor.brush.polys if len(p.vertices) >= 3]
    tree = _build_solid_bsp(polys, [], inside=True, ref=actor.name)
    leaves = _collect_solid_leaves(tree)
    if not leaves:
        raise DegenerateBrushError(f"{actor.name}: brush does not bound a valid solid "
                                    f"(self-intersecting or non-manifold PolyList)")
    cells = []
    for planes in leaves:
        verts = _cell_vertices(planes)
        if len(verts) < 4:      # a genuine solid cell always has >= 4 corners in 3-D
            raise DegenerateBrushError(f"{actor.name}: brush does not bound a valid solid "
                                        f"(a decomposed cell has no volume)")
        cells.append(ConvexCell(vertices=verts, half_spaces=planes))
    if cache is not None:
        cache[actor.name] = cells
    return cells


# Touching tolerance -- the same class of constant as relation.py's _PARALLEL_EPS/_PLANE_EPS/
# _TOUCH_EPS/_GAP_EPS: real editor-placed brushes carry sub-uu float noise (t3d.md "Fractional
# vertices"), so "touching" means within this band, not exact zero-gap contact.
_TOUCH_EPS = 1e-3

# Same constant/rationale as relation.py's own _PARALLEL_EPS: 1 - |n.n'| below this => same plane
# orientation (parallel or anti-parallel normals), used to decide two faces are coplanar candidates.
_PARALLEL_EPS = 1e-3


def _cell_edge_directions(cell: ConvexCell) -> list[Vec3]:
    """Unit directions of the cell's true polytope EDGES (not merely its face normals): two
    vertices lying on >= 2 common bounding planes share an edge, since in 3-D an edge is exactly
    the intersection of two faces. Needed for SAT's edge-cross candidate axes -- face-normal-only
    SAT is NOT exact for two general convex polytopes (spec 'Detection algorithm')."""
    on_planes = []
    for v in cell.vertices:
        on_planes.append(frozenset(
            i for i, (n, d) in enumerate(cell.half_spaces) if abs(_dot(n, v) - d) <= _VERTEX_EPS))
    dirs = []
    n = len(cell.vertices)
    for i in range(n):
        for j in range(i + 1, n):
            if len(on_planes[i] & on_planes[j]) >= 2:
                delta = _sub(cell.vertices[j], cell.vertices[i])
                if _len(delta) > _SINGULAR_EPS:
                    dirs.append(_norm(delta))
    return dirs


def _sat_axes(cell_a: ConvexCell, cell_b: ConvexCell) -> list[Vec3]:
    """Every face normal of both cells, plus every cross product of an edge of A with an edge of
    B -- the standard exact candidate-axis set for two convex polytopes (not face normals alone)."""
    axes = [n for n, _ in cell_a.half_spaces] + [n for n, _ in cell_b.half_spaces]
    for ea in _cell_edge_directions(cell_a):
        for eb in _cell_edge_directions(cell_b):
            cr = _cross(ea, eb)
            if _len(cr) > _SINGULAR_EPS:
                axes.append(_norm(cr))
    return axes


def cells_touch_or_overlap(cell_a: ConvexCell, cell_b: ConvexCell) -> bool:
    """SAT: the two convex cells are DISJOINT iff some candidate axis separates their projected
    intervals by more than `_TOUCH_EPS`. True (touching or overlapping) otherwise."""
    for axis in _sat_axes(cell_a, cell_b):
        a_vals = [_dot(axis, v) for v in cell_a.vertices]
        b_vals = [_dot(axis, v) for v in cell_b.vertices]
        a_lo, a_hi = min(a_vals), max(a_vals)
        b_lo, b_hi = min(b_vals), max(b_vals)
        if a_hi < b_lo - _TOUCH_EPS or b_hi < a_lo - _TOUCH_EPS:
            return False
    return True


@dataclass(frozen=True)
class BrushOverlap:
    touches: bool
    matched_pair: tuple[int, int] | None
    area_estimate: float | None


def _bbox(cell: ConvexCell) -> tuple[Vec3, Vec3]:
    xs = [v[0] for v in cell.vertices]; ys = [v[1] for v in cell.vertices]; zs = [v[2] for v in cell.vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _bbox_intersection_area(a_lo, a_hi, b_lo, b_hi) -> float:
    """A rough overlap SIZE estimate: the intersection box's two smallest side lengths multiplied --
    an informational annotation only (spec 'Output format'), never the touch/overlap DETECTION
    itself, which is exact via SAT regardless of this number."""
    lo = tuple(max(a_lo[i], b_lo[i]) for i in range(3))
    hi = tuple(min(a_hi[i], b_hi[i]) for i in range(3))
    sides = sorted(max(0.0, hi[i] - lo[i]) for i in range(3))
    return sides[0] * sides[1]   # the two smallest dims approximate the touching cross-section


def _plane_basis_2d(normal: Vec3) -> tuple[Vec3, Vec3]:
    """An arbitrary, deterministic orthonormal (U, V) basis for the plane perpendicular to
    `normal` -- same construction as `relation.py`'s own `_plane_basis`, not imported from it (this
    module has no other dependency on `relation.py`'s internals). Only used to compare two faces'
    OWN footprints against each other in a shared 2-D frame; not meaningful in isolation."""
    helper = (0.0, 0.0, 1.0) if abs(normal[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = _norm(_cross(helper, normal))
    v = _cross(normal, u)
    return u, v


def _footprints_overlap(wa: list[Vec3], wb: list[Vec3], normal: Vec3) -> bool:
    """Round-2 review finding: two faces can be coplanar (same plane) without their FOOTPRINTS
    (2-D extents within that plane) actually overlapping -- e.g. two rooms sharing a common floor
    HEIGHT at opposite ends of a level. `_matched_face_pair` picking the largest-area coplanar face
    ANYWHERE, with no overlap check, could report a physically unrelated pair as the 'exact' matched
    boundary. Fixed with a projected-bounding-box overlap test in a shared (U,V) frame -- cheaper
    than a full polygon clip and sufficient to reject a spatially-separate coincidental coplanar
    pair, which is the actual failure mode found (not a hairline-adjacent-footprint edge case)."""
    u, v = _plane_basis_2d(normal)
    origin = wa[0]
    proj_a = [(_dot(_sub(p, origin), u), _dot(_sub(p, origin), v)) for p in wa]
    proj_b = [(_dot(_sub(p, origin), u), _dot(_sub(p, origin), v)) for p in wb]
    a_lo = (min(p[0] for p in proj_a), min(p[1] for p in proj_a))
    a_hi = (max(p[0] for p in proj_a), max(p[1] for p in proj_a))
    b_lo = (min(p[0] for p in proj_b), min(p[1] for p in proj_b))
    b_hi = (max(p[0] for p in proj_b), max(p[1] for p in proj_b))
    return (a_lo[0] <= b_hi[0] + _TOUCH_EPS and b_lo[0] <= a_hi[0] + _TOUCH_EPS and
            a_lo[1] <= b_hi[1] + _TOUCH_EPS and b_lo[1] <= a_hi[1] + _TOUCH_EPS)


def _ensure_ccw_2d(poly: list[tuple[float, float]]) -> list[tuple[float, float]]:
    area2 = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                for i in range(len(poly)))
    return list(reversed(poly)) if area2 < 0 else poly


def _clip_2d(subject: list[tuple[float, float]], clip: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Sutherland-Hodgman: clip `subject` (any simple polygon) against the CONVEX polygon `clip`
    (every brush face is convex by construction), edge by edge. Both must be CCW-wound (caller's
    job -- see `_ensure_ccw_2d`) for the half-plane test's sign to be consistent, same convention
    `relation.py`'s own `classify_footprint_2d`/`_clip_2d` use for the identical problem in a
    different module (round 3 review: no public function to call directly, see the module
    docstring's "Output format" note -- this mirrors that approach rather than reusing it)."""
    out = list(subject)
    n = len(clip)
    for i in range(n):
        if not out:
            return []
        cx0, cy0 = clip[i]
        cx1, cy1 = clip[(i + 1) % n]
        ex, ey = cx1 - cx0, cy1 - cy0
        def inside(px, py):
            return (px - cx0) * ey - (py - cy0) * ex <= 1e-9
        new_out = []
        m = len(out)
        for j in range(m):
            cur = out[j]
            prev = out[j - 1]
            cur_in, prev_in = inside(*cur), inside(*prev)
            if cur_in:
                if not prev_in:
                    new_out.append(_seg_intersect_2d(prev, cur, (cx0, cy0), ex, ey))
                new_out.append(cur)
            elif prev_in:
                new_out.append(_seg_intersect_2d(prev, cur, (cx0, cy0), ex, ey))
        out = new_out
    return out


def _seg_intersect_2d(p1, p2, edge_origin, ex, ey):
    x1, y1 = p1
    x2, y2 = p2
    ox, oy = edge_origin
    dx, dy = x2 - x1, y2 - y1
    denom = dx * ey - dy * ex
    if abs(denom) < 1e-12:
        return p2
    t = ((ox - x1) * ey - (oy - y1) * ex) / denom
    return (x1 + t * dx, y1 + t * dy)


def _shoelace_area_2d(poly: list[tuple[float, float]]) -> float:
    if len(poly) < 3:
        return 0.0
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                    for i in range(len(poly)))) / 2.0


def _footprint_overlap_area(wa: list[Vec3], wb: list[Vec3], normal: Vec3) -> float:
    """The ACTUAL shared area between two coplanar faces' footprints -- round-3 review found
    `_matched_face_pair` was reporting face A's OWN full area even for a PARTIAL overlap (the
    footprint-overlap gate added in round 3 allows partial/bbox overlap through, not just
    identical footprints), contradicting the 'exact area' claim in `BrushOverlap`'s docstring and
    the spec's 'Output format' section. Projects both faces into the same (U,V) frame
    `_footprints_overlap` already uses, CCW-normalizes each (a face's own winding faces ITS OWN
    outward normal, which can project CW or CCW depending on the chosen (U,V) handedness -- same
    reasoning `relation.py`'s `classify_footprint_2d` documents for the identical problem), clips
    B against A, and shoelaces the result. Zero-vertex clip result (no overlap at all, despite
    passing the cheaper bbox pre-check) returns 0.0, not an error -- a real, if rare, case for two
    footprints whose bboxes touch but whose actual polygons don't (an L-shaped face's notch)."""
    u, v = _plane_basis_2d(normal)
    origin = wa[0]
    proj_a = _ensure_ccw_2d([(_dot(_sub(p, origin), u), _dot(_sub(p, origin), v)) for p in wa])
    proj_b = _ensure_ccw_2d([(_dot(_sub(p, origin), u), _dot(_sub(p, origin), v)) for p in wb])
    clipped = _clip_2d(proj_b, proj_a)
    return _shoelace_area_2d(clipped)


def _matched_face_pair(actor_a, actor_b) -> tuple[int, int, float] | None:
    """A SINGLE poly pair (one from each brush) whose planes are near-coincident AND whose
    footprints actually overlap -- the 'clean shared flat boundary' case. Returns
    (idx_a, idx_b, overlap_area) or None -- `overlap_area` is the ACTUAL shared footprint area
    (`_footprint_overlap_area`), not either face's own full area, so a partial overlap reports the
    true shared size, not an overstated one. Deliberately independent of ConvexCell decomposition:
    this asks about the brushes' ORIGINAL faces, which is what a `Name:idx` drill-down selector
    must name. Ranks candidates by this SAME overlap area (the pair sharing the most real area,
    not the pair whose face-A happens to be biggest)."""
    best = None
    for ia, pa in enumerate(actor_a.brush.polys):
        try:
            na = polyalign._world_normal(actor_a, pa, ref=f"{actor_a.name}:{ia}")
        except polyalign.PolyAlignError:
            continue
        wa = polyalign._world_verts(actor_a, pa)
        for ib, pb in enumerate(actor_b.brush.polys):
            try:
                nb = polyalign._world_normal(actor_b, pb, ref=f"{actor_b.name}:{ib}")
            except polyalign.PolyAlignError:
                continue
            if abs(abs(_dot(na, nb)) - 1.0) > _PARALLEL_EPS:   # not parallel/anti-parallel -> not coplanar
                continue
            wb = polyalign._world_verts(actor_b, pb)
            if abs(_dot(_sub(wb[0], wa[0]), na)) > _TOUCH_EPS:   # not on the same plane
                continue
            if not _footprints_overlap(wa, wb, na):     # coplanar but spatially unrelated -- reject
                continue
            area = _footprint_overlap_area(wa, wb, na)
            if area <= 0.0:      # bboxes touched but the real polygons don't (e.g. an L-shape notch)
                continue
            if best is None or area > best[2]:
                best = (ia, ib, area)
    return best



def brush_overlap(actor_a, actor_b, *, cache=None) -> BrushOverlap:
    """Exact touch/overlap between two brushes' full volumes (via decomposition + SAT over every
    cell pair), plus a matched single face pair + exact area when one clean shared boundary exists,
    else a bounding-box-intersection area ESTIMATE (informational only -- detection stays exact).
    `cache`: see `decompose_convex` -- pass the SAME dict `build_graph` uses for every brush pair."""
    cells_a = decompose_convex(actor_a, cache=cache)
    cells_b = decompose_convex(actor_b, cache=cache)
    touches = any(cells_touch_or_overlap(ca, cb) for ca in cells_a for cb in cells_b)
    if not touches:
        return BrushOverlap(touches=False, matched_pair=None, area_estimate=None)
    matched = _matched_face_pair(actor_a, actor_b)
    if matched is not None:
        ia, ib, area = matched
        return BrushOverlap(touches=True, matched_pair=(ia, ib), area_estimate=area)
    a_lo, a_hi = None, None
    for c in cells_a:
        lo, hi = _bbox(c)
        a_lo = lo if a_lo is None else tuple(min(a_lo[i], lo[i]) for i in range(3))
        a_hi = hi if a_hi is None else tuple(max(a_hi[i], hi[i]) for i in range(3))
    b_lo, b_hi = None, None
    for c in cells_b:
        lo, hi = _bbox(c)
        b_lo = lo if b_lo is None else tuple(min(b_lo[i], lo[i]) for i in range(3))
        b_hi = hi if b_hi is None else tuple(max(b_hi[i], hi[i]) for i in range(3))
    return BrushOverlap(touches=True, matched_pair=None,
                         area_estimate=_bbox_intersection_area(a_lo, a_hi, b_lo, b_hi))


def point_in_brush(actor, point: Vec3, *, cache=None) -> bool:
    """True iff `point` is inside (or within tolerance of the boundary of) ANY ONE of `actor`'s
    decomposed convex cells -- a plain OR over cells, so a point on a cell boundary the
    decomposition itself introduced (shared by two cells of the SAME brush) is safely reported as
    contained by whichever cell's tolerance band it lands in, not double-penalised.
    `cache`: see `decompose_convex`."""
    for cell in decompose_convex(actor, cache=cache):
        if all(_dot(n, point) <= d + _VERTEX_EPS for n, d in cell.half_spaces):
            return True
    return False


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    relation: str
    directed: bool
    matched_pair: tuple[int, int] | None = None
    area_estimate: float | None = None


def classify_pair(name_a, actor_a, name_b, actor_b, *, order_index: dict, class_index,
                   cache=None) -> list[Edge]:
    """Every edge between two BRUSH actors (both must have `.brush is not None`; a caller passing a
    non-brush actor here is a bug in Task 6's dispatch, not something this function guards).
    `cache`: see `decompose_convex` -- forwarded to `brush_overlap`."""
    ov = brush_overlap(actor_a, actor_b, cache=cache)
    if not ov.touches:
        return []
    a_is_sub = query.csg_is_subtract(actor_a)
    b_is_sub = query.csg_is_subtract(actor_b)
    edge_kwargs = dict(matched_pair=ov.matched_pair, area_estimate=ov.area_estimate)

    if a_is_sub and b_is_sub:
        return [Edge(src=name_a, dst=name_b, relation="touches", directed=False, **edge_kwargs)]
    if not a_is_sub and not b_is_sub:      # both Add-or-Mover
        return [Edge(src=name_a, dst=name_b, relation="touches", directed=False, **edge_kwargs)]

    # exactly one is a Subtract: the other is Add-or-Mover. A Subtract itself is never a Mover (a
    # Mover emits no CsgOper at all, so csg_is_subtract is always False for it) -- only the
    # non-Subtract side ever needs a mover check, and only here. This is the ONE shape where
    # mover-ness controls the answer (contains vs. carved_by), so a missing class_index here is not
    # "assume not a Mover" -- it's "cannot know", and this module answers or raises, never guesses
    # (the same convention `movers.is_mover` itself follows): silently defaulting to "not a Mover"
    # could misclassify a real Mover as `carved_by`, the one relation this function must never
    # produce for a Mover.
    sub_name = name_a if a_is_sub else name_b
    other_name, other_actor = (name_b, actor_b) if a_is_sub else (name_a, actor_a)
    if class_index is None:
        raise ClassRefError(
            f"cannot classify {name_a!r}/{name_b!r}: exactly one is a Subtract, so whether "
            f"{other_name!r} is a Mover decides contains vs. carved_by, and no class_index was "
            f"given to check it")
    other_is_mover = is_mover(other_actor, class_index)

    if other_is_mover:
        # Movers never carve or get carved -- always `contains`, Subtract -> Mover, regardless of
        # level.order (a Mover generates no CsgOper at all; CSG order is meaningless for it).
        return [Edge(src=sub_name, dst=other_name, relation="contains", directed=True, **edge_kwargs)]

    if order_index[sub_name] < order_index[other_name]:
        return [Edge(src=sub_name, dst=other_name, relation="contains", directed=True, **edge_kwargs)]
    return [Edge(src=other_name, dst=sub_name, relation="carved_by", directed=True, **edge_kwargs)]


@dataclass(frozen=True)
class ActorGraph:
    node_names: list[str]
    edges: list[Edge]
    skipped: list[tuple[str, str]]


def build_graph(level, class_index) -> "ActorGraph":
    """Every actor is a node. Every BRUSH pair is tested via `classify_pair` (skipping any brush
    that raises `DegenerateBrushError`, recorded once in `skipped`, never re-attempted for other
    pairs it would have been in). Every non-brush actor gets a `contains` edge from EVERY brush
    whose volume contains its Location -- the multi-edge fan-out rule, same as brush-brush pairs.

    Owns ONE `cache` dict for the whole call and threads it through every `classify_pair`/
    `point_in_brush` call below -- per `decompose_convex`'s own docstring, this is what keeps
    decomposition at O(N) (once per brush) instead of O(N^2) (recomputed on every pair a brush
    participates in)."""
    order_index = {name: i for i, name in enumerate(level.order) if level.actors[name].brush is not None}
    brush_names = list(order_index)
    point_names = [n for n in level.order if level.actors[n].brush is None]

    skipped: dict[str, str] = {}
    edges: list[Edge] = []
    cache: dict[str, list[ConvexCell]] = {}

    def _safe(name):
        """Probe once whether `name`'s brush decomposes cleanly; cache the verdict so a later pair
        involving the same bad brush doesn't re-raise (and re-append to `skipped`). A CLEAN probe's
        result lands in `cache` via `decompose_convex`'s own memoization, so this is also the one
        and only time each good brush is ever decomposed."""
        if name in skipped:
            return False
        try:
            decompose_convex(level.actors[name], cache=cache)
            return True
        except DegenerateBrushError as e:
            skipped[name] = str(e)
            return False

    ok_brushes = [n for n in brush_names if _safe(n)]
    for name_a, name_b in itertools.combinations(ok_brushes, 2):
        edges.extend(classify_pair(name_a, level.actors[name_a], name_b, level.actors[name_b],
                                    order_index=order_index, class_index=class_index, cache=cache))

    for pname in point_names:
        loc = level.actors[pname].location
        if loc is None:
            continue
        point = (float(loc[0]), float(loc[1]), float(loc[2]))
        for bname in ok_brushes:
            if point_in_brush(level.actors[bname], point, cache=cache):
                edges.append(Edge(src=bname, dst=pname, relation="contains", directed=True))

    return ActorGraph(node_names=list(level.order), edges=edges,
                       skipped=sorted(skipped.items()))
