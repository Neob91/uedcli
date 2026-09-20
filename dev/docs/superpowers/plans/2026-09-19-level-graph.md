# `level graph` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `uedcli level graph`, a queryable graph over every actor in a level — nodes are every
brush (Add/Subtract/Mover) and every non-brush actor; edges are `touches`/`contains`/`carved_by`,
derived from exact geometric volume overlap plus CSG order — so an agent can discover which brushes
form one segmented room, what a room connects to, and what it contains, without a native BSP build.

**Architecture:** A new pure-Python module `uedcli/actorgraph.py` (model-side, no editor, no native
CSG — mirrors `uedcli/relation.py`'s shape) does all the geometry: exact convex decomposition of a
brush's own `PolyList` via a solid-leaf BSP self-split, an exact convex-convex separating-axis test
(SAT) over decomposed cells, point-in-cell containment reusing the same decomposition, and
`touches`/`contains`/`carved_by` edge classification from CSG order. A thin CLI layer
(`uedcli/cli/commands/level.py`'s new `_level_graph`, `uedcli/cli/parsers/level.py`'s new `graph`
sub-parser) wires it to `uedcli level graph`, mirroring the existing `_level_doctor`/`event graph`
pattern exactly (`resources.mover_index` for Mover resolution, `level_sources.resolve_level_source`
for `--tree`).

**Tech Stack:** Python 3.12, pytest (`bin/test`), no new dependencies.

**Spec:** `dev/docs/superpowers/specs/2026-09-19-level-graph-design.md`

## Global Constraints

(Copied verbatim from the spec — every task's work implicitly includes these.)

- **No approximation, anywhere.** Non-convex brushes get EXACT touch/overlap detection via convex
  decomposition — the earlier bounding-box-overlap `⚠ approximate` fallback is explicitly rejected,
  not an option.
- **No `--json` in v1.** YAGNI (owner ruling, 2026-09-19; `CLAUDE.md`'s new "YAGNI on output surface"
  line). Do not add it "for consistency" with other graph verbs.
- **Flat, one-edge-per-line output, never a nested/indented tree.** Mirrors `eventgraph.py`'s
  `format_text` shape exactly: `f"{src} --{relation}--> {dst}"`, optionally with a `(...)` size
  annotation on `touches` edges only.
- **No clustering, no "room" grouping, no threshold deciding whether a connection "counts."** The
  graph reports raw nodes and edges; grouping is left to the reader.
- **Multi-edge fan-out**: an actor overlapping several others gets one edge per overlapping pair,
  never collapsed to one.
- **Movers are Add-like and NEVER appear in a `carved_by` edge**, in either direction — they carry a
  `PolyList` but generate no `CsgOper` and don't participate in world CSG.
- **Every named tolerance/epsilon must be a real, documented constant** — this codebase's convention
  (`relation.py`'s `_PARALLEL_EPS`/`_PLANE_EPS`/`_TOUCH_EPS`/`_GAP_EPS`), never an implicit magic
  number.
- **No exception ever reaches the user.** A degenerate or self-intersecting/non-manifold brush is
  reported as a named, skipped node — never a crash.

---

### Task 1: Convex self-split decomposition

**Files:**
- Create: `uedcli/actorgraph.py`
- Test: `uedcli/tests/test_actorgraph.py`

**Interfaces:**
- Consumes: `polyalign._world_verts(actor, poly) -> list[Vec3]`, `polyalign.PolyAlignError`,
  `texframe.newell(verts) -> Vec3` (unnormalized), `builders.cube`/`make_brush_actor` (tests only).
- Produces:
  - `Vec3 = tuple[float, float, float]`
  - `_SPLIT_EPS: float` — named epsilon for the self-split's plane classification (coplanar
    tolerance) and vertex-triple intersection tolerance.
  - `@dataclass(frozen=True) class ConvexCell: vertices: list[Vec3]; half_spaces: list[tuple[Vec3, float]]`
    (a `half_spaces` entry `(n, d)` means "inside" is `dot(n, p) <= d + _SPLIT_EPS`).
  - `class DegenerateBrushError(ValueError)` — raised naming the actor for a self-intersecting/
    non-manifold brush the self-split can't classify (the spec's "one honest remaining edge case").
  - `decompose_convex(actor, *, cache: dict | None = None) -> list[ConvexCell]` — the brush's
    world-space volume as convex cells;
    an already-convex brush returns exactly one cell (same code path, not a branch). Later tasks
    consume this signature.

- [ ] **Step 1: Write the failing tests**

```python
# uedcli/tests/test_actorgraph.py
from decimal import Decimal
import pytest
from uedcli import actorgraph
from uedcli.builders import cube, make_brush_actor


def _brush(name, brush, loc=(0, 0, 0)):
    return make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc))


def _cell_volume(cell: "actorgraph.ConvexCell") -> float:
    # Signed-volume-of-tetrahedra-from-a-point sum over the cell's own triangulated hull is overkill
    # for this test; instead assert the SET of half-space plane offsets matches a convex brush's own
    # 6 face planes exactly (a cube's half-spaces are trivially derivable), which is what "one cell,
    # trivial case" actually claims.
    return sorted(round(d, 3) for _, d in cell.half_spaces)


def test_convex_brush_decomposes_to_one_cell():
    a = _brush("A", cube(64, 64, 64))
    cells = actorgraph.decompose_convex(a)
    assert len(cells) == 1
    assert len(cells[0].half_spaces) == 6          # a cube's own 6 faces, nothing invented
    assert len(cells[0].vertices) == 8              # a cube's 8 corners, no duplicates


def test_l_shaped_brush_decomposes_to_two_or_more_convex_cells():
    # An L-shape: a 64x64x64 cube union a 64x64x64 cube offset by (64,64,0) sharing one edge --
    # built directly as a Brush with 8 faces (bottom+top+6 sides, an L-shaped prism), not via two
    # separate actors.
    from uedcli.model import Brush, Polygon
    verts_bottom = [  # the L footprint at Z=-32/+32, CCW from +Z: (0,0)-(128,0)-(128,64)-(64,64)-(64,128)-(0,128)
        (0, 0), (128, 0), (128, 64), (64, 64), (64, 128), (0, 128),
    ]
    def V(x, y, z):
        return (Decimal(x), Decimal(y), Decimal(z))
    bottom = Polygon(vertices=[V(x, y, -32) for x, y in reversed(verts_bottom)], normal=(0, 0, -1))
    top = Polygon(vertices=[V(x, y, 32) for x, y in verts_bottom], normal=(0, 0, 1))
    sides = []
    n = len(verts_bottom)
    for i in range(n):
        x0, y0 = verts_bottom[i]
        x1, y1 = verts_bottom[(i + 1) % n]
        sides.append(Polygon(vertices=[V(x0, y0, -32), V(x1, y1, -32), V(x1, y1, 32), V(x0, y0, 32)]))
    brush = Brush(model_name="Model_L", polys=[bottom, top] + sides)
    a = _brush("L", brush)
    cells = actorgraph.decompose_convex(a)
    assert len(cells) >= 2
    # Union sanity: every cell's vertices lie within the L's own bounding box, and at least one
    # cell's vertex set touches x=128 (the far arm) and another touches y=128 (the other arm) --
    # i.e. the decomposition didn't collapse to a single box bigger than the true L shape.
    all_x = [v[0] for c in cells for v in c.vertices]
    all_y = [v[1] for c in cells for v in c.vertices]
    assert max(all_x) == pytest.approx(128.0, abs=0.01)
    assert max(all_y) == pytest.approx(128.0, abs=0.01)
    assert min(all_x) == pytest.approx(0.0, abs=0.01)
    assert min(all_y) == pytest.approx(0.0, abs=0.01)

    # Stronger regression pin (added in this plan's own self-review, after finding a real
    # front/back-fragment swap bug in the "span" branch that these loose bbox checks alone did NOT
    # catch): a point genuinely INSIDE the L (the lower-left arm) must be inside exactly one cell; a
    # point in the NOTCH -- the missing upper-right quadrant this footprint carves away -- must be
    # inside NO cell. `point_in_brush` doesn't exist until Task 4, so this checks `half_spaces`
    # directly, the same way Task 4's own implementation will.
    def _in_any_cell(cells, point):
        return sum(1 for c in cells
                   if all(_dp(n, point) <= d + 1e-2 for n, d in c.half_spaces))
    def _dp(n, p):
        return n[0] * p[0] + n[1] * p[1] + n[2] * p[2]
    inside_point = (32.0, 32.0, 0.0)     # lower-left arm -- unambiguously part of the L
    notch_point = (96.0, 96.0, 0.0)      # upper-right quadrant -- unambiguously NOT part of the L
    assert _in_any_cell(cells, inside_point) == 1
    assert _in_any_cell(cells, notch_point) == 0


def test_coplanar_splitting_tie_break_is_deterministic():
    # Two independent decompositions of the SAME brush must classify a coplanar face identically --
    # regression-pins whatever tie-break Step 3 implements, not just "it doesn't crash."
    a = _brush("A", cube(64, 64, 64))
    cells1 = actorgraph.decompose_convex(a)
    cells2 = actorgraph.decompose_convex(a)
    assert [sorted(round(d, 6) for _, d in c.half_spaces) for c in cells1] == \
           [sorted(round(d, 6) for _, d in c.half_spaces) for c in cells2]


def test_collinear_face_raises_named_error_not_zerodivisionerror():
    # Round-2 review found the pre-fix code had NO guard on `_norm(newell(...))` for a genuinely
    # degenerate (collinear, zero-area) face -- and found that the plan's EXISTING degenerate-brush
    # tests (Task 3/6) use a zero-VERTEX polygon, which `decompose_convex`'s own `len(p.vertices) >=
    # 3` filter removes before it ever reaches this code, so those tests exercise a completely
    # different (already-safe) path and prove nothing about this guard. This fixture is deliberately
    # different: THREE collinear points (len == 3, passes the filter) with zero actual area, placed
    # FIRST in the poly list so it's picked as the very first splitting plane -- guaranteed to hit
    # the exact `newell(plane_poly)` call site the guard protects, not the coplanar-branch one.
    from uedcli.model import Brush, Polygon
    collinear = Polygon(vertices=[(Decimal(0), Decimal(0), Decimal(0)),
                                   (Decimal(1), Decimal(0), Decimal(0)),
                                   (Decimal(2), Decimal(0), Decimal(0))])
    brush = Brush(model_name="Model_Bad", polys=[collinear])
    a = _brush("A", brush)
    with pytest.raises(actorgraph.DegenerateBrushError, match="A"):
        actorgraph.decompose_convex(a)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'uedcli.actorgraph'`

- [ ] **Step 3: Write the implementation**

```python
# uedcli/actorgraph.py
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
    if abs(det) < 1e-9:
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
        if all(_dot(n, p) <= d + _SPLIT_EPS * 10 for n, d in planes):
            if not any(_len(_sub(p, q)) < _SPLIT_EPS * 10 for q in out):
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: PASS. If `test_l_shaped_brush_decomposes_to_two_or_more_convex_cells` fails on the exact
cell count or vertex bounds, adjust the L-shape fixture's winding (every face must wind so its Newell
normal points OUTWARD, matching `cube()`'s own convention in `builders.py`) before touching the
algorithm -- a winding bug in the test fixture is the most likely first failure, not the recursion.

- [ ] **Step 5: Commit**

```bash
git add uedcli/actorgraph.py uedcli/tests/test_actorgraph.py
git commit -m "actorgraph: exact convex self-split decomposition of one brush"
```

---

### Task 2: Exact convex-convex SAT over decomposed cells

**Files:**
- Modify: `uedcli/actorgraph.py`
- Test: `uedcli/tests/test_actorgraph.py`

**Interfaces:**
- Consumes: `ConvexCell` (Task 1).
- Produces: `_TOUCH_EPS: float`; `cells_touch_or_overlap(cell_a: ConvexCell, cell_b: ConvexCell) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
def test_two_cells_sharing_a_face_touch():
    a = _brush("A", cube(64, 64, 64), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 64), loc=(0, 0, 64))   # A's top face == B's bottom face, zero gap
    ca, = actorgraph.decompose_convex(a)
    cb, = actorgraph.decompose_convex(b)
    assert actorgraph.cells_touch_or_overlap(ca, cb)


def test_two_cells_with_a_real_gap_do_not_touch():
    a = _brush("A", cube(64, 64, 64), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 64), loc=(0, 0, 128))   # 32uu real gap
    ca, = actorgraph.decompose_convex(a)
    cb, = actorgraph.decompose_convex(b)
    assert not actorgraph.cells_touch_or_overlap(ca, cb)


def test_overlapping_cells_touch():
    a = _brush("A", cube(64, 64, 64), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 64), loc=(32, 0, 0))    # half-overlap in X
    ca, = actorgraph.decompose_convex(a)
    cb, = actorgraph.decompose_convex(b)
    assert actorgraph.cells_touch_or_overlap(ca, cb)


def test_edge_cross_axis_is_needed_for_two_rotated_convex_shapes():
    # Two OBLIQUE (non-parallel-axis) thin boxes -- see the implementer note below for why this
    # must NOT be two prisms sharing one extrusion axis (the plan's own first draft used two
    # Z-extruded triangular prisms, only rotated about Z; caught in this plan's self-review: for
    # any two convex shapes sharing one common "long" axis, EVERY edge-cross candidate axis reduces
    # to a multiple of an already-tested face normal -- cross(shared_axis, anything) and
    # cross(anything_in_the_shared_axis's_perpendicular_plane, same) both land back on that shape's
    # own face-normal set. Such a fixture can NEVER exercise a genuinely new edge-cross axis no
    # matter how it's rotated/translated -- tuning it would have been chasing a test that cannot
    # pass for the reason intended even in principle. Two boxes on genuinely different (skew) axes
    # are required instead.
    from uedcli.model import Brush, Polygon
    def box(center, long_axis_deg_from_y_toward_z, half_long=15.0, half_thin=1.0):
        """A thin rectangular box: half_long along a LONG axis tilted `long_axis_deg_from_y_toward_z`
        degrees from +Y toward +Z (0 -> long axis is +Y, i.e. this box's own axis choice; a second
        box built with a different angle here is on a genuinely different, non-parallel axis from
        one built at a different angle -- unlike the rejected prism fixture, these two boxes'
        long axes are NOT forced to be parallel)."""
        import math
        a = math.radians(long_axis_deg_from_y_toward_z)
        long_dir = (0.0, math.cos(a), math.sin(a))
        thin1 = (1.0, 0.0, 0.0)                                   # always perpendicular to long_dir
        thin2 = _cross(long_dir, thin1)                           # actorgraph._cross -- also perp.
        cx, cy, cz = center
        def corner(u, v, w):  # u,v,w in {-1, 1}
            return (Decimal(str(cx + u * half_long * long_dir[0] + v * half_thin * thin1[0]
                                 + w * half_thin * thin2[0])),
                    Decimal(str(cy + u * half_long * long_dir[1] + v * half_thin * thin1[1]
                                 + w * half_thin * thin2[1])),
                    Decimal(str(cz + u * half_long * long_dir[2] + v * half_thin * thin1[2]
                                 + w * half_thin * thin2[2])))
        # 8 corners of a parallelepiped, 6 quad faces. `(long_dir, thin1, thin2)` is right-handed
        # (thin2 = cross(long_dir, thin1)), so each face's winding below was hand-derived via the
        # cross-product test itself (edge1 x edge2 must point along that face's own outward axis) --
        # round 2 review found 4 of the original 6 faces backwards (this fixture's own first draft
        # asserted "winding not asserted, order-tolerant," which was WRONG: an inward-pointing face
        # picked as a splitting plane inverts the front/back labelling for whatever it splits,
        # exactly the class of bug this whole detection algorithm exists to get right). Re-derived
        # all 6 by hand for this fix; STILL run `newell`/`polyalign._world_normal` on each and
        # confirm all 6 point outward before trusting anything downstream -- hand-derivation is not
        # a substitute for checking against real code, only a starting point that is no longer
        # blind guessing.
        c = {(u, v, w): corner(u, v, w) for u in (-1, 1) for v in (-1, 1) for w in (-1, 1)}
        faces = [
            [c[(1, -1, -1)], c[(1, 1, -1)], c[(1, 1, 1)], c[(1, -1, 1)]],       # +long_dir cap
            [c[(-1, -1, 1)], c[(-1, 1, 1)], c[(-1, 1, -1)], c[(-1, -1, -1)]],   # -long_dir cap
            [c[(-1, 1, 1)], c[(1, 1, 1)], c[(1, 1, -1)], c[(-1, 1, -1)]],       # +thin1
            [c[(-1, -1, -1)], c[(1, -1, -1)], c[(1, -1, 1)], c[(-1, -1, 1)]],   # -thin1
            [c[(-1, 1, -1)], c[(1, 1, -1)], c[(1, -1, -1)], c[(-1, -1, -1)]],   # -thin2
            [c[(-1, -1, 1)], c[(1, -1, 1)], c[(1, 1, 1)], c[(-1, 1, 1)]],       # +thin2
        ]
        return Brush(model_name="Model_Box", polys=[Polygon(vertices=v) for v in faces])
    a = _brush("A", box((0, 0, 0), long_axis_deg_from_y_toward_z=0.0))
    b = _brush("B", box((0, 0, 8), long_axis_deg_from_y_toward_z=45.0))
    ca, = actorgraph.decompose_convex(a)
    cb, = actorgraph.decompose_convex(b)
    result = actorgraph.cells_touch_or_overlap(ca, cb)
    assert isinstance(result, bool)   # placeholder pending the implementer's own verified value --
                                       # see the note below; DO NOT leave this as the final assertion
```

Note for the implementer -- this is real, required work, not a placeholder to skip, and it is
GENUINELY HARD to get right by hand (this plan's own author tried and could not reach confident exact
numbers without running code -- said so plainly rather than guessing):

1. The face/winding sketch above (6 quad faces of an oblique box) needs its OWN outward-normal
   verification first -- run `polyalign._world_normal` (or plain `newell`) on each of the 6 faces
   right after building one and confirm ALL SIX point outward (away from the box's own center)
   before trusting anything downstream. These 6 windings were hand-re-derived in this plan's own
   round-2 review after the original draft had 4 of 6 backwards (an inward-pointing face, if picked
   as a splitting plane, inverts front/back for its whole subtree -- exactly the bug class this
   algorithm exists to avoid) -- hand-derivation lowers the risk, it does not remove the need to
   check against real code before relying on it.
2. **Do not derive the expected touching/not-touching answer from `cells_touch_or_overlap` itself, or
   from face-normal-only SAT, or from any variant of the code under test** -- that is exactly the
   circularity this note exists to prevent. Instead, write a small, throwaway, fully independent
   brute-force check: sample a dense grid of points across each box's own volume (trivial for a
   parallelepiped: `center + u*half_long*long_dir + v*half_thin*thin1 + w*half_thin*thin2` for
   `u,v,w` ranging over, say, 20 evenly-spaced steps in `[-1,1]` each -- ~9000 points per box) and
   compute the minimum pairwise distance between any sampled point of A and any sampled point of B.
   This uses no SAT/BSP machinery at all -- pure coordinate arithmetic -- so it is a genuinely
   independent ground truth.
3. Start from the `long_axis_deg_from_y_toward_z=0.0` / `45.0`, `center=(0,0,8)` configuration above,
   but treat it as a STARTING POINT ONLY, not a verified answer -- run the brute-force check, and if
   the two boxes turn out to be more than a couple of tolerance-widths apart (a clean "obviously not
   touching" case) or badly overlapping (a clean "obviously touching" case) EITHER is fine, as long
   as the SEPARATE follow-up check in step 4 shows face-normal-only SAT gets it wrong.
4. With a brute-force verdict in hand, temporarily disable the edge-cross loop in
   `cells_touch_or_overlap` (comment out the `for ea in ... for eb in ...` block in `_sat_axes`) and
   re-run `cells_touch_or_overlap` on the same two cells. If face-normal-only SAT agrees with the
   brute-force verdict, this configuration does NOT exercise the bug this test exists to pin --
   adjust the angle/offset (try a larger tilt, a different `center` offset axis, or swapping which
   perpendicular direction is `thin1` vs `thin2`) and repeat from step 2 until face-normal-only SAT
   and the brute-force verdict DISAGREE. That disagreement is what proves this specific configuration
   needs the edge-cross axes.
5. Only then replace the placeholder `assert isinstance(result, bool)` with the real, brute-force-
   verified expected value (`assert result is True` or `assert result is False`), and leave a comment
   citing the brute-force distance that established it (e.g. "brute-force min sampled distance:
   1.3uu, well under the 2*half_thin=2uu combined half-thickness -- these genuinely touch").

- [ ] **Step 2: Run tests to verify they fail**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: FAIL with `AttributeError: module 'uedcli.actorgraph' has no attribute 'cells_touch_or_overlap'`

- [ ] **Step 3: Write the implementation**

```python
# appended to uedcli/actorgraph.py

# Touching tolerance -- the same class of constant as relation.py's _PARALLEL_EPS/_PLANE_EPS/
# _TOUCH_EPS/_GAP_EPS: real editor-placed brushes carry sub-uu float noise (t3d.md "Fractional
# vertices"), so "touching" means within this band, not exact zero-gap contact.
_TOUCH_EPS = 1e-3


def _cell_edge_directions(cell: ConvexCell) -> list[Vec3]:
    """Unit directions of the cell's true polytope EDGES (not merely its face normals): two
    vertices lying on >= 2 common bounding planes share an edge, since in 3-D an edge is exactly
    the intersection of two faces. Needed for SAT's edge-cross candidate axes -- face-normal-only
    SAT is NOT exact for two general convex polytopes (spec 'Detection algorithm')."""
    on_planes = []
    for v in cell.vertices:
        on_planes.append(frozenset(
            i for i, (n, d) in enumerate(cell.half_spaces) if abs(_dot(n, v) - d) <= _SPLIT_EPS * 10))
    dirs = []
    n = len(cell.vertices)
    for i in range(n):
        for j in range(i + 1, n):
            if len(on_planes[i] & on_planes[j]) >= 2:
                delta = _sub(cell.vertices[j], cell.vertices[i])
                if _len(delta) > 1e-9:
                    dirs.append(_norm(delta))
    return dirs


def _sat_axes(cell_a: ConvexCell, cell_b: ConvexCell) -> list[Vec3]:
    """Every face normal of both cells, plus every cross product of an edge of A with an edge of
    B -- the standard exact candidate-axis set for two convex polytopes (not face normals alone)."""
    axes = [n for n, _ in cell_a.half_spaces] + [n for n, _ in cell_b.half_spaces]
    for ea in _cell_edge_directions(cell_a):
        for eb in _cell_edge_directions(cell_b):
            cr = _cross(ea, eb)
            if _len(cr) > 1e-9:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: PASS (tune the rotated-prism fixture per the note above if the last test needs it).

- [ ] **Step 5: Commit**

```bash
git add uedcli/actorgraph.py uedcli/tests/test_actorgraph.py
git commit -m "actorgraph: exact convex-convex SAT (face normals + edge-cross axes)"
```

---

### Task 3: Brush-to-brush touch/overlap, matched face pair, and size annotation

**Files:**
- Modify: `uedcli/actorgraph.py`
- Test: `uedcli/tests/test_actorgraph.py`

**Interfaces:**
- Consumes: `decompose_convex`, `cells_touch_or_overlap`, `DegenerateBrushError` (Task 1-2);
  `polyalign._world_normal`, `polyalign.PolyAlignError`; `relation._shoelace_area`-STYLE area math
  (a NEW function, not calling `relation.classify_footprint_2d` directly -- see spec "Output format":
  that function returns only a shape label, not an area).
- Produces:
  ```python
  @dataclass(frozen=True)
  class BrushOverlap:
      touches: bool
      matched_pair: tuple[int, int] | None   # (poly_idx_a, poly_idx_b) when ONE clean face pair
                                              # accounts for the touch; None for a genuine volume
                                              # overlap with no single shared flat boundary
      area_estimate: float | None            # exact area when matched_pair is set; a bounding-box
                                              # intersection estimate otherwise; None if not touching
  def brush_overlap(actor_a, actor_b, *, cache: dict | None = None) -> BrushOverlap
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_brush_overlap_touching_flat_face_gives_matched_pair_and_exact_area():
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))     # top face at Z=4, area 64*64=4096
    b = _brush("B", cube(64, 64, 8), loc=(0, 0, 8))     # bottom face at Z=4
    ov = actorgraph.brush_overlap(a, b)
    assert ov.touches
    assert ov.matched_pair is not None
    assert ov.area_estimate == pytest.approx(4096.0, rel=1e-3)


def test_brush_overlap_partial_footprint_reports_actual_shared_area_not_full_face_area():
    # Round-3 review finding: allowing a PARTIAL (not just identical) footprint overlap through
    # `_footprints_overlap` without also fixing the reported area meant a partial match reported
    # face A's own FULL area, contradicting `BrushOverlap`'s "exact area" claim. A: top face at
    # Z=4, X,Y in [-32,32] (area 4096). B: bottom face at Z=4, X,Y in [0,64] (also area 4096, offset
    # by (32,32) so only the X,Y in [0,32] quadrant genuinely overlaps -- area 32*32=1024).
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 8), loc=(32, 32, 8))
    ov = actorgraph.brush_overlap(a, b)
    assert ov.touches
    assert ov.matched_pair is not None
    assert ov.area_estimate == pytest.approx(1024.0, rel=1e-3)   # the SHARED area, not either face's 4096


