"""Typed property VALUES — the value semantics the post-verify compares with.

**The problem this solves.** UnrealEd's `MAP EXPORT` is *member-precise default-diffing*: it omits a
whole property whose value equals the class default, and omits an individual struct member equal to
the default member (`dev/docs/unrealed/t3d.md` "Partial struct/array property values"). uedcli's own
producers, by contrast, write every property and every member explicitly (a write path has no
resolver, and omitting a property means "the class default", which is not zero for every class). So
the built map's re-export and the trunk it was built from state the SAME values in DIFFERENT TEXT,
and a text compare aborts the build.

**The fix is to compare VALUES, not text.** A property's *effective value* is the stored value if
the actor states it, else the class default; a struct member's effective value is the stated member
if present, else the corresponding DEFAULT member (never zero). Values are decoded according to the
property's DECLARED TYPE, so `StayOpenTime=4.0` and a default rendered `4` are simply the same
float, `LightRadius=0` and an omitted `LightRadius` are simply the same byte, and an
`Engine.Camera`'s `Location=(X=100,Y=200)` is `(100, 200, 300)` — its default Z — rather than
`(100, 200, 0)`.

**Layering.** This module is PURE value semantics: it knows nothing about packages, `.u` files or
the resolver. The type of each property arrives as a `Field` tree, compiled from the decoded schema
by `classdefaults.ClassInfo`. It is used ONLY at the compare seam (`normalize.compare_view`, on a
throwaway copy) — never by `model.parse_t3d` (which is schema-free by design: it is also the trunk,
stash, prefab and generator-snippet reader, and a generator has no project context), and never by
`normalize.canonical_actor_t3d` / `canonical_level_hash`, whose bytes must not depend on which
packages happen to be installed.

**No fabricated defaults.** A property with no `Field` and no class default yields `ABSENT`, which
equals nothing — not even another `ABSENT`-adjacent zero. Guessing "it was probably zero" is the
exact class of bug the typed compare exists to remove (see `classdefaults`' no-fallback rule).
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field as _dc_field


# ── the type description ────────────────────────────────────────────────────────────────────────
#
# A `Field` is the compare-side projection of a `uprops.Prop`: just enough of the declared type to
# decode a T3D value text into a comparable Python value. `classdefaults` compiles it once per
# class (recursively, for struct members); this module never resolves anything itself.

FLOAT = "float"          # FloatProperty — compared at float32, the precision the editor stores
INT = "int"              # IntProperty — VERBATIM, never reduced mod anything (see FRotator below)
BOOL = "bool"            # BoolProperty
ENUM = "enum"            # ByteProperty WITH an enum — normalized to the ORDINAL, so a T3D enum
                         # NAME and a default rendered as a number are the same value
BYTE = "byte"            # ByteProperty with no enum — a plain 0..255 int
NAME = "name"            # NameProperty — an FName, so case-INSENSITIVE
STRING = "string"        # StrProperty — a real string, case-SENSITIVE
OBJECT = "object"        # Object/ClassProperty — `Class'Pkg.Name'` text, FName-ish (case-insensitive)
STRUCT = "struct"        # StructProperty — decoded member-wise
UNKNOWN = "unknown"      # no schema entry: text-shaped comparison, never a synthesized zero


@dataclass(frozen=True)
class Field:
    """The declared type of one property (or one struct member).

    `kind` is one of the constants above. `enum` is a ByteProperty's ordered value names (index ==
    ordinal). `members` is a struct's `(casefolded member name, Field)` pairs in DECLARED order;
    empty means "this is a struct whose member layout we could not resolve", which is compared
    leniently (see `_struct_value`) rather than guessed at."""
    kind: str = UNKNOWN
    enum: tuple[str, ...] = ()
    members: tuple[tuple[str, "Field"], ...] = ()


UNKNOWN_FIELD = Field(UNKNOWN)
FLOAT_FIELD = Field(FLOAT)
# `Location`/`MainScale`/`PostScale` are parsed OUT of the property list into typed model fields
# (`model.Actor.location` / `.main_scale` / `.post_scale`), so the compare re-renders them from the
# model rather than from raw text. Their layout is a MODEL fact, not a schema fact, which is why it
# is spelled here as well: it must work even for a level whose class schema is unavailable.
FVECTOR_FIELD = Field(STRUCT, members=(("x", FLOAT_FIELD), ("y", FLOAT_FIELD), ("z", FLOAT_FIELD)))
# `Core.Object.ESheerAxis`, ordinal-ordered (pinned against the real `Core.u` in
# `test_engine_facts`): T3D writes the NAME (`SHEER_ZX`) while a struct-member default decodes as
# the ordinal, so the compare needs the mapping even when no class schema is available.
ESHEER_AXIS = ("SHEER_None", "SHEER_XY", "SHEER_XZ", "SHEER_YX", "SHEER_YZ", "SHEER_ZX", "SHEER_ZY")
FSCALE_FIELD = Field(STRUCT, members=(("scale", FVECTOR_FIELD), ("sheerrate", FLOAT_FIELD),
                                      ("sheeraxis", Field(ENUM, enum=ESHEER_AXIS))))
# The three properties the MODEL types itself, with the layout the model already assumes. Used
# wherever the class schema has no usable entry for them (`classdefaults.ClassInfo.field`), so that
# an actor STATING one and an actor OMITTING it are typed the same way — an asymmetry there is a
# permanently unpassable post-verify for that actor.
MODEL_TYPED_FIELDS = {"location": FVECTOR_FIELD, "mainscale": FSCALE_FIELD,
                      "postscale": FSCALE_FIELD}


class _Absent:
    """Sentinel for "this property has no value we can name": the actor does not state it, the class
    does not default it, and there is no declared type to derive a zero from. It is equal only to
    itself, so it can never match a real value — deliberately NOT "0", because a `StrProperty` whose
    value happens to read `0` and an omitted property are different values, and equating them would
    let a wrong map pass the post-verify.

    Its self-equality never decides a comparison: a side that STATES the property has a real decoded
    value, and a property NEITHER side states is absent from both `own` maps and so is never looked
    up (`ActorValues.diff_key` walks the union of the two stated sets)."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<absent>"


