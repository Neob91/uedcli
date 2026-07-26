"""The swept-profile generators — `brush build extrude` (and, once it lands, `brush build
revolve`). Drives the REAL argparse parser through `dispatch()` so the flags parse and route
exactly as a user would spell them; the geometry oracles work directly against `builders`.

The strongest available oracle for the axis mapping and winding is `builders.cube`: a centred
square profile swept along each axis must reproduce the equivalent box, vertex for vertex."""
from __future__ import annotations

import math

import pytest

from uedcli import builders, cli, dispatch, doctor
from uedcli.builders import make_brush_actor, translate_brush
from uedcli.model import parse_t3d
from uedcli.tests.conftest import StubClassIndex

IDX = StubClassIndex()          # the offline class resolver `doctor`'s mover gate needs


def _run(argv):
    """Parse `argv` with the real CLI and dispatch it; returns the exit code."""
    return dispatch.dispatch(cli.build_parser().parse_args(argv))


def _points(*pairs):
    out = []
    for u, v in pairs:
        out += ["--point", f"{u},{v}"]
    return out


def _vset(brush):
    """The brush's vertex SET, rounded past float noise (face order and item names differ by
    design between a swept brush and the parametric oracle, so only the point set is compared).

    A vertex set is orientation-BLIND — an inside-out solid has exactly the same one — so every
    caller pairs it with `_volume(...) > 0`, which is the half that catches inverted winding.
    """
    return {tuple(round(float(c), 6) for c in v) for p in brush.polys for v in p.vertices}


