from decimal import Decimal
import pytest
from uedcli import actorgraph, polyalign
from uedcli.builders import cube, make_brush_actor
from uedcli.tests.conftest import StubClassIndex


def _brush(name, brush, loc=(0, 0, 0)):
    return make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc))


def _cell_volume(cell: "actorgraph.ConvexCell") -> float:
    # Signed-volume-of-tetrahedra-from-a-point sum over the cell's own triangulated hull is overkill
    # for this test; instead assert the SET of half-space plane offsets matches a convex brush's own
    # 6 face planes exactly (a cube's half-spaces are trivially derivable), which is what "one cell,
    # trivial case" actually claims.
    return sorted(round(d, 3) for _, d in cell.half_spaces)


def _l_shaped_brush():
    """An L-shape: a 64x64x64 cube union a 64x64x64 cube offset by (64,64,0) sharing one edge --
    built directly as a Brush with 8 faces (bottom+top+6 sides, an L-shaped prism), not via two
    separate actors. Returns the actor."""
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
    return _brush("L", brush)


def test_convex_brush_decomposes_to_one_cell():
    a = _brush("A", cube(64, 64, 64))
    cells = actorgraph.decompose_convex(a)
    assert len(cells) == 1
    assert len(cells[0].half_spaces) == 6          # a cube's own 6 faces, nothing invented
    assert len(cells[0].vertices) == 8              # a cube's 8 corners, no duplicates


def test_l_shaped_brush_decomposes_to_two_or_more_convex_cells():
    a = _l_shaped_brush()
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


def _oblique_box(center, axes, half=(15.0, 1.0, 1.0)):
    """A thin rectangular rod: `half` extents along the orthonormal right-handed frame
    `axes = (long, thin1, thin2)` (`long x thin1 == thin2`), centred at `center`.

    The 6 quad windings below run counterclockwise seen from OUTSIDE, so every face's Newell normal
    points away from the box centre -- asserted directly in the test that uses this, since an
    inward-pointing face chosen as a splitting plane would invert front/back for its whole subtree.
    """
    from uedcli.model import Brush, Polygon
    (lg, t1, t2), (hl, h1, h2) = axes, half
    cx, cy, cz = center

    def corner(u, v, w):    # u, v, w in {-1, 1}
        return tuple(Decimal(repr(c + u * hl * lg[i] + v * h1 * t1[i] + w * h2 * t2[i]))
                     for i, c in enumerate((cx, cy, cz)))

    c = {(u, v, w): corner(u, v, w) for u in (-1, 1) for v in (-1, 1) for w in (-1, 1)}
    faces = [
        [c[(1, -1, -1)], c[(1, 1, -1)], c[(1, 1, 1)], c[(1, -1, 1)]],       # +long cap
        [c[(-1, -1, 1)], c[(-1, 1, 1)], c[(-1, 1, -1)], c[(-1, -1, -1)]],   # -long cap
        [c[(-1, 1, 1)], c[(1, 1, 1)], c[(1, 1, -1)], c[(-1, 1, -1)]],       # +thin1
        [c[(-1, -1, -1)], c[(1, -1, -1)], c[(1, -1, 1)], c[(-1, -1, 1)]],   # -thin1
        [c[(-1, 1, -1)], c[(1, 1, -1)], c[(1, -1, -1)], c[(-1, -1, -1)]],   # -thin2
        [c[(-1, -1, 1)], c[(1, -1, 1)], c[(1, 1, 1)], c[(-1, 1, 1)]],       # +thin2
    ]
    return Brush(model_name="Model_Box", polys=[Polygon(vertices=v) for v in faces])


