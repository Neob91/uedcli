from unittest import mock
from uedctl.verify import verify_dx_matches, VerifyResult
from uedctl.model import parse_t3d
from uedctl.normalize import normalize_level, level_order
from uedctl.tests.conftest import StubDefaults


_T3D = ("Begin Map\nBegin Actor Class=Engine.Light Name=L1\n    Name=\"L1\"\nEnd Actor\nEnd Map")
_DEFAULTS = StubDefaults()          # no class has a non-zero default in these fixtures


def _lvl():
    lv = parse_t3d(_T3D)
    lv.order = level_order(lv)
    normalize_level(lv)
    return lv


def test_verify_passes_when_exported_matches_expected():
    with mock.patch("uedctl.store_export.export_dx_t3d", autospec=True, return_value=_T3D):
        result = verify_dx_matches(container="c", dx_path="/repo/Temp/x.dx", expected=_lvl(), defaults=_DEFAULTS)
    assert isinstance(result, VerifyResult) and result.ok is True


def test_verify_fails_when_exported_differs():
    moved = _T3D.replace('Name="L1"', 'Location=(X=99.000000,Y=0,Z=0)\n    Name="L1"')
    with mock.patch("uedctl.store_export.export_dx_t3d", autospec=True, return_value=moved):
        result = verify_dx_matches(container="c", dx_path="/repo/Temp/x.dx", expected=_lvl(), defaults=_DEFAULTS)
    assert result.ok is False and "mismatch" in result.message


def test_verify_mismatch_message_names_the_differing_actor():
    # black-box-materialize fix: the message must point at the FIRST differing actor+field.
    moved = _T3D.replace('Name="L1"', 'Location=(X=99.000000,Y=0,Z=0)\n    Name="L1"')
    with mock.patch("uedctl.store_export.export_dx_t3d", autospec=True, return_value=moved):
        result = verify_dx_matches(container="c", dx_path="/repo/Temp/x.dx", expected=_lvl(), defaults=_DEFAULTS)
    assert result.ok is False
    assert "'L1'" in result.message and "differs" in result.message


def test_verify_mismatch_message_names_the_PROPERTY_and_both_values():
    """The post-verify aborts the build with nothing written, so its message is the ONLY thing the
    user has to work from. It must name the property and show both sides — including, when one side
    simply omits the line, the class default that side therefore resolves to, which is usually the
    actual explanation."""
    d = StubDefaults({"Engine.Light": {("lightradius", 0): "64"}},
                     schema={"Engine.Light": {"LightRadius": "byte"}})
    built = _T3D.replace('Name="L1"', 'LightRadius=0\n    Name="L1"')
    with mock.patch("uedctl.store_export.export_dx_t3d", autospec=True, return_value=built):
        result = verify_dx_matches(container="c", dx_path="/repo/Temp/x.dx", expected=_lvl(),
                                   defaults=d)
    assert result.ok is False
    assert "'L1'" in result.message and "LightRadius" in result.message
    assert "built:    LightRadius=0" in result.message
    assert "class default 64" in result.message


def test_verify_mismatch_message_points_at_the_GEOMETRY_line_when_the_brush_differs():
    """A brush difference is not a property difference — the message must still land on the exact
    line rather than a bare 'the actors differ'."""
    brush = ("Begin Map\nBegin Actor Class=Engine.Brush Name=B1\n"
             "    Begin Brush Name=Model0\n       Begin PolyList\n"
             "         Begin Polygon Texture=T\n"
             "         Vertex   +00000.000000,+00000.000000,+000%s.000000\n"
             "         End Polygon\n"
             "       End PolyList\n    End Brush\n"
             '    Brush=Model\'MyLevel.Model0\'\n    Name="B1"\nEnd Actor\nEnd Map')
    expected = parse_t3d(brush % "64")
    expected.order = level_order(expected)
    normalize_level(expected)
    with mock.patch("uedctl.store_export.export_dx_t3d", autospec=True,
                    return_value=brush % "96"):
        result = verify_dx_matches(container="c", dx_path="/repo/Temp/x.dx", expected=expected,
                                   defaults=_DEFAULTS)
    assert result.ok is False and "GEOMETRY" in result.message
    assert "+00096.000000" in result.message and "+00064.000000" in result.message