def test_brush_overlap_no_touch():
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 8), loc=(0, 0, 128))
    ov = actorgraph.brush_overlap(a, b)
    assert not ov.touches
    assert ov.matched_pair is None
    assert ov.area_estimate is None


def test_brush_overlap_volume_overlap_no_matched_pair():
    a = _brush("A", cube(64, 64, 64), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 64), loc=(32, 32, 32))   # genuine 3-D corner overlap, no shared flat face
    ov = actorgraph.brush_overlap(a, b)
    assert ov.touches
    assert ov.matched_pair is None
    assert ov.area_estimate is not None   # bounding-box-intersection estimate, not exact


def test_footprints_overlap_rejects_coplanar_but_spatially_separate_faces():
    # Round-2 review finding: `_matched_face_pair` used to accept ANY coplanar pair (same plane),
    # with no check that their actual 2-D footprints overlap -- two rooms sharing a common floor
    # HEIGHT at opposite ends of a level would wrongly "match." Direct unit test of the fix, not a
    # full adversarial brush pair (simpler to get exactly right): two quads on the SAME plane
    # (Z=0, normal (0,0,1)), disjoint in X by a clean 10-unit gap.
    quad_a = [(Decimal(0), Decimal(0), Decimal(0)), (Decimal(10), Decimal(0), Decimal(0)),
              (Decimal(10), Decimal(10), Decimal(0)), (Decimal(0), Decimal(10), Decimal(0))]
    quad_b = [(Decimal(20), Decimal(0), Decimal(0)), (Decimal(30), Decimal(0), Decimal(0)),
              (Decimal(30), Decimal(10), Decimal(0)), (Decimal(20), Decimal(10), Decimal(0))]
    wa = [tuple(float(c) for c in v) for v in quad_a]
    wb = [tuple(float(c) for c in v) for v in quad_b]
    assert not actorgraph._footprints_overlap(wa, wb, (0.0, 0.0, 1.0))


