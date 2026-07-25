"""Value semantics of the typed compare (`uedctl.typedprops`) — the layer that makes the H3
post-verify compare VALUES instead of text. Everything here is pure: no packages, no resolver.
The schema-aware half (compiling a `.u` property into a `Field`) lives in `classdefaults`, and the
end-to-end behaviour is covered in `test_normalize.py`."""
from uedctl import typedprops as tp
from uedctl.typedprops import ABSENT, Field, typed_value, zero_value


F_FLOAT = Field(tp.FLOAT)
F_INT = Field(tp.INT)
F_BOOL = Field(tp.BOOL)
F_NAME = Field(tp.NAME)
F_STR = Field(tp.STRING)
F_VEC = tp.FVECTOR_FIELD
F_ROT = Field(tp.STRUCT, members=(("pitch", F_INT), ("yaw", F_INT), ("roll", F_INT)))


# --- keys ---------------------------------------------------------------------------------------

def test_a_static_array_element_keys_off_its_own_index():
    assert tp.prop_key("KeyPos(1)") == ("keypos", 1)
    assert tp.prop_key("LightRadius") == ("lightradius", 0)
    assert tp.key_text(("keypos", 1)) == "keypos(1)"


# --- struct literals ----------------------------------------------------------------------------

def test_a_struct_literal_splits_on_top_level_commas_only():
    """A nested struct or a comma inside a quoted string must not split a member — `MainScale`'s
    `(Scale=(X=1,Y=1,Z=1),SheerRate=0,SheerAxis=SHEER_ZX)` is the everyday case."""
    assert tp.parse_struct_text("(Scale=(X=1,Y=2,Z=3),SheerRate=0,SheerAxis=SHEER_ZX)") == {
        "scale": "(X=1,Y=2,Z=3)", "sheerrate": "0", "sheeraxis": "SHEER_ZX"}
    assert tp.parse_struct_text('(Text="a,b",N=2)') == {"text": '"a,b"', "n": "2"}
    assert tp.parse_struct_text("()") == {}
    assert tp.parse_struct_text("64") is None            # not a struct literal at all
    assert tp.parse_struct_text("(Yaw)") is None         # no `name=value` — not one either


# --- scalars ------------------------------------------------------------------------------------

def test_a_float_compares_numerically_and_at_float32():
    """DEFECT 1: the trunk stores `StayOpenTime=4.0` and the class default renders `4`. Typed they
    are one float. Float32 is the precision UnrealEd stores every float at, so a full-precision
    authored value and its editor round-trip converge too."""
    assert typed_value("4.0", F_FLOAT) == typed_value("4", F_FLOAT)
    assert typed_value("43.552099", F_FLOAT) == typed_value("43.552097", F_FLOAT)
    assert typed_value("-0", F_FLOAT) == typed_value("0.000000", F_FLOAT)
    assert typed_value("4.5", F_FLOAT) != typed_value("4", F_FLOAT)


def test_an_int_is_decoded_VERBATIM_never_reduced():
    """An FRotator component is an `IntProperty` and UnrealEd stores it verbatim, over-range values
    included. `-131072 % 65536 == 0`, so any reduction would make an over-range rotator compare
    equal to an unrotated one."""
    assert typed_value("-131072", F_INT) == -131072
    assert typed_value("65536", F_INT) == 65536
    assert typed_value("-16384", F_INT) != 49152
    # ...and a non-integer literal is NOT coerced: truncating `4.9` to `4` would make malformed
    # input compare equal to a real 4. Neither T3D nor the default rendering writes an int that way.
    assert typed_value("4.9", F_INT) != 4


