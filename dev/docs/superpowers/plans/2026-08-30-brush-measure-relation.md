# `brush measure relation` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `uedcli brush measure relation <names…>`, a read-only verb that reports the exact
geometric relationship (coplanar/parallel, normals, signed distance, footprint overlap, positional
deltas) between every pair of faces across a named set of brushes, so an agent can verify placement
by reading numbers instead of guessing from a rendered image.

**Architecture:** A new pure-Python domain module (`uedcli/relation.py`) does all the geometry and
builds the report as a plain string, following the existing `doctor.py`/`format_report` split (domain
module never touches stdout). A thin CLI layer (`uedcli/cli/commands/brush/measure.py` +
parser/dispatch registration) resolves brush names to `Level` data, calls the domain module, and
prints the result. No native/Rust code, no live editor, no `--json` in this pass.

**Tech Stack:** Pure Python 3.12, reusing `polyalign.py`'s world-space vertex/normal helpers and
`preview.py`'s area-weighted centroid; pytest for tests (`bin/test`).

**Spec:** `docs/superpowers/specs/2026-08-29-brush-measure-design.md` (this plan implements only the
`brush measure relation` section of that spec — `brush measure alignment` is explicitly out of scope
here per the spec's own "Out of scope / deferred" section, added after owner review).

## Global Constraints

(Copied from the spec verbatim — every task below implicitly must satisfy these.)

- **Never emit a verdict.** No pass/fail, no field that defaults to "should be zero." Every field is
  a measured fact; the calling agent decides if it's a problem.
- **The *search* is always exhaustive; the *report* is capped, transparently.** Every poly of every
  named brush is checked against every poly of every other named brush — nothing is skipped to save
  compute. What's *shown* per brush pair defaults to the top 1 ranked candidate (`--top N`/`--top all`
  overrides this), but the true candidate count is always stated, so capping never silently drops
  information — only compacts it with the fact of compaction always visible.
- **`footprint_2d: "none"` is always a reportable value, never grounds for exclusion** — a `parallel`
  pair with no footprint overlap can be exactly the answer being checked for (e.g. "do these align").
  Only a pair with no plane relationship *at all* is excluded.
- **`distance` is signed**, along the *first-named* face's own world normal: positive = separated,
  negative = interpenetrating, and it reports the actual measured value (not forced to exactly
  `0.000` just because a pair was classified `coplanar` — the tolerance decides the bucket, not the
  printed number).
- **No `--json`, no mutation.** This verb never calls `src.save(...)`; it only reads.
- **`brush measure alignment` is not part of this plan.** Do not add its parser, its module, or any
  code for it — only `brush measure relation`.

---

## File Structure

| File | Responsibility |
|---|---|
| `uedcli/relation.py` (new) | All geometry: plane relationship, 2-D projection, footprint taxonomy, centroid/edge deltas, pairwise orchestration over a named set, disjoint-set computation, and `format_report()` (pure, returns `str`). No I/O. |
| `uedcli/cli/commands/brush/measure.py` (new) | CLI glue: `run(args, src)` → resolves names, loads the `Level`, calls `relation.compute(...)`, prints `relation.format_report(...)`. Mirrors `uedcli/cli/commands/brush/poly.py`'s shape. |
| `uedcli/cli/parsers/brush.py` (modify) | Register `brush measure relation <names…>` under a new `measure` subparser family, next to the existing `poly`/`vertex` families. |
| `uedcli/cli/commands/brush/routes.py` (modify) | Add the `measure` branch to the family dispatch so it reaches the new module. |
| `uedcli/tests/test_relation.py` (new) | Domain-level tests: plane relationship, footprint taxonomy (all six values), deltas, pairwise orchestration, disjoint set, report formatting. Direct function calls, no CLI. |
| `uedcli/tests/test_cli_brush_measure_relation.py` (new) | CLI-level tests: argument parsing, `-` stdin, error cases, end-to-end report via `dispatch.dispatch(...)`. |

---

## Task 1: Plane relationship (coplanar vs. parallel vs. neither)

**Files:**
- Create: `uedcli/relation.py`
- Test: `uedcli/tests/test_relation.py`

**Interfaces:**
- Produces: `uedcli.relation.PlaneRelation` (dataclass: `plane: str` — `"coplanar"` or `"parallel"`;
  `normal_a: tuple[float, float, float]`; `normal_b: tuple[float, float, float]`;
  `distance: float`), and `uedcli.relation.plane_relationship(actor_a, poly_a, actor_b, poly_b) ->
  PlaneRelation | None` (`None` means "neither" — not coplanar, not parallel-facing).

This reuses `polyalign._world_verts`/`polyalign._PARALLEL_EPS`/`polyalign._PLANE_EPS` — the existing,
already-tuned cross-brush (possibly-rotated, different-actor) plane-comparison tolerances — rather
than `geometry.PLANAR_TOL`, which tests a single poly's vertices against its *own* best-fit plane and
isn't built for comparing two *different* polys' planes. `polyalign._coplanar_align`'s own check
rejects opposite-facing normals (it needs same-orientation for texture continuity); this task's check
must accept *both* orientations, since a floor's top face and a leg's bottom face resting on it are
expected to face opposite ways.

- [ ] **Step 1: Write the failing tests**

