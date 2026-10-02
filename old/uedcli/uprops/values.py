"""Value decode and render, plus the rendering policy: one defaults `PropertyTag`, one in-struct
binary block or one dynamic array → its canonical text or a nested member tree, and the
hierarchy-walking `resolve_class_defaults` that callers actually ask for."""
from __future__ import annotations

import struct
from dataclasses import dataclass, replace

from ..upackage import (
    Package,
    PropertyTag,
    SchemaError,
    load_package,
    read_compact_index as _read_compact_index,
    read_fstring as _read_fstring,
    PT_BYTE, PT_INT, PT_BOOL, PT_FLOAT, PT_OBJECT, PT_NAME, PT_STR_LEGACY, PT_STR, PT_STRUCT,
)
from .base import Prop, _STRUCT_BIN_SIZES, _safe_name, _schema_guard
from .ufield import enum_values, find_struct_export, struct_members
from .uclass import class_default_tags, resolve_class_properties, _super_fqcn


@_schema_guard
def resolve_type_export(pkg: Package, type_ref: int, want_class: str, *, resolver, _pkgs: dict):
    """Resolve a Prop's `type_ref` (enum/struct) to (owning_package, 1-based export index). A
    local ref resolves in `pkg`; an import resolves via its owning package + a name lookup
    there. `want_class` is "Enum" or "Struct". PUBLIC because `classdefaults` compiles struct
    member layouts through it for the typed compare, and `dispatch` renders struct defaults —
    which is also why it carries `@_schema_guard`: an out-of-range import ref in a corrupt package
    used to escape as a bare `IndexError`, and the compare now walks the member layout of EVERY
    struct property of every class in a level, so callers that catch only `SchemaError` would have
    surfaced a traceback."""
    if type_ref > 0:
        if type_ref > len(pkg.exports):          # bounds-check AT THE SOURCE: a corrupt local ref
            raise SchemaError(f"{want_class} type ref {type_ref} out of range in {pkg.name}")
        return pkg, type_ref
    if type_ref == 0:
        raise SchemaError(f"no {want_class} type ref to resolve")
    j = -type_ref - 1
    type_name = pkg.names[pkg.imports[j][3]]
    owner_pkg_name = pkg.import_package_of(j)
    if owner_pkg_name is None:
        raise SchemaError(f"cannot resolve the owning package of imported {want_class} "
                          f"{type_name}")
    if owner_pkg_name not in _pkgs:
        path = resolver(owner_pkg_name)
        if path is None:
            raise SchemaError(f"package {owner_pkg_name!r} not found on the schema search path "
                              f"(needed for {want_class} {type_name})")
        _pkgs[owner_pkg_name] = load_package(path, name=owner_pkg_name)
    tp = _pkgs[owner_pkg_name]
    if want_class == "Struct":
        ti = find_struct_export(tp, type_name)
    else:
        want = type_name.casefold()
        ti = None
        for i, e in enumerate(tp.exports):
            if tp.name_of_ref(e["cls"]) == want_class:
                nm = _safe_name(tp, e["nm"])
                if nm is not None and nm.casefold() == want:
                    ti = i + 1
                    break
    if ti is None:
        raise SchemaError(f"{want_class} {type_name} not found in package {owner_pkg_name}")
    return tp, ti


@_schema_guard
def resolve_enum_names(prop: Prop, declaring_pkg: Package, *, resolver,
                       _pkgs: dict | None = None) -> tuple[str, ...]:
    """A ByteProperty's enum value names, CROSS-PACKAGE (spec §4): a local enum comes from the
    eager `enum_value_names`; an imported enum resolves its owning package via the import table
    and decodes the enum there. A plain byte (no enum) yields ()."""
    if prop.enum_value_names:
        return prop.enum_value_names
    if prop.kind != "ByteProperty" or prop.type_ref == 0:
        return ()
    pkgs = _pkgs if _pkgs is not None else {}
    tp, ti = resolve_type_export(declaring_pkg, prop.type_ref, "Enum",
                                  resolver=resolver, _pkgs=pkgs)
    return tuple(enum_values(tp, ti))