def test_footprints_overlap_accepts_genuinely_overlapping_coplanar_faces():
    quad_a = [(Decimal(0), Decimal(0), Decimal(0)), (Decimal(10), Decimal(0), Decimal(0)),
              (Decimal(10), Decimal(10), Decimal(0)), (Decimal(0), Decimal(10), Decimal(0))]
    quad_b = [(Decimal(5), Decimal(5), Decimal(0)), (Decimal(15), Decimal(5), Decimal(0)),
              (Decimal(15), Decimal(15), Decimal(0)), (Decimal(5), Decimal(15), Decimal(0))]
    wa = [tuple(float(c) for c in v) for v in quad_a]
    wb = [tuple(float(c) for c in v) for v in quad_b]
    assert actorgraph._footprints_overlap(wa, wb, (0.0, 0.0, 1.0))


def test_brush_overlap_degenerate_brush_reports_named_error_not_crash():
    from uedcli.model import Brush, Polygon
    bad = Brush(model_name="Model_Bad", polys=[Polygon(vertices=[])])   # no faces at all -> no solid
    a = _brush("A", bad)
    b = _brush("B", cube(64, 64, 64))
    with pytest.raises(actorgraph.DegenerateBrushError, match="A"):
        actorgraph.brush_overlap(a, b)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: FAIL with `AttributeError: ... has no attribute 'brush_overlap'`

