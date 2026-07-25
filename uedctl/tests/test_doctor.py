"""Static `level doctor` checks. Positive fixtures (planted bug → finding) AND negative fixtures
(good geometry → silence) — the negatives lock out the false-positive failure modes the review
fleet flagged (fractional watertight brushes, clean cubes)."""
import copy
from decimal import Decimal

from uedctl import builders, doctor
from uedctl.builders import PF_NOTSOLID, PF_SEMISOLID, make_brush_actor
from uedctl.doctor import Severity
from uedctl.model import Actor, Brush, Level, Polygon
from uedctl.tests.conftest import StubClassIndex

IDX = StubClassIndex()          # the offline class resolver `movers.is_mover` needs


def _D(*xyz):
    return tuple(Decimal(str(c)) for c in xyz)


def _poly(verts, **kw):
    return Polygon(vertices=[_D(*v) for v in verts], **kw)


def _solid_cube(name="Box1", csg="add", poly_flags=0, location=(0, 0, 0)):
    return make_brush_actor(name, builders.cube(128, 128, 128), location=location,
                            csg=csg, poly_flags=poly_flags)


def _level(*actors):
    lvl = Level()
    for a in actors:
        lvl.actors[a.name] = a
    lvl.order = [a.name for a in actors]
    return lvl


def _cats(findings):
    return [(f.severity, f.category) for f in findings]


# --- degeneracy --------------------------------------------------------------------------------

def test_it_flags_collinear_triangle_as_degenerate():
    # 3 colinear points collapse below 3 after the engine's colinear cleanup.
    brush = Brush(model_name="M", polys=[_poly([(0, 0, 0), (50, 0, 0), (100, 0, 0)])])
    actor = Actor(name="Bad1", cls="Engine.Brush", brush=brush)

    findings = doctor.check_degenerate(actor)

    assert any(f.category == "degenerate" and f.severity is Severity.ERROR for f in findings)
    assert "Not enough vertices" in findings[0].symptom


def test_it_flags_nonconvex_face_as_error():
    # A chevron: vertex (64,16) dents inward → one reflex turn → non-convex.
    brush = Brush(model_name="M", polys=[_poly(
        [(0, 0, 0), (64, 16, 0), (128, 0, 0), (128, 128, 0), (0, 128, 0)])])
    actor = Actor(name="Bad2", cls="Engine.Brush", brush=brush)

    findings = doctor.check_degenerate(actor)

    assert _cats(findings) == [(Severity.ERROR, "convex")]


def test_it_flags_nonplanar_quad_as_warn():
    # Three corners on z=0, one lifted 7uu off the plane.
    brush = Brush(model_name="M", polys=[_poly(
        [(0, 0, 0), (128, 0, 0), (128, 128, 7), (0, 128, 0)])])
    actor = Actor(name="Bad3", cls="Engine.Brush", brush=brush)

    findings = doctor.check_degenerate(actor)

    assert any(f.category == "planar" and f.severity is Severity.WARN for f in findings)


# --- watertightness ----------------------------------------------------------------------------

def test_it_flags_open_solid_as_not_watertight():
    actor = _solid_cube("Open1")
    actor.brush.polys.pop()                       # remove one face → 4 open edges

    findings = doctor.check_watertight(actor, IDX)

    assert findings, "an open box must report open edges"
    assert all(f.category == "watertight" and f.severity is Severity.ERROR for f in findings)
    assert any("open edge" in f.message for f in findings)


def test_it_flags_reversed_face_as_winding_error():
    actor = _solid_cube("Flip1")
    actor.brush.polys[0].vertices.reverse()       # one face wound backwards

    findings = doctor.check_watertight(actor, IDX)

    assert findings
    assert all(f.category == "watertight" for f in findings)
    assert any("wound backwards" in f.message for f in findings)


def test_it_stays_quiet_on_clean_solid_cube():
    assert doctor.check_watertight(_solid_cube("Clean1"), IDX) == []


