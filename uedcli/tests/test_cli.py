import argparse
from decimal import Decimal

import pytest

from uedcli.cli.main import build_parser
from uedcli.cli.parsers._arguments import parse_bbox, parse_coord, parse_decimal, parse_pan


def test_parse_decimal_returns_exact_decimal():
    assert parse_decimal(" 32.5 ") == Decimal("32.5")
    assert parse_decimal("-16") == Decimal("-16")


@pytest.mark.parametrize("bad", ["abc", "", "1,2", "12x"])
def test_parse_decimal_rejects_non_numeric(bad):
    # `Decimal("abc")` raises decimal.InvalidOperation, an ArithmeticError argparse does NOT
    # convert — it would escape as a raw traceback. The validator must raise ArgumentTypeError.
    with pytest.raises(argparse.ArgumentTypeError):
        parse_decimal(bad)


@pytest.mark.parametrize("bad", ["nan", "NaN", "snan", "inf", "-inf", "Infinity"])
def test_parse_decimal_rejects_non_finite(bad):
    # Decimal CONSTRUCTS all of these; they must not survive into the model.
    with pytest.raises(argparse.ArgumentTypeError):
        parse_decimal(bad)


@pytest.mark.parametrize("bad", ["nan,0,0", "0,inf,0", "0,0,snan", "-inf,0,0"])
def test_parse_coord_rejects_non_finite_components(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_coord(bad)


@pytest.mark.parametrize("bad", ["nan,0,0,1,1,1", "0,0,0,1,inf,1"])
def test_parse_bbox_rejects_non_finite_components(bad):
    with pytest.raises(argparse.ArgumentTypeError):
        parse_bbox(bad)


def test_coord_and_bbox_keep_the_two_failure_modes_distinct():
    """"not a number" and "not finite" are DIFFERENT mistakes and must not collapse into one
    message — telling someone who typed `abc` that it "must be finite" describes a problem their
    input does not have. Both parsers carry the component's own reason through."""
    with pytest.raises(argparse.ArgumentTypeError, match="expected a number") as ei:
        parse_coord("abc,0,0")
    assert "finite" not in str(ei.value)
    with pytest.raises(argparse.ArgumentTypeError, match="must be finite"):
        parse_coord("inf,0,0")
    with pytest.raises(argparse.ArgumentTypeError, match="expected a number") as ei:
        parse_bbox("abc,0,0,1,1,1")
    assert "finite" not in str(ei.value)
    with pytest.raises(argparse.ArgumentTypeError, match="must be finite"):
        parse_bbox("inf,0,0,1,1,1")


@pytest.mark.parametrize("bad", ["nan,0", "0,inf", "1.5,0"])
def test_parse_pan_rejects_non_integer_and_non_finite(bad):
    # Pan is int-valued and does not route through parse_decimal — `int()` already rejects every
    # non-finite spelling with a ValueError argparse converts cleanly. Pinned so it stays true.
    with pytest.raises(argparse.ArgumentTypeError):
        parse_pan(bad)


def test_clip_offset_flag_rejects_bad_values_cleanly(capsys):
    # `brush clip --offset` is the renamed `--coord` (no alias — unreleased). Its type is
    # parse_decimal, so a non-numeric/non-finite value is a clean parser error (SystemExit 2),
    # never the decimal.InvalidOperation traceback the bare `Decimal` type used to leak.
    p = build_parser()
    assert p.parse_args(["brush", "clip", "-", "--axis", "z", "--offset", "128"]).offset == Decimal(128)
    for bad in ("abc", "inf"):
        with pytest.raises(SystemExit):
            p.parse_args(["brush", "clip", "-", "--axis", "z", "--offset", bad])
        assert "--offset" in capsys.readouterr().err


def test_clip_coord_flag_is_gone():
    # The old spelling is DELETED outright (no back-compat cruft), and shares no unambiguous
    # argparse prefix with a surviving option, so it is genuinely unrecognized.
    with pytest.raises(SystemExit):
        build_parser().parse_args(["brush", "clip", "-", "--axis", "z", "--coord", "128"])


def test_parse_coord_returns_decimal_triple():
    assert parse_coord("32.5,0,-16") == (Decimal("32.5"), Decimal("0"), Decimal("-16"))


def test_parse_coord_accepts_integers_and_surrounding_spaces():
    assert parse_coord(" 100 , 200 , 300 ") == (Decimal("100"), Decimal("200"), Decimal("300"))


def test_parse_coord_rejects_wrong_arity():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_coord("1,2")


def test_parse_coord_rejects_non_numeric():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_coord("1,x,3")


def test_parser_has_core_verbs():
    p = build_parser()
    # parse a query verb (--exact-class repeats on find, so cls is a list)
    ns = p.parse_args(["actor", "find", "--exact-class", "Brush"])
    assert ns.cmd == "actor" and ns.sub == "find" and ns.cls == ["Brush"]


def test_parser_find_subclass_of_and_exact_class_coexist():
    # the --class rename (2026-07-19): --class is gone; --exact-class + --subclass-of are the two
    # class filters (both repeatable, ORing within the class dimension)
    p = build_parser()
    ns = p.parse_args(["actor", "find", "--subclass-of", "Engine.Light",
                       "--subclass-of", "Engine.Mover", "--exact-class", "Engine.Brush"])
    assert ns.subclass_of == ["Engine.Light", "Engine.Mover"] and ns.cls == ["Engine.Brush"]


def test_parser_find_rejects_bare_class_as_unrecognized(capsys):
    # THE reason the survivor is spelled `--exact-class` and not `--class-exact`: argparse expands
    # any UNAMBIGUOUS prefix of a defined option, so while the flag was `--class-exact` a bare
    # `--class Light` abbreviated straight into it — silently restoring the exact-vs-subclass
    # footgun the 2026-07-19 rename existed to kill. `--exact-class` shares no prefix with
    # `--class`, so the old spelling is now genuinely UNRECOGNIZED. Assert the *reason* (the
    # unrecognized-argument error), not just a SystemExit — a bare SystemExit also passes when the
    # abbreviation is silently accepted and the parse fails later for some unrelated reason.
    with pytest.raises(SystemExit):
        build_parser().parse_args(["actor", "find", "--class", "Light"])
    assert "unrecognized arguments: --class" in capsys.readouterr().err


def test_parser_move_accepts_to_and_by():
    p = build_parser()
    ns = p.parse_args(["actor", "move", "L1", "--to", "1,2,3"])
    assert ns.to == (Decimal("1"), Decimal("2"), Decimal("3"))
    ns2 = p.parse_args(["actor", "move", "L1", "--by", "5,0,0"])
    assert ns2.by == (Decimal("5"), Decimal("0"), Decimal("0"))


def test_parser_brush_vertex_list():
    p = build_parser()
    ns = p.parse_args(["brush", "vertex", "list", "B1"])
    assert ns.cmd == "brush" and ns.sub == "vertex" and ns.vsub == "list" and ns.name == "B1"


def test_parser_facing_accepts_leading_dash_space_form():
    # usability nit (2026-07-19): `--facing -Z` (space form) must parse — argparse would otherwise
    # read the leading-dash token as an option. The `+` facings never had the problem.
    p = build_parser()
    for val in ("-X", "-Y", "-Z"):
        ns = p.parse_args(["brush", "poly", "find", "B1", "--facing", val])
        assert ns.facing == val
    ns = p.parse_args(["brush", "poly", "find", "B1", "--facing", "+Z"])
    assert ns.facing == "+Z"


def test_parser_brush_vertex_move_multiple_at_with_delta():
    p = build_parser()
    ns = p.parse_args(["brush", "vertex", "move", "B1",
                       "--at", "0,0,0", "--at", "64,0,0", "--by", "0,0,128"])
    assert ns.sub == "vertex" and ns.vsub == "move" and ns.name == "B1"
    assert ns.at == [(Decimal("0"), Decimal("0"), Decimal("0")),
                     (Decimal("64"), Decimal("0"), Decimal("0"))]
    assert ns.by == (Decimal("0"), Decimal("0"), Decimal("128"))
    assert ns.to is None


def test_parser_accepts_negative_coordinate_tokens():
    # A bare "-32,..." starts with '-'; the parser must treat it as a value, not an option.
    p = build_parser()
    ns = p.parse_args(["brush", "vertex", "move", "B1", "--at", "-32,-32,32", "--by", "0,0,-16"])
    assert ns.at == [(Decimal("-32"), Decimal("-32"), Decimal("32"))]
    assert ns.by == (Decimal("0"), Decimal("0"), Decimal("-16"))
    ns2 = p.parse_args(["actor", "move", "L1", "--to", "-100,-200,-300"])
    assert ns2.to == (Decimal("-100"), Decimal("-200"), Decimal("-300"))


def test_parser_brush_vertex_move_to_absolute():
    p = build_parser()
    ns = p.parse_args(["brush", "vertex", "move", "B1", "--at", "0,0,0", "--to", "8,8,8.5"])
    assert ns.to == (Decimal("8"), Decimal("8"), Decimal("8.5"))
    assert ns.by is None


def test_parser_level_preview_takes_shots_and_backend_flags():
    ns = build_parser().parse_args(["level", "preview", "at:0,0,0;rot:0,90",
                                    "orbit:@Keep;radius:600;azimuth:45",
                                    "--out-dir", "shots/", "--size", "640x480", "--fov", "90"])
    assert ns.shots == ["at:0,0,0;rot:0,90", "orbit:@Keep;radius:600;azimuth:45"]
    assert ns.out_dir == "shots/" and ns.size == "640x480" and ns.fov == 90.0
    assert not ns.game and not ns.native          # backend default (game) resolved in dispatch


def test_parser_level_preview_native_game_mutually_exclusive():
    import pytest
    with pytest.raises(SystemExit):
        build_parser().parse_args(["level", "preview", "at:0,0,0;rot:0,0",
                                   "--out-dir", "s", "--native", "--game"])


def test_parser_level_preview_shot_and_outdir_optional_at_argparse():
    # The "need a SHOT + --out-dir" requirement moved from argparse to dispatch so `--list-actors`
    # can run with neither; argparse now accepts both empty (dispatch enforces the real rule).
    a = build_parser().parse_args(["level", "preview", "--out-dir", "s"])   # no SHOT: OK at argparse
    assert a.shots == [] and a.out_dir == "s"
    a = build_parser().parse_args(["level", "preview", "at:0,0,0;rot:0,0"])  # no --out-dir: OK at argparse
    assert a.shots == ["at:0,0,0;rot:0,0"] and a.out_dir is None
    a = build_parser().parse_args(["level", "preview", "--game", "--map", "x.dx",
                                   "--list-actors", "Engine.PathNode", "--sample", "5"])
    assert a.list_actors == "Engine.PathNode" and a.sample == 5


def test_parser_actor_list_is_removed():
    # `actor list` was dropped as redundant with `actor find`; the parser must reject it.
    with pytest.raises(SystemExit):
        build_parser().parse_args(["actor", "list", "--name", "Brush*"])


def test_parser_actor_show():
    p = build_parser()
    ns = p.parse_args(["actor", "show", "Light1"])
    assert ns.cmd == "actor" and ns.sub == "show" and ns.name == "Light1"


def test_parser_actor_get_verb_is_retired():
    # `actor get` was retired by the prop-subcommands change (spec 2026-07-18 §7) —
    # `actor prop get` is the one reader.
    with pytest.raises(SystemExit):
        build_parser().parse_args(["actor", "get", "Light1", "LightBrightness"])


def test_parser_actor_prop_subcommands():
    p = build_parser()
    ns = p.parse_args(["actor", "prop", "set", "Light1", "LightBrightness=80",
                       "Rotation.Yaw=8192"])
    assert ns.sub == "prop" and ns.propsub == "set" and ns.name == "Light1"
    assert ns.tokens == ["LightBrightness=80", "Rotation.Yaw=8192"]
    ns = p.parse_args(["actor", "prop", "unset", "Light1", "LightHue"])
    assert ns.propsub == "unset" and ns.tokens == ["LightHue"]
    ns = p.parse_args(["actor", "prop", "get", "Light1", "LightBrightness", "--kv"])
    assert ns.propsub == "get" and ns.tokens == ["LightBrightness"] and ns.kv
    ns = p.parse_args(["actor", "prop", "get", "Light1"])           # dump-all form
    assert ns.tokens == [] and not ns.kv
    with pytest.raises(SystemExit):                                  # old flags removed
        p.parse_args(["actor", "prop", "Light1", "--set", "A=1"])


def test_parser_actor_delete():
    p = build_parser()
    ns = p.parse_args(["actor", "delete", "Brush1", "Brush2"])
    assert ns.names == ["Brush1", "Brush2"]


def test_parser_preview():
    p = build_parser()
    ns = p.parse_args(["actor", "preview", "B1", "B2", "--view", "front", "--out", "/tmp/out.pgm"])
    assert ns.names == ["B1", "B2"] and ns.view == "front" and ns.out == "/tmp/out.pgm"


def test_parser_actor_preview_flags():
    p = build_parser()
    ns = p.parse_args(["actor", "preview", "--from-t3d", "a.t3d", "b.t3d", "--frame", "Wall:2",
                       "--layout", "breakdown", "--brush-colors", "legend",
                       "--highlight", "Wall:1", "--highlight", "Roof:0,3", "--annotate", "highlighted",
                       "--frame-tightness", "0.5", "--show", "collision,light-range,sound-range",
                       "--out", "o.png"])
    assert ns.from_t3d == ["a.t3d", "b.t3d"] and ns.frame == "Wall:2"
    assert ns.layout == "breakdown" and ns.brush_colors == "legend"
    assert ns.highlight == ["Wall:1", "Roof:0,3"] and ns.frame_tightness == 0.5
    assert ns.annotate == "highlighted"
    assert ns.show == "collision,light-range,sound-range"
    assert ns.names == []                                  # names ignored under --from-t3d


def test_parser_actor_preview_frame_accepts_a_negative_leading_aabb():
    # A six-field --frame AABB whose first coord is negative parses as a VALUE, not mistaken for an
    # option — load-bearing on `_CoordArgumentParser._parse_optional`, so pin it (cold-review finding).
    ns = build_parser().parse_args(["actor", "preview", "W", "--frame", "-512,0,0,512,0,256",
                                    "--out", "o.png"])
    assert ns.frame == "-512,0,0,512,0,256"


def test_actor_preview_rejects_renamed_flags(capsys):
    # The migration-error shims for these eight old spellings were DELETED (no-back-compat rule), so
    # each is now simply an unrecognized argument. None of them is a prefix of a flag that survives,
    # so deleting the shim cannot silently resurrect one by argparse abbreviation — that is what this
    # asserts, by pinning the unrecognized-argument error rather than a bare SystemExit.
    for removed in ("--single", "--breakdown", "--zoom", "--zoom-region", "--zoom-factor",
                    "--show-collision", "--show-light-range", "--show-sound-range"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["actor", "preview", "B1", "--out", "o.png", removed])
        assert f"unrecognized arguments: {removed}" in capsys.readouterr().err


def test_actor_preview_annotate_default_matches_annotationspec_default():
    from uedcli.preview import AnnotationSpec, parse_annotation_spec
    ns = build_parser().parse_args(["actor", "preview", "B1", "--out", "o.png"])
    assert parse_annotation_spec(ns.annotate) == AnnotationSpec.default()   # CLI default == the canonical default


def test_actor_preview_png_flag_is_gone():
    # PNG is the only preview output, so the flag that used to select it was DELETED outright
    # (no-back-compat rule) — `--png` is now an unrecognized argument on every preview verb.
    for verb in (["actor", "preview", "B1"], ["stash", "preview", "s1"], ["prefab", "preview", "p1"]):
        with pytest.raises(SystemExit):
            build_parser().parse_args(verb + ["--out", "o.png", "--png"])


def test_parser_brush_preview_is_gone():
    with pytest.raises(SystemExit):                        # renamed to `actor preview`
        build_parser().parse_args(["brush", "preview", "B1", "--out", "o.png"])


def test_parser_brush_build_cube():
    p = build_parser()
    ns = p.parse_args(["brush", "build", "cube", "--width", "256", "--breadth", "128",
                       "--height", "64", "--at", "100,200,300", "--csg", "subtract"])
    assert ns.sub == "build" and ns.shape == "cube"
    assert (ns.width, ns.breadth, ns.height) == (256.0, 128.0, 64.0)
    assert ns.at == (Decimal("100"), Decimal("200"), Decimal("300")) and ns.csg == "subtract"
    assert ns.solidity is None             # default None (runtime falls back to "solid")


def test_parser_brush_build_base_name_and_no_legacy_name():
    p = build_parser()
    ns = p.parse_args(["brush", "build", "cube", "--width", "256", "--breadth", "128",
                       "--height", "64", "--base-name", "Merlon"])
    assert ns.base_name == "Merlon"
    with pytest.raises(SystemExit):                     # the old --name spelling is gone
        p.parse_args(["brush", "build", "cube", "--width", "1", "--breadth", "1",
                      "--height", "1", "--name", "Merlon"])


def test_parser_actor_build_base_name():
    p = build_parser()
    ns = p.parse_args(["actor", "build", "Engine.Light", "--base-name", "Torch"])
    assert ns.aclass == "Engine.Light" and ns.base_name == "Torch"
    ns2 = p.parse_args(["actor", "build", "Engine.Light"])
    assert ns2.base_name is None                        # default: fall back to the class name


def test_parser_brush_build_cylinder_defaults():
    p = build_parser()
    ns = p.parse_args(["brush", "build", "cylinder", "--height", "128", "--radius", "64"])
    assert ns.sub == "build" and ns.shape == "cylinder"
    assert ns.sides == 8 and ns.align_to_side is False


def test_parser_brush_build_staircase():
    p = build_parser()
    ns = p.parse_args(["brush", "build", "staircase", "--steps", "8", "--depth", "32",
                       "--rise", "16", "--breadth", "128", "--solidity", "semisolid"])
    assert ns.sub == "build" and ns.shape == "staircase"
    assert ns.steps == 8 and ns.solidity == "semisolid"


def test_parser_brush_build_spiral():
    p = build_parser()
    ns = p.parse_args(["brush", "build", "spiral", "--steps", "12", "--inner-radius", "48",
                       "--step-width", "96", "--rise", "16", "--angle-per-step", "4096"])
    assert ns.sub == "build" and ns.shape == "spiral"
    assert ns.inner_radius == 48.0
    assert ns.step_width == 96.0 and ns.angle_per_step == 4096


def test_parser_container_flag_is_removed():
    # The global --container flag was dropped; editors are per-command ephemeral.
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--container", "x", "actor", "find"])


def test_level_materialize_parser_flags():
    ns = build_parser().parse_args(["level", "materialize", "--out", "Maps/X.dx", "--overwrite"])
    assert ns.cmd == "level" and ns.sub == "materialize"
    assert ns.out == "Maps/X.dx" and ns.overwrite is True


def test_level_materialize_parser_defaults():
    ns = build_parser().parse_args(["level", "materialize"])
    assert ns.out is None and ns.overwrite is False


def test_level_materialize_parser_rejects_retired_apply_flags():
    import pytest
    for removed in ("--reconcile", "--to-map-file", "--git-commit", "--reapply"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["level", "materialize", removed])
    with pytest.raises(SystemExit):                         # `level apply` itself is gone
        build_parser().parse_args(["level", "apply"])


def test_it_parses_stash_capture_and_subverbs():
    p = build_parser()
    ns = p.parse_args(["stash", "capture", "Arch", "Post_L", "--id", "archway", "--from-t3d", "x.t3d"])
    assert (ns.cmd, ns.sub) == ("stash", "capture")
    assert ns.names == ["Arch", "Post_L"] and ns.id == "archway" and ns.from_t3d == ["x.t3d"]

    ns = p.parse_args(["stash", "apply", "archway", "--at", "512,0,128", "--no-group"])
    assert (ns.cmd, ns.sub, ns.id) == ("stash", "apply", "archway")
    assert ns.at == (Decimal(512), Decimal(0), Decimal(128)) and ns.no_group is True


def test_it_parses_prefab_apply_and_promote():
    p = build_parser()
    ns = p.parse_args(["prefab", "apply", "hangar/archway", "--group", "g1"])
    assert (ns.cmd, ns.sub, ns.name) == ("prefab", "apply", "hangar/archway") and ns.group == "g1"
    ns = p.parse_args(["stash", "promote", "archway", "--as", "hangar/archway"])
    assert (ns.cmd, ns.sub) == ("stash", "promote") and ns.as_name == "hangar/archway"


def test_it_parses_actor_preview():
    p = build_parser()
    ns = p.parse_args(["actor", "preview", "Brush41", "--out", "shot.png"])
    assert (ns.cmd, ns.sub) == ("actor", "preview") and ns.names == ["Brush41"] and ns.out == "shot.png"


def test_actor_preview_out_is_optional():
    # --out is optional: with none given it parses to None (dispatch then mints a temp path and prints
    # the absolute path it wrote).
    ns = build_parser().parse_args(["actor", "preview", "Brush41"])
    assert ns.out is None


def test_level_preview_parser_rejects_retired_flags():
    import pytest
    for removed in ("--mode", "--lit", "--rotate", "--at"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["level", "preview", "at:0,0,0;rot:0,0",
                                       "--out-dir", "o", removed, "x"])
def test_parser_actor_rotate_by_and_pivot():
    p = build_parser()
    ns = p.parse_args(["actor", "rotate", "L1", "L2", "--by", "0,90,0", "--pivot", "0,0,0"])
    assert ns.cmd == "actor" and ns.sub == "rotate" and ns.names == ["L1", "L2"]
    assert ns.by == (Decimal("0"), Decimal("90"), Decimal("0"))
    assert ns.pivot == (Decimal("0"), Decimal("0"), Decimal("0"))
    assert ns.pivot_actor is None


def test_parser_actor_rotate_negative_angles_and_pivot_actor():
    p = build_parser()
    ns = p.parse_args(["actor", "rotate", "B1", "--by", "-45,0,90", "--pivot-actor", "Pivot"])
    assert ns.by == (Decimal("-45"), Decimal("0"), Decimal("90"))
    assert ns.pivot_actor == "Pivot" and ns.pivot is None


def test_parser_actor_rotate_pivot_and_pivot_actor_are_mutually_exclusive():
    import pytest
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["actor", "rotate", "B1", "--by", "0,90,0",
                      "--pivot", "0,0,0", "--pivot-actor", "P"])


