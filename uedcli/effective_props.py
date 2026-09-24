"""Effective-property resolution for the GUI Inspector — schema + stored/default value, structured
as a tree (struct/array expansion), not a flat KEY=VALUE list. Pure: takes a `model.Actor` and a
`propedit.ClassCtx`, returns `list[EffectiveProp]`. No FastAPI/scene-payload knowledge here — that
wiring lives in `serve/scene.py`.

See `dev/docs/board/to-plan/gui-inspector-effective-props-search-show-all/spec.md` for the design
this implements — the resolution engine (`propedit.effective_value`), the show-all filter
(`HARD_REJECT`+`is_computed_key`, not `CPF_Edit`), and the ArrayProperty/PointerProperty exclusion
are all owner-ruled decisions from that spec, not judgment calls made here."""
from __future__ import annotations

from dataclasses import dataclass

from . import propedit


@dataclass(frozen=True, kw_only=True)
class ScalarProp:
    name: str
    category: str
    kind: str                          # 'float'|'int'|'bool'|'byte'|'name'|'string'
    stored_value: str | None
    default_value: str


@dataclass(frozen=True, kw_only=True)
class EnumProp:
    name: str
    category: str
    enum_type: str                     # key into ScenePayload.enums, "<Package>.<Class>.<EnumName>"
    stored_value: str | None           # ALWAYS a canonical enum NAME, never a bare ordinal (Task 4
    default_value: str                 # canonicalizes both — see Task 4's enum branch)
    kind: str = "enum"


@dataclass(frozen=True, kw_only=True)
class StructProp:
    name: str
    category: str
    members: list["EffectiveProp"]
    kind: str = "struct"


@dataclass(frozen=True, kw_only=True)
class ArrayProp:
    name: str
    category: str
    element_kind: str
    elements: list["EffectiveProp"]
    kind: str = "array"


EffectiveProp = ScalarProp | EnumProp | StructProp | ArrayProp


# ── PropToken constructors for TYPED_FIELDS.get() ───────────────────────────────────────────────
# `TypedField._axis_of`/`ScaleField._member` (propedit/fields.py) only inspect `tok.segs` — the
# smallest `PropToken` (propedit/tokens.py: `base`, `segs`, `value`, `raw`) that satisfies each.

def _axis_token(axis: str):
    from .propedit.tokens import PropToken
    return PropToken(base="Location", segs=(axis,), value=None, raw=f"Location.{axis}")


def _scale_component_token(axis: str):
    from .propedit.tokens import PropToken
    return PropToken(base="Scale", segs=("Scale", axis), value=None, raw=f"Scale.{axis}")


def _sheerrate_token():
    from .propedit.tokens import PropToken
    return PropToken(base="SheerRate", segs=("SheerRate",), value=None, raw="SheerRate")


def _sheeraxis_token():
    from .propedit.tokens import PropToken
    return PropToken(base="SheerAxis", segs=("SheerAxis",), value=None, raw="SheerAxis")


def _stated_scale_members(text: str | None, current) -> str:
    """MainScale/PostScale's own `_stated_axes` -- same self-invalidation rule as Location's, ported
    to FScale's three real members (Scale, SheerRate, SheerAxis) instead of X/Y/Z. Returns a string
    of stated member tags, e.g. 'ScaleSheerRate' -- or the empty string when nothing was stated."""
    from .transform import IDENTITY, parse_fscale
    if text is not None and parse_fscale(text) == (current or IDENTITY):
        stated = []
        if "Scale" in text:
            stated.append("Scale")
        if "SheerRate" in text:
            stated.append("SheerRate")
        if "SheerAxis" in text:
            stated.append("SheerAxis")
        return "".join(stated)
    return "ScaleSheerRateSheerAxis"   # self-invalidated: every member reads as stated


def _member_default(defaults_text: str | None, member: str, fallback: str | None) -> str | None:
    """The TRUE class-default text for one member of a struct-typed field's class default
    (`ctx.defaults()[(key, 0)]`, a full struct literal per `structtext.render_default_tag`'s "every
    member stated" guarantee). `fallback` covers both real absences: the class states no default at
    all (`defaults_text is None`), or the struct text doesn't mention this member (shouldn't happen
    per that guarantee, handled defensively anyway)."""
    if defaults_text is None:
        return fallback
    from .propedit import split_struct_text
    pairs = split_struct_text(defaults_text)
    if pairs is None:
        return fallback
    for k, v in pairs:
        if k.casefold() == member.casefold():
            return v
    return fallback