def test_it_stays_quiet_on_fractional_watertight_box():
    # Reviewer C2: edges keyed on welded CLEANED corners — a watertight box on genuinely
    # fractional coords (a 0.707 shift, CSG-native) must NOT read as all-open-edges.
    actor = _solid_cube("Frac1")
    for p in actor.brush.polys:
        p.vertices = [(x + Decimal("0.707"), y + Decimal("0.707"), z + Decimal("0.707"))
                      for x, y, z in p.vertices]

    assert doctor.check_watertight(actor, IDX) == []


def test_it_skips_watertight_for_nonsolid_brush():
    # A nonsolid sheet is intentionally open — never flag it as non-watertight.
    actor = _solid_cube("Sheet1", poly_flags=PF_NOTSOLID)
    actor.brush.polys.pop()

    assert doctor.check_watertight(actor, IDX) == []


# --- watertightness: T-junction-aware interval parity (spec 2026-07-21 Part B) ------------------

def _wface(ring, outward, item="F"):
    return builders._face([tuple(float(c) for c in v) for v in ring], outward, item=item)


def _t_junction_box(*, drop_top_b=False):
    """A 0..64 axis box whose +Z top is SPLIT at x=32 into TopA (x∈[0,32]) and TopB (x∈[32,64]).
    The ±Y faces keep their single full-width top edge, so those edges meet the two half-top
    edges as T-junctions — a closed solid the exact-pair keying would false-flag. With
    `drop_top_b`, TopB is removed so the +Y/-Y top edge's x∈[32,64] portion becomes a REAL open
    edge collinear with the still-healthy x∈[0,32] seam (the anti-masking case)."""
    L = 64.0
    faces = [
        _wface([(0, 0, 0), (L, 0, 0), (L, L, 0), (0, L, 0)], (0, 0, -1)),   # bottom -Z
        _wface([(0, 0, 0), (0, 0, L), (0, L, L), (0, L, 0)], (-1, 0, 0)),   # -X
        _wface([(L, 0, 0), (L, L, 0), (L, L, L), (L, 0, L)], (1, 0, 0)),    # +X
        _wface([(0, 0, 0), (L, 0, 0), (L, 0, L), (0, 0, L)], (0, -1, 0)),   # -Y (single top edge)
        _wface([(0, L, 0), (0, L, L), (L, L, L), (L, L, 0)], (0, 1, 0)),    # +Y (single top edge)
        _wface([(0, 0, L), (32, 0, L), (32, L, L), (0, L, L)], (0, 0, 1)),  # TopA x∈[0,32]
    ]
    if not drop_top_b:
        faces.append(_wface([(32, 0, L), (L, 0, L), (L, L, L), (32, L, L)], (0, 0, 1)))  # TopB
    return Brush(model_name="M", polys=faces)


def test_it_stays_quiet_on_real_t_junction_box():
    # A genuine T-junction (one face split, its neighbours not) is closed — zero findings.
    actor = Actor(name="TJ1", cls="Engine.Brush", brush=_t_junction_box())
    assert doctor.check_watertight(actor, IDX) == []


def test_it_stays_quiet_on_single_brush_staircase():
    # The new single non-convex staircase brush is full of per-step T-junctions yet watertight.
    actor = make_brush_actor("Staircase", builders.staircase(6, depth=48, rise=24, breadth=96))
    assert doctor.check_watertight(actor, IDX) == []


def test_it_flags_open_edge_collinear_with_healthy_seam():
    # Anti-masking: with TopB dropped, on the line y=64,z=64 the +Y face's long edge is covered
    # only on x∈[0,32] (by TopA, a healthy 1/1 seam) and OPEN on x∈[32,64]. The open sub-segment
    # MUST still be flagged even though its supporting line coincides with the healthy seam.
    actor = Actor(name="Mask1", cls="Engine.Brush",
                  brush=_t_junction_box(drop_top_b=True))

    findings = doctor.check_watertight(actor, IDX)

    on_line = [f for f in findings
               if abs(f.coord[1] - 64) < 1e-6 and abs(f.coord[2] - 64) < 1e-6]
    # the uncovered sub-segment (x in (32,64)) is flagged open ...
    assert any("open edge" in f.message and 32 < f.coord[0] < 64 for f in on_line), on_line
    # ... and the healthy seam sub-segment (x in (0,32)) is NOT false-flagged.
    assert not any(0 < f.coord[0] < 32 for f in on_line), on_line