def test_parser_poly_set_parses_targets_texture_and_flags():
    p = build_parser()
    ns = p.parse_args(["brush", "poly", "set", "Wall1:3,5", "Wall2:all",
                       "--texture", "DeusExDeco.Textures.Wood",
                       "--add-flag", "translucent", "--add-flag", "unlit",
                       "--remove-flag", "masked"])
    assert ns.cmd == "brush" and ns.sub == "poly" and ns.polysub == "set"
    assert ns.targets == ["Wall1:3,5", "Wall2:all"]
    assert ns.texture == "DeusExDeco.Textures.Wood"
    assert ns.add_flags == ["translucent", "unlit"]
    assert ns.remove_flags == ["masked"]


@pytest.mark.parametrize("flag", ["--pan-to", "--pan-by"])
def test_parser_poly_set_no_longer_accepts_the_pan_flags(flag):
    # Pan moved to its own verb (`brush poly pan --to/--by`) and the old spelling was DELETED
    # outright — no alias, no no-op flag, no rename shim (CLAUDE.md "No back-compat cruft").
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["brush", "poly", "set", "Wall1:all", flag, "0,64"])


def test_parser_poly_set_rejects_an_unknown_flag_name():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["brush", "poly", "set", "Wall1:all", "--add-flag", "bogus"])


