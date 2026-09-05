"""Compile a parsed UnrealScript class into a `CompiledPackage` (see `model.py`) that serializes
byte-identical to UCC, for the BYTECODE-FREE declaration surface: the class header + its modifiers
(→ `ClassFlags`/`ClassWithin`/`ClassConfigName`), member `var`s (scalar/static-array/object/class/
struct/dynamic-array/enum-typed, with their `var()`/`const`/`config`/… modifier flags and editor
category), `enum`/`const`/`struct` declarations, and a `defaultproperties` block. No function bodies /
bytecode, states, replication, `#exec`, or `cpptext` yet.

Pipeline: `parse` (parser.py) → this module builds the object graph (a `ScriptText` UTextBuffer, one
UProperty per member var / struct member / array inner, a UEnum/UConst/UStruct per type decl, the
UClass), resolves every ref, and returns the linked model. `serialize.serialize` then encodes it.

Ordering: the name/import/export TABLE order needs the engine global-index tie-break table, not yet
available, so a caller passes `order_override=(names, imports, exports)` taken from a golden. Without
it, only scalar-member classes order autonomously (`order_package`); any new-kind member raises
`NotImplementedError` naming the gap.

The measured `ClassFlags`/`CPF_` bit maps and the enum/const/struct/property-tail byte layouts are
pinned by `test_uscript_compile` against committed UCC goldens.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field

from ..native.actor_write import (PT_ARRAY, PT_BOOL, PT_BYTE, PT_FLOAT, PT_INT, PT_NAME, PT_OBJECT,
                                   PT_STR, PT_STRUCT, ArrayValue, Prop, StructValue, write_props)
from .ast import ClassDecl, ConstDecl, EnumDecl, FuncDecl, StructDecl, VarDecl
from .bytecode import Tok, encode_script
from .crc import script_text_crc
from .env import InstallEnv
from .lower import (LowerError, build_scope, consts_of, enum_type_names, enums_of, local_funcs_of,
                    lower_function, members_of, _mem_size)
from .model import (ClassBody, CompiledPackage, ConstBody, Dependency, EnumBody, Export, FunctionBody,
                    Import, Name, PropertyBody, StructBody, TextBufferBody)
from .global_index import default_global_index, engine_name_pool, highlight_name_pool, pool_case
from .natives import ClassGraph, load_catalog, load_graph, prop_type_label
from .ordering import ObjInput, order_package
from .parser import parse
from ..upackage import read_compact_index as _rci
from ..uprops.base import PROPERTY_TYPES
from ..uprops.ufield import _decode_property, _field_next

# object flags per object kind
_RF_TEXTBUFFER = 0x00340000
_RF_FIELD = 0x00070004               # UProperty / Enum / Struct / struct-member / array-inner
_RF_CONST = 0x00070000               # UConst (no low 0x4 bit)
_RF_CLASS = 0x000F0004

_NAME_BASE = 0x00070010
_RF_NATIVE = 0x04000000              # engine boot global name pool (engine_name_pool)
_HIGHLIGHT = 0x00000400             # RF_HighlightName — keywords / intrinsic types (highlight_name_pool)

# ── ClassFlags (RE'd 2026-09-05; base = CLASS_Parsed|CLASS_Compiled) ──────────────────────────────
_CLASS_FLAGS_BASE = 0x00000012
# The subset a class inherits from its super's ClassFlags (RE'd 2026-09-05 against UT99: a Texture
# subclass carries Texture's CLASS_SafeReplace, a TcpLink subclass its CLASS_Transient). Matches UE1
# CLASS_Inherit: Config|Transient|Localized|SafeReplace|RuntimeStatic|PerObjectConfig (NOT Abstract).
_CLASS_INHERIT_MASK = 0x00000004 | 0x00000008 | 0x00000020 | 0x00000040 | 0x00000080 | 0x00000400
CLASS_TRANSIENT = 0x00000008         # a transient (or native) class doesn't auto-serialize its CDO
_CLASS_MODIFIER_FLAGS: dict[str, int] = {
    "abstract": 0x0001,              # CLASS_Abstract
    "native": 0x0000, "intrinsic": 0x0000,   # no persisted ClassFlags bit
    "transient": 0x0008,             # CLASS_Transient
    "safereplace": 0x0040,           # CLASS_SafeReplace
    "noexport": 0x0100,              # CLASS_NoExport (UCC also requires `native`)
    "perobjectconfig": 0x0400,       # CLASS_PerObjectConfig
    "nativereplication": 0x0800,     # CLASS_NativeReplication
}

# ── PropertyFlags / CPF_ (RE'd 2026-09-05) ────────────────────────────────────────────────────────
CPF_EDIT = 0x00000001
CPF_CONST = 0x00000002
CPF_INPUT = 0x00000004
CPF_EXPORTOBJECT = 0x00000008
CPF_TRANSIENT = 0x00002000
CPF_CONFIG = 0x00004000
CPF_LOCALIZED = 0x00008000
CPF_TRAVEL = 0x00010000
CPF_GLOBALCONFIG = 0x00040000
CPF_NEEDCTORLINK = 0x00400000        # StrProperty and ArrayProperty
_VAR_MODIFIER_FLAGS: dict[str, int] = {
    "const": CPF_CONST,
    "config": CPF_CONFIG,
    "globalconfig": CPF_GLOBALCONFIG | CPF_CONFIG,
    "localized": CPF_LOCALIZED,
    "transient": CPF_TRANSIENT,
    "travel": CPF_TRAVEL,
    "input": CPF_INPUT,
    "export": CPF_EXPORTOBJECT,
    "native": 0, "intrinsic": 0, "private": 0,   # accepted, no persisted CPF bit
}


# ── FunctionFlags / FUNC_ (RE'd 2026-09-05 from UCC compiles) ─────────────────────────────────────
FUNC_DEFINED = 0x00000002            # a function with a compiled body
FUNC_NATIVE = 0x00000400             # a body-less native function
_FUNC_MODIFIER_FLAGS: dict[str, int] = {
    "final": 0x00000001,             # FUNC_Final
    "singular": 0x00000020,          # FUNC_Singular
    "native": FUNC_NATIVE,           # FUNC_Native (also implied by a body-less function)
    "simulated": 0x00000100,         # FUNC_Simulated
    "static": 0x00002000,            # FUNC_Static
}
# CPF_ role flags on a function's child properties (RE'd 2026-09-05)
CPF_PARM = 0x00000080
CPF_OPTIONAL = 0x00000010
CPF_OUT = 0x00000100
CPF_COERCE = 0x00000800
CPF_RETURN_ROLE = 0x00000580         # ReturnValue = CPF_PARM|CPF_OUT(0x100)|CPF_RETURN(0x400)
_PARAM_MODIFIER_FLAGS: dict[str, int] = {
    "optional": CPF_OPTIONAL, "out": CPF_OUT, "coerce": CPF_COERCE,
}
EX_NATIVE_PARM = 0x29                # bytecode: push a native function's parameter


@dataclass(frozen=True, kw_only=True)
class _Kind:
    prop_class: str                  # the UProperty subclass (IntProperty, ObjectProperty, …)
    ptype: int                       # actor_write PT_* default-tag code
    base_flags: int = 0              # type-inherent PropertyFlags (StrProperty/ArrayProperty)


_SCALAR_KINDS: dict[str, _Kind] = {
    "int":    _Kind(prop_class="IntProperty",   ptype=PT_INT),
    "float":  _Kind(prop_class="FloatProperty", ptype=PT_FLOAT),
    "bool":   _Kind(prop_class="BoolProperty",  ptype=PT_BOOL),
    "byte":   _Kind(prop_class="ByteProperty",  ptype=PT_BYTE),
    "string": _Kind(prop_class="StrProperty",   ptype=PT_STR, base_flags=CPF_NEEDCTORLINK),
    "name":   _Kind(prop_class="NameProperty",  ptype=PT_NAME),
}
_SCALAR_ZERO = {PT_INT: 0, PT_FLOAT: 0.0, PT_BOOL: False, PT_BYTE: 0, PT_STR: "", PT_NAME: "None"}
_LITERAL_OPS = {"intconst", "floatconst", "boolconst", "byteconst", "stringconst", "nameconst"}


# ── resolved-field model ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, kw_only=True)
class _RefSpec:
    """One type-tail object ref, resolved late against the final tables: an import (`is_export=False`,
    `key` = import object name), an export (`is_export=True`, `key` = export key), or the literal
    None ref (`key = ""` → resolves to 0, used for a plain ByteProperty's trailing Enum slot)."""
    key: str
    is_export: bool


_NONE_REF = _RefSpec(key="", is_export=False)


@dataclass(frozen=True, kw_only=True)
class _Prop:
    """A UProperty export: a class member, a struct member, or an array inner."""
    key: str
    name: str
    prop_class: str
    outer_key: str                   # class key or struct key or array key
    array_dim: int
    property_flags: int
    category_name: str | None        # editor category (None → cat index 0)
    type_tail: tuple[_RefSpec, ...]
    in_class_chain: bool             # participates in the class Children chain (class members only)
    object_flags: int = _RF_FIELD    # export RF_* flags (private clears RF_Public → 0x00070000)
    is_var: bool = True


@dataclass(frozen=True, kw_only=True)
class _EnumDef:
    key: str
    name: str
    values: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class _ConstDef:
    key: str
    name: str
    value: str


@dataclass(frozen=True, kw_only=True)
class _StructDef:
    key: str
    name: str
    member_keys: tuple[str, ...]     # struct member _Prop keys, in declaration order


@dataclass(frozen=True, kw_only=True)
class _Func:
    """A UFunction export: a class member function plus everything to emit its body."""
    key: str
    name: str
    class_key: str                   # the owning class's export key (own-member/func scoping)
    line: int
    text_pos: int
    function_flags: int
    child_keys: tuple[str, ...]      # param/return/local _Prop keys, in Children order
    local_by_name: dict[str, str]    # casefold local/param/return name -> its child _Prop key
    toks: tuple                      # lowered token stream (list[Tok])
    script_size: int                 # in-memory ScriptSize (sum of _mem_size)
    super_ref_key: str | None = None  # import key of an overridden inherited function (else 0)


@dataclass(kw_only=True)
class _Build:
    """Accumulator threaded through field construction. For a single class `prefix` is "" and object
    keys are unprefixed (the original scheme); the multi-class path (`compile_package_dir`) sets
    `prefix = f"{class_name}::"` per class so keys never collide across classes in the shared tables,
    while `props`/`enums`/`consts`/`structs`/`funcs`/`imports` accumulate package-wide."""
    class_name: str
    env: InstallEnv
    prefix: str = ""
    props: dict[str, _Prop] = field(default_factory=dict)
    enums: dict[str, _EnumDef] = field(default_factory=dict)
    consts: dict[str, _ConstDef] = field(default_factory=dict)
    structs: dict[str, _StructDef] = field(default_factory=dict)
    funcs: dict[str, _Func] = field(default_factory=dict)
    chain_fields: list[tuple[str, bool]] = field(default_factory=list)  # (key, is_var) in decl order
    default_props: list[Prop] = field(default_factory=list)
    member_class_flags: int = 0      # ClassFlags contributed by member vars (config/localized)
    class_object_flags: int = _RF_CLASS  # the UClass export's ObjectFlags (+RF_Native for native)
    emit_zero_defaults: bool = True  # non-native: emit a type-zero tag for every own property.
                                     # native: emit only explicitly-set defaults (C++ builds the CDO).
    imports: dict[str, _ImportSpec] = field(default_factory=dict)
    local_enums: set[str] = field(default_factory=set)
    local_structs: set[str] = field(default_factory=set)
    in_pkg_class_names: dict[str, str] = field(default_factory=dict)  # casefold -> declared class name
    graph_override: object | None = None      # multi-class: a ClassGraph seeing in-package classes
    catalog_override: object | None = None
    class_ref_packages: list[str] = field(default_factory=list)  # non-Core pkgs this class imports

    def okey(self, local: str) -> str:
        """A package-unique object key: `prefix` + the class-local key (identity when prefix is "")."""
        return self.prefix + local


class _NameIndex(dict):
    """name -> name-table index, resolved case-insensitively. UE1 `FName` is case-insensitive, and the
    table spells a name from the global pool, not the source (a member `a` -> `A`, a const `K` -> `k`
    when the pool already holds that FName). Callers hold names in source case, so any-case lookup must
    hit the single pooled entry. Built from casefolded keys; a mixed-case lookup falls to casefold."""

    def __missing__(self, key: str) -> int:
        return self[key.casefold()]


def compile_package(src: str, env: InstallEnv, *,
                    order_override: tuple[list[str], list[str], list[str]] | None = None
                    ) -> CompiledPackage:
    """Compile UnrealScript `src` to a linked `CompiledPackage`, byte-exact vs UCC. `env` resolves the
    super's home package + CRC. Ordering is autonomous: a provisional compile is decoded and re-emitted
    in UCC's real name/import/export order (`reorder.true_order` — the runtime-dumped global index +
    faithful qsort). `order_override=(names, imports, export_rows)` forces a specific order (used by
    tests to pin bodies against a golden); otherwise it is derived."""
    if order_override is None:
        from .reorder import true_order
        from .serialize import serialize as _serialize
        return _compile_single(src, env, true_order(_serialize(_compile_single(src, env, None))))
    return _compile_single(src, env, order_override)


def _compile_single(src: str, env: InstallEnv,
                    order_override: tuple[list[str], list[str], list[str]] | None
                    ) -> CompiledPackage:
    decl = parse(src)
    _reject_unsupported(decl)
    class_name = decl.name
    super_name = decl.super_name
    super_info = env.resolve_class(super_name)
    if super_info is None:
        raise NotImplementedError(f"cannot resolve super class {super_name!r} on the search path")
    if super_info.package.casefold() != "core":
        raise NotImplementedError(f"super {super_name!r} outside Core (package "
                                  f"{super_info.package!r}) — deeper rung")

    crlf_source = _to_crlf(_script_text(decl.source or src))
    class_flags, config_name, within_key = _class_header(decl, env)
    class_flags |= super_info.class_flags & _CLASS_INHERIT_MASK

    b = _Build(class_name=class_name, env=env, class_object_flags=_class_object_flags(decl),
               emit_zero_defaults=_auto_emit_defaults(decl, class_flags))
    b.local_enums = {m.name for m in decl.members if isinstance(m, EnumDecl)}
    b.local_structs = {m.name for m in decl.members if isinstance(m, StructDecl)}
    _seed_imports(b, super_name, within_key)
    _build_members(b, decl)
    if decl.functions:
        _build_functions(b, decl, super_name, crlf_source)

    has_new_kind = bool(b.enums or b.consts or b.structs or b.funcs) or any(
        not (p.in_class_chain and p.prop_class in {k.prop_class for k in _SCALAR_KINDS.values()}
             and p.array_dim == 1) for p in b.props.values())

    default_names = {p.name for p in b.default_props} | {
        p.value for p in b.default_props if p.ptype == PT_NAME and isinstance(p.value, str)}
    names_order, imports_order, export_rows = _orders(b, class_name, super_name, config_name, decl,
                                                      default_names, has_new_kind, order_override)
    names_order = [pool_case(n) for n in names_order]     # canonical FName spelling from the pool
    if order_override is not None:                          # override imports are DISPLAY names
        imports_order = _imports_by_display(b, imports_order)

    name_cf = {n.casefold(): i for i, n in enumerate(names_order)}
    name_index = _NameIndex(name_cf)

    def nidx(name: str) -> int:
        return name_index[name]

    imp_ref = {n: -(i + 1) for i, n in enumerate(imports_order)}
    exp_ref = _export_refs(b, class_name, export_rows)

    def ref(spec: _RefSpec) -> int:
        if spec.key == "":
            return 0
        return exp_ref[spec.key] if spec.is_export else imp_ref[spec.key]

    class_flags |= b.member_class_flags
    chain = _class_chain(b)
    chain_next = _next_map(chain, exp_ref)

    names = tuple(Name(text=n, flags=_name_flags(n)) for n in names_order)
    import_recs = tuple(_import_rec(b.imports[n], name_index, imp_ref) for n in imports_order)

    exports = _build_exports(b, class_name, super_name, super_info.self_crc, crlf_source,
                             class_flags, config_name, within_key, chain, chain_next,
                             name_index, nidx, name_cf, exp_ref, imp_ref, ref, export_rows)
    return CompiledPackage(version=69, licensee=0, package_flags=1,
                           names=names, imports=import_recs, exports=exports)


# ── scope gate ────────────────────────────────────────────────────────────────────────────────────
_CONV_IMPORT_RE = re.compile(r'^\s*CONVERSATION\s+IMPORT\s+FILE\s*=\s*"([^"]+)"\s*$', re.IGNORECASE)


def conversation_import_files(decl: ClassDecl) -> list[str]:
    """The `.con` filenames a class's `#exec CONVERSATION IMPORT FILE="X"` directives name, in order.
    These emit SIBLING packages (`conimport.py`); the class package itself is unchanged."""
    out: list[str] = []
    for directive in decl.exec_directives:
        m = _CONV_IMPORT_RE.match(directive)
        if m is not None:
            out.append(m.group(1))
    return out


def _reject_unsupported(decl: ClassDecl) -> None:
    if decl.super_name is None:
        raise NotImplementedError(f"base class {decl.name!r} has no super — later rung")
    # `#exec CONVERSATION IMPORT` is supported (it emits sibling packages, `conimport.py`, and adds
    # nothing to this package); any OTHER `#exec` is not.
    other_exec = [d for d in decl.exec_directives if _CONV_IMPORT_RE.match(d) is None]
    for feature, present in (("states", decl.states), ("replication", decl.replication),
                             ("#exec directives", other_exec),
                             ("cpptext", decl.cpptext)):
        if present:
            raise NotImplementedError(f"{feature} not supported yet (class {decl.name!r})")


# ── class header ────────────────────────────────────────────────────────────────────────────────
def _class_header(decl: ClassDecl, env: InstallEnv) -> tuple[int, str, str]:
    """Returns (ClassFlags, ClassConfigName, ClassWithin import-object-name). Default within=Object,
    config=System."""
    flags = _CLASS_FLAGS_BASE
    config_name = "System"
    within_key = "Object"
    for mod in decl.modifiers:
        head, _, arg = mod.partition("(")
        arg = arg[:-1] if arg.endswith(")") else arg
        if head == "config":
            config_name = arg or "System"
        elif head in _CLASS_MODIFIER_FLAGS:
            flags |= _CLASS_MODIFIER_FLAGS[head]
        else:
            raise NotImplementedError(f"class modifier {head!r} not supported (class {decl.name!r})")
    if decl.within is not None:
        within_key = decl.within
    return flags, config_name, within_key


def _is_native_class(decl: ClassDecl) -> bool:
    return "native" in decl.modifiers or "intrinsic" in decl.modifiers


def _class_object_flags(decl: ClassDecl) -> int:
    """The UClass export's ObjectFlags: base `_RF_CLASS`, plus RF_Native for a native class."""
    return _RF_CLASS | (_RF_NATIVE if _is_native_class(decl) else 0)


def _auto_emit_defaults(decl: ClassDecl, class_flags: int) -> bool:
    """Whether the class default block auto-materialises a tag for every own property (RE'd 2026-09-05
    against UT99). A NATIVE or TRANSIENT class serialises only the defaults explicitly written in its
    `defaultproperties` (its CDO is built in C++ / never saved); every other class also emits a
    type-zero tag for each own property it does not set."""
    return not (_is_native_class(decl) or bool(class_flags & CLASS_TRANSIENT))


# ── members ─────────────────────────────────────────────────────────────────────────────────────
def _build_members(b: _Build, decl: ClassDecl) -> None:
    default_values, inherited = _default_value_map(decl)
    for m in decl.members:
        match m:
            case VarDecl():
                _build_var(b, m, default_values)
            case EnumDecl():
                _build_enum(b, m)
            case ConstDecl():
                _build_const(b, m, decl.source or "")
            case StructDecl():
                _build_struct(b, m)
            case _:
                raise NotImplementedError(f"member {type(m).__name__} not supported yet")
    _emit_inherited_defaults(b, decl, inherited)


def _build_enum(b: _Build, m: EnumDecl) -> None:
    key = b.okey(f"enum:{m.name}")
    b.enums[key] = _EnumDef(key=key, name=m.name, values=m.values)
    b.chain_fields.append((key, False))
    _add_import(b, "Enum")


def _build_const(b: _Build, m: ConstDecl, source: str) -> None:
    key = b.okey(f"const:{m.name}")
    b.consts[key] = _ConstDef(key=key, name=m.name, value=_const_value_text(m.name, source))
    b.chain_fields.append((key, False))
    _add_import(b, "Const")


def _build_struct(b: _Build, m: StructDecl) -> None:
    if m.base is not None:
        raise NotImplementedError(f"struct {m.name!r} extends {m.base!r} not supported yet")
    key = b.okey(f"struct:{m.name}")
    member_keys: list[str] = []
    for var in m.members:
        if var.type.base.casefold() == "array" or var.type.inner is not None:
            raise NotImplementedError(f"struct {m.name!r} member {var.names[0]!r}: dynamic-array member "
                                      "not supported yet")
        prop_class, base_flags, tail, _ptype, _sname = _resolve_var_type(b, var, var.names[0])
        array_dim = _static_dim(var)
        for pname in var.names:
            pkey = b.okey(f"smember:{m.name}.{pname}")
            b.props[pkey] = _Prop(key=pkey, name=pname, prop_class=prop_class, outer_key=key,
                                  array_dim=array_dim, property_flags=base_flags, category_name=None,
                                  type_tail=tail, in_class_chain=False)
            _add_import(b, prop_class)
            member_keys.append(pkey)
    b.structs[key] = _StructDef(key=key, name=m.name, member_keys=tuple(member_keys))
    b.chain_fields.append((key, False))
    _add_import(b, "Struct")


# ── functions ─────────────────────────────────────────────────────────────────────────────────────
def _build_functions(b: _Build, decl: ClassDecl, super_name: str, crlf_source: str) -> None:
    search_dir = b.env._search_dirs[0]
    graph = b.graph_override if b.graph_override is not None else load_graph(search_dir)
    catalog = b.catalog_override if b.catalog_override is not None else load_catalog(search_dir)
    enames = enum_type_names(decl.members)
    members = members_of(decl.members, graph)
    lfuncs = local_funcs_of(decl.functions, graph, enames)
    enums = enums_of(decl.members)
    consts = consts_of(decl.members)
    _add_import(b, "Function")
    for func, (line, text_pos) in zip(decl.functions, _function_positions(crlf_source, decl.functions)):
        _build_one_function(b, decl, func, super_name, graph, catalog, members, lfuncs, line, text_pos,
                            enames, enums, consts)


def _build_one_function(b: _Build, decl: ClassDecl, func: FuncDecl, super_name: str, graph, catalog,
                        members, lfuncs, line: int, text_pos: int, enames, enums, consts) -> None:
    if func.kind not in ("function", "event"):
        raise NotImplementedError(f"function kind {func.kind!r} not supported yet ({func.name!r})")
    fkey = b.okey(f"fn:{func.name}")
    flags = _func_flags(func) | (FUNC_DEFINED if func.has_body else 0)  # native flag via modifier

    child_keys: list[str] = []
    local_by_name: dict[str, str] = {}
    for p in func.params:
        pkey = _add_func_prop(b, fkey, func.name, p.name, p.type, CPF_PARM | _param_flags(func, p))
        child_keys.append(pkey); local_by_name[p.name.casefold()] = pkey
    if func.return_type is not None:
        rkey = _add_func_prop(b, fkey, func.name, "ReturnValue", func.return_type, CPF_RETURN_ROLE)
        child_keys.append(rkey); local_by_name["returnvalue"] = rkey
    for vd in func.locals:
        for n in vd.names:
            lkey = _add_func_prop(b, fkey, func.name, n, vd.type, 0)
            child_keys.append(lkey); local_by_name[n.casefold()] = lkey

    if func.has_body:
        scope = build_scope(func, members=members, funcs=lfuncs, class_name=decl.name,
                            super_name=super_name, graph=graph,
                            enums=enums, enum_names=enames, consts=consts)
        try:
            toks = lower_function(func, scope, catalog)
        except LowerError as e:
            raise NotImplementedError(f"cannot lower function {func.name!r}: {e}") from e
    elif flags & FUNC_NATIVE:                        # native thunk: one NativeParm per param
        toks = [Tok(EX_NATIVE_PARM, (("obj", p.name),)) for p in func.params]
    else:                                            # abstract declaration (`function Foo();`)
        toks = []

    _register_struct_member_imports(b, toks, _struct_var_map(b, fkey), _member_graph(b))

    b.funcs[fkey] = _Func(key=fkey, name=func.name, class_key=b.okey(f"class:{decl.name}"),
                          line=line, text_pos=text_pos,
                          function_flags=flags, child_keys=tuple(child_keys),
                          local_by_name=local_by_name, toks=tuple(toks),
                          script_size=sum(_mem_size(t) for t in toks),
                          super_ref_key=_super_func_import(b, super_name, func.name, graph))
    b.chain_fields.append((fkey, False))


def _super_func_import(b: _Build, super_name: str, func_name: str, graph) -> str | None:
    """If this function overrides one inherited from the super chain, register an import of the parent
    UFunction (Class=Function, Outer=its declaring class) and return its import key — the overriding
    function's `SuperField`. Otherwise None (SuperField 0)."""
    fb = graph.function(super_name, func_name) if graph is not None else None
    if fb is None:
        return None
    _add_import(b, fb.class_name)                         # ensure the declaring class is imported
    key = f"func:{fb.class_name}.{fb.name}"
    b.imports.setdefault(key, _ImportSpec(class_package="Core", class_name="Function",
                                          outer=fb.class_name, object_name=fb.name))
    return key


def _func_flags(func: FuncDecl) -> int:
    flags = 0x00000800 if func.kind == "event" else 0        # FUNC_Event
    for mod in func.modifiers:
        if mod not in _FUNC_MODIFIER_FLAGS:
            raise NotImplementedError(f"function modifier {mod!r} not supported yet ({func.name!r})")
        flags |= _FUNC_MODIFIER_FLAGS[mod]
    return flags


def _param_flags(func: FuncDecl, p) -> int:
    flags = 0
    for mod in p.modifiers:
        if mod not in _PARAM_MODIFIER_FLAGS:
            raise NotImplementedError(f"param modifier {mod!r} on {func.name}.{p.name} not supported "
                                      "yet")
        flags |= _PARAM_MODIFIER_FLAGS[mod]
    return flags


def _add_func_prop(b: _Build, fkey: str, func_name: str, pname: str, type_ref, role_flags: int) -> str:
    """One param/return/local UProperty of a function (Outer = the function). `role_flags` is the
    CPF role: CPF_PARM for a param, CPF_RETURN_ROLE for ReturnValue, 0 for a local."""
    prop_class, base_flags, tail = _func_prop_type(b, type_ref, func_name, pname)
    key = b.okey(f"fprop:{func_name}.{pname}")
    b.props[key] = _Prop(key=key, name=pname, prop_class=prop_class, outer_key=fkey, array_dim=1,
                         property_flags=role_flags | base_flags, category_name=None,
                         type_tail=tail, in_class_chain=False)
    _add_import(b, prop_class)
    return key


def _func_prop_type(b: _Build, tr, func_name: str, pname: str) -> tuple[str, int, tuple[_RefSpec, ...]]:
    base = tr.base
    if tr.inner is not None or base.casefold() == "array":
        raise NotImplementedError(f"array param/local {func_name}.{pname} not supported yet")
    if base.casefold() in _SCALAR_KINDS:                 # primitive type keywords are case-insensitive
        k = _SCALAR_KINDS[base.casefold()]
        return k.prop_class, k.base_flags, ((_NONE_REF,) if base.casefold() == "byte" else ())
    if base in b.local_enums:
        return "ByteProperty", 0, (_RefSpec(key=b.okey(f"enum:{base}"), is_export=True),)
    if base in b.local_structs:
        return "StructProperty", 0, (_RefSpec(key=b.okey(f"struct:{base}"), is_export=True),)
    if base.casefold() == "class":
        meta = tr.meta_class or "Object"
        _add_import(b, "Class")
        meta_key = _add_import(b, meta)
        return "ClassProperty", 0, (_RefSpec(key="Class", is_export=False),
                                    _RefSpec(key=meta_key, is_export=False))
    graph = _member_graph(b)                              # a built-in/cross-package struct (Vector, …)
    if graph.is_struct_name(base):
        skey = _add_struct_import(b, graph, base)
        return "StructProperty", 0, (_RefSpec(key=skey, is_export=False),)
    if b.env.resolve_class(base) is None:
        raise NotImplementedError(f"param/local type {base!r} ({func_name}.{pname}) not supported yet")
    obj_key = _add_import(b, base)
    return "ObjectProperty", 0, (_RefSpec(key=obj_key, is_export=False),)


_FUNC_KW = r"\b(?:function|event|operator|preoperator|postoperator|delegate)\b"


def _function_positions(crlf: str, funcs) -> list[tuple[int, int]]:
    """(Line, TextPos) for each function, in `funcs` order. For a function WITH a body both point at
    its first EXECUTABLE statement — right after the body `{`, skipping whitespace, comments, AND
    leading `local` declarations. For a body-less (native) function they point at the `;` terminating
    its declaration. Line = 1-based source line, TextPos = byte offset into the CRLF ScriptText (RE'd
    2026-09-05 against UCC; verified byte-exact for every UscW/UscFn/FrameBuilder function and UWeb's
    native functions). The declaration is anchored on the `function`/`event`/… keyword (a bare
    name-`(` substring also matches a CALL to the function, and body-less functions have no `{`)."""
    out: list[tuple[int, int]] = []
    cur = 0
    ws = " \t\r\n"
    for f in funcs:
        namepat = (r"\b" + re.escape(f.name) + r"\b") if (f.name[:1].isalnum() or f.name[:1] == "_") \
            else re.escape(f.name)
        m = re.compile(_FUNC_KW + r"[^{};]*?" + namepat + r"\s*\(", re.IGNORECASE).search(crlf, cur)
        if m is None:
            raise NotImplementedError(f"could not locate declaration of function {f.name!r} in source "
                                      "for TextPos")
        j = m.end() - 1                                 # the matched param-list open paren
        depth = 0
        while True:                                     # matching close of the parameter list
            c = crlf[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if not f.has_body:                              # native/declared: TextPos = the ';'
            k = crlf.index(";", j)
            out.append((crlf.count("\n", 0, k) + 1, k))
            cur = k + 1
            continue
        k = crlf.index("{", j) + 1
        while True:                                     # skip to the first executable statement
            while k < len(crlf) and crlf[k] in ws:
                k += 1
            if crlf[k:k + 2] == "//":                    # line comment
                nl = crlf.find("\n", k)
                k = len(crlf) if nl < 0 else nl + 1
                continue
            if crlf[k:k + 2] == "/*":                    # block comment
                end = crlf.find("*/", k)
                k = len(crlf) if end < 0 else end + 2
                continue
            if crlf[k:k + 5].casefold() == "local" and (
                    k + 5 >= len(crlf) or not (crlf[k + 5].isalnum() or crlf[k + 5] == "_")):
                k = crlf.index(";", k) + 1
                continue
            break
        out.append((crlf.count("\n", 0, k) + 1, k))
        cur = k
    return out


def _build_var(b: _Build, m: VarDecl, default_values: dict) -> None:
    flags = 0
    category_name: str | None = None
    if m.category is not None:                        # var() or var(Cat) → editable
        flags |= CPF_EDIT
        category_name = m.category if m.category else b.class_name
    for mod in m.modifiers:
        if mod not in _VAR_MODIFIER_FLAGS:
            raise NotImplementedError(f"var modifier {mod!r} not supported (var {m.names[0]!r})")
        flags |= _VAR_MODIFIER_FLAGS[mod]
    obj_flags = _RF_FIELD & ~0x04 if "private" in m.modifiers else _RF_FIELD  # private clears RF_Public
    if flags & CPF_CONFIG:                            # a config/globalconfig member → CLASS_Config
        b.member_class_flags |= 0x04
    if flags & CPF_LOCALIZED:                         # a localized member → CLASS_Localized
        b.member_class_flags |= 0x20
    skip_default = bool(flags & CPF_TRANSIENT)        # transient values aren't default-serialised

    for pname in m.names:
        prop_class, base_flags, tail, ptype, struct_name = _resolve_var_type(b, m, pname)
        array_dim = _static_dim(m)
        key = b.okey(f"cprop:{pname}")
        b.props[key] = _Prop(key=key, name=pname, prop_class=prop_class,
                             outer_key=b.okey(f"class:{b.class_name}"), array_dim=array_dim,
                             property_flags=flags | base_flags, category_name=category_name,
                             type_tail=tail, in_class_chain=True, object_flags=obj_flags)
        _add_import(b, prop_class)
        b.chain_fields.append((key, True))
        if not skip_default:
            _emit_default(b, pname, ptype, array_dim, struct_name, default_values)


def _resolve_var_type(b: _Build, m: VarDecl, pname: str
                      ) -> tuple[str, int, tuple[_RefSpec, ...], int, str | None]:
    """(prop_class, base_flags, type_tail, default-tag ptype, struct_name-for-default)."""
    base = m.type.base
    if base.casefold() in _SCALAR_KINDS:                 # primitive type keywords are case-insensitive
        k = _SCALAR_KINDS[base.casefold()]
        tail = (_NONE_REF,) if base.casefold() == "byte" else ()  # ByteProperty always trails a ci(Enum)
        return k.prop_class, k.base_flags, tail, k.ptype, None
    if base in b.local_enums:
        return ("ByteProperty", 0, (_RefSpec(key=b.okey(f"enum:{base}"), is_export=True),),
                PT_BYTE, None)
    if base in b.local_structs:
        return ("StructProperty", 0, (_RefSpec(key=b.okey(f"struct:{base}"), is_export=True),),
                PT_STRUCT, base)
    if base.casefold() == "class":
        meta = m.type.meta_class or "Object"
        _add_import(b, "Class")
        meta_key = _add_import(b, meta)
        return ("ClassProperty", 0, (_RefSpec(key="Class", is_export=False),
                                     _RefSpec(key=meta_key, is_export=False)), PT_OBJECT, None)
    if base.casefold() == "array":
        return _resolve_array_type(b, m, pname)
    # otherwise an object type: a class reference resolved via env.
    info = b.env.resolve_class(base)
    if info is None:
        raise NotImplementedError(f"var {pname!r}: unknown type {base!r} (not scalar/local/class)")
    obj_key = _add_import(b, base)
    return ("ObjectProperty", 0, (_RefSpec(key=obj_key, is_export=False),), PT_OBJECT, None)


def _resolve_array_type(b: _Build, m: VarDecl, pname: str
                        ) -> tuple[str, int, tuple[_RefSpec, ...], int, str | None]:
    inner = m.type.inner
    if inner is None:
        raise NotImplementedError(f"var {pname!r}: array without element type")
    array_key = b.okey(f"cprop:{pname}")
    inner_key = b.okey(f"inner:{pname}")
    base = inner.base
    if base.casefold() in _SCALAR_KINDS:                 # primitive keywords are case-insensitive
        k = _SCALAR_KINDS[base.casefold()]
        inner_class = k.prop_class
        inner_tail = (_NONE_REF,) if base.casefold() == "byte" else ()
    elif base in b.local_enums:
        inner_class = "ByteProperty"
        inner_tail = (_RefSpec(key=b.okey(f"enum:{base}"), is_export=True),)
    elif base in b.local_structs:
        inner_class = "StructProperty"
        inner_tail = (_RefSpec(key=b.okey(f"struct:{base}"), is_export=True),)
    elif _member_graph(b).is_struct_name(base):          # built-in/cross-package struct (Vector, …)
        inner_class = "StructProperty"
        inner_tail = (_RefSpec(key=_add_struct_import(b, _member_graph(b), base), is_export=False),)
    elif b.env.resolve_class(base) is not None:
        inner_class = "ObjectProperty"
        inner_tail = (_RefSpec(key=_add_import(b, base), is_export=False),)
    else:
        raise NotImplementedError(f"var {pname!r}: array<{base}> element not supported yet")
    b.props[inner_key] = _Prop(key=inner_key, name=pname, prop_class=inner_class,
                              outer_key=array_key, array_dim=1, property_flags=0,
                              category_name=None, type_tail=inner_tail, in_class_chain=False)
    _add_import(b, inner_class)
    return ("ArrayProperty", CPF_NEEDCTORLINK,
            (_RefSpec(key=inner_key, is_export=True),), PT_ARRAY, None)


def _static_dim(m: VarDecl) -> int:
    if m.array_dim is None:
        return 1
    if isinstance(m.array_dim, int):
        return m.array_dim
    raise NotImplementedError(f"const-named static array size {m.array_dim!r} not supported yet")


# ── defaults ──────────────────────────────────────────────────────────────────────────────────────
def _default_value_map(decl: ClassDecl):
    """Split the `defaultproperties` entries into overrides of the class's OWN members (returned as a
    `{(name, array_index): value}` map for `_emit_default`) and overrides of INHERITED members
    (returned as a list, emitted after own tags by `_emit_inherited_defaults`)."""
    declared = {name for m in decl.members if isinstance(m, VarDecl) for name in m.names}
    own: dict[tuple[str, int | None], object] = {}
    inherited = []
    for d in decl.default_props:
        if d.name in declared:
            own[(d.name, d.array_index)] = d.value
        else:
            inherited.append(d)
    return own, inherited


def _emit_inherited_defaults(b: _Build, decl: ClassDecl, entries: list) -> None:
    """Emit a class-default tag for each `defaultproperties` entry naming an INHERITED member. The
    UClass default block is a diff vs the super CDO, so an inherited member appears only when the
    class changes it — i.e. exactly the entries the author wrote. Tags follow the class's own-member
    tags, in the super's field-iteration order (most-derived ancestor first, Children order within).
    The member's type is resolved by walking the super chain across packages."""
    if not entries:
        return
    graph = _defaults_graph(b, decl.super_name)
    order = _super_field_order(graph, decl.super_name)
    label_by = {cf: label for cf, label in order}
    pos_by = {cf: i for i, (cf, _label) in enumerate(order)}
    resolved = []
    for d in entries:
        cf = d.name.casefold()
        label = label_by.get(cf)
        if label is None:
            raise NotImplementedError(f"inherited default {d.name!r}: not a member of super chain "
                                      f"of {decl.super_name!r}")
        if label == "class" or label.startswith("object:"):
            ptype = PT_OBJECT                            # a class/object ref, resolved at write time
            value = _object_default_ref(b, d.name, d.value)
        elif label not in _SCALAR_KINDS:
            raise NotImplementedError(f"inherited default {d.name!r}: non-scalar type {label!r} "
                                      "not supported yet")
        else:
            ptype = _SCALAR_KINDS[label].ptype
            if ptype == PT_BYTE and d.value is not None and d.value.op == "name":
                value = _byte_enum_ordinal(b, d.name, d.value, graph)  # inherited enum tag → ordinal
            else:
                value = _scalar_default(d.name, ptype, d.value)
        resolved.append((pos_by[cf], d.array_index if d.array_index is not None else -1,
                         d.name, ptype, value, d.array_index))
    resolved.sort(key=lambda t: (t[0], t[1]))
    for _pos, _ai, name, ptype, value, arr in resolved:
        b.default_props.append(Prop(name, ptype, value, array_index=arr))


def _defaults_graph(b: _Build, super_name: str) -> ClassGraph:
    """A `ClassGraph` that can resolve `super_name`'s inherited members. The multi-class path already
    has one (`graph_override`, seeing Editor + in-package classes); the single-class path builds one
    over Core/Engine plus the super's home package."""
    if b.graph_override is not None:
        return b.graph_override
    search_dir = b.env._search_dirs[0]
    pkgs = ["core.u", "Engine.u"]
    info = b.env.resolve_class(super_name)
    if info is not None and info.package.casefold() not in ("core", "engine"):
        pkgs.append(f"{info.package}.u")
    return load_graph(search_dir, packages=tuple(pkgs))


def _own_props_in_order(pkg, idx1: int) -> list[tuple[str, str]]:
    """One class's OWN properties (casefolded name, type label) in `Children` chain order."""
    e = pkg.exports[idx1 - 1]
    buf, p = pkg.buf, e["soff"]
    for _ in range(3):                                   # Super, Next, ScriptText
        _, p = _rci(buf, p)
    children, _ = _rci(buf, p)
    out: list[tuple[str, str]] = []
    cur = children
    for _ in range(4096):
        if cur <= 0:
            break
        ee = pkg.exports[cur - 1]
        if pkg.name_of_ref(ee["cls"]) in PROPERTY_TYPES:
            out.append((pkg.names[ee["nm"]].casefold(), prop_type_label(_decode_property(pkg, cur, ""))))
        cur = _field_next(pkg, cur)
    return out


def _super_field_order(graph: ClassGraph, super_name: str) -> list[tuple[str, str]]:
    """Inherited fields in class field-iteration order — the super's own properties first (Children
    order), then its ancestors', up the chain."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    name: str | None = super_name
    for _ in range(64):
        if name is None:
            break
        loc = graph._locate(name)
        if loc is None:
            break
        pkg, idx1 = loc
        for cf, label in _own_props_in_order(pkg, idx1):
            if cf not in seen:
                seen.add(cf)
                out.append((cf, label))
        e = pkg.exports[idx1 - 1]
        name = pkg.name_of_ref(e["sup"]) if e["sup"] != 0 else None
    return out


def _emit_default(b: _Build, pname: str, ptype: int, array_dim: int, struct_name: str | None,
                  values: dict) -> None:
    """Append the class-default tag(s) for one member var. A non-native class materialises every
    declared member (UCC emits a tag even for the type-zero; a static array emits all N elements); a
    native class emits only members explicitly set in `defaultproperties` (its CDO is built in C++)."""
    if not b.emit_zero_defaults and not any(name == pname for name, _ai in values):
        return
    if ptype == PT_STRUCT:
        if (pname, None) in values or (pname, 0) in values:
            raise NotImplementedError(f"explicit struct default for {pname!r} not supported yet")
        b.default_props.append(Prop(pname, PT_STRUCT, _zero_struct(b, struct_name)))
        return
    if ptype == PT_ARRAY:
        if (pname, None) in values:
            raise NotImplementedError(f"explicit array default for {pname!r} not supported yet")
        b.default_props.append(Prop(pname, PT_ARRAY, ArrayValue([])))
        return
    if ptype == PT_OBJECT:
        if (pname, None) in values:
            raise NotImplementedError(f"explicit object default for {pname!r} not supported yet")
        b.default_props.append(Prop(pname, PT_OBJECT, 0))
        return
    for idx in range(array_dim):
        arr_idx = None if array_dim == 1 else idx
        expr = values.get((pname, idx)) or (values.get((pname, None)) if array_dim == 1 else None)
        if expr is None and not b.emit_zero_defaults:
            continue                                     # explicit-only class: skip an unset element
        if ptype == PT_BYTE and expr is not None and expr.op == "name":
            value = _byte_enum_ordinal(b, pname, expr)   # an enum-constant default → its ordinal byte
        else:
            value = _scalar_default(pname, ptype, expr)
        b.default_props.append(Prop(pname, ptype, value, array_index=arr_idx))


def _object_default_ref(b: _Build, pname: str, expr) -> object:
    """A class/object-reference default (e.g. `AcceptClass=Class'UWeb.WebConnection'`) → a deferred
    `_RefSpec` (resolved to a table index at write time) or 0 for `None`. Only class-literal targets
    are resolved: an in-package class becomes an export ref, any other an import ref."""
    if expr is None or expr.op == "noneconst":
        return 0
    if expr.op != "objref":
        raise NotImplementedError(f"object default for {pname!r}: unsupported value op {expr.op!r}")
    target = str(expr.value).rsplit(".", 1)[-1]          # `UWeb.WebConnection` -> `WebConnection`
    cf = target.casefold()
    if cf in b.in_pkg_class_names:
        name = b.in_pkg_class_names[cf]
        return _RefSpec(key=f"{name}::class:{name}", is_export=True)
    return _RefSpec(key=_add_import(b, target), is_export=False)


def _byte_enum_ordinal(b: _Build, pname: str, expr, graph=None) -> int:
    """Resolve an enum-constant default (e.g. `StellateType=DB_NoStellate`, `RemoteRole=ROLE_None`) to
    its ordinal byte — first among the class's own enums, then any inherited enum via `graph` (or
    `graph_override`)."""
    tag = expr.text or (expr.value if isinstance(expr.value, str) else "")
    cf = tag.casefold()
    for e in b.enums.values():
        for i, v in enumerate(e.values):
            if v.casefold() == cf:
                return i
    g = graph if graph is not None else b.graph_override
    if g is not None:
        ordinal = g.enum_ordinal(tag)
        if ordinal is not None:
            return ordinal
    raise NotImplementedError(f"enum-constant default {tag!r} for {pname!r} unresolved")


def _zero_struct(b: _Build, struct_name: str | None) -> StructValue:
    sdef = b.structs.get(b.okey(f"struct:{struct_name}"))
    if sdef is None:
        raise NotImplementedError(f"zero default for non-local struct {struct_name!r} not supported")
    members = [Prop(b.props[mk].name, _mem_ptype(b.props[mk].prop_class), _mem_zero(b.props[mk]))
               for mk in sdef.member_keys]
    return StructValue(struct_name, members)


_PROPCLASS_PTYPE = {"IntProperty": PT_INT, "FloatProperty": PT_FLOAT, "BoolProperty": PT_BOOL,
                    "ByteProperty": PT_BYTE, "StrProperty": PT_STR, "NameProperty": PT_NAME}


def _mem_ptype(prop_class: str) -> int:
    return _PROPCLASS_PTYPE[prop_class]


def _mem_zero(p: _Prop) -> object:
    return _SCALAR_ZERO[_mem_ptype(p.prop_class)]


def _scalar_default(pname: str, ptype: int, expr) -> object:
    if expr is None:
        return _SCALAR_ZERO[ptype]
    if ptype == PT_NAME:
        if expr.op == "stringconst":                     # a name default may be written quoted
            return expr.value
        if expr.op not in ("name", "nameconst"):
            raise NotImplementedError(f"non-name default for name var {pname!r} (op {expr.op!r})")
        return expr.text if expr.value is None else expr.value
    if expr.op not in _LITERAL_OPS:
        raise NotImplementedError(f"non-literal default for {pname!r} (op {expr.op!r})")
    return expr.value


def _const_value_text(name: str, source: str) -> str:
    """UCC stores a UConst's Value as the verbatim source between `=` and `;`, trailing-trimmed."""
    m = re.search(r"\bconst\s+" + re.escape(name) + r"\b\s*=([^;]*);", source, re.IGNORECASE)
    if m is None:
        raise NotImplementedError(f"could not extract source value for const {name!r}")
    return m.group(1).rstrip()


# ── imports ───────────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, kw_only=True)
class _ImportSpec:
    class_package: str
    class_name: str
    outer: str | None
    object_name: str


def _seed_imports(b: _Build, super_name: str, within_key: str) -> None:
    b.imports["Core"] = _ImportSpec(class_package="Core", class_name="Package", outer=None,
                                    object_name="Core")
    for obj in (super_name, "Object", "Class", "TextBuffer"):
        _add_import(b, obj)
    if within_key != "Object":
        _add_import(b, within_key)


def _add_import(b: _Build, obj: str) -> str:
    """Ensure `obj` (a class or the Core package) is imported; return its import key (object name).
    A Core class imports with outer=Core; a class in another package pulls in that package import.
    A non-Core home package is recorded in `class_ref_packages` for THIS class's PackageImports —
    even when the import already exists (imports dedupe package-wide, PackageImports is per-class)."""
    def note_pkg(pkg: str | None) -> None:
        if pkg and pkg != "Core" and pkg not in b.class_ref_packages:
            b.class_ref_packages.append(pkg)

    if obj == "Core":
        return obj
    existing = obj if obj in b.imports else next(       # FName is case-insensitive: `texture` (a member
        (k for k in b.imports if k.casefold() == obj.casefold()), None)  # type) dedupes onto `Texture`
    if existing is not None:
        note_pkg(b.imports[existing].outer)              # outer of a class import = its home package
        return existing
    info = b.env.resolve_class(obj)
    if info is None or info.package.casefold() == "core":
        b.imports[obj] = _ImportSpec(class_package="Core", class_name="Class", outer="Core",
                                     object_name=obj)
        return obj
    pkg = info.package
    if pkg not in b.imports:
        b.imports[pkg] = _ImportSpec(class_package="Core", class_name="Package", outer=None,
                                     object_name=pkg)
    note_pkg(pkg)
    b.imports[obj] = _ImportSpec(class_package="Core", class_name="Class", outer=pkg,
                                 object_name=obj)
    return obj


def _resolve_default_refs(props, ref) -> list:
    """Resolve any deferred object-ref default value (a `_RefSpec`) to its final table index, now that
    the export/import tables are ordered. Other props pass through unchanged."""
    return [Prop(p.name, p.ptype, ref(p.value), array_index=p.array_index)
            if isinstance(p.value, _RefSpec) else p for p in props]


def _import_rec(spec: _ImportSpec, name_index: dict[str, int], imp_ref: dict[str, int]) -> Import:
    return Import(class_package=name_index[spec.class_package], class_name=name_index[spec.class_name],
                  package_index=0 if spec.outer is None else imp_ref[spec.outer],
                  object_name=name_index[spec.object_name])


# ── struct (Vector/Rotator/…) imports ──────────────────────────────────────────────────────────────
def _member_graph(b: _Build) -> ClassGraph:
    """The class graph for member/struct resolution — `graph_override` in the multi-class path, else a
    Core/Engine graph (the built-in structs Vector/Rotator/… live in `core.u`)."""
    return b.graph_override if b.graph_override is not None else load_graph(b.env._search_dirs[0])


def _struct_location(graph: ClassGraph, struct_name: str):
    """(home Package, declaring-class name, spelled struct name) for a struct known to the graph."""
    graph.is_struct_name(struct_name)                    # ensures the struct index is built
    loc = graph._struct_loc.get(struct_name.casefold())
    if loc is None:
        return None
    pkg = graph._pkgs[loc[0]]
    e = pkg.exports[loc[1] - 1]
    return pkg, pkg.name_of_ref(e["outer"]), pkg.names[e["nm"]]


def _add_struct_import(b: _Build, graph: ClassGraph, struct_name: str) -> str:
    """Import a struct object (e.g. `Core.Object.Vector`): Class=Struct, Outer=its declaring class.
    Returns the import key (the struct's object name)."""
    loc = _struct_location(graph, struct_name)
    if loc is None:
        raise NotImplementedError(f"struct type {struct_name!r} not found on the search path")
    _pkg, decl_class, spelled = loc
    _add_import(b, decl_class)                            # declaring class + its package import
    b.imports.setdefault(spelled, _ImportSpec(class_package="Core", class_name="Struct",
                                              outer=decl_class, object_name=spelled))
    return spelled


def _add_struct_member_import(b: _Build, graph: ClassGraph, struct_name: str, field: str) -> None:
    """Import a struct member property (e.g. `Core.Object.Vector.X`, a FloatProperty), referenced by a
    `StructMember` (0x36) bytecode token. Outer = the struct import."""
    skey = _add_struct_import(b, graph, struct_name)
    label = graph.struct_member_type(struct_name, field)
    if label is None or label not in _SCALAR_KINDS:
        raise NotImplementedError(f"struct member {struct_name}.{field}: type {label!r} unsupported")
    prop_class = _SCALAR_KINDS[label].prop_class
    spelled = field
    existing = b.imports.get(spelled)
    if existing is not None and existing.outer != skey:
        raise NotImplementedError(f"ambiguous struct-member import {spelled!r} "
                                  f"({existing.outer} vs {skey})")
    b.imports.setdefault(spelled, _ImportSpec(class_package="Core", class_name=prop_class,
                                              outer=skey, object_name=spelled))


def _struct_var_map(b: _Build, fkey: str) -> dict[str, str]:
    """Casefolded name -> struct spelled-name, for this function's struct params/locals and the class's
    struct member vars — but only IMPORTED (built-in/cross-package) structs, whose members become
    imports. Local-struct members resolve via in-package exports, so are excluded."""
    local_struct_keys = set(b.structs)
    out: dict[str, str] = {}
    for p in b.props.values():
        if p.prop_class != "StructProperty" or not (p.outer_key == fkey or p.in_class_chain):
            continue
        tail = [s.key for s in p.type_tail if s.key]
        if tail and tail[0] not in local_struct_keys:
            out[p.name.casefold()] = tail[0]              # import key == struct object name
    return out


def _register_struct_member_imports(b: _Build, toks, name_to_struct: dict[str, str],
                                    graph: ClassGraph) -> None:
    """After lowering, create an import for every struct member a `StructMember` token references. The
    token carries only the field name, so the owning struct is derived from the base sub-expression
    (a struct-typed variable, or a nested struct member)."""
    def struct_of(base) -> str | None:
        op = base.op
        if op in (0x00, 0x01, 0x02):                      # Local/Instance/Default Variable
            for kind, val in base.parts:
                if kind == "obj":
                    return name_to_struct.get(val.casefold())
            return None
        if op == 0x2D:                                    # BoolVariable wraps a variable
            for kind, val in base.parts:
                if kind == "sub":
                    return struct_of(val)
            return None
        if op == 0x36:                                    # nested struct member returning a struct
            fld = sub = None
            for kind, val in base.parts:
                if kind == "obj":
                    fld = val
                elif kind == "sub":
                    sub = val
            st = struct_of(sub) if sub is not None else None
            if st is None:
                return None
            inner = graph.struct_member_type(st, fld)
            return inner.split(":", 1)[1] if inner and inner.startswith("struct:") else None
        return None

    def walk(t) -> None:
        if t.op == 0x36:
            fld = sub = None
            for kind, val in t.parts:
                if kind == "obj":
                    fld = val
                elif kind == "sub":
                    sub = val
            st = struct_of(sub) if sub is not None else None
            if st is None:
                raise NotImplementedError(f"struct-member access .{fld}: owning struct unresolved")
            _add_struct_member_import(b, graph, st, fld)
        for kind, val in t.parts:
            if kind == "sub":
                walk(val)
            elif kind == "parms":
                for s in val:
                    walk(s)

    for t in toks:
        walk(t)


# ── ordering ──────────────────────────────────────────────────────────────────────────────────────
def _orders(b: _Build, class_name: str, super_name: str, config_name: str, decl: ClassDecl,
            default_names, has_new_kind: bool, override):
    """Returns (names, imports, export_rows). `export_rows` are (display name, outer display name)
    pairs — the outer disambiguates the many duplicate names functions introduce (e.g. a param `a` of
    `F5` vs of `F7`). The override supplies rows straight from a golden; without it, the scalar path
    reproduces UCC's export order byte-exact, and the general path (`has_new_kind`) produces a VALID,
    deterministic order for every member kind (functions/enums/consts/structs/arrays/objects) — not
    UCC's within-tier order (that needs the un-reconstructable global FName encounter index, the
    documented name-table-order permutation exclusion), just an internally consistent one."""
    if override is not None:
        return list(override[0]), list(override[1]), [tuple(r) for r in override[2]]
    if has_new_kind:
        return _general_orders(b, class_name, super_name, config_name, default_names)
    members = [b.props[f"cprop:{n}"] for m in decl.members if isinstance(m, VarDecl) for n in m.names]
    name_values = [p.value for p in b.default_props
                   if p.ptype == PT_NAME and isinstance(p.value, str)]
    objs, creation = _scalar_obj_inputs(class_name, super_name, members, b.imports, name_values)
    ordered = order_package(objs, creation, default_global_index())
    names = list(ordered.names)
    for extra in default_names:                          # any default name not reached by the gather
        if extra not in names:
            names.append(extra)
    rows = [(n, None if n == class_name else class_name) for n in ordered.exports]
    return names, list(ordered.imports), rows


# ── general (any-kind) autonomous ordering ────────────────────────────────────────────────────────
def _general_orders(b: _Build, class_name: str, super_name: str, config_name: str, default_names):
    """Order a package with functions/enums/consts/structs/arrays. Feeds every object (each keyed by
    its unique export KEY, since duplicate display names like a param `A` of two functions collide)
    into `order_package`; takes its export/import order (both permutation-excluded by the parity gate)
    and builds the name table deterministically. The result loads and is self-consistent."""
    ident = _export_identity_map(b, class_name)
    class_key = f"class:{class_name}"

    def class_of(key: str) -> str | None:
        if key == class_key:
            return None                                  # a UClass export's Class ref is 0
        if key == "ScriptText":
            return "TextBuffer"
        if key in b.props:
            return b.props[key].prop_class
        if key in b.enums:
            return "Enum"
        if key in b.consts:
            return "Const"
        if key in b.structs:
            return "Struct"
        return "Function"

    objs: list[ObjInput] = []
    creation = _creation_order(b, class_name)
    for key in creation:
        nrefs, orefs = _obj_streams(b, class_name, super_name, config_name, key)
        objs.append(ObjInput(name=key, class_name=class_of(key), outer=ident[key][1],
                             in_package=True, name_refs=nrefs, obj_refs=orefs))
    for objname, spec in b.imports.items():
        objs.append(ObjInput(name=objname, class_name=spec.class_name, outer=spec.outer,
                             in_package=False))

    ordered = order_package(objs, creation, default_global_index())
    export_rows = [ident[k] for k in ordered.exports]
    names_order = _general_names(b, class_name, super_name, config_name, default_names)
    return names_order, list(ordered.imports), export_rows


def _export_identity_map(b: _Build, class_name: str) -> dict[str, tuple[str, str | None]]:
    """Every export KEY -> (display name, outer display name) — the (name, outer) identity used to
    re-key the golden/ordered export slots back onto compiled objects (`_export_refs`)."""
    out: dict[str, tuple[str, str | None]] = {f"class:{class_name}": (class_name, None),
                                              "ScriptText": ("ScriptText", class_name)}
    for key, p in b.props.items():
        out[key] = (p.name, _outer_display(b, class_name, p.outer_key))
    for key, e in b.enums.items():
        out[key] = (e.name, class_name)
    for key, c in b.consts.items():
        out[key] = (c.name, class_name)
    for key, s in b.structs.items():
        out[key] = (s.name, class_name)
    for key, f in b.funcs.items():
        out[key] = (f.name, class_name)
    return out


def _creation_order(b: _Build, class_name: str) -> list[str]:
    """A deterministic parse-order key list covering every export exactly once: class, ScriptText,
    then each class-Children field in declaration order — a function/struct immediately followed by
    its child properties — then any array-inner property left over."""
    order = [f"class:{class_name}", "ScriptText"]
    seen = set(order)

    def add(key: str) -> None:
        if key not in seen:
            seen.add(key)
            order.append(key)

    for key, _is_var in b.chain_fields:
        add(key)
        if key in b.funcs:
            for ck in b.funcs[key].child_keys:
                add(ck)
        elif key in b.structs:
            for mk in b.structs[key].member_keys:
                add(mk)
    for key in b.props:                                  # array inners (not in chain_fields)
        add(key)
    return order


def _obj_streams(b: _Build, class_name: str, super_name: str, config_name: str, key: str
                 ) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The `<<FName` / `<<UObject` emission streams for one export's body, as (name_refs, obj_refs),
    used only to weight `order_package`'s (permutation-excluded) sort. Object refs are import display
    names or export keys — both valid `order_package` lookup keys. A function's streams come from its
    lowered token refs, per the RE'd import-tag pass."""
    if key == f"class:{class_name}":
        return (class_name, config_name, "Core", "None"), (super_name, "ScriptText")
    if key == "ScriptText":
        return ("None",), ()
    if key in b.props:
        p = b.props[key]
        nrefs = (p.category_name,) if p.category_name is not None else ()
        return nrefs, tuple(t.key for t in p.type_tail if t.key)
    if key in b.enums:
        e = b.enums[key]
        return (e.name, *e.values), ()
    if key in b.consts:
        return (b.consts[key].name,), ()
    if key in b.structs:
        return (b.structs[key].name,), ()
    f = b.funcs[key]
    nrefs, orefs = _token_refs(f.toks)
    return (f.name, *nrefs), orefs


def _token_refs(toks) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Walk a lowered token stream, collecting its `<<FName` (`("name", ident)`) and `<<UObject`
    (`("obj", ident)`) ref identities in emission order."""
    names: list[str] = []
    objs: list[str] = []

    def walk(tok) -> None:
        for part in tok.parts:
            match part:
                case ("name", ident):
                    names.append(ident)
                case ("obj", ident):
                    objs.append(ident)
                case ("sub", sub):
                    walk(sub)
                case ("parms", run):
                    for t in run:
                        walk(t)
    for t in toks:
        walk(t)
    return tuple(names), tuple(objs)


def _general_names(b: _Build, class_name: str, super_name: str, config_name: str,
                   default_names) -> list[str]:
    """Every distinct name any body references, deterministically ordered (`None` first, the rest by
    first encounter over a fixed traversal). Name-table ORDER is a documented permutation exclusion,
    so any complete, deterministic order loads."""
    order: list[str] = []
    seen: set[str] = set()

    def add(name: str | None) -> None:
        if name is not None and name not in seen:
            seen.add(name)
            order.append(name)

    add("None")
    add(class_name)
    add("ScriptText")
    add(config_name)
    add("Core")
    for spec in b.imports.values():
        add(spec.class_package)
        add(spec.class_name)
        add(spec.object_name)
    for p in b.props.values():
        add(p.name)
        add(p.category_name)
    for e in b.enums.values():
        add(e.name)
        for v in e.values:
            add(v)
    for c in b.consts.values():
        add(c.name)
    for s in b.structs.values():
        add(s.name)
    for f in b.funcs.values():
        add(f.name)
        for ident in _token_refs(f.toks)[0]:
            add(ident)
    for extra in default_names:
        add(extra)
    return order


def _scalar_obj_inputs(class_name, super_name, members, imports, name_values=()):
    """`ObjInput` graph for the scalar-only autonomous path (mirrors the pre-feature compiler).
    `name_values` are the class's name-typed `defaultproperties` VALUES (e.g. `Naym=Wobbl` -> `Wobbl`),
    emitted as `<<FName` writes in the class-defaults tail — they enter the name gather/count."""
    objs = [ObjInput(name="ScriptText", class_name="TextBuffer", outer=class_name, in_package=True,
                     name_refs=("None",))]
    for i, p in enumerate(members):
        nxt = (members[i + 1].name,) if i + 1 < len(members) else ()
        objs.append(ObjInput(name=p.name, class_name=p.prop_class, outer=class_name, in_package=True,
                             name_refs=(p.name, "None", "None"), obj_refs=nxt))
    child = (members[0].name,) if members else ()
    objs.append(ObjInput(
        name=class_name, class_name="Class", outer=None, in_package=True,
        name_refs=(class_name, class_name, "Core", "System", *name_values, "None"),
        obj_refs=(super_name, "ScriptText", *child, class_name, super_name, "Object")))
    for objname, spec in imports.items():
        objs.append(ObjInput(name=objname, class_name=spec.class_name, outer=spec.outer,
                             in_package=False))
    creation = [class_name, "ScriptText", *(p.name for p in members)]
    return objs, creation


def _export_refs(b: _Build, class_name: str, export_rows: list[tuple[str, str | None]]) -> dict[str, int]:
    """Map each export KEY to its 1-based table index by matching every golden export slot to a
    compiled object on (name, outer name), both casefolded. Function names, the class name, and struct
    names are unique, so (name, outer) is a unique identity even when a bare name repeats across many
    functions (params `A`, `ReturnValue`, …). FName is case-insensitive and UCC re-spells locals from
    its global name pool, hence the casefold."""
    index: dict[tuple[str, str], str] = {}

    def add(name: str, outer: str | None, key: str) -> None:
        ck = (name.casefold(), (outer or "").casefold())
        if ck in index:
            raise NotImplementedError(f"ambiguous export identity {ck!r} ({index[ck]!r} vs {key!r})")
        index[ck] = key

    add(class_name, None, f"class:{class_name}")
    add("ScriptText", class_name, "ScriptText")
    for key, p in b.props.items():
        add(p.name, _outer_display(b, class_name, p.outer_key), key)
    for e in b.enums.values():
        add(e.name, class_name, e.key)
    for c in b.consts.values():
        add(c.name, class_name, c.key)
    for s in b.structs.values():
        add(s.name, class_name, s.key)
    for f in b.funcs.values():
        add(f.name, class_name, f.key)

    refs: dict[str, int] = {}
    for i, (name, path) in enumerate(export_rows):
        # A row's outer is either an immediate-outer string (provisional rows) or an outer-chain tuple
        # (override rows); a single class needs only the immediate outer, which is unique.
        outer = (path[-1] if path else None) if isinstance(path, tuple) else path
        key = index.get((name.casefold(), (outer or "").casefold()))
        if key is None:
            raise NotImplementedError(f"golden export slot {(name, path)!r} has no matching object")
        refs[key] = i + 1
    return refs


def _outer_display(b: _Build, class_name: str, outer_key: str) -> str:
    """The display NAME of an object's outer, for export-slot matching."""
    if outer_key == f"class:{class_name}":
        return class_name
    if outer_key in b.funcs:
        return b.funcs[outer_key].name
    if outer_key in b.structs:
        return b.structs[outer_key].name
    if outer_key in b.props:                           # an array inner's outer is its array property
        return b.props[outer_key].name
    raise NotImplementedError(f"unknown outer key {outer_key!r}")


# ── class Children chain ──────────────────────────────────────────────────────────────────────────
def _class_chain(b: _Build) -> list[str]:
    """The class Children linked-list order (RE'd 2026-09-05): types declared AFTER the first var
    (reversed) + vars (forward) + types declared BEFORE the first var (reversed)."""
    first_var = next((i for i, (_k, is_var) in enumerate(b.chain_fields) if is_var), None)
    if first_var is None:
        return [k for k, _ in reversed(b.chain_fields)]     # no vars: all types reversed
    vars_fwd = [k for k, is_var in b.chain_fields if is_var]
    before = [k for i, (k, is_var) in enumerate(b.chain_fields) if not is_var and i < first_var]
    after = [k for i, (k, is_var) in enumerate(b.chain_fields) if not is_var and i > first_var]
    return list(reversed(after)) + vars_fwd + list(reversed(before))


def _next_map(chain: list[str], exp_ref: dict[str, int]) -> dict[str, int]:
    return {chain[i]: (exp_ref[chain[i + 1]] if i + 1 < len(chain) else 0) for i in range(len(chain))}


# ── name flags ──────────────────────────────────────────────────────────────────────────────────
def _name_flags(name: str) -> int:
    """The u32 name-table flags. Base `0x00070010`; `+0x400` (RF_HighlightName) iff the name is a
    keyword / intrinsic type (`highlight_name_pool`); `+0x04000000` (RF_Native) iff the name is in the
    engine boot global name pool (`engine_name_pool`). Both keyed on the engine pools, not on whether
    this package imports the name."""
    flags = _NAME_BASE
    cf = name.casefold()
    if cf in highlight_name_pool():
        flags |= _HIGHLIGHT
    if cf in engine_name_pool():
        flags |= _RF_NATIVE
    return flags


# ── exports ─────────────────────────────────────────────────────────────────────────────────────
def _build_exports(b, class_name, super_name, super_crc, crlf_source, class_flags, config_name,
                   within_key, chain, chain_next, name_index, nidx, name_cf, exp_ref, imp_ref, ref,
                   export_rows):
    recs: dict[str, Export] = {}
    class_key = f"class:{class_name}"
    recs["ScriptText"] = Export(
        cls=imp_ref["TextBuffer"], super_ref=0, outer=exp_ref[class_key],
        name=name_index["ScriptText"], flags=_RF_TEXTBUFFER,
        body=TextBufferBody(pos=0, top=0, text=crlf_source))

    # Next chains: the class Children chain, each function's param→return→local chain, and each
    # struct's member chain (X→Y→0, same as the class Children linkage).
    next_lookup = dict(chain_next)
    for f in b.funcs.values():
        for i, ck in enumerate(f.child_keys):
            next_lookup[ck] = exp_ref[f.child_keys[i + 1]] if i + 1 < len(f.child_keys) else 0
    for s in b.structs.values():
        for i, mk in enumerate(s.member_keys):
            next_lookup[mk] = exp_ref[s.member_keys[i + 1]] if i + 1 < len(s.member_keys) else 0

    for key, p in b.props.items():
        cat = name_index[p.category_name] if p.category_name is not None else 0
        recs[key] = Export(
            cls=imp_ref[p.prop_class], super_ref=0, outer=exp_ref[p.outer_key],
            name=nidx(p.name), flags=p.object_flags,
            body=PropertyBody(next_field=next_lookup.get(key, 0), array_dim=p.array_dim,
                              property_flags=p.property_flags, category=cat,
                              type_tail=tuple(ref(t) for t in p.type_tail)))
    _build_function_exports(b, class_key, next_lookup, nidx, name_cf, exp_ref, imp_ref, recs)
    for key, e in b.enums.items():
        recs[key] = Export(cls=imp_ref["Enum"], super_ref=0, outer=exp_ref[class_key],
                           name=name_index[e.name], flags=_RF_FIELD,
                           body=EnumBody(next_field=chain_next.get(key, 0),
                                         values=tuple(name_index[v] for v in e.values)))
    for key, c in b.consts.items():
        recs[key] = Export(cls=imp_ref["Const"], super_ref=0, outer=exp_ref[class_key],
                           name=name_index[c.name], flags=_RF_CONST,
                           body=ConstBody(next_field=chain_next.get(key, 0), value=c.value))
    for key, s in b.structs.items():
        children = exp_ref[s.member_keys[0]] if s.member_keys else 0
        recs[key] = Export(cls=imp_ref["Struct"], super_ref=0, outer=exp_ref[class_key],
                           name=name_index[s.name], flags=_RF_FIELD,
                           body=StructBody(super_field=0, next_field=chain_next.get(key, 0),
                                           children=children, friendly_name=name_index[s.name]))

    recs[class_key] = _class_export(b, class_name, super_name, super_crc, crlf_source, class_flags,
                                    config_name, within_key, chain, name_index, exp_ref, imp_ref, ref)
    return tuple(recs[key] for key, _ in sorted(exp_ref.items(), key=lambda kv: kv[1]))


def _build_function_exports(b, class_key, next_lookup, nidx, name_cf, exp_ref, imp_ref, recs) -> None:
    """Emit one UFunction export per function, encoding its script against the final tables. A script
    obj ref is a local/param/return of THIS function, a class member var, an own function, or an
    imported class/function; a name ref is a name-table index."""
    member_by_name = {p.name.casefold(): key for key, p in b.props.items()
                      if p.in_class_chain and p.is_var}
    func_by_name = {f.name.casefold(): f.key for f in b.funcs.values()}
    import_by_name = {k.casefold(): k for k in b.imports}

    def resolver(fn):
        def resolve_inv(kind: str, ident: str) -> int:
            if kind == "name":
                return name_cf[ident.casefold()]
            cf = ident.casefold()
            if cf in fn.local_by_name:
                return exp_ref[fn.local_by_name[cf]]
            if cf in member_by_name:
                return exp_ref[member_by_name[cf]]
            if cf in func_by_name:
                return exp_ref[func_by_name[cf]]
            if cf in import_by_name:
                return imp_ref[import_by_name[cf]]
            raise NotImplementedError(f"cannot resolve script ref {ident!r} in {fn.name!r}")
        return resolve_inv

    for fkey, fn in b.funcs.items():
        children = exp_ref[fn.child_keys[0]] if fn.child_keys else 0
        super_ref = imp_ref[fn.super_ref_key] if fn.super_ref_key else 0
        recs[fkey] = Export(
            # the export-table Super column carries the overridden function too, not just the body
            cls=imp_ref["Function"], super_ref=super_ref, outer=exp_ref[class_key], name=nidx(fn.name),
            flags=_RF_FIELD,
            body=FunctionBody(
                super_field=super_ref,
                next_field=next_lookup.get(fkey, 0), children=children,
                friendly_name=nidx(fn.name), line=fn.line, text_pos=fn.text_pos,
                script=encode_script(list(fn.toks), resolver(fn)), script_size=fn.script_size,
                inative=0, oper_precedence=0, function_flags=fn.function_flags))


def _class_export(b, class_name, super_name, super_crc, crlf_source, class_flags, config_name,
                  within_key, chain, name_index, exp_ref, imp_ref, ref):
    children = exp_ref[chain[0]] if chain else 0
    return Export(
        cls=0, super_ref=imp_ref[super_name], outer=0, name=name_index[class_name],
        flags=b.class_object_flags,
        body=ClassBody(
            super_field=imp_ref[super_name], next_field=0, script_text=exp_ref["ScriptText"],
            children=children, friendly_name=name_index[class_name],
            line=0xFFFFFFFF, text_pos=0xFFFFFFFF, script=b"",
            probe_mask=0, ignore_mask=0xFFFFFFFFFFFFFFFF, label_table_offset=0xFFFF,
            state_flags=0, class_flags=class_flags, class_guid=b"\x00" * 16,
            dependencies=(Dependency(cls=exp_ref[f"class:{class_name}"], deep=1,
                                     script_text_crc=script_text_crc(crlf_source)),
                          Dependency(cls=imp_ref[super_name], deep=1, script_text_crc=super_crc)),
            package_imports=(name_index[class_name], name_index["Core"]),
            class_within=imp_ref[within_key], class_config_name=name_index[config_name],
            default_props=write_props(lambda s: name_index[s],
                                      _resolve_default_refs(b.default_props, ref))))


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────
def _script_text(source: str) -> str:
    """The text UCC stores in `ScriptText`: the class source up to (not including) the
    `defaultproperties` block, which the compiler consumes separately."""
    m = re.search(r"(?im)^[ \t]*defaultproperties\b", source)
    return source[:m.start()] if m else source


def _to_crlf(text: str) -> str:
    """Normalise every lone `\\n` and `\\r\\n` to `\\r\\n` (the form UCC stores in `ScriptText`)."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


# ══ multi-class package compile (compile_package_dir) ═════════════════════════════════════════════
# Build a WHOLE package (many `.uc` -> one `.u`) with shared name/import/export tables. The parity
# oracle is `gate.perm_gate`, which excludes name/import/export table ORDER, so this path assigns a
# valid deterministic order (creation order) rather than reproducing UCC's refcount sort. What it
# DOES reproduce byte-exact (perm_gate compares them): every object body, name CONTENT+FLAGS, import
# CONTENT, the export identity set, same-package super/refs, Dependencies, and PackageImports order.

@dataclass(frozen=True, kw_only=True)
class _ClassUnit:
    """Everything resolved for one class in a multi-class build."""
    name: str
    class_key: str
    st_key: str
    super_name: str
    super_export_key: str | None      # in-package super's class export key, else None (an import)
    super_crc: int                    # the super's own ScriptTextCRC (in-package: computed; else env)
    crlf_source: str
    class_flags: int
    config_name: str
    within_key: str
    chain: tuple[str, ...]            # class Children order (prefixed keys)
    default_props: tuple[Prop, ...]
    package_imports: tuple[str, ...]  # PackageImports package names, in order
    self_crc: int
    object_flags: int                 # the UClass export's ObjectFlags (+RF_Native for native)


def compile_package_dir(classes: dict[str, str], env: InstallEnv, *,
                        package_name: str) -> CompiledPackage:
    """Compile every `.uc` in a package (`{filename: source}`) into ONE `CompiledPackage` with shared
    tables. `package_name` is the package's own name (UCC takes it from EditPackages / the output
    filename — it heads every class's PackageImports and enters the name table). Classes are compiled
    supers-first; a same-package super/ref becomes an EXPORT ref, a cross-package super an import.
    `perm_gate(serialize(...), ucc_golden)` is byte-exact modulo the documented exclusions (table
    order, GUID, FName case)."""
    from .serialize import serialize as _serialize      # local: avoid a compile<->serialize cycle

    decls: dict[str, tuple[ClassDecl, str]] = {}
    for src in classes.values():
        decl = parse(src)
        _reject_unsupported(decl)
        decls[decl.name] = (decl, decl.source or src)
    in_pkg_cf = {name.casefold() for name in decls}
    order = _compile_order(decls, in_pkg_cf)
    extra_pkgs = _extra_super_packages(decls, env, in_pkg_cf)

    search_dir = env._search_dirs[0]
    base_pkgs = ("core.u", "Engine.u", *(f"{p}.u" for p in extra_pkgs))
    catalog = load_catalog(search_dir, packages=base_pkgs)
    base_paths = [os.path.join(search_dir, p) for p in base_pkgs]

    b = _Build(class_name="", env=env,
               in_pkg_class_names={name.casefold(): name for name in decls})
    units: list[_ClassUnit] = []
    tmp = tempfile.mkdtemp(prefix="uscpkg-", dir=os.environ.get("TMPDIR"))
    partial = os.path.join(tmp, "partial.u")
    try:
        pkg = None
        for i, cname in enumerate(order):
            decl, src = decls[cname]
            graph = ClassGraph(base_paths + ([partial] if i > 0 else []))
            unit = _build_class_unit(b, decl, src, env, in_pkg_cf, units, graph, catalog,
                                     package_name)
            units.append(unit)
            pkg = _finalize_multi(b, units, package_name)
            if i + 1 < len(order):                        # only needed to seed the next class's graph
                with open(partial, "wb") as fh:
                    fh.write(_serialize(pkg))
        # Re-emit in UCC's real name/import/export order (decode the provisional bytes, run the
        # dumped-global-index tie-break) — the same autonomous ordering the single-class path uses.
        from .reorder import true_order
        names, imports, export_rows = true_order(_serialize(pkg))
        return _finalize_multi(b, units, package_name, override=(names, imports, export_rows))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def compile_conversation_siblings(classes: dict[str, str], env: InstallEnv, *, package_name: str,
                                  con_files: dict[str, bytes]) -> dict[str, CompiledPackage]:
    """Build the sibling packages every `#exec CONVERSATION IMPORT` in `classes` emits, keyed by
    package name (`<package_name>Text`, `<package_name>Audio<audioPackage>`). `con_files` maps a
    referenced `.con` filename (as written in the directive, case-insensitively) to its bytes. Returns
    `{}` when no class imports a conversation. The class package itself gets nothing from the
    directive."""
    from .conimport import build_conversation_packages, parse_con

    by_cf = {name.casefold(): data for name, data in con_files.items()}
    wanted: list[str] = []
    for src in classes.values():
        for fname in conversation_import_files(parse(src)):
            if fname not in wanted:
                wanted.append(fname)
    if not wanted:
        return {}
    if len(wanted) > 1:
        raise NotImplementedError(f"multiple CONVERSATION IMPORTs in one package not supported yet: "
                                  f"{wanted}")
    fname = wanted[0]
    data = by_cf.get(fname.casefold())
    if data is None:
        raise NotImplementedError(f"conversation file not found: {fname!r} "
                                  f"(have {sorted(con_files)})")
    return build_conversation_packages(parse_con(data), package_name, env)


def _compile_order(decls: dict[str, tuple[ClassDecl, str]], in_pkg_cf: set[str]) -> list[str]:
    """Class names ordered so a class follows every in-package class it depends on: its super AND any
    in-package class it names in a member/param/local/return/struct-member type (so member access like
    `Request.Username` resolves against the already-built partial package). A reference CYCLE (mutual
    references) can't be honoured by the incremental build, so such an edge is dropped and the classes
    fall back to source order."""
    order: list[str] = []
    placed: set[str] = set()
    stack: set[str] = set()
    by_cf = {n.casefold(): n for n in decls}

    def place(name: str) -> None:
        if name in placed or name in stack:
            return                                       # placed, or a cycle back-edge (dropped)
        stack.add(name)
        decl = decls[name][0]
        deps = list(_referenced_in_pkg(decl, in_pkg_cf))
        if decl.super_name is not None and decl.super_name.casefold() in in_pkg_cf:
            deps.insert(0, decl.super_name.casefold())   # super first among deps
        for dep_cf in deps:
            place(by_cf[dep_cf])
        stack.discard(name)
        placed.add(name)
        order.append(name)

    for name in decls:
        place(name)
    return order


def _referenced_in_pkg(decl: ClassDecl, in_pkg_cf: set[str]) -> list[str]:
    """Casefolded names of the in-package classes `decl` references through a type (deduped, in first-
    encounter order); excludes `decl` itself and its super (ordered separately)."""
    out: list[str] = []
    seen = {decl.name.casefold()}
    if decl.super_name is not None:
        seen.add(decl.super_name.casefold())

    def note(type_ref) -> None:
        if type_ref is None:
            return
        for base in (type_ref.base, getattr(type_ref.inner, "base", None), type_ref.meta_class):
            cf = base.casefold() if base else None
            if cf and cf in in_pkg_cf and cf not in seen:
                seen.add(cf)
                out.append(cf)

    for m in decl.members:
        if isinstance(m, VarDecl):
            note(m.type)
        elif isinstance(m, StructDecl):
            for sm in m.members:
                note(sm.type)
    for f in decl.functions:
        note(f.return_type)
        for p in f.params:
            note(p.type)
        for vd in f.locals:
            note(vd.type)
    return out


def _extra_super_packages(decls, env: InstallEnv, in_pkg_cf: set[str]) -> list[str]:
    """Non-Core/Engine home packages of any cross-package super — loaded into the lowering graph and
    catalog so inherited members/functions resolve (a `BrushBuilder` subclass pulls in `Editor`)."""
    out: list[str] = []
    for decl, _src in decls.values():
        sup = decl.super_name
        if sup is None or sup.casefold() in in_pkg_cf:
            continue
        info = env.resolve_class(sup)
        if info is not None and info.package.casefold() not in ("core", "engine") \
                and info.package not in out:
            out.append(info.package)
    return out


def _build_class_unit(b: _Build, decl: ClassDecl, src: str, env: InstallEnv, in_pkg_cf: set[str],
                      built: list[_ClassUnit], graph, catalog, package_name: str) -> _ClassUnit:
    """Build one class into the shared accumulator `b` (prefixed keys), returning its resolved unit.
    Per-class state (chain, defaults, member ClassFlags, referenced packages) is snapshotted and reset
    here; `props`/`funcs`/`imports`/… stay package-wide."""
    class_name = decl.name
    super_name = decl.super_name
    in_package_super = super_name.casefold() in in_pkg_cf
    super_unit = next((u for u in built if u.name.casefold() == super_name.casefold()), None)
    if in_package_super and super_unit is None:
        raise NotImplementedError(f"in-package super {super_name!r} of {class_name!r} not built first")
    if in_package_super:
        super_crc = super_unit.self_crc
        super_class_flags = super_unit.class_flags
        super_pkg_imports = super_unit.package_imports
    else:
        info = env.resolve_class(super_name)
        if info is None:
            raise NotImplementedError(f"cannot resolve super class {super_name!r} on the search path")
        super_crc = info.self_crc
        super_class_flags = info.class_flags
        super_pkg_imports = info.package_imports

    b.prefix = f"{class_name}::"
    b.class_name = class_name
    b.chain_fields = []
    b.default_props = []
    b.member_class_flags = 0
    b.class_object_flags = _class_object_flags(decl)
    b.class_ref_packages = []
    b.local_enums = {m.name for m in decl.members if isinstance(m, EnumDecl)}
    b.local_structs = {m.name for m in decl.members if isinstance(m, StructDecl)}
    b.graph_override = graph
    b.catalog_override = catalog

    crlf_source = _to_crlf(_script_text(src))
    class_flags, config_name, within_key = _class_header(decl, env)
    b.emit_zero_defaults = _auto_emit_defaults(
        decl, class_flags | (super_class_flags & _CLASS_INHERIT_MASK))

    # Seed the always-present imports; the super import only when it is cross-package.
    b.imports.setdefault("Core", _ImportSpec(class_package="Core", class_name="Package", outer=None,
                                             object_name="Core"))
    for obj in ("Object", "Class", "TextBuffer"):
        _add_import(b, obj)
    if not in_package_super:
        _add_import(b, super_name)
    if within_key != "Object":
        _add_import(b, within_key)

    _build_members(b, decl)
    if decl.functions:
        _build_functions(b, decl, super_name, crlf_source)

    class_flags |= b.member_class_flags | (super_class_flags & _CLASS_INHERIT_MASK)
    chain = tuple(_class_chain(b))
    # PackageImports = own package, then the super chain's transitive package deps (a class inherits
    # Engine from an in-package Texture subclass, IpDrv+Engine from a TcpLink subclass), then any
    # other package this class references directly, then Core.
    # FName is case-insensitive: dedup Editor/editor, and spell each dep as its existing package
    # import so the name table doesn't carry both spellings (the super's PI may differ in case).
    imp_by_cf = {k.casefold(): b.imports[k].object_name for k in b.imports}
    deps: list[str] = []
    seen_cf = {package_name.casefold(), "core"}
    for p in (*super_pkg_imports, *b.class_ref_packages):
        cf = p.casefold()
        if cf not in seen_cf:
            seen_cf.add(cf)
            deps.append(imp_by_cf.get(cf, p))
    package_imports = (package_name, *deps, "Core")
    return _ClassUnit(
        name=class_name, class_key=b.okey(f"class:{class_name}"), st_key=b.okey("ScriptText"),
        super_name=super_name,
        super_export_key=(super_unit.class_key if in_package_super else None),
        super_crc=super_crc, crlf_source=crlf_source, class_flags=class_flags,
        config_name=config_name, within_key=within_key, chain=chain,
        default_props=tuple(b.default_props), package_imports=package_imports,
        self_crc=script_text_crc(crlf_source), object_flags=b.class_object_flags)


def _imports_by_display(b: _Build, display_order: list[str]) -> list[str]:
    """Map an order of import DISPLAY names (object names, as `reorder.true_order` yields them) to
    `b.imports` KEYS — a function import is keyed `func:<Class>.<Name>`, not its bare object name."""
    by_disp: dict[str, str] = {}
    for key, spec in b.imports.items():
        by_disp.setdefault(spec.object_name.casefold(), key)
    return [by_disp[n.casefold()] for n in display_order]


def _multi_key_identity(b: _Build, units: list[_ClassUnit]) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Every export KEY -> (display name, outer-chain) for the multi-class path — the identity used to
    map an `order_override`'s export rows back onto compiled keys. The outer-chain (outermost->
    immediate) disambiguates a leaf whose immediate outer repeats across classes."""
    disp: dict[str, str] = {}
    outer_key: dict[str, str | None] = {}
    for u in units:
        disp[u.class_key] = u.name; outer_key[u.class_key] = None
        disp[u.st_key] = "ScriptText"; outer_key[u.st_key] = u.class_key
    for key, p in b.props.items():
        disp[key] = p.name; outer_key[key] = p.outer_key
    for key, e in b.enums.items():
        disp[key] = e.name; outer_key[key] = _outer_class_key(key)
    for key, c in b.consts.items():
        disp[key] = c.name; outer_key[key] = _outer_class_key(key)
    for key, s in b.structs.items():
        disp[key] = s.name; outer_key[key] = _outer_class_key(key)
    for key, f in b.funcs.items():
        disp[key] = f.name; outer_key[key] = f.class_key

    def chain(key: str) -> tuple[str, ...]:
        out, cur = [], outer_key[key]
        while cur is not None:
            out.append(disp[cur]); cur = outer_key.get(cur)
        return tuple(reversed(out))
    return {k: (d, chain(k)) for k, d in disp.items()}


def _finalize_multi(b: _Build, units: list[_ClassUnit], package_name: str,
                    override: tuple[list[str], list[str], list[tuple[str, str | None]]] | None = None
                    ) -> CompiledPackage:
    """Order the shared tables and emit the linked `CompiledPackage`. Without `override` a provisional
    order is used (the caller re-derives the real order via `reorder.true_order` and calls again with
    `override=(names, imports, export_rows)`)."""
    if override is None:
        export_keys = _multi_export_order(b, units)
        imports_order = list(b.imports)
        names_order = [pool_case(n) for n in _multi_names(b, units, package_name)]
    else:
        ov_names, ov_imports, ov_rows = override
        ident = {(d.casefold(), tuple(x.casefold() for x in path)): k
                 for k, (d, path) in _multi_key_identity(b, units).items()}
        export_keys = [ident[(d.casefold(), tuple(x.casefold() for x in path))] for d, path in ov_rows]
        imports_order = _imports_by_display(b, ov_imports)
        names_order = [pool_case(n) for n in ov_names]
    exp_ref = {k: i + 1 for i, k in enumerate(export_keys)}
    imp_ref = {n: -(i + 1) for i, n in enumerate(imports_order)}

    name_cf = {n.casefold(): i for i, n in enumerate(names_order)}
    name_index = _NameIndex(name_cf)

    def nidx(name: str) -> int:
        return name_index[name]

    def ref(spec: _RefSpec) -> int:
        if spec.key == "":
            return 0
        return exp_ref[spec.key] if spec.is_export else imp_ref[spec.key]

    names = tuple(Name(text=n, flags=_name_flags(n)) for n in names_order)
    import_recs = tuple(_import_rec(b.imports[n], name_index, imp_ref) for n in imports_order)

    next_lookup: dict[str, int] = {}
    for u in units:
        for i, key in enumerate(u.chain):
            next_lookup[key] = exp_ref[u.chain[i + 1]] if i + 1 < len(u.chain) else 0
    for f in b.funcs.values():
        for i, ck in enumerate(f.child_keys):
            next_lookup[ck] = exp_ref[f.child_keys[i + 1]] if i + 1 < len(f.child_keys) else 0
    for s in b.structs.values():
        for i, mk in enumerate(s.member_keys):
            next_lookup[mk] = exp_ref[s.member_keys[i + 1]] if i + 1 < len(s.member_keys) else 0

    recs: dict[str, Export] = {}
    for u in units:
        recs[u.st_key] = Export(
            cls=imp_ref["TextBuffer"], super_ref=0, outer=exp_ref[u.class_key],
            name=name_index["ScriptText"], flags=_RF_TEXTBUFFER,
            body=TextBufferBody(pos=0, top=0, text=u.crlf_source))
    for key, p in b.props.items():
        cat = name_index[p.category_name] if p.category_name is not None else 0
        recs[key] = Export(
            cls=imp_ref[p.prop_class], super_ref=0, outer=exp_ref[p.outer_key],
            name=nidx(p.name), flags=p.object_flags,
            body=PropertyBody(next_field=next_lookup.get(key, 0), array_dim=p.array_dim,
                              property_flags=p.property_flags, category=cat,
                              type_tail=tuple(ref(t) for t in p.type_tail)))
    for key, e in b.enums.items():
        recs[key] = Export(cls=imp_ref["Enum"], super_ref=0, outer=exp_ref[_outer_class_key(key)],
                           name=name_index[e.name], flags=_RF_FIELD,
                           body=EnumBody(next_field=next_lookup.get(key, 0),
                                         values=tuple(name_index[v] for v in e.values)))
    for key, c in b.consts.items():
        recs[key] = Export(cls=imp_ref["Const"], super_ref=0, outer=exp_ref[_outer_class_key(key)],
                           name=name_index[c.name], flags=_RF_CONST,
                           body=ConstBody(next_field=next_lookup.get(key, 0), value=c.value))
    for key, s in b.structs.items():
        children = exp_ref[s.member_keys[0]] if s.member_keys else 0
        recs[key] = Export(cls=imp_ref["Struct"], super_ref=0, outer=exp_ref[_outer_class_key(key)],
                           name=name_index[s.name], flags=_RF_FIELD,
                           body=StructBody(super_field=0, next_field=next_lookup.get(key, 0),
                                           children=children, friendly_name=name_index[s.name]))
    _multi_function_exports(b, next_lookup, nidx, name_cf, exp_ref, imp_ref, recs)
    for u in units:
        recs[u.class_key] = _multi_class_export(b, u, name_index, exp_ref, imp_ref, ref)

    exports = tuple(recs[k] for k in export_keys)
    return CompiledPackage(version=69, licensee=0, package_flags=1,
                           names=names, imports=import_recs, exports=exports)


def _outer_class_key(key: str) -> str:
    """The owning-class export key of a prefixed enum/const/struct member key
    (`Foo::enum:Bar` -> `Foo::class:Foo`)."""
    cname = key.split("::", 1)[0]
    return f"{cname}::class:{cname}"


def _multi_export_order(b: _Build, units: list[_ClassUnit]) -> list[str]:
    """A deterministic order covering every export key exactly once (permutation-excluded by the
    gate): per class its UClass, ScriptText, then each Children field with its child properties, then
    any leftover (array-inner) property."""
    order: list[str] = []
    seen: set[str] = set()

    def add(key: str) -> None:
        if key not in seen:
            seen.add(key)
            order.append(key)

    for u in units:
        add(u.class_key)
        add(u.st_key)
        for key in u.chain:
            add(key)
            if key in b.funcs:
                for ck in b.funcs[key].child_keys:
                    add(ck)
            elif key in b.structs:
                for mk in b.structs[key].member_keys:
                    add(mk)
    for key in b.props:                                   # array inners (not in any chain)
        add(key)
    return order


def _multi_names(b: _Build, units: list[_ClassUnit], package_name: str) -> list[str]:
    """Every distinct name any table/body references, deterministically ordered (`None` first)."""
    order: list[str] = []
    seen: set[str] = set()

    def add(name: str | None) -> None:
        if name is not None and name not in seen:
            seen.add(name)
            order.append(name)

    add("None")
    add(package_name)
    for u in units:
        add(u.name)
        add("ScriptText")
        add(u.config_name)
        for pkg in u.package_imports:
            add(pkg)
    for spec in b.imports.values():
        add(spec.class_package)
        add(spec.class_name)
        add(spec.object_name)
    for p in b.props.values():
        add(p.name)
        add(p.category_name)
    for e in b.enums.values():
        add(e.name)
        for v in e.values:
            add(v)
    for c in b.consts.values():
        add(c.name)
    for s in b.structs.values():
        add(s.name)
    for f in b.funcs.values():
        add(f.name)
        for ident in _token_refs(f.toks)[0]:
            add(ident)
    for u in units:
        for prop in u.default_props:
            add(prop.name)                                # inherited-override names aren't in b.props
            if prop.ptype == PT_NAME and isinstance(prop.value, str):
                add(prop.value)
    return order


def _multi_function_exports(b: _Build, next_lookup, nidx, name_cf, exp_ref, imp_ref, recs) -> None:
    """One UFunction export per function; each script ref resolves within its OWN class (locals, own
    members, own funcs) then package imports. Cross-class inherited virtual calls are name refs (no
    object ref), so they need only the name table."""
    members_by_class: dict[str, dict[str, str]] = {}
    funcs_by_class: dict[str, dict[str, str]] = {}
    for key, p in b.props.items():
        if p.in_class_chain and p.is_var:
            members_by_class.setdefault(p.outer_key, {})[p.name.casefold()] = key
    for f in b.funcs.values():
        funcs_by_class.setdefault(f.class_key, {})[f.name.casefold()] = f.key
    import_by_name = {k.casefold(): k for k in b.imports}

    def resolver(fn: _Func):
        own_members = members_by_class.get(fn.class_key, {})
        own_funcs = funcs_by_class.get(fn.class_key, {})

        def resolve_inv(kind: str, ident: str) -> int:
            if kind == "name":
                return name_cf[ident.casefold()]
            cf = ident.casefold()
            if cf in fn.local_by_name:
                return exp_ref[fn.local_by_name[cf]]
            if cf in own_members:
                return exp_ref[own_members[cf]]
            if cf in own_funcs:
                return exp_ref[own_funcs[cf]]
            if cf in import_by_name:
                return imp_ref[import_by_name[cf]]
            raise NotImplementedError(f"cannot resolve script ref {ident!r} in {fn.name!r}")
        return resolve_inv

    for fkey, fn in b.funcs.items():
        children = exp_ref[fn.child_keys[0]] if fn.child_keys else 0
        super_ref = imp_ref[fn.super_ref_key] if fn.super_ref_key else 0
        recs[fkey] = Export(
            cls=imp_ref["Function"], super_ref=super_ref, outer=exp_ref[fn.class_key], name=nidx(fn.name),
            flags=_RF_FIELD,
            body=FunctionBody(
                super_field=super_ref,
                next_field=next_lookup.get(fkey, 0), children=children,
                friendly_name=nidx(fn.name), line=fn.line, text_pos=fn.text_pos,
                script=encode_script(list(fn.toks), resolver(fn)), script_size=fn.script_size,
                inative=0, oper_precedence=0, function_flags=fn.function_flags))


def _multi_class_export(b: _Build, u: _ClassUnit, name_index, exp_ref, imp_ref, ref) -> Export:
    super_ref = exp_ref[u.super_export_key] if u.super_export_key else imp_ref[u.super_name]
    children = exp_ref[u.chain[0]] if u.chain else 0
    self_dep = Dependency(cls=exp_ref[u.class_key], deep=1, script_text_crc=u.self_crc)
    super_dep = Dependency(cls=super_ref, deep=1, script_text_crc=u.super_crc)
    return Export(
        cls=0, super_ref=super_ref, outer=0, name=name_index[u.name], flags=u.object_flags,
        body=ClassBody(
            super_field=super_ref, next_field=0, script_text=exp_ref[u.st_key],
            children=children, friendly_name=name_index[u.name],
            line=0xFFFFFFFF, text_pos=0xFFFFFFFF, script=b"",
            probe_mask=0, ignore_mask=0xFFFFFFFFFFFFFFFF, label_table_offset=0xFFFF,
            state_flags=0, class_flags=u.class_flags, class_guid=b"\x00" * 16,
            dependencies=(self_dep, super_dep),
            package_imports=tuple(name_index[p] for p in u.package_imports),
            class_within=imp_ref[u.within_key], class_config_name=name_index[u.config_name],
            default_props=write_props(lambda s: name_index[s],
                                      _resolve_default_refs(u.default_props, ref))))
