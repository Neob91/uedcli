"""Actor connectivity/containment graph -- `level graph`. Pure Python, model-side, no editor, no
native CSG. See dev/docs/superpowers/specs/2026-09-19-level-graph-design.md."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from . import polyalign
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
    try:
        polys = [polyalign._world_verts(actor, p) for p in actor.brush.polys if len(p.vertices) >= 3]
    except polyalign.PolyAlignError as e:
        raise DegenerateBrushError(f"{actor.name}: brush does not bound a valid solid "
                                    f"(degenerate actor transform)") from e
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
