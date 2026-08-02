"""Tests for generator-pattern helpers: translate_brush, name allocation,
brush build / actor build dispatch. (The CSG set-merge verbs live in
test_brush_merge.py.)"""

# ---------------------------------------------------------------------------
# Step 1c — translate_brush
# ---------------------------------------------------------------------------

def test_translate_brush_shifts_all_vertices():
    from uedcli.builders import cube, translate_brush
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
    from uedcli.builders import cube, translate_brush
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

from uedcli.cli.dispatch import dispatch
from uedcli.model import parse_t3d


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
    from uedcli.builders import PF_SEMISOLID
    assert props.get("PolyFlags") == str(PF_SEMISOLID)


def test_it_emits_folder_and_label_carriers(capsys):
    # Generators author organization: --folder/--label emit the `// uedcli-folder:` / `// uedcli-labels:`
    # carriers that `actor add` reads back into the sidecars (2026-07-24 17:04). Pure emit — no schema.
    rc = dispatch(_brush_build_cube_args(folder="castle.tower", label=["lit", "hero"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert "// uedcli-folder: castle.tower" in out
    assert "// uedcli-labels: hero,lit" in out            # labels carrier is sorted, comma-joined


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
        steps=steps, inner_radius=48.0, step_width=32.0, rise=16.0, angle_per_step=8192,
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
        steps=4, inner_radius=48.0, step_width=32.0, rise=16.0, angle_per_step=8192,
        at=(0.0, 0.0, 0.0),
        base_name=None, csg="add", solidity="solid", group=None, texture=None)
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.mark.parametrize("bad_uu", [40000, -8192, 32768, 0])
def test_brush_build_spiral_bad_angle_per_step_clean_exit2(capsys, bad_uu):
    # validate_brush is winding/convexity-blind, so a half-turn-or-more or negative sweep would
    # silently emit a non-convex/inverted wedge. The check lives at the dispatch boundary, in the
    # unreal rotation units the user typed and naming the flag they typed — the builder's own
    # guard is in degrees and names its parameter, so it could only report a value and a flag
    # that never appeared on the command line.
    rc = dispatch(_brush_build_spiral_args(angle_per_step=bad_uu))
    assert rc == 2
    err = capsys.readouterr().err
    assert "--angle-per-step" in err and str(bad_uu) in err
    assert "Traceback" not in err


def test_spiral_staircase_library_guard_still_rejects_a_nonpositive_inner_radius():
    # The CLI-side positive-dimension guard now catches `--inner-radius <= 0` first (see
    # test_builder_rejects_a_negative_dimension), so this pins the LIBRARY guard directly: a
    # non-CLI caller of builders.spiral_staircase must still be refused, not silently handed a
    # degenerate column.
    from uedcli.builders import spiral_staircase
    from uedcli.geometry import GeometryError
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
    from uedcli.builders import PF_TWOSIDED, PF_NOTSOLID
    from uedcli.query import PF_NAMES
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
    from uedcli.builders import PF_TWOSIDED, PF_NOTSOLID
    rc = dispatch(_brush_build_sheet_args())
    assert rc == 0
    out = capsys.readouterr().out
    a = next(iter(parse_t3d(out).actors.values()))
    assert a.brush.polys[0].flags == (PF_TWOSIDED | PF_NOTSOLID)


def test_brush_build_sheet_bad_flag_rejected_by_parser():
    # argparse `choices` rejects an unknown flag name cleanly (SystemExit, no traceback).
    from uedcli.cli.main import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["brush", "build", "sheet", "--width", "256", "--height", "128", "--flag", "bogus"])


def test_brush_build_sheet_good_flag_accepted_by_parser():
    from uedcli.cli.main import build_parser
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
        height=64.0, radius=48.0, sides=8, align_to_side=False,
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
    from uedcli.uprops import Prop
    schema = {"lightbrightness": Prop(name="LightBrightness", kind="ByteProperty", array_dim=1,
                                      property_flags=0, type_ref=0, type_name=None,
                                      owner="Engine.Light")}
    args = Namespace(cmd="actor", sub="build", aclass="Engine.Light",
                     at=(0.0, 0.0, 128.0), base_name=None, prop=["LightBrightness=80"])
    with mock.patch("uedcli.cli.resources.class_schema", lambda cls, project=None: dict(schema)):
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
        "cylinder": dict(height=64.0, radius=48.0, sides=8, align_to_side=False),
        "cone": dict(height=64.0, radius=48.0, sides=8, align_to_side=False),
        "sheet": dict(width=256.0, height=128.0, plane="xz", flags=[]),
        "staircase": dict(steps=6, depth=32.0, rise=16.0, breadth=128.0),
        "spiral": dict(steps=4, inner_radius=48.0, step_width=32.0, rise=16.0,
                       angle_per_step=8192),
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


def test_align_to_side_is_not_caught_by_the_positive_dimension_guard(capsys):
    # --align-to-side is a cross-section option, not a dimension: the guard must ignore it (and,
    # being a bool, it can no longer be a float flag needing an allow-list entry either).
    assert dispatch(_build_args("cylinder", align_to_side=True)) == 0
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
    from uedcli.cli.main import build_parser
    from uedcli.cli.commands.brush.build import _POSITIVE_BUILD_DIMS

    # Currently EMPTY, and that is the point: since the builder-angle units retrofit, every
    # builder angle is either a bool (--align-to-side) or an integer count of unreal rotation
    # units (--angle, --angle-per-step), so no float flag of any shape is exempt from the guard.
    # A future signed float flag would be added here, visibly and reviewably.
    NON_DIMENSION_FLOATS: set[str] = set()

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


# ---------------------------------------------------------------------------
# Builder angles are unreal rotation units (or a bool) at the CLI — the units retrofit
# ---------------------------------------------------------------------------

def _cli_brush(argv):
    """Run the REAL parser + dispatch and return the emitted brush of the first actor."""
    import io
    from uedcli.cli.main import build_parser
    from uedcli.cli.dispatch import dispatch as _dispatch
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _dispatch(build_parser().parse_args(argv))
    assert rc == 0, buf.getvalue()
    return next(iter(parse_t3d(buf.getvalue()).actors.values())).brush


def _verts(brush):
    return [tuple(round(float(c), 6) for c in v) for p in brush.polys for v in p.vertices]


def test_align_to_side_offsets_an_octagon_by_half_a_segment():
    # `--align-to-side` IS the old `--angle-offset 22.5` for an 8-gon: a face, not a vertex, faces
    # the axis, so the pillar sits flush against an axis-aligned wall.
    from uedcli.builders import cylinder, make_brush_actor
    built = _cli_brush(["brush", "build", "cylinder", "--height", "64", "--radius", "48",
                        "--sides", "8", "--align-to-side"])
    expect = make_brush_actor("Cylinder", cylinder(64, 48, 8, angle_offset=22.5)).brush
    assert _verts(built) == _verts(expect)


def test_align_to_side_is_half_a_segment_of_THIS_polygon_not_a_hardcoded_22_5():
    from uedcli.builders import cylinder, make_brush_actor
    built = _cli_brush(["brush", "build", "cylinder", "--height", "64", "--radius", "48",
                        "--sides", "6", "--align-to-side"])
    assert _verts(built) == _verts(make_brush_actor(
        "Cylinder", cylinder(64, 48, 6, angle_offset=30.0)).brush)         # 180/6, not 22.5
    assert _verts(built) != _verts(make_brush_actor(
        "Cylinder", cylinder(64, 48, 6, angle_offset=22.5)).brush)


def test_without_align_to_side_the_cross_section_is_unrotated():
    from uedcli.builders import cylinder, make_brush_actor
    built = _cli_brush(["brush", "build", "cylinder", "--height", "64", "--radius", "48"])
    assert _verts(built) == _verts(make_brush_actor("Cylinder", cylinder(64, 48, 8)).brush)


def test_angle_per_step_in_uu_reproduces_the_same_spiral_as_the_degrees_it_names():
    # 8192 uu IS 45°, and the spiral's default is now that (not the old 30°).
    from uedcli.builders import spiral_staircase, make_brush_actor
    built = _cli_brush(["brush", "build", "spiral", "--steps", "3", "--inner-radius", "48",
                        "--step-width", "32", "--rise", "16", "--angle-per-step", "8192"])
    expect = spiral_staircase(3, 48.0, 32.0, 16.0, degrees_per_step=45.0)[0]
    assert _verts(built) == _verts(make_brush_actor("Spiral0", expect).brush)


def test_the_spiral_default_is_8192_uu():
    assert _verts(_cli_brush(["brush", "build", "spiral", "--steps", "3", "--inner-radius", "48",
                              "--step-width", "32", "--rise", "16"])) == \
        _verts(_cli_brush(["brush", "build", "spiral", "--steps", "3", "--inner-radius", "48",
                           "--step-width", "32", "--rise", "16", "--angle-per-step", "8192"]))


def test_the_spiral_library_guard_still_refuses_a_half_turn_tread():
    # Unreachable from the CLI (dispatch checks the UU value first and names --angle-per-step), so
    # it is exercised HERE — an unreachable, untested guard is a second thing to keep true with
    # nothing enforcing it. It names its own PARAMETER, in degrees, for its direct callers.
    from uedcli.builders import spiral_staircase
    from uedcli.geometry import GeometryError
    with pytest.raises(GeometryError, match="degrees_per_step"):
        spiral_staircase(3, 48.0, 32.0, 16.0, degrees_per_step=200)


@pytest.mark.parametrize("argv", [
    ["brush", "build", "cylinder", "--height", "64", "--radius", "48", "--angle-offset", "22.5"],
    ["brush", "build", "cone", "--height", "64", "--radius", "48", "--angle-offset", "22.5"],
    ["brush", "build", "spiral", "--steps", "3", "--inner-radius", "48", "--step-width", "32",
     "--rise", "16", "--degrees-per-step", "45"],
])
def test_the_replaced_degree_flags_no_longer_parse(argv):
    # No back-compat cruft: the old spellings are DELETED, not aliased — argparse refuses them.
    from uedcli.cli.main import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


# ---------------------------------------------------------------------------
# Revolve segmentation — the fact the curved-texture shear formula rests on
# (spike: dev/docs/spikes/2026-07-26-poly-rotate-curved-track/)
# ---------------------------------------------------------------------------

import math

import pytest


@pytest.mark.parametrize("angle_deg,segments", [(90.0, 8), (90.0, 16), (60.0, 4), (180.0, 12)])
def test_revolve_facets_are_evenly_spaced_by_angle_over_segments(angle_deg, segments):
    """A `--segments N` revolve of a `--angle A` sweep divides the sweep into facets of EXACTLY
    `A/N`, with vertices only at those angles.

    Pinned because a whole family of texture-alignment numbers is derived from it, not because the
    spacing is surprising. The 2026-07-26 curved-track spike measured the seam texture mismatch of an
    orthogonally-framed run as `2*sin(dtheta/2) * half_width` texels, where `dtheta` is the per-facet
    turn — verified predictive at 8 segments (12.546781) and 16 (6.281331). Every one of those
    numbers, and the "add segments to halve the mismatch" guidance that follows from them, silently
    goes stale if the builder ever spaces facets differently (unevenly, or off by an end cap). This
    test is what makes that a red failure instead of quietly wrong documentation.
    """
    from uedcli.builders import revolve

    # Profile in the (u, v) plane: a rectangle at radii 512..640. axis="x" maps u->Y, v->Z, so the
    # sweep revolves about world Z and a vertex's angle is measured in the XY plane.
    brush = revolve([(512, 0), (640, 0), (640, 16), (512, 16)],
                    angle_deg=angle_deg, segments=segments, axis="x")

    angles = set()
    for poly in brush.polys:
        for vx, vy, _vz in poly.vertices:
            x, y = float(vx), float(vy)
            if math.hypot(x, y) < 1e-6:          # a vertex on the axis has no bearing
                continue
            angles.add(round(math.degrees(math.atan2(x, y)), 6))

    step = angle_deg / segments
    expected = [round(k * step, 6) for k in range(segments + 1)]
    got = sorted(angles)

    assert len(got) == len(expected), (
        f"expected {len(expected)} distinct facet angles for {segments} segments, got {len(got)}: "
        f"{got}")
    for want, have in zip(expected, got):
        assert abs(have - want) < 1e-4, f"facet angle {have} is not the expected {want}"


# ---------------------------------------------------------------------------
# cylinder/cone cap tiling above 16 sides
# (board: brush-build-cylinder-cone-sides-has-no-upper)
#
# An engine `FPoly` is convex and holds at most 16 vertices, so a `--sides > 16`
# end cap cannot be one N-gon face. cylinder/cone tile the cap into convex
# ≤16-vertex pieces via `profile.convex_pieces`, exactly like `extrude` — one
# cap face per end when the ring is convex and ≤16, else one face per piece.
# ---------------------------------------------------------------------------

from uedcli import profile as _profile
from uedcli.builders import cylinder, cone
from uedcli.geometry import validate_brush


def _cap_pieces(brush, item):
    """The vertex rings of the faces tagged `item` (Cap/Base)."""
    return [p.vertices for p in brush.polys if p.item == item]


def _side_count(brush):
    return sum(1 for p in brush.polys if p.item == "Side")


@pytest.mark.parametrize("sides", [8, 16])
def test_cylinder_le16_emits_exactly_one_cap_face_per_end(sides):
    # The convex invariant: a convex ≤16-vertex ring is ONE piece, so a plain prism still emits
    # exactly two cap faces (one Cap per end) and the ≤16 case is byte-identical to before tiling.
    b = cylinder(64, 48, sides=sides)
    assert len(_cap_pieces(b, "Cap")) == 2
    assert _side_count(b) == sides
    assert len(b.polys) == sides + 2


@pytest.mark.parametrize("sides", [8, 16])
def test_cone_le16_emits_exactly_one_base_face(sides):
    b = cone(64, 48, sides=sides)
    assert len(_cap_pieces(b, "Base")) == 1
    assert _side_count(b) == sides
    assert len(b.polys) == sides + 1


def _assert_pieces_tile_ring(pieces, sides):
    """Each piece is convex and ≤16 vertices, and the union of the pieces' (x,y) vertex sets is the
    full `sides`-vertex ring (tiling adds only diagonals — no new boundary vertices)."""
    union = set()
    for ring in pieces:
        assert 3 <= len(ring) <= 16, f"cap piece has {len(ring)} vertices, must be 3..16"
        ring2d = [(round(float(x), 6), round(float(y), 6)) for x, y, _z in ring]
        assert _profile.is_convex(ring2d), f"cap piece is not convex: {ring2d}"
        union |= set(ring2d)
    assert len(union) == sides, f"pieces cover {len(union)} distinct ring vertices, want {sides}"
    # And more than one piece — tiling actually happened above 16.
    assert len(pieces) > 1


@pytest.mark.parametrize("sides", [17, 24])
def test_cylinder_above16_tiles_both_caps(sides):
    b = cylinder(64, 48, sides=sides)
    validate_brush(b)
    assert _side_count(b) == sides
    caps = _cap_pieces(b, "Cap")
    # Two caps (top + bottom), each tiled into the same number of pieces.
    top = [r for r in caps if float(r[0][2]) > 0]
    bot = [r for r in caps if float(r[0][2]) < 0]
    assert len(top) == len(bot) == len(caps) // 2
    _assert_pieces_tile_ring(top, sides)
    _assert_pieces_tile_ring(bot, sides)
    # No face anywhere exceeds the FPoly bound.
    assert max(len(p.vertices) for p in b.polys) <= 16


@pytest.mark.parametrize("sides", [17, 24])
def test_cone_above16_tiles_the_base_cap(sides):
    b = cone(64, 48, sides=sides)
    validate_brush(b)
    assert _side_count(b) == sides
    _assert_pieces_tile_ring(_cap_pieces(b, "Base"), sides)
    # The apex end is a point, not a cap: no Cap/Base face lives at +z.
    assert all(float(v[2]) < 0 for r in _cap_pieces(b, "Base") for v in r)
    assert max(len(p.vertices) for p in b.polys) <= 16


def test_no_builder_face_exceeds_the_fpoly_16_vertex_bound():
    # The invariant the whole change exists to hold, swept across the boundary and well past it.
    for sides in (16, 17, 20, 24, 32, 64):
        for b in (cylinder(64, 48, sides=sides), cone(64, 48, sides=sides)):
            validate_brush(b)
            assert max(len(p.vertices) for p in b.polys) <= 16, f"sides={sides}"
