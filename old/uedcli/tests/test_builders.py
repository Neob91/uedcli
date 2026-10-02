from collections import Counter

import pytest

from uedcli.builders import (
    cube, cylinder, cone, sheet, staircase, spiral_staircase, make_brush_actor,
    PF_TWOSIDED, PF_NOTSOLID, PF_SEMISOLID,
    _newell, _centroid, _dot,
)
from uedcli.geometry import GeometryError, validate_brush
from uedcli.emit import emit_actor, snap
from uedcli.model import Brush, parse_t3d


def _is_closed(brush):
    """A closed solid: every undirected edge is shared by exactly two faces."""
    edges = Counter()
    for p in brush.polys:
        ring = [tuple(snap(c) for c in v) for v in p.vertices]
        n = len(ring)
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            edges[tuple(sorted((a, b)))] += 1
    return all(count == 2 for count in edges.values()) and bool(edges)


def _winds_outward(brush, center=(0.0, 0.0, 0.0)):
    """For a convex solid centered at `center`, every face's winding normal must
    point away from the center."""
    for p in brush.polys:
        nw = _newell(p.vertices)
        radial = tuple(_centroid(p.vertices)[i] - center[i] for i in range(3))
        if _dot(nw, radial) <= 0:
            return False
    return True


# --- cube --------------------------------------------------------------------

def test_cube_valid_closed_and_outward():
    b = cube(256, 128, 64, texture="T")
    validate_brush(b)
    assert len(b.polys) == 6
    assert _is_closed(b)
    assert _winds_outward(b)


def test_cube_bounds_centered():
    b = cube(200, 100, 60)
    xs = [v[0] for p in b.polys for v in p.vertices]
    zs = [v[2] for p in b.polys for v in p.vertices]
    assert max(xs) == 100 and min(xs) == -100
    assert max(zs) == 30 and min(zs) == -30


def test_cube_texture_vectors_nondegenerate():
    b = cube(128, 128, 128)
    for p in b.polys:
        assert sum(c * c for c in p.texture_u) > 0.5
        assert sum(c * c for c in p.texture_v) > 0.5


def test_cube_faces_have_no_pan_by_default():
    # A freshly built face must NOT carry an explicit (0, 0) pan -- the editor's own re-export
    # omits a zero pan as the implicit default, so an explicit (0, 0) would break canonical-hash
    # equality between a never-materialized brush and its first materialize (2026-06-21).
    b = cube(128, 128, 128)
    assert all(p.pan is None for p in b.polys)


# --- cylinder ----------------------------------------------------------------

def test_cylinder_valid_closed_and_facecount():
    b = cylinder(128, 64, sides=8)
    validate_brush(b)
    assert len(b.polys) == 8 + 2          # 8 sides + 2 caps
    assert _is_closed(b)
    assert _winds_outward(b)


def test_cylinder_height_extent():
    b = cylinder(200, 50, sides=6)
    zs = [v[2] for p in b.polys for v in p.vertices]
    assert max(zs) == 100 and min(zs) == -100


def test_cylinder_too_few_sides_raises():
    with pytest.raises(GeometryError):
        cylinder(100, 50, sides=2)


# --- cone --------------------------------------------------------------------

def test_cone_valid_closed_and_facecount():
    b = cone(128, 64, sides=6)
    validate_brush(b)
    assert len(b.polys) == 6 + 1          # 6 slope faces + 1 base
    assert _is_closed(b)
    assert _winds_outward(b)


def test_cone_has_single_apex():
    b = cone(100, 40, sides=5)
    apexes = {tuple(v) for p in b.polys for v in p.vertices if v[2] == 50}
    assert apexes == {(0.0, 0.0, 50.0)}


# --- cylinder/cone --axis orientation ----------------------------------------

def _spans(brush):
    """(x, y, z) bounding-box extents of a brush's vertices."""
    def span(i):
        cs = [float(v[i]) for p in brush.polys for v in p.vertices]
        return max(cs) - min(cs)
    return (span(0), span(1), span(2))


def test_cylinder_default_axis_is_a_plus_z_prism():
    # sides=8 gives a symmetric cross-section (100×100), so the +Z prism spans (100, 100, height).
    assert _spans(cylinder(200, 50, sides=8)) == (100.0, 100.0, 200.0)


