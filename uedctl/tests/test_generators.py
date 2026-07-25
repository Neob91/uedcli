"""Tests for generator-pattern helpers: translate_brush, name allocation,
brush build / actor build dispatch. (The CSG set-merge verbs live in
test_brush_merge.py.)"""

# ---------------------------------------------------------------------------
# Step 1c — translate_brush
# ---------------------------------------------------------------------------

def test_translate_brush_shifts_all_vertices():
    from uedctl.builders import cube, translate_brush
    b = cube(100, 200, 300)
    original_verts = [v for poly in b.polys for v in poly.vertices]
    shifted = translate_brush(b, 10, 20, 30)
    shifted_verts = [v for poly in shifted.polys for v in poly.vertices]
    assert len(shifted_verts) == len(original_verts)
    for (ox, oy, oz), (sx, sy, sz) in zip(original_verts, shifted_verts):
        assert abs(float(sx) - float(ox) - 10) < 1e-9
        assert abs(float(sy) - float(oy) - 20) < 1e-9
        assert abs(float(sz) - float(oz) - 30) < 1e-9


def test_translate_brush_does_not_mutate_original():
    from uedctl.builders import cube, translate_brush
    b = cube(100, 200, 300)
    original_first_vertex = b.polys[0].vertices[0]
    translate_brush(b, 1000, 2000, 3000)
    assert b.polys[0].vertices[0] == original_first_vertex


# ---------------------------------------------------------------------------
# Step 3 — brush build <shape>
# ---------------------------------------------------------------------------

from argparse import Namespace
from unittest import mock

import pytest

from uedctl.dispatch import dispatch
from uedctl.model import parse_t3d


def _brush_build_cube_args(**overrides):
    defaults = dict(
        cmd="brush", sub="build", shape="cube",
        width=256.0, breadth=128.0, height=64.0,
        at=(0.0, 0.0, 0.0),
        base_name=None, csg="add", solidity="solid", texture=None,
        prop=None, folder=None, label=[], mover_class=None, rotate=None)
    defaults.update(overrides)
    return Namespace(**defaults)


def test_it_outputs_t3d_for_brush_build_cube(capsys):
    rc = dispatch(_brush_build_cube_args())
    assert rc == 0
    out = capsys.readouterr().out
    level = parse_t3d(out)
    assert len(level.actors) == 1
    a = next(iter(level.actors.values()))
    assert a.cls == "Engine.Brush"
    props = dict(a.props)
    assert props.get("CsgOper") == "CSG_Add"
    assert a.location == (0.0, 0.0, 0.0)
    assert a.brush is not None and len(a.brush.polys) == 6


def test_it_bakes_at_csg_solidity_into_t3d(capsys):
    # Group is no longer a dedicated brush-build flag (ditched 2026-07-24 17:04) — it is set via
    # --prop Group=, whose schema validation is covered where the game schema is available; this unit
    # test (no schema on the search path) covers the schema-free at/csg/solidity baking.
    rc = dispatch(_brush_build_cube_args(
        at=(100.0, 200.0, 300.0), csg="subtract", solidity="semisolid"))
    assert rc == 0
    out = capsys.readouterr().out
    level = parse_t3d(out)
    a = next(iter(level.actors.values()))
    props = dict(a.props)
    assert props.get("CsgOper") == "CSG_Subtract"
    assert a.location == (100.0, 200.0, 300.0)
    from uedctl.builders import PF_SEMISOLID
    assert props.get("PolyFlags") == str(PF_SEMISOLID)


