"""Reading and writing a T3D struct literal `(A=1,B=(X=2))`: the split/emit pair, the member-wise
merge onto the class default, the type's zero, and the targeted member set/unset.

The member split and the name/value `=` come from `typedprops` — the SAME quote- and depth-aware
code the typed compare path uses — so the codebase's two struct-literal parsers cannot disagree.
"""
from __future__ import annotations

from .. import typedprops
from ..uprops import Prop
from .base import ClassCtx, PropEditError, _VR_STRUCTS, _dec_finite, _dequote
from .paths import MemberStep, _member_map, _text_key_ident


# ── struct-text helpers ──────────────────────────────────────────────────────────────────────

def split_struct_text(text: str) -> list[tuple[str, str]] | None:
    """`(A=1,B=(C=2))` → [("A","1"), ("B","(C=2)")]; None if not a parenthesized K=V list.
    Keys may be identifiers, integers (the array tuple form), or `Name(N)` (a struct member
    that is a static array).

    The member split and the name/value `=` both come from `typedprops`
    (`split_struct_members` / `top_level_eq`) — the SAME quote- and depth-aware code the typed
    compare path uses — so the two struct-literal parsers in the codebase cannot disagree. That
    is what makes a quoted comma or a quoted `=` inside a member value safe: `(Msg="a,b",N=1)`
    is two members, not three, and `(Msg="x=y")` has value `"x=y"`.

    This one differs from `typedprops.parse_struct_text` ONLY in its result shape: an ORDERED
    list with the key's authored case preserved, because `emit_struct_text` writes the members
    back out and a struct's member order and spelling are part of the emitted T3D."""
    items = typedprops.split_struct_members(text)
    if items is None:
        return None
    out: list[tuple[str, str]] = []
    for item in items:
        eq = typedprops.top_level_eq(item)
        if eq is None:
            return None
        out.append((item[:eq].strip(), item[eq + 1:].strip()))
    return out


def emit_struct_text(pairs: list[tuple[str, str]]) -> str:
    return "(" + ",".join(f"{k}={v}" for k, v in pairs) + ")"


def zero_value(prop: Prop, ctx: ClassCtx) -> str:
    """The type's ZERO in canonical form (spec §2.3): what the engine uses when neither the
    actor nor any class default mentions the prop."""
    if prop.kind == "BoolProperty":
        return "False"
    if prop.kind in ("IntProperty", "FloatProperty"):
        return "0"
    if prop.kind == "ByteProperty":
        names = ctx.enums(prop)
        return names[0] if names else "0"
    if prop.kind in ("NameProperty", "ObjectProperty", "ClassProperty"):
        return "None"
    if prop.kind == "StrProperty":
        return ""
    if prop.kind == "StructProperty":
        pairs: list[tuple[str, str]] = []
        for m in ctx.members(prop):
            if m.array_dim > 1:                      # member static array: per-element spelling
                mz = zero_value(m, ctx)
                pairs.extend((f"{m.name}({i})", mz) for i in range(m.array_dim))
            else:
                pairs.append((m.name, zero_value(m, ctx)))
        return emit_struct_text(pairs)
    return ""                                        # Array/Pointer: empty (out of scope, §3)


def merge_struct_texts(prop: Prop, base_text: str, over_text: str, ctx: ClassCtx) -> str:
    """Merge `over_text`'s members onto `base_text`'s, RECURSIVELY for struct-typed members
    (review finding: a stored partial NESTED member must not wholesale-replace the default's
    nested struct — the engine merges member-wise at every depth, per the §9 probe). Member
    order follows the base; over-only members append. Unparseable sides pass through."""
    bp = split_struct_text(base_text)
    op = split_struct_text(over_text)
    if bp is None or op is None:
        return over_text                             # un-mergeable over side passes through
    members = _member_map(ctx.members(prop)) if prop.kind == "StructProperty" else {}
    over_by_ident = { _text_key_ident(k): v for k, v in op }
    merged: list[tuple[str, str]] = []
    seen: set[tuple[str, int | None]] = set()
    for k, v in bp:
        ident = _text_key_ident(k)
        seen.add(ident)
        ov = over_by_ident.get(ident)
        if ov is None:
            merged.append((k, v))
            continue
        m = members.get(ident[0])
        if m is not None and m.kind == "StructProperty":
            merged.append((k, merge_struct_texts(m, v, ov, ctx)))
        else:
            merged.append((k, ov))
    for k, v in op:
        if _text_key_ident(k) not in seen:
            merged.append((k, v))
    return emit_struct_text(merged)