ABSENT = _Absent()


# ── property keys ───────────────────────────────────────────────────────────────────────────────

_INDEXED_KEY = re.compile(r"^([^()]+)\((\d+)\)$")


def prop_key(raw_key: str) -> tuple[str, int]:
    """The `(casefolded name, static-array index)` a T3D property key compares/looks up under.

    T3D writes a static-array element as `KeyPos(1)=…` (`unrealed/t3d.md` "Indexed static-array
    form") and `uprops.resolve_class_defaults` keys that element `("keypos", 1)`; a scalar property
    is index 0. Getting this wrong is not cosmetic — every indexed element would compare against
    index 0's default."""
    m = _INDEXED_KEY.match(raw_key.strip())
    if m is None:
        return (raw_key.strip().casefold(), 0)
    return (m.group(1).strip().casefold(), int(m.group(2)))


def key_text(key: tuple[str, int]) -> str:
    """A `(name, index)` key back in its T3D spelling, for diagnostics: `("keypos", 1)` → `KeyPos(1)`."""
    return key[0] if key[1] == 0 else f"{key[0]}({key[1]})"


# ── struct literal parsing ──────────────────────────────────────────────────────────────────────

def parse_struct_text(text: str) -> dict[str, str] | None:
    """`(A=1,B=(X=2),C="a,b")` → `{"a": "1", "b": "(X=2)", "c": '"a,b"'}`; `None` when `text` is not
    a parenthesised struct literal at all.

    Splitting is depth- and quote-aware, so a nested struct or a comma inside a quoted string never
    splits a member. Member names are casefolded (UnrealScript identifiers are case-insensitive).
    An empty literal `()` yields `{}` — a struct that states no members, i.e. one that is entirely
    at its default."""
    t = text.strip()
    if not (t.startswith("(") and t.endswith(")")):
        return None
    inner = t[1:-1]
    out: dict[str, str] = {}
    depth, quote, start = 0, "", 0
    parts: list[str] = []
    for i, ch in enumerate(inner):
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(inner[start:i])
            start = i + 1
    parts.append(inner[start:])
    for part in parts:
        p = part.strip()
        if not p:
            continue
        eq = _top_level_eq(p)
        if eq is None:
            return None                      # not `name=value` — not a struct literal we understand
        out[p[:eq].strip().casefold()] = p[eq + 1:].strip()
    return out


def _top_level_eq(part: str) -> int | None:
    depth, quote = 0, ""
    for i, ch in enumerate(part):
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "=" and depth == 0:
            return i
    return None


# ── value decoding ──────────────────────────────────────────────────────────────────────────────

def _f32(x: float) -> float:
    """A float at IEEE single precision — the precision UnrealEd stores EVERY float property at.
    A value authored at full decimal precision (a rotated slab's `43.552099`) comes back from the
    editor as `43.552097`; quantizing both sides makes the comparison exact at the only precision
    the round-trip can preserve, and never changes a grid value (`f32(64.0) == 64.0`)."""
    return struct.unpack("f", struct.pack("f", x))[0]


def _unquote(text: str) -> str:
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    return t


