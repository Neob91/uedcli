"""Typed T3D-property -> FPropertyTag conversion (N-3 deliverable 1).

The trunk stores each actor property as a raw `(key, value)` STRING pair (see
`model.Actor.props`); `Location` is the one value pulled out into a typed field.  To emit a
correctly-typed `FPropertyTag` for each one we need the property's declared TYPE, which comes
from the class SCHEMA (`uprops.resolve_class_properties`, parsed offline from the real game
`.u`).  This module walks an actor's raw props, looks each up in that schema, parses the string
value into the matching Python value, and produces `actor_write.Prop` tags: Int / Float / Bool /
Byte+enum / Name / Str / Object/Class / Struct (atomic Vector/Rotator/Scale/Color as raw bytes,
any other game struct as a recursive member-wise `StructValue`) / static-array element / dynamic
array (`ArrayValue`).

A non-atomic struct or a dynamic array needs the struct's/array's own member layout, which is not
in the class-prop entry -- it is resolved through the `ImportSchema` (`resolver` + shared package
cache) the caller passes. Without a resolver (an engine-only probe with a bare `schema_lookup`
callback), a non-atomic struct / array is SKIPPED with a warning, never guessed.

Design choices (so a materialize never emits a WRONG tag):
  * A prop not in the schema is SKIPPED and a warning collected -- never guessed, never crashed on.
  * `Location` is routed from `actor.location`; `Rotation` and every other struct is a schema-typed
    prop parsed from its string.
  * Object/Class values (top-level AND inside a struct/array) become a late-bound `ImportRef` the
    assembler resolves to a package import; `None` is a null (0) ref.
  * A partial struct value (the trunk stores only members that differ from the class default) is
    overlaid member-wise on the CLASS DEFAULT: an omitted member takes the class default for that
    (class, prop, array index, member) -- e.g. a Jock's `InitialInventory(0)` omits `Count`, whose
    class default is 1, not 0. Only when the class declares no default does a member fall to zero.

Never raises to the CLI: a malformed value raises `PropError` naming the offending
`Class.prop=value`, which the orchestrator turns into a clean exit-2 (repo rule).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import actor_write as AW
from .actor_write import Prop

# ESheerAxis ordinals (a Scale struct's SheerAxis byte; the enum is a nested struct field, not a
# top-level ByteProperty, so it isn't in the class schema -- pin it here). Engine.u order.
_SHEER_AXIS = {
    "SHEER_None": 0, "SHEER_XY": 1, "SHEER_XZ": 2, "SHEER_YX": 3,
    "SHEER_YZ": 4, "SHEER_ZX": 5, "SHEER_ZY": 6,
}

# The struct value layouts this module can serialize (by the schema's struct type_name).
_KNOWN_STRUCTS = frozenset({"Vector", "Rotator", "Scale", "Color"})

_KEY_INDEX = re.compile(r"^([A-Za-z_]\w*)(?:\((\d+)\))?$")
_OBJREF = re.compile(r"^([A-Za-z_]\w*)'([^']*)'$")   # Class'Package.Group.Name'


class PropError(ValueError):
    """A property value could not be typed/encoded; carries the offending Class.prop=value."""


@dataclass
class ImportRef:
    """A late-bound Object/Class property value -> a package import, resolved by the assembler
    (which owns the import table).  `object_class` is the referenced object's class (e.g.
    'Texture', 'Mesh', 'Sound'); `qualified` is its `Package[.Group].Name`."""
    object_class: str
    qualified: str


def _split_key(key: str) -> tuple[str, int | None]:
    m = _KEY_INDEX.match(key)
    if not m:
        raise PropError(f"unparseable property key: {key!r}")
    base, idx = m.group(1), m.group(2)
    return base, (int(idx) if idx is not None else None)


def _parse_struct_fields(s: str) -> dict[str, str]:
    """Parse a top-level `(Field=Value,Field=Value,...)` into {field: raw_value}, respecting
    nested parens (a value may itself be a `(...)` struct).  Whitespace-tolerant."""
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        raise PropError(f"struct value is not parenthesized: {s!r}")
    inner = s[1:-1]
    out: dict[str, str] = {}
    i, n = 0, len(inner)
    while i < n:
        # read field name up to '='
        j = inner.find("=", i)
        if j < 0:
            break
        name = inner[i:j].strip()
        k = j + 1
        # read value: balance parens, stop at a top-level comma
        depth = 0
        while k < n:
            c = inner[k]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif c == "," and depth == 0:
                break
            k += 1
        out[name] = inner[j + 1:k].strip()
        i = k + 1
    return out


def _f(v: str, default: float = 0.0) -> float:
    v = v.strip()
    return default if v == "" else float(v)


def _i(v: str, default: int = 0) -> int:
    v = v.strip()
    return default if v == "" else int(float(v)) if ("." in v or "e" in v.lower()) else int(v)


def _struct_bytes(type_name: str, raw: str, where: str) -> tuple[bytes, str]:
    """Serialize a struct value -> (bytes, struct_name).  Raises PropError on a bad value."""
    try:
        fields = _parse_struct_fields(raw)
    except PropError as e:
        raise PropError(f"{where}: {e}") from e
    if type_name == "Vector":
        return AW.struct_vector(_f(fields.get("X", "")), _f(fields.get("Y", "")),
                                _f(fields.get("Z", ""))), "Vector"
    if type_name == "Rotator":
        return AW.struct_rotator(_i(fields.get("Pitch", "")), _i(fields.get("Yaw", "")),
                                 _i(fields.get("Roll", ""))), "Rotator"
    if type_name == "Scale":
        # struct Scale { Vector Scale; float SheerRate; ESheerAxis SheerAxis; }
        # The inner Vector (default 1,1,1) may be flattened or nested as `Scale=(X=..)`.
        sc = fields.get("Scale")
        if sc is not None:
            sv = _parse_struct_fields(sc)
        else:
            sv = fields
        sx = _f(sv.get("X", ""), 1.0)
        sy = _f(sv.get("Y", ""), 1.0)
        sz = _f(sv.get("Z", ""), 1.0)
        rate = _f(fields.get("SheerRate", ""), 0.0)
        axis_raw = fields.get("SheerAxis", "").strip()
        axis = _SHEER_AXIS.get(axis_raw, 0) if axis_raw and not axis_raw.lstrip("-").isdigit() \
            else (int(axis_raw) if axis_raw else 0)
        return AW.struct_scale(sx, sy, sz, rate, axis), "Scale"
    if type_name == "Color":
        return AW.struct_color(_i(fields.get("R", "")), _i(fields.get("G", "")),
                               _i(fields.get("B", "")), _i(fields.get("A", ""))), "Color"
    raise PropError(f"{where}: unsupported struct type {type_name!r}")


def _byte_value(sp, raw: str, where: str) -> int:
    """A ByteProperty value: an enum NAME (via the schema's enum_value_names ordinal) or a
    literal 0..255."""
    raw = raw.strip()
    if raw == "":
        raise PropError(f"{where}: empty byte value")
    if raw.lstrip("-").isdigit():
        return int(raw) & 0xFF
    # an enum value name
    names = list(sp.enum_value_names)
    fold = {n.casefold(): idx for idx, n in enumerate(names)}
    idx = fold.get(raw.casefold())
    if idx is None:
        raise PropError(f"{where}: byte value {raw!r} is not an integer and not in the enum "
                        f"{sp.type_name or '<none>'} {tuple(names) or '()'}")
    return idx & 0xFF


class _CallableSchema:
    """Adapt a bare `schema_lookup(fqcn) -> {casefold: uprops.Prop}` callback to the `ImportSchema`
    surface used here. It has no resolver/package cache, so non-atomic structs and dynamic arrays
    cannot be serialized (they warn+skip -- the engine-only-probe behaviour)."""

    def __init__(self, lookup):
        self._lookup = lookup
        self.resolver = None
        self.packages: dict = {}

    def props(self, fqcn: str) -> dict:
        return self._lookup(fqcn)


def _object_ref(raw: str, where: str):
    """A top-level or in-struct Object/Class value -> `ImportRef` (the assembler resolves the
    import) or `0` for a null. Raises on a bare/unqualified ref (it cannot be imported)."""
    val = raw.strip()
    if val in ("", "None"):
        return 0
    m = _OBJREF.match(val)
    if not m or "." not in m.group(2):
        raise PropError(f"{where}: object ref {val!r} is not a qualified Class'Package.Name'")
    return ImportRef(m.group(1), m.group(2))


def _member_prop(schema, members_pkg, m, raw: str | None, where: str) -> Prop:
    """One struct member / array element as a `Prop` used for its (ptype, value, struct_name) only.
    `raw` is the member's T3D value text, or None when the (partial) struct omitted it -- an omitted
    member takes the member type's zero. `m` is the member's `uprops.Prop`; `members_pkg` is the
    package its schema was decoded from (for a nested struct's own members)."""
    kind = m.kind
    if kind == "IntProperty":
        return Prop(m.name, AW.PT_INT, _i(raw or ""))
    if kind == "FloatProperty":
        return Prop(m.name, AW.PT_FLOAT, _f(raw or ""))
    if kind == "BoolProperty":
        return Prop(m.name, AW.PT_BOOL, (raw or "").strip().casefold() in ("true", "1"))
    if kind == "ByteProperty":
        return Prop(m.name, AW.PT_BYTE, _byte_value(m, raw, where) if (raw or "").strip() else 0)
    if kind == "NameProperty":
        return Prop(m.name, AW.PT_NAME, ((raw or "").strip().strip('"')) or "None")
    if kind == "StrProperty":
        return Prop(m.name, AW.PT_STR, _unquote(raw or ""))
    if kind in ("ObjectProperty", "ClassProperty"):
        return Prop(m.name, AW.PT_OBJECT, _object_ref(raw or "", where))
    if kind == "StructProperty":
        p = _struct_prop(schema, members_pkg, m, raw, None, where)
        if p is None:
            raise PropError(f"{where}: cannot resolve nested struct {m.type_name!r} layout")
        return p
    raise PropError(f"{where}: unsupported struct-member kind {kind}")


def _unquote(v: str) -> str:
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == '"' and v[-1] == '"' else v


def _default_members(schema, pkg, sp, fqcn, array_index) -> dict:
    """The class default of struct prop `sp` at `array_index`, as `{member_casefold: text}`. When the
    class chain declares a default (`defaultproperties`), its members win; otherwise every member is
    the type's zero. This is what fills a partial struct value: the trunk stores only members that
    DIFFER from this, so an omitted member takes its default here, not a bare zero (a Jock's
    `InitialInventory(0)` omits `Count`, whose class default is 1, not 0)."""
    from uedcli import uprops
    if fqcn is None or not hasattr(schema, "default_tag"):
        tree = uprops.zero_struct_tree(pkg, sp, resolver=schema.resolver, _pkgs=schema.packages,
                                       style=uprops.T3D_STYLE)
    else:
        entry = schema.default_tag(fqcn, sp.name, array_index or 0)
        if entry is not None and entry[1].struct_name is not None:
            tree = uprops.struct_tag_member_tree(entry[0], entry[1], sp, resolver=schema.resolver,
                                                 _pkgs=schema.packages, style=uprops.T3D_STYLE)
        else:
            tree = uprops.zero_struct_tree(pkg, sp, resolver=schema.resolver,
                                           _pkgs=schema.packages, style=uprops.T3D_STYLE)
    return {k.casefold(): v for k, v in _parse_struct_fields(uprops.render_member_tree(tree)).items()}


def _struct_prop(schema, pkg, sp, raw: str | None, array_index, where: str, *, fqcn=None) -> Prop:
    """A StructProperty value -> a `Prop`. Atomic structs (Vector/Rotator/Scale/Color) stay raw
    bytes (the proven fast path); any other struct becomes a recursive member-wise `StructValue`. The
    binary struct value is FULL (every member, positionally), so a partial trunk value is overlaid on
    the class default (`_default_members`): stated member wins, else the class default. `pkg` is the
    package `sp` was decoded from; `fqcn` the actor class (for the class default)."""
    from uedcli import uprops
    tn = sp.type_name
    if tn in _KNOWN_STRUCTS:
        body, name = _struct_bytes(tn, raw or "()", where)
        return Prop(sp.name, AW.PT_STRUCT, body, struct_name=name, array_index=array_index)
    if schema.resolver is None or sp.type_ref == 0:
        return None                                      # no resolver -> can't get the layout; skip
    members_pkg, members = uprops.struct_member_schema(pkg, sp, resolver=schema.resolver,
                                                       _pkgs=schema.packages)
    stated = {k.casefold(): v for k, v in (_parse_struct_fields(raw).items() if raw else ())}
    defaults = _default_members(schema, pkg, sp, fqcn, array_index)
    out = []
    for m in members:
        for i in range(m.array_dim):
            fk = m.name.casefold() if m.array_dim == 1 else f"{m.name.casefold()}({i})"
            text = stated[fk] if fk in stated else defaults.get(fk)
            out.append(_member_prop(schema, members_pkg, m, text, f"{where}.{m.name}"))
    return Prop(sp.name, AW.PT_STRUCT, AW.StructValue(tn, out), struct_name=tn,
                array_index=array_index)


def _owner_pkg(schema, sp):
    """The package `sp`'s owner class was decoded from (its `type_ref` is relative to it)."""
    from uedcli.upackage import load_package
    owner = getattr(sp, "owner", None)
    if not owner or "." not in owner or schema.resolver is None:
        return None
    pkg_name = owner.split(".", 1)[0]
    if pkg_name not in schema.packages:
        path = schema.resolver(pkg_name)
        if path is None:
            return None
        schema.packages[pkg_name] = load_package(path, name=pkg_name)
    return schema.packages[pkg_name]


def _dynamic_array_prop(schema, sp, items, where: str) -> Prop | None:
    """A dynamic `ArrayProperty` -> one `ArrayValue` tag: the elements coalesced (each arrives as a
    separate `foo(i)=` T3D line). The element kind comes from `sp.array_inner` (the schema's only
    record of it). None (skip+warn) without a resolver."""
    from uedcli import uprops
    inner = sp.array_inner
    if schema.resolver is None or inner is None:
        return None
    pkg = _owner_pkg(schema, sp)
    elements = []
    for idx, value in sorted(items):
        if inner.kind == "StructProperty":
            elements.append(_struct_prop(schema, pkg, inner, value, None, f"{where}({idx})"))
        else:
            elements.append(_member_prop(schema, pkg, inner, value, f"{where}({idx})"))
    return Prop(sp.name, AW.PT_ARRAY, AW.ArrayValue(elements))


def convert_prop(schema, sp, raw: str, array_index, where: str, fqcn=None) -> Prop | None:
    """Convert one raw (schema-Prop, value-string) into a typed `Prop`. Returns None (caller warns)
    for a value/type this path cannot serialize (a non-atomic struct with no resolver). `sp` is a
    `uprops.Prop`; `schema` is the `ImportSchema` (for struct member layouts + defaults); `fqcn` the
    actor class (for a struct's class default)."""
    kind = sp.kind
    if kind == "IntProperty":
        return Prop(sp.name, AW.PT_INT, _i(raw), array_index=array_index)
    if kind == "FloatProperty":
        return Prop(sp.name, AW.PT_FLOAT, _f(raw), array_index=array_index)
    if kind == "BoolProperty":
        return Prop(sp.name, AW.PT_BOOL, raw.strip().casefold() in ("true", "1"))
    if kind == "ByteProperty":
        return Prop(sp.name, AW.PT_BYTE, _byte_value(sp, raw, where), array_index=array_index)
    if kind == "NameProperty":
        return Prop(sp.name, AW.PT_NAME, raw.strip().strip('"'), array_index=array_index)
    if kind == "StrProperty":
        return Prop(sp.name, AW.PT_STR, _unquote(raw), array_index=array_index)
    if kind == "StructProperty":
        return _struct_prop(schema, _owner_pkg(schema, sp), sp, raw, array_index, where, fqcn=fqcn)
    if kind in ("ObjectProperty", "ClassProperty"):
        # Emit even an explicit `None` (ref 0): a trunk only stores a value that DIFFERS from the class
        # default, so `contents=None` on a crate whose default is `Ammo10mm` is a real override -- if
        # dropped, the built actor falls back to the non-None default. Matches the struct-member path.
        return Prop(sp.name, AW.PT_OBJECT, _object_ref(raw, where), array_index=array_index)
    return None                                          # Pointer/... -> skip


def convert_actor_props(qualified_class: str, raw_props, schema):
    """Convert an actor's raw `(key, value)` props into typed `Prop`s.

    `schema` is an `ImportSchema` (its `.props(fqcn)` gives the class schema unioned over the Super
    chain; its `.resolver`/`.packages` resolve struct member layouts) -- or a bare
    `schema_lookup(fqcn) -> {casefold: uprops.Prop}` callback, adapted to that surface (then
    non-atomic structs / dynamic arrays skip+warn). Returns `(props, warnings)`; `warnings` names
    every skipped prop. Raises `PropError` (naming the offender) on a present+typed malformed value.

    Props are grouped by base name first, so a dynamic array's `foo(0)`/`foo(1)` lines coalesce into
    one tag; a scalar or static-array property keeps one tag per (element) line."""
    if callable(schema):
        schema = _CallableSchema(schema)
    try:
        class_props = schema.props(qualified_class)
    except Exception as e:
        # A bare (unqualified) or unresolvable class: type nothing rather than crash the build. The
        # real path pre-validates every class in `apply._level_defaults` (fail-fast exit 2), so this
        # only fires for an engine-only probe or a genuinely absent package -- warn, don't abort.
        return [], [f"{qualified_class}: class schema unavailable ({e}); typed props skipped"]
    groups: dict[str, tuple[str, list]] = {}
    for key, value in raw_props:
        base, idx = _split_key(key)
        groups.setdefault(base.casefold(), (base, []))[1].append((idx, value))

    out: list[Prop] = []
    warnings: list[str] = []
    for basef, (base, items) in groups.items():
        sp = class_props.get(basef)
        if sp is None:
            warnings.append(f"{qualified_class}.{base}: not in class schema (skipped)")
            continue
        if sp.kind == "ArrayProperty":
            where = f"{qualified_class}.{base}"
            p = _guarded(where, _dynamic_array_prop, schema, sp, items, where)
            _collect(out, warnings, p, qualified_class, base, sp)
            continue
        for idx, value in items:
            where = f"{qualified_class}.{base}{f'({idx})' if idx is not None else ''}={value}"
            p = _guarded(where, convert_prop, schema, sp, value, idx, where, qualified_class)
            _collect(out, warnings, p, qualified_class, base, sp)
    return out, warnings


def _guarded(where, fn, *args):
    """Run a converter, re-raising a `PropError` and wrapping any other value error as one."""
    try:
        return fn(*args)
    except PropError:
        raise
    except (ValueError, KeyError) as e:
        raise PropError(f"{where}: {e}") from e


def _collect(out, warnings, p, cls, base, sp) -> None:
    if p is None:
        warnings.append(f"{cls}.{base}: {sp.kind}"
                        f"{'/' + sp.type_name if sp.type_name else ''} not emitted (skipped)")
    else:
        out.append(p)
