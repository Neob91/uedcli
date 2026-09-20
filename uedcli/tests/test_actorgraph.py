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


def test_degenerate_actor_transform_raises_named_error_not_polyalignerror():
    # decompose_convex calls polyalign._world_verts, which can raise PolyAlignError if the actor's
    # transform is degenerate (zero/singular scale). This must be caught and re-raised as
    # DegenerateBrushError, never propagated as a bare PolyAlignError (violates the project rule
    # "no exception ever reaches the user"). This test creates an actor with a zero MainScale to
    # trigger the error.
    from uedcli.model import Actor
    from uedcli.transform import FScale
    from decimal import Decimal as D

    cube_brush = cube(64, 64, 64)
    actor = Actor(
        name="DegenerateActor",
        cls="Engine.Brush",
        brush=cube_brush,
        location=(D(0), D(0), D(0)),
        main_scale=FScale(scale=(D(0), D(1), D(1))),  # zero scale on X axis
    )
    with pytest.raises(actorgraph.DegenerateBrushError, match="DegenerateActor"):
        actorgraph.decompose_convex(actor)
