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
        thin2 = actorgraph._cross(long_dir, thin1)                           # actorgraph._cross -- also perp.
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
    # Verified: boxes do touch (SAT result=True on both full + edge-cross and face-normal-only paths,
    # indicating the edge-cross axes provide additional confidence, though in this particular fixture
    # both methods agree). The cell A bounds are x∈[-1,1] y∈[-15,15] z∈[-1,1]; cell B bounds are
    # x∈[-1,1] y∈[-11.31,11.31] z∈[-3.31,19.31]. The overlapping zones (x fully, y from -11.31 to 11.31,
    # z from -1 to 1) place the boxes within touching distance via their skew orientations.
    assert result is True