def _as_int(text: str) -> int | str:
    """An `IntProperty`/`ByteProperty` value. Anything that is not an integer literal is kept as its
    TEXT rather than coerced: neither T3D nor `uprops`' default rendering ever writes an integer
    property in a float form, so a `4.9` here is malformed input, and truncating it to `4` would make
    it compare EQUAL to a real `4` — a false pass. Keeping the text makes the compare fail loudly."""
    t = _unquote(text)
    try:
        return int(t, 10)
    except ValueError:
        return t


def typed_value(text: str, field: Field, default_text: str | None = None):
    """Decode one property/member value `text` as declared by `field`.

    `default_text` is the class default's text for the SAME property, consulted only for a struct:
    a member the text omits takes the DEFAULT member (the engine's own import rule), not zero."""
    kind = field.kind
    if kind == STRUCT:
        return _struct_value(text, field, default_text)
    t = _unquote(text)
    if kind == FLOAT:
        try:
            return _f32(float(t))
        except ValueError:
            return t
    if kind == INT:
        # VERBATIM. An FRotator component is an IntProperty and UnrealEd stores it exactly as
        # given — over-range values included (`Yaw=-131072` survives import, MAP SAVE and the UCC
        # re-export the post-verify reads; live-probed 2026-07-25,
        # `dev/docs/spikes/2026-07-25-frotator-import-normalization/findings.md`). Reducing mod
        # 65536 anywhere on this path would rewrite most ingested retail rotators and make the
        # post-verify unpassable.
        return _as_int(t)
    if kind == BYTE:
        return _as_int(t)
    if kind == ENUM:
        return _enum_value(t, field.enum)
    if kind == BOOL:
        low = t.casefold()
        if low in ("true", "1"):
            return True
        if low in ("false", "0"):
            return False
        return t
    if kind in (NAME, OBJECT):
        return t.casefold()                  # FName semantics: case-insensitive
    if kind == STRING:
        return t
    if parse_struct_text(text) is not None:  # untyped, but shaped like a struct: still member-wise
        return _struct_value(text, UNKNOWN_FIELD, default_text)
    return _untyped_value(text)


def _enum_value(text: str, names: tuple[str, ...]):
    """An enum value normalized to its ORDINAL. T3D writes the enum NAME (`SHEER_ZX`,
    `MV_GlideByTime`) while a struct-member default decodes as the raw byte (`uprops`'
    `_decode_struct_bin_at` renders a member ByteProperty as a number), so the two forms must
    converge or a default-equal member never matches. An unrecognized name is kept as text rather
    than guessed at."""
    low = text.casefold()
    for i, n in enumerate(names):
        if n.casefold() == low:
            return i
    try:
        return int(low, 10)
    except ValueError:
        return low


def _untyped_value(text: str):
    """A value with no declared type: shaped by its TEXT, never by an assumed type. Numbers compare
    numerically (so `4.0` == `4`), `True`/`False` compare as bools, a struct literal compares
    member-wise, and everything else compares as its exact text. This is strictly a text-equality
    comparison plus the two spelling equivalences the editor itself creates, so it can never turn a
    real difference into a match — it only fails to recognize a default-equal value, which is the
    pre-existing loud abort."""
    t = _unquote(text)
    if parse_struct_text(text) is not None:
        return _struct_value(text, UNKNOWN_FIELD, None)
    low = t.casefold()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(t, 10)
    except ValueError:
        pass
    try:
        return _f32(float(t))
    except ValueError:
        return t


def _struct_value(text: str, field: Field, default_text: str | None):
    """A struct value as `{casefolded member: value}`.

    With a known member layout every member is present in the result: stated members take their
    stated value, unstated ones take the corresponding DEFAULT member, and members the default does
    not state either take their type's zero. That IS the engine's import rule, so two spellings of
    the same value (`(Pitch=0,Yaw=16384,Roll=0)` vs the editor's `(Yaw=16384)`) decode identically.

    With an UNKNOWN layout (no schema for this property) the members cannot be enumerated, so the
    result is the union of what the two texts state with ZERO-valued members dropped — the only
    canonical form available without knowing the member set. It is still symmetric on both compare
    sides, and it never invents a member neither side mentions. Known limitation of that branch:
    two structs whose only members are DIFFERENT zeros (`(A=0)` vs `(B=0)`) both canonicalize to
    `{}` and so compare equal. Unreachable on real content (a survey of 5570 actors from real
    editor exports found no stated property whose field was an unknown/memberless struct), and it
    cannot arise at all once the class schema resolves."""
    parsed = parse_struct_text(text)
    if parsed is None:
        return _unquote(text)                # not a struct literal — compare it as its own text
    defaults = parse_struct_text(default_text or "") or {}
    if field.members:
        out: dict[str, object] = {}
        for name, mf in field.members:
            if name in parsed:
                out[name] = typed_value(parsed[name], mf, defaults.get(name))
            elif name in defaults:
                out[name] = typed_value(defaults[name], mf, None)
            else:
                out[name] = zero_value(mf)
        # Members the schema does not know about (a decode gap, or a hand-authored member name)
        # are kept verbatim rather than dropped, so they can never be silently ignored.
        for name, raw in parsed.items():
            if name not in out:
                out[name] = _untyped_value(raw)
        return out
    merged = dict(defaults)
    merged.update(parsed)
    out = {}
    for name, raw in merged.items():
        v = _untyped_value(raw)
        if not _is_untyped_zero(v):
            out[name] = v
    return out


