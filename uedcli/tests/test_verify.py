from unittest import mock
from uedcli.verify import verify_dx_matches, VerifyResult, decode_dx_level_offline
from uedcli.model import parse_t3d
from uedcli.normalize import normalize_level, level_order
from uedcli.tests.conftest import StubDefaults


_T3D = ("Begin Map\nBegin Actor Class=Engine.Light Name=L1\n    Name=\"L1\"\nEnd Actor\nEnd Map")
_DEFAULTS = StubDefaults()          # no class has a non-zero default in these fixtures


def _lvl(t3d=_T3D):
    lv = parse_t3d(t3d)
    lv.order = level_order(lv)
    normalize_level(lv)
    return lv


def _verify(built_t3d, expected, defaults, **kw):
    """Run the post-verify with the built `.dx` decode STUBBED to `built_t3d` — the real decode
    (`decode_dx_level_offline`) reads a package file + game schema the offline suite has none of, so
    the got side is injected as an already-parsed level here (its class-ref qualification is covered
    by the materialize integration path, not these unit fixtures)."""
    with mock.patch("uedcli.verify.decode_dx_level_offline", return_value=_lvl(built_t3d)):
        return verify_dx_matches(dx_path="/tmp/x.dx", expected=expected, defaults=defaults,
                                 index=None, schema=None, **kw)


def test_verify_passes_when_exported_matches_expected():
    result = _verify(_T3D, _lvl(), _DEFAULTS)
    assert isinstance(result, VerifyResult) and result.ok is True


def test_verify_fails_when_exported_differs():
    moved = _T3D.replace('Name="L1"', 'Location=(X=99.000000,Y=0,Z=0)\n    Name="L1"')
    result = _verify(moved, _lvl(), _DEFAULTS)
    assert result.ok is False and "mismatch" in result.message


def test_verify_mismatch_message_names_the_differing_actor():
    # black-box-materialize fix: the message must point at the FIRST differing actor+field.
    moved = _T3D.replace('Name="L1"', 'Location=(X=99.000000,Y=0,Z=0)\n    Name="L1"')
    result = _verify(moved, _lvl(), _DEFAULTS)
    assert result.ok is False
    assert "'L1'" in result.message and "differs" in result.message


def test_verify_mismatch_message_names_the_PROPERTY_and_both_values():
    """The post-verify aborts the build with nothing written, so its message is the ONLY thing the
    user has to work from. It must name the property and show both sides — including, when one side
    simply omits the line, the class default that side therefore resolves to."""
    d = StubDefaults({"Engine.Light": {("lightradius", 0): "64"}},
                     schema={"Engine.Light": {"LightRadius": "byte"}})
    built = _T3D.replace('Name="L1"', 'LightRadius=0\n    Name="L1"')
    result = _verify(built, _lvl(), d)
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
    expected = _lvl(brush % "64")
    result = _verify(brush % "96", expected, _DEFAULTS)
    assert result.ok is False and "GEOMETRY" in result.message
    assert "+00096.000000" in result.message and "+00064.000000" in result.message


def test_verify_passes_when_poly_texture_differs_only_by_group_segment():
    # The trunk stores a poly texture 2-part (`Pkg.Name`); the offline .dx decode renders it 3-part
    # (`Pkg.Group.Name`) from the import table -- same face. It must PASS, not report a GEOMETRY diff.
    brush = ("Begin Map\nBegin Actor Class=Engine.Brush Name=B1\n"
             "    Begin Brush Name=Model0\n       Begin PolyList\n"
             "         Begin Polygon Texture=%s\n"
             "         Vertex   +00000.000000,+00000.000000,+00000.000000\n"
             "         End Polygon\n       End PolyList\n    End Brush\n"
             '    Brush=Model\'MyLevel.Model0\'\n    Name="B1"\nEnd Actor\nEnd Map')
    expected = _lvl(brush % "NYCBar.BarSign_Bb")            # trunk: 2-part
    result = _verify(brush % "NYCBar.Misc.BarSign_Bb", expected, _DEFAULTS)  # built: 3-part
    assert result.ok is True
    # A genuinely different leaf still fails.
    bad = _verify(brush % "NYCBar.Misc.OtherSign", expected, _DEFAULTS)
    assert bad.ok is False and "GEOMETRY" in bad.message


def test_verify_mismatch_message_flags_a_missing_actor():
    # expected has L1+L2; the built map (got) has only L1 -> name L2 as MISSING.
    two = _T3D.replace("End Map",
                       'Begin Actor Class=Engine.Light Name=L2\n    Name="L2"\nEnd Actor\nEnd Map')
    result = _verify(_T3D, _lvl(two), _DEFAULTS)
    assert result.ok is False and "'L2'" in result.message and "MISSING" in result.message


def test_verify_drops_editor_spawned_cameras_absent_from_the_trunk():
    # The editor spawns viewport Engine.Camera actors on build; the trunk has none, so they must be
    # dropped from the got side (an authored camera would be in expected by name and kept).
    built = _T3D.replace("End Map",
                         'Begin Actor Class=Engine.Camera Name=Camera6\n    Name="Camera6"\n'
                         'End Actor\nEnd Map')
    result = _verify(built, _lvl(), _DEFAULTS)
    assert result.ok is True                 # the extra Camera6 is dropped, not a mismatch


def test_verify_per_game_ignore_drops_a_prop_the_built_map_lacks():
    # bOwned is authored but the editor's engine can't round-trip it (per-game ignore); the built
    # map omits it, the trunk has it -> ignoring it makes the verify pass.
    d = StubDefaults(schema={"Engine.Light": {"bOwned": "bool"}})
    expected = _lvl(_T3D.replace('Name="L1"', 'bOwned=True\n    Name="L1"'))
    result = _verify(_T3D, expected, d, ignore=frozenset({("engine.light", "bowned")}))
    assert result.ok is True