```python
# uedcli/tests/test_relation.py
from decimal import Decimal
import pytest
from uedcli import relation
from uedcli.builders import cube, make_brush_actor


def _brush(name, brush, loc=(0, 0, 0)):
    return make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc))


def test_coplanar_opposite_normals():
    # Two 64x64x8 slabs stacked with zero gap: A's top face (Z=8) touches B's bottom face (Z=8).
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 8), loc=(0, 0, 8))
    top_a = next(p for p in a.brush.polys if p.item == "Top")
    bottom_b = next(p for p in b.brush.polys if p.item == "Bottom")
    rel = relation.plane_relationship(a, top_a, b, bottom_b)
    assert rel is not None
    assert rel.plane == "coplanar"
    assert rel.distance == pytest.approx(0.0, abs=1e-3)
    assert rel.normal_a[2] == pytest.approx(1.0, abs=1e-6)
    assert rel.normal_b[2] == pytest.approx(-1.0, abs=1e-6)


def test_parallel_separated_positive_distance():
    # Same as above but B is 4uu higher: a real gap, not touching.
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 8), loc=(0, 0, 12))
    top_a = next(p for p in a.brush.polys if p.item == "Top")
    bottom_b = next(p for p in b.brush.polys if p.item == "Bottom")
    rel = relation.plane_relationship(a, top_a, b, bottom_b)
    assert rel is not None
    assert rel.plane == "parallel"
    assert rel.distance == pytest.approx(4.0, abs=1e-3)


def test_parallel_interpenetrating_negative_distance():
    # B is only 4uu above A's top (A is 8 tall): B's bottom is 4uu INSIDE A's solid.
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 8), loc=(0, 0, 4))
    top_a = next(p for p in a.brush.polys if p.item == "Top")
    bottom_b = next(p for p in b.brush.polys if p.item == "Bottom")
    rel = relation.plane_relationship(a, top_a, b, bottom_b)
    assert rel is not None
    assert rel.plane == "parallel"
    assert rel.distance == pytest.approx(-4.0, abs=1e-3)


def test_non_parallel_faces_are_neither():
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 8), loc=(0, 0, 8))
    top_a = next(p for p in a.brush.polys if p.item == "Top")
    side_b = next(p for p in b.brush.polys if p.item == "North")
    assert relation.plane_relationship(a, top_a, b, side_b) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'uedcli.relation'` (or `AttributeError` once
the empty file exists) — confirms the test file is wired up before real code exists.

- [ ] **Step 3: Write `uedcli/relation.py` (plane relationship part)**

```python
"""Cross-brush geometric relationships — `brush measure relation`. Pure Python, model-side, no
editor, no native CSG. See docs/superpowers/specs/2026-08-29-brush-measure-design.md."""
from __future__ import annotations

from dataclasses import dataclass

from . import polyalign

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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /workspace/uedcli && git add uedcli/relation.py uedcli/tests/test_relation.py
git commit -m "brush measure relation: plane relationship (coplanar/parallel/neither, signed distance)"
```

---

## Task 2: Project a poly's world vertices into a shared 2-D (U, V) frame

**Files:**
- Modify: `uedcli/relation.py`
- Test: `uedcli/tests/test_relation.py`

**Interfaces:**
- Consumes: nothing new from Task 1 (independent geometry step).
- Produces: `uedcli.relation.project_to_plane(world_verts: list[Vec3], normal: Vec3, *,
  origin: Vec3 | None = None) -> list[Vec2]` — projects a list of world-space points into an
  arbitrary-but-deterministic orthonormal (U, V) basis for the plane with the given normal.

**Caller contract — get this wrong and every downstream number is silently meaningless, not just
off.** `origin` defaults to `world_verts[0]`, which is fine only when inspecting one poly in
isolation. **A caller comparing two different polys' footprints (`classify_footprint_2d`,
`compute_deltas` in Task 5) MUST pass the same explicit `origin` to both calls.** Each call's
default is *that poly's own* first vertex — an arbitrary point unrelated to the other poly's first
vertex — so two independently-defaulted projections land in unrelated coordinate frames, and any
overlap/containment/delta computed across them measures a meaningless synthetic offset instead of
true relative position. This was not caught by the first draft's own tests (which only checked a
projection against itself) — it was only caught later, hand-verifying a real Leg/Floor pair through
the actual CLI, where an 8×8 corner overlap was silently misreported as one poly fully `contains`-ing
the other. Task 5 must call `project_to_plane(world_a, rel.normal_a)` for the first-named poly, then
`project_to_plane(world_b, rel.normal_a, origin=world_a[0])` for the second — same explicit origin,
derived from the first call.

- [ ] **Step 1: Write the failing tests**

```python
def test_project_to_plane_z_normal_is_xy():
    pts = [(0.0, 0.0, 5.0), (10.0, 0.0, 5.0), (10.0, 20.0, 5.0)]
    uv = relation.project_to_plane(pts, (0.0, 0.0, 1.0))
    assert uv[0] == pytest.approx((0.0, 0.0))
    # second point is 10 world-units from the first, purely in-plane -> distance preserved
    du = uv[1][0] - uv[0][0]
    dv = uv[1][1] - uv[0][1]
    assert (du**2 + dv**2) ** 0.5 == pytest.approx(10.0, abs=1e-6)


def test_project_to_plane_preserves_relative_distances():
    # Any normal: projecting shouldn't change in-plane distances between points already on the plane.
    pts = [(0.0, 0.0, 0.0), (3.0, 4.0, 0.0)]  # 3-4-5 triangle leg in the XY plane
    uv = relation.project_to_plane(pts, (0.0, 0.0, 1.0))
    du, dv = uv[1][0] - uv[0][0], uv[1][1] - uv[0][1]
    assert (du**2 + dv**2) ** 0.5 == pytest.approx(5.0, abs=1e-6)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v -k project_to_plane`
Expected: FAIL, `AttributeError: module 'uedcli.relation' has no attribute 'project_to_plane'`.

- [ ] **Step 3: Add to `uedcli/relation.py`**