# --- brush poly pan / rotate / scale --------------------------------------------

def test_parser_poly_pan_parses_targets_and_absolute_pan():
    p = build_parser()
    ns = p.parse_args(["brush", "poly", "pan", "Wall1:3,5", "Wall2:all", "--to", "0,64"])
    assert ns.cmd == "brush" and ns.sub == "poly" and ns.polysub == "pan"
    assert ns.targets == ["Wall1:3,5", "Wall2:all"]
    assert ns.pan_to == (0, 64) and ns.pan_by is None


def test_parser_poly_pan_by_takes_a_negative_delta():
    p = build_parser()
    ns = p.parse_args(["brush", "poly", "pan", "Wall1:all", "--by", "-5,3"])
    assert ns.pan_by == (-5, 3) and ns.pan_to is None


def test_parser_poly_pan_to_and_by_are_mutually_exclusive():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["brush", "poly", "pan", "Wall1:all", "--to", "0,0", "--by", "1,1"])


def test_parser_poly_pan_requires_one_of_to_or_by():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["brush", "poly", "pan", "Wall1:all"])


def test_parser_poly_rotate_parses_a_signed_angle_in_rotation_units():
    p = build_parser()
    assert p.parse_args(["brush", "poly", "rotate", "Wall1:all", "--by", "16384"]).by == 16384
    assert p.parse_args(["brush", "poly", "rotate", "Wall1:all", "--by", "-16384"]).by == -16384