def _resolve_typed_fields(actor, ctx, ctx_by_type: dict[str, list[str]]) -> list[EffectiveProp]:
    """`Location`/`MainScale`/`PostScale` -- the three model fields routed through `TYPED_FIELDS`
    instead of the stored props (spec §6/§10) -- resolved to their own `StructProp` tree, with
    per-member `stored_value` reflecting exactly which axes/members the source actually stated
    (`normalize._stated_axes`'s self-invalidation rule, ported to FScale for the two scale fields).

    `default_value` is the TRUE class default (`ctx.defaults()`), never the actor's own (zero-filled
    at T3D-parse time, per `model.py`) value -- an unstated axis on a class with a non-origin
    Location default (e.g. `Engine.Camera`) must report that real default, not 0 (spec's Design
    section; controller ruling on the Task 3 report's Discrepancy 3).

    Mutates `ctx_by_type`: `SheerAxis` is a fixed Python enum constant, not schema-resolved, so this
    is the only place that ever seeds `ctx_by_type["typedprops.ESheerAxis"]` -- Task 5's enum
    collector never touches it."""
    from .normalize import _stated_axes
    from .transform import DEFAULT_SHEER_AXIS
    from .typedprops import ESHEER_AXIS

    ctx_by_type.setdefault("typedprops.ESheerAxis", list(ESHEER_AXIS))

    tf_location = propedit.TYPED_FIELDS["location"]
    stated = _stated_axes(actor)
    loc_defaults_text = ctx.defaults().get(("location", 0))
    loc_members = []
    for ax in "XYZ":
        _, text = tf_location.get(_axis_token(ax), actor.location)
        loc_members.append(ScalarProp(
            name=ax, category="Movement", kind="float",
            stored_value=text if ax in stated else None,
            default_value=_member_default(loc_defaults_text, ax, "0")))
    location_prop = StructProp(name="Location", category="Movement", members=loc_members)

    scale_props = []
    for key, attr, text_attr, category in (
        ("mainscale", "main_scale", "main_scale_text", "Brush"),
        ("postscale", "post_scale", "post_scale_text", "Brush"),
    ):
        tf = propedit.TYPED_FIELDS[key]
        current = getattr(actor, attr)
        stated_members = _stated_scale_members(getattr(actor, text_attr), current)
        whole_defaults_text = ctx.defaults().get((key, 0))
        scale_defaults_text = _member_default(whole_defaults_text, "Scale", None)
        scale_members = []
        for ax in "XYZ":
            _, text = tf.get(_scale_component_token(ax), current)
            scale_members.append(ScalarProp(
                name=ax, category=category, kind="float",
                stored_value=text if "Scale" in stated_members else None,
                default_value=_member_default(scale_defaults_text, ax, "1")))
        _, rate_text = tf.get(_sheerrate_token(), current)
        _, axis_text = tf.get(_sheeraxis_token(), current)
        scale_props.append(StructProp(
            name=tf.name, category=category,
            members=[
                StructProp(name="Scale", category=category, members=scale_members),
                ScalarProp(name="SheerRate", category=category, kind="float",
                          stored_value=rate_text if "SheerRate" in stated_members else None,
                          default_value=_member_default(whole_defaults_text, "SheerRate", "0")),
                EnumProp(name="SheerAxis", category=category, enum_type="typedprops.ESheerAxis",
                        stored_value=axis_text if "SheerAxis" in stated_members else None,
                        default_value=_member_default(whole_defaults_text, "SheerAxis",
                                                       DEFAULT_SHEER_AXIS)),
            ]))
    return [location_prop, *scale_props]


# ── generic schema walk (scalar/enum/struct/array) ──────────────────────────────────────────────
# Mirrors scene.py's own constant of the same name -- duplicated, not imported (scene.py imports
# THIS module, the reverse would cycle), same leaf-helper convention as e.g. scene.py's own
# _strip_object_ref.
_FALLBACK_CATEGORY = "Uncategorized"

_SCALAR_KIND = {
    "IntProperty": "int",
    "FloatProperty": "float",
    "BoolProperty": "bool",
    "ByteProperty": "byte",
    "NameProperty": "name",
    "StrProperty": "string",
}