```python
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
    if origin is None:
        origin = world_verts[0]
    u_axis, v_axis = _plane_basis(_norm(normal))
    out = []
    for p in world_verts:
        rel = _sub(p, origin)
        out.append((_dot(rel, u_axis), _dot(rel, v_axis)))
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v -k project_to_plane`
Expected: 2 passed. These two tests alone can't catch the shared-origin requirement above (each
only projects one poly against itself) — Task 5's tests are what actually exercise two polys
sharing an origin; don't take "2 passed" here as proof the caller contract is satisfied.

- [ ] **Step 5: Commit**

```bash
cd /workspace/uedcli && git add uedcli/relation.py uedcli/tests/test_relation.py
git commit -m "brush measure relation: project world vertices into a plane's (U, V) frame"
```

---

## Task 3: Footprint taxonomy (`none`/`vertex`/`edge`/`partial`/`contains`/`coincident`)

**Files:**
- Modify: `uedcli/relation.py`
- Test: `uedcli/tests/test_relation.py`

**Interfaces:**
- Consumes: `project_to_plane` (Task 2) to get each poly's 2-D footprint before calling this.
- Produces: `uedcli.relation.classify_footprint_2d(poly_a: list[Vec2], poly_b: list[Vec2]) -> str`,
  returning one of `"none"`, `"vertex"`, `"edge"`, `"partial"`, `"contains_a_in_b"`,
  `"contains_b_in_a"`, `"coincident"`. Both inputs are simple (non-self-intersecting), CCW-wound
  polygons in the same 2-D frame.

This is genuinely new geometry — the codebase has no existing 2-D polygon-vs-polygon overlap
primitive (`clip.py`'s Sutherland-Hodgman kernel is a single 3-D half-space clip built for brush-solid
clipping with cap-vertex tracking, not a flat-polygon intersection loop; reusing it here would mean
fighting its 3-D/cap-vertex assumptions for no real benefit over a small dedicated 2-D version).

- [ ] **Step 1: Write the failing tests**

```python
SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]  # CCW, 10x10 at origin


def _shifted(poly, du, dv):
    return [(x + du, y + dv) for x, y in poly]


def test_footprint_none():
    b = _shifted(SQUARE, 100.0, 0.0)  # far away, no contact at all
    assert relation.classify_footprint_2d(SQUARE, b) == "none"


def test_footprint_vertex():
    b = _shifted(SQUARE, 10.0, 10.0)  # touches SQUARE only at corner (10, 10)
    assert relation.classify_footprint_2d(SQUARE, b) == "vertex"


def test_footprint_edge():
    b = _shifted(SQUARE, 10.0, 0.0)  # butted end-to-end, shares the x=10 edge fully
    assert relation.classify_footprint_2d(SQUARE, b) == "edge"


def test_footprint_partial():
    b = _shifted(SQUARE, 5.0, 5.0)  # overlapping quadrant, neither contains the other
    assert relation.classify_footprint_2d(SQUARE, b) == "partial"


def test_footprint_contains_a_in_b():
    small = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]  # fully inside SQUARE
    assert relation.classify_footprint_2d(small, SQUARE) == "contains_a_in_b"
    assert relation.classify_footprint_2d(SQUARE, small) == "contains_b_in_a"


def test_footprint_coincident():
    assert relation.classify_footprint_2d(SQUARE, list(SQUARE)) == "coincident"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v -k footprint`
Expected: FAIL, `AttributeError: ... has no attribute 'classify_footprint_2d'`.

- [ ] **Step 3: Add to `uedcli/relation.py`**

```python
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


def _shares_vertex(a: list[Vec2], b: list[Vec2]) -> bool:
    return any(
        abs(pa[0] - pb[0]) <= _TOUCH_EPS and abs(pa[1] - pb[1]) <= _TOUCH_EPS
        for pa in a for pb in b
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
    # (A first draft used `>= ... - _TOUCH_EPS` here, which let an endpoint-only touch pass as
    # "edge" -- caught by hand-checking a corner-touch case against the spec's own taxonomy.)
    return min(hi_a, hi_b) - max(lo_a, lo_b) > _TOUCH_EPS


def _shares_edge(a: list[Vec2], b: list[Vec2]) -> bool:
    return any(_segments_overlap(a0, a1, b0, b1) for a0, a1 in _edges(a) for b0, b1 in _edges(b))


def _ensure_ccw(poly: list[Vec2]) -> list[Vec2]:
    return list(reversed(poly)) if _shoelace_area(poly) < 0 else poly


def classify_footprint_2d(poly_a: list[Vec2], poly_b: list[Vec2]) -> str:
    """Re-winds both polys to CCW rather than trusting the caller. A poly's own vertex winding
    faces ITS OWN outward normal, so a coplanar pair with anti-parallel normals -- e.g. a floor's
    top face and a leg's bottom face resting on it, the central motivating case for this whole
    verb -- projects into the SAME (normal_a-based) 2-D frame with OPPOSITE winding. `_clip_2d`'s
    half-plane test assumes its clip polygon is CCW; an un-normalized CW `poly_b` clips against
    the wrong half-plane and silently produces an empty intersection, misreporting a genuine
    overlap as `footprint_2d: none`. A first draft's tests all built both test polys by hand with
    matching (CCW) winding and didn't catch this -- it surfaced only when hand-verifying a real
    Leg/Floor pair through the actual CLI. Any new test for this function should include at least
    one pair built via `plane_relationship`'s actual anti-parallel-normal path, not two polys
    typed in by hand with the same winding."""
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v -k footprint`
Expected: 7 passed (6 tests, `contains_a_in_b` test asserts two directions).