def format_float(v: float) -> str:
    """Canonical CLI float rendering: integral values bare (`24`), fractions trimmed to ≤6dp
    (`0.5`, `-10.25`) — the spec §4 display form (set stores text verbatim, so any float text
    round-trips; numeric comparison in `find` is format-independent)."""
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return f"{v:.6f}".rstrip("0").rstrip(".")


def format_float_t3d(v: float) -> str:
    """T3D float rendering: ALWAYS six decimal places (`24.000000`, `-2240.000000`) — the C `%f`
    form UnrealEd's own `MAP EXPORT` writes for every float, scalar or struct member. Distinct from
    `format_float`, which trims an integral value to `24` for CLI display; a natively decoded map
    must match the editor's text exactly, so it renders through this instead."""
    return f"{v:.6f}"


@dataclass(frozen=True)
class ValueStyle:
    """How a decoded property VALUE is rendered to text. Two styles exist and they are NOT
    interchangeable:

    - **`CLI_STYLE`** (the default for every caller that displays a value — `actor prop get`, the
      class-defaults table): floats trimmed (`24`, `0.5`), and a BYTE member inside a struct shown
      as its plain number.
    - **`T3D_STYLE`**: exactly what UnrealEd's `MAP EXPORT` writes — every float at six decimals
      (`24.000000`), and a byte struct member spelled as its ENUM NAME (`MainScale=(SheerAxis=
      SHEER_ZX)`, never `(SheerAxis=5)`). `mapimport` uses this so a natively decoded `.dx` is
      textually identical to the editor's export of the same map.
    """
    float_fmt: "object" = format_float       # (float) -> str
    enum_bytes: bool = False                 # render a byte STRUCT MEMBER as its enum value name


CLI_STYLE = ValueStyle()


T3D_STYLE = ValueStyle(float_fmt=format_float_t3d, enum_bytes=True)


def _pkg_for_owner(owner: str, fallback: Package, *, resolver, _pkgs: dict) -> Package:
    """The package a Prop was DECLARED in (its `owner` fqcn's package) — the package its
    `type_ref` is relative to. Falls back to `fallback` when the owner isn't dotted (struct
    members decoded in-place)."""
    if "." not in owner:
        return fallback
    pkg_name = owner.split(".", 1)[0]
    if pkg_name == fallback.name:
        return fallback
    if pkg_name not in _pkgs:
        path = resolver(pkg_name)
        if path is None:
            raise SchemaError(f"package {pkg_name!r} not found on the schema search path "
                              f"(needed to resolve {owner})")
        _pkgs[pkg_name] = load_package(path, name=pkg_name)
    return _pkgs[pkg_name]


