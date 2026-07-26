"""propedit — the pure dot-path grammar / struct-text / typed-field internals (the verb-level
contracts live in test_actor_prop.py; these pin the grammar corners directly)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from uedcli import propedit as pe
from uedcli.propedit import PropEditError, TypedField, parse_token, split_struct_text


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