- [ ] **Step 5: Commit**

```bash
cd /workspace/uedcli && git add uedcli/relation.py uedcli/tests/test_relation.py
git commit -m "brush measure relation: 2-D footprint taxonomy classifier"
```

---

## Task 4: Centroid and edge deltas

**Files:**
- Modify: `uedcli/relation.py`
- Test: `uedcli/tests/test_relation.py`

**Interfaces:**
- Consumes: `project_to_plane` (Task 2).
- Produces: `uedcli.relation.Deltas` (dataclass: `centroid_u: float`, `centroid_v: float`,
  `edge_u_label: str`, `edge_u: float`, `edge_v_label: str`, `edge_v: float`) and
  `uedcli.relation.compute_deltas(poly_a: list[Vec2], poly_b: list[Vec2]) -> Deltas`. Both deltas are
  **second-named (`poly_b`) minus first-named (`poly_a`)**, per the spec's stated convention.
  `edge_u_label`/`edge_v_label` are `"U-min"`/`"U-max"`/`"V-min"`/`"V-max"`, tie-break prefers `-min`.

- [ ] **Step 1: Write the failing tests**

```python
from uedcli.preview import _poly_centroid_2d


def test_deltas_centroid_matches_shoelace_centroid():
    a = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    b = [(20.0, 5.0), (30.0, 5.0), (30.0, 15.0), (20.0, 15.0)]
    d = relation.compute_deltas(a, b)
    ca = _poly_centroid_2d(a)
    cb = _poly_centroid_2d(b)
    assert d.centroid_u == pytest.approx(cb[0] - ca[0])
    assert d.centroid_v == pytest.approx(cb[1] - ca[1])


def test_deltas_edge_picks_closer_of_min_or_max():
    a = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    # b's U range [1, 11]: |min-min|=1, |max-max|=1 -> tie -> prefer U-min
    b = [(1.0, 0.0), (11.0, 0.0), (11.0, 10.0), (1.0, 10.0)]
    d = relation.compute_deltas(a, b)
    assert d.edge_u_label == "U-min"
    assert d.edge_u == pytest.approx(1.0)


def test_deltas_edge_picks_max_when_closer():
    a = [(0.0, 0.0), (100.0, 0.0), (100.0, 10.0), (0.0, 10.0)]
    b = [(90.0, 0.0), (98.0, 0.0), (98.0, 10.0), (90.0, 10.0)]  # b's max (98) is 2 from a's max (100)
    d = relation.compute_deltas(a, b)
    assert d.edge_u_label == "U-max"
    assert d.edge_u == pytest.approx(-2.0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v -k deltas`
Expected: FAIL, `AttributeError: ... has no attribute 'compute_deltas'`.

- [ ] **Step 3: Add to `uedcli/relation.py`**

```python
from dataclasses import dataclass as _dataclass  # already imported above; kept for clarity
from .preview import _poly_centroid_2d


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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v -k deltas`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /workspace/uedcli && git add uedcli/relation.py uedcli/tests/test_relation.py
git commit -m "brush measure relation: centroid and edge deltas"
```

---

## Task 5: Pairwise orchestration, ranking, and the `--top` cap

**Files:**
- Modify: `uedcli/relation.py`
- Test: `uedcli/tests/test_relation.py`

**Interfaces:**
- Consumes: `plane_relationship` (Task 1), `project_to_plane` (Task 2), `classify_footprint_2d`
  (Task 3), `compute_deltas` (Task 4).
- Produces:
  - `uedcli.relation.PairFace` (dataclass: `brush_a: str`, `poly_a: int`, `brush_b: str`,
    `poly_b: int`, `plane: PlaneRelation`, `footprint_2d: str`, `deltas: Deltas`).
  - `uedcli.relation.PairGroup` (dataclass: `brush_a: str`, `brush_b: str`, `shown: list[PairFace]`
    — ranked best-first, at most `top` entries — `candidate_count: int` — the TOTAL candidates found
    for this brush pair, before capping).
  - `uedcli.relation.RelationReport` (dataclass: `groups: list[PairGroup]`, `disjoint: list[str]`,
    `brush_count: int`, `pair_count: int`).
  - `uedcli.relation.compute(level, names: list[str], *, top: int | None = 1) -> RelationReport`.
    `top=None` means unlimited (every candidate shown — the `--top all` case). Raises
    `uedcli.relation.RelationError(ValueError)` naming the actor if a named actor has no brush (a
    point actor was passed), the name doesn't exist in `level.actors`, or `top` is not `None` and
    not `>= 1`.

`compute` iterates `itertools.combinations(names, 2)` (preserves input order, so "first-named" in
each pair is always whichever name came first in the CLI args) and, for every such `(name_a,
name_b)`, every `(poly_a_idx, poly_b_idx)` pair across both brushes' polys. **Every candidate with a
plane relationship is collected — `footprint_2d: "none"` is not filtered out** (per the spec: a
`none` result on a genuinely parallel pair can itself be the answer being asked for, e.g. checking
whether a floor marking aligns with a ceiling fixture). Only a brush pair with *zero* candidates
(normals never even parallel) contributes nothing, and if a brush has zero candidates against
*every* other named brush, it lands in `disjoint`.

Within a brush pair, candidates are ranked (best first) by, in order:

1. `footprint_2d` quality: `coincident` > `contains_*` > `partial` > `edge` > `vertex` > `none`.
2. `abs(distance)`, ascending.
3. Centroid-delta magnitude (`√(du² + dv²)`), ascending.
4. `(poly_a, poly_b)` index pair, ascending — deterministic final tie-break; without this, a
   perfectly symmetric case (a beam centered in a wall's thickness) has an undefined winner.

Then only the first `top` (default `1`) survive into `PairGroup.shown`; `candidate_count` always
records the true total, so a caller can tell "1 of 1" from "1 of 12" even though both show one block.

- [ ] **Step 1: Write the failing tests**

```python
def _level(*actors):
    from uedcli.model import Level
    lv = Level()
    for a in actors:
        lv.actors[a.name] = a
    lv.order = [a.name for a in actors]
    return lv


