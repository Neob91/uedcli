"""The REAL schema→`Field` compilation behind the typed compare (`classdefaults.ClassDefaults`),
driven against the game's own `.u` packages.

Everything else in the compare suite stubs the class info (`conftest.StubDefaults`) so it can run
with no game install; these tests are the other half — they exercise the code that actually decodes
`Engine.u`/`Core.u`/`DeusEx.u`: the Super-chain property walk, the defaults decode, ByteProperty enum
resolution and StructProperty member layouts (recursively, across packages). Without them a `uprops`
signature change could break every real `level materialize` with a fully green suite.

Install-backed and SKIPPED where the (gitignored) install is absent, mirroring `test_uprops.py`.
"""
from __future__ import annotations

import os

import pytest

from uedcli import typedprops
from uedcli.classdefaults import ClassDefaults
from uedcli.model import parse_t3d
from uedcli.normalize import canonical_actor_t3d, compare_view, level_order, normalize_level
from uedcli.tests.conftest import install_system_root, read_fixture

_INSTALL = str(install_system_root())


def _resolver(name):
    p = os.path.join(_INSTALL, f"{name}.u")
    return p if os.path.isfile(p) else None


_HAVE_INSTALL = all(os.path.isfile(os.path.join(_INSTALL, f"{p}.u"))
                    for p in ("Core", "Engine", "DeusEx", "TNM"))

pytestmark = pytest.mark.skipif(
    not _HAVE_INSTALL, reason="v68 install (Core/Engine/DeusEx/TNM .u) not present")


@pytest.fixture
def defaults():
    return ClassDefaults(_resolver)


def _level(body, cls, name="A1"):
    lv = parse_t3d(f"Begin Map\nBegin Actor Class={cls} Name={name}\n{body}"
                   f'    Name="{name}"\nEnd Actor\nEnd Map\n')
    lv.order = level_order(lv)
    return lv


def _same(defaults, a_body, b_body, *, cls):
    return (compare_view(_level(a_body, cls), defaults=defaults)
            == compare_view(_level(b_body, cls), defaults=defaults))


# --- the compiled types -------------------------------------------------------------------------

def test_it_compiles_the_real_declared_types(defaults):
    """Each `uprops.Prop` kind must land on the right `typedprops.Field`, or the compare falls back
    to untyped text and silently loses the default-equality it exists to provide."""
    info = defaults.for_class("Engine.Brush")
    assert info.field("location").members == typedprops.FVECTOR_FIELD.members   # 3 floats
    assert [k for k, _ in info.field("rotation").members] == ["pitch", "yaw", "roll"]
    assert all(f.kind == typedprops.INT for _, f in info.field("rotation").members)
    assert info.field("lightradius").kind == typedprops.BYTE      # a ByteProperty with NO enum
    assert info.field("polyflags").kind == typedprops.INT
    assert info.field("bhidden").kind == typedprops.BOOL
    assert info.field("tag").kind == typedprops.NAME
    assert info.field("brush").kind == typedprops.OBJECT
    assert info.field("csgoper").kind == typedprops.ENUM
    assert info.field("csgoper").enum[:3] == ("CSG_Active", "CSG_Add", "CSG_Subtract")
    assert info.field("nosuchproperty").kind == typedprops.UNKNOWN


def test_it_compiles_a_NESTED_struct_and_its_cross_package_enum(defaults):
    """`MainScale` is an `FScale` (declared in Core) holding an `FVector` plus an `ESheerAxis` enum —
    the deepest thing the compiler has to do: resolve a struct type across a package boundary,
    recurse into a member struct, and decode a member enum's value names."""
    scale = defaults.for_class("Engine.Brush").field("mainscale")
    assert [k for k, _ in scale.members] == ["scale", "sheerrate", "sheeraxis"]
    inner, rate, axis = (f for _, f in scale.members)
    assert [k for k, _ in inner.members] == ["x", "y", "z"]
    assert rate.kind == typedprops.FLOAT
    assert axis.kind == typedprops.ENUM
    assert axis.enum == typedprops.ESHEER_AXIS      # pins the schema-free fallback against Core.u


def test_the_decoded_defaults_are_the_real_shipped_values(defaults):
    """The three class defaults every compare rule in this repo is argued from."""
    assert defaults.for_class("Engine.Camera").typed_default(("location", 0)) == {
        "x": -500.0, "y": -300.0, "z": 300.0}
    assert defaults.for_class("TNM.LavaSpitter").typed_default(("rotation", 0)) == {
        "pitch": 16384, "yaw": 0, "roll": 0}
    assert defaults.for_class("DeusEx.DeusExMover").typed_default(("stayopentime", 0)) == 4.0


def test_a_struct_member_enum_default_decodes_as_an_ORDINAL_and_still_matches_the_T3D_NAME(defaults):
    """`uprops` renders a whole-property enum default as its NAME but a struct MEMBER enum as the raw
    byte: `MainScale`'s default really does come back with `SheerAxis=0`. Comparing by ordinal is
    what keeps that in the same value space as the T3D spelling `SHEER_ZX`."""
    info = defaults.for_class("Engine.Brush")
    assert info.defaults[("mainscale", 0)].endswith("SheerAxis=0)")     # the raw ordinal, as decoded
    assert typedprops.typed_value("SHEER_ZX", info.field("mainscale").members[2][1]) == 5


# --- the three defects, end to end against the real packages ------------------------------------

