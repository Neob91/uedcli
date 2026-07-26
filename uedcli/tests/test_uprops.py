"""Tests for uedcli.uprops — offline class-property extraction (the actor-prop schema source).
Run against the COMMITTED UED22 `.u` (version-agnostic parser; offline, no install/container)."""
from __future__ import annotations

import os

import pytest

from uedcli import uprops
from uedcli.uprops import SchemaError

_UED22 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uned", "UED22")
_ENGINE = os.path.join(_UED22, "Engine.u")

pytestmark = pytest.mark.skipif(not os.path.isfile(_ENGINE),
                                reason="committed UED22/Engine.u not present")


def _ued22_resolver(name):
    p = os.path.join(_UED22, f"{name}.u")
    return p if os.path.isfile(p) else None


# Full-chain inheritance bottoms out at Core.Object, but Core.u is NOT in the committed UED22 tree
# (only the v68 install has it). So inheritance tests use an install-backed resolver and skip when
# the gitignored install is absent (CI). This mirrors the real schema source (decision 2026-06-26
# 14:10: parse the real game .u, never stubs).
from uedcli.tests.conftest import install_system_root  # noqa: E402  (test-only install pointer)

_INSTALL = str(install_system_root())


def _install_resolver(name):
    p = os.path.join(_INSTALL, f"{name}.u")
    return p if os.path.isfile(p) else None


_HAVE_INSTALL = os.path.isfile(os.path.join(_INSTALL, "Core.u")) \
    and os.path.isfile(os.path.join(_INSTALL, "Engine.u"))


# --------------------------------------------------------------------------- load + integrity

def test_it_loads_a_package_to_eof():
    pkg = uprops.load_package(_ENGINE)
    assert pkg.name == "Engine"
    assert pkg.version in (61, 68, 69)
    assert len(pkg.exports) > 1000


def test_it_raises_on_a_non_package_file(tmp_path):
    bad = tmp_path / "x.u"
    bad.write_bytes(b"\x00" * 64)          # >= 36 bytes so the header unpacks; magic is wrong
    with pytest.raises(SchemaError, match=r"bad magic"):
        uprops.load_package(str(bad))


def test_it_raises_schema_error_not_struct_error_on_a_truncated_file(tmp_path):
    # A too-short file must be a clean SchemaError (no-fallback contract), never a bare struct.error
    # reaching the CLI as a traceback.
    bad = tmp_path / "x.u"
    bad.write_bytes(b"\xc1\x83\x2a\x9e\x03")   # correct magic but only 5 bytes
    with pytest.raises(SchemaError, match=r"too small"):
        uprops.load_package(str(bad))


def test_it_raises_schema_error_on_a_missing_file(tmp_path):
    with pytest.raises(SchemaError, match=r"cannot read package"):
        uprops.load_package(str(tmp_path / "nope.u"))


# --------------------------------------------------------------------------- typed decode

def test_it_decodes_an_enum_byte_property():
    # Brush.CsgOper is a ByteProperty -> ECsgOper enum (the spike's worked case)
    pkg = uprops.load_package(_ENGINE)
    props = {p.name: p for p in uprops.own_class_properties(pkg, "Brush", owner_fqcn="Engine.Brush")}
    assert "CsgOper" in props
    cs = props["CsgOper"]
    assert cs.kind == "ByteProperty"
    vals = uprops.enum_values(pkg, cs.type_ref)
    assert vals[:3] == ["CSG_Active", "CSG_Add", "CSG_Subtract"]
    assert "CSG_Deintersect" in vals


def test_prop_carries_local_enum_value_names():
    # resolve_class_properties discards the loaded Package, so a ByteProperty's LOCAL enum values
    # must ride on the Prop itself for actor-prop validation (CsgOper -> ECsgOper, a local export).
    pkg = uprops.load_package(_ENGINE)
    props = {p.name: p for p in uprops.own_class_properties(pkg, "Brush", owner_fqcn="Engine.Brush")}
    assert props["CsgOper"].enum_value_names[:3] == ("CSG_Active", "CSG_Add", "CSG_Subtract")
    assert props["PolyFlags"].enum_value_names == ()      # a non-enum scalar carries none


def test_it_decodes_a_static_array_bound():
    # Mover.KeyPos is KeyPos[8] (array_dim 8)
    pkg = uprops.load_package(_ENGINE)
    props = {p.name: p for p in uprops.own_class_properties(pkg, "Mover", owner_fqcn="Engine.Mover")}
    assert props["KeyPos"].array_dim == 8
    assert props["KeyRot"].array_dim == 8


def test_a_scalar_property_has_array_dim_one():
    pkg = uprops.load_package(_ENGINE)
    props = {p.name: p for p in uprops.own_class_properties(pkg, "Brush", owner_fqcn="Engine.Brush")}
    assert props["CsgOper"].array_dim == 1     # a scalar (vs Mover.KeyPos[8])


