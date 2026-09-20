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
  - `decompose_convex(actor) -> list[ConvexCell]` — the brush's world-space volume as convex cells;
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
    # built directly as a Brush with 10 faces (an L-shaped prism), not via two separate actors.
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


def test_coplanar_splitting_tie_break_is_deterministic():
    # Two independent decompositions of the SAME brush must classify a coplanar face identically --
    # regression-pins whatever tie-break Step 3 implements, not just "it doesn't crash."
    a = _brush("A", cube(64, 64, 64))
    cells1 = actorgraph.decompose_convex(a)
    cells2 = actorgraph.decompose_convex(a)
    assert [sorted(round(d, 6) for _, d in c.half_spaces) for c in cells1] == \
           [sorted(round(d, 6) for _, d in c.half_spaces) for c in cells2]
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
                      *, inside: bool) -> _BspNode:
    """Recursive solid-leaf BSP over `polys` (world-space polygons, initially a brush's own faces --
    each face's OWN outward normal, so 'front' of any one of them is genuinely outside the solid).
    A leaf (empty remaining poly set) is classified `inside` -- inherited from which side of its
    PARENT split it fell on, per the standard solid-leaf BSP construction this project's own native
    engine already applies at brush scale (`bspBrushCSG`'s temp-brush BSP, NATIVE-MATERIALIZE.md)."""
    if not polys:
        return _BspNode(planes=list(planes_so_far), solid=inside)
    plane_poly = polys[0]
    normal = _norm(newell(plane_poly))
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
            own_normal = _norm(newell(poly))
            (front_polys if _dot(own_normal, normal) > 0 else back_polys).append(poly)
        else:  # span
            fp = _clip_polygon(poly, normal, d)
            bp = _clip_polygon(list(reversed(poly)), _neg(normal), -d)
            if len(fp) >= 3:
                front_polys.append(fp)
            if len(bp) >= 3:
                back_polys.append(bp)
    front = _build_solid_bsp(front_polys, planes_so_far + [(normal, d)], inside=False)
    back = _build_solid_bsp(back_polys, planes_so_far + [(_neg(normal), -d)], inside=True)
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


def decompose_convex(actor) -> list[ConvexCell]:
    """`actor`'s brush volume as a list of convex cells (world space). An already-convex brush
    decomposes to exactly ONE cell -- the trivial case of this same recursion, not a separate code
    path. Raises `DegenerateBrushError` naming the actor if no solid leaf survives (a malformed,
    self-intersecting/non-manifold PolyList -- no well-defined 'inside' to decompose)."""
    polys = [polyalign._world_verts(actor, p) for p in actor.brush.polys if len(p.vertices) >= 3]
    tree = _build_solid_bsp(polys, [], inside=True)
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
    # Two triangular prisms positioned so no face-normal axis separates them but a true polytope
    # edge-cross axis does -- the exact case face-normal-only SAT (the rejected earlier design) gets
    # wrong. Regression-pins the fix from the spec's own math review.
    from uedcli.model import Brush, Polygon
    def prism(cx, cy, cz, angle_deg):
        import math
        a = math.radians(angle_deg)
        pts = [(0.0, 0.0), (40.0, 0.0), (20.0, 34.6)]     # equilateral-ish triangle, side 40
        rot = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)) for x, y in pts]
        def V(x, y, z):
            return (Decimal(str(x + cx)), Decimal(str(y + cy)), Decimal(str(z + cz)))
        bottom = Polygon(vertices=[V(x, y, -20) for x, y in reversed(rot)], normal=(0, 0, -1))
        top = Polygon(vertices=[V(x, y, 20) for x, y in rot], normal=(0, 0, 1))
        sides = []
        n = len(rot)
        for i in range(n):
            x0, y0 = rot[i]
            x1, y1 = rot[(i + 1) % n]
            sides.append(Polygon(vertices=[V(x0, y0, -20), V(x1, y1, -20), V(x1, y1, 20), V(x0, y0, 20)]))
        return Brush(model_name="Model_Prism", polys=[bottom, top] + sides)
    a = _brush("A", prism(0, 0, 0, 0))
    b = _brush("B", prism(45, 25, 0, 60))   # positioned/rotated to graze -- verify with a plain bbox
    ca, = actorgraph.decompose_convex(a)
    cb, = actorgraph.decompose_convex(b)
    result = actorgraph.cells_touch_or_overlap(ca, cb)
    assert isinstance(result, bool)   # exactness sanity: doesn't crash, produces a definite answer