def test_an_enum_normalizes_a_NAME_and_an_ORDINAL_to_one_value():
    """T3D writes the enum name; `uprops` renders a struct-MEMBER enum default as the raw ordinal.
    Both must decode to the same value or a default-equal member never matches."""
    f = Field(tp.ENUM, enum=("SHEER_None", "SHEER_XY", "SHEER_XZ", "SHEER_YX", "SHEER_YZ",
                             "SHEER_ZX", "SHEER_ZY"))
    assert typed_value("SHEER_ZX", f) == typed_value("5", f) == 5
    assert typed_value("sheer_zx", f) == 5                       # FName: case-insensitive
    assert typed_value("SHEER_XY", f) != typed_value("SHEER_ZX", f)
    assert typed_value("SHEER_MADE_UP", f) == "sheer_made_up"    # unknown name kept, not guessed


def test_bools_names_and_strings_follow_their_own_case_rules():
    assert typed_value("False", F_BOOL) is False and typed_value("TRUE", F_BOOL) is True
    assert typed_value("Player", F_NAME) == typed_value("player", F_NAME)   # FName
    assert typed_value("Hello", F_STR) != typed_value("hello", F_STR)       # a real string


# --- the type's zero ----------------------------------------------------------------------------

def test_the_zero_of_each_type_comes_from_the_TYPE_not_the_text():
    """DEFECT 3. The editor omits a property equal to the class default, so an actor that states the
    type's zero and an export that omits the line are the same value — but only the declared type
    can say what that zero is. A `StrProperty` reading `0` is NOT zero."""
    assert zero_value(F_FLOAT) == 0.0 and typed_value("0.000000", F_FLOAT) == zero_value(F_FLOAT)
    assert zero_value(Field(tp.BYTE)) == 0 and typed_value("0", Field(tp.BYTE)) == 0
    assert zero_value(F_BOOL) is False and typed_value("False", F_BOOL) == zero_value(F_BOOL)
    assert zero_value(F_NAME) == "none" and typed_value("None", F_NAME) == zero_value(F_NAME)
    assert zero_value(F_STR) == "" and typed_value("0", F_STR) != zero_value(F_STR)
    assert zero_value(F_VEC) == {"x": 0.0, "y": 0.0, "z": 0.0}


def test_an_untyped_property_has_NO_zero_and_never_matches_one():
    """NO FABRICATED DEFAULTS: with no declared type there is nothing to compare an omission
    against, so `ABSENT` equals nothing — a guess here is exactly how a wrong map passes."""
    assert zero_value(tp.UNKNOWN_FIELD) is ABSENT
    assert ABSENT != 0 and ABSENT != "" and ABSENT != False        # noqa: E712 — that is the point
    assert typed_value("0", tp.UNKNOWN_FIELD) != ABSENT


# --- struct expansion ---------------------------------------------------------------------------

def test_an_omitted_struct_member_takes_the_DEFAULT_member_not_zero():
    """The engine's own import rule (`unrealed/t3d.md` "Partial struct/array property values"), and
    DEFECT 2: an `Engine.Camera`'s `Location=(X=100,Y=200)` means Z=300, its default member."""
    assert typed_value("(X=100,Y=200)", F_VEC, "(X=-500,Y=-300,Z=300)") == {
        "x": 100.0, "y": 200.0, "z": 300.0}
    assert typed_value("(Yaw=16384)", F_ROT) == {"pitch": 0, "yaw": 16384, "roll": 0}
    assert typed_value("(Pitch=0)", F_ROT, "(Pitch=16384,Yaw=0,Roll=0)") == {
        "pitch": 0, "yaw": 0, "roll": 0}


def test_a_member_the_schema_does_not_know_is_kept_rather_than_dropped():
    assert typed_value("(Bogus=3)", F_ROT)["bogus"] == 3


def test_an_unknown_struct_layout_compares_by_its_NON_ZERO_members():
    """With no member list the members cannot be enumerated, so the canonical form is "the members
    that are not zero" — symmetric on both compare sides, and it never invents a member neither
    side mentions."""
    u = tp.UNKNOWN_FIELD
    assert typed_value("(X=0,Y=0,Z=0)", u) == typed_value("()", u) == {}
    assert typed_value("(X=0,Y=64,Z=0)", u) == typed_value("(Y=64)", u) == {"y": 64}
    assert typed_value("(X=1)", u) != typed_value("(Y=1)", u)
