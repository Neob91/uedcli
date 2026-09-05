"""Operator/native catalog + UFunction body reader for UnrealScript bytecode lowering.

The lowering (`lower.py`) turns operators, built-in calls, and casts into native-opcode calls. The
native index for each comes from the callee `UFunction`'s stored `iNative`; this module reads it
straight out of the compiled `.u` packages (index-independent — no package-ordering work) and indexes
it by operator symbol / function name + operand types.

A `UFunction` export body is `[None][SuperField][Next][ScriptText][Children][FriendlyName]
[Line u32][TextPos u32][ScriptSize u32] <script> [iNative u16][OperPrecedence u8][FunctionFlags u32]
[RepOffset u16 iff FUNC_Net]` — 6 compact indices, 12 header bytes, the bytecode, then the tail. Its
operand types come from the `Children` param properties (kind → type label).
"""
from __future__ import annotations

import glob
import os
import struct
from dataclasses import dataclass
from functools import lru_cache

from ..upackage import (Package, load_package, read_compact_index as _rci, read_fstring,
                        read_property_tags)
from ..uprops.base import PROPERTY_TYPES
from ..uprops.ufield import (_decode_property, _field_next, enum_values, find_struct_export,
                             struct_members)
from .bytecode import Tok, decode_script

# EFunctionFlags (UE1)
FUNC_FINAL = 0x0001
FUNC_ITERATOR = 0x0004
FUNC_LATENT = 0x0008
FUNC_PRE_OPERATOR = 0x0010
FUNC_NET = 0x0040
FUNC_NATIVE = 0x0400
FUNC_EVENT = 0x0800
FUNC_OPERATOR = 0x1000
FUNC_STATIC = 0x2000

# ECppForm / CPF_ param flags (UE1)
CPF_OPTIONAL = 0x00000010
CPF_PARM = 0x00000080
CPF_OUT = 0x00000100
CPF_RETURN = 0x00000400
CPF_COERCE = 0x00000800

# UProperty subclass -> lowering type label. Object/struct types carry their class/struct name so
# member access can resolve them (`object:Pawn`, `struct:Vector`); primitives stay bare.
_PRIM_PROP = {
    "IntProperty": "int", "FloatProperty": "float", "BoolProperty": "bool",
    "ByteProperty": "byte", "StrProperty": "string", "NameProperty": "name",
}


def prop_type_label(prop) -> str:
    """The lowering type label for a decoded UProperty."""
    k = prop.kind
    if k in _PRIM_PROP:
        return _PRIM_PROP[k]
    if k == "ObjectProperty":
        return "object:" + (prop.type_name or "Object").casefold()
    if k == "ClassProperty":
        return "class"
    if k == "StructProperty":
        return "struct:" + (prop.type_name or "Struct").casefold()
    if k == "ArrayProperty":
        return "array"
    return "object:Object"


def is_object(t: str) -> bool:
    return t.startswith("object:")


def is_struct(t: str) -> bool:
    return t.startswith("struct:")


def class_of(t: str) -> str | None:
    """The class/struct name inside an `object:`/`struct:` label."""
    return t.split(":", 1)[1] if (":" in t) else None

# Widening conversions allowed when matching a PRIMITIVE call/operator argument to a parameter,
# cheapest first. (from -> to): cost. Exact match is cost 0. Ranks overloads; never emits code.
_WIDEN = {
    ("byte", "int"): 1, ("byte", "float"): 2, ("int", "float"): 1,
    ("byte", "string"): 4, ("int", "string"): 4, ("float", "string"): 4,
    ("bool", "string"): 4, ("name", "string"): 4,
    ("byte", "bool"): 3, ("int", "bool"): 3, ("float", "bool"): 3, ("name", "bool"): 3,
}