def test_it_flags_nonmanifold_edge():
    # A solid cube plus a DUPLICATE of one face: that face's 4 edges are traversed by 3 half-edges
    # (original + neighbour + duplicate) → f+b == 3 > 2 → non-manifold (caught before net-flow).
    actor = _solid_cube("NM1")
    actor.brush.polys.append(copy.deepcopy(actor.brush.polys[0]))

    findings = doctor.check_watertight(actor, IDX)

    assert findings
    assert all(f.category == "watertight" and f.severity is Severity.ERROR for f in findings)
    assert any("non-manifold" in f.message for f in findings)


def test_it_stays_quiet_on_cone_and_cylinder():
    # Slanted (cone) and many-sided (cylinder) edges must still read clean — the float
    # line-grouping must not regress a genuinely closed non-axis-aligned solid.
    assert doctor.check_watertight(
        make_brush_actor("Cone1", builders.cone(160, 96, sides=6)), IDX) == []
    assert doctor.check_watertight(
        make_brush_actor("Cyl1", builders.cylinder(128, 96, sides=8)), IDX) == []


def test_it_pins_line_key_epsilon_to_weld():
    # The line-key quantum is the vertex weld grid (1e-3 uu): an offset below half the quantum
    # keys onto the same supporting line, above it splits off; a clearly separate line never merges.
    from uedctl.doctor import _line_key, WATERTIGHT_LINE_EPS
    from uedctl.builders import WELD
    assert WATERTIGHT_LINE_EPS == WELD == 1e-3
    base = _line_key((0.0, 0.0, 0.0), (10.0, 0.0, 0.0))[0]
    assert _line_key((0.0, 0.0, 0.0004), (10.0, 0.0, 0.0004))[0] == base
    assert _line_key((0.0, 0.0, 0.0006), (10.0, 0.0, 0.0006))[0] != base
    assert _line_key((0.0, 0.0, 5.0), (10.0, 0.0, 5.0))[0] != base


# --- solidity ----------------------------------------------------------------------------------

def test_it_flags_semisolid_portal_brush():
    PF_PORTAL = doctor.PF_PORTAL
    actor = _solid_cube("Portal1", poly_flags=PF_SEMISOLID | PF_PORTAL)

    findings = doctor.check_solidity(actor)

    assert any(f.category == "solidity" and f.severity is Severity.ERROR for f in findings)
    assert any("Semisolid and Portal" in f.message for f in findings)


def test_it_does_not_flag_nonsolid_walkable_floor():
    # A nonsolid brush with an upward-facing face is a legitimate authoring choice (water,
    # decoration, a deliberate trap) — doctor must not flag it (decisions.md 2026-07-19).
    actor = _solid_cube("Floor1", poly_flags=PF_NOTSOLID)

    assert doctor.check_solidity(actor) == []


def test_it_does_not_flag_semisolid_walkable_floor():
    actor = _solid_cube("Semi1", poly_flags=PF_SEMISOLID)

    assert doctor.check_solidity(actor) == []


def test_it_stays_quiet_on_solid_brush_solidity():
    assert doctor.check_solidity(_solid_cube("S1")) == []


# --- portal / nonsolid sheets: per-poly flags (board bug 1) ------------------------------------

# `brush build sheet` writes PF_NotSolid/PF_TwoSided/PF_Portal ONLY on the per-poly flags — the
# actor-level PolyFlags stays 0. A sheet is a single open 2-sided quad: watertightness saw only the
# actor-level flags, treated it as a solid, and reported "edge used by only one face" ×4 (phantom
# ERRORs + exit 1) on the legitimate zone-portal workflow. The fix reads flags effectively.

PF_TWOSIDED = builders.PF_TWOSIDED
PF_PORTAL_BIT = doctor.PF_PORTAL


def _sheet_actor(name, flags):
    brush = builders.sheet(128, 128, plane="xz", flags=flags)      # single per-poly-flagged quad
    return make_brush_actor(name, brush, poly_flags=0)             # actor-level PolyFlags stays 0