def test_compute_reports_coplanar_pair_and_disjoint_brush():
    a = _brush("Leg", cube(16, 16, 64), loc=(0, 0, 0))
    b = _brush("Floor", cube(200, 200, 8), loc=(-100, -100, -8))
    c = _brush("Lamp", cube(8, 8, 8), loc=(500, 500, 500))
    level = _level(a, b, c)
    report = relation.compute(level, ["Leg", "Floor", "Lamp"])
    assert report.brush_count == 3
    assert report.pair_count == 3  # C(3,2)
    assert report.disjoint == ["Lamp"]
    assert len(report.groups) == 1
    group = report.groups[0]
    assert {group.brush_a, group.brush_b} == {"Leg", "Floor"}
    assert len(group.shown) == 1  # default top=1
    assert group.shown[0].plane.plane == "coplanar"


def test_compute_unknown_name_raises():
    a = _brush("Leg", cube(16, 16, 64))
    level = _level(a)
    with pytest.raises(relation.RelationError):
        relation.compute(level, ["Leg", "NoSuchBrush"])


def test_compute_point_actor_raises():
    from uedcli.model import Actor
    a = _brush("Leg", cube(16, 16, 64))
    light = Actor(name="Light0", cls="Engine.Light", location=(0, 0, 0))
    level = _level(a, light)
    with pytest.raises(relation.RelationError):
        relation.compute(level, ["Leg", "Light0"])


def test_compute_ranks_footprint_quality_over_distance():
    # Two axis-aligned cubes of the same size, touching flush on one axis (Z: contains/coincident,
    # distance 0) and ALSO coincidentally sharing an X-facing plane far along X with zero overlap
    # (footprint: none) -- the "none" candidate must NOT win just because nothing beats distance=0
    # on ties; footprint quality is checked first, and only within the winning quality tier does
    # distance matter.
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))  # flush on top of A
    level = _level(a, b)
    report = relation.compute(level, ["A", "B"], top=None)  # see every candidate for this assertion
    group = report.groups[0]
    assert group.candidate_count > 1  # more than one axis is parallel between two same-size cubes
    best = group.shown[0]
    assert best.footprint_2d in ("coincident", "contains_a_in_b", "contains_b_in_a")


def test_compute_top_caps_shown_but_not_candidate_count():
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    capped = relation.compute(level, ["A", "B"], top=1)
    full = relation.compute(level, ["A", "B"], top=None)
    assert len(capped.groups[0].shown) == 1
    assert capped.groups[0].candidate_count == full.groups[0].candidate_count
    assert len(full.groups[0].shown) == full.groups[0].candidate_count