@dataclass(frozen=True, kw_only=True)
class FuncBody:
    """One decoded UFunction: identity, its stored bytecode, and the fields lowering needs."""
    name: str                       # FriendlyName (the operator symbol for operators)
    package: str
    class_name: str
    script_size: int
    tokens: tuple[Tok, ...]
    inative: int
    precedence: int
    flags: int
    param_types: tuple[str, ...]    # operand/param type labels (return value excluded)
    return_type: str | None

    @property
    def is_operator(self) -> bool:
        return bool(self.flags & FUNC_OPERATOR)

    @property
    def is_preoperator(self) -> bool:
        return bool(self.flags & FUNC_PRE_OPERATOR)

    @property
    def is_final(self) -> bool:
        return bool(self.flags & FUNC_FINAL)

    @property
    def is_native(self) -> bool:
        return self.inative != 0


def _read_const_value(pkg: Package, idx1: int) -> str:
    """A UConst body: [None][SuperField][Next][Value FString] — returns the source text of the value."""
    buf, p = pkg.buf, pkg.exports[idx1 - 1]["soff"]
    _none, p = _rci(buf, p)
    _sup, p = _rci(buf, p)
    _next, p = _rci(buf, p)
    value, _p = read_fstring(buf, p)
    return value.strip()


def name_resolver(pkg: Package):
    """A `decode_script` resolver that maps object/name refs to their NAME string, so decoded tokens
    are index-independent (the lowering oracle: lowered tokens == these decoded tokens)."""
    def resolve(kind: str, index: int) -> str:
        if kind == "name":
            return pkg.names[index] if 0 <= index < len(pkg.names) else "None"
        return pkg.name_of_ref(index) or "None"
    return resolve


def _params(pkg: Package, children: int) -> tuple[tuple[str, ...], str | None]:
    ptypes: list[str] = []
    rtype: str | None = None
    cur = children
    for _ in range(256):
        if cur <= 0:
            break
        prop = _decode_property(pkg, cur, "")
        flags = prop.property_flags
        if flags & CPF_PARM:
            label = prop_type_label(prop)
            if flags & CPF_RETURN:
                rtype = label
            else:
                ptypes.append(label)
        cur = _field_next(pkg, cur)
    return tuple(ptypes), rtype


def read_function(pkg: Package, export_index1: int) -> FuncBody:
    """Decode the UFunction export at 1-based `export_index1` into a `FuncBody`."""
    e = pkg.exports[export_index1 - 1]
    buf = pkg.buf
    end = e["soff"] + e["ssize"]
    _tags, p = read_property_tags(pkg, e["soff"], end)          # leading [None]
    _sup, p = _rci(buf, p)
    _next, p = _rci(buf, p)
    _stext, p = _rci(buf, p)
    children, p = _rci(buf, p)
    friendly, p = _rci(buf, p)
    line, textpos, ssize = struct.unpack_from("<III", buf, p); p += 12
    tokens, p = decode_script(buf, p, ssize, name_resolver(pkg))
    inative, precedence = struct.unpack_from("<HB", buf, p); p += 3
    flags = struct.unpack_from("<I", buf, p)[0]; p += 4
    ptypes, rtype = _params(pkg, children)
    return FuncBody(
        name=pkg.names[friendly], package=pkg.name,
        class_name=pkg.name_of_ref(e["outer"]) or "", script_size=ssize,
        tokens=tuple(tokens), inative=inative, precedence=precedence, flags=flags,
        param_types=ptypes, return_type=rtype)


def iter_functions(pkg: Package):
    """Yield a `FuncBody` for every UFunction export in `pkg`."""
    for i, e in enumerate(pkg.exports):
        if pkg.name_of_ref(e["cls"]) == "Function":
            yield read_function(pkg, i + 1)