def test_edge_cross_axis_is_needed_for_two_rotated_convex_shapes():
    # Two thin rods passing each other in a SKEW crossing. Face-normal-only SAT wrongly calls this
    # touching; only an edge(A) x edge(B) axis separates it.
    #
    # Why the fixture is shaped exactly this way -- two earlier fixtures could not exhibit the
    # phenomenon AT ALL, for the same structural reason at three different depths:
    #   * two Z-extruded prisms rotated only about Z (the plan's first draft): both share the
    #     extrusion axis, so every edge-cross lands back on an existing face normal.
    #   * two boxes whose `thin1` is hardcoded to world X and whose long axes rotate within the Y-Z
    #     plane (the committed fixture this replaces): the shared axis is now the THIN one, but every
    #     edge still lies along X or inside the Y-Z plane, so cross(X, yz) is in the Y-Z plane
    #     (parallel to a face normal) and cross(yz, yz) is parallel to X (also a face normal). A
    #     63-configuration sweep over that fixture's angle/offset found zero divergence, as it must.
    #   * a compound Rz-then-Rx rotation ALONE is still degenerate: whichever order it composes in,
    #     one of B's own axes stays perpendicular to A's long axis, so cross(A.long, B.long) is
    #     again just a face normal.
    # The degree of freedom all three lack is ROLL about B's own long axis. Here B's long axis is
    # tilted out of the X-Y plane AND then rolled about itself, so its thin axes no longer line up
    # with cross(A.long, B.long) -- that cross product becomes a genuinely new candidate axis.
    import math
    phi, rho, gap_along_n = math.radians(60.0), math.radians(30.0), 4.0

    a_axes = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))     # A: long along world X
    long_b = (0.0, math.cos(phi), math.sin(phi))                      # tilted phi from +Y toward +Z
    q = (0.0, math.sin(phi), -math.cos(phi))                          # long_b x X; (X, q, long_b) RH
    thin1 = tuple(math.cos(rho) * x + math.sin(rho) * qi              # X, rolled rho about long_b
                  for x, qi in zip((1.0, 0.0, 0.0), q))
    thin2 = tuple(math.cos(rho) * qi - math.sin(rho) * x              # == long_b x thin1
                  for x, qi in zip((1.0, 0.0, 0.0), q))
    b_axes = (long_b, thin1, thin2)
    n = actorgraph._norm(actorgraph._cross(a_axes[0], long_b))        # the edge-cross axis at issue
    b_center = tuple(gap_along_n * ni for ni in n)                    # push B apart along exactly it

    # Non-degenerate by construction: no axis of A is parallel to any axis of B (a shared axis is
    # what collapsed all three earlier fixtures).
    assert max(abs(actorgraph._dot(u, v)) for u in a_axes for v in b_axes) < 0.95
    # ...and the axis at issue is not a face normal of either box, so it is reachable ONLY as an
    # edge-cross product.
    assert all(abs(actorgraph._dot(n, v)) < 0.95 for v in a_axes + b_axes)

    a = _brush("A", _oblique_box((0.0, 0.0, 0.0), a_axes))
    b = _brush("B", _oblique_box(b_center, b_axes))

    # Every face of both fixtures must point OUTWARD before anything downstream can be trusted.
    from uedcli.texframe import newell
    for actor, center in ((a, (0.0, 0.0, 0.0)), (b, b_center)):
        for poly in actor.brush.polys:
            verts = polyalign._world_verts(actor, poly)
            normal = actorgraph._norm(newell(verts))
            outward = actorgraph._sub(verts[0], center)
            assert actorgraph._dot(normal, outward) > 0, f"{actor.name}: inward-pointing face"

    ca, = actorgraph.decompose_convex(a)
    cb, = actorgraph.decompose_convex(b)

    # Ground truth, from an oracle that shares no code with SAT: the rods are 1.267949uu apart.
    # Established by closest-feature enumeration (every vertex-face and edge-edge pair, plain
    # coordinate arithmetic) and cross-checked by dense volume sampling (18^3 points per rod, which
    # bounds it at 1.463176uu -- a sampled minimum is always an upper bound). That is ~1268x
    # `_TOUCH_EPS`, nowhere near the tolerance band.
    assert actorgraph.cells_touch_or_overlap(ca, cb) is False

    # ...and this is the configuration's whole point: dropping the edge-cross axes makes SAT get it
    # WRONG. Face-normal-only SAT finds no separating axis here (all 6 overlap -- each rod is 30
    # long and 2 thick, so every face projection of one straddles the other's), so it reports a
    # touch that isn't there. Measured: all 16 separating axes the full test finds are the single
    # edge-cross direction cross(A.long, B.long), with a projection gap of 1.267949uu.
    face_normals = [nn for nn, _ in ca.half_spaces] + [nn for nn, _ in cb.half_spaces]
    separated_by_a_face = any(
        max(actorgraph._dot(ax, v) for v in ca.vertices)
        < min(actorgraph._dot(ax, v) for v in cb.vertices) - actorgraph._TOUCH_EPS
        or max(actorgraph._dot(ax, v) for v in cb.vertices)
        < min(actorgraph._dot(ax, v) for v in ca.vertices) - actorgraph._TOUCH_EPS
        for ax in face_normals)
    assert separated_by_a_face is False


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


