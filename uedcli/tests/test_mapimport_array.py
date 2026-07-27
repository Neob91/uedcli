"""Dynamic-array (`array<T> Foo`) property decode, against REAL class schemas.

A dynamic array is the one property shape the decoder needed new machinery for, because of how the
engine stores its type. A property's declared type normally names its own kind, but an `array<T>`'s
type reference points at a separate hidden property object describing the ELEMENT — so the array's
type name is that object's NAME, and the element kind `T` is recorded nowhere else. Without following
that reference there is no way to know whether the bytes hold ints, object refs or structs.

`uprops.Prop.array_inner` is that followed reference. These tests check it against the two real
`array<T>` properties in the committed `Engine` package, so the plumbing is pinned against what the
engine declares rather than a hand-made schema.

Distinct from a STATIC array (`var int Foo[4]`), which is not one property value at all: the engine
writes a separate tagged property per element, each with its own index. Those already worked.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from uedcli import mapimport, uprops
from uedcli.classindex import ClassIndex
from uedcli.native.codec import write_ci
from uedcli.upackage import PT_ARRAY, Package, PropertyTag, SchemaError

_ROOT = Path(__file__).resolve().parent.parent.parent
_UED22 = _ROOT / "uned" / "UED22"

pytestmark = pytest.mark.skipif(not (_UED22 / "Engine.u").is_file(),
                                reason="committed UED22/Engine.u not present")


def _resolver(name: str) -> str | None:
    p = _UED22 / f"{name}.u"
    return str(p) if p.is_file() else None


def _prop(fqcn: str, name: str) -> uprops.Prop:
    for p in uprops.resolve_class_properties(fqcn, resolver=_resolver):
        if p.name.casefold() == name.casefold():
            return p
    raise AssertionError(f"{fqcn} declares no property {name}")


# ── the element kind resolves (Slice 1.3) ────────────────────────────────────────────────────

@pytest.mark.parametrize("fqcn,name,kind,type_name", [
    # `var const Actor Touching[…]` — an array of object references.
    ("Engine.Actor", "Touching", "ObjectProperty", "Actor"),
    # `var int SurfList[…]` — an array of plain ints; an int has no further type object, hence None.
    ("Engine.Decal", "SurfList", "IntProperty", None),
])
def test_the_element_kind_of_a_real_dynamic_array_resolves(fqcn, name, kind, type_name):
    """An `array<T>`'s element kind is recovered from the engine's own compiled schema.

    Both of these are genuine declarations in the shipped `Engine` package, so this pins the
    plumbing against reality: if following the hidden element reference ever broke, `array_inner`
    would come back `None` and every dynamic-array value in a map would become undecodable.
    """
    prop = _prop(fqcn, name)

    assert prop.kind == "ArrayProperty"
    assert prop.array_inner is not None, (
        f"{fqcn}.{name} lost its element property — dynamic arrays cannot be decoded without it")
    assert prop.array_inner.kind == kind
    assert prop.array_inner.type_name == type_name


def test_a_non_array_property_has_no_element_kind():
    """Only an `array<T>` carries an element property; nothing else grows the field spuriously."""
    assert _prop("Engine.Actor", "Location").array_inner is None


# ── the value decode (Slice 1.4) ─────────────────────────────────────────────────────────────

def _int_array_tag(name: str, values: list[int]) -> tuple[Package, PropertyTag]:
    """A `PT_ARRAY` tag holding `values` as ints, in the engine's wire form.

    The layout is a compact element COUNT followed by each element written exactly as that element
    kind is written anywhere else — for an int, four little-endian bytes.
    """
    raw = bytearray(write_ci(len(values)))
    for v in values:
        raw += v.to_bytes(4, "little", signed=True)
    pkg = Package(name="Synth", version=68, names=["None", name], imports=[], exports=[], buf=b"")
    tag = PropertyTag(name=name, ptype=PT_ARRAY, struct_name=None, array_index=0,
                      bool_value=None, raw=bytes(raw))
    return pkg, tag


def test_a_dynamic_int_array_decodes_to_its_elements():
    """Each element comes back in order, negatives included."""
    pkg, tag = _int_array_tag("SurfList", [1337, 42, 0, -7])

    values = uprops.decode_array_tag(pkg, tag, _prop("Engine.Decal", "SurfList"),
                                     resolver=_resolver, _pkgs={}, style=uprops.T3D_STYLE)

    assert values == ["1337", "42", "0", "-7"]


def test_an_empty_dynamic_array_decodes_to_nothing():
    """A stored-but-empty array is a count of zero and no elements — not an error."""
    pkg, tag = _int_array_tag("SurfList", [])

    assert uprops.decode_array_tag(pkg, tag, _prop("Engine.Decal", "SurfList"),
                                   resolver=_resolver, _pkgs={},
                                   style=uprops.T3D_STYLE) == []


def test_a_dynamic_array_whose_bytes_do_not_match_its_count_is_a_named_error():
    """A count that disagrees with the bytes present is a decode failure, never a short answer.

    Silently returning the elements that did fit would hand back a plausible, shorter array — the
    kind of corruption that survives every check and only shows up as missing content much later.

    Two guards can catch it depending on where the bytes run out — the per-element read hitting the
    end, or the whole-value length check afterwards — and both name the property. The test accepts
    either message rather than pinning which one fires, since that depends on the element size.
    """
    pkg, tag = _int_array_tag("SurfList", [1, 2, 3])
    truncated = PropertyTag(name=tag.name, ptype=tag.ptype, struct_name=None,
                            array_index=0, bool_value=None, raw=tag.raw[:-4])

    with pytest.raises(SchemaError, match=r"SurfList"):
        uprops.decode_array_tag(pkg, truncated, _prop("Engine.Decal", "SurfList"),
                                resolver=_resolver, _pkgs={}, style=uprops.T3D_STYLE)


# ── how it reaches the T3D text (Slice 2.1) ──────────────────────────────────────────────────

def _schema() -> mapimport.ImportSchema:
    return mapimport.ImportSchema(resolver=_resolver)


def test_a_dynamic_array_becomes_one_indexed_t3d_line_per_element():
    """`MAP EXPORT` writes an array as a separate indexed line per element, not one joined value."""
    pkg, tag = _int_array_tag("SurfList", [1337, 42])

    lines = mapimport.render_prop(pkg, tag, "Engine.Decal", schema=_schema())

    assert lines == [("SurfList(0)", "1337"), ("SurfList(1)", "42")]


def test_an_empty_dynamic_array_contributes_no_t3d_lines():
    """An empty array writes nothing at all — not `SurfList=()` and not an empty line."""
    pkg, tag = _int_array_tag("SurfList", [])

    assert mapimport.render_prop(pkg, tag, "Engine.Decal", schema=_schema()) == []


def test_an_array_the_installed_class_does_not_declare_is_a_named_error():
    """If the map holds an array the installed class package knows nothing about, import STOPS.

    The element kind lives only in the class schema, so an undeclared array is not decodable at
    all. Guessing would fabricate values; skipping it would drop authored content while reporting
    success. Both are worse than refusing, so the error names the property and the class.
    """
    pkg, tag = _int_array_tag("NoSuchArray", [1])

    with pytest.raises(SchemaError, match=r"NoSuchArray is not declared by Engine\.Decal"):
        mapimport.render_prop(pkg, tag, "Engine.Decal", schema=_schema())


def test_the_class_index_agrees_the_array_owners_are_real_classes():
    """Guard against the two probe classes above quietly disappearing from the shipped package.

    If `Engine.Decal` or `Engine.Actor` ever stops declaring its array, the tests above would still
    fail — but with a confusing "declares no property" error from the helper. This says plainly
    that the fixtures these tests are built on are still present.
    """
    paths = {p.stem.casefold(): str(p) for p in _UED22.glob("*.u")}
    idx = ClassIndex(_paths=paths, _stems={k: Path(v).stem for k, v in paths.items()})

    assert idx.descends_from("Engine.Decal", "Engine.Actor")