def test_parser_poly_rotate_requires_by():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["brush", "poly", "rotate", "Wall1:all"])


def test_parser_poly_rotate_rejects_a_non_integer_angle():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["brush", "poly", "rotate", "Wall1:all", "--by", "90.5"])


def test_parser_poly_scale_parses_a_float_factor_pair():
    p = build_parser()
    ns = p.parse_args(["brush", "poly", "scale", "Wall1:all", "--by", "2,0.5"])
    assert ns.polysub == "scale" and ns.by == (2.0, 0.5)


def test_parser_poly_scale_requires_by():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["brush", "poly", "scale", "Wall1:all"])


def test_parser_poly_scale_and_rotate_report_a_missing_by_identically(capsys):
    # `--by` is a plain required flag on both, NOT a one-member mutually-exclusive group holding a
    # place for `--to` (which needs the texture catalog and does not exist yet). A group of one
    # only degrades the message to "one of the arguments --by is required".
    p = build_parser()
    messages = []
    for verb in ("scale", "rotate"):
        with pytest.raises(SystemExit):
            p.parse_args(["brush", "poly", verb, "Wall1:all"])
        messages.append(capsys.readouterr().err.splitlines()[-1])
    assert all("the following arguments are required: --by" in m for m in messages), messages


@pytest.mark.parametrize("bad", ["2", "2,2,2", "x,2", "nan,1", "inf,1"])
def test_parser_poly_scale_rejects_a_malformed_factor_pair(bad):
    # A malformed --by must be a clean argparse error, never a traceback out of float()/the model.
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["brush", "poly", "scale", "Wall1:all", "--by", bad])