def test_it_emits_folder_and_label_carriers(capsys):
    # Generators author organization: --folder/--label emit the `// uedctl-folder:` / `// uedctl-labels:`
    # carriers that `actor add` reads back into the sidecars (2026-07-24 17:04). Pure emit — no schema.
    rc = dispatch(_brush_build_cube_args(folder="castle.tower", label=["lit", "hero"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert "// uedctl-folder: castle.tower" in out
    assert "// uedctl-labels: hero,lit" in out            # labels carrier is sorted, comma-joined


def test_brush_build_staircase_outputs_one_actor(capsys):
    # `brush build staircase` emits ONE non-convex-brush actor (decisions 2026-07-21 12:06),
    # unlike the spiral which still emits one slab per step.
    args = Namespace(
        cmd="brush", sub="build", shape="staircase",
        steps=6, depth=32.0, rise=16.0, breadth=128.0,
        at=(0.0, 0.0, 0.0),
        base_name=None, csg="add", solidity="solid", group=None, texture=None)
    rc = dispatch(args)
    assert rc == 0
    out = capsys.readouterr().out
    level = parse_t3d(out)
    assert len(level.actors) == 1
    a = next(iter(level.actors.values()))
    assert a.name == "Staircase"
    assert len(a.brush.polys) == 2 + 4 * 6


def test_brush_build_spiral_outputs_column_plus_wedge_actors(capsys):
    # `brush build spiral` emits one central-column actor + one wedge-tread actor per
    # step, so steps=4 -> 5 actors (column + 4 wedges).
    steps = 4
    args = Namespace(
        cmd="brush", sub="build", shape="spiral",
        steps=steps, inner_radius=48.0, step_width=32.0, rise=16.0, degrees_per_step=30.0,
        at=(0.0, 0.0, 0.0),
        base_name=None, csg="add", solidity="solid", group=None, texture=None)
    rc = dispatch(args)
    assert rc == 0
    out = capsys.readouterr().out
    level = parse_t3d(out)
    assert len(level.actors) == steps + 1


def _brush_build_spiral_args(**overrides):
    defaults = dict(
        cmd="brush", sub="build", shape="spiral",
        steps=4, inner_radius=48.0, step_width=32.0, rise=16.0, degrees_per_step=30.0,
        at=(0.0, 0.0, 0.0),
        base_name=None, csg="add", solidity="solid", group=None, texture=None)
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.mark.parametrize("bad_degrees", [200.0, -30.0])
def test_brush_build_spiral_bad_degrees_per_step_clean_exit2(capsys, bad_degrees):
    # validate_brush is winding/convexity-blind, so a >=180 or negative sweep would
    # silently emit a non-convex/inverted wedge; spiral_staircase guards it. The bad
    # value must surface in a clean exit-2 message, never a traceback.
    rc = dispatch(_brush_build_spiral_args(degrees_per_step=bad_degrees))
    assert rc == 2
    err = capsys.readouterr().err
    assert "degrees_per_step" in err and str(bad_degrees) in err
    assert "Traceback" not in err


def test_spiral_staircase_library_guard_still_rejects_a_nonpositive_inner_radius():
    # The CLI-side positive-dimension guard now catches `--inner-radius <= 0` first (see
    # test_builder_rejects_a_negative_dimension), so this pins the LIBRARY guard directly: a
    # non-CLI caller of builders.spiral_staircase must still be refused, not silently handed a
    # degenerate column.
    from uedctl.builders import spiral_staircase
    from uedctl.geometry import GeometryError
    with pytest.raises(GeometryError, match="inner_radius"):
        spiral_staircase(4, inner_radius=0.0, step_width=32.0, rise=16.0)


def test_brush_build_requires_no_level(capsys, monkeypatch):
    rc = dispatch(_brush_build_cube_args())
    assert rc == 0


def _brush_build_sheet_args(**overrides):
    defaults = dict(
        cmd="brush", sub="build", shape="sheet",
        width=256.0, height=128.0, plane="xz",
        at=(0.0, 0.0, 0.0),
        base_name=None, csg=None, solidity=None, group=None, texture=None, flags=[])
    defaults.update(overrides)
    return Namespace(**defaults)


def test_brush_build_sheet_flag_passthrough_bakes_poly_flags(capsys):
    # `brush build sheet --flag portal --flag translucent` OR-s both onto the sheet's
    # face at build time, ON TOP OF the default twosided|notsolid — a zone portal in one step.
    from uedctl.builders import PF_TWOSIDED, PF_NOTSOLID
    from uedctl.query import PF_NAMES
    bit = {name: b for b, name in PF_NAMES}
    rc = dispatch(_brush_build_sheet_args(flags=["portal", "translucent"]))
    assert rc == 0
    out = capsys.readouterr().out
    level = parse_t3d(out)
    a = next(iter(level.actors.values()))
    assert a.brush is not None and len(a.brush.polys) == 1
    f = a.brush.polys[0].flags
    assert f & PF_TWOSIDED and f & PF_NOTSOLID          # defaults kept
    assert f & bit["portal"] and f & bit["translucent"]  # requested flags baked in


def test_brush_build_sheet_no_flag_keeps_bare_defaults(capsys):
    from uedctl.builders import PF_TWOSIDED, PF_NOTSOLID
    rc = dispatch(_brush_build_sheet_args())
    assert rc == 0
    out = capsys.readouterr().out
    a = next(iter(parse_t3d(out).actors.values()))
    assert a.brush.polys[0].flags == (PF_TWOSIDED | PF_NOTSOLID)


def test_brush_build_sheet_bad_flag_rejected_by_parser():
    # argparse `choices` rejects an unknown flag name cleanly (SystemExit, no traceback).
    from uedctl.cli import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["brush", "build", "sheet", "--width", "256", "--height", "128", "--flag", "bogus"])


def test_brush_build_sheet_good_flag_accepted_by_parser():
    from uedctl.cli import build_parser
    ns = build_parser().parse_args(
        ["brush", "build", "sheet", "--width", "256", "--height", "128",
         "--flag", "Portal", "--flag", "translucent"])
    assert ns.flags == ["portal", "translucent"]   # case-folded via type=str.lower


# ---------------------------------------------------------------------------
# Feature 7 — --rotate on the generators (brush build / actor build)
# ---------------------------------------------------------------------------

from decimal import Decimal


def test_brush_build_rotate_sets_absolute_rotation_field(capsys):
    # yaw 90° → Yaw=16384 UU; SET absolutely (fresh actor is identity, no add-vs-override).
    rc = dispatch(_brush_build_cube_args(rotate=(Decimal(0), Decimal(16384), Decimal(0))))
    assert rc == 0
    out = capsys.readouterr().out
    a = next(iter(parse_t3d(out).actors.values()))
    assert dict(a.props).get("Rotation") == "(Pitch=0,Yaw=16384,Roll=0)"


def test_brush_build_rotate_identity_still_writes_the_rotator(capsys):
    # An EXPLICIT `--rotate 0,0,0` writes `(Pitch=0,Yaw=0,Roll=0)`. Omitting the property does not
    # mean "unrotated" — the engine substitutes the CLASS DEFAULT for an omitted property, and
    # `TNM.LavaSpitter` defaults `Rotation=(Pitch=16384,Yaw=0,Roll=0)`, so the old "identity → write
    # nothing" shortcut silently built it pitched 90° (2026-07-25). Not writing is reserved for
    # "the flag was not given" (see below).
    rc = dispatch(_brush_build_cube_args(rotate=(Decimal(0), Decimal(0), Decimal(0))))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Rotation=(Pitch=0,Yaw=0,Roll=0)" in out


def test_brush_build_rotate_warns_off_grid(capsys):
    # 45° yaw carries the box corners off the integer grid → stderr warning (never blocks emit).
    rc = dispatch(_brush_build_cube_args(rotate=(Decimal(0), Decimal(45), Decimal(0))))
    assert rc == 0
    cap = capsys.readouterr()
    assert "off" in cap.err and "grid" in cap.err
    assert "Rotation=" in cap.out                     # the actor still emits (warn is advisory)


def test_brush_build_no_rotate_flag_is_unchanged(capsys):
    rc = dispatch(_brush_build_cube_args(rotate=None))
    assert rc == 0
    assert "Rotation=" not in capsys.readouterr().out


def test_brush_build_rotate_subquantum_stores_the_field_but_does_not_warn(capsys):
    # A sub-quantum rotate (uu low-2-bits only) RENDERS straight in the editor — the GMath table
    # truncates the low 2 bits — but the field is still stored verbatim, exactly as the editor
    # stores it, because omitting it would mean "the class default" and not "unrotated".
    # `is_identity_uu` therefore governs only the off-grid WARNING, not whether we write.
    rc = dispatch(_brush_build_cube_args(rotate=(Decimal(2), Decimal(0), Decimal(0))))
    assert rc == 0
    cap = capsys.readouterr()
    assert "Rotation=(Pitch=2,Yaw=0,Roll=0)" in cap.out
    assert cap.err.strip() == ""                 # no off-grid warning for a sub-quantum rotate


def _brush_build_cyl_args(**overrides):
    defaults = dict(
        cmd="brush", sub="build", shape="cylinder",
        height=64.0, radius=48.0, sides=8, angle_offset=0.0,
        at=(0.0, 0.0, 0.0), base_name=None, csg="add", solidity="solid",
        group=None, texture=None, mover_class=None, rotate=None)
    defaults.update(overrides)
    return Namespace(**defaults)


def test_cylinder_rotate_identity_does_not_warn_about_its_own_fractional_ring(capsys):
    # A cylinder's ring vertices are inherently fractional. An IDENTITY --rotate must not blame that
    # pre-existing off-grid geometry on --rotate (the warning is for rotation-INDUCED off-grid only).
    rc = dispatch(_brush_build_cyl_args(rotate=(Decimal(0), Decimal(0), Decimal(0))))
    assert rc == 0
    assert capsys.readouterr().err.strip() == ""


def test_actor_build_rotate_sets_rotation_field(capsys):
    args = Namespace(cmd="actor", sub="build", aclass="Engine.Light",
                     at=(0.0, 0.0, 0.0), base_name=None, prop=[],
                     rotate=(Decimal(0), Decimal(16384), Decimal(0)))
    rc = dispatch(args)
    assert rc == 0
    a = next(iter(parse_t3d(capsys.readouterr().out).actors.values()))
    assert dict(a.props).get("Rotation") == "(Pitch=0,Yaw=16384,Roll=0)"


# ---------------------------------------------------------------------------
# Step 4 — actor build <class>
# ---------------------------------------------------------------------------

def test_it_outputs_t3d_for_actor_build_light(capsys):
    # --prop is schema-validated since the prop-subcommands change (spec 2026-07-18 §7) —
    # mock the schema seam like the actor-prop tests do.
    from uedctl.uprops import Prop
    schema = {"lightbrightness": Prop(name="LightBrightness", kind="ByteProperty", array_dim=1,
                                      property_flags=0, type_ref=0, type_name=None,
                                      owner="Engine.Light")}
    args = Namespace(cmd="actor", sub="build", aclass="Engine.Light",
                     at=(0.0, 0.0, 128.0), base_name=None, prop=["LightBrightness=80"])
    with mock.patch("uedctl.dispatch._class_schema", lambda cls, project=None: dict(schema)):
        rc = dispatch(args)
    assert rc == 0
    out = capsys.readouterr().out
    level = parse_t3d(out)
    assert len(level.actors) == 1
    a = next(iter(level.actors.values()))
    assert a.cls == "Engine.Light"
    assert a.location == (0.0, 0.0, 128.0)
    props = dict(a.props)
    assert props.get("LightBrightness") == "80"


def test_actor_build_name_is_bare_class(capsys):
    args = Namespace(cmd="actor", sub="build", aclass="Engine.Light",
                     at=(0.0, 0.0, 0.0), base_name=None, prop=[])
    dispatch(args)
    out = capsys.readouterr().out
    level = parse_t3d(out)
    a = next(iter(level.actors.values()))
    assert a.name == "Light"


def test_actor_build_rejects_missing_dot(capsys):
    args = Namespace(cmd="actor", sub="build", aclass="Brush",
                     at=(0.0, 0.0, 0.0), prop=[])
    rc = dispatch(args)
    assert rc == 2
    assert "Brush" in capsys.readouterr().err


def test_actor_build_rejects_leading_dot(capsys):
    args = Namespace(cmd="actor", sub="build", aclass=".Light",
                     at=(0.0, 0.0, 0.0), prop=[])
    rc = dispatch(args)
    assert rc == 2


def test_actor_build_rejects_trailing_dot(capsys):
    args = Namespace(cmd="actor", sub="build", aclass="Engine.",
                     at=(0.0, 0.0, 0.0), prop=[])
    rc = dispatch(args)
    assert rc == 2


def test_actor_build_rejects_too_many_dots(capsys):
    args = Namespace(cmd="actor", sub="build", aclass="A.B.C",
                     at=(0.0, 0.0, 0.0), prop=[])
    rc = dispatch(args)
    assert rc == 2


def test_actor_build_rejects_prop_without_equals(capsys):
    args = Namespace(cmd="actor", sub="build", aclass="Engine.Light",
                     at=(0.0, 0.0, 0.0), prop=["LightBrightness"])
    rc = dispatch(args)
    assert rc == 2
    assert "LightBrightness" in capsys.readouterr().err


def _brush_build_mover_args(**overrides):
    defaults = dict(
        cmd="brush", sub="build", shape="cube",
        width=128.0, breadth=64.0, height=128.0,
        at=(0.0, 0.0, 0.0),
        base_name=None, csg=None, solidity=None, group=None, texture=None,
        mover_class="Engine.Mover")
    defaults.update(overrides)
    return Namespace(**defaults)


def test_brush_build_mover_emits_mover_class_no_csgoper(capsys):
    rc = dispatch(_brush_build_mover_args())
    out = capsys.readouterr().out
    assert rc == 0
    assert "Class=Engine.Mover" in out
    assert "CsgOper" not in out
    assert 'Name="Mover"' in out             # template = mover-class bare-name


def test_brush_build_mover_rejects_csg(capsys):
    rc = dispatch(_brush_build_mover_args(csg="add"))
    assert rc == 2
    assert "--csg is invalid with --mover-class" in capsys.readouterr().err


def test_brush_build_mover_rejects_solidity(capsys):
    rc = dispatch(_brush_build_mover_args(solidity="nonsolid"))
    assert rc == 2
    assert "--solidity is invalid with --mover-class" in capsys.readouterr().err


def test_brush_build_bare_mover_class_rejected(capsys):
    rc = dispatch(_brush_build_mover_args(mover_class="Mover"))
    assert rc == 2
    assert "must be Package.Name" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Positive-dimension guard — ONE shared validator across every builder verb
# ---------------------------------------------------------------------------

def _build_args(shape, **overrides):
    """A minimal VALID `brush build <shape>` Namespace, per shape, for the guard tests."""
    # Mirrors what the real parser produces: no --group on any builder (it was removed 2026-07-24
    # in favour of --prop Group=), and --prop is action="append" so its default is [], not None.
    common = dict(cmd="brush", sub="build", shape=shape, at=(0.0, 0.0, 0.0), base_name=None,
                  csg="add", solidity="solid", texture=None, prop=[], folder=None,
                  label=[], mover_class=None, rotate=None)
    per_shape = {
        "cube": dict(width=256.0, breadth=128.0, height=64.0),
        "cylinder": dict(height=64.0, radius=48.0, sides=8, angle_offset=0.0),
        "cone": dict(height=64.0, radius=48.0, sides=8, angle_offset=0.0),
        "sheet": dict(width=256.0, height=128.0, plane="xz", flags=[]),
        "staircase": dict(steps=6, depth=32.0, rise=16.0, breadth=128.0),
        "spiral": dict(steps=4, inner_radius=48.0, step_width=32.0, rise=16.0,
                       degrees_per_step=30.0),
    }[shape]
    return Namespace(**{**common, **per_shape, **overrides})


@pytest.mark.parametrize("shape, flag, dest", [
    ("cube", "--width", "width"),
    ("cube", "--breadth", "breadth"),
    ("cube", "--height", "height"),
    ("cylinder", "--height", "height"),
    ("cylinder", "--radius", "radius"),
    ("cone", "--height", "height"),
    ("cone", "--radius", "radius"),
    ("sheet", "--width", "width"),
    ("sheet", "--height", "height"),
    ("staircase", "--depth", "depth"),      # the reported bug: exited 0, emitted inside-out steps
    ("staircase", "--rise", "rise"),
    ("staircase", "--breadth", "breadth"),
    ("spiral", "--inner-radius", "inner_radius"),
    ("spiral", "--step-width", "step_width"),
    ("spiral", "--rise", "rise"),
])
def test_builder_rejects_a_negative_dimension(shape, flag, dest, capsys):
    # A negative length used to sail through and emit self-overlapping, inside-out geometry at
    # exit 0. Every builder verb now fails cleanly with ONE message shape naming flag and value.
    rc = dispatch(_build_args(shape, **{dest: -32.0}))
    assert rc == 2
    err = capsys.readouterr().err
    assert f"{flag} must be greater than 0" in err and "-32.0" in err
    assert "Traceback" not in err


@pytest.mark.parametrize("shape, flag, dest", [
    ("cube", "--height", "height"),
    ("cylinder", "--radius", "radius"),
    ("cone", "--height", "height"),
    ("sheet", "--width", "width"),
    ("staircase", "--rise", "rise"),
    ("spiral", "--step-width", "step_width"),
])
def test_builder_rejects_a_zero_dimension(shape, flag, dest, capsys):
    # Zero is rejected too: a zero-extent brush is degenerate (zero-area faces), not a valid shape.
    rc = dispatch(_build_args(shape, **{dest: 0.0}))
    assert rc == 2
    assert f"{flag} must be greater than 0" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_builder_rejects_a_non_finite_dimension(bad, capsys):
    # NaN compares False against EVERY operator, so a plain `value <= 0` guard waves `--width nan`
    # straight through — it then dies deep in the builder as "face has < 3 distinct vertices",
    # naming neither the flag nor the value and reading like a geometry bug. inf is rejected for
    # the same reason. The guard must report these like any other bad dimension.
    rc = dispatch(_build_args("cube", width=bad))
    assert rc == 2
    err = capsys.readouterr().err
    assert "--width must be greater than 0" in err and "Traceback" not in err


def test_builder_still_accepts_a_negative_angle_offset(capsys):
    # --angle-offset is an ANGLE, not a dimension: negative is meaningful (it rotates the
    # cross-section the other way) and must NOT be caught by the positive-dimension guard.
    assert dispatch(_build_args("cylinder", angle_offset=-22.5)) == 0
    assert parse_t3d(capsys.readouterr().out).actors                 # a real brush came out


def test_every_builder_shape_declares_its_positive_dimensions():
    # THE plug-in point's enforcement: enumerate what the CLI actually defines and require EVERY
    # float-typed flag of every `brush build <shape>` to be either guarded by
    # `_POSITIVE_BUILD_DIMS` or named in the explicit non-dimension allow-list below. A new shape
    # (e.g. `extrude`/`revolve`) therefore cannot ship a dimension outside the shared guard — this
    # test fails until the flag is either added to the table or consciously exempted here.
    #
    # Checking *every* float flag rather than only the `required=True` ones is deliberate: a
    # dimension that merely has a DEFAULT (`--thickness`, default 16.0) is exactly as capable of
    # building inside-out geometry, and an earlier version of this test missed that whole class.
    # The allow-list is the escape hatch for a float that is legitimately signed or has a tighter
    # rule of its own; adding to it is a visible, reviewable act.
    from argparse import _SubParsersAction
    from uedctl.cli import build_parser
    from uedctl.dispatch import _POSITIVE_BUILD_DIMS

    # Angles: signed by nature, or range-checked in builders.py (0 < sweep < 180).
    NON_DIMENSION_FLOATS = {"--angle-offset", "--degrees-per-step"}

    def sub(parser, name):
        for action in parser._actions:
            if isinstance(action, _SubParsersAction):
                assert name in action.choices, f"no subcommand {name!r}"
                return action.choices[name]
        raise AssertionError(f"{parser.prog} has no subcommands")

    build = sub(sub(build_parser(), "brush"), "build")
    shapes = next(a for a in build._actions if isinstance(a, _SubParsersAction)).choices
    assert set(shapes) == set(_POSITIVE_BUILD_DIMS), "a brush build shape has no guard-table row"
    for shape, shape_parser in shapes.items():
        float_flags = {opt for a in shape_parser._actions
                       if a.type is float for opt in a.option_strings}
        guarded = set(_POSITIVE_BUILD_DIMS[shape])
        assert guarded <= float_flags, (
            f"{shape}: guard table names {sorted(guarded - float_flags)}, which the parser does not "
            f"define as float flags")
        unguarded = float_flags - guarded - NON_DIMENSION_FLOATS
        assert not unguarded, (
            f"{shape}: float flag(s) {sorted(unguarded)} are neither in _POSITIVE_BUILD_DIMS nor "
            f"in NON_DIMENSION_FLOATS — add a guard-table row, or exempt them explicitly")
