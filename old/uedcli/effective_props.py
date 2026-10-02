"""Location/MainScale/PostScale resolution for the GUI Inspector -- the one part of the old
per-actor EffectiveProp walk that survives gui-inspector-props-payload-redesign (spec §2): these
three are a real special case, resolved from model.Actor fields directly via propedit.TYPED_FIELDS,
never from the generic class schema uedcli_native.resolve_class_json/resolve_actor_props_json now
own. `effective_props_native.py` (this feature's own new bridge module) reuses
`_resolve_typed_fields` for exactly this STATEDNESS half -- see its own module docstring."""
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


EffectiveProp = ScalarProp | EnumProp | StructProp


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