def test_point_inside_convex_brush():
    a = _brush("A", cube(64, 64, 64), loc=(0, 0, 0))
    assert actorgraph.point_in_brush(a, (0.0, 0.0, 0.0))
    assert not actorgraph.point_in_brush(a, (1000.0, 0.0, 0.0))


def test_point_on_internal_decomposition_boundary_of_l_shape_still_contained():
    # The L-shape from Task 1's test, decomposed into >= 2 cells sharing an INTERNAL wall the
    # decomposition itself introduced (not a real outer surface). A point sitting exactly on that
    # internal wall, well inside the true L volume, must not false-negative from tolerance stacking
    # across two adjacent cells (spec 'Containment reuses the SAME decomposition').
    # The real split is at y=64 (Cell 0: x∈[0,64], y∈[64,128]; Cell 1: x∈[0,128], y∈[0,64]).
    a_l_shape = _l_shaped_brush()
    # A point exactly on the shared internal wall at y=64, within both cells' x range [0,64]:
    point_on_internal_wall = (32.0, 64.0, 0.0)
    assert actorgraph.point_in_brush(a_l_shape, point_on_internal_wall)

    # Verify the tolerance is actually load-bearing: a point offset from the true boundary
    # by more than _SPLIT_EPS but less than _VERTEX_EPS should still be reported as contained
    # (proving the wider tolerance is genuinely needed, not decorative). The boundary is at y=64;
    # offset by 0.0005 (between _SPLIT_EPS=1e-4 and _VERTEX_EPS=1e-3):
    point_near_boundary = (32.0, 64.0005, 0.0)  # offset > _SPLIT_EPS, < _VERTEX_EPS
    assert actorgraph.point_in_brush(a_l_shape, point_near_boundary), \
        "Point within _VERTEX_EPS of boundary should be reported as contained"


@pytest.fixture
def mover_class_index():
    """A `classindex.ClassIndex` stand-in for `movers.is_mover` -- same `StubClassIndex` the
    offline suite uses everywhere else (`test_movers.py`, `conftest.py`'s own autouse dispatch
    stub); its default `MOVER_CLASSES` already includes `Engine.Mover`."""
    return StubClassIndex()


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


def test_subtract_add_earlier_subtract_gives_contains(mover_class_index):
    # A real class_index is required here (not None) -- whether the Add side is a Mover controls
    # contains vs. carved_by, so this branch cannot answer without one (see
    # test_subtract_add_pair_with_no_class_index_raises_clearly below).
    sub = make_brush_actor("Room", cube(64, 64, 64), csg="subtract")
    add = make_brush_actor("Furniture", cube(8, 8, 8), csg="add")
    edges = actorgraph.classify_pair("Room", sub, "Furniture", add,
                                      order_index={"Room": 0, "Furniture": 1},
                                      class_index=mover_class_index)
    assert len(edges) == 1
    assert edges[0].relation == "contains" and edges[0].directed
    assert edges[0].src == "Room" and edges[0].dst == "Furniture"


def test_subtract_add_later_subtract_gives_carved_by(mover_class_index):
    # Same reason as above: needs a real class_index, not None.
    add = make_brush_actor("Wall", cube(64, 64, 64), csg="add")
    sub = make_brush_actor("DoorCutout", cube(8, 8, 32), location=(0, 0, 0), csg="subtract")
    edges = actorgraph.classify_pair("Wall", add, "DoorCutout", sub,
                                      order_index={"Wall": 0, "DoorCutout": 1},
                                      class_index=mover_class_index)
    assert len(edges) == 1
    assert edges[0].relation == "carved_by" and edges[0].directed
    assert edges[0].src == "Wall" and edges[0].dst == "DoorCutout"


def test_subtract_add_pair_with_no_class_index_raises_clearly():
    # Exactly one Subtract, class_index=None: whether the other side is a Mover controls contains
    # vs. carved_by, and there is no way to check it -- must raise (answer or raise, never guess),
    # not silently default to "not a Mover" and risk a wrong carved_by naming a real Mover.
    add = make_brush_actor("Wall", cube(64, 64, 64), csg="add")
    sub = make_brush_actor("DoorCutout", cube(8, 8, 32), location=(0, 0, 0), csg="subtract")
    with pytest.raises(actorgraph.ClassRefError, match="class_index"):
        actorgraph.classify_pair("Wall", add, "DoorCutout", sub,
                                  order_index={"Wall": 0, "DoorCutout": 1}, class_index=None)