class Catalog:
    """Operator + native-function lookup, built from a set of compiled packages."""

    def __init__(self, funcs: list[FuncBody]) -> None:
        self.funcs = funcs
        self._by_op: dict[str, list[FuncBody]] = {}
        self._by_name: dict[str, list[FuncBody]] = {}
        for fb in funcs:
            if fb.is_operator:
                self._by_op.setdefault(fb.name, []).append(fb)
            self._by_name.setdefault(fb.name.casefold(), []).append(fb)

    def binary_operator(self, symbol: str, left: str, right: str) -> FuncBody | None:
        cands = [f for f in self._by_op.get(symbol, ())
                 if not f.is_preoperator and len(f.param_types) == 2]
        return _best(cands, (left, right))

    def unary_operator(self, symbol: str, operand: str, *, pre: bool) -> FuncBody | None:
        cands = [f for f in self._by_op.get(symbol, ())
                 if f.is_preoperator == pre and len(f.param_types) == 1]
        return _best(cands, (operand,))

    def function(self, name: str, argtypes: tuple[str, ...]) -> FuncBody | None:
        cands = [f for f in self._by_name.get(name.casefold(), ()) if not f.is_operator]
        exact = [f for f in cands if len(f.param_types) == len(argtypes)]
        best = _best(exact, argtypes)
        return best if best is not None else (cands[0] if cands else None)


def _best(cands: list[FuncBody], argtypes: tuple[str, ...]) -> FuncBody | None:
    """The cheapest overload that each argument can widen into, or None if none match."""
    scored: list[tuple[int, int, FuncBody]] = []
    for i, fb in enumerate(cands):
        cost = _match_cost(fb.param_types, argtypes)
        if cost is not None:
            scored.append((cost, i, fb))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1]))
    return scored[0][2]


def _match_cost(params: tuple[str, ...], args: tuple[str, ...]) -> int | None:
    if len(params) != len(args):
        return None
    total = 0
    for want, got in zip(params, args):
        if want == got:
            continue
        if got == "none" and (is_object(want) or is_struct(want) or want in ("class", "name")):
            continue
        if is_object(want) and (is_object(got) or got == "class"):
            continue                                    # any object/class ref matches an object parm
        if is_object(got) and want == "string":
            total += 4                                  # object -> string (ToString) coercion
            continue
        if (is_struct(want) or is_struct(got)) and want != got:
            return None                                 # struct params need the exact struct
        step = _WIDEN.get((got, want))
        if step is None:
            return None
        total += step
    return total


@lru_cache(maxsize=8)
def _load_catalog(search_dir: str, packages: tuple[str, ...]) -> Catalog:
    funcs: list[FuncBody] = []
    for stem in packages:
        pkg = load_package(f"{search_dir}/{stem}")
        funcs.extend(iter_functions(pkg))
    return Catalog(funcs)


def load_catalog(search_dir: str, packages=("core.u", "Engine.u")) -> Catalog:
    """Build (and cache) the native catalog from `<search_dir>/<pkg>` for each package stem+ext."""
    return _load_catalog(search_dir, tuple(packages))


# ── class graph: cross-package member/function resolution ───────────────────────────────────────
# In-memory byte size / alignment of value types (for struct layout & Context bSize). bool is a
# 4-byte DWORD; byte aligns to 1, everything else to 4. UE1 lays out struct members aligned and pads
# the struct's total to its widest member's alignment (e.g. MouseCursor 4+4+4+1 -> 16, not 13).
_TYPE_SIZE = {"int": 4, "float": 4, "bool": 4, "name": 4, "class": 4, "byte": 1}
_TYPE_ALIGN = {"int": 4, "float": 4, "bool": 4, "name": 4, "class": 4, "byte": 1}


def _align_up(offset: int, align: int) -> int:
    return (offset + align - 1) // align * align


def _type_size(ty: str, graph: "ClassGraph", seen: frozenset[str]) -> int | None:
    if ty.startswith("object:"):
        return 4
    if ty.startswith("struct:"):
        return graph.struct_size(ty.split(":", 1)[1], seen)
    return _TYPE_SIZE.get(ty)                            # None for string/array (unknown here)


def _type_align(ty: str, graph: "ClassGraph", seen: frozenset[str]) -> int | None:
    if ty.startswith("object:"):
        return 4
    if ty.startswith("struct:"):
        return graph.struct_align(ty.split(":", 1)[1], seen)
    return _TYPE_ALIGN.get(ty)


