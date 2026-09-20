from decimal import Decimal
import pytest
from uedcli import actorgraph, polyalign
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