- [ ] **Step 3: Write the implementation**

```python
# appended to uedcli/actorgraph.py
from dataclasses import dataclass as _dc  # (already imported above; shown for clarity)


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
            if abs(abs(_dot(na, nb)) - 1.0) > 1e-3:      # not parallel/anti-parallel -> not coplanar
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/actorgraph.py uedcli/tests/test_actorgraph.py
git commit -m "actorgraph: brush-to-brush overlap with matched-face-pair drill-down + area estimate"
```

---

### Task 4: Point-in-brush containment (reusing Task 1's decomposition)

**Files:**
- Modify: `uedcli/actorgraph.py`
- Test: `uedcli/tests/test_actorgraph.py`

**Interfaces:**
- Consumes: `decompose_convex`, `ConvexCell`.
- Produces: `point_in_brush(actor, point: Vec3, *, cache: dict | None = None) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
def test_point_inside_convex_brush():
    a = _brush("A", cube(64, 64, 64), loc=(0, 0, 0))
    assert actorgraph.point_in_brush(a, (0.0, 0.0, 0.0))
    assert not actorgraph.point_in_brush(a, (1000.0, 0.0, 0.0))


def test_point_on_internal_decomposition_boundary_of_l_shape_still_contained():
    # The L-shape from Task 1's test, decomposed into >= 2 cells sharing an INTERNAL wall the
    # decomposition itself introduced (not a real outer surface). A point sitting exactly on that
    # internal wall, well inside the true L volume, must not false-negative from tolerance stacking
    # across two adjacent cells (spec 'Containment reuses the SAME decomposition').
    from uedcli.model import Brush, Polygon
    # (reuse the same L-shape construction as test_l_shaped_brush_decomposes_to_two_or_more_convex_cells)
    ...  # implementer: factor the L-shape builder out of Task 1's test into a shared fixture helper
         # in this file once this task starts, rather than duplicating it a second time.
    # A point on the shared internal wall at x=64 (the L's own inner corner), well inside in y/z:
    point_on_internal_wall = (64.0, 32.0, 0.0)
    assert actorgraph.point_in_brush(a_l_shape, point_on_internal_wall)
```

Note for the implementer: extract the L-shape `Brush` construction from Task 1's
`test_l_shaped_brush_decomposes_to_two_or_more_convex_cells` into a module-level helper
`_l_shaped_brush()` in `test_actorgraph.py` in this task (both tests need the identical fixture) —
do this refactor as part of Step 1, not as a separate cleanup task.

- [ ] **Step 2: Run tests to verify they fail**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: FAIL with `AttributeError: ... has no attribute 'point_in_brush'`

- [ ] **Step 3: Write the implementation**

```python
# appended to uedcli/actorgraph.py

def point_in_brush(actor, point: Vec3, *, cache=None) -> bool:
    """True iff `point` is inside (or within tolerance of the boundary of) ANY ONE of `actor`'s
    decomposed convex cells -- a plain OR over cells, so a point on a cell boundary the
    decomposition itself introduced (shared by two cells of the SAME brush) is safely reported as
    contained by whichever cell's tolerance band it lands in, not double-penalised.
    `cache`: see `decompose_convex`."""
    for cell in decompose_convex(actor, cache=cache):
        if all(_dot(n, point) <= d + _SPLIT_EPS * 10 for n, d in cell.half_spaces):
            return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: PASS. If the internal-boundary test false-negatives, widen the tolerance multiplier in
`point_in_brush`'s half-space check (currently `_SPLIT_EPS * 10`, matching `_cell_vertices`'s own
tolerance) rather than `_SPLIT_EPS` alone — the spec explicitly calls out that internal boundaries
need the SAME generous tolerance as vertex extraction, not the tighter classification epsilon.

- [ ] **Step 5: Commit**

```bash
git add uedcli/actorgraph.py uedcli/tests/test_actorgraph.py
git commit -m "actorgraph: point-in-brush containment reusing the convex decomposition"
```

---

### Task 5: Edge classification (kind + CSG order -> touches/contains/carved_by)

**Files:**
- Modify: `uedcli/actorgraph.py`
- Test: `uedcli/tests/test_actorgraph.py`

**Interfaces:**
- Consumes: `query.csg_is_subtract(actor) -> bool`, `movers.is_mover(actor, index) -> bool`,
  `brush_overlap`, `point_in_brush`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Edge:
      src: str
      dst: str
      relation: str          # "touches" | "contains" | "carved_by"
      directed: bool          # False for touches, True for contains/carved_by
      matched_pair: tuple[int, int] | None   # only for a brush-brush touches edge
      area_estimate: float | None            # only for touches
  def classify_pair(name_a, actor_a, name_b, actor_b, *, order_index, class_index,
                     cache: dict | None = None) -> list[Edge]
  ```
  `order_index: dict[str, int]` — each brush actor's position in `level.order`'s brush subsequence
  (LOWER = earlier/built first); callers build this once per level (Task 6), not per pair.

- [ ] **Step 1: Write the failing tests**

```python
def test_subtract_subtract_touching_gives_undirected_touches():
    a = _brush("A", cube(64, 64, 64), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 64), loc=(64, 0, 0))
    # make_brush_actor defaults csg="add"; both these need csg="subtract" explicitly:
    a2 = make_brush_actor("A", a.brush, location=a.location, csg="subtract")
    b2 = make_brush_actor("B", b.brush, location=b.location, csg="subtract")
    edges = actorgraph.classify_pair("A", a2, "B", b2, order_index={"A": 0, "B": 1}, class_index=None)
    assert len(edges) == 1
    e = edges[0]
    assert e.relation == "touches" and not e.directed
    assert {e.src, e.dst} == {"A", "B"}


def test_subtract_add_earlier_subtract_gives_contains():
    sub = make_brush_actor("Room", cube(64, 64, 64), csg="subtract")
    add = make_brush_actor("Furniture", cube(8, 8, 8), csg="add")
    edges = actorgraph.classify_pair("Room", sub, "Furniture", add,
                                      order_index={"Room": 0, "Furniture": 1}, class_index=None)
    assert len(edges) == 1
    assert edges[0].relation == "contains" and edges[0].directed
    assert edges[0].src == "Room" and edges[0].dst == "Furniture"


def test_subtract_add_later_subtract_gives_carved_by():
    add = make_brush_actor("Wall", cube(64, 64, 64), csg="add")
    sub = make_brush_actor("DoorCutout", cube(8, 8, 32), location=(0, 0, 0), csg="subtract")
    edges = actorgraph.classify_pair("Wall", add, "DoorCutout", sub,
                                      order_index={"Wall": 0, "DoorCutout": 1}, class_index=None)
    assert len(edges) == 1
    assert edges[0].relation == "carved_by" and edges[0].directed
    assert edges[0].src == "Wall" and edges[0].dst == "DoorCutout"


def test_no_overlap_gives_no_edges():
    a = make_brush_actor("A", cube(8, 8, 8), location=(0, 0, 0))
    b = make_brush_actor("B", cube(8, 8, 8), location=(1000, 0, 0))
    edges = actorgraph.classify_pair("A", a, "B", b, order_index={"A": 0, "B": 1}, class_index=None)
    assert edges == []
```