def _decode_struct_bin_at(value_pkg: Package, members_pkg: Package, members: list[Prop],
                          raw: bytes, start: int, *, resolver,
                          _pkgs: dict, style: ValueStyle = CLI_STYLE
                          ) -> tuple[list[tuple[str, str]], int]:
    """Decode an in-struct binary value block (`UStructProperty::SerializeItem` →
    member-wise `SerializeBin`) into ordered (member_name, rendered_text) pairs from cursor
    `start`. Object/name COMPACTS in the VALUE resolve against `value_pkg` (the package the
    defaults tag was serialized in); a member's own `type_ref` (nested struct types) resolves
    against `members_pkg` (the package the member schema was decoded from). Returns
    (pairs, cursor_after).

    `style` picks the text form of floats and byte members — see `ValueStyle`.

    NB the SAME per-member wire forms are how UE1 serializes a DYNAMIC ARRAY's elements
    (`UArrayProperty::SerializeItem` calls the Inner property's `SerializeItem` per element), so
    `mapimport` decodes an array by passing `[inner] * count` as `members`."""
    out: list[tuple[str, str]] = []
    p = start
    for m in members:
        for i in range(m.array_dim):
            suffix = f"({i})" if m.array_dim > 1 else ""
            if m.kind in _STRUCT_BIN_SIZES:
                n = _STRUCT_BIN_SIZES[m.kind]
                chunk = raw[p:p + n]
                if len(chunk) < n:
                    raise SchemaError(f"struct value truncated at member {m.name}")
                if m.kind == "ByteProperty":
                    out.append((m.name + suffix, _byte_member_text(m, chunk[0], members_pkg,
                                                                  resolver=resolver, _pkgs=_pkgs,
                                                                  style=style)))
                elif m.kind == "IntProperty":
                    out.append((m.name + suffix,
                                str(int.from_bytes(chunk, "little", signed=True))))
                else:
                    out.append((m.name + suffix,
                                style.float_fmt(struct.unpack("<f", chunk)[0])))
                p += n
            elif m.kind in ("ObjectProperty", "ClassProperty"):
                ref, p = _read_compact_index(raw, p)
                out.append((m.name + suffix, render_object_ref(value_pkg, ref)))
            elif m.kind == "NameProperty":
                ni, p = _read_compact_index(raw, p)
                out.append((m.name + suffix,
                            value_pkg.names[ni] if 0 <= ni < len(value_pkg.names) else "None"))
            elif m.kind == "StrProperty":            # in-struct FString (compact len + bytes)
                s, p = _read_fstring(raw, p)
                out.append((m.name + suffix, s))
            elif m.kind == "BoolProperty":           # in-struct bool: one byte (0/1)
                if p >= len(raw):
                    raise SchemaError(f"struct value truncated at member {m.name}")
                out.append((m.name + suffix, "True" if raw[p] else "False"))
                p += 1
            elif m.kind == "StructProperty":
                tp, inner = struct_member_schema(members_pkg, m, resolver=resolver, _pkgs=_pkgs)
                sub, p = _decode_struct_bin_at(value_pkg, tp, inner, raw, p,
                                               resolver=resolver, _pkgs=_pkgs, style=style)
                out.append((m.name + suffix,
                            "(" + ",".join(f"{k}={v}" for k, v in sub) + ")"))
            else:
                raise SchemaError(f"unsupported struct member kind {m.kind} ({m.name}) "
                                  "in a defaults value")
    return out, p


def _byte_member_text(m: Prop, value: int, members_pkg: Package, *, resolver, _pkgs: dict,
                      style: ValueStyle) -> str:
    """A ByteProperty struct member's rendered text: its plain number under `CLI_STYLE`, its ENUM
    VALUE NAME under a style with `enum_bytes` (what `MAP EXPORT` writes — `SheerAxis=SHEER_ZX`).
    Falls back to the number when the member has no enum or the value is out of the enum's range
    (a real, if odd, possibility: a byte holds 0-255 regardless of how many names the enum has)."""
    if not style.enum_bytes or m.type_ref == 0:
        return str(value)
    dp = _pkg_for_owner(m.owner, members_pkg, resolver=resolver, _pkgs=_pkgs)
    names = resolve_enum_names(m, dp, resolver=resolver, _pkgs=_pkgs)
    return names[value] if value < len(names) else str(value)


@_schema_guard
def struct_member_schema(pkg: Package, prop: Prop, *, resolver,
                         _pkgs: dict) -> tuple[Package, list[Prop]]:
    """A `StructProperty`'s struct type resolved to `(package_it_was_decoded_from, ordered members)`.
    `pkg` is the fallback package for a member whose `owner` is not dotted (a nested struct decoded
    in place); a dotted `owner` resolves to that class's declaring package, which is what the
    prop's `type_ref` indexes."""
    if prop.kind != "StructProperty" or prop.type_ref == 0:
        raise SchemaError(f"cannot resolve the struct type of {prop.name} "
                          f"(kind={prop.kind}, type_ref={prop.type_ref})")
    dp = _pkg_for_owner(prop.owner, pkg, resolver=resolver, _pkgs=_pkgs)
    tp, ti = resolve_type_export(dp, prop.type_ref, "Struct", resolver=resolver, _pkgs=_pkgs)
    return tp, struct_members(tp, ti, owner=prop.type_name or prop.name)