def full_struct_text(prop: Prop, index: int, stored_text: str | None, ctx: ClassCtx) -> str:
    """The EFFECTIVE full-member struct text for `prop[index]`: stored members merged
    RECURSIVELY over the class default, over the zero struct (every member explicit — spec §4).
    With no stored value: default over zero."""
    zero = zero_value(prop, ctx)
    dflt = ctx.defaults().get((prop.name.casefold(), index))
    base = merge_struct_texts(prop, zero, dflt, ctx) if dflt is not None else zero
    if stored_text is None:
        return base
    return merge_struct_texts(prop, base, _dequote(stored_text), ctx)


def _maybe_comma_sugar(prop: Prop, value: str) -> str:
    """Vector/Rotator comma sugar (spec §2.1, ruling R1): interpreted ONLY when the schema says
    the prop is a Vector/Rotator struct; on every other prop a comma value is verbatim text."""
    if prop.kind != "StructProperty" or (prop.type_name or "").casefold() not in _VR_STRUCTS:
        return value
    t = _dequote(value)
    if t.startswith("(") or "," not in t:
        return value
    parts = [p.strip() for p in t.split(",")]
    if len(parts) != 3:
        raise PropEditError(f"{prop.name}={value}: {prop.type_name} comma form needs exactly "
                            f"3 components, got {len(parts)}")
    for p in parts:
        _dec_finite(p, f"{prop.name}={value}")
    axes = ("X", "Y", "Z") if (prop.type_name or "").casefold() == "vector" \
        else ("Pitch", "Yaw", "Roll")
    return emit_struct_text(list(zip(axes, parts)))


def _set_member_in_text(base_text: str, steps: tuple[MemberStep, ...], value: str,
                        label: str) -> str:
    """Set the (possibly nested) member chain inside a struct text, preserving every other
    member as stored. Member-array elements address their `Name(N)` entry."""
    pairs = split_struct_text(base_text)
    if pairs is None:
        raise PropEditError(f"{label}: stored value is not a struct literal: {base_text!r}")
    step = steps[0]
    rest = steps[1:]
    want = (step.prop.name.casefold(), step.index)
    hit_i = next((i for i, (k, _v) in enumerate(pairs)
                  if _text_key_ident(k) == want), None)
    if rest:
        inner = pairs[hit_i][1] if hit_i is not None else "()"
        new_inner = _set_member_in_text(inner if inner.strip().startswith("(") else "()",
                                        rest, value, label)
        entry = (step.text_key, new_inner)
    else:
        entry = (step.text_key, value)
    if hit_i is not None:
        pairs[hit_i] = entry
    else:
        pairs.append(entry)
    return emit_struct_text(pairs)


def _unset_member_in_text(base_text: str, steps: tuple[MemberStep, ...],
                          label: str) -> tuple[bool, str | None]:
    """Remove the member chain from a struct text. Returns (changed, new_text|None) — None
    when the struct becomes empty (→ the whole stored line is removed, spec §3.1); changed
    False when the member wasn't stored (silent success MUST NOT rewrite the trunk — review
    finding: a no-op used to re-emit the normalized text)."""
    pairs = split_struct_text(base_text)
    if pairs is None:
        raise PropEditError(f"{label}: stored value is not a struct literal: {base_text!r}")
    step = steps[0]
    rest = steps[1:]
    want = (step.prop.name.casefold(), step.index)
    hit_i = next((i for i, (k, _v) in enumerate(pairs)
                  if _text_key_ident(k) == want), None)
    if hit_i is None:
        return False, base_text
    if rest:
        changed, inner = _unset_member_in_text(pairs[hit_i][1], rest, label)
        if not changed:
            return False, base_text
        if inner is None:
            del pairs[hit_i]
        else:
            pairs[hit_i] = (pairs[hit_i][0], inner)
    else:
        del pairs[hit_i]
    if not pairs:
        return True, None
    return True, emit_struct_text(pairs)
