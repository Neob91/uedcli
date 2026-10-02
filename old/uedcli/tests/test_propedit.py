"""propedit — the pure dot-path grammar / struct-text / typed-field internals (the verb-level
contracts live in test_actor_prop.py; these pin the grammar corners directly)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from uedcli import propedit as pe
from uedcli import typedprops as tp
from uedcli.propedit import PropEditError, TypedField, parse_token, split_struct_text
from uedcli.propedit.base import _prop_type_key
from uedcli.uprops import Prop as _Prop


# ── parse_token ──────────────────────────────────────────────────────────────────


def test_parse_token_paths():
    t = parse_token("VectArray.0.X=4", expect_value=True)
    assert (t.base, t.segs, t.value) == ("VectArray", (0, "X"), "4")
    t2 = parse_token("Rotation.Yaw", expect_value=False)
    assert (t2.base, t2.segs, t2.value) == ("Rotation", ("Yaw",), None)


def test_parse_token_value_may_contain_anything_after_first_equals():
    t = parse_token("Key==v", expect_value=True)
    assert t.value == "=v"
    t2 = parse_token("Key=", expect_value=True)          # empty value is a legal empty string
    assert t2.value == ""


def test_parse_token_rejects_paren_form_with_dot_hint():
    with pytest.raises(PropEditError, match=r"MultiSkins\.2"):
        parse_token("MultiSkins(2)=X", expect_value=True)


def test_parse_token_rejects_missing_equals_on_set_and_equals_on_get():
    with pytest.raises(PropEditError):
        parse_token("Key", expect_value=True)
    with pytest.raises(PropEditError):
        parse_token("Key=1", expect_value=False)


def test_parse_token_rejects_negative_index_and_bad_segments():
    with pytest.raises(PropEditError, match="negative"):
        parse_token("MultiSkins.-1=X", expect_value=True)
    with pytest.raises(PropEditError):
        parse_token("Bad..Path=1", expect_value=True)
    with pytest.raises(PropEditError):
        parse_token("1Key=1", expect_value=True)


# ── overlap rule ─────────────────────────────────────────────────────────────────


def test_check_overlaps():
    toks = [parse_token(s, expect_value=True)
            for s in ("Rotation.Pitch=1", "Rotation.Yaw=2", "Group=x")]
    pe.check_overlaps(toks)                              # disjoint members: fine
    with pytest.raises(PropEditError, match="conflicting"):
        pe.check_overlaps([parse_token("Rotation=(Yaw=1)", expect_value=True),
                           parse_token("rotation.pitch=2", expect_value=True)])


# ── split_struct_text ────────────────────────────────────────────────────────────


def test_split_struct_text_nested_and_malformed():
    assert split_struct_text("(A=1,B=(C=2,D=3))") == [("A", "1"), ("B", "(C=2,D=3)")]
    assert split_struct_text("()") == []
    assert split_struct_text("bare") is None
    assert split_struct_text("(A=1") is None
    assert split_struct_text("(A)") is None


def test_split_struct_text_is_quote_aware():
    # A comma (or an `=`) inside a quoted member value must NOT split/cut the member. This used to
    # split on any depth-0 comma, so `(Msg="a,b",Count=1)` parsed as three broken members and every
    # `actor prop get/set/find` over such a struct errored. Both parsers now share
    # `typedprops.split_struct_members` + `top_level_eq`, so they cannot drift apart again.
    assert split_struct_text('(Msg="a,b",Count=1)') == [("Msg", '"a,b"'), ("Count", "1")]
    assert split_struct_text('(Msg="x=y")') == [("Msg", '"x=y"')]
    assert split_struct_text('(Outer=(Msg="a,b"),N=2)') == [("Outer", '(Msg="a,b")'), ("N", "2")]
    assert split_struct_text('(Msg="a,b)c",N=2)') == [("Msg", '"a,b)c"'), ("N", "2")]
    assert split_struct_text('(Msg="unclosed)') is None      # an unclosed quote is not a literal


def test_single_quotes_are_object_reference_delimiters_and_are_tracked_as_such():
    """In T3D a single quote delimits an OBJECT REFERENCE — `Texture'Package.Name'`,
    `Model'MyLevel.Model823'` (`dev/docs/unrealed/t3d.md` "Property line forms"). It is always
    PAIRED, and a string literal is DOUBLE-quoted (`Name="Brush938"`), so an apostrophe inside a
    string is ordinary text the `"` quote state already swallows.

    Audited over the 39 committed `.t3d` files: 102 lines contain a single quote and every one has
    an EVEN count — there is no unpaired apostrophe anywhere in the corpus, and none of the 159
    struct-valued properties parses differently under quote tracking. So tracking `'` is right, and
    a bare unquoted `(Text=it's ok)` is not a T3D value form (it would be written
    `(Text="it's ok")`). Escaping of a quote INSIDE a literal is undocumented and untested here —
    neither parser claims to handle it."""
    assert split_struct_text("(Skin=Texture'Pkg.Name',N=2)") == \
        [("Skin", "Texture'Pkg.Name'"), ("N", "2")]
    assert split_struct_text('(Msg="it\'s ok",N=1)') == [("Msg", '"it\'s ok"'), ("N", "1")]
    # An UNPAIRED single quote leaves the literal unbalanced → "not a struct literal", the same
    # answer both parsers give. It cannot occur in real T3D (see the audit above).
    assert split_struct_text("(A=it's,N=1)") is None
    assert tp.parse_struct_text("(A=it's,N=1)") is None


def test_split_struct_text_drops_empty_members_like_typedprops_does():
    # A trailing or doubled comma used to be the one remaining DISAGREEMENT: typedprops skipped the
    # empty member, propedit returned None. Observable as `actor prop get Foo.A` erroring "not a
    # struct" on a stored `(A=1,)` that the post-verify compare read as a struct all along.
    assert split_struct_text("(A=1,)") == [("A", "1")]
    assert split_struct_text("(A=1, ,B=2)") == [("A", "1"), ("B", "2")]
    assert split_struct_text("(,)") == []
    assert split_struct_text("( )") == []


def test_split_struct_text_agrees_with_typedprops_parse_struct_text():
    # The two parsers differ ONLY in result shape (ordered+case-preserving vs casefolded dict).
    for text in ('(A=1,B=(C=2,D=3))', '(Msg="a,b",Count=1)', "()", "bare", "(A=1", "(A)",
                 '(Msg="x=y")', "(A=1))", "(A=1,)", "(A=1, ,B=2)", "(,)", "( )", "(,A=1)",
                 "(A=1,,)", '(Skin=Texture\'Pkg.Name\',N=2)', '(Msg="it\'s ok",N=1)'):
        pairs = split_struct_text(text)
        dct = tp.parse_struct_text(text)
        if pairs is None or dct is None:
            assert pairs is None and dct is None, text
        else:
            assert {k.casefold(): v for k, v in pairs} == dct, text


# ── format helpers ───────────────────────────────────────────────────────────────


def test_fmt_dec_trims():
    assert pe._fmt_dec(Decimal("4.000000")) == "4"
    assert pe._fmt_dec(Decimal("-17")) == "-17"
    assert pe._fmt_dec(Decimal("32.5")) == "32.5"


# ── TypedField (Location) pure semantics ─────────────────────────────────────────


def test_typed_field_whole_set_zero_fills_and_comma_requires_three():
    tf = TypedField(name="Location")
    tok = parse_token("Location=(Z=64)", expect_value=True)
    assert tf.apply(tok, "set", (Decimal(1), Decimal(2), Decimal(3))) == \
        (Decimal(0), Decimal(0), Decimal(64))            # ruling R2: zero-fill
    with pytest.raises(PropEditError):
        tf.apply(parse_token("Location=1,2", expect_value=True), "set", None)


def test_typed_field_member_and_unset():
    tf = TypedField(name="Location")
    loc = (Decimal(1), Decimal(2), Decimal(3))
    assert tf.apply(parse_token("Location.Y=50", expect_value=True), "set", loc) == \
        (Decimal(1), Decimal(50), Decimal(3))
    assert tf.apply(parse_token("Location.Y", expect_value=False), "unset", loc) == \
        (Decimal(1), Decimal(0), Decimal(3))
    assert tf.apply(parse_token("Location", expect_value=False), "unset", loc) is None


def test_typed_field_get_and_deep_path_rejected():
    tf = TypedField(name="Location")
    assert tf.get(parse_token("Location.Z", expect_value=False),
                  (Decimal(1), Decimal(2), Decimal("-17.5"))) == ("Location.Z", "-17.5")
    assert tf.get(None, None) == ("Location", "(X=0,Y=0,Z=0)")
    with pytest.raises(PropEditError):
        tf.get(parse_token("Location.X.Y", expect_value=False), None)
    with pytest.raises(PropEditError, match="valid: X, Y, Z"):
        tf.get(parse_token("Location.Q", expect_value=False), None)


# ── ClassCtx.members()/enums() cache keying (Critical 2 regression) ─────────────────────────────
# `ClassCtx` used to cache both by `id(prop)`: a plain memory address, which CPython commonly reuses
# for the VERY NEXT allocation once the previous object's only reference is dropped. A caller that
# builds one small throwaway `Prop` per array element (`dataclasses.replace(prop, array_dim=1)`,
# effective_props.py's old pattern) freed one such object per element, and the review's own corpus
# sweep found this collided DETERMINISTICALLY on real content: a later array's own throwaway element
# `Prop` landed on the exact freed address of an EARLIER, structurally different array's element,
# and `ClassCtx.members()` silently returned the wrong struct type's member list.


def _struct_prop(name: str, owner: str, type_ref: int, type_name: str) -> _Prop:
    return _Prop(name=name, kind="StructProperty", array_dim=1, property_flags=0,
                type_ref=type_ref, type_name=type_name, owner=owner)


def test_classctx_members_survives_a_freed_props_address_being_reused():
    """Direct reproduction against `ClassCtx.members()`, independent of any particular caller's
    Prop-construction pattern (mirrors the review's own `_scratch/probe_idreuse3.py`, scaled down):
    build struct A's `Prop`, resolve+cache its members, drop the ONLY reference (`del`) so CPython
    is free to reuse its address, then build struct B's `Prop` -- a genuinely DIFFERENT struct type
    -- via the identical construction call site (same field types/sizes, so CPython's per-size-class
    free list reuses A's just-freed block for B with very high reliability in this back-to-back
    pattern; `id(prop_b) == freed_id_a` is asserted below as a build-time self-check, not assumed).
    On the old `id()`-keyed cache this made `ctx.members(prop_b)` silently return struct A's cached
    members; keyed on `(owner, name, type_ref, type_name)` instead, it must return B's own."""
    calls: list[str] = []          # type_name only -- keeping the Prop itself would pin its address

    def load_members(prop: _Prop):
        calls.append(prop.type_name)
        return {"StructA": ["PitchA", "YawA"], "StructB": ["XB", "YB", "ZB"]}[prop.type_name]

    ctx = pe.ClassCtx(cls="Pkg.Whatever", load_schema=lambda: {}, load_defaults=lambda: {},
                      load_members=load_members, load_enums=lambda p: ())

    prop_a = _struct_prop("A", "Pkg.A", 501, "StructA")
    members_a = ctx.members(prop_a)
    assert members_a == ["PitchA", "YawA"]
    freed_id = id(prop_a)
    del prop_a                                            # the only reference -- CPython frees it now

    prop_b = _struct_prop("B", "Pkg.B", 502, "StructB")    # same construction shape/size as prop_a
    if id(prop_b) != freed_id:
        pytest.skip("CPython did not reuse the freed Prop's address in this run -- "
                    "the id()-keying bug this test pins is address-reuse-dependent")

    members_b = ctx.members(prop_b)
    assert members_b == ["XB", "YB", "ZB"]                 # NOT struct A's cached members
    assert calls == ["StructA", "StructB"]                 # both structs really loaded


def test_prop_type_key_differs_for_genuinely_different_struct_types():
    """Deterministic pin, no id() reuse required: `_prop_type_key` (the cache key `ClassCtx.members()`/
    `enums()` actually key on, `(owner, name, type_ref, type_name)`) must produce a DIFFERENT key for
    two `Prop`s naming genuinely different struct types. This is what makes the address-reuse test
    above pass regardless of whether CPython happens to reuse the freed address in a given run --
    the key is type-identity-based, so two different types can never collide on it even by luck."""
    prop_a = _struct_prop("A", "Pkg.A", 501, "StructA")
    prop_b = _struct_prop("B", "Pkg.B", 502, "StructB")
    assert _prop_type_key(prop_a) != _prop_type_key(prop_b)


def test_classctx_members_caches_by_type_not_by_object_identity():
    """The cache-HIT half of the same fix, equally id()-independent: two DISTINCT `Prop` objects that
    name the SAME real struct type (same owner/name/type_ref/type_name, different object identity)
    must share one cache entry -- resolving `.members()` for both triggers `load_members` only ONCE.
    Rules out a degenerate "just stop caching" fix, which would also make the id()-collision bug
    unreproducible but would be a silent performance regression rather than a real fix."""
    calls: list[str] = []

    def load_members(prop: _Prop):
        calls.append(prop.type_name)
        return ["PitchA", "YawA"]

    ctx = pe.ClassCtx(cls="Pkg.Whatever", load_schema=lambda: {}, load_defaults=lambda: {},
                      load_members=load_members, load_enums=lambda p: ())

    prop_1 = _struct_prop("A", "Pkg.A", 501, "StructA")
    prop_2 = _struct_prop("A", "Pkg.A", 501, "StructA")    # a distinct object, same declared type
    assert prop_1 is not prop_2

    assert ctx.members(prop_1) == ["PitchA", "YawA"]
    assert ctx.members(prop_2) == ["PitchA", "YawA"]
    assert calls == ["StructA"]                            # loaded once, not twice -- still a cache


def test_classctx_enums_survives_a_freed_props_address_being_reused():
    """Same mechanism as the members() test above, for `ClassCtx.enums()` -- the review found the
    identical `id()`-keying pattern there too (latent: no real corpus instance was found triggering
    it, but the bug class is the same)."""
    calls: list[str] = []          # type_name only -- keeping the Prop itself would pin its address

    def load_enums(prop: _Prop):
        calls.append(prop.type_name)
        return {"EnumA": ("A0", "A1"), "EnumB": ("B0", "B1", "B2")}[prop.type_name]

    def _enum_prop(name: str, owner: str, type_ref: int, type_name: str) -> _Prop:
        return _Prop(name=name, kind="ByteProperty", array_dim=1, property_flags=0,
                    type_ref=type_ref, type_name=type_name, owner=owner)

    ctx = pe.ClassCtx(cls="Pkg.Whatever", load_schema=lambda: {}, load_defaults=lambda: {},
                      load_members=lambda p: [], load_enums=load_enums)

    prop_a = _enum_prop("A", "Pkg.A", 601, "EnumA")
    names_a = ctx.enums(prop_a)
    assert names_a == ("A0", "A1")
    freed_id = id(prop_a)
    del prop_a

    prop_b = _enum_prop("B", "Pkg.B", 602, "EnumB")
    if id(prop_b) != freed_id:
        pytest.skip("CPython did not reuse the freed Prop's address in this run -- "
                    "the id()-keying bug this test pins is address-reuse-dependent")

    names_b = ctx.enums(prop_b)
    assert names_b == ("B0", "B1", "B2")                   # NOT enum A's cached names
    assert calls == ["EnumA", "EnumB"]