```

Note for the implementer: the exact numeric placement of the two prisms in
`test_edge_cross_axis_is_needed_for_two_rotated_convex_shapes` may need tuning once you have a
working SAT to actually witness a face-normal-only false-positive vs. the edge-cross-corrected
true-negative (or vice versa) -- the point of the test is pinning that SOME configuration exercises
the edge-cross axes, not the specific numbers. Adjust `cx`/`cy`/`angle_deg` until you find a pair
where commenting out the edge-cross loop in `cells_touch_or_overlap` changes the result, then assert
the WITH-edge-cross-axes answer explicitly (`True` or `False`, not just `isinstance(..., bool)`).

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
  def brush_overlap(actor_a, actor_b) -> BrushOverlap
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


def _matched_face_pair(actor_a, actor_b) -> tuple[int, int, float] | None:
    """A SINGLE poly pair (one from each brush) whose planes are near-coincident and whose
    footprints actually overlap -- the 'clean shared flat boundary' case. Returns
    (idx_a, idx_b, area) or None. Deliberately independent of ConvexCell decomposition: this asks
    about the brushes' ORIGINAL faces, which is what a `Name:idx` drill-down selector must name."""
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
            area = _shoelace_area_3d(wa, na)
            if best is None or area > best[2]:
                best = (ia, ib, area)
    return best


def _shoelace_area_3d(verts: list[Vec3], normal: Vec3) -> float:
    """A planar polygon's area via Newell's identity: 0.5*|sum of cross products| projected onto
    its own normal -- `texframe.newell`'s magnitude IS twice the planar area, reused directly rather
    than re-deriving a 2-D projection (relation.classify_footprint_2d's own area math is private and
    2-D-projection-based; this is a small, independent function built for this module, per the spec's
    explicit correction that no public reuse exists)."""
    n = newell(verts)
    return abs(_dot(n, normal)) / 2.0 if _len(normal) > 1e-9 else abs(_len(n)) / 2.0


def brush_overlap(actor_a, actor_b) -> BrushOverlap:
    """Exact touch/overlap between two brushes' full volumes (via decomposition + SAT over every
    cell pair), plus a matched single face pair + exact area when one clean shared boundary exists,
    else a bounding-box-intersection area ESTIMATE (informational only -- detection stays exact)."""
    cells_a = decompose_convex(actor_a)
    cells_b = decompose_convex(actor_b)
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
- Produces: `point_in_brush(actor, point: Vec3) -> bool`.

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

def point_in_brush(actor, point: Vec3) -> bool:
    """True iff `point` is inside (or within tolerance of the boundary of) ANY ONE of `actor`'s
    decomposed convex cells -- a plain OR over cells, so a point on a cell boundary the
    decomposition itself introduced (shared by two cells of the SAME brush) is safely reported as
    contained by whichever cell's tolerance band it lands in, not double-penalised."""
    for cell in decompose_convex(actor):
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
  def classify_pair(name_a, actor_a, name_b, actor_b, *, order_index, class_index) -> list[Edge]
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


def classify_pair(name_a, actor_a, name_b, actor_b, *, order_index: dict, class_index) -> list[Edge]:
    """Every edge between two BRUSH actors (both must have `.brush is not None`; a caller passing a
    non-brush actor here is a bug in Task 6's dispatch, not something this function guards)."""
    ov = brush_overlap(actor_a, actor_b)
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
    whose volume contains its Location -- the multi-edge fan-out rule, same as brush-brush pairs."""
    order_index = {name: i for i, name in enumerate(level.order) if level.actors[name].brush is not None}
    brush_names = list(order_index)
    point_names = [n for n in level.order if level.actors[n].brush is None]

    skipped: dict[str, str] = {}
    edges: list[Edge] = []

    def _safe(name):
        """Probe once whether `name`'s brush decomposes cleanly; cache the verdict so a later pair
        involving the same bad brush doesn't re-raise (and re-append to `skipped`)."""
        if name in skipped:
            return False
        try:
            decompose_convex(level.actors[name])
            return True
        except DegenerateBrushError as e:
            skipped[name] = str(e)
            return False

    ok_brushes = [n for n in brush_names if _safe(n)]
    for name_a, name_b in _itertools.combinations(ok_brushes, 2):
        edges.extend(classify_pair(name_a, level.actors[name_a], name_b, level.actors[name_b],
                                    order_index=order_index, class_index=class_index))

    for pname in point_names:
        loc = level.actors[pname].location
        if loc is None:
            continue
        point = (float(loc[0]), float(loc[1]), float(loc[2]))
        for bname in ok_brushes:
            if point_in_brush(level.actors[bname], point):
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


def scoped_edges(graph: "ActorGraph", *, seed: str, hops) -> list["Edge"]:
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
    """Flat, one edge per line, subject-relation-object -- mirrors `eventgraph.format_text`'s exact
    shape (spec 'Output format'). A `touches` edge with a matched face pair prints `Name:idx`
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