@dataclass(frozen=True, kw_only=True)
class ClassSig:
    """A class's members and functions (own + inherited, resolved across packages)."""
    name: str
    package: str
    super_name: str | None
    members: dict[str, str]                 # casefolded field name -> type label
    functions: dict[str, FuncBody]          # casefolded function name -> its FuncBody


def _class_children(pkg: Package, idx1: int) -> int:
    """A UClass export's `Children` head ref (no leading None terminator: Super, Next, ScriptText,
    Children …)."""
    e = pkg.exports[idx1 - 1]
    buf, p = pkg.buf, e["soff"]
    _sup, p = _rci(buf, p)
    _next, p = _rci(buf, p)
    _st, p = _rci(buf, p)
    children, _p = _rci(buf, p)
    return children


class ClassGraph:
    """Resolve a class name to its members/functions (own + inherited) across a set of packages.
    Only the indexed packages are searched; a type from an unindexed package resolves to None (its
    members stay unresolved, so lowering raises `LowerError` rather than guessing)."""

    def __init__(self, package_paths: list[str]) -> None:
        self._paths = package_paths
        self._pkgs: dict[str, Package] = {}
        self._index: dict[str, tuple[str, int]] | None = None      # class cf -> (stem, idx1)
        self._struct_loc: dict[str, tuple[str, int]] | None = None  # struct cf -> (stem, idx1)
        self._enum_vals: dict[str, int] | None = None               # enum tag cf -> ordinal
        self._enum_types: set[str] | None = None                     # enum type names, casefolded
        self._consts: dict[str, str] | None = None                   # const name cf -> value text
        self._cache: dict[str, ClassSig | None] = {}
        self._struct_cache: dict[str, dict[str, str] | None] = {}

    def _build_index(self) -> None:
        self._index = {}
        self._struct_loc = {}
        self._enum_vals = {}
        self._enum_types = set()
        self._consts = {}
        for path in self._paths:
            stem = os.path.splitext(os.path.basename(path))[0]
            try:
                pkg = load_package(path)
            except Exception:
                continue
            self._pkgs[stem] = pkg
            for i, e in enumerate(pkg.exports):
                nm = pkg.names[e["nm"]] if 0 <= e["nm"] < len(pkg.names) else None
                if nm is None:
                    continue
                cls = pkg.name_of_ref(e["cls"])
                if e["cls"] == 0:
                    self._index.setdefault(nm.casefold(), (stem, i + 1))
                elif cls == "Struct":
                    self._struct_loc.setdefault(nm.casefold(), (stem, i + 1))
                elif cls == "Enum":
                    self._enum_types.add(nm.casefold())
                    try:
                        for ordinal, tag in enumerate(enum_values(pkg, i + 1)):
                            self._enum_vals.setdefault(tag.casefold(), ordinal)
                    except Exception:
                        pass
                elif cls == "Const":
                    try:
                        self._consts.setdefault(nm.casefold(), _read_const_value(pkg, i + 1))
                    except Exception:
                        pass

    def const_value(self, name: str) -> str | None:
        if self._consts is None:
            self._build_index()
        return self._consts.get(name.casefold())

    def enum_ordinal(self, tag: str) -> int | None:
        if self._enum_vals is None:
            self._build_index()
        return self._enum_vals.get(tag.casefold())

    def is_enum_name(self, name: str) -> bool:
        if self._enum_types is None:
            self._build_index()
        return name.casefold() in self._enum_types

    def is_struct_name(self, name: str) -> bool:
        if self._struct_loc is None:
            self._build_index()
        return name.casefold() in self._struct_loc

    def struct_member_type(self, struct_name: str, field: str) -> str | None:
        if self._struct_loc is None:
            self._build_index()
        key = struct_name.casefold()
        if key not in self._struct_cache:
            loc = self._struct_loc.get(key)
            if loc is None:
                self._struct_cache[key] = None
            else:
                pkg = self._pkgs[loc[0]]
                idx = find_struct_export(pkg, struct_name)
                try:
                    props = struct_members(pkg, idx, owner=struct_name) if idx else []
                except Exception:
                    props = []
                self._struct_cache[key] = {p.name.casefold(): prop_type_label(p) for p in props}
        table = self._struct_cache[key]
        return table.get(field.casefold()) if table else None

    def _struct_fields(self, name: str) -> dict[str, str] | None:
        self.struct_member_type(name, "")               # ensures the table is built + cached
        return self._struct_cache.get(name.casefold())

    def struct_align(self, name: str, _seen: frozenset[str] = frozenset()) -> int | None:
        """A struct's alignment = the widest alignment among its members (min 1)."""
        key = name.casefold()
        if key in _seen:
            return None
        fields = self._struct_fields(name)
        if not fields:
            return None
        align = 1
        for ty in fields.values():
            a = _type_align(ty, self, _seen | {key})
            if a is None:
                return None
            align = max(align, a)
        return align

    def struct_size(self, name: str, _seen: frozenset[str] = frozenset()) -> int | None:
        """In-memory byte size of a struct value (for a Context's bSize) — members laid out aligned,
        total padded to the struct's alignment. None if any member's size is unknown."""
        key = name.casefold()
        if key in _seen:
            return None                                 # cyclic (shouldn't happen)
        fields = self._struct_fields(name)
        if not fields:
            return None
        seen = _seen | {key}
        offset = 0
        max_align = 1
        for ty in fields.values():
            size = _type_size(ty, self, seen)
            align = _type_align(ty, self, seen)
            if size is None or align is None:
                return None
            offset = _align_up(offset, align) + size
            max_align = max(max_align, align)
        return _align_up(offset, max_align)

    def _locate(self, name: str) -> tuple[Package, int] | None:
        if self._index is None:
            self._build_index()
        loc = self._index.get(name.casefold())
        if loc is None:
            return None
        return self._pkgs[loc[0]], loc[1]

    def class_sig(self, name: str) -> ClassSig | None:
        key = name.casefold()
        if key in self._cache:
            return self._cache[key]
        self._cache[key] = None                         # guard against a cyclic super chain
        loc = self._locate(name)
        if loc is None:
            return None
        pkg, idx1 = loc
        e = pkg.exports[idx1 - 1]
        super_name = pkg.name_of_ref(e["sup"]) if e["sup"] != 0 else None
        members: dict[str, str] = {}
        functions: dict[str, FuncBody] = {}
        if super_name:
            sup = self.class_sig(super_name)
            if sup is not None:
                members.update(sup.members)
                functions.update(sup.functions)
        cur = _class_children(pkg, idx1)
        for _ in range(4096):
            if cur <= 0:
                break
            ee = pkg.exports[cur - 1]
            kind = pkg.name_of_ref(ee["cls"])
            if kind in PROPERTY_TYPES:
                prop = _decode_property(pkg, cur, "")
                members[pkg.names[ee["nm"]].casefold()] = prop_type_label(prop)
            elif kind == "Function":
                fb = read_function(pkg, cur)
                functions[fb.name.casefold()] = fb
            cur = _field_next(pkg, cur)
        sig = ClassSig(name=pkg.names[e["nm"]], package=pkg.name, super_name=super_name,
                       members=members, functions=functions)
        self._cache[key] = sig
        return sig

    def member_type(self, class_name: str, field: str) -> str | None:
        sig = self.class_sig(class_name)
        return sig.members.get(field.casefold()) if sig else None

    def function(self, class_name: str, name: str) -> FuncBody | None:
        sig = self.class_sig(class_name)
        return sig.functions.get(name.casefold()) if sig else None


@lru_cache(maxsize=8)
def _load_graph(search_dir: str, packages: tuple[str, ...]) -> ClassGraph:
    return ClassGraph([os.path.join(search_dir, p) for p in packages])


def load_graph(search_dir: str, packages=("core.u", "Engine.u")) -> ClassGraph:
    """Build (and cache) the class graph from `<search_dir>/<pkg>` for each package stem+ext."""
    return _load_graph(search_dir, tuple(packages))