def test_substrate_stub_parses():
    from uedcli.cli.main import build_parser
    args = build_parser().parse_args(["substrate", "stub", "DeusExItems", "--force"])
    assert args.cmd == "substrate" and args.sub == "stub"
    assert args.package == "DeusExItems" and args.force is True


def test_substrate_stub_list_parses():
    from uedcli.cli.main import build_parser
    args = build_parser().parse_args(["substrate", "stub", "--list"])
    assert args.cmd == "substrate" and args.list is True


def test_texture_verb_tree_parses():
    p = build_parser()
    a = p.parse_args(["texture", "list", "--package", "P", "--group", "Ladder", "--masked",
                      "--unclassified", "--json"])
    assert a.sub == "list" and a.group == "Ladder" and a.masked is True and a.unclassified is True
    a = p.parse_args(["texture", "search", "rusty", "--tag", "metal", "--color", "grey"])
    assert a.terms == ["rusty"] and a.tag == ["metal"] and a.color == ["grey"]
    a = p.parse_args(["texture", "show", "P.Wall", "--json"])
    assert a.refs == ["P.Wall"] and a.json is True
    a = p.parse_args(["texture", "preview", "P.Wall", "--skeleton", "--out", "x.png"])
    assert a.refs == ["P.Wall"] and a.skeleton is True
    a = p.parse_args(["texture", "classify", "set", "P.Wall", "--tags", "a,b", "--colors", "grey",
                      "--force"])
    assert a.ref == "P.Wall" and a.tags == ["a", "b"] and a.colors == ["grey"] and a.force is True
    assert p.parse_args(["texture", "classify", "status", "--json"]).csub == "status"
    assert p.parse_args(["texture", "classify", "tags"]).csub == "tags"
    assert p.parse_args(["texture", "prewarm", "--package", "P"]).sub == "prewarm"