def test_class_lookup_is_case_insensitive():
    pkg = uprops.load_package(_ENGINE)
    assert uprops.class_export_index(pkg, "brush") == uprops.class_export_index(pkg, "Brush")


# --------------------------------------------------------------------------- inheritance

@pytest.mark.skipif(not _HAVE_INSTALL, reason="v68 install (Core.u/Engine.u) not present")
def test_it_inherits_props_up_the_super_chain():
    # Brush extends Actor extends Object — full chain crosses Engine -> Core. Must inherit
    # Actor.Location (owner Engine.Actor) and reach Core.Object without erroring.
    props = uprops.resolve_class_properties("Engine.Brush", resolver=_install_resolver)
    by_name = {p.name: p for p in props}
    assert by_name["CsgOper"].owner == "Engine.Brush"           # own
    assert by_name["Location"].owner == "Engine.Actor"          # inherited (local super)
    assert any(p.owner == "Core.Object" for p in props)         # inherited cross-package


@pytest.mark.skipif(not _HAVE_INSTALL, reason="v68 install not present")
def test_it_inherits_across_a_package_boundary():
    # A DeusEx class whose direct super is an IMPORT: prove the walk crosses into that package.
    deusex = os.path.join(_INSTALL, "DeusEx.u")
    pkg = uprops.load_package(deusex, name="DeusEx")
    crossing = None
    for e in pkg.exports:
        if pkg.name_of_ref(e["cls"]) in (None, "Class") and e["sup"] < 0:
            cls = pkg.names[e["nm"]]
            sup = uprops._super_fqcn(pkg, cls)
            if sup and not sup.startswith("DeusEx."):
                crossing = (cls, sup)
                break
    assert crossing is not None, "expected at least one DeusEx class with a cross-package super"
    cls, sup = crossing
    props = uprops.resolve_class_properties(f"DeusEx.{cls}", resolver=_install_resolver)
    assert any(not p.owner.startswith("DeusEx.") for p in props), \
        f"{cls} should inherit from {sup}'s package"


# --------------------------------------------------------------------------- no-fallback errors

def test_it_errors_when_a_package_cannot_be_resolved():
    with pytest.raises(SchemaError, match=r"not found on the schema search path"):
        uprops.resolve_class_properties("Nonexistent.Foo", resolver=lambda n: None)


def test_it_errors_on_a_missing_class():
    with pytest.raises(SchemaError, match=r"class not found"):
        uprops.resolve_class_properties("Engine.NoSuchClass", resolver=_ued22_resolver)


def test_it_requires_a_fully_qualified_class():
    with pytest.raises(SchemaError, match=r"fully qualified"):
        uprops.resolve_class_properties("Brush", resolver=_ued22_resolver)


def test_corrupt_class_body_raises_schema_error_not_traceback():
    """Review A1: the body decoders (script walker, defaults, struct members) must convert a
    corrupt-but-loadable package body into SchemaError — never a bare IndexError/struct.error
    (dispatch catches only SchemaError). Synthetic Package: a class export whose body offset
    points past EOF, and one whose body truncates mid-header."""
    from uedcli.uprops import Package, SchemaError, class_default_tags
    names = ["None", "Class", "Widget"]
    exports = [
        dict(cls=0, sup=0, outer=0, nm=2, flags=0, ssize=50, soff=1000),   # soff past EOF
    ]
    pkg = Package(name="X", version=68, names=names, imports=[], exports=exports, buf=b"\x00" * 8)
    try:
        class_default_tags(pkg, "Widget")
        assert False, "expected SchemaError"
    except SchemaError:
        pass

    exports2 = [dict(cls=0, sup=0, outer=0, nm=2, flags=0, ssize=6, soff=2)]
    pkg2 = Package(name="X", version=68, names=names, imports=[], exports=exports2,
                   buf=b"\x00" * 8)                     # truncates before ScriptSize
    try:
        class_default_tags(pkg2, "Widget")
        assert False, "expected SchemaError"
    except SchemaError:
        pass


def test_an_out_of_range_type_ref_raises_schema_error_not_traceback():
    """`resolve_type_export` is public (the typed compare compiles every struct property's member
    layout through it, and it now walks EVERY class of a level rather than only the classes with a
    struct DEFAULT), so a corrupt package must reach the caller as a named `SchemaError` — every
    caller catches that and turns it into a clean exit 2. An out-of-range IMPORT ref used to escape
    as a bare `IndexError`. (Cold review, 2026-07-25.)"""
    from uedcli.uprops import Package, SchemaError, resolve_type_export
    pkg = Package(name="X", version=68, names=["None"], imports=[], exports=[], buf=b"")
    for bad_ref in (-99999999, 99999999):
        try:
            resolve_type_export(pkg, bad_ref, "Struct", resolver=lambda n: None, _pkgs={})
            assert False, f"expected SchemaError for type_ref={bad_ref}"
        except SchemaError:
            pass