def _decode_struct_bin(value_pkg: Package, members_pkg: Package, members: list[Prop],
                       raw: bytes, *, resolver, _pkgs: dict,
                       style: ValueStyle = CLI_STYLE) -> list[tuple[str, str]]:
    """`_decode_struct_bin_at` from 0 with the exact-consume integrity check (no-fallback:
    leftover bytes mean the member layout is wrong)."""
    out, p = _decode_struct_bin_at(value_pkg, members_pkg, members, raw, 0,
                                   resolver=resolver, _pkgs=_pkgs, style=style)
    if p != len(raw):
        raise SchemaError(f"struct value did not consume exactly ({p} != {len(raw)})")
    return out


def render_object_ref(pkg: Package, ref: int) -> str:
    """A signed object ref (in `pkg`'s tables) → the T3D object-ref form
    `Class'Package[.Group].Name'`, or `None` for a 0 ref."""
    if ref == 0:
        return "None"
    cls = pkg.object_class_name(ref) or "Object"
    path = pkg.object_path(ref)
    if path is None:
        raise SchemaError(f"unresolvable object ref {ref} in {pkg.name}")
    return f"{cls}'{path}'"


@_schema_guard
def struct_tag_member_tree(pkg: Package, tag: PropertyTag, prop: Prop, *, resolver, _pkgs: dict,
                           style: ValueStyle = CLI_STYLE) -> dict:
    """A `StructProperty` tag's value decoded to a NESTED tree of its members.

    The tree maps each member's rendered key → either the member's rendered TEXT, or, for a member
    that is itself a struct, a sub-tree of the same shape. It is the same decode
    `render_default_tag` joins into `(A=…,B=…)`, kept structured instead.

    **Why a tree rather than flat pairs.** UnrealEd's `MAP EXPORT` writes only the struct members
    that DIFFER from the class default's corresponding member, and it does so **recursively** — a
    mirrored brush exports `MainScale=(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)`, where the nested
    `Scale` states only the one axis that changed and drops the two that match the default. Real
    editor output committed at `uedcli/tests/fixtures/level_small.t3d` shows exactly that. Flat
    pairs cannot express it: the nested struct would already be joined into one string, so a
    comparison could only keep or drop the whole of it, producing
    `Scale=(X=-1.000000,Y=1.000000,Z=1.000000)`. Pair this with `zero_struct_tree` (for a class that
    declares no default) and `strip_member_tree` (the comparison), then `render_member_tree`.
    """
    tp, members = struct_member_schema(pkg, prop, resolver=resolver, _pkgs=_pkgs)
    tree, pos = _struct_tree_at(pkg, tp, members, tag.raw, 0, resolver=resolver, _pkgs=_pkgs,
                                style=style)
    if pos != len(tag.raw):
        raise SchemaError(f"struct value did not consume exactly ({pos} != {len(tag.raw)})")
    return tree


def _struct_tree_at(value_pkg: Package, members_pkg: Package, members: list[Prop], raw: bytes,
                    start: int, *, resolver, _pkgs: dict, style: ValueStyle) -> tuple[dict, int]:
    """`struct_tag_member_tree`'s walk. Non-struct members are decoded one at a time by the shared
    `_decode_struct_bin_at` (so there is exactly ONE definition of each member kind's wire form);
    a struct member recurses. A member that is a STATIC ARRAY contributes one entry per element,
    decoded in sequence — hence the per-key loop rather than one decode per member."""
    out: dict = {}
    p = start
    for m in members:
        if m.kind == "StructProperty":
            tp, inner = struct_member_schema(members_pkg, m, resolver=resolver, _pkgs=_pkgs)
            for k in member_keys(m):
                sub, p = _struct_tree_at(value_pkg, tp, inner, raw, p, resolver=resolver,
                                         _pkgs=_pkgs, style=style)
                out[k] = sub
        else:
            one = m if m.array_dim == 1 else replace(m, array_dim=1)
            for k in member_keys(m):
                pairs, p = _decode_struct_bin_at(value_pkg, members_pkg, [one], raw, p,
                                                 resolver=resolver, _pkgs=_pkgs, style=style)
                out[k] = pairs[0][1]
    return out, p