def test_materialize_parses_out():
    ns = build_parser().parse_args(["level", "materialize", "--out", "Maps/X.dx"])
    assert ns.out == "Maps/X.dx" and ns.overwrite is False


# ── Step 2: actor find subparser + validators ─────────────────────────────────


def test_actor_find_parses_all_flags():
    ns = build_parser().parse_args([
        "actor", "find",
        "--exact-class", "Engine.Light", "--exact-class", "Engine.Brush",
        "--group", "cells", "--group", "vents",
        "--name", "Helper*", "--name", "Light*",
        "--prop", "bHidden=True", "--prop", "Group=cells",
        "--kind", "point",
    ])
    assert ns.cmd == "actor" and ns.sub == "find"
    assert ns.cls == ["Engine.Light", "Engine.Brush"]
    assert ns.group == ["cells", "vents"]
    assert ns.name == ["Helper*", "Light*"]
    assert ns.prop == ["bHidden=True", "Group=cells"]
    assert ns.kind == "point"


def test_actor_find_defaults_are_empty_lists_and_none_kind():
    ns = build_parser().parse_args(["actor", "find"])
    assert ns.cls == [] and ns.group == [] and ns.name == [] and ns.prop == []
    assert ns.kind is None


def test_actor_find_prop_tokens_pass_through_raw():
    # --prop tokens are raw KEY[.PATH]=VALUE strings since the prop-subcommands change —
    # the dispatch handler parses them with the shared propedit grammar (malformed tokens
    # error there, exit 2, covered in test_dispatch.py).
    ns = build_parser().parse_args(["actor", "find", "--prop", "Location.X=512"])
    assert ns.prop == ["Location.X=512"]


def test_actor_find_errors_on_empty_class(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["actor", "find", "--exact-class", ""])
    assert exc.value.code == 2


def test_actor_find_errors_on_trailing_dot_class(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["actor", "find", "--exact-class", "Foo."])
    assert exc.value.code == 2


def test_actor_find_errors_on_dot_only_class(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["actor", "find", "--exact-class", "."])
    assert exc.value.code == 2


def test_actor_find_errors_on_leading_dot_class(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["actor", "find", "--exact-class", ".Foo"])
    assert exc.value.code == 2


def test_actor_find_errors_on_empty_group(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["actor", "find", "--group", ""])
    assert exc.value.code == 2


def test_actor_find_errors_on_whitespace_only_name(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["actor", "find", "--name", "  "])
    assert exc.value.code == 2


def test_actor_find_errors_on_bad_kind(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["actor", "find", "--kind", "blah"])
    assert exc.value.code == 2