# spec's "Explicitly out of scope" section: a property of any of these kinds is simply not included
# in props at all -- same treatment for ArrayProperty/PointerProperty (never a usable static-array
# element type in practice) and ObjectProperty/ClassProperty (object refs, out of scope). One shared
# predicate so the exclusion list is never hand-written twice (top-level loop + _resolve_one's own
# recursion into struct members/array elements).
_EXCLUDED_KINDS = ("ArrayProperty", "PointerProperty", "ObjectProperty", "ClassProperty")


def _is_excluded_kind(kind: str) -> bool:
    return kind in _EXCLUDED_KINDS


def resolve_actor_props(actor, ctx) -> tuple[list[EffectiveProp], dict[str, list[str]], str | None]:
    """The complete per-actor `EffectiveProp` tree (spec's "Server-side resolution"), plus the
    `ctx_by_type` enum accumulator (Task 5 unions this across actors into `ScenePayload.enums`) and
    a `note` (third element, `None` on success) for the SAME class-unresolvable degrade convention
    `_is_hidden_ed`/`_actor_radii` already use in `serve/scene.py`. `ctx.schema()`/`ctx.defaults()`
    (the latter reached transitively via `_resolve_typed_fields`) can both raise `SchemaError` for
    an actor whose class can't be resolved at all -- that failure degrades the WHOLE actor to
    `([], {}, note)`, never a 500. A single unresolvable STRUCT MEMBER (the class itself fine) is a
    narrower, per-property degrade -- see `_resolve_actor_props_unsafe`'s own inner try/except."""
    from .uprops import SchemaError

    try:
        out, ctx_by_type = _resolve_actor_props_unsafe(actor, ctx)
        return out, ctx_by_type, None
    except SchemaError as e:
        return [], {}, (f"actor {actor.name!r}: schema unavailable ({actor.cls}) — cannot resolve "
                        f"effective props ({e})")


def _resolve_actor_props_unsafe(actor, ctx) -> tuple[list[EffectiveProp], dict[str, list[str]]]:
    """The real work, unguarded -- `resolve_actor_props` wraps the WHOLE thing in one try/except so
    a class-level failure (`ctx.schema()` or `ctx.defaults()`, both reachable per-actor, not just
    per-property) degrades exactly once, the same way `_is_hidden_ed`/`_actor_radii` already do in
    `scene.py`. A per-PROPERTY failure (one struct member unresolvable, the class itself fine)
    still degrades independently inside the loop below -- a separate, narrower try/except."""
    from .normalize import is_computed_key
    from .uprops import SchemaError

    ctx_by_type: dict[str, list[str]] = {}
    out: list[EffectiveProp] = _resolve_typed_fields(actor, ctx, ctx_by_type)
    for prop in ctx.schema().values():
        base = prop.name.casefold()
        if (base in propedit.HARD_REJECT or base in propedit.TYPED_FIELDS
                or is_computed_key(base) or _is_excluded_kind(prop.kind)):
            # up-front skip, kept as a (now slightly redundant) optimization -- _resolve_one's own
            # _is_excluded_kind guard below is what makes the exclusion apply uniformly no matter
            # how _resolve_one is reached (here, a struct member, or an array element)
            continue
        try:
            resolved = _resolve_one(prop, ctx, actor, category=_category_for(prop),
                                    ctx_by_type=ctx_by_type,
                                    base_prop=prop, base_index=None, member_path=())
        except SchemaError:
            # unresolvable struct member / cross-package miss: degrade, never 500 the whole payload.
            # Preserves the prop's own real KIND (Minor 5): a static array of structs degrades to an
            # empty ArrayProp (its true wire kind is "array"), never a relabeled StructProp -- only a
            # scalar StructProperty (no array_dim) degrades to StructProp.
            if prop.array_dim > 1:
                out.append(ArrayProp(name=prop.name, category=_category_for(prop),
                                     element_kind="struct", elements=[]))
            else:
                out.append(StructProp(name=prop.name, category=_category_for(prop), members=[]))
            continue
        if resolved is not None:
            out.append(resolved)
    return out, ctx_by_type