@pytest.mark.parametrize("axis,want", [
    ("z", (100.0, 100.0, 200.0)),
    ("x", (200.0, 100.0, 100.0)),
    ("y", (100.0, 200.0, 100.0)),
])
def test_cylinder_axis_runs_the_long_axis_along_that_world_axis(axis, want):
    assert _spans(cylinder(200, 50, sides=8, axis=axis)) == want


@pytest.mark.parametrize("axis,want", [
    ("z", (100.0, 100.0, 200.0)),
    ("x", (200.0, 100.0, 100.0)),
    ("y", (100.0, 200.0, 100.0)),
])
def test_cone_axis_runs_the_long_axis_along_that_world_axis(axis, want):
    assert _spans(cone(200, 50, sides=8, axis=axis)) == want


def test_cylinder_axis_remaps_every_vertex_through_the_sweep_frame():
    # The right-handed frame: z is identity (u,v,w)→(X,Y,Z); x maps (u,v,w)→(w,u,v) and y→(v,w,u).
    # So each x-prism vertex is its z-prism vertex rolled (X,Y,Z)→(Z,X,Y), and each y-prism vertex
    # (X,Y,Z)→(Y,Z,X) — exact, since only multiplies by 1.0/0.0 are involved. Full-geometry pin.
    zb = cylinder(128, 64, sides=8)
    xb = cylinder(128, 64, sides=8, axis="x")
    yb = cylinder(128, 64, sides=8, axis="y")
    for pz, px, py in zip(zb.polys, xb.polys, yb.polys):
        for (vx, vy, vz), vex, vey in zip(pz.vertices, px.vertices, py.vertices):
            assert vex == (vz, vx, vy)
            assert vey == (vy, vz, vx)


def test_cone_axis_remaps_every_vertex_through_the_sweep_frame():
    zb = cone(160, 96, sides=6)
    xb = cone(160, 96, sides=6, axis="x")
    yb = cone(160, 96, sides=6, axis="y")
    for pz, px, py in zip(zb.polys, xb.polys, yb.polys):
        for (vx, vy, vz), vex, vey in zip(pz.vertices, px.vertices, py.vertices):
            assert vex == (vz, vx, vy)
            assert vey == (vy, vz, vx)


@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_cylinder_axis_stays_closed_and_outward(axis):
    b = cylinder(128, 64, sides=8, axis=axis)
    validate_brush(b)
    assert _is_closed(b)
    assert _winds_outward(b)


@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_cone_axis_stays_closed_and_outward(axis):
    b = cone(128, 64, sides=6, axis=axis)
    validate_brush(b)
    assert _is_closed(b)
    assert _winds_outward(b)


def test_cylinder_rejects_a_bad_axis_naming_it():
    with pytest.raises(GeometryError, match="q"):
        cylinder(100, 50, sides=8, axis="q")


def test_cone_rejects_a_bad_axis_naming_it():
    with pytest.raises(GeometryError, match="q"):
        cone(100, 50, sides=8, axis="q")


# --- sheet -------------------------------------------------------------------

def test_sheet_single_face_twosided_nonsolid():
    b = sheet(256, 128, plane="xz")
    validate_brush(b)
    assert len(b.polys) == 1
    assert b.polys[0].flags & PF_TWOSIDED
    assert b.polys[0].flags & PF_NOTSOLID


def test_sheet_plane_orientation():
    b = sheet(100, 100, plane="xy")
    assert all(v[2] == 0 for p in b.polys for v in p.vertices)


def test_sheet_bad_plane_raises():
    with pytest.raises(GeometryError):
        sheet(100, 100, plane="zz")


def test_sheet_extra_flags_or_onto_defaults():
    from uedcli.query import PF_NAMES
    bit = {name: b for b, name in PF_NAMES}
    b = sheet(256, 128, plane="xz", extra_flags=["portal", "translucent"])
    validate_brush(b)
    f = b.polys[0].flags
    # defaults preserved AND the two requested flags OR-ed on top
    assert f & PF_TWOSIDED and f & PF_NOTSOLID
    assert f & bit["portal"] and f & bit["translucent"]


def test_sheet_extra_flags_reject_unknown_name():
    with pytest.raises(ValueError):
        sheet(100, 100, extra_flags=["bogus"])


# --- staircase (linear) — ONE non-convex brush (decisions 2026-07-21 12:06) ------

def _item_hist(brush):
    from collections import Counter
    return Counter(p.item for p in brush.polys)