def test_compute_rejects_invalid_top():
    a = _brush("A", cube(16, 16, 16))
    b = _brush("B", cube(16, 16, 16), loc=(0, 0, 16))
    level = _level(a, b)
    with pytest.raises(relation.RelationError):
        relation.compute(level, ["A", "B"], top=0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v -k compute`
Expected: FAIL, `AttributeError: ... has no attribute 'compute'`.

- [ ] **Step 3: Add to `uedcli/relation.py`**

```python
import itertools


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
                uv_a = project_to_plane(world_a, rel.normal_a)
                uv_b = project_to_plane(world_b, rel.normal_a, origin=world_a[0])  # SAME origin as uv_a -- see Task 2
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v -k compute`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /workspace/uedcli && git add uedcli/relation.py uedcli/tests/test_relation.py
git commit -m "brush measure relation: pairwise orchestration, ranking, top-K cap, disjoint set"
```

---

## Task 6: Report formatting

**Files:**
- Modify: `uedcli/relation.py`
- Test: `uedcli/tests/test_relation.py`

**Interfaces:**
- Consumes: `RelationReport`/`PairGroup` (Task 5).
- Produces: `uedcli.relation.format_report(report: RelationReport) -> str`. Pure function, no I/O —
  matches `doctor.format_report`'s split (domain module returns a string; the CLI layer prints it).

Field labels/nesting/vocabulary here must match the spec's field names exactly (`plane:`, `normals:`,
`distance:`, `footprint_2d:`, `deltas:` → `centroid:`/`edge:`) — the values are simple `key: value`
pairs at each indent level (no cosmetic column-alignment padding attempted; that's a visual nicety
the spec's hand-written examples used, not a semantic requirement, and chasing exact padding would
make this brittle to maintain for no real benefit). A `PairGroup` whose every candidate is `none`
collapses to one summary line instead of a full block (per the spec's "Reporting volume" section) —
that's the header candidate count times capping doesn't actually fix on its own, since a `none`-only
group still gets a full block otherwise. Every other group's header states `shown`-of-`candidate`
count whenever they differ.

- [ ] **Step 1: Write the failing tests**

```python
def test_format_report_matches_expected_shape():
    a = _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4))
    b = _brush("FloorPad", cube(200, 200, 8), loc=(-100, -100, -8))
    level = _level(a, b)
    report = relation.compute(level, ["LegFoot", "FloorPad"])
    text = relation.format_report(report)
    assert "LegFoot <-> FloorPad" in text
    assert "plane: parallel" in text
    assert "footprint_2d: contains" in text
    assert "checked: 2 brushes, 1 pairs, every face" in text
    assert "disjoint:" not in text  # both brushes are involved, nothing left over


def test_format_report_lists_disjoint_brushes():
    a = _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4))
    b = _brush("FloorPad", cube(200, 200, 8), loc=(-100, -100, -8))
    c = _brush("Lamp", cube(8, 8, 8), loc=(500, 500, 500))
    level = _level(a, b, c)
    report = relation.compute(level, ["LegFoot", "FloorPad", "Lamp"])
    text = relation.format_report(report)
    assert "disjoint: {Lamp}" in text
    assert "checked: 3 brushes, 3 pairs, every face" in text


def test_format_report_states_shown_of_candidates_when_capped():
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    report = relation.compute(level, ["A", "B"], top=1)  # default cap
    text = relation.format_report(report)
    total = report.groups[0].candidate_count
    assert total > 1
    assert f"(1 of {total} candidates shown)" in text


def test_format_report_collapses_all_none_group_to_one_line():
    # Two cubes far enough apart on every axis that every candidate is footprint_2d "none".
    a = _brush("Far1", cube(16, 16, 16), loc=(0, 0, 0))
    b = _brush("Far2", cube(16, 16, 16), loc=(1000, 1000, 0))
    level = _level(a, b)
    report = relation.compute(level, ["Far1", "Far2"], top=None)
    assert all(p.footprint_2d == "none" for p in report.groups[0].shown)
    text = relation.format_report(report)
    assert "Far1 <-> Far2: no overlapping face pairs" in text
    assert "plane:" not in text  # collapsed -- no full block fields printed
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v -k format_report`
Expected: FAIL, `AttributeError: ... has no attribute 'format_report'`.

- [ ] **Step 3: Add to `uedcli/relation.py`**

```python
def _fmt(v: float) -> str:
    return f"{v:.3f}uu"


def _fmt_vec(v: Vec3) -> str:
    return f"({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f})"


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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_relation.py -v`
Expected: all tests in the file pass (this also re-runs Tasks 1-5's tests — confirm nothing broke).

- [ ] **Step 5: Commit**

```bash
cd /workspace/uedcli && git add uedcli/relation.py uedcli/tests/test_relation.py
git commit -m "brush measure relation: report formatting"
```

---

## Task 7: CLI wiring (`brush measure relation`)

**Files:**
- Create: `uedcli/cli/commands/brush/measure.py`
- Modify: `uedcli/cli/parsers/brush.py`
- Modify: `uedcli/cli/commands/brush/routes.py`
- Test: `uedcli/tests/test_cli_brush_measure_relation.py`

**Interfaces:**
- Consumes: `relation.compute`, `relation.format_report`, `relation.RelationError` (Tasks 5-6);
  `uedcli.cli.targets.resolve_target_names` (existing, for the `-` stdin convention).
- Produces: the wired CLI verb itself — no further tasks depend on this one.

- [ ] **Step 1: Write the failing CLI-level tests**

```python
# uedcli/tests/test_cli_brush_measure_relation.py
import argparse
from decimal import Decimal

from uedcli import trunk
from uedcli.builders import cube, make_brush_actor
from uedcli.cli import dispatch
from uedcli.model import Level


def _brush(name, brush, loc=(0, 0, 0)):
    return make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc))


def _lexo(i):
    return f"{i:04d}"


def _project(tmp_path, monkeypatch, actors, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={a.name: a for a in actors})
    trunk.write_level(proj / "maps" / name, lvl, {a.name: _lexo(i) for i, a in enumerate(actors)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _ns(proj, names, top=1):
    return argparse.Namespace(
        cmd="brush", sub="measure", measuresub="relation",
        project=str(proj), tree=None, names=names, top=top,
    )


def test_relation_prints_report_and_exits_zero(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4)),
        _brush("FloorPad", cube(200, 200, 8), loc=(-100, -100, -8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["LegFoot", "FloorPad"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert "LegFoot <-> FloorPad" in out
    assert "checked: 2 brushes, 1 pairs, every face" in out


def test_relation_unknown_name_exits_2(tmp_path, monkeypatch, capsys):
    actors = [_brush("LegFoot", cube(16, 16, 4))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["LegFoot", "NoSuchBrush"]))
    assert rc == 2
    assert "NoSuchBrush" in capsys.readouterr().err


def test_relation_stdin_dash_reads_names(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4)),
        _brush("FloorPad", cube(200, 200, 8), loc=(-100, -100, -8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("LegFoot\nFloorPad\n"))
    rc = dispatch.dispatch(_ns(proj, ["-"]))
    assert rc == 0
    assert "LegFoot <-> FloorPad" in capsys.readouterr().out


def test_relation_empty_stdin_is_clean_noop(tmp_path, monkeypatch, capsys):
    actors = [_brush("LegFoot", cube(16, 16, 4))]
    proj = _project(tmp_path, monkeypatch, actors)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
    rc = dispatch.dispatch(_ns(proj, ["-"]))
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_relation_fewer_than_two_names_exits_2(tmp_path, monkeypatch, capsys):
    actors = [_brush("LegFoot", cube(16, 16, 4))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["LegFoot"]))
    assert rc == 2
    assert "at least 2" in capsys.readouterr().err


def test_relation_top_all_shows_every_candidate(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("A", cube(32, 32, 32), loc=(0, 0, 0)),
        _brush("B", cube(32, 32, 32), loc=(0, 0, 32)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["A", "B"], top="all"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "candidates shown)" not in out  # --top all never caps, so no "N of M" note at all


def test_relation_invalid_top_exits_2(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("A", cube(16, 16, 16)),
        _brush("B", cube(16, 16, 16), loc=(0, 0, 16)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["A", "B"], top=0))
    assert rc == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_cli_brush_measure_relation.py -v`
Expected: FAIL — `args.sub == "measure"` isn't routed yet (argparse itself will also reject
`measuresub`/`sub="measure"` once the real parser exists and is exercised via `main()`, but these
tests build the `Namespace` directly and go through `dispatch.dispatch`, so the first failure is
`routes.run` returning `None` / an `AttributeError` inside dispatch, not an argparse error).

- [ ] **Step 3a: Create `uedcli/cli/commands/brush/measure.py`**

```python
"""`brush measure` — pure geometric measurement sub-verbs (no mutation, no verdicts)."""
import sys

from ...targets import resolve_target_names
from ...errors import CommandError
from .... import relation


def run(args, src) -> int:
    if args.measuresub == "relation":
        return _relation(args, src)
    raise CommandError(f"unimplemented brush measure sub-verb: {args.measuresub}")


def _relation(args, src) -> int:
    names = resolve_target_names(args.names)
    if not names:
        return 0
    if len(names) < 2:
        print("brush measure relation needs at least 2 brush names, got 1", file=sys.stderr)
        return 2
    top = None if args.top == "all" else args.top
    level = src.load()
    try:
        report = relation.compute(level, names, top=top)
    except relation.RelationError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(relation.format_report(report))
    return 0
```

`args.top` arrives as whatever the parser's `type=` produced (Step 3b defines a small custom parser
type, `_top_arg`, that already turns `"all"` into the literal string `"all"` and everything else into
a validated positive `int` — so `_relation` only has to special-case the string sentinel, never parse
digits itself).