def _resolve_one(prop, ctx, actor, *, category: str, ctx_by_type: dict,
                 base_prop, base_index: int | None, member_path: tuple,
                 elem_index: int | None = None) -> EffectiveProp | None:
    """One `Prop` -> its `EffectiveProp`, or `None` when `prop`'s kind is excluded from scope
    (`_is_excluded_kind` -- ArrayProperty/PointerProperty/ObjectProperty/ClassProperty). Checked
    here, not just in the top-level loop, so a struct MEMBER or array ELEMENT of an excluded kind is
    excluded the same way a top-level property is (both recursive callers below filter `None` out).

    `base_prop`/`base_index`/`member_path` are `prop`'s REAL resolved-path identity (Critical 1
    fix): the schema-level `Prop` this whole walk started from, its own array index once picked, and
    the chain of `propedit.MemberStep`s descended through struct members so far. A struct member used
    to be resolved by recursing `_resolve_one` on the MEMBER `Prop` as if it were its own top-level
    property -- `ctx.defaults()`/`propedit.effective_value` key struct-typed defaults by the STRUCT's
    own top-level name only (`uprops.resolve_class_defaults`'s `tag.name`, never a member name), so
    every unstated member silently fell through to the type zero instead of the struct's TRUE class
    default. `base_prop`/`base_index`/`member_path` let a LEAF (struct member or not, array element
    or not) build the exact `propedit.ResolvedPath` `propedit.effective_value`/CLI `actor prop get
    --effective` use, so both `default_value` (the merged stored-or-default) and `stored_value` (the
    raw partial-literal text, via `_raw_stored_text`) resolve through the SAME real member-chain path
    -- never a bare top-level-name lookup that could coincidentally collide with an unrelated
    top-level prop of the same spelling (Critical 1's second, latent defect).

    `elem_index` is set only on a recursive call that has ALREADY picked one element of `prop`'s own
    static array (`prop.array_dim > 1`) -- it skips re-entering the array branch below; `base_index`/
    `member_path` (built by that branch, BEFORE the recursive call) already carry the picked index at
    the right spot (the base level for a top-level array, the last `member_path` step for a member
    array), so this recursive call falls straight through to StructProperty/enum/scalar handling.

    `array_dim > 1` is checked BEFORE `StructProperty`, not after: a static array of structs
    (`prop.kind == "StructProperty"` AND `prop.array_dim > 1`, e.g. `var Rotator Foo[4]`) must
    resolve as an `ArrayProp` of `StructProp` elements, not as one `StructProp` whose "members" are
    actually the struct type's own fields read off the array-declared `prop`. Every element recurses
    on the SAME `prop` object (never a throwaway `dataclasses.replace` copy -- that was Critical 2's
    root cause: a freed throwaway `Prop`'s `id()` can be reused by CPython for a later, structurally
    DIFFERENT throwaway `Prop`, so `ClassCtx.members()`'s old `id(prop)` cache silently returned a
    different struct's members). `elem_index` alone distinguishes "already resolved this level's
    array" from "resolve it now", so `ctx.members(prop)` always sees the one real, persistent
    schema-level `Prop` object -- never an ephemeral stand-in."""
    if _is_excluded_kind(prop.kind):
        return None
    if prop.array_dim > 1 and elem_index is None:
        elements = []
        for i in range(prop.array_dim):
            if member_path:                          # a MEMBER's own array: index its last step
                *rest, last = member_path
                new_member_path = tuple(rest) + (propedit.MemberStep(prop=last.prop, index=i),)
                new_base_index = base_index
            else:                                    # the BASE property's own array
                new_member_path = member_path
                new_base_index = i
            r = _resolve_one(prop, ctx, actor, category=category, ctx_by_type=ctx_by_type,
                             base_prop=base_prop, base_index=new_base_index,
                             member_path=new_member_path, elem_index=i)
            if r is not None:
                elements.append(r)
        # elements is never empty here: array_dim > 1 guarantees at least 2 iterations, and an
        # excluded-kind element would have made the WHOLE property excluded above (an array's own
        # `prop.kind` IS its element kind). Deriving `element_kind` from the resolved elements (not
        # `_scalar_kind(prop)`) is what makes struct- and enum-typed arrays report their real kind
        # ("struct"/"enum") instead of _scalar_kind's unrecognized-kind fallback ("string"/"byte").
        return ArrayProp(name=prop.name, category=category,
                         element_kind=elements[0].kind, elements=elements)
    if prop.kind == "StructProperty":
        members = []
        for m in ctx.members(prop):
            r = _resolve_one(m, ctx, actor, category=category, ctx_by_type=ctx_by_type,
                             base_prop=base_prop, base_index=base_index,
                             member_path=member_path + (propedit.MemberStep(prop=m, index=None),))
            if r is not None:
                members.append(r)
        return StructProp(name=prop.name, category=category, members=members)
    rp = propedit.ResolvedPath(prop=base_prop, index=base_index, members=member_path,
                               canonical=_canonical_path(base_prop, base_index, member_path))
    stored_value = _raw_stored_text(actor, rp)
    # `propedit.effective_value` DELIBERATELY includes the actor's own stored value when present
    # (spec's "Explicitly out of scope" correction, owner-confirmed 2026-09-23): for an explicit
    # property, `default_value` collapses to `stored_value` -- not a bug, and not a true actor-
    # independent class default (that would need a separate, narrower resolution a future "reset to
    # default" action would add).
    if prop.kind == "ByteProperty" and ctx.enums(prop):
        enum_type = f"{prop.owner}.{prop.type_name}"
        names = list(ctx.enums(prop))
        ctx_by_type.setdefault(enum_type, names)
        return EnumProp(name=prop.name, category=category, enum_type=enum_type,
                        stored_value=_canonicalize_enum_text(stored_value, names),
                        default_value=_canonicalize_enum_text(
                            propedit.effective_value(actor, rp, ctx), names))
    return ScalarProp(name=prop.name, category=category, kind=_scalar_kind(prop),
                      stored_value=stored_value,
                      default_value=propedit.effective_value(actor, rp, ctx))