def test_verify_mismatch_message_flags_a_missing_actor():
    # expected has L1+L2; the built map (got) has only L1 -> name L2 as MISSING.
    two = _T3D.replace("End Map",
                       'Begin Actor Class=Engine.Light Name=L2\n    Name="L2"\nEnd Actor\nEnd Map')
    expected = parse_t3d(two)
    expected.order = level_order(expected)
    normalize_level(expected)
    with mock.patch("uedctl.store_export.export_dx_t3d", autospec=True, return_value=_T3D):
        result = verify_dx_matches(container="c", dx_path="/repo/Temp/x.dx", expected=expected, defaults=_DEFAULTS)
    assert result.ok is False and "'L2'" in result.message and "MISSING" in result.message


def test_verify_qualifies_via_the_passed_driver_before_comparing():
    from uedctl.qualify import qualify_level_textures   # sanity: real function exists
    # `requalify_classes_to_loaded` is mocked out here, so the export must arrive already
    # qualified: an unresolvable class is fatal to the compare by design (no zero fallback).
    bare_export = ("Begin Map\nBegin Actor Class=Engine.Light Name=L1\n"
                   "    Name=\"L1\"\nEnd Actor\nEnd Map")
    with mock.patch("uedctl.store_export.export_dx_t3d", autospec=True, return_value=bare_export), \
         mock.patch("uedctl.qualify.qualify_live_level", autospec=True) as ql, \
         mock.patch("uedctl.qualify.requalify_classes_to_loaded", autospec=True) as qlc, \
         mock.patch("uedctl.qualify._read_loaded_classes", autospec=True, return_value={}):
        result = verify_dx_matches(container="c", dx_path="/repo/Temp/x.dx", expected=_lvl(), defaults=_DEFAULTS,
                                   qualify_driver=mock.Mock())
    ql.assert_called_once()                  # the qualify pass ran before the hash-compare
    qlc.assert_called_once()                 # expected's classes are reconciled to the live set (live-vs-live)
    assert result.ok is True                 # L1 has no brush/texture, so qualify is a no-op here


def test_verify_qualifies_expected_so_a_bare_expected_class_still_matches_a_qualified_got():
    # `expected` may carry a bare class from any creation path that doesn't qualify at
    # construction (e.g. actor add <file.t3d>, or stash/prefab content authored before class
    # qualification shipped) -- it must be qualified against the SAME loaded-class set as the
    # on-disk read, or a real content match looks like a post-verify mismatch (2026-06-21,
    # GPT-5.4 review).
    already_qualified_export = ("Begin Map\nBegin Actor Class=Engine.Light Name=L1\n"
                                "    Name=\"L1\"\nEnd Actor\nEnd Map")
    bare_expected = parse_t3d(
        "Begin Map\nBegin Actor Class=Light Name=L1\n    Name=\"L1\"\nEnd Actor\nEnd Map")
    bare_expected.order = level_order(bare_expected)
    normalize_level(bare_expected)
    with mock.patch("uedctl.store_export.export_dx_t3d", autospec=True,
                    return_value=already_qualified_export), \
         mock.patch("uedctl.qualify.qualify_live_level", autospec=True), \
         mock.patch("uedctl.qualify._read_loaded_classes", autospec=True,
                    return_value={"Light": {"Engine.Light"}}):
        result = verify_dx_matches(container="c", dx_path="/repo/Temp/x.dx",
                                   expected=bare_expected, defaults=_DEFAULTS,
                                   qualify_driver=mock.Mock())
    assert result.ok is True
    assert bare_expected.actors["L1"].cls == "Engine.Light"     # mutated in place