def test_portal_sheet_is_not_flagged_non_watertight():
    portal = _sheet_actor("Portal1", PF_TWOSIDED | PF_NOTSOLID | PF_PORTAL_BIT)
    # It is NOT a closed solid, and produces zero watertight findings.
    assert doctor._is_closed_solid_brush(portal, IDX) is False
    assert doctor.check_watertight(portal, IDX) == []
    findings = doctor.run_doctor(_level(portal), IDX)
    assert [f for f in findings if f.category == "watertight"] == []


def test_plain_nonsolid_sheet_is_not_flagged_non_watertight():
    sheet = _sheet_actor("Fence1", PF_TWOSIDED | PF_NOTSOLID)      # no portal bit, still nonsolid
    assert doctor._is_closed_solid_brush(sheet, IDX) is False
    assert doctor.check_watertight(sheet, IDX) == []


def test_solid_cube_is_still_watertight_checked():
    # Guard: a genuine solid (no nonsolid/portal poly flags) is STILL treated as a closed solid, so
    # the fix didn't silence real open-solid detection.
    assert doctor._is_closed_solid_brush(_solid_cube("S9"), IDX) is True


# --- CSG order ---------------------------------------------------------------------------------

def test_it_flags_add_inside_later_subtract():
    add = make_brush_actor("Add1", builders.cube(64, 64, 64), csg="add")
    sub = make_brush_actor("Sub1", builders.cube(256, 256, 256), csg="subtract")
    level = _level(add, sub)                        # add is EARLIER in order

    findings = doctor.check_csg_order(level)

    erased = [f for f in findings if f.category == "csg_order" and f.brush == "Add1"]
    assert len(erased) == 1 and erased[0].severity is Severity.WARN
    assert "carved away" in erased[0].symptom


def test_it_flags_noop_subtract():
    here = make_brush_actor("AddHere", builders.cube(64, 64, 64), csg="add", location=(0, 0, 0))
    far = make_brush_actor("SubFar", builders.cube(64, 64, 64), csg="subtract",
                           location=(9000, 0, 0))
    level = _level(here, far)

    findings = doctor.check_csg_order(level)

    noop = [f for f in findings if f.brush == "SubFar"]
    assert len(noop) == 1 and noop[0].severity is Severity.INFO
    assert "overlaps no other brush" in noop[0].message


# --- driver / severity / scale -----------------------------------------------------------------

def test_it_reports_clean_level_with_no_findings():
    level = _level(_solid_cube("OnlyBox"))         # single solid add cube, watertight, on-grid

    findings = doctor.run_doctor(level, IDX)

    assert findings == []
    assert doctor.worst(findings) is None


def test_it_exit_severity_reflects_worst_finding():
    bad = _solid_cube("OpenBox")
    bad.brush.polys.pop()
    level = _level(bad)

    findings = doctor.run_doctor(level, IDX)

    assert doctor.worst(findings) is Severity.ERROR


def _open_box_level():
    bad = _solid_cube("OpenBox")
    bad.brush.polys.pop()
    return _level(bad)


def _doctor_args(**kw):
    base = dict(cmd="level", sub="doctor", project=None,
                container="c", json=False, severity=None, category=None)
    base.update(kw)
    return __import__("types").SimpleNamespace(**base)


def _run_dispatch(args, level):
    from unittest import mock
    from uedctl.dispatch import dispatch
    src = mock.Mock()                                 # the trunk seam
    src.load.return_value = level
    src._ranks = {}                                   # _level_doctor reads it for the dup-order check
    src.display_name = "AireGardens.dx"               # _level_doctor uses src.display_name as header
    with mock.patch("uedctl.dispatch._resolve_level_source", return_value=src):
        return dispatch(args)


def test_dispatch_doctor_reports_and_exits_nonzero_on_error(capsys):
    rc = _run_dispatch(_doctor_args(), _open_box_level())
    out = capsys.readouterr().out
    assert rc == 1                                  # an ERROR finding fails the gate
    assert "AireGardens.dx" in out and "open edge" in out