def _volume(brush):
    """Enclosed volume by the divergence theorem over triangle fans. Positive iff every face is
    wound counter-clockwise seen from OUTSIDE — so this measures orientation as well as size.

    This is the ONLY oracle here that sees a globally inverted solid: `doctor.check_watertight`
    pairs directed edges, so it detects winding that is INCONSISTENT between neighbouring faces
    and stays silent when every face is flipped together (verified by mutation — negating every
    outward hint yields 0 doctor findings, an identical `_vset`, and a negated volume).
    """
    total = 0.0
    for poly in brush.polys:
        vs = [tuple(float(c) for c in v) for v in poly.vertices]
        for i in range(1, len(vs) - 1):
            a, b, c = vs[0], vs[i], vs[i + 1]
            total += (a[0] * (b[1] * c[2] - b[2] * c[1])
                      - a[1] * (b[0] * c[2] - b[2] * c[0])
                      + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return total


# --- the cube oracle: the axis mapping and the sweep, checked against builders.cube --------------

W, H, D = 256.0, 128.0, 64.0
CENTRED_SQUARE = [(-W / 2, -H / 2), (W / 2, -H / 2), (W / 2, H / 2), (-W / 2, H / 2)]


@pytest.mark.parametrize("axis, shift, oracle", [
    # `cube` is origin-centred while an extrude sweeps 0..depth, so the raw vertex sets can never
    # match — the extrude is translated back by −depth/2 along its own axis first. The per-axis
    # dimension mapping is pinned here too, because it is exactly what is easy to get backwards:
    # for --axis y, u→Z and v→X, so the box is width=v_extent, breadth=depth, height=u_extent.
    ("z", (0.0, 0.0, -D / 2), (W, H, D)),      # u→X, v→Y, sweep +Z
    ("x", (-D / 2, 0.0, 0.0), (D, W, H)),      # u→Y, v→Z, sweep +X
    ("y", (0.0, -D / 2, 0.0), (H, D, W)),      # u→Z, v→X, sweep +Y
])
def test_extruded_square_reproduces_the_equivalent_cube(axis, shift, oracle):
    swept = translate_brush(builders.extrude(CENTRED_SQUARE, D, axis), *shift)
    assert _vset(swept) == _vset(builders.cube(*oracle))
    # The vertex set alone would also pass on an inside-out solid; the volume's SIGN is what
    # pins the outward orientation, and its magnitude must match the oracle box.
    assert _volume(swept) == pytest.approx(_volume(builders.cube(*oracle)))
    assert _volume(swept) > 0


def test_extruded_square_has_one_face_per_profile_edge_plus_two_caps():
    brush = builders.extrude(CENTRED_SQUARE, D, "z")
    assert [p.item for p in brush.polys] == ["Cap", "Cap", "Side0", "Side1", "Side2", "Side3"]


# --- anchoring: --at is where profile (0,0) lands ------------------------------------------------


@pytest.mark.parametrize("axis, expect", [
    # The spec's worked example, per axis: a 128×64 profile drawn from (0,0), swept 32.
    ("z", ((512, 640), (0, 64), (64, 96))),        # u→X, v→Y, sweep +Z
    ("x", ((512, 544), (0, 128), (64, 128))),      # u→Y, v→Z, sweep +X
    ("y", ((512, 576), (0, 32), (64, 192))),       # u→Z, v→X, sweep +Y
])
def test_at_is_the_world_point_profile_00_lands_on(axis, expect, capsys):
    rc = _run(["brush", "build", "extrude", "--axis", axis, "--depth", "32",
               "--at", "512,0,64",
               *_points((0, 0), (128, 0), (128, 64), (0, 64))])
    assert rc == 0
    actor = next(iter(parse_t3d(capsys.readouterr().out).actors.values()))
    world = [tuple(float(v[i]) + float(actor.location[i]) for i in range(3))
             for p in actor.brush.polys for v in p.vertices]
    for i, (lo, hi) in enumerate(expect):
        assert (min(w[i] for w in world), max(w[i] for w in world)) == (lo, hi)


def test_profile_00_is_a_local_vertex_so_the_actor_location_is_the_anchor(capsys):
    rc = _run(["brush", "build", "extrude", "--depth", "32", "--at", "512,0,64",
               *_points((0, 0), (128, 0), (128, 64), (0, 64))])
    assert rc == 0
    actor = next(iter(parse_t3d(capsys.readouterr().out).actors.values()))
    assert actor.location == (512.0, 0.0, 64.0)
    assert (0.0, 0.0, 0.0) in {tuple(float(c) for c in v)
                               for p in actor.brush.polys for v in p.vertices}


# --- winding-agnostic input ----------------------------------------------------------------------


def test_a_reversed_profile_emits_byte_identical_t3d(capsys):
    ring = [(0, 0), (128, 0), (128, 64), (0, 64)]
    assert _run(["brush", "build", "extrude", "--depth", "32", *_points(*ring)]) == 0
    ccw = capsys.readouterr().out
    assert _run(["brush", "build", "extrude", "--depth", "32", *_points(*reversed(ring))]) == 0
    assert capsys.readouterr().out == ccw
    # The invariant is EXACT REVERSAL only: a clockwise spelling that starts at a different vertex
    # normalizes to a cyclic ROTATION of this ring, which renumbers every Side<k>. That numbering
    # is user-visible (`brush poly find --item Side0`) and frozen by the committed goldens, so it
    # is a documented property, not an accident.
    rotated = ring[2::-1] + ring[3:2:-1]
    assert _run(["brush", "build", "extrude", "--depth", "32", *_points(*rotated)]) == 0
    assert capsys.readouterr().out != ccw


# --- doctor is clean on what extrude emits -------------------------------------------------------


def _doctor_findings(brush):
    actor = make_brush_actor("Extrude", brush)
    return doctor.check_degenerate(actor) + doctor.check_watertight(actor, IDX)


def test_a_box_profile_extrude_is_doctor_clean():
    brush = builders.extrude(CENTRED_SQUARE, D, "z")
    findings = _doctor_findings(brush)
    assert [(f.category, f.message) for f in findings] == []
    assert _volume(brush) > 0        # doctor alone is blind to a uniformly inverted solid


@pytest.mark.parametrize("axis", ["x", "y", "z"])
def test_an_irregular_convex_profile_extrude_is_doctor_clean(axis):
    # A non-axis-aligned, off-grid profile: catches an outward hint that is merely "not obviously
    # wrong" on a box, where every face normal is a world axis.
    ring = [(0, 0), (96, 0), (128, 48), (64, 96), (8, 40)]
    brush = builders.extrude(ring, 48.0, axis)
    findings = _doctor_findings(brush)
    assert [(f.category, f.message) for f in findings] == []
    assert _volume(brush) > 0        # doctor alone is blind to a uniformly inverted solid


# --- concave / oversized profiles: tiled caps, ONE brush -----------------------------------------

L_PROFILE = [(0, 0), (96, 0), (96, 32), (32, 32), (32, 96), (0, 96)]
BIG_PROFILE = [(round(100 * math.cos(2 * math.pi * i / 17), 6),
                round(100 * math.sin(2 * math.pi * i / 17), 6)) for i in range(17)]


def test_a_convex_profile_still_emits_exactly_two_cap_faces():
    # Guards the simple case against a tiling regression: a box profile must not start emitting
    # triangles just because the decomposition became general.
    brush = builders.extrude(CENTRED_SQUARE, D, "z")
    assert sum(1 for p in brush.polys if p.item == "Cap") == 2


@pytest.mark.parametrize("ring", [L_PROFILE, BIG_PROFILE])
def test_a_concave_or_oversized_profile_extrudes_to_one_brush_with_tiled_caps(ring, capsys):
    from uedcli import profile as profile2d
    pieces = len(profile2d.convex_pieces(profile2d.normalize_winding(
        [(float(u), float(v)) for u, v in ring])))
    assert pieces > 1
    rc = _run(["brush", "build", "extrude", "--depth", "32", *_points(*ring)])
    assert rc == 0
    level = parse_t3d(capsys.readouterr().out)
    assert len(level.actors) == 1                          # ONE brush, not one per piece
    actor = next(iter(level.actors.values()))
    assert len(actor.brush.polys) == len(ring) + 2 * pieces
    assert sum(1 for p in actor.brush.polys if p.item == "Cap") == 2 * pieces


@pytest.mark.parametrize("ring", [L_PROFILE, BIG_PROFILE])
def test_a_tiled_cap_extrude_is_doctor_clean(ring):
    # The point of tiling: every FACE is convex (so no `convex` finding) while the BRUSH is not,
    # and tiling adds only diagonals, so the solid stays watertight (no T-junctions).
    brush = builders.extrude(ring, 32.0, "z")
    findings = _doctor_findings(brush)
    assert [(f.category, f.message) for f in findings] == []
    assert _volume(brush) > 0        # doctor alone is blind to a uniformly inverted solid


# --- revolve: the rotated outward hints are the load-bearing part --------------------------------

# A corridor cross-section: 128 uu wide, 128 uu tall, inner wall 64 uu from the bend centre.
CORRIDOR = [(64, 0), (192, 0), (192, 128), (64, 128)]

# A TAPERED cross-section — a turned column, an arch ring with a batter. Every profile edge of
# CORRIDOR is axis-parallel in (u,v), which makes it blind to a whole class of hint error: the
# rotated-2D-edge-normal shortcut is exact iff `du == 0` or `dv == 0`. These two rings have
# slanted edges and are the ones that actually exercise the side-quad hint.
TAPERED = [(64, 0), (192, 0), (160, 128), (96, 128)]
CHAMFERED = [(64, 0), (192, 0), (192, 96), (160, 128), (96, 128), (64, 96)]


def _hint_disagreements(brush, tol=1e-6):
    """Faces whose STORED hint disagrees with the face's own winding-derived normal.

    `builders._face` takes a rough outward direction and uses it for three things: to decide
    whether to reverse the ring, as the emitted `Normal`, and as the seed for `_tex_basis`. Only
    the first is self-correcting. So a hint that is merely CLOSE ENOUGH to flip correctly can
    still leave a face whose `Normal` points somewhere else and whose TextureU/TextureV lie in
    the wrong plane — and the editor PRESERVES TextureU/V (it only recomputes `Normal`), so wrong
    texture axes survive into the built map as a visibly mis-projected surface.

    Returns `(item, reason)` pairs so a failure names the offending face.
    """
    bad = []
    for poly in brush.polys:
        ring = [tuple(float(c) for c in v) for v in poly.vertices]
        true_n = builders._normalize(builders._newell(ring))
        stored = tuple(float(c) for c in poly.normal)
        if builders._dot(true_n, stored) < 1 - 1e-9:
            bad.append((poly.item, f"Normal {stored} != winding normal {true_n}"))
        for name, axis in (("TextureU", poly.texture_u), ("TextureV", poly.texture_v)):
            d = builders._dot(true_n, tuple(float(c) for c in axis))
            if abs(d) > tol:
                bad.append((poly.item, f"{name} is not in the face plane (dot={d:g})"))
    return bad


@pytest.mark.parametrize("angle_uu, degrees", [(16384, 90.0), (32768, 180.0), (65536, 360.0)])
def test_a_revolve_is_doctor_clean_at_a_quarter_half_and_full_turn(angle_uu, degrees):
    # THE gate for the rotated outward directions. `builders._face` FLIPS a ring whose winding
    # disagrees with the outward hint it is given, so a hint that has not been rotated with its
    # face emits a BACKWARDS-WOUND face — `doctor`'s "inverted solid → CSG crash / HOM", and
    # unrecoverable in UnrealEd's importer, which derives the face from the winding alone.
    # Written before the geometry and confirmed RED against unrotated hints — but only at 180°
    # and 360°. MEASURED sensitivity of the doctor assertion alone, by mutation (unrotated
    # far cap / unrotated sides / both):
    #     90°  → 0 / 0  / 0  findings      180° → 4 / 20 / 20      360° → 0 / 20 / 20
    # At 90° an unrotated far-cap hint is exactly perpendicular to the true normal, so
    # `_dot(nw, out)` is 0, no flip happens, and the winding comes out right by luck — `doctor`
    # cannot see it. That is the `_dot == 0` case, and it is the WORST one, because the same
    # degenerate hint still seeds the texture basis. `_hint_disagreements` is what covers it, and
    # it is why the 90° row above is not evidence that this parametrization is redundant.
    brush = builders.revolve(CORRIDOR, degrees, 8, "z")
    findings = _doctor_findings(brush)
    assert [(f.category, f.message) for f in findings] == []
    assert _hint_disagreements(brush) == []
    assert _volume(brush) > 0


@pytest.mark.parametrize("ring", [TAPERED, CHAMFERED])
@pytest.mark.parametrize("degrees, segments", [(30.0, 1), (90.0, 4), (180.0, 5), (360.0, 8)])
def test_a_slanted_profile_revolve_has_an_exact_outward_hint(ring, degrees, segments):
    # The case CORRIDOR structurally cannot cover. A profile edge that is neither horizontal nor
    # vertical in (u,v) has a swept quad whose true normal is proportional to
    # `(dv, −du·cos(Δ/2))`, so the rotated 2D edge normal is off by `90° − 2·atan(√cos(Δ/2))` — 0.56° at the default 22.5° facet, 2.27° at 45° — and that error is
    # INVISIBLE to both other oracles here: it never mis-winds the face (the two directions stay
    # within 90° of each other), so `doctor` is silent and the volume stays positive. It lands in
    # TextureU/TextureV instead, which the editor preserves. Measured against the pre-fix
    # builder: 20 disagreements at 90°/4 and 32 at 360°/8 for TAPERED, worst axis 1° out of plane.
    brush = builders.revolve(ring, degrees, segments, "z")
    assert _hint_disagreements(brush) == []
    assert [(f.category, f.message) for f in _doctor_findings(brush)] == []
    assert _volume(brush) > 0


def test_a_full_turn_revolve_is_a_closed_solid_with_no_caps():
    # Proves the UU→degrees conversion did not wrap a full turn to zero (`rotation.uu_to_deg(65536)`
    # IS 0.0 — which is why sweep magnitudes never go through it), and that the ring closes onto
    # itself instead of leaving two coincident caps inside the solid.
    brush = builders.revolve(CORRIDOR, 360.0, 16, "z")
    assert [p for p in brush.polys if p.item == "Cap"] == []
    assert len(brush.polys) == 4 * 16
    # A faceted ring holds a little less than the true torus (2π·R̄·A, R̄ = 128, A = 128×128).
    torus = 2 * math.pi * 128 * 128 * 128
    assert 0.9 * torus < _volume(brush) < torus


@pytest.mark.parametrize("angle_uu, expect_segments", [(16384, 4), (65536, 16)])
def test_the_segment_default_is_one_facet_per_22_5_degrees(angle_uu, expect_segments, capsys):
    rc = _run(["brush", "build", "revolve", "--angle", str(angle_uu), *_points(*CORRIDOR)])
    assert rc == 0
    actor = next(iter(parse_t3d(capsys.readouterr().out).actors.values()))
    sides = [p for p in actor.brush.polys if (p.item or "").startswith("Side")]
    assert len(sides) == 4 * expect_segments


def test_side_item_names_are_keyed_to_the_profile_edge_across_every_segment(capsys):
    rc = _run(["brush", "build", "revolve", "--angle", "16384", "--segments", "4",
               *_points(*CORRIDOR)])
    assert rc == 0
    actor = next(iter(parse_t3d(capsys.readouterr().out).actors.values()))
    items = [p.item for p in actor.brush.polys]
    for k in range(4):
        assert items.count(f"Side{k}") == 4          # one per segment: the whole strip is Side<k>
    assert items.count("Cap") == 2                   # a partial sweep keeps both caps


@pytest.mark.parametrize("argv, needle", [
    (["--angle", "0"], "--angle"),
    (["--angle", "65537"], "--angle"),
    (["--angle", "16384", "--segments", "0"], "--segments"),
    (["--angle", "32768", "--segments", "1"], "per facet"),
    (["--angle", "65536", "--segments", "2"], "at least 3"),
])
def test_a_degenerate_sweep_exits_2_naming_the_flag(argv, needle, capsys):
    rc = _run(["brush", "build", "revolve", *argv, *_points(*CORRIDOR)])
    assert rc == 2
    err = capsys.readouterr().err
    assert needle in err and "Traceback" not in err


@pytest.mark.parametrize("ring", [
    [(-64, 0), (64, 0), (64, 128), (-64, 128)],      # straddles the axis
    [(0, 0), (128, 0), (128, 128), (0, 128)],        # touches the axis
    [(-192, 0), (-64, 0), (-64, 128), (-192, 128)],  # wholly on the negative side
])
def test_a_profile_that_is_not_strictly_off_axis_exits_2(ring, capsys):
    rc = _run(["brush", "build", "revolve", "--angle", "16384", *_points(*ring)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "POSITIVE-u" in err and "Traceback" not in err


def test_revolve_at_is_the_bend_centre(capsys):
    # The revolve axis passes through profile (0,0), so --at places the centre the sweep bends
    # around — with --axis z that axis is the world Y line through --at.
    rc = _run(["brush", "build", "revolve", "--angle", "16384", "--segments", "4",
               "--at", "512,0,64", *_points(*CORRIDOR)])
    assert rc == 0
    actor = next(iter(parse_t3d(capsys.readouterr().out).actors.values()))
    assert actor.location == (512.0, 0.0, 64.0)
    world = [tuple(float(v[i]) + float(actor.location[i]) for i in range(3))
             for p in actor.brush.polys for v in p.vertices]
    # u→X and the sweep grows +Z: a 90° bend swings the profile from the +X side round to +Z, so
    # X runs 512+0 (the far ring, which lies ON the axis plane) .. 512+192, and Z 64..64+192.
    assert (min(w[0] for w in world), max(w[0] for w in world)) == (512.0, 704.0)
    assert (min(w[2] for w in world), max(w[2] for w in world)) == (64.0, 256.0)


# --- rejections: exit 2, the offending value named, never a traceback ----------------------------


@pytest.mark.parametrize("argv, needle", [
    (["--point", "128"], "two comma-separated numbers"),
    (["--point", "1,2,3"], "two comma-separated numbers"),
    (["--point", "a,b"], "must be numbers"),
])
def test_a_malformed_point_token_exits_2_naming_it(argv, needle, capsys):
    rc = _run(["brush", "build", "extrude", "--depth", "32",
               *_points((0, 0), (128, 0), (128, 64)), *argv])
    assert rc == 2
    err = capsys.readouterr().err
    assert needle in err and "Traceback" not in err


@pytest.mark.parametrize("ring", [[], [(0, 0)], [(0, 0), (128, 0)]])
def test_fewer_than_three_points_exits_2(ring, capsys):
    rc = _run(["brush", "build", "extrude", "--depth", "32", *_points(*ring)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "at least 3 points" in err and str(len(ring)) in err and "Traceback" not in err


@pytest.mark.parametrize("depth", ["0", "-5"])
def test_a_non_positive_depth_exits_2_naming_the_flag(depth, capsys):
    rc = _run(["brush", "build", "extrude", "--depth", depth,
               *_points((0, 0), (128, 0), (128, 64), (0, 64))])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--depth must be greater than 0" in err and depth in err and "Traceback" not in err


def test_a_bowtie_profile_exits_2(capsys):
    rc = _run(["brush", "build", "extrude", "--depth", "32",
               *_points((0, 0), (128, 128), (128, 0), (0, 128))])
    assert rc == 2
    err = capsys.readouterr().err
    assert "not simple" in err and "Traceback" not in err


def test_a_pinched_profile_exits_2(capsys):
    rc = _run(["brush", "build", "extrude", "--depth", "32",
               *_points((0, 0), (128, 0), (128, 64), (64, 0), (0, 64))])
    assert rc == 2
    err = capsys.readouterr().err
    assert "not simple" in err and "Traceback" not in err


def test_a_zero_area_profile_exits_2(capsys):
    rc = _run(["brush", "build", "extrude", "--depth", "32",
               *_points((0, 0), (64, 0), (128, 0), (192, 0))])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err and err.strip()


# --- the builders' own internal-API guards (not reachable through the CLI, so tested direct) -----


@pytest.mark.parametrize("kwargs, needle", [
    (dict(angle_deg=90.0, segments=0), "segments >= 1"),
    (dict(angle_deg=0.0, segments=4), "0 < angle_deg <= 360"),
    (dict(angle_deg=400.0, segments=4), "0 < angle_deg <= 360"),
    (dict(angle_deg=360.0, segments=2), "segments >= 3"),
    (dict(angle_deg=180.0, segments=1), "facet under 180"),
])
def test_the_revolve_library_guards_refuse_a_degenerate_sweep(kwargs, needle):
    # `dispatch` catches all of these first, in UU and naming the flags — so these guards protect
    # only NON-CLI callers, and an unexercised guard is a second thing to keep true with nothing
    # enforcing it. Called directly for exactly that reason.
    from uedcli.geometry import GeometryError
    with pytest.raises(GeometryError, match=needle):
        builders.revolve(CORRIDOR, **kwargs)


def test_the_revolve_library_guard_refuses_an_on_axis_profile():
    from uedcli.geometry import GeometryError
    with pytest.raises(GeometryError, match="u > 0"):
        builders.revolve([(0, 0), (128, 0), (128, 128)], 90.0, 4)


def test_the_extrude_library_guard_refuses_a_non_positive_depth():
    from uedcli.geometry import GeometryError
    with pytest.raises(GeometryError, match="depth > 0"):
        builders.extrude(CENTRED_SQUARE, 0.0)


# --- committed goldens: face order, item names and coordinates cannot drift silently -------------


@pytest.mark.parametrize("fixture, argv", [
    ("builder_extrude.t3d",
     ["brush", "build", "extrude", "--axis", "y", "--depth", "16", "--at", "0,0,0",
      "--point", "0,0", "--point", "96,0", "--point", "96,32",
      "--point", "32,32", "--point", "32,96", "--point", "0,96"]),
    ("builder_revolve.t3d",
     ["brush", "build", "revolve", "--axis", "x", "--angle", "16384", "--segments", "4",
      "--at", "0,0,0",
      "--point", "64,0", "--point", "192,0", "--point", "192,128", "--point", "64,128"]),
])
def test_the_emitted_t3d_matches_its_committed_golden(fixture, argv, capsys):
    # These are SELF-blessed (generated by this code), unlike the six parametric shapes, which are
    # pinned against real-editor captures by `builder_parity_cases.py`. So they pin DRIFT, not
    # correctness: face order, the Cap/Side<k> item names and every coordinate. A parity case
    # against the live editor is a follow-up, not covered here.
    #
    # `builder_revolve.t3d` was re-blessed once, 2026-07-26, on ONE face: the far cap's
    # TextureU/V. Its texture basis had been selected by a 6.1e-17 rotation residue rather than by
    # its geometry (`_tex_basis` seeds from the least-aligned world axis, so a residue can decide
    # the seed), and `_denoise` now snaps that away. The re-blessed values are exactly in-plane
    # (`U·N = V·N = 0`); the previous ones were valid too, but arbitrary. Vertices did not move.
    from uedcli.tests.conftest import read_fixture
    assert _run(argv) == 0
    assert capsys.readouterr().out == read_fixture(fixture)


# --- the two stderr advisories (stdout stays a clean T3D snippet, exit stays 0) ------------------


def _revolve_argv(*extra):
    return ["brush", "build", "revolve", "--angle", "16384", "--segments", "4",
            *extra, *_points(*CORRIDOR)]


def test_a_solid_off_grid_revolve_warns_about_the_bsp(capsys):
    rc = _run(_revolve_argv())
    assert rc == 0
    cap = capsys.readouterr()
    assert "off the integer grid" in cap.err and "semisolid" in cap.err
    assert parse_t3d(cap.out).actors                     # …and stdout is still a valid snippet


def test_a_semisolid_revolve_does_not_warn_about_the_grid(capsys):
    # Semisolid receives cuts but emits no world-splitting planes, so the situation is already
    # handled — warning there would make the advisory noise.
    rc = _run(_revolve_argv("--solidity", "semisolid"))
    assert rc == 0
    assert "off the integer grid" not in capsys.readouterr().err


def test_a_mover_revolve_does_not_warn_about_the_grid(capsys):
    # A mover REJECTS --solidity, so it always lands on the solid flag value — but it never
    # partitions the world, so the BSP advisory would be simply wrong.
    rc = _run(_revolve_argv("--mover-class", "Engine.Mover"))
    assert rc == 0
    assert "off the integer grid" not in capsys.readouterr().err


def test_an_on_grid_extrude_does_not_warn(capsys):
    rc = _run(["brush", "build", "extrude", "--depth", "32",
               *_points((0, 0), (128, 0), (128, 64), (0, 64))])
    assert rc == 0
    assert capsys.readouterr().err.strip() == ""


def test_a_cylinder_still_says_nothing_about_its_own_fractional_ring(capsys):
    # The advisory is shape-gated. `brush build cylinder --radius 48` has inherently off-grid ring
    # vertices; an ungated advisory would turn its existing silence assertion red.
    rc = _run(["brush", "build", "cylinder", "--height", "64", "--radius", "48"])
    assert rc == 0
    assert capsys.readouterr().err.strip() == ""


def test_a_heavy_revolve_warns_about_the_poly_budget(capsys):
    # 4 profile edges × 17 segments = 68 faces, and NO caps — `--angle 65536` is a closed turn,
    # which omits both. 17 rather than 16 is load-bearing: the advisory fires above 64 faces, and
    # a full turn's default 16 segments gives exactly 4 × 16 = 64, which is not > 64.
    rc = _run(["brush", "build", "revolve", "--angle", "65536", "--segments", "17",
               "--solidity", "semisolid", *_points(*CORRIDOR)])
    assert rc == 0
    cap = capsys.readouterr()
    assert "68 faces" in cap.err and "heavy brush" in cap.err
    assert parse_t3d(cap.out).actors


def test_a_light_revolve_does_not_warn_about_the_poly_budget(capsys):
    rc = _run(_revolve_argv("--solidity", "semisolid"))
    assert rc == 0
    assert "heavy brush" not in capsys.readouterr().err


# --- the generator surface is the standard one ---------------------------------------------------


def test_extrude_takes_the_common_generator_options(capsys):
    rc = _run(["brush", "build", "extrude", "--depth", "32", "--csg", "subtract",
               "--solidity", "semisolid", "--folder", "castle.hall", "--base-name", "Ledge",
               *_points((0, 0), (96, 0), (96, 32), (0, 32))])
    assert rc == 0
    out = capsys.readouterr().out
    actor = next(iter(parse_t3d(out).actors.values()))
    assert dict(actor.props).get("CsgOper") == "CSG_Subtract"
    assert dict(actor.props).get("PolyFlags") == str(builders.PF_SEMISOLID)
    assert actor.name == "Ledge"
    assert "// uedcli-folder: castle.hall" in out