def zero_struct_tree(pkg: Package, prop: Prop, *, resolver, _pkgs: dict,
                     style: ValueStyle = CLI_STYLE) -> dict:
    """The ZERO value of struct property `prop`, in `struct_tag_member_tree`'s nested shape.

    A class that declares no default for a property inherits the class-default object's raw memory,
    which UE1 starts as zeros — so "no declared default" means the type's zero, member by member.
    See `_zero_member_text` for what zero SPELLS per kind; note it is not simply an all-zero byte
    buffer decoded, because a zero name/object reference spells `None` rather than name-table
    index 0 (which is an ordinary name — `unrealed/package-format.md` "`FPoly.ItemName` — name
    index 0 is a REAL name")."""
    tp, members = struct_member_schema(pkg, prop, resolver=resolver, _pkgs=_pkgs)
    out: dict = {}
    for m in members:
        if m.kind == "StructProperty":
            sub = zero_struct_tree(tp, m, resolver=resolver, _pkgs=_pkgs, style=style)
            for k in member_keys(m):
                out[k] = sub
        else:
            text = _zero_member_text(m, tp, resolver=resolver, _pkgs=_pkgs, style=style)
            for k in member_keys(m):
                out[k] = text
    return out


def strip_member_tree(value_tree: dict, default_tree: dict) -> dict:
    """`value_tree` with every member equal to `default_tree`'s corresponding member REMOVED,
    recursively — the editor's own export rule.

    A nested struct is kept only when something inside it differs, and then only the differing
    members are kept, which is what makes `MainScale=(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)`
    come out right. A member absent from `default_tree` (the schemas disagree) is KEPT: stating a
    value that might have been droppable is harmless, whereas dropping one that differs is data
    loss."""
    kept: dict = {}
    for k, v in value_tree.items():
        d = default_tree.get(k)
        if isinstance(v, dict):
            sub = strip_member_tree(v, d if isinstance(d, dict) else {})
            if sub:
                kept[k] = sub
        elif v != d:
            kept[k] = v
    return kept


def render_member_tree(tree: dict) -> str:
    """A member tree as the `(A=…,B=(X=…))` text a T3D property line carries."""
    return "(" + ",".join(
        f"{k}=" + (render_member_tree(v) if isinstance(v, dict) else v)
        for k, v in tree.items()) + ")"


def member_keys(m: Prop) -> list[str]:
    """The rendered key(s) one struct member (or one array element property) contributes: `Name`
    for a scalar, `Name(0)`/`Name(1)`/… when the member is itself a STATIC array. The single
    definition of that suffixing, so every producer and consumer of the `(member, text)` pairs
    keys identically."""
    if m.array_dim > 1:
        return [f"{m.name}({i})" for i in range(m.array_dim)]
    return [m.name]


@_schema_guard
def _zero_member_text(m: Prop, members_pkg: Package, *, resolver, _pkgs: dict,
                      style: ValueStyle) -> str:
    if m.kind == "FloatProperty":
        return style.float_fmt(0.0)
    if m.kind == "IntProperty":
        return "0"
    if m.kind == "ByteProperty":
        return _byte_member_text(m, 0, members_pkg, resolver=resolver, _pkgs=_pkgs, style=style)
    if m.kind in ("ObjectProperty", "ClassProperty", "NameProperty"):
        return "None"
    if m.kind == "StrProperty":
        return ""
    if m.kind == "BoolProperty":
        return "False"
    if m.kind == "StructProperty":
        return render_member_tree(
            zero_struct_tree(members_pkg, m, resolver=resolver, _pkgs=_pkgs, style=style))
    raise SchemaError(f"unsupported struct member kind {m.kind} ({m.name})")