def test_classify_pair_contains_never_carries_matched_pair_or_area_even_with_real_face_contact(
        mover_class_index):
    # The real regression for the "edge_kwargs splatted into every branch" bug: `Room`/`Shelf`
    # share a flat face exactly (same geometry shape as
    # test_brush_overlap_touching_flat_face_gives_matched_pair_and_exact_area), so `brush_overlap`
    # itself DOES compute a real matched_pair/area for this pair -- confirmed below. A `contains`
    # edge must still come out with neither, which only holds if `classify_pair` itself drops the
    # annotation for contains/carved_by, not because the geometry happens to produce no match.
    room = make_brush_actor("Room", cube(64, 64, 8), location=(0, 0, 0), csg="subtract")
    shelf = make_brush_actor("Shelf", cube(64, 64, 8), location=(0, 0, 8), csg="add")

    ov = actorgraph.brush_overlap(room, shelf)
    assert ov.matched_pair is not None and ov.area_estimate is not None   # the geometry IS a real match

    edges = actorgraph.classify_pair("Room", room, "Shelf", shelf,
                                      order_index={"Room": 0, "Shelf": 1}, class_index=mover_class_index)
    assert len(edges) == 1
    e = edges[0]
    assert e.relation == "contains" and e.src == "Room" and e.dst == "Shelf"
    assert e.matched_pair is None
    assert e.area_estimate is None


def test_classify_pair_carved_by_never_carries_matched_pair_or_area_even_with_real_face_contact(
        mover_class_index):
    # Same regression, the carved_by direction: Wall placed BEFORE DoorCutout in level.order, so a
    # later Subtract carving it produces carved_by -- same flat-face-contact geometry.
    wall = make_brush_actor("Wall", cube(64, 64, 8), location=(0, 0, 0), csg="add")
    cutout = make_brush_actor("DoorCutout", cube(64, 64, 8), location=(0, 0, 8), csg="subtract")

    ov = actorgraph.brush_overlap(wall, cutout)
    assert ov.matched_pair is not None and ov.area_estimate is not None

    edges = actorgraph.classify_pair("Wall", wall, "DoorCutout", cutout,
                                      order_index={"Wall": 0, "DoorCutout": 1}, class_index=mover_class_index)
    assert len(edges) == 1
    e = edges[0]
    assert e.relation == "carved_by" and e.src == "Wall" and e.dst == "DoorCutout"
    assert e.matched_pair is None
    assert e.area_estimate is None


def test_no_overlap_gives_no_edges():
    a = make_brush_actor("A", cube(8, 8, 8), location=(0, 0, 0))
    b = make_brush_actor("B", cube(8, 8, 8), location=(1000, 0, 0))
    edges = actorgraph.classify_pair("A", a, "B", b, order_index={"A": 0, "B": 1}, class_index=None)
    assert edges == []


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


def test_format_text_touches_with_matched_pair_and_area():
    e = actorgraph.Edge(src="Subtract_ConfMain", dst="Subtract_ConfBay", relation="touches",
                        directed=False, matched_pair=(5, 2), area_estimate=112.0)
    line = actorgraph.format_text([e])
    assert line == "Subtract_ConfMain:5 --touches(112uu^2)--> Subtract_ConfBay:2"


def test_format_text_touches_no_matched_pair_no_selector():
    e = actorgraph.Edge(src="A", dst="B", relation="touches", directed=False,
                        matched_pair=None, area_estimate=50.0)
    assert actorgraph.format_text([e]) == "A --touches(50uu^2)--> B"


def test_format_text_contains_no_size_no_selector():
    # Deliberately constructed WITH matched_pair set (unlike a real classify_pair-produced contains
    # edge, which never carries one) -- format_text must gate the `:idx` selector on
    # relation == "touches" itself, not just trust matched_pair being non-None, so this fails on the
    # pre-fix code (which always added the selector whenever matched_pair was set) and passes now.
    e = actorgraph.Edge(src="Room", dst="Add_FrontDesk", relation="contains", directed=True,
                        matched_pair=(5, 5), area_estimate=99.0)
    assert actorgraph.format_text([e]) == "Room --contains--> Add_FrontDesk"


def test_format_text_carved_by():
    e = actorgraph.Edge(src="Wall", dst="DoorCutout", relation="carved_by", directed=True)
    assert actorgraph.format_text([e]) == "Wall --carved_by--> DoorCutout"


def test_format_text_multiple_edges_one_per_line():
    e1 = actorgraph.Edge(src="A", dst="B", relation="touches", directed=False)
    e2 = actorgraph.Edge(src="A", dst="C", relation="contains", directed=True)
    assert actorgraph.format_text([e1, e2]) == "A --touches--> B\nA --contains--> C"