def _canonical_path(base_prop, base_index: int | None, member_path: tuple) -> str:
    """`base_prop`/`base_index`/`member_path` -> the same canonical dot spelling
    `propedit.paths.resolve_path` builds (e.g. `"Nest.Marks.1"`) -- diagnostic only (used in
    `propedit.effective_value`'s own error messages), never load-bearing for resolution."""
    canonical = base_prop.name
    if base_index is not None:
        canonical += f".{base_index}"
    for step in member_path:
        canonical += f".{step.prop.name}"
        if step.index is not None:
            canonical += f".{step.index}"
    return canonical


def _raw_stored_text(actor, rp) -> str | None:
    """The RAW stored text at `rp`'s exact member-chain path, or `None` when the actor doesn't state
    it -- drilled member-wise through the struct's own stated PARTIAL-literal text
    (`dev/docs/unrealed/t3d.md` "Partial struct/array property values"), never a bare top-level-name
    lookup that could coincidentally collide with an unrelated top-level prop of the same spelling
    (Critical 1's second, latent defect)."""
    smap = propedit._stored_map(actor)
    bf = rp.prop.name.casefold()
    idx = rp.index if rp.index is not None else 0
    text = smap.get((bf, idx))
    if text is None:
        return None
    for step in rp.members:
        pairs = propedit.split_struct_text(text)
        if pairs is None:
            return None
        want = (step.prop.name.casefold(), step.index)
        hit = next((v for k, v in pairs if propedit._text_key_ident(k) == want), None)
        if hit is None:
            return None
        text = hit
    return text


def _category_for(prop) -> str:
    """`prop`'s UnrealEd category, or `_FALLBACK_CATEGORY` for a bare `var()` with none."""
    return prop.category or _FALLBACK_CATEGORY


def _scalar_kind(prop) -> str:
    """`Prop.kind` -> the `EffectiveProp` scalar `kind` label. `ObjectProperty`/`ClassProperty` are
    excluded before this is ever reached for them (`_is_excluded_kind`); anything else outside the
    six spec'd scalar kinds falls back to `'string'`, the same untyped-text treatment the Inspector
    already gives any kind it doesn't specially render."""
    return _SCALAR_KIND.get(prop.kind, "string")


def _canonicalize_enum_text(text: str | None, names: list[str]) -> str | None:
    """An ordinal string -> its NAME; an already-a-name string (or None) passes through unchanged.
    `propedit.edit.effective_value`'s own default/zero branches do NOT canonicalize (only its stored
    branch does, via `_canonicalize_enum`) -- this GUI-only helper applies the SAME conversion to
    both stored_value and default_value, so an EnumProp's two fields are always consistently
    NAME-form, never a mix. Mirrors propedit.edit._canonicalize_enum's own ordinal-detection rule
    exactly (isdigit check) rather than inventing a new one."""
    if text is None:
        return None
    if text.strip().isdigit():
        i = int(text.strip())
        if i < len(names):
            return names[i]
    return text