@_schema_guard
def decode_array_tag(pkg: Package, tag: PropertyTag, prop: Prop, *, resolver, _pkgs: dict,
                     style: ValueStyle = CLI_STYLE) -> list[str]:
    """A DYNAMIC array (`array<T> Foo`) property tag's value → the rendered text of each element.

    UE1 serializes `UArrayProperty` as a compact element COUNT followed by that many elements, each
    written by the ELEMENT property's own `SerializeItem` — the very same per-kind wire forms a
    struct's members use (`_decode_struct_bin_at`). So the decode is that decoder handed the element
    property repeated `count` times, which also brings its exact-consume integrity check.

    The element property comes from `prop.array_inner`: an ArrayProperty's own `type_ref` points at
    the element property OBJECT, so its `type_name` is that object's NAME and never its kind — the
    element kind exists nowhere else.

    (Distinct from a STATIC array `var int Foo[4]`, which is not one tag at all: the engine writes a
    separate tag per element, each carrying its own `array_index`.)"""
    if prop.kind != "ArrayProperty":
        raise SchemaError(f"{tag.name} is not a dynamic array (kind={prop.kind})")
    if prop.array_inner is None:
        raise SchemaError(f"cannot decode dynamic array {tag.name}: its element property "
                          f"(the ArrayProperty's Inner) did not resolve in {prop.owner}")
    count, pos = _read_compact_index(tag.raw, 0)
    if not (0 <= count <= 1 << 22):
        raise SchemaError(f"implausible element count {count} for dynamic array {tag.name}")
    declaring = _pkg_for_owner(prop.owner, pkg, resolver=resolver, _pkgs=_pkgs)
    pairs, pos = _decode_struct_bin_at(pkg, declaring, [prop.array_inner] * count, tag.raw, pos,
                                       resolver=resolver, _pkgs=_pkgs, style=style)
    if pos != len(tag.raw):
        raise SchemaError(f"dynamic array {tag.name} did not consume exactly "
                          f"({pos} != {len(tag.raw)} bytes)")
    return [v for _k, v in pairs]


@_schema_guard
def render_default_tag(pkg: Package, tag: PropertyTag, prop: Prop | None, *, resolver,
                       _pkgs: dict, style: ValueStyle = CLI_STYLE) -> str:
    """One defaults `PropertyTag` → its canonical CLI text (spec §4 forms). `pkg` is the
    package the tag was serialized in (its VALUE compacts resolve there); `prop` (the schema
    entry, if known) supplies enum naming + the struct type, whose refs resolve against the
    prop's DECLARING package.

    `style` picks the text form (CLI display vs UnrealEd's T3D) — see `ValueStyle`."""
    if tag.ptype == PT_BOOL:
        return "True" if tag.bool_value else "False"
    if tag.ptype == PT_BYTE:
        v = tag.raw[0]
        if prop is not None and prop.kind == "ByteProperty" and prop.type_ref != 0:
            dp = _pkg_for_owner(prop.owner, pkg, resolver=resolver, _pkgs=_pkgs)
            names = resolve_enum_names(prop, dp, resolver=resolver, _pkgs=_pkgs)
            if v < len(names):
                return names[v]
        return str(v)
    if tag.ptype == PT_INT:
        return str(int.from_bytes(tag.raw, "little", signed=True))
    if tag.ptype == PT_FLOAT:
        return style.float_fmt(struct.unpack("<f", tag.raw)[0])
    if tag.ptype == PT_OBJECT:
        ref, _ = _read_compact_index(tag.raw, 0)
        return render_object_ref(pkg, ref)
    if tag.ptype == PT_NAME:
        ni, _ = _read_compact_index(tag.raw, 0)
        return pkg.names[ni] if 0 <= ni < len(pkg.names) else "None"
    if tag.ptype in (PT_STR, PT_STR_LEGACY):
        if tag.ptype == PT_STR:
            s, _ = _read_fstring(tag.raw, 0)
        else:
            s = tag.raw.split(b"\x00", 1)[0].decode("latin-1")
        return s
    if tag.ptype == PT_STRUCT:
        if prop is None:
            raise SchemaError(f"cannot render struct default {tag.name} without its schema")
        # The FULL struct, every member stated. `mapimport` is the only caller that drops members
        # equal to the class default, and it does that itself via `strip_member_tree` — a rendered
        # default must state everything, because it IS the thing others compare against.
        return render_member_tree(struct_tag_member_tree(pkg, tag, prop, resolver=resolver,
                                                         _pkgs=_pkgs, style=style))
    raise SchemaError(f"unsupported default value type {tag.ptype} for {tag.name}")