def test_a_float_property_equal_to_its_default_compares_equal_to_an_omitted_line(defaults):
    """DEFECT 1: this repo's own `uedcli/maps/probe-mv-a5` stores `StayOpenTime=4.0`; the class
    default renders `4` and the editor omits the line."""
    assert _same(defaults, "    StayOpenTime=4.0\n", "", cls="DeusEx.DeusExMover")
    assert not _same(defaults, "    StayOpenTime=5.0\n", "", cls="DeusEx.DeusExMover")


def test_an_omitted_location_axis_resolves_to_the_class_default_member(defaults):
    """DEFECT 2: `Engine.Camera` defaults `Location=(X=-500,Y=-300,Z=300)`, so the editor's
    `Location=(X=100,Y=200)` means Z=300 — not the 0 the parser fills for the geometry math."""
    assert _same(defaults, "    Location=(X=100.000000,Y=200.000000)\n",
                 "    Location=(X=100.000000,Y=200.000000,Z=300.000000)\n", cls="Engine.Camera")
    assert not _same(defaults, "    Location=(X=100.000000,Y=200.000000)\n",
                     "    Location=(X=100.000000,Y=200.000000,Z=0.000000)\n", cls="Engine.Camera")


def test_an_explicit_zero_scalar_compares_equal_to_an_omitted_line(defaults):
    """DEFECT 3: `Engine.Brush` does not default `LightRadius`, so its zero IS the default and the
    editor omits the line — while `Engine.Light` DOES default it to 64, where an explicit 0 is a
    real difference. Only the decoded schema can tell those two apart."""
    assert _same(defaults, "    LightRadius=0\n", "", cls="Engine.Brush")
    assert not _same(defaults, "    LightRadius=0\n", "", cls="Engine.Light")
    assert _same(defaults, "    LightRadius=64\n", "", cls="Engine.Light")


def test_the_lavaspitter_injectivity_guard_holds_against_the_real_default(defaults):
    """"Rotator explicitly zero" and "no rotator" are DIFFERENT levels for the one class that
    defaults `Rotation` — the second is pitched 90°."""
    assert _same(defaults, "    Rotation=(Pitch=0,Yaw=0,Roll=0)\n", "    Rotation=(Pitch=0)\n",
                 cls="TNM.LavaSpitter")
    assert not _same(defaults, "    Rotation=(Pitch=0,Yaw=0,Roll=0)\n", "", cls="TNM.LavaSpitter")
    assert not _same(defaults, "    Rotation=(Yaw=-131072)\n", "", cls="Engine.PlayerStart")


def test_the_editor_golden_round_trips_through_the_trunk_emit_with_REAL_class_info(defaults):
    """THE END-TO-END MATERIALIZE INVARIANT on a real `MAP EXPORT`, with the real schema: re-emitting
    the editor's own export through `canonical_actor_t3d` (the trunk write + import payload) and
    re-parsing it must compare EQUAL to the original — otherwise materializing a level captured from
    the editor would abort on its own post-verify. And the trunk bytes must be untouched by the
    compare."""
    lv = parse_t3d(read_fixture("level_small.t3d"))
    lv.order = level_order(lv)
    normalize_level(lv)
    for a in lv.actors.values():                     # what qualify does against the live editor
        if "." not in a.cls:
            a.cls = f"Engine.{a.cls}"
    before = {n: canonical_actor_t3d(a) for n, a in lv.actors.items()}
    reemitted = parse_t3d("Begin Map\n" + "\n".join(before.values()) + "\nEnd Map\n")
    reemitted.order = list(lv.order)
    assert compare_view(reemitted, defaults=defaults) == compare_view(lv, defaults=defaults)
    assert {n: canonical_actor_t3d(a) for n, a in lv.actors.items()} == before


def test_the_compare_resolves_each_DISTINCT_class_exactly_once(defaults):
    """PERF GUARD on the REAL resolver. Class resolution is the expensive half (a package load, a
    Super-chain walk, a defaults decode, struct/enum layouts — ~0.1-0.3 s cold), so it is memoized
    per class over one shared package map. A level has 5-60 distinct classes across hundreds of
    actors; resolving per-ACTOR instead would turn a ~1 s verify into minutes."""
    body = "".join(
        f'Begin Actor Class={cls} Name=A{i}\n    Name="A{i}"\nEnd Actor\n'
        for i, cls in enumerate(["Engine.Light"] * 5 + ["Engine.Brush"] * 5
                                + ["DeusEx.DeusExMover"] * 5))
    lv = parse_t3d("Begin Map\n" + body + "End Map\n")
    lv.order = level_order(lv)
    compare_view(lv, defaults=defaults)
    compare_view(lv, defaults=defaults)              # both compare sides share the memo
    assert defaults.resolutions == 3                 # three DISTINCT classes, 30 actor views


def test_an_unresolvable_class_raises_naming_the_actor_and_never_assumes_zero(defaults):
    """No fabricated defaults: a class whose package is not on the schema search path fails the
    compare loudly (the caller turns it into a clean exit 2), rather than being compared against an
    assumed-zero default."""
    from uedcli.uprops import SchemaError
    with pytest.raises(SchemaError, match="cannot verify actor 'Ghost1'"):
        compare_view(_level("", "NoSuchPackage.Ghost", name="Ghost1"), defaults=defaults)
    with pytest.raises(SchemaError, match="cannot verify actor 'Bare1'"):
        compare_view(_level("", "Light", name="Bare1"), defaults=defaults)