def test_staircase_is_one_nonconvex_brush():
    n = 12
    b = staircase(n, depth=32, rise=16, breadth=384)
    assert isinstance(b, Brush)                    # ONE brush, not a list of boxes
    validate_brush(b)                              # every face convex, planar, non-degenerate
    assert len(b.polys) == 2 + 4 * n
    # Base + back + per-step Step/Rise + tiled Side strips (UED LinearStairBuilder taxonomy).
    assert _item_hist(b) == {"Base": 1, "back": 1, "Step": n, "Rise": n, "Side": 2 * n}


def test_staircase_corner_pivot_and_bounds():
    b = staircase(12, depth=32, rise=16, breadth=384)
    xs = [v[0] for p in b.polys for v in p.vertices]
    ys = [v[1] for p in b.polys for v in p.vertices]
    zs = [v[2] for p in b.polys for v in p.vertices]
    assert (min(xs), max(xs)) == (0, 384)         # corner pivot, spans 0..steps*depth
    assert (min(ys), max(ys)) == (0, 384)
    assert (min(zs), max(zs)) == (0, 192)         # at/above the floor, top at steps*rise


def test_staircase_treads_ascend_from_one_rise():
    b = staircase(4, depth=32, rise=16, breadth=64)
    # each Step face (a tread) sits at (k+1)*rise — first tread one rise above the floor,
    # ascending. Step faces are horizontal, so every vertex is at the tread z.
    tread_z = sorted(p.vertices[0][2] for p in b.polys if p.item == "Step")
    assert tread_z == [16, 32, 48, 64]


def test_staircase_sides_are_tiled_per_step_columns():
    n = 5
    b = staircase(n, depth=40, rise=20, breadth=80)
    sides = [p for p in b.polys if p.item == "Side"]
    assert len(sides) == 2 * n                    # one convex strip per step column, per side
    # each -Y strip spans a single depth column, from the floor up to its own tread top
    minus_y = sorted((min(v[0] for v in p.vertices), max(v[0] for v in p.vertices),
                      min(v[2] for v in p.vertices), max(v[2] for v in p.vertices))
                     for p in sides if all(v[1] == 0 for v in p.vertices))
    assert minus_y == [(k * 40, (k + 1) * 40, 0, (k + 1) * 20) for k in range(n)]


def test_staircase_zero_steps_raises():
    with pytest.raises(GeometryError):
        staircase(0, 32, 16, 64)


def test_staircase_passes_doctor_clean():
    """The single non-convex staircase brush passes `level doctor` with ZERO error findings.
    This is now coupled to Part B: the T-junction-aware `check_watertight` must accept its
    per-step Side/tread/base T-junctions, and every face must be convex/planar/non-degenerate."""
    from uedcli.doctor import run_doctor, Severity
    from uedcli.tests.conftest import StubClassIndex
    from uedcli.model import Level
    from decimal import Decimal
    b = staircase(8, depth=48, rise=24, breadth=96, texture="DefaultTexture")
    a = make_brush_actor("Staircase", b, location=(Decimal(0), Decimal(0), Decimal(0)))
    findings = run_doctor(Level(actors={a.name: a}, order=[a.name]), StubClassIndex())
    errors = [f for f in findings if f.severity is Severity.ERROR]
    assert errors == [], f"staircase tripped doctor: {[(f.category, f.message) for f in errors]}"


def test_builder_matches_ued_linear_stair_taxonomy(fixtures):
    """Builder-vs-UED equivalence: our single-brush `staircase` reproduces UnrealEd's own
    `LinearStairBuilder` face taxonomy — one brush of Base + back + per-step Step/Rise + tiled
    Side strips, `2 + 4n` faces — captured as Brush5 in level_small.t3d (12 steps, depth 32,
    rise 16, breadth 384). Pins BOTH the reference engine fact (the native bspBrushCSG port must
    reproduce UED builds) AND that our builder now equals it (dev/docs/direction/generators.md 2026-07-21 12:06 UTC)."""
    n = 12
    ued = parse_t3d((fixtures / "level_small.t3d").read_text(encoding="latin1"))
    ued_stair = ued.actors["Brush5"].brush
    assert _item_hist(ued_stair) == {"Base": 1, "back": 1, "Step": n, "Rise": n, "Side": 2 * n}
    assert len(ued_stair.polys) == 2 + 4 * n

    ours = staircase(n, depth=32, rise=16, breadth=384)
    assert _item_hist(ours) == _item_hist(ued_stair)      # same face taxonomy as UED
    assert len(ours.polys) == len(ued_stair.polys)


# --- spiral staircase --------------------------------------------------------