@_schema_guard
def resolve_class_default_tags(fqcn: str, *, resolver, _pkgs: dict | None = None
                               ) -> dict[tuple[str, int], tuple[Package, PropertyTag]]:
    """The EFFECTIVE class defaults of `fqcn` as RAW tags: every ancestor's defaults block read and
    overlaid root→leaf (each block is a sparse diff against its super), keyed
    `(casefold(prop_name), array_index)` and valued `(package_the_tag_was_serialized_in, tag)` —
    the package matters because the tag's object/name compacts index THAT package's tables.

    This is the primitive `resolve_class_defaults` renders; it is public because a caller that needs
    the default MEMBER-WISE (`mapimport`'s struct member-strip) must decode the raw tag itself
    rather than re-parse a joined `(A=…,B=…)` string."""
    pkgs: dict = _pkgs if _pkgs is not None else {}
    chain: list[tuple[Package, str]] = []
    cur = fqcn
    seen: set[str] = set()
    while cur is not None and cur.casefold() not in seen:
        seen.add(cur.casefold())
        if "." not in cur:
            raise SchemaError(f"class must be fully qualified (Package.Class): {cur!r}")
        pkg_name, cls_name = cur.split(".", 1)
        if pkg_name not in pkgs:
            path = resolver(pkg_name)
            if path is None:
                raise SchemaError(f"cannot resolve defaults of {fqcn}: package {pkg_name!r} "
                                  "not found on the schema search path")
            pkgs[pkg_name] = load_package(path, name=pkg_name)
        pkg = pkgs[pkg_name]
        chain.append((pkg, cls_name))
        cur = _super_fqcn(pkg, cls_name)
    out: dict[tuple[str, int], tuple[Package, PropertyTag]] = {}
    for pkg, cls_name in reversed(chain):                # root first; leaf overrides
        for tag in class_default_tags(pkg, cls_name):
            out[(tag.name.casefold(), tag.array_index)] = (pkg, tag)
    return out


@_schema_guard
def resolve_class_defaults(fqcn: str, *, resolver, schema: dict | None = None,
                           _pkgs: dict | None = None,
                           style: ValueStyle = CLI_STYLE) -> dict[tuple[str, int], str]:
    """The EFFECTIVE class defaults of `fqcn`: every ancestor's defaults block decoded and
    overlaid root→leaf (each block is a sparse diff against its super — verified: `Engine.Light`
    re-states only what it changes vs `Actor`), rendered to canonical CLI text. Keys are
    `(casefold(prop_name), array_index)`. A prop absent here defaults to its type's ZERO (the
    caller synthesizes it — spec §2.3).

    `schema` (casefold name → Prop, the resolved leaf schema) supplies enum naming + struct
    member layouts; when None it is resolved here via the same `resolver`."""
    pkgs: dict = _pkgs if _pkgs is not None else {}
    if schema is None:
        schema = {p.name.casefold(): p
                  for p in resolve_class_properties(fqcn, resolver=resolver)}
    # Build the chain leaf→root, loading each package once (shared with the render cache).
    chain: list[tuple[Package, str]] = []
    cur = fqcn
    seen: set[str] = set()
    while cur is not None and cur.casefold() not in seen:
        seen.add(cur.casefold())
        if "." not in cur:
            raise SchemaError(f"class must be fully qualified (Package.Class): {cur!r}")
        pkg_name, cls_name = cur.split(".", 1)
        if pkg_name not in pkgs:
            path = resolver(pkg_name)
            if path is None:
                raise SchemaError(f"cannot resolve defaults of {fqcn}: package {pkg_name!r} "
                                  "not found on the schema search path")
            pkgs[pkg_name] = load_package(path, name=pkg_name)
        pkg = pkgs[pkg_name]
        chain.append((pkg, cls_name))
        cur = _super_fqcn(pkg, cls_name)
    out: dict[tuple[str, int], str] = {}
    for pkg, cls_name in reversed(chain):            # root first; leaf overrides
        for tag in class_default_tags(pkg, cls_name):
            prop = schema.get(tag.name.casefold())
            out[(tag.name.casefold(), tag.array_index)] = \
                render_default_tag(pkg, tag, prop, resolver=resolver, _pkgs=pkgs,
                                   style=style)
    return out