Mover tests (require a real `class_index` resolving `movers.is_mover` — see Task 6's fixture
strategy for wiring a fake/minimal `ClassIndex`; do not skip these, they pin the spec's most
error-prone rule):

```python
def test_mover_touching_add_gives_touches_not_carved_by(mover_class_index):
    add = make_brush_actor("Wall", cube(64, 64, 64), csg="add")
    mover = make_brush_actor("Door", cube(32, 8, 64), location=(0, 28, 0), mover_class="Engine.Mover")
    edges = actorgraph.classify_pair("Wall", add, "Door", mover,
                                      order_index={"Wall": 0, "Door": 1}, class_index=mover_class_index)
    assert len(edges) == 1
    assert edges[0].relation == "touches" and not edges[0].directed


def test_mover_inside_subtract_gives_contains_never_carved_by(mover_class_index):
    room = make_brush_actor("Room", cube(128, 128, 128), csg="subtract")
    mover = make_brush_actor("Door", cube(32, 8, 64), mover_class="Engine.Mover")
    # Door built AFTER Room in level.order -- if the code wrongly treated Door like a later
    # Subtract, this would misclassify as carved_by; it must not.
    edges = actorgraph.classify_pair("Room", room, "Door", mover,
                                      order_index={"Room": 0, "Door": 1}, class_index=mover_class_index)
    assert len(edges) == 1
    assert edges[0].relation == "contains" and edges[0].src == "Room" and edges[0].dst == "Door"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: FAIL with `AttributeError: ... has no attribute 'classify_pair'` (and a `fixture
