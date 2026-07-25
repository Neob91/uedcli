"""Typed T3D-property -> FPropertyTag conversion (N-3 deliverable 1).

The trunk stores each actor property as a raw `(key, value)` STRING pair (see
`model.Actor.props`); `Location` is the one value pulled out into a typed field.  To emit a
correctly-typed `FPropertyTag` for each one we need the property's declared TYPE, which comes
from the class SCHEMA (`uprops.resolve_class_properties`, parsed offline from the real game
`.u`).  This module walks an actor's raw props, looks each up in that schema, parses the string
value into the matching Python value, and produces `actor_write.Prop` tags (Int / Float / Bool /
Byte+enum / Name / Str / Struct(Vector,Rotator,Scale,Color) / static-array).

Design choices (kept deliberately conservative so a materialize never emits a WRONG tag):
  * A prop whose name is not in the schema, or whose declared type this module does not yet
    encode (an unknown struct, an object/class value we can't resolve here), is SKIPPED and a
    human-readable warning is collected — never guessed, never crashed on.
  * `Location` is routed from `actor.location`; `Rotation` (and every other struct) is an
    ordinary schema-typed prop parsed from its string.
  * Object/Class-valued props are resolved to a package IMPORT via a late-bound `ImportRef`
    placeholder (the assembler holds the import table) or, for `None`, dropped.

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


def convert_prop(sp, raw: str, array_index: int | None, where: str) -> Prop | None:
    """Convert one raw (schema-Prop, value-string) into a typed `Prop`.  Returns None (with the
    caller collecting a warning) for a value/type this cut skips.  `sp` is a `uprops.Prop`."""
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
        return Prop(sp.name, AW.PT_STR, raw.strip().strip('"'), array_index=array_index)
    if kind == "StructProperty":
        tn = sp.type_name
        if tn not in _KNOWN_STRUCTS:
            return None                                  # unknown struct layout -> skip+warn
        body, struct_name = _struct_bytes(tn, raw, where)
        return Prop(sp.name, AW.PT_STRUCT, body, struct_name=struct_name,
                    array_index=array_index)
    if kind in ("ObjectProperty", "ClassProperty"):
        val = raw.strip()
        if val in ("", "None"):
            return None                                  # default null -> omit
        m = _OBJREF.match(val)
        if not m:
            return None                                  # a bare/odd object value -> skip+warn
        obj_class, qualified = m.group(1), m.group(2)
        if "." not in qualified:
            return None                                  # unqualified -> can't import; skip
        return Prop(sp.name, AW.PT_OBJECT, ImportRef(obj_class, qualified),
                    array_index=array_index)
    return None                                          # ArrayProperty/Pointer/... -> skip


def convert_actor_props(qualified_class: str, raw_props, schema_lookup):
    """Convert an actor's raw `(key, value)` props into typed `Prop`s.

    `schema_lookup(fqcn) -> {casefold(name): uprops.Prop}` supplies the class schema (unioned
    over the Super chain).  Returns `(props, warnings)`; `warnings` names every skipped prop so
    the caller can flag them (never silently lost).  Raises `PropError` (naming the offender) on
    a value that is present+typed but malformed."""
    schema = schema_lookup(qualified_class)
    out: list[Prop] = []
    warnings: list[str] = []
    for key, value in raw_props:
        base, idx = _split_key(key)
        sp = schema.get(base.casefold())
        if sp is None:
            warnings.append(f"{qualified_class}.{key}: not in class schema (skipped)")
            continue
        where = f"{qualified_class}.{key}={value}"
        try:
            p = convert_prop(sp, value, idx, where)
        except PropError:
            raise
        except (ValueError, KeyError) as e:
            raise PropError(f"{where}: {e}") from e
        if p is None:
            warnings.append(f"{where}: {sp.kind}"
                            f"{'/' + sp.type_name if sp.type_name else ''} not emitted (skipped)")
        else:
            out.append(p)
    return out, warnings