def test_dispatch_doctor_exit_code_ignores_severity_filter(capsys):
    # Filtering DISPLAY to info-only must still exit non-zero (the ERROR exists).
    rc = _run_dispatch(_doctor_args(severity="info"), _open_box_level())
    capsys.readouterr()
    assert rc == 1


def test_dispatch_doctor_clean_level_exits_zero(capsys):
    rc = _run_dispatch(_doctor_args(), _level(_solid_cube("OnlyBox")))
    assert rc == 0
    assert "no issues found" in capsys.readouterr().out


def test_dispatch_doctor_rejects_unknown_category(capsys):
    rc = _run_dispatch(_doctor_args(category="bogus"), _open_box_level())
    assert rc == 2
    assert "unknown --category: bogus" in capsys.readouterr().err


def test_dispatch_doctor_json_output(capsys):
    rc = _run_dispatch(_doctor_args(json=True), _open_box_level())
    out = capsys.readouterr().out
    assert rc == 1
    data = __import__("json").loads(out)
    assert any(d["category"] == "watertight" and d["severity"] == "error" for d in data)


def test_it_flags_nonidentity_scale_as_info():
    actor = _solid_cube("Scaled1")
    actor.props = [(k, v) for k, v in actor.props if k != "MainScale"]
    actor.props.append(("MainScale", "(Scale=(X=2.000000,Y=1.000000,Z=1.000000),SheerAxis=SHEER_ZX)"))

    findings = doctor.check_scale(actor)

    assert _cats(findings) == [(Severity.INFO, "scale")]


def test_subclass_mover_is_treated_as_closed_solid():
    from uedctl.doctor import _is_closed_solid_brush
    a = Actor(name="Lift", cls="DeusEx.ElevatorMover",
              props=[], brush=Brush(model_name="Model_Lift", polys=[]))
    assert _is_closed_solid_brush(a, IDX) is True       # old _MOVER_CLASSES exact-match missed this


# --- duplicate order_value (git-native trunk sidecar) ------------------------------------------

def test_it_flags_actors_sharing_an_order_value():
    # Two actors on the SAME LexoRank order_value; a third on a distinct one is untouched.
    ranks = {"Wall_a1b2c3": "hzzzzz", "Door_d4e5f6": "hzzzzz", "Floor_g7h8i9": "m"}

    findings = doctor.check_duplicate_order(ranks)

    assert len(findings) == 1
    (f,) = findings
    assert f.severity is Severity.WARN
    assert f.category == "csg_order"
    assert f.brush == "Door_d4e5f6"                 # first actor in the SORTED group
    assert "Door_d4e5f6" in f.message and "Wall_a1b2c3" in f.message and "hzzzzz" in f.message
    assert "Floor_g7h8i9" not in f.message          # distinct rank, not implicated
    assert "tiebreak" in f.symptom
    assert "distinct order_value" in f.fix
    assert f.poly is None


def test_it_names_every_actor_in_a_three_way_order_collision():
    # A 3-actor collision must name ALL three in the single finding (guards against dropping a name).
    ranks = {"Wall_a1b2c3": "hzzzzz", "Door_d4e5f6": "hzzzzz", "Ramp_x9y8z7": "hzzzzz",
             "Floor_g7h8i9": "m"}

    findings = doctor.check_duplicate_order(ranks)

    assert len(findings) == 1
    (f,) = findings
    assert all(n in f.message for n in ("Wall_a1b2c3", "Door_d4e5f6", "Ramp_x9y8z7"))
    assert "Floor_g7h8i9" not in f.message


def test_it_flags_actors_with_no_order_value_distinctly():
    # An empty sidecar (missing/blank order_value) reads as "no order_value", not "share ''".
    findings = doctor.check_duplicate_order({"Wall_a1b2c3": "", "Door_d4e5f6": ""})

    (f,) = findings
    assert "have no order_value" in f.message
    assert "''" not in f.message


def test_it_reports_no_duplicate_order_when_ranks_distinct():
    ranks = {"Wall_a1b2c3": "hzzzzz", "Door_d4e5f6": "m", "Floor_g7h8i9": "t"}

    assert doctor.check_duplicate_order(ranks) == []