def _is_untyped_zero(v) -> bool:
    """Whether an UNTYPED member value is its type's zero, and so indistinguishable from a member
    the other side simply omitted. Deliberately narrow — a number equal to 0, `False`, the empty
    string, or a struct with no non-zero members. NOT the object/name `None`: without a type we
    cannot tell an object ref from a string that reads `None`, and equating them could hide a real
    difference."""
    if isinstance(v, dict):
        return not v
    if isinstance(v, bool):
        return v is False
    if isinstance(v, (int, float)):
        return v == 0
    return v == ""


def zero_value(field: Field):
    """The value a property of this type has when NOTHING states it — the engine's zero-initialized
    default object. `ABSENT` when the type is unknown, because there is then no zero to name and
    guessing one is how a wrong map passes the verify."""
    kind = field.kind
    if kind == FLOAT:
        return 0.0
    if kind in (INT, BYTE, ENUM):
        return 0
    if kind == BOOL:
        return False
    if kind in (NAME, OBJECT):
        return "none"                        # FName index 0 / the null object ref both render `None`
    if kind == STRING:
        return ""
    if kind == STRUCT:
        return {name: zero_value(mf) for name, mf in field.members}
    return ABSENT


def render(value) -> str:
    """A typed value in a form a human can read in a post-verify diagnostic."""
    if value is ABSENT:
        return "<absent>"
    if isinstance(value, dict):
        return "(" + ",".join(f"{k}={render(v)}" for k, v in sorted(value.items())) + ")"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return repr(value)
    return str(value)


# ── the per-actor effective view ────────────────────────────────────────────────────────────────

@dataclass
class ActorValues:
    """One actor's typed property values, as the post-verify compares them.

    `own` holds ONLY the properties the actor itself states; everything else resolves through
    `info.typed_default(key)` on demand. Storing just the stated values (rather than materializing
    all ~200-400 properties of the class per actor) is what keeps the compare cheap, and it is
    exactly equivalent: two actors of the same class that both omit a property both get the same
    class default, so a key absent from both sides can never be a difference.

    `raw` (the value text as authored) and `spelled` (the property key as authored) are kept purely
    for diagnostics and are NEVER compared — a spelling difference must not come back in through a
    diagnostic field."""

    cls: str                                          # casefolded FQCN
    info: object                                      # classdefaults.ClassInfo
    own: dict[tuple[str, int], object]
    brush: str = ""                                   # canonical geometry text ("" for a point actor)
    raw: dict[tuple[str, int], str] = _dc_field(default_factory=dict, compare=False)
    spelled: dict[tuple[str, int], str] = _dc_field(default_factory=dict, compare=False)

    def effective(self, key: tuple[str, int]):
        """This actor's effective value for `key`: the stated value if it states one, else the class
        default (else the type zero, else `ABSENT`)."""
        if key in self.own:
            return self.own[key]
        return self.info.typed_default(key)

    def name_of(self, key: tuple[str, int]) -> str:
        """`key` as this actor spells it (`LightRadius`), falling back to the compare key."""
        return self.spelled.get(key, key_text(key))

    def describe(self, key: tuple[str, int], name: str | None = None) -> str:
        """`key`'s value as a diagnostic line: the authored text when the actor states it, else the
        class default it fell through to. `name` is the spelling to use when THIS actor omits the
        property and so has no spelling of its own (the other side's, normally) — the compare key is
        casefolded, and a message that says `lightradius` where the user wrote `LightRadius` reads
        like a different property."""
        if key in self.raw:
            return f"{self.name_of(key)}={self.raw[key]}"
        return f"{name or key_text(key)} omitted (class default {render(self.effective(key))})"

    def diff_key(self, other: "ActorValues") -> tuple[str, int] | None:
        """The first property (in sorted order) whose effective value differs, or None."""
        for key in sorted(set(self.own) | set(other.own)):
            if self.effective(key) != other.effective(key):
                return key
        return None

    def __eq__(self, other) -> bool:
        if not isinstance(other, ActorValues):
            return NotImplemented
        if self.cls != other.cls or self.brush != other.brush:
            return False
        return self.diff_key(other) is None

    __hash__ = None                                   # mutable + custom __eq__: never hash one