'mover_class_index' not found` error for the mover tests — add it as a local pytest fixture in
`test_actorgraph.py`, built the same way any other test in this codebase constructs a minimal
`classindex.ClassIndex` for `movers.is_mover` — grep `uedcli/tests/test_eventgraph.py` or
`uedcli/tests/test_movers.py` for the existing pattern and reuse it; do not invent a new one).

- [ ] **Step 3: Write the implementation**

```python
# appended to uedcli/actorgraph.py
from . import query
from .movers import is_mover


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
    a_is_mover = is_mover(actor_a, class_index)
    b_is_mover = is_mover(actor_b, class_index)
    edge_kwargs = dict(matched_pair=ov.matched_pair, area_estimate=ov.area_estimate)

    if a_is_sub and b_is_sub:
        return [Edge(src=name_a, dst=name_b, relation="touches", directed=False, **edge_kwargs)]
    if not a_is_sub and not b_is_sub:      # both Add-or-Mover
        return [Edge(src=name_a, dst=name_b, relation="touches", directed=False, **edge_kwargs)]

    # exactly one is a Subtract: the other is Add-or-Mover
    sub_name, sub_actor = (name_a, actor_a) if a_is_sub else (name_b, actor_b)
    other_name, other_actor = (name_b, actor_b) if a_is_sub else (name_a, actor_a)
    other_is_mover = b_is_mover if a_is_sub else a_is_mover

    if other_is_mover:
        # Movers never carve or get carved -- always `contains`, Subtract -> Mover, regardless of
        # level.order (a Mover generates no CsgOper at all; CSG order is meaningless for it).
        return [Edge(src=sub_name, dst=other_name, relation="contains", directed=True, **edge_kwargs)]

    if order_index[sub_name] < order_index[other_name]:
        return [Edge(src=sub_name, dst=other_name, relation="contains", directed=True, **edge_kwargs)]
    return [Edge(src=other_name, dst=sub_name, relation="carved_by", directed=True, **edge_kwargs)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/actorgraph.py uedcli/tests/test_actorgraph.py
git commit -m "actorgraph: edge classification (touches/contains/carved_by from kind + CSG order)"
```

---

### Task 6: Whole-level graph builder (all actors, multi-edge fan-out, degenerate skip)

**Files:**
- Modify: `uedcli/actorgraph.py`
- Test: `uedcli/tests/test_actorgraph.py`

**Interfaces:**
- Consumes: `classify_pair`, `point_in_brush`, `DegenerateBrushError`; `model.Level`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class ActorGraph:
      node_names: list[str]           # every actor in the level, in level.order (all-actors order)
      edges: list[Edge]
      skipped: list[tuple[str, str]]  # (actor_name, reason) for a degenerate/malformed brush
  def build_graph(level, class_index) -> ActorGraph
  ```

- [ ] **Step 1: Write the failing tests**

```python
def _level(*actors):
    from uedcli.model import Level
    return Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])


def test_build_graph_multi_edge_fanout_add_straddling_two_subtracts(mover_class_index):
    room1 = make_brush_actor("Room1", cube(64, 64, 64), location=(0, 0, 0), csg="subtract")
    room2 = make_brush_actor("Room2", cube(64, 64, 64), location=(64, 0, 0), csg="subtract")
    wall = make_brush_actor("Wall", cube(8, 128, 64), location=(32, 32, 0), csg="add")
    level = _level(room1, room2, wall)
    graph = actorgraph.build_graph(level, mover_class_index)
    contains = [e for e in graph.edges if e.relation == "contains" and e.dst == "Wall"]
    assert {e.src for e in contains} == {"Room1", "Room2"}   # BOTH, not just one


def test_build_graph_multi_edge_fanout_subtract_carving_two_different_adds(mover_class_index):
    # Spec Test Strategy item 3's third fan-out case (the other two are covered above/below): a
    # Subtract carving through two different Adds gets a `carved_by` edge to BOTH, not just one.
    wall1 = make_brush_actor("Wall1", cube(64, 64, 64), location=(0, 0, 0), csg="add")
    wall2 = make_brush_actor("Wall2", cube(64, 64, 64), location=(64, 0, 0), csg="add")   # touches Wall1
    door = make_brush_actor("Door", cube(16, 64, 64), location=(32, 0, 0), csg="subtract")  # straddles both
    level = _level(wall1, wall2, door)   # Door is LATER in level.order than both walls
    graph = actorgraph.build_graph(level, mover_class_index)
    carved_by = [e for e in graph.edges if e.relation == "carved_by" and e.dst == "Door"]
    assert {e.src for e in carved_by} == {"Wall1", "Wall2"}   # BOTH, not just one


def test_build_graph_non_brush_actor_contains_from_every_containing_brush(mover_class_index):
    outer = make_brush_actor("Outer", cube(128, 128, 128), csg="subtract")
    inner = make_brush_actor("Inner", cube(64, 64, 64), csg="subtract")   # nested inside Outer
    from uedcli.model import Actor
    light = Actor(name="Light0", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))
    level = _level(outer, inner, light)
    graph = actorgraph.build_graph(level, mover_class_index)
    contains = [e for e in graph.edges if e.dst == "Light0"]
    assert {e.src for e in contains} == {"Outer", "Inner"}


def test_build_graph_degenerate_brush_is_skipped_not_crashed(mover_class_index):
    from uedcli.model import Brush, Polygon, Actor
    good = make_brush_actor("Good", cube(64, 64, 64), csg="subtract")
    bad_brush = Brush(model_name="Model_Bad", polys=[Polygon(vertices=[])])
    bad = make_brush_actor("Bad", bad_brush, csg="subtract")
    level = _level(good, bad)
    graph = actorgraph.build_graph(level, mover_class_index)
    assert ("Bad", ) in [(n,) for n, _ in graph.skipped] or any(n == "Bad" for n, _ in graph.skipped)
    assert all(e.src != "Bad" and e.dst != "Bad" for e in graph.edges)
    assert "Good" in graph.node_names and "Bad" in graph.node_names   # still a NODE, just no edges
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: FAIL with `AttributeError: ... has no attribute 'build_graph'`

- [ ] **Step 3: Write the implementation**

```python
# appended to uedcli/actorgraph.py
import itertools as _itertools  # already imported above; shown for clarity


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
    participates in). Caught missing in this plan's own self-review: the pre-fix version called
    `decompose_convex` with no cache at all, silently defeating the spec's explicit "computed ONCE
    per brush" performance requirement -- exactly the case `--from`/`--hops` scoping exists to make
    tolerable for a large level, undermined if the underlying detection itself is quadratic."""
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
    for name_a, name_b in _itertools.combinations(ok_brushes, 2):
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/actorgraph.py uedcli/tests/test_actorgraph.py
git commit -m "actorgraph: whole-level graph builder with multi-edge fan-out + degenerate-brush skip"
```

---

### Task 7: `--from`/`--hops` BFS scoping

**Files:**
- Modify: `uedcli/actorgraph.py`
- Test: `uedcli/tests/test_actorgraph.py`

**Interfaces:**
- Consumes: `ActorGraph`, `Edge`.
- Produces:
  ```python
  class GraphError(ValueError):
      pass
  def scoped_edges(graph: ActorGraph, *, seed: str, hops: int | Literal["all"]) -> list[Edge]
  ```
  Raises `GraphError` naming `seed` if it isn't a node in `graph.node_names` (the CLI layer, Task 9,
  catches this the same way every other `*Error(ValueError)` in this codebase is caught — never a
  bare `KeyError`).

- [ ] **Step 1: Write the failing tests**

```python
def test_scoped_edges_one_hop(mover_class_index):
    a = make_brush_actor("A", cube(64, 64, 64), location=(0, 0, 0), csg="subtract")
    b = make_brush_actor("B", cube(64, 64, 64), location=(64, 0, 0), csg="subtract")
    c = make_brush_actor("C", cube(64, 64, 64), location=(128, 0, 0), csg="subtract")   # touches B, not A
    level = _level(a, b, c)
    graph = actorgraph.build_graph(level, mover_class_index)
    edges = actorgraph.scoped_edges(graph, seed="A", hops=1)
    names = {e.src for e in edges} | {e.dst for e in edges}
    assert names == {"A", "B"}   # C is 2 hops away, excluded


def test_scoped_edges_all_hops_reaches_transitively(mover_class_index):
    a = make_brush_actor("A", cube(64, 64, 64), location=(0, 0, 0), csg="subtract")
    b = make_brush_actor("B", cube(64, 64, 64), location=(64, 0, 0), csg="subtract")
    c = make_brush_actor("C", cube(64, 64, 64), location=(128, 0, 0), csg="subtract")
    level = _level(a, b, c)
    graph = actorgraph.build_graph(level, mover_class_index)
    edges = actorgraph.scoped_edges(graph, seed="A", hops="all")
    names = {e.src for e in edges} | {e.dst for e in edges}
    assert names == {"A", "B", "C"}


def test_scoped_edges_unknown_seed_raises_graph_error(mover_class_index):
    a = make_brush_actor("A", cube(64, 64, 64), csg="subtract")
    level = _level(a)
    graph = actorgraph.build_graph(level, mover_class_index)
    with pytest.raises(actorgraph.GraphError, match="Nope"):
        actorgraph.scoped_edges(graph, seed="Nope", hops=1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: FAIL with `AttributeError: ... has no attribute 'scoped_edges'`

- [ ] **Step 3: Write the implementation**

```python
# appended to uedcli/actorgraph.py
from typing import Literal


class GraphError(ValueError):
    pass


def scoped_edges(graph: "ActorGraph", *, seed: str, hops: "int | Literal['all']") -> list["Edge"]:
    """Every edge touching a node reachable from `seed` within `hops` (undirected reachability --
    a `contains`/`carved_by` edge's direction doesn't limit which way a BFS may walk it, only what
    it prints later). `hops == 'all'` is unbounded."""
    if seed not in graph.node_names:
        raise GraphError(f"level graph: no such actor: {seed!r}")
    adjacency: dict[str, list["Edge"]] = {n: [] for n in graph.node_names}
    for e in graph.edges:
        adjacency[e.src].append(e)
        adjacency[e.dst].append(e)

    limit = float("inf") if hops == "all" else hops
    visited = {seed}
    frontier = {seed}
    depth = 0
    kept: list["Edge"] = []
    seen_edges: set[int] = set()
    while frontier and depth < limit:
        next_frontier = set()
        for node in frontier:
            for e in adjacency[node]:
                if id(e) not in seen_edges:
                    seen_edges.add(id(e))
                    kept.append(e)
                other = e.dst if e.src == node else e.src
                if other not in visited:
                    visited.add(other)
                    next_frontier.add(other)
        frontier = next_frontier
        depth += 1
    return kept
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/actorgraph.py uedcli/tests/test_actorgraph.py
git commit -m "actorgraph: --from/--hops BFS scoping"
```

---

### Task 8: Flat text output formatting

**Files:**
- Modify: `uedcli/actorgraph.py`
- Test: `uedcli/tests/test_actorgraph.py`

**Interfaces:**
- Consumes: `list[Edge]`.
- Produces: `format_text(edges: list[Edge]) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
def test_format_text_touches_with_matched_pair_and_area():
    e = actorgraph.Edge(src="Subtract_ConfMain", dst="Subtract_ConfBay", relation="touches",
                        directed=False, matched_pair=(5, 2), area_estimate=112.0)
    line = actorgraph.format_text([e])
    assert line == "Subtract_ConfMain:5 --touches(112.0uu^2)--> Subtract_ConfBay:2"


def test_format_text_touches_no_matched_pair_no_selector():
    e = actorgraph.Edge(src="A", dst="B", relation="touches", directed=False,
                        matched_pair=None, area_estimate=50.0)
    assert actorgraph.format_text([e]) == "A --touches(50.0uu^2)--> B"


def test_format_text_contains_no_size_no_selector():
    e = actorgraph.Edge(src="Room", dst="Add_FrontDesk", relation="contains", directed=True)
    assert actorgraph.format_text([e]) == "Room --contains--> Add_FrontDesk"


def test_format_text_carved_by():
    e = actorgraph.Edge(src="Wall", dst="DoorCutout", relation="carved_by", directed=True)
    assert actorgraph.format_text([e]) == "Wall --carved_by--> DoorCutout"


def test_format_text_multiple_edges_one_per_line():
    e1 = actorgraph.Edge(src="A", dst="B", relation="touches", directed=False)
    e2 = actorgraph.Edge(src="A", dst="C", relation="contains", directed=True)
    assert actorgraph.format_text([e1, e2]) == "A --touches--> B\nA --contains--> C"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: FAIL with `AttributeError: ... has no attribute 'format_text'`

- [ ] **Step 3: Write the implementation**

```python
# appended to uedcli/actorgraph.py

def format_text(edges: list["Edge"]) -> str:
    """Flat, one edge per line, subject-relation-object -- the same one-line-per-edge shape
    `eventgraph.format_text` uses (minus its class annotations; spec 'Output format'). A `touches`
    edge with a matched face pair prints `Name:idx`
    selectors so the line is directly pipeable into `brush relation measure`; a `touches` edge with
    an area estimate but no matched pair prints bare names with the size still shown."""
    lines = []
    for e in edges:
        src = f"{e.src}:{e.matched_pair[0]}" if e.matched_pair is not None else e.src
        dst = f"{e.dst}:{e.matched_pair[1]}" if e.matched_pair is not None else e.dst
        rel = e.relation
        if e.relation == "touches" and e.area_estimate is not None:
            rel = f"touches({e.area_estimate:.4g}uu^2)"
        lines.append(f"{src} --{rel}--> {dst}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_actorgraph -v`
Expected: PASS. If the area formatting (`:.4g`) doesn't match the exact string the first test
asserts (`112.0uu^2`), adjust the test's expected string to whatever `.4g`/`.3f`-equivalent format
you settle on — the important thing is ONE consistent format, not this specific spelling.

- [ ] **Step 5: Commit**

```bash
git add uedcli/actorgraph.py uedcli/tests/test_actorgraph.py
git commit -m "actorgraph: flat one-edge-per-line text output"
```

---

### Task 9: CLI wiring — `uedcli level graph`

**Files:**
- Modify: `uedcli/cli/commands/level.py`
- Modify: `uedcli/cli/parsers/level.py`
- Test: `uedcli/tests/test_cli_level_graph.py`

**Interfaces:**
- Consumes: `actorgraph.build_graph`, `actorgraph.scoped_edges`, `actorgraph.format_text`,
  `actorgraph.GraphError`; `resources.mover_index`; `level_sources.resolve_level_source`; `_tree_flag`.
- Produces: the `uedcli level graph [--from NAME --hops N|all] [--tree KIND/NAME]` CLI surface.

- [ ] **Step 1: Write the failing tests**

```python
# uedcli/tests/test_cli_level_graph.py
"""Follow this codebase's existing CLI-test convention -- grep uedcli/tests/test_cli_event_graph.py
(or the nearest analog) for how a test drives `uedcli.cli.main`/`dispatch` against a scratch project
fixture, and match that pattern exactly rather than inventing a new harness here."""
import pytest


def test_level_graph_no_from_prints_whole_level_graph(scratch_project_with_two_touching_subtracts):
    # implementer: this fixture name is illustrative -- use whatever this codebase's existing CLI
    # tests use to stand up a scratch $UEDCLI_LEVEL project (see test_cli_brush_relation_find.py or
    # similar for the real fixture/helper name and copy its exact setup shape).
    ...


def test_level_graph_from_and_hops_scopes(scratch_project_with_three_chained_subtracts):
    ...


def test_level_graph_hops_without_from_exits_2(scratch_project_with_two_touching_subtracts):
    ...


def test_level_graph_from_without_hops_exits_2(scratch_project_with_two_touching_subtracts):
    ...


def test_level_graph_unknown_from_name_exits_2(scratch_project_with_two_touching_subtracts):
    ...


def test_level_graph_tree_stash_analyzes_stash_not_live_level(scratch_project_with_a_stash):
    ...


def test_level_graph_unresolvable_class_exits_2_not_traceback(scratch_project_with_an_unresolvable_class):
    # `movers.is_mover` can raise `ClassRefError` on ordinary content (found in this plan's own
    # self-review, see "Deviations from the spec's own Module shape section"). `dispatch.py`'s
    # existing top-level `except ClassRefError` handler should degrade this to a clean exit 2 --
    # confirm it actually does for THIS verb, not just assume the generic handler covers it. Match
    # whatever fixture `level doctor`'s own equivalent test already uses for this exact scenario
    # (grep `uedcli/tests/test_cli_level_doctor.py` or its nearest analog) rather than inventing one.
    ...
```

Implementer note: fill in each test body against the REAL scratch-project CLI test fixture this
codebase already uses (do not invent a new one) — this task's Step 1 is explicitly to find and copy
that pattern (likely a `tmp_path`-based project + `subprocess`/direct `dispatch()` call, matching
`uedcli/tests/test_cli_brush_relation_measure.py` or the closest sibling), THEN write these six
tests concretely before moving to Step 2. This is real work, not a placeholder to skip — the plan
names every behavior the tests must cover; only the exact fixture mechanics are left to match the
codebase's existing convention precisely.

- [ ] **Step 2: Run tests to verify they fail**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_cli_level_graph -v`
Expected: FAIL (either a collection error until the test bodies are filled in per the note above, or
`argument graph: invalid choice` once they're real, since the sub-parser doesn't exist yet).

- [ ] **Step 3: Write the implementation**

In `uedcli/cli/parsers/level.py`, inside `register()`, alongside the existing `ldoc`/`_tree_flag(ldoc)`
block:

```python
    lgraph = lsub.add_parser(
        "graph",
        help="print the level's actor connectivity/containment graph — every brush and non-brush "
             "actor as a node, touches/contains/carved_by edges from exact geometry + CSG order")

    def _hops_arg(s: str):
        if s == "all":
            return "all"
        try:
            n = int(s)
        except ValueError:
            raise argparse.ArgumentTypeError(f"--hops must be a positive integer or 'all', got {s!r}")
        if n < 1:
            raise argparse.ArgumentTypeError(f"--hops must be a positive integer or 'all', got {s!r}")
        return n

    lgraph.add_argument("--from", dest="from_actor", default=None, metavar="NAME",
                        help="scope the graph to the neighbourhood reachable from this actor "
                             "(brush or non-brush) within --hops. Omit both --from and --hops for "
                             "the whole level's graph")
    lgraph.add_argument("--hops", type=_hops_arg, default=None, metavar="N|all",
                        help="max hops from --from (required with --from; rejected without it). "
                             "'all' means unbounded — mirrors --top N|all elsewhere in this CLI")
    _tree_flag(lgraph)
```

(`argparse` must already be imported at the top of this file — add `import argparse` if it isn't.)

In `uedcli/cli/commands/level.py`:

```python
    if args.sub == "graph":
        return _level_graph(args, level_sources.resolve_level_source(args))
```

added to `run()`'s if-chain, and:

```python
def _level_graph(args, src) -> int:
    """`level graph` — print the level's actor connectivity/containment graph. Pure, model-side (no
    editor, no native CSG). Default: the whole level's graph, one edge per line to stdout.
    `--from NAME --hops N|all`: scoped to the reachable neighbourhood. No `--json` in v1 (YAGNI —
    CLAUDE.md)."""
    from ... import actorgraph

    from_actor = getattr(args, "from_actor", None)
    hops = getattr(args, "hops", None)
    if from_actor is not None and hops is None:
        raise CommandError("level graph: --hops is required when --from is given "
                            "(N, or 'all' for unbounded)")
    if from_actor is None and hops is not None:
        raise CommandError("level graph: --hops has nothing to scope without --from")

    level = src.load()
    index = resources.mover_index(args, "level graph")
    graph = actorgraph.build_graph(level, index)
    for name, reason in graph.skipped:
        print(f"level graph: skipping {name} — {reason}", file=sys.stderr)

    if from_actor is not None:
        try:
            edges = actorgraph.scoped_edges(graph, seed=from_actor, hops=hops)
        except actorgraph.GraphError as e:
            raise CommandError(str(e))
    else:
        edges = graph.edges

    print(actorgraph.format_text(edges))
    return 0
```

(`sys` must already be imported at the top of `uedcli/cli/commands/level.py` — add if not.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `UEDCLI_SKIP_NATIVE=1 bin/test -k test_cli_level_graph -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add uedcli/cli/commands/level.py uedcli/cli/parsers/level.py uedcli/tests/test_cli_level_graph.py
git commit -m "level graph: CLI wiring (--from/--hops/--tree)"
```

---

### Task 10: Reference docs

**Files:**
- Create: `docs/reference/level/graph.md`
- Modify: `docs/reference/level/README.md`
- Modify: `docs/reference/brush/relation.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Write `docs/reference/level/graph.md`**

Cover, in this codebase's existing reference-doc style (see `docs/reference/brush/relation.md` for
the calibration example — worked examples with real command output, not just a flag list):

- What a node is (every brush + every non-brush actor) and what an edge means
  (`touches`/`contains`/`carved_by`, with the CSG-order rule stated plainly).
- The multi-edge fan-out rule (an actor overlapping several others gets one edge per pair).
- The Mover rule (Add-like, never `carved_by`).
- **The false-positive limitation, verbatim in substance from the spec's "Known limitation"
  section** — a decorative notch/bevel touching both sides of a wall reads as a connection whether
  or not it's a real passage. This MUST land in the shipped doc, not stay implicit — a user reading
  only this page has no other way to learn it.
- The output format (flat, one edge per line; the `Name:idx` drill-down into `brush relation
  measure`; no size on `contains`/`carved_by`).
- `--from`/`--hops`/`--tree` grammar, with a worked example showing the scoped vs. whole-level cases.
- No `--json` in v1 (state it plainly rather than leaving a reader to wonder why every other
  producer verb has one).

- [ ] **Step 2: Add the index row to `docs/reference/level/README.md`**

Insert a `| `level graph [--from NAME --hops N|all] [--tree KIND/NAME]`](graph.md) | print the
level's actor connectivity/containment graph (touches/contains/carved_by), whole-level or scoped |`
row in the existing table, positioned near `doctor` (both are read-only analysis verbs over the
current level).

- [ ] **Step 3: Add the cross-link to `docs/reference/brush/relation.md`**

Add one line near the top (after the existing intro paragraph) or in a "See also" section if one
exists: "For connectivity/containment discovery across MULTIPLE brushes — which brushes touch,
contain, or are carved by which — see [`level graph`](../level/graph.md); `brush relation` answers
questions about a pair of faces you already know."

- [ ] **Step 4: Commit**

```bash
git add docs/reference/level/graph.md docs/reference/level/README.md docs/reference/brush/relation.md
git commit -m "docs: level graph reference page + cross-links"
```

---

## Coordinator's own self-review pass (separate from the drafting pass above), fixed inline

Hand-traced `_build_solid_bsp` on a concrete cube example before accepting this plan: the front/back
branches had their stored half-space tuples SWAPPED (`front` got `(normal, d)` and `back` got
`(_neg(normal), -d)`, backwards from the `ConvexCell` docstring's own "inside iff dot(n,p) <= d"
convention). Traced through: this would have made `_cell_vertices` find zero valid vertices for a
plain cube (the six stored half-spaces would describe the cube's EXTERIOR, whose intersection is
empty), failing `test_convex_brush_decomposes_to_one_cell` — the simplest possible case. Fixed in
Task 1's code block; the fix is verified by the same hand-trace, re-run with the swap applied,
landing on the cube's own natural 6 face planes. SAT (Task 2) turns out to be sign-invariant to this
specific bug (a flipped axis gives the same overlap verdict) — only vertex extraction and point-in-
cell containment were actually broken by it, which is why it's worth tracing by hand rather than
trusting "SAT works so decomposition must be fine."

## Self-Review (performed while writing this plan, fixed inline)

**Spec coverage** — every "What we want" / "Design decisions" / "Test strategy" item in the spec
maps to a task: Nodes/Edges table → Tasks 5-6; multi-edge fan-out → Task 6's tests; no-clustering →
nowhere to build (a non-feature, correctly absent); Detection algorithm (SAT + decomposition +
tolerances + degenerate handling) → Tasks 1-2; Known limitation → Task 10 (must reach the shipped
doc, not stay implicit); Output format → Task 8; CLI grammar → Task 9; the zone/portal-graph and
`brush relation find`-folding "superseded" decisions → correctly built as NOTHING (out of scope,
noted in the spec, not re-litigated here).

**Placeholder scan** — the one deliberate exception is Task 9's CLI test bodies (`...`) and Task 4's
fixture-sharing note, both explicitly flagged as "real work to do in Step 1, not a placeholder to
skip," with the exact reason (this codebase's real scratch-project CLI test fixture must be found
and matched, not invented blind from this plan alone) — consistent with the skill's own guidance
that a task can legitimately start with "find the real pattern" as its first step when the plan
author (this fork) didn't have that fixture's exact shape in hand.

**Type/signature consistency** — `Edge`/`ConvexCell`/`BrushOverlap`/`ActorGraph` are defined once
(Tasks 1, 3, 5, 6) and referenced identically by name in every later task; `classify_pair`'s
`order_index`/`class_index` parameter names match `build_graph`'s construction of them; `hops`'s
`int | Literal["all"]` type is consistent from Task 7 through the CLI layer.

## Deviations from the spec's own "Module shape" section (expected — that section says
"implementation-stage detail, not prescriptive")

- **A class resolver (`resources.mover_index`) is required, and the spec's Module Shape section
  never mentions it.** Determining Mover-ness (`movers.is_mover`) is schema-aware and needs the
  game's `.u` packages — the SAME dependency `level doctor`/`event graph`/`mover key` already have.
  `level graph` inherits this: a missing games config is a clean exit 2 naming the verb (handled
  automatically by reusing `resources.mover_index`), never a silent "every brush is treated as
  static." This is a real, load-bearing dependency the spec's author didn't have in view when writing
  "Module shape," not a design gap — flagging it here per the task's own instruction.
- **`movers.is_mover` can raise `ClassRefError`** on ordinary, realistic content (an unresolvable or
  ambiguous class, a truncated ancestor chain) — `classify_pair`/`build_graph` do not catch this
  themselves, relying on `dispatch.py`'s existing top-level `except ClassRefError` handler (verified:
  it's already there, degrading to a clean exit 2). This is correct behavior, not a gap, but it means
  `level graph` inherits a real failure mode with no test of its own in this plan — Task 9 should add
  one CLI-level test confirming `level graph` exits 2 (not a traceback) on a level containing a brush
  whose class can't be resolved, using whatever fixture `level doctor`'s own equivalent test already
  uses for this (found in review — check `uedcli/tests/test_cli_level_doctor.py` or its nearest
  analog for the pattern before writing a new one).
- **`uedcli/cli/commands/level.py` is confirmed flat** (786 lines exactly), and `_level_graph`
  follows `_level_doctor`'s existing `(args, src)` shape precisely — the spec's own guess about this
  was already correct, no deviation needed there.
- **CSG_Intersect/CSG_Deintersect brushes** aren't in the spec's Subtract-vs-Add table at all (only
  those two named kinds). `query.csg_is_subtract` is a strict boolean (True only for CSG_Subtract),
  so Task 5's `classify_pair` naturally buckets Intersect/Deintersect brushes with the Add-like
  branch — consistent with how the REST of this codebase already treats any non-Subtract CsgOper
  (`preview.py`'s own comment: CsgOper is only ever binned add-vs-subtract elsewhere too). Not a
  gap introduced by this plan; flagging it because the spec itself never considered these two CsgOper
  values explicitly.
- **The spec's `Deltas`/`classify_footprint_2d` "reuse" language was already corrected in the spec
  itself** during its own review pass (it now explicitly says a NEW area function is needed, not a
  call to the existing one) — Task 3 implements exactly that correction, no further deviation.

## Requesting-code-review pass, round 2 (fixed inline, this commit)

An independent reviewer (with real access to this repo's source, unlike the first self-review pass
above) found and I fixed:

- **A second bug in `_build_solid_bsp`'s "span" branch** (Task 1): the front/back polygon fragments
  were routed to the wrong lists, and the front fragment's winding was corrupted by an unnecessary
  `reversed(poly)` call — hand-traced against the L-shaped fixture's own real split sequence, where
  this branch genuinely fires. Fixed; strengthened the L-shape test with known inside/notch points
  (the loose bounding-box assertions alone would not have caught this).
- **An unguarded `ZeroDivisionError`** on a genuinely degenerate (collinear/zero-area, but
  `>= 3`-vertex) face in two `_norm(newell(...))` call sites — the plan's existing degenerate-brush
  test used a *zero-vertex* polygon, which is filtered out before reaching this code, so it never
  exercised this path. Fixed with an explicit length check raising `DegenerateBrushError`, threading
  an actor-name `ref` through `_build_solid_bsp` for the message (it had no actor context before).
- **Missing decomposition memoization**, contradicting the spec's explicit "computed ONCE per brush"
  requirement — `build_graph` was calling `decompose_convex` fresh on every pair a brush appears in
  (O(N²) instead of O(N) for N brushes). Fixed by threading an optional `cache` dict through
  `decompose_convex`/`brush_overlap`/`point_in_brush`/`classify_pair`, owned and populated once by
  `build_graph`.
- **The edge-cross-axis SAT test could not fail even if the edge-cross code were missing entirely**,
  and its underlying fixture (two prisms sharing one extrusion axis) turns out to be STRUCTURALLY
  incapable of ever needing edge-cross axes, regardless of tuning (every edge-cross candidate for two
  shapes on a shared axis reduces to an existing face normal — worked out by hand while fixing this).
  Replaced with an oblique-box fixture on genuinely non-parallel axes, and rewrote the implementer
  guidance to require an independent brute-force distance check (not the SAT code under test, and not
  face-normal-only SAT either) before hardcoding an expected result — this plan's own author could
  not derive exact verified numbers by hand and says so rather than guessing.
- **Added the spec's third named fan-out case** (a Subtract carving two different Adds gets
  `carved_by` to both) as its own Task 6 test — the other two fan-out cases already had one.
- **Noted `movers.is_mover`'s `ClassRefError`** as a real, currently-untested failure mode `level
  graph` inherits (correctly handled by `dispatch.py`'s existing generic handler, but with no
  dedicated test) and added one to Task 9.
- Two minor wording fixes (an overstated "exact shape" match to `eventgraph.format_text`, and a face
  count off by one in a comment).

## Requesting-code-review pass, round 3 (fixed inline, this commit)

A follow-up reviewer verifying round 2's fixes found round 2 had NOT fully closed two of its own
findings, plus one new gap:

- **The zero-normal guard (round 2) had no test actually exercising it** — the plan's existing
  degenerate-brush tests use a zero-VERTEX polygon, filtered out before reaching the guarded code, so
  they prove nothing about it. Added `test_collinear_face_raises_named_error_not_zerodivisionerror`
  (Task 1): a genuine 3-vertex, zero-area (collinear) face, placed first so it's guaranteed to hit the
  exact `newell(plane_poly)` call site the guard protects.
- **The oblique-box fixture for the edge-cross-axis test (round 2) had 4 of its 6 faces wound
  backwards** — confirmed by an independent hand-trace via the cross-product test on each face. An
  inward-pointing face, if ever picked as a splitting plane, inverts front/back for its whole
  subtree — as literally written, `decompose_convex` on this fixture would very likely raise
  `DegenerateBrushError` before the test could even reach the SAT call it exists to exercise. Fixed
  all 6 windings by hand (each re-derived via `edge1 x edge2` against that face's intended outward
  axis) and reworded the implementer note, which had wrongly flagged only 1 of the 4 broken faces as
  needing a second look.
- **New finding: `_matched_face_pair` accepted any COPLANAR poly pair with no check that their
  footprints actually overlap** — two brushes with an unrelated coincidentally-coplanar face pair
  elsewhere (e.g. two rooms sharing a floor height) could be reported as the "exact" matched boundary
  for the `Name:idx` drill-down, contradicting the docstring's own "footprints actually overlap"
  claim. Fixed with `_footprints_overlap` (a projected-bounding-box check in a shared 2-D frame,
  `_plane_basis_2d`) gating candidate selection in `_matched_face_pair`; added direct unit tests for
  both the reject and accept cases.

## Requesting-code-review pass, round 4 (fixed inline, this commit)

Round 3's own verification pass confirmed all of round 3's fixes correct by independently running
the real `texframe.newell` against the fixtures, but surfaced one more real gap, directly adjacent
to round 3's own footprint-overlap fix:

- **`BrushOverlap.area_estimate` reported face A's own FULL area for a matched pair, even when the
  two footprints only PARTIALLY overlap** — contradicting the "exact area" claim once round 3's
  `_footprints_overlap` started correctly allowing partial (not just identical) overlaps through.
  Fixed with `_footprint_overlap_area` (a real 2-D polygon clip — `_clip_2d`/`_ensure_ccw_2d`/
  `_shoelace_area_2d`, mirroring `relation.py`'s `classify_footprint_2d` approach for the same
  problem in a different module) computing the ACTUAL shared area, not either face's own area;
  `_matched_face_pair` now also ranks candidates by this real overlap area rather than face A's
  size. Removed `_shoelace_area_3d`, now dead code. Added a partial-overlap regression test
  (`test_brush_overlap_partial_footprint_reports_actual_shared_area_not_full_face_area`) alongside
  the existing full-overlap one, so both are pinned, not just the symmetric case that happened to
  hide this bug.