(Confirmed against the real shipped file: `CommandError` is `...errors` — **three** dots, not four —
`uedcli/cli/errors.py` is one level up from `uedcli/cli/commands/brush/`, not two; the earlier draft
of this plan guessed wrong here. `resolve_target_names` is `...targets` as originally guessed. `relation`
itself is `....` since `uedcli/relation.py` sits a level above `uedcli/cli/` entirely. If you're
implementing this fresh in a different tree layout, still verify against the real file rather than
trusting any of these counts — that's what caught the error here.)

- [ ] **Step 3b: Modify `uedcli/cli/parsers/brush.py`** — add near the `poly`/`vertex` family
  registration (inside `register(sub)`, alongside `poly = bsub.add_parser("poly", ...)`):

```python
    def _top_arg(s: str):
        if s == "all":
            return "all"
        try:
            n = int(s)
        except ValueError:
            raise argparse.ArgumentTypeError(f"--top must be a positive integer or 'all', got {s!r}")
        if n < 1:
            raise argparse.ArgumentTypeError(f"--top must be a positive integer or 'all', got {s!r}")
        return n

    measure = bsub.add_parser("measure", help="pure geometric measurement (no mutation)")
    msub = measure.add_subparsers(dest="measuresub", required=True)
    mrel = msub.add_parser(
        "relation",
        help="report the exact geometric relationship between every pair of faces across "
             "2+ named brushes (plane, normals, distance, footprint_2d overlap, deltas)")
    mrel.add_argument(
        "names", nargs="+",
        help="brush actor names to compare, or '-' to read a newline name list from stdin")
    mrel.add_argument(
        "--top", type=_top_arg, default=1,
        help="max ranked candidate poly-pairs to show per brush pair (default 1); "
             "'all' shows every qualifying pair with no cap")
```

(`argparse` is already imported at the top of `uedcli/cli/parsers/brush.py` for the rest of the file's
subparsers — confirm this before assuming it needs a new import.)

- [ ] **Step 3c: Modify `uedcli/cli/commands/brush/routes.py`** — add the `measure` branch to the
  existing `if/elif` chain in `run(args)`:

```python
    elif sub == "measure":
        from . import measure as feature
```

(placed alongside the existing `poly`/`vertex`/edit branches, before the `else: return None` — do
not add a `level_sources.resolve_level_source` call twice; the existing code below the `if/elif`
chain already does `src = level_sources.resolve_level_source(args); return feature.run(args, src)`
for every branch, so `measure.run(args, src)` receives `src` the same way `poly.run`/`vertex.run` do.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd /workspace/uedcli && bin/test uedcli/tests/test_cli_brush_measure_relation.py -v`
Expected: 7 passed.

- [ ] **Step 4b: Regenerate the parser characterization baseline**

This repo freezes the whole `argparse` tree (help text, the subcommand structure) in
`uedcli/tests/fixtures/parser_baseline/`, checked by `test_parser_baseline.py`, so a later refactor
can't silently change CLI behavior. Adding a brand-new subcommand is exactly the kind of change that
baseline is meant to catch — **this step is not optional, and it isn't mentioned anywhere else in
this plan**, which is itself a gap worth knowing about: it wasn't in the original task breakdown and
was only discovered by actually running the full suite and reading the failure.

Run: `cd /workspace/uedcli && UEDCLI_SKIP_NATIVE=1 bin/test uedcli/tests/test_parser_baseline.py -v`
Expected: FAILS at this point — `test_help_screens_match_baseline` (and possibly others) diff against
the old, `relation`-less baseline. That failure is expected and correct, not a bug to chase.

Regenerate deliberately (never let a test silently rewrite its own fixture on failure — this project's
convention, stated in `parser_baseline.py`'s own docstring, is explicit-only regeneration):

```bash
cd /workspace/uedcli && python3 -m uedcli.tests.parser_baseline
git add uedcli/tests/fixtures/parser_baseline/
bin/test uedcli/tests/test_parser_baseline.py -v   # confirm it's green now
```

Before committing the regenerated fixture, skim the diff (`git diff --cached
uedcli/tests/fixtures/parser_baseline/`) — it should show only the new `brush measure relation`
entries appearing, nothing about any other existing command changing. If anything unrelated shows up
as different, stop and figure out why before proceeding; that would mean this work accidentally
changed something else's CLI behavior.

- [ ] **Step 5: Run the full suite**

Run: `cd /workspace/uedcli && UEDCLI_SKIP_NATIVE=1 bin/test uedcli -q`
Expected: all pass, no regressions in unrelated tests. If you see failures in `test_preview_faces.py`
about `uedcli_native extension is not built`, that's a pre-existing environment limitation (the native
Rust extension isn't compiled in every sandbox) — confirm it's pre-existing by checking that none of
your commits touch `preview.py`/`preview_native.py`/`test_preview_faces.py` (`git diff --stat
<base>..HEAD`), not by assuming and moving on.

- [ ] **Step 6: Manual smoke test through the real CLI**

```bash
cd /workspace/uedcli
export UEDCLI_PROJECT=/tmp/relation-smoke
mkdir -p "$UEDCLI_PROJECT/maps/smoke"
echo 'game = "deusex"' > "$UEDCLI_PROJECT/uedcli.toml"
export UEDCLI_LEVEL=smoke
bin/uedcli level create smoke 2>/dev/null || true
bin/uedcli brush build cube --width 64 --breadth 64 --height 8 --at 0,0,0 | bin/uedcli actor add -
bin/uedcli brush build cube --width 200 --breadth 200 --height 8 --at 0,0,-8 | bin/uedcli actor add -
bin/uedcli actor find
```

(There is no `brush build box` shape — the real name is `cube`, with `--width`/`--breadth`/`--height`,
not `--size`; a first draft of this plan got this wrong from memory instead of checking
`bin/uedcli brush build cube --help`. Also note `--at` is the brush's geometric CENTER on every axis,
not a corner — both boxes above are centered on the same X/Y so the small one's footprint is fully
`contains`-ed by the large one's; off-centering the second box, e.g. to `-100,-100,-8`, would instead
produce `footprint_2d: partial`, which is still a valid, real report but not what this step is meant
to demonstrate.)

Note the two allocated names printed by `actor add -` (e.g. `Cube_ab12cd`, `Cube_ef34gh` — real names
are randomized, not `Brush0`/`Brush1`), then run:

```bash
bin/uedcli brush measure relation <first-name> <second-name>
```

Expected: a report block showing `plane: coplanar`, `footprint_2d: contains` (the small box's bottom
face sits inside the big box's top face's footprint), and a trailing `checked: 2 brushes, 1 pairs,
every face` line. Read the actual output and confirm it's sensible before calling this task done —
an automated test passing is not the same as the real CLI producing a sane report end to end. Also
try the same command with `--top all` and confirm the output expands to more candidates (two same-
size-ish cubes are parallel on more than one axis).

- [ ] **Step 7: Commit**

```bash
cd /workspace/uedcli && git add uedcli/cli/commands/brush/measure.py uedcli/cli/parsers/brush.py \
  uedcli/cli/commands/brush/routes.py uedcli/tests/test_cli_brush_measure_relation.py
git commit -m "brush measure relation: CLI wiring"
```

---

## Self-Review Notes (from writing this plan)

- **Spec coverage:** every field in the spec's `relation` section (`plane`, `normals`, `distance`,
  `footprint_2d`, `deltas`, `disjoint`, `checked`, `--top`) has a producing task above. `--json` and
  `brush measure alignment` are explicitly out of scope per the spec's own deferred section and the
  owner's later scope correction — correctly absent from every task.
- **Note already reflected in the spec (not a plan-vs-spec deviation anymore):** the coplanarity
  tolerance is `polyalign._PARALLEL_EPS`/`_PLANE_EPS`, not `geometry.PLANAR_TOL` — this was caught
  while writing this plan and the spec has since been corrected to match, so Task 1 and the spec now
  agree; no outstanding discrepancy here.
- **`footprint_2d == "none"` is always reported, never filtered** — an earlier draft of this plan
  excluded it for `parallel` pairs; that was reversed after discussion (a `none` result on a pair the
  agent specifically asked about, e.g. a floor/ceiling alignment check, IS the useful answer). Task 5
  reflects the final rule: only a pair with no plane relationship *at all* (`plane_relationship`
  returns `None`) is excluded.
- **The ranking/cap design (Task 5) has one deliberately accepted, documented limitation**, not an
  oversight: an independent Opus review found that footprint-quality-first ranking can be misled by
  interpenetrating brushes, where several axes tie at `distance≈0` for incidental reasons (matching
  heights) and the ranking can't distinguish that from the axis that actually describes the
  interpenetration. A fix (rank by relative overlap area before distance) was designed and reviewed
  but intentionally not implemented for v1 — see the spec's "Design decisions" entry on this. Do not
  silently add the area-based fix while implementing this plan; if Task 5's tests or the five-agent
  build-and-check exercise (run after this plan, per the session's own next step) turn up a real case
  that needs it, that's a plan revision to make deliberately, with its own tests, not a mid-task
  addition.
- **Type consistency checked:** `PlaneRelation`, `Deltas`, `PairFace`, `PairGroup`, `RelationReport`
  field names are used identically across Tasks 1–7 (no renamed fields between where a task defines a
  dataclass and where a later task consumes it) — in particular, `report.pairs` from the pre-ranking
  draft is gone everywhere; every task and test now uses `report.groups[i].shown`/`.candidate_count`.