def test_spiral_returns_column_plus_valid_closed_wedges():
    steps = 6
    brushes = spiral_staircase(steps, inner_radius=64, step_width=96, rise=16,
                               degrees_per_step=30)
    assert len(brushes) == steps + 1     # central column + one wedge tread per step
    for b in brushes:
        validate_brush(b)                # convex, planar, non-degenerate (also post-rotation)
        assert _is_closed(b)


def test_spiral_wedges_are_convex_and_wind_outward():
    # validate_brush + _is_closed are winding/convexity-blind, so they'd accept an
    # inverted or non-convex wedge. For each convex wedge, every face normal must point
    # away from the wedge's OWN centroid (wedges are rotated off the origin, so we can't
    # reuse (0,0,0)). This pins the Newell-flip-survives-rotation correctness.
    steps = 6
    brushes = spiral_staircase(steps, inner_radius=64, step_width=96, rise=16,
                               degrees_per_step=30)
    wedges = brushes[1:]                  # drop the central column
    for wedge in wedges:
        own_centroid = _centroid([v for p in wedge.polys for v in p.vertices])
        assert _winds_outward(wedge, own_centroid)


def test_spiral_column_is_centered_and_spans_full_height():
    steps, rise, inner_radius = 5, 20, 48
    column = spiral_staircase(steps, inner_radius, step_width=96, rise=rise)[0]
    verts = [v for p in column.polys for v in p.vertices]
    xs = [float(v[0]) for v in verts]
    ys = [float(v[1]) for v in verts]
    zs = [float(v[2]) for v in verts]
    # centered on the column axis (origin in XY), base at z=0, top at steps*rise
    assert (min(xs) + max(xs)) / 2 == pytest.approx(0.0, abs=1e-6)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(0.0, abs=1e-6)
    assert min(zs) == pytest.approx(0.0)
    assert max(zs) == pytest.approx(steps * rise)


def test_spiral_wedge_tops_ascend_monotonically():
    steps, rise = 5, 24
    brushes = spiral_staircase(steps, inner_radius=64, step_width=96, rise=rise,
                               degrees_per_step=30)
    wedges = brushes[1:]                  # drop the central column
    tops = [max(float(v[2]) for p in b.polys for v in p.vertices) for b in wedges]
    # Each wedge strictly higher than the one below — kills the mirrored-V regression.
    assert all(tops[k] > tops[k - 1] for k in range(1, len(tops)))
    assert tops == [pytest.approx((k + 1) * rise) for k in range(steps)]


# --- actor wrapping ----------------------------------------------------------

def test_make_brush_actor_props_and_csg():
    a = make_brush_actor("UedcliBrush0", cube(128, 128, 128),
                         location=(100, 200, 300), csg="subtract",
                         group="club", poly_flags=PF_SEMISOLID)
    props = dict(a.props)
    assert a.cls == "Engine.Brush"      # already-qualified at creation (2026-06-21)
    assert props["CsgOper"] == "CSG_Subtract"
    assert props["Group"] == "club"
    assert props["PolyFlags"] == str(PF_SEMISOLID)
    assert props["Brush"] == "Model'MyLevel.Model_UedcliBrush0'"
    assert a.brush.model_name == "Model_UedcliBrush0"
    assert a.location == (100.0, 200.0, 300.0)


def test_make_brush_actor_emits_brush_ref_after_block():
    a = make_brush_actor("UedcliBrush1", cube(64, 64, 64))
    t3d = emit_actor(a)
    # The Brush= ref MUST come after End Brush, or the brush is unselectable.
    assert t3d.index("Brush=Model'") > t3d.index("End Brush")


def test_built_cube_actor_roundtrips():
    a = make_brush_actor("UedcliBrush2", cube(256, 128, 64))
    back = next(iter(parse_t3d("Begin Map\n" + emit_actor(a) + "\nEnd Map\n").actors.values()))
    assert back.name == "UedcliBrush2"
    assert back.brush is not None and len(back.brush.polys) == 6
    validate_brush(back.brush)


def test_make_brush_actor_mover_variant_sets_class_and_omits_csgoper():
    a = make_brush_actor("Mover", cube(128, 64, 128), location=(0.0, 0.0, 0.0),
                         mover_class="DeusEx.ElevatorMover")
    assert a.cls == "DeusEx.ElevatorMover"
    keys = {k for k, _ in a.props}
    assert "CsgOper" not in keys               # a mover carries no CsgOper
    assert ("Brush", "Model'MyLevel.Model_Mover'") in a.props
