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
from dataclasses import dataclass, field

from ..native.actor_write import (PT_ARRAY, PT_BOOL, PT_BYTE, PT_FLOAT, PT_INT, PT_NAME, PT_OBJECT,
                                   PT_STR, PT_STRUCT, ArrayValue, Prop, StructValue, write_props)
from .ast import ClassDecl, ConstDecl, EnumDecl, FuncDecl, StateDecl, StructDecl, VarDecl
from .bytecode import Tok, encode_script
from .crc import script_text_crc
from .env import InstallEnv
from .lower import (EX_DEFAULT_VARIABLE, EX_DYNAMIC_CAST, EX_FINAL_FUNCTION, EX_INSTANCE_VARIABLE,
                    EX_LABEL_TABLE, EX_METACAST, EX_NOTHING, EX_OBJECT_CONST, EX_RETURN, LowerError,
                    Scope, build_scope, consts_of, enum_type_names, enums_of, local_funcs_of,
                    lower_function, lower_state_body, members_array_dim_of, members_meta_of,
                    members_of, _mem_size)
from .model import (ClassBody, CompiledPackage, ConstBody, Dependency, EnumBody, Export, FunctionBody,
                    Import, Name, ObjectBody, PropertyBody, StateBody, StructBody, TextBufferBody,
                    TextureBody, TextureMip)
from .global_index import default_global_index, engine_name_pool, highlight_name_pool, pool_case
from .natives import (FUNC_NET, FUNC_NET_RELIABLE, ClassGraph, ClassSig, FuncBody, load_catalog,
                      load_graph, prop_type_label)
from .ordering import ObjInput, order_package
from .parser import parse
from . import texture_import
from ..upackage import read_compact_index as _rci
from ..uprops.base import PROPERTY_TYPES
from ..uprops.ufield import _decode_property, _field_next

# object flags per object kind
_RF_TEXTBUFFER = 0x00340000
_RF_FIELD = 0x00070004               # UProperty / Enum / Struct / struct-member / array-inner
_RF_CONST = 0x00070000               # UConst (no low 0x4 bit)
_RF_CLASS = 0x000F0004
# `#exec TEXTURE IMPORT` objects (RE'd 2026-09-13 against a live UED22 golden, spike.md): the
# UPalette export is a plain object (matches `conimport._RF_OBJECT`); the UTexture export carries
# RF_Standalone (matches `conimport._RF_STANDALONE`) — both top-level package objects, Outer=0.
_RF_PALETTE_OBJ = 0x00070004
_RF_TEXTURE_OBJ = 0x000F0004

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

# ── EProbe / ProbeMask (RE'd 2026-09-12) ──────────────────────────────────────────────────────────
# The engine's fixed probe-function table. Each bit corresponds to a "probe" event native code
# dispatches into script only if the bit is set. Recovered from the boot-registered EName table
# (`global_index.py`'s dumped `ename_ued22.json`): probe function names occupy consecutive ordinals
# starting at "Spawned" (217); unused slots register a literal "ProbeN" placeholder instead of a real
# function name, where N IS the bit index -- e.g. "Probe34" sits at ordinal 251 = 251-217 = bit 34,
# self-confirming the offset for every gap (Probe4/5/34/39/48..62). Cross-checked against a real
# measured fact from earlier in this campaign (`UnrealShare.UnrealTestInfo` overriding `Tick` alone ->
# ProbeMask=0x1000000000 = bit 36, matching "Tick" at ordinal 253 here) and against `Engine.Pawn`'s
# real ProbeMask (0xf8040c02 decodes to Destroyed/Falling/Landed/BaseChange/EncroachingOn/
# EncroachedBy/FootZoneChange/HeadZoneChange/PainTimer -- all plausible Pawn overrides).
_EPROBE_BASE = 217
_EPROBE_TABLE: tuple[str, ...] = (
    "Spawned", "Destroyed", "GainedChild", "LostChild", None, None, "Trigger", "UnTrigger",
    "Timer", "HitWall", "Falling", "Landed", "ZoneChange", "Touch", "UnTouch", "Bump",
    "BeginState", "EndState", "BaseChange", "Attach", "Detach", "ActorEntered", "ActorLeaving",
    "KillCredit", "AnimEnd", "EndedRotation", "InterpolateEnd", "EncroachingOn", "EncroachedBy",
    "FootZoneChange", "HeadZoneChange", "PainTimer", "SpeechTimer", "MayFall", None, "Die",
    "Tick", "PlayerTick", "Expired", None, "SeePlayer", "EnemyNotVisible", "HearNoise",
    "UpdateEyeHeight", "SeeMonster", "SeeFriend", "SpecialHandling", "BotDesireability",
)
_PROBE_BIT_OF: dict[str, int] = {name.casefold(): i for i, name in enumerate(_EPROBE_TABLE) if name}


def _probe_bits(function_names) -> int:
    """The OR of EProbe bits for every name in `function_names` that is a probe function."""
    mask = 0
    for name in function_names:
        bit = _PROBE_BIT_OF.get(name.casefold())
        if bit is not None:
            mask |= 1 << bit
    return mask


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
CPF_NATIVE = 0x00001000              # the `native` var modifier (measured live vs UCC on UWeb's
                                      # `WebRequest.VariableMap`/`WebResponse.ReplacementMap`)
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
    "native": CPF_NATIVE, "intrinsic": CPF_NATIVE, "private": 0,
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


# `pointer` (raw native-only field, e.g. UWeb `WebRequest.VariableMap`) has no on-disk default-tag
# type code — a `PointerProperty` is a C++ address with no UnrealScript literal syntax, so real UCC
# never emits a defaultproperties tag for one (confirmed: it only appears on native classes, which
# skip unset defaults entirely — `_auto_emit_defaults`). PT_POINTER is a local sentinel, never a real
# PT_* tag code, so `_emit_default` can name the gap instead of a `_SCALAR_ZERO` KeyError if a default
# were ever attempted.
PT_POINTER = -1
_SCALAR_KINDS: dict[str, _Kind] = {
    "int":     _Kind(prop_class="IntProperty",     ptype=PT_INT),
    "float":   _Kind(prop_class="FloatProperty",   ptype=PT_FLOAT),
    "bool":    _Kind(prop_class="BoolProperty",    ptype=PT_BOOL),
    "byte":    _Kind(prop_class="ByteProperty",    ptype=PT_BYTE),
    "string":  _Kind(prop_class="StrProperty",     ptype=PT_STR, base_flags=CPF_NEEDCTORLINK),
    "name":    _Kind(prop_class="NameProperty",    ptype=PT_NAME),
    "pointer": _Kind(prop_class="PointerProperty", ptype=PT_POINTER),
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
    rep_offset: int | None = None    # inherited from an overridden FUNC_Net function; else None


@dataclass(frozen=True, kw_only=True)
class _State:
    """A UState export: a `state Foo {...}` block's top-level labelled code. No params/locals/return
    of its own (`children=0` always, for now — nested function overrides aren't supported yet)."""
    key: str
    name: str
    class_key: str
    line: int
    text_pos: int
    toks: tuple                      # full lowered stream: code + Stop + Nothing + [LabelTable]
    script_size: int                 # in-memory ScriptSize (sum of _mem_size over all of `toks`)


@dataclass(frozen=True, kw_only=True)
class _TexDef:
    """One `#exec TEXTURE IMPORT` — a `UTexture` export plus its auto-created `UPalette` sibling
    export (both top-level package objects, Outer=0; see `texture_import.py` / `compile-model.md`)."""
    key: str                          # the UTexture export key
    name: str                         # its object name (directive NAME=)
    palette_key: str                  # the UPalette export key
    palette_name: str                 # "Palette1", "Palette2", ... (numbered within this class)
    lodset: int
    result: texture_import.TextureImportResult


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
    states: dict[str, _State] = field(default_factory=dict)
    textures: dict[str, _TexDef] = field(default_factory=dict)
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
    in_pkg_decls: dict[str, ClassDecl] = field(default_factory=dict)  # casefold -> its ClassDecl
                                                  # (multi-class: every sibling's AST, incl. one not
                                                  # yet built — backs `_super_field_order`'s in-package
                                                  # fallback, since an in-progress class has no
                                                  # compiled export to decode field order from)
    graph_override: object | None = None      # multi-class: a ClassGraph seeing in-package classes
    catalog_override: object | None = None
    extra_deps: list[str] = field(default_factory=list)  # classes Context'd into (deep=0 Dependency
                                                          # entries), real-cased, one per occurrence,
                                                          # assembled by `_build_callables` (below)

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


def _pool_cased_dedup(names: list[str]) -> list[str]:
    """`pool_case` each name, then drop a later EXACT-text repeat (first occurrence wins) — matching
    `serialize.NameTable.index`'s own exact-string dedup. Needed because the gather order is deduped
    on the SOURCE spelling (case-sensitive) before `pool_case` runs: two source names differing only
    in case (e.g. a param `S` in one function, `s` in another) can both survive that gather dedup and
    then collapse onto the SAME pooled spelling here — without re-deduping, `name_cf`'s positions
    (baked into every export's `name` field) drift out of sync with `NameTable`'s own collapsed
    table by one slot per such collision, corrupting every export name after it. (Found via UWeb's
    `WebRequest`/`WebConnection`, whose `S`/`s` params collide via the pool onto `S`.)"""
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        n = pool_case(raw)
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _top_level_name_order(decl: ClassDecl) -> list[str]:
    """The class's own immediate children (vars/enums/consts/structs/functions/states), in TRUE
    SOURCE order — `decl.decl_order` interleaved as written, each `VarDecl` expanded to its own
    declared names. This is the piece the compiled `.u`'s Children chain cannot recover (it bins
    properties and non-properties into separate sub-chains); see `reorder.name_creation_order`."""
    names: list[str] = []
    for item in decl.decl_order:
        if isinstance(item, VarDecl):
            names.extend(item.names)
        else:
            names.append(item.name)
    return names


def compile_package(src: str, env: InstallEnv, *,
                    order_override: tuple[list[str], list[tuple[str, str | None]],
                                          list[tuple[str, tuple[str, ...]]]] | None = None,
                    texture_files: dict[str, bytes] | None = None) -> CompiledPackage:
    """Compile UnrealScript `src` to a linked `CompiledPackage`, byte-exact vs UCC. `env` resolves the
    super's home package + CRC. `texture_files` maps a `#exec TEXTURE IMPORT FILE=` path (as written,
    case/slash-insensitive) to its PCX bytes. Ordering is autonomous: a provisional compile is decoded
    and re-emitted in UCC's real name/import/export order (`reorder.true_order` — the runtime-dumped
    global index + faithful qsort), with the class's own true top-level declaration order
    (`_top_level_name_order`, from the parsed AST) supplying the NAME-table gather order the compiled
    bytes alone can't recover. `order_override=(names, imports, export_rows)` forces a specific order
    (used by tests to pin bodies against a golden); otherwise it is derived."""
    if order_override is None:
        from .reorder import true_order
        from .serialize import serialize as _serialize
        decl = parse(src)
        provisional = _compile_single(src, env, None, texture_files)
        ordered = true_order(_serialize(provisional), [decl.name],
                             {decl.name: _top_level_name_order(decl)})
        return _compile_single(src, env, ordered, texture_files)
    return _compile_single(src, env, order_override, texture_files)


def _compile_single(src: str, env: InstallEnv,
                    order_override: tuple[list[str], list[tuple[str, str | None]],
                                          list[tuple[str, tuple[str, ...]]]] | None,
                    texture_files: dict[str, bytes] | None = None) -> CompiledPackage:
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
    class_flags, config_name, within_key = _class_header(decl, env, super_info.config_name)
    class_flags |= super_info.class_flags & _CLASS_INHERIT_MASK

    b = _Build(class_name=class_name, env=env, class_object_flags=_class_object_flags(decl),
               emit_zero_defaults=_auto_emit_defaults(decl, class_flags, substrate=env.substrate))
    b.local_enums = {m.name for m in decl.members if isinstance(m, EnumDecl)}
    b.local_structs = {m.name for m in decl.members if isinstance(m, StructDecl)}
    _seed_imports(b, super_name, within_key)
    _build_members(b, decl)
    if decl.functions or decl.states:
        _build_callables(b, decl, super_name, crlf_source)
    _build_texture_imports(b, decl, texture_files or {})
    for dep_name in b.extra_deps:
        _add_import(b, dep_name)

    has_new_kind = bool(b.enums or b.consts or b.structs or b.funcs or b.textures) or any(
        not (p.in_class_chain and p.prop_class in {k.prop_class for k in _SCALAR_KINDS.values()}
             and p.array_dim == 1) for p in b.props.values())

    default_names = {p.name for p in b.default_props} | {
        p.value for p in b.default_props if p.ptype == PT_NAME and isinstance(p.value, str)}
    names_order, imports_order, export_rows = _orders(b, class_name, super_name, config_name, decl,
                                                      default_names, has_new_kind, order_override)
    names_order = _pool_cased_dedup(names_order)           # canonical FName spelling from the pool
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

    probe_mask = super_info.probe_mask | _probe_bits(f.name for f in decl.functions)
    exports = _build_exports(b, class_name, super_name, super_info.self_crc, crlf_source,
                             class_flags, config_name, within_key, chain, chain_next,
                             name_index, nidx, name_cf, exp_ref, imp_ref, ref, export_rows,
                             probe_mask)
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


def texture_import_directives(decl: ClassDecl) -> list[texture_import.TextureImportDirective]:
    """The `#exec TEXTURE IMPORT` directives a class carries, in order. Unlike `#exec CONVERSATION
    IMPORT`, these create `UTexture`/`UPalette` exports INSIDE the compiling package."""
    return [d for directive in decl.exec_directives
           for d in [texture_import.parse_texture_import(directive)] if d is not None]


def _reject_unsupported(decl: ClassDecl) -> None:
    if decl.super_name is None:
        raise NotImplementedError(f"base class {decl.name!r} has no super — later rung")
    # `#exec CONVERSATION IMPORT` (sibling packages, `conimport.py`) and `#exec TEXTURE IMPORT`
    # (in-package `UTexture`/`UPalette`, `texture_import.py`) are supported; any OTHER `#exec` is not.
    other_exec = [d for d in decl.exec_directives
                 if _CONV_IMPORT_RE.match(d) is None and texture_import.parse_texture_import(d) is None]
    # States are supported in the single-class path (see `_build_callables`/`_build_one_state`); a
    # state's own unsupported shapes (extends/ignores/nested function overrides) raise inside
    # `lower_state_body` instead.
    for feature, present in (("replication", decl.replication),
                             ("#exec directives", other_exec),
                             ("cpptext", decl.cpptext)):
        if present:
            raise NotImplementedError(f"{feature} not supported yet (class {decl.name!r})")


def _build_texture_imports(b: _Build, decl: ClassDecl, texture_files: dict[str, bytes]) -> None:
    """Build a `_TexDef` (decoded PCX + mip chain) for each `#exec TEXTURE IMPORT` in `decl`. Only ONE
    per class is RE-verified (spike.md: "Palette1, for the first (only measured) import in a class") —
    a second is handled the same way (numbered `Palette2`, ...) but is an untested generalisation."""
    directives = texture_import_directives(decl)
    if not directives:
        return
    by_cf = {name.replace("\\", "/").casefold(): data for name, data in texture_files.items()}
    for d in directives:
        pcx_bytes = by_cf.get(d.file.replace("\\", "/").casefold())
        if pcx_bytes is None:
            raise NotImplementedError(
                f"#exec TEXTURE IMPORT: PCX file not found: {d.file!r} "
                f"(have {sorted(texture_files)}) (class {decl.name!r})")
        result = texture_import.import_texture(pcx_bytes, lodset=d.lodset)
        _add_import(b, "Texture")
        _add_import(b, "Palette")
        n = len(b.textures) + 1
        tex_key = b.okey(f"tex:{d.name}")
        b.textures[tex_key] = _TexDef(
            key=tex_key, name=d.name, palette_key=b.okey(f"palette:{d.name}"),
            palette_name=f"Palette{n}", lodset=d.lodset, result=result)


# ── class header ────────────────────────────────────────────────────────────────────────────────
def _class_header(decl: ClassDecl, env: InstallEnv, super_config_name: str = "System"
                  ) -> tuple[int, str, str]:
    """Returns (ClassFlags, ClassConfigName, ClassWithin import-object-name). Default within=Object.
    A BARE `config;` modifier (no explicit name) INHERITS the super's own ClassConfigName rather than
    resetting to `System` — live-probed (`dev/docs/spikes/2026-09-14-utserveradmin-class-ref-gaps/
    probe_config_name_inheritance.py`): real UT99 `Engine.
    MessagingSpectator`/`Engine.Spectator` are both `config(User)`-declared (`'User'`, not `'System'`),
    and a subclass with bare `config;` (e.g. real `UTServerAdminSpectator`) keeps `'User'`. A class
    with NO `config` modifier at all is left at the prior, unverified default (`"System"`) — only the
    evidenced bare-`config;` shape changes; whether ConfigName ALSO inherits with no `config` keyword
    present at all is untested, not guessed at here."""
    flags = _CLASS_FLAGS_BASE
    config_name = "System"
    within_key = "Object"
    for mod in decl.modifiers:
        head, _, arg = mod.partition("(")
        arg = arg[:-1] if arg.endswith(")") else arg
        if head == "config":
            config_name = arg or super_config_name
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


def _auto_emit_defaults(decl: ClassDecl, class_flags: int, *, substrate: str) -> bool:
    """Whether the class default block auto-materialises a tag for every own property. Measured
    against UED22: a NATIVE or TRANSIENT class serialises only the defaults explicitly written in its
    `defaultproperties` (its CDO is built in C++ / never saved); every other class also emits a
    type-zero tag for each own property it does not set. UT99's own `UCC.exe` does NOT do this at all
    (RE'd 2026-09-13, 5 minimal isolated UT99 compiles: no tag for any type, count, or presence of an
    explicit empty `defaultproperties{}` block — `dev/docs/board/done/
    ut99-ucc-never-auto-emits-type-zero/`) — a genuine difference between the two UCC.exe builds, not
    a bug in either."""
    if substrate == "ut99":
        return False
    return not (_is_native_class(decl) or bool(class_flags & CLASS_TRANSIENT))


# ── members ─────────────────────────────────────────────────────────────────────────────────────
def _build_members(b: _Build, decl: ClassDecl) -> None:
    default_values, inherited = _default_value_map(decl)
    native_class = _is_native_class(decl)
    for m in decl.members:
        match m:
            case VarDecl():
                _build_var(b, m, default_values, native_class=native_class)
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


# ── functions / states ───────────────────────────────────────────────────────────────────────────
def _build_callables(b: _Build, decl: ClassDecl, super_name: str, crlf_source: str) -> None:
    """Build every function and state, in TRUE declaration order (`decl.callables` — the two are
    split into `decl.functions`/`decl.states` elsewhere, but the class Children chain interleaves
    them by source position, so this is the one place that must walk the combined order).

    Each callable's own Context-node Dependencies (`lower_function`'s `extra_deps`) are collected
    into a PER-CALLABLE slice in this same forward walk (needed for correct bytecode/scope
    threading), then assembled into `b.extra_deps` in REVERSE callable order — UCC gathers a class's
    `Dependencies` array by walking the compiled Children chain, which prepends functions/states
    (the same reversal `_class_chain` already applies to the chain itself); within one callable the
    occurrences stay forward/textual. Measured against real UWeb (`WebConnection`/`WebResponse`,
    2026-09-13): each callable's own Context sequence matches forward, but the multi-function
    concatenation only matches gathered in reverse callable order."""
    search_dir = b.env._search_dirs[0]
    graph = b.graph_override if b.graph_override is not None else load_graph(search_dir)
    catalog = b.catalog_override if b.catalog_override is not None else load_catalog(search_dir)
    enames = enum_type_names(decl.members)
    members = members_of(decl.members, graph)
    members_meta = members_meta_of(decl.members)
    members_array_dim = members_array_dim_of(decl.members)
    lfuncs = local_funcs_of(decl.functions, graph, enames)
    enums = enums_of(decl.members)
    consts = consts_of(decl.members)
    if decl.functions:
        _add_import(b, "Function")
    if decl.states:
        _add_import(b, "State")
    func_pos = dict(zip((id(f) for f in decl.functions), _function_positions(crlf_source, decl.functions)))
    state_pos = dict(zip((id(s) for s in decl.states), _state_positions(crlf_source, decl.states)))
    dep_slices: list[list[str]] = []
    for item in decl.callables:
        if isinstance(item, StateDecl):
            line, text_pos = state_pos[id(item)]
            _build_one_state(b, decl, item, super_name, graph, catalog, members, members_meta,
                             members_array_dim, lfuncs, line, text_pos, enums, consts, dep_slices)
        else:
            line, text_pos = func_pos[id(item)]
            _build_one_function(b, decl, item, super_name, graph, catalog, members, members_meta,
                                members_array_dim, lfuncs, line, text_pos, enames, enums, consts,
                                dep_slices)
    b.extra_deps = [dep for slice_ in reversed(dep_slices) for dep in slice_]


def _build_one_state(b: _Build, decl: ClassDecl, state: StateDecl, super_name: str, graph, catalog,
                     members, members_meta, members_array_dim, lfuncs, line: int, text_pos: int,
                     enums, consts, dep_slices: list[list[str]]) -> None:
    skey = b.okey(f"state:{state.name}")
    scope = Scope(locals_={}, own_members=members, own_members_meta=members_meta,
                 own_members_array_dim=members_array_dim, own_funcs={f.name: f for f in lfuncs},
                 class_name=decl.name, super_name=super_name, graph=graph, enums=enums, consts=consts)
    own_deps: list[str] = []
    try:
        toks = lower_state_body(state, scope, catalog, extra_deps=own_deps)
    except LowerError as e:
        raise NotImplementedError(f"cannot lower state {state.name!r}: {e}") from e
    dep_slices.append(own_deps)
    _register_final_call_imports(b, toks)
    _register_member_var_imports(b, toks, _member_graph(b))
    _register_cast_class_imports(b, toks)
    b.states[skey] = _State(key=skey, name=state.name, class_key=b.okey(f"class:{decl.name}"),
                            line=line, text_pos=text_pos, toks=tuple(toks),
                            script_size=sum(_mem_size(t) for t in toks))
    b.chain_fields.append((skey, False))


def _state_positions(crlf: str, states) -> list[tuple[int, int]]:
    """(Line, TextPos) for each state's own top-level code, in `states` order: the first non-
    whitespace/comment content after the state's `{` (RE'd 2026-09-13 against UCC — every controlled
    state fixture's first item is a label, so this is verified only for that shape)."""
    out: list[tuple[int, int]] = []
    cur = 0
    ws = " \t\r\n"
    for st in states:
        namepat = r"\b" + re.escape(st.name) + r"\b"
        m = re.compile(r"\bstate\b[^{};]*?" + namepat + r"[^{};]*\{", re.IGNORECASE).search(crlf, cur)
        if m is None:
            raise NotImplementedError(f"could not locate declaration of state {st.name!r} in source "
                                      "for TextPos")
        k = m.end()
        while True:
            while k < len(crlf) and crlf[k] in ws:
                k += 1
            if crlf[k:k + 2] == "//":
                nl = crlf.find("\n", k)
                k = len(crlf) if nl < 0 else nl + 1
                continue
            if crlf[k:k + 2] == "/*":
                end = crlf.find("*/", k)
                k = len(crlf) if end < 0 else end + 2
                continue
            break
        out.append((crlf.count("\n", 0, k) + 1, k))
        cur = k
    return out


def _build_one_function(b: _Build, decl: ClassDecl, func: FuncDecl, super_name: str, graph, catalog,
                        members, members_meta, members_array_dim, lfuncs, line: int, text_pos: int,
                        enames, enums, consts, dep_slices: list[list[str]]) -> None:
    if func.kind not in ("function", "event"):
        raise NotImplementedError(f"function kind {func.kind!r} not supported yet ({func.name!r})")
    fkey = b.okey(f"fn:{func.name}")
    flags = _func_flags(func) | (FUNC_DEFINED if func.has_body else 0)  # native flag via modifier
    # An override inherits FUNC_Net (+FUNC_NetReliable) + RepOffset from the function it overrides —
    # replication is a property of the FUNCTION ITSELF (its `replication` block lives on the
    # DECLARING class), not redeclared per override. `replication` blocks in the class being compiled
    # aren't supported yet (`_reject_unsupported`), so this is the only source of FUNC_Net for now —
    # live-probed against real UT99 `UTServerAdminSpectator` (extends `Engine.MessagingSpectator`,
    # itself extending `PlayerPawn`): `ClientMessage`/`ClientVoiceMessage`/`TeamMessage`/
    # `ReceiveLocalizedMessage`, all bodyless overrides with no local `replication` block, each carry
    # the SAME FunctionFlags/RepOffset as `PlayerPawn`'s own declaration (`0x40|0x80`, i.e. a
    # `reliable` replicated function — FUNC_NetReliable always travels with FUNC_Net together).
    super_fb = graph.function(super_name, func.name) if graph else None
    rep_offset = None
    if super_fb is not None and super_fb.flags & FUNC_NET:
        flags |= super_fb.flags & (FUNC_NET | FUNC_NET_RELIABLE)
        rep_offset = super_fb.rep_offset

    child_keys: list[str] = []
    local_by_name: dict[str, str] = {}
    for p in func.params:
        pkey = _add_func_prop(b, fkey, func.name, p.name, p.type, CPF_PARM | _param_flags(func, p),
                              array_dim=p.array_dim)
        child_keys.append(pkey); local_by_name[p.name.casefold()] = pkey
    if func.return_type is not None:
        rkey = _add_func_prop(b, fkey, func.name, "ReturnValue", func.return_type, CPF_RETURN_ROLE)
        child_keys.append(rkey); local_by_name["returnvalue"] = rkey
    for vd in func.locals:
        for n in vd.names:
            lkey = _add_func_prop(b, fkey, func.name, n, vd.type, 0, array_dim=vd.array_dim)
            child_keys.append(lkey); local_by_name[n.casefold()] = lkey

    if func.has_body:
        scope = build_scope(func, members=members, members_meta=members_meta,
                            members_array_dim=members_array_dim, funcs=lfuncs,
                            class_name=decl.name, super_name=super_name, graph=graph,
                            enums=enums, enum_names=enames, consts=consts)
        own_deps: list[str] = []
        try:
            toks = lower_function(func, scope, catalog, extra_deps=own_deps)
        except LowerError as e:
            raise NotImplementedError(f"cannot lower function {func.name!r}: {e}") from e
        dep_slices.append(own_deps)
    elif flags & FUNC_NATIVE:                        # native thunk: one NativeParm per param
        toks = [Tok(EX_NATIVE_PARM, (("obj", p.name),)) for p in func.params]
    else:                                            # non-native body-less decl (`function Foo();`,
        # meant to be overridden) compiles as an EMPTY body — same trailing Return(Nothing)
        # `lower_function` appends after a real (possibly empty) `{}` body; measured against a live
        # UCC build of `WebApplication.Init/Cleanup/Query` (UWeb), all three bodyless and non-native.
        toks = [Tok(EX_RETURN, (("sub", Tok(EX_NOTHING)),))]

    _register_struct_member_imports(b, toks, _member_graph(b))
    _register_final_call_imports(b, toks)
    _register_member_var_imports(b, toks, _member_graph(b))
    _register_cast_class_imports(b, toks)

    b.funcs[fkey] = _Func(key=fkey, name=func.name, class_key=b.okey(f"class:{decl.name}"),
                          line=line, text_pos=text_pos,
                          function_flags=flags, child_keys=tuple(child_keys),
                          local_by_name=local_by_name, toks=tuple(toks),
                          script_size=sum(_mem_size(t) for t in toks),
                          super_ref_key=_super_func_import(b, super_name, func.name, graph),
                          rep_offset=rep_offset)
    b.chain_fields.append((fkey, False))


def _super_func_import(b: _Build, super_name: str, func_name: str, graph) -> str | None:
    """If this function overrides one inherited from the super chain, return the overridden UFunction's
    identity key (`func:<Class>.<Name>`) for the overriding function's `SuperField`; otherwise None
    (SuperField 0). When the declaring class is a SAME-PACKAGE ancestor (multi-class compile), no
    import is registered — the consumer resolves this key to that class's own export instead (see
    `_sibling_export_ref`), same as `_register_final_call_imports` does for an ordinary inherited
    call. Otherwise registers an import of the parent UFunction (Class=Function, Outer=its declaring
    class), as before."""
    fb = graph.function(super_name, func_name) if graph is not None else None
    if fb is None:
        return None
    key = f"func:{fb.class_name}.{fb.name}"
    if fb.class_name.casefold() in b.in_pkg_class_names:
        return key
    _add_import(b, fb.class_name)                         # ensure the declaring class is imported
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


def _add_func_prop(b: _Build, fkey: str, func_name: str, pname: str, type_ref, role_flags: int,
                   *, array_dim: int | str | None = None) -> str:
    """One param/return/local UProperty of a function (Outer = the function). `role_flags` is the
    CPF role: CPF_PARM for a param, CPF_RETURN_ROLE for ReturnValue, 0 for a local. `array_dim` is a
    static-array size, e.g. `byte B[255]` (rare; a param's is usually dropped by the parser — see
    `Param.array_dim`/`_dim_value` — measured against UWeb's `WebResponse.SendBinary`)."""
    prop_class, base_flags, tail = _func_prop_type(b, type_ref, func_name, pname)
    key = b.okey(f"fprop:{func_name}.{pname}")
    b.props[key] = _Prop(key=key, name=pname, prop_class=prop_class, outer_key=fkey,
                         array_dim=_dim_value(array_dim),
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
        _add_import(b, "Class")
        return "ClassProperty", 0, (_RefSpec(key="Class", is_export=False),
                                    _class_meta_ref(b, tr.meta_class or "Object"))
    graph = _member_graph(b)                              # a built-in/cross-package struct (Vector, …)
    if graph.is_struct_name(base):
        skey = _add_struct_import(b, graph, base)
        return "StructProperty", 0, (_RefSpec(key=skey, is_export=False),)
    if base.casefold() in b.in_pkg_class_names:           # a same-package sibling class -> export ref
        real = b.in_pkg_class_names[base.casefold()]
        return "ObjectProperty", 0, (_RefSpec(key=f"{real}::class:{real}", is_export=True),)
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


def _build_var(b: _Build, m: VarDecl, default_values: dict, *, native_class: bool) -> None:
    flags = 0
    category_name: str | None = None
    if m.category is not None:                        # var() or var(Cat) → editable
        flags |= CPF_EDIT
        category_name = m.category if m.category else b.class_name
    for mod in m.modifiers:
        if mod not in _VAR_MODIFIER_FLAGS:
            raise NotImplementedError(f"var modifier {mod!r} not supported (var {m.names[0]!r})")
        bit = _VAR_MODIFIER_FLAGS[mod]
        # CPF_Native persists only on a var of a NATIVE class — measured live: the same `native`/
        # `intrinsic` var modifier on a non-native class carries NO CPF bit (a plain class's CDO is
        # Python-serialised, so there's no C++ struct field for the engine to mark). WebRequest
        # (native) vs a controlled non-native counterpart, 2026-09-13, `CPFNativeProbe` fixture.
        if bit == CPF_NATIVE and not native_class:
            continue
        flags |= bit
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
    graph = _member_graph(b)                              # a built-in/cross-package struct (Vector,
    if graph.is_struct_name(base):                         # IpAddr, …) — same shape as
        skey = _add_struct_import(b, graph, base)           # `_func_prop_type`/`_resolve_array_type`
        return ("StructProperty", 0, (_RefSpec(key=skey, is_export=False),), PT_STRUCT, skey)
    if base.casefold() == "class":
        _add_import(b, "Class")
        return ("ClassProperty", 0, (_RefSpec(key="Class", is_export=False),
                                     _class_meta_ref(b, m.type.meta_class or "Object")), PT_OBJECT, None)
    if base.casefold() == "array":
        return _resolve_array_type(b, m, pname)
    if base.casefold() in b.in_pkg_class_names:           # a SIBLING class in this same package (own
        real = b.in_pkg_class_names[base.casefold()]       # or mutually referenced) -> an export ref,
        return ("ObjectProperty", 0,                        # never an import (it has no home package
               (_RefSpec(key=f"{real}::class:{real}", is_export=True),), PT_OBJECT, None)  # of its own)
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
    elif base.casefold() in b.in_pkg_class_names:        # a same-package sibling class -> export ref
        real = b.in_pkg_class_names[base.casefold()]
        inner_class = "ObjectProperty"
        inner_tail = (_RefSpec(key=f"{real}::class:{real}", is_export=True),)
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


def _dim_value(array_dim: int | str | None) -> int:
    if array_dim is None:
        return 1
    if isinstance(array_dim, int):
        return array_dim
    raise NotImplementedError(f"const-named static array size {array_dim!r} not supported yet")


def _static_dim(m: VarDecl) -> int:
    return _dim_value(m.array_dim)


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
    order = _super_field_order(b, graph, decl.super_name)
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


def _super_field_order(b: _Build, graph: ClassGraph, super_name: str) -> list[tuple[str, str]]:
    """Inherited fields in class field-iteration order — the super's own properties first (Children
    order), then its ancestors', up the chain. A same-package super (`b.in_pkg_decls`) has no compiled
    export yet to decode field order from — its own properties resolve from its AST instead
    (`members_of`, forward declaration order; only non-var chain fields ever reverse, so this needs no
    chain-reversal logic). Disk-backed ancestors keep decoding compiled bytes."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    name: str | None = super_name
    for _ in range(64):
        if name is None:
            break
        decl = b.in_pkg_decls.get(name.casefold())
        if decl is not None:
            for n, label in members_of(decl.members, graph).items():
                cf = n.casefold()
                if cf not in seen:
                    seen.add(cf)
                    out.append((cf, label))
            name = decl.super_name
            continue
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
    if ptype == PT_POINTER:
        raise NotImplementedError(f"pointer property {pname!r}: default-value emission not supported "
                                  "(no UnrealScript literal for a pointer; expected only on native "
                                  "classes, which skip unset defaults)")
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
        # An explicit `Foo=None` is the SAME zero-object tag an unset property gets — resolved via
        # `_object_default_ref` (already handles `noneconst` -> 0, and a genuine `Class'X'`/object
        # literal -> a deferred ref; anything else still raises there).
        expr = values.get((pname, None), values.get((pname, 0)))
        value = _object_default_ref(b, pname, expr) if expr is not None else 0
        b.default_props.append(Prop(pname, PT_OBJECT, value))
        return
    for idx in range(array_dim):
        arr_idx = None if array_dim == 1 else idx
        expr = values.get((pname, idx)) or (values.get((pname, None)) if array_dim == 1 else None)
        is_enum_default = ptype == PT_BYTE and expr is not None and expr.op == "name"
        if is_enum_default:
            value = _byte_enum_ordinal(b, pname, expr)   # an enum-constant default → its ordinal byte
        else:
            value = _scalar_default(pname, ptype, expr)
        # `emit_zero_defaults=False` (UT99): no tag for a type-zero value, whether the property was
        # left unset OR explicitly assigned its own zero -- probed live against UT99 UCC (the real
        # `ASPMutator`'s `bDebugMode=False` gets no defaultproperties tag, while its sibling
        # `bEnabled=True`/`bAdvancedSpawns=True`/`bSafeSpawns=True` on the SAME multi-name `var`
        # declaration all do) -- an explicit zero write is indistinguishable from never setting it.
        # Only measured for a plain scalar; an explicit enum-constant default (`is_enum_default`)
        # whose ordinal happens to be 0 is never suppressed, matching prior (unmeasured-but-never-
        # wrong) behavior -- see `dev/docs/board/inbox/` for the open question.
        if not b.emit_zero_defaults and not is_enum_default and value == _SCALAR_ZERO[ptype]:
            continue
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


def _class_meta_ref(b: _Build, meta: str) -> _RefSpec:
    """A `class<Meta>` property's meta-class type-tail ref: a same-package sibling's own class export
    (`f"{real}::class:{real}"`, same identity a same-package `var Meta x` property already resolves to
    — see `_resolve_var_type`), an IMPORT otherwise."""
    if meta.casefold() in b.in_pkg_class_names:
        real = b.in_pkg_class_names[meta.casefold()]
        return _RefSpec(key=f"{real}::class:{real}", is_export=True)
    return _RefSpec(key=_add_import(b, meta), is_export=False)


def _extra_dep_crc(env: InstallEnv, dep: str) -> int:
    """The `script_text_crc` for an extra (deep=0) `Dependency` entry. `Class` (the metaclass a
    `class'X'` literal's own type is -- see `lower._record_dep`) is a bootstrap Core type with no
    `ScriptText` to CRC and no `.u` export `resolve_class` can find; real UCC's own Dependency entry
    for it carries CRC 0 (live-probed against UED22 UCC, `class'X'.default.Field` access)."""
    if dep.casefold() == "class":
        return 0
    return env.resolve_class(dep).self_crc


def _add_import(b: _Build, obj: str) -> str:
    """Ensure `obj` (a class or the Core package) is imported; return its import key (object name).
    A Core class imports with outer=Core; a class in another package pulls in that package import
    (not into `PackageImports` — see `_build_class_unit`'s `package_imports` comment). A class with
    NO exported script body anywhere on the search path (a fully-native class, e.g. UT99's
    `Engine.NetConnection` — see `env.class_home_from_imports`) falls back to its home package as
    discovered from another package's own IMPORT table, rather than defaulting to Core."""
    if obj == "Core":
        return obj
    existing = obj if obj in b.imports else next(       # FName is case-insensitive: `texture` (a member
        (k for k in b.imports if k.casefold() == obj.casefold()), None)  # type) dedupes onto `Texture`
    if existing is not None:
        return existing
    info = b.env.resolve_class(obj)
    pkg = info.package if info is not None else b.env.import_only_class_package(obj)
    if pkg is None or pkg.casefold() == "core":
        b.imports[obj] = _ImportSpec(class_package="Core", class_name="Class", outer="Core",
                                     object_name=obj)
        return obj
    if pkg not in b.imports:
        b.imports[pkg] = _ImportSpec(class_package="Core", class_name="Package", outer=None,
                                     object_name=pkg)
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


def _existing_import_key(b: _Build, ident: str) -> str | None:
    """The existing `b.imports` key matching `ident` case-insensitively (FName identity), or None.
    Two SOURCE occurrences of the same inherited field/function/struct member differing only in case
    (real UT99 `UTServerAdmin`: `GameReplicationInfo.MOTDLine1` vs `.MOTDline1`) must dedupe onto ONE
    import row — the same rule `_add_import` already applies to a plain class/package name. Without
    this, two b.imports entries end up representing the "same" identity, and whichever one
    `_imports_by_display`'s ambiguous-name tie-break keeps can differ from the one a token's own
    (differently-cased) `resolve_inv` lookup expects, a silent `KeyError` at encode time."""
    return ident if ident in b.imports else next(
        (k for k in b.imports if k.casefold() == ident.casefold()), None)


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


def _add_struct_member_import(b: _Build, graph: ClassGraph, ident: str, struct_name: str,
                              field: str) -> None:
    """Import a struct member property (e.g. `Core.Object.Vector.X`, a FloatProperty), referenced by a
    `StructMember` (0x36) bytecode token. Outer = the struct import. Keyed by the qualified
    `smem:<Struct>.<Field>` ident (`lower._struct_member_ident`), never the bare field name — a bare
    key would let `resolve_inv`'s local/param lookup shadow it (a param sharing the field's name, e.g.
    real UT99 `IpAddr`'s own `Addr` field vs a param also named `Addr`). Dedupes case-insensitively
    (`_existing_import_key`) — two occurrences differing only in case are the SAME struct member."""
    if _existing_import_key(b, ident) is not None:
        return
    skey = _add_struct_import(b, graph, struct_name)
    label = graph.struct_member_type(struct_name, field)
    if label is None or label not in _SCALAR_KINDS:
        raise NotImplementedError(f"struct member {struct_name}.{field}: type {label!r} unsupported")
    prop_class = _SCALAR_KINDS[label].prop_class
    b.imports[ident] = _ImportSpec(class_package="Core", class_name=prop_class,
                                   outer=skey, object_name=field)


def _register_struct_member_imports(b: _Build, toks, graph: ClassGraph) -> None:
    """After lowering, create an import for every struct member a `StructMember` token references.
    `lower.py` tags the token's field identity `smem:<Struct>.<Field>` directly — the owning struct is
    already known at lowering time (`lower._ex_member` has the base expression's resolved type), so
    unlike the qualifier-stripped `func:`/`mem:` idents this needs no post-hoc re-derivation from the
    base sub-expression."""
    def walk(t) -> None:
        if t.op == 0x36:
            ident = next((v for k, v in t.parts if k == "obj"), None)
            if ident is not None and ident.startswith("smem:"):
                struct_name, field = ident[len("smem:"):].rsplit(".", 1)
                _add_struct_member_import(b, graph, ident, struct_name, field)
        for kind, val in t.parts:
            if kind == "sub":
                walk(val)
            elif kind == "parms":
                for s in val:
                    walk(s)

    for t in toks:
        walk(t)


def _register_final_call_imports(b: _Build, toks) -> None:
    """After lowering, import the target of every INHERITED final-function call (an ordinary call to a
    function the class being compiled doesn't itself declare/override, and a `super.Foo()` call, which
    always targets an ancestor) OR a final call through an object typed to a same-package SIBLING
    class. `lower.py` marks such a call's obj identity `func:<Class>.<Name>` (never a bare identifier,
    which is reserved for the class's own function, resolved as a same-package export) — the same key
    format `_super_func_import` uses for an override's SuperField, so the two mechanisms dedupe onto
    one import when both name the same inherited function. When `<Class>` is one of THIS package's own
    classes (own super OR a sibling — including one referenced MUTUALLY, see `_prepass_signatures`),
    no import is registered at all: `_multi_function_exports`'s resolver resolves the identity straight
    to that class's own function export instead."""
    def walk(t) -> None:
        if t.op == EX_FINAL_FUNCTION:
            ident = next((v for k, v in t.parts if k == "obj"), None)
            if ident is not None and ident.startswith("func:") and _existing_import_key(b, ident) is None:
                owner_cls, func_name = ident[len("func:"):].rsplit(".", 1)
                if owner_cls.casefold() not in b.in_pkg_class_names:
                    outer = _add_import(b, owner_cls)
                    b.imports[ident] = _ImportSpec(class_package="Core", class_name="Function",
                                                   outer=outer, object_name=func_name)
        for kind, val in t.parts:
            if kind == "sub":
                walk(val)
            elif kind == "parms":
                for s in val:
                    walk(s)

    for t in toks:
        walk(t)


def _member_import_prop_class(label: str | None) -> str | None:
    """The UProperty subclass to import an inherited member AS — an import table row only names the
    field's identity (class_package/class_name/outer/object_name), never its type-tail (that lives on
    the DECLARING class's own export, which this package doesn't touch), so any type down to its
    UProperty subclass is enough. Scalars use `_SCALAR_KINDS`; object/class/struct labels
    (`natives.prop_type_label`) map straight to their UProperty subclass. `None` for an unsupported
    label (currently just `array`, whose element type an import row cannot express)."""
    if label in _SCALAR_KINDS:
        return _SCALAR_KINDS[label].prop_class
    if label is not None and label.startswith("object:"):
        return "ObjectProperty"
    if label == "class":
        return "ClassProperty"
    if label is not None and label.startswith("struct:"):
        return "StructProperty"
    return None


def _register_member_var_imports(b: _Build, toks, graph: ClassGraph) -> None:
    """After lowering, import the target of every INHERITED instance-variable access (a member field
    the class being compiled doesn't itself declare/override), one reached through an object typed
    to a same-package SIBLING class, or a `class'X'.default.Field` read (`EX_DEFAULT_VARIABLE`, the
    SAME identity/import shape, `lower._ex_member`'s "`.default`" branch). `lower.py` marks such an
    access's obj identity `mem:<Class>.<Name>` (never a bare identifier, reserved for the class's own
    field, resolved as a same-package export) — same shape as `_register_final_call_imports`, but a
    Property import (the field's concrete UProperty subclass, e.g. IntProperty) rather than a
    Function import. When `<Class>` is one of THIS package's own classes, no import is registered —
    see `_register_final_call_imports`. Dedupes case-insensitively (`_existing_import_key`): real UT99
    `UTServerAdmin` reads `GameReplicationInfo.MOTDLine1` in one place and writes `.MOTDline1` in
    another — the SAME field, case-insensitive `FName`, one import row."""
    def walk(t) -> None:
        if t.op in (EX_INSTANCE_VARIABLE, EX_DEFAULT_VARIABLE):
            ident = next((v for k, v in t.parts if k == "obj"), None)
            if ident is not None and ident.startswith("mem:") and _existing_import_key(b, ident) is None:
                owner_cls, field = ident[len("mem:"):].rsplit(".", 1)
                if owner_cls.casefold() not in b.in_pkg_class_names:
                    label = graph.member_type(owner_cls, field)
                    prop_class = _member_import_prop_class(label)
                    if prop_class is None:
                        raise NotImplementedError(
                            f"inherited member {owner_cls}.{field}: type {label!r} unsupported")
                    outer = _add_import(b, owner_cls)
                    b.imports[ident] = _ImportSpec(class_package="Core", class_name=prop_class,
                                                   outer=outer, object_name=field)
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
    palette_keys = {t.palette_key for t in b.textures.values()}

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
        if key in b.textures:
            return "Texture"
        if key in palette_keys:
            return "Palette"
        return "Function"

    objs: list[ObjInput] = []
    creation = _creation_order(b, class_name)
    for key in creation:
        nrefs, orefs = _obj_streams(b, class_name, super_name, config_name, key)
        objs.append(ObjInput(name=key, class_name=class_of(key), outer=ident[key][1],
                             in_package=True, name_refs=nrefs, obj_refs=orefs))
    for objname, spec in b.imports.items():
        objs.append(ObjInput(name=objname, class_name=spec.class_name, outer=spec.outer,
                             display=spec.object_name, in_package=False))

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
    for key, s in b.states.items():
        out[key] = (s.name, class_name)
    for t in b.textures.values():
        out[t.key] = (t.name, None)                       # Outer=0: a top-level package object
        out[t.palette_key] = (t.palette_name, None)
    return out


def _creation_order(b: _Build, class_name: str) -> list[str]:
    """A deterministic parse-order key list covering every export exactly once: class, ScriptText,
    then each class-Children field in declaration order — a function/struct immediately followed by
    its child properties — then any array-inner property left over, then any `#exec TEXTURE IMPORT`
    (its Palette then its Texture — processed after the whole class body, like `#exec CONVERSATION
    IMPORT`'s own late defaultproperties-style registration)."""
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
    for t in b.textures.values():
        add(t.palette_key)
        add(t.key)
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
    if key in b.states:
        s = b.states[key]
        nrefs, orefs = _token_refs(s.toks)
        return (s.name, *nrefs), orefs
    for t in b.textures.values():
        if key == t.palette_key:                          # empty tag list + a raw TArray<FColor>
            return (), ()
        if key == t.key:
            return tuple(_texture_prop_names(t)), (t.palette_key,)
    f = b.funcs[key]
    nrefs, orefs = _token_refs(f.toks)
    return (f.name, *nrefs), orefs


def _texture_prop_names(t: _TexDef) -> list[str]:
    """Every NAME the UTexture body's tagged-property list references, in body-write order (each
    STRUCT tag also references its struct type name "Color") — feeds both `order_package`'s
    reference-count gather (`_obj_streams`) and name-table membership (`_general_names`)."""
    names = ["LODSet", "Palette", "UBits", "VBits", "USize", "VSize", "UClamp", "VClamp"]
    r = t.result
    if r.mip_zero != (0, 0, 0):
        names += ["MipZero", "Color"]
    if r.max_color != texture_import.MAX_COLOR_DEFAULT:
        names += ["MaxColor", "Color"]
    names.append("InternalTime")
    return names


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
    for s in b.states.values():
        add(s.name)
        for ident in _token_refs(s.toks)[0]:
            add(ident)
    for t in b.textures.values():
        add(t.name)
        add(t.palette_name)
        for ident in _texture_prop_names(t):
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
                             display=spec.object_name, in_package=False))
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
    for s in b.states.values():
        add(s.name, class_name, s.key)
    for t in b.textures.values():
        add(t.name, None, t.key)
        add(t.palette_name, None, t.palette_key)

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
                   export_rows, probe_mask):
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
    _build_state_exports(b, class_key, next_lookup, nidx, name_cf, exp_ref, imp_ref, recs)
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

    _build_texture_exports(b, name_index, exp_ref, imp_ref, ref, recs)
    recs[class_key] = _class_export(b, class_name, super_name, super_crc, crlf_source, class_flags,
                                    config_name, within_key, chain, name_index, exp_ref, imp_ref, ref,
                                    probe_mask)
    return tuple(recs[key] for key, _ in sorted(exp_ref.items(), key=lambda kv: kv[1]))


def _build_texture_exports(b: _Build, name_index, exp_ref, imp_ref, ref, recs: dict[str, Export]
                           ) -> None:
    """Emit the `UPalette` + `UTexture` export pair for each `#exec TEXTURE IMPORT` (`_TexDef`), per
    the body layout `texture_import.py`/`compile-model.md` document."""
    for t in b.textures.values():
        r = t.result
        recs[t.palette_key] = Export(
            cls=imp_ref["Palette"], super_ref=0, outer=0, name=name_index[t.palette_name],
            flags=_RF_PALETTE_OBJ,
            body=ObjectBody(props=write_props(lambda s: name_index[s], []),
                            trailer=texture_import.palette_trailer_bytes(r.palette)))
        props: list[Prop] = [
            Prop("LODSet", PT_BYTE, t.lodset),
            Prop("Palette", PT_OBJECT, _RefSpec(key=t.palette_key, is_export=True)),
            Prop("UBits", PT_BYTE, r.ubits), Prop("VBits", PT_BYTE, r.vbits),
            Prop("USize", PT_INT, r.usize), Prop("VSize", PT_INT, r.vsize),
            Prop("UClamp", PT_INT, r.usize), Prop("VClamp", PT_INT, r.vsize),
        ]
        if r.mip_zero != (0, 0, 0):
            props.append(Prop("MipZero", PT_STRUCT, bytes((*r.mip_zero, 0)), struct_name="Color"))
        if r.max_color != texture_import.MAX_COLOR_DEFAULT:
            props.append(Prop("MaxColor", PT_STRUCT, bytes((*r.max_color, 255)), struct_name="Color"))
        # InternalTime[2]: per-compile-random (excluded from the strict gate, `gate.py`) — values are
        # placeholders, only the tag SHAPE (a 2-element int static array) needs to be right.
        props.append(Prop("InternalTime", PT_INT, 0))
        props.append(Prop("InternalTime", PT_INT, 0, array_index=1))
        props_bytes = write_props(lambda s: name_index[s], _resolve_default_refs(props, ref))
        mips = tuple(TextureMip(width=m.width, height=m.height, data=m.indices) for m in r.mips)
        recs[t.key] = Export(cls=imp_ref["Texture"], super_ref=0, outer=0, name=name_index[t.name],
                             flags=_RF_TEXTURE_OBJ, body=TextureBody(props=props_bytes, mips=mips))


def _build_function_exports(b, class_key, next_lookup, nidx, name_cf, exp_ref, imp_ref, recs) -> None:
    """Emit one UFunction export per function, encoding its script against the final tables. A script
    obj ref is a local/param/return of THIS function, a class member var, an own function, or an
    imported class/function; a name ref is a name-table index."""
    member_by_name = {p.name.casefold(): key for key, p in b.props.items()
                      if p.in_class_chain and p.is_var}
    func_by_name = {f.name.casefold(): f.key for f in b.funcs.values()}
    import_by_name = {k.casefold(): k for k in b.imports}
    texture_by_name = {t.name.casefold(): t.key for t in b.textures.values()}

    def resolver(fn):
        def resolve_inv(kind: str, ident: str) -> int:
            if kind == "name":
                return name_cf[ident.casefold()]
            if ident.startswith("class:"):                # a cast/class-literal target: see
                return imp_ref[import_by_name[ident[len("class:"):].casefold()]]  # `_sibling_export_ref`
            cf = ident.casefold()
            if cf in fn.local_by_name:
                return exp_ref[fn.local_by_name[cf]]
            if cf in member_by_name:
                return exp_ref[member_by_name[cf]]
            if cf in func_by_name:
                return exp_ref[func_by_name[cf]]
            if cf in texture_by_name:                     # a same-package `Texture'Pkg.Name'` literal
                return exp_ref[texture_by_name[cf]]
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
                inative=0, oper_precedence=0, function_flags=fn.function_flags,
                rep_offset=fn.rep_offset))


def _build_state_exports(b, class_key, next_lookup, nidx, name_cf, exp_ref, imp_ref, recs) -> None:
    """Emit one UState export per state, encoding its script against the final tables (same resolver
    shape as `_build_function_exports` — a state has no params/locals of its own). The `EX_LabelTable`
    token (if any) sits inside `st.toks` already (`lower_state_body`); `StateBody.label_table_offset`
    is its in-MEMORY offset + 1 (see `model.StateBody`), needing no resolver to compute."""
    member_by_name = {p.name.casefold(): key for key, p in b.props.items()
                      if p.in_class_chain and p.is_var}
    func_by_name = {f.name.casefold(): f.key for f in b.funcs.values()}
    import_by_name = {k.casefold(): k for k in b.imports}
    texture_by_name = {t.name.casefold(): t.key for t in b.textures.values()}

    def resolve_inv(kind: str, ident: str) -> int:
        if kind == "name":
            return name_cf[ident.casefold()]
        if ident.startswith("class:"):                    # a cast/class-literal target: see
            return imp_ref[import_by_name[ident[len("class:"):].casefold()]]  # `_sibling_export_ref`
        cf = ident.casefold()
        if cf in member_by_name:
            return exp_ref[member_by_name[cf]]
        if cf in func_by_name:
            return exp_ref[func_by_name[cf]]
        if cf in texture_by_name:
            return exp_ref[texture_by_name[cf]]
        if cf in import_by_name:
            return imp_ref[import_by_name[cf]]
        raise NotImplementedError(f"cannot resolve script ref {ident!r} in a state")

    for skey, st in b.states.items():
        has_table = bool(st.toks) and st.toks[-1].op == EX_LABEL_TABLE
        label_table_offset = (sum(_mem_size(t) for t in st.toks[:-1]) + 1) if has_table else 0xFFFF
        recs[skey] = Export(
            cls=imp_ref["State"], super_ref=0, outer=exp_ref[class_key], name=nidx(st.name),
            flags=_RF_FIELD,
            body=StateBody(
                super_field=0, next_field=next_lookup.get(skey, 0), children=0,
                friendly_name=nidx(st.name), line=st.line, text_pos=st.text_pos,
                script=encode_script(list(st.toks), resolve_inv), script_size=st.script_size,
                probe_mask=0, ignore_mask=0xFFFFFFFFFFFFFFFF,
                label_table_offset=label_table_offset, state_flags=0))


def _class_export(b, class_name, super_name, super_crc, crlf_source, class_flags, config_name,
                  within_key, chain, name_index, exp_ref, imp_ref, ref, probe_mask):
    children = exp_ref[chain[0]] if chain else 0
    return Export(
        cls=0, super_ref=imp_ref[super_name], outer=0, name=name_index[class_name],
        flags=b.class_object_flags,
        body=ClassBody(
            super_field=imp_ref[super_name], next_field=0, script_text=exp_ref["ScriptText"],
            children=children, friendly_name=name_index[class_name],
            line=0xFFFFFFFF, text_pos=0xFFFFFFFF, script=b"",
            probe_mask=probe_mask, ignore_mask=0xFFFFFFFFFFFFFFFF, label_table_offset=0xFFFF,
            state_flags=0, class_flags=class_flags, class_guid=b"\x00" * 16,
            dependencies=(Dependency(cls=exp_ref[f"class:{class_name}"], deep=1,
                                     script_text_crc=script_text_crc(crlf_source)),
                          Dependency(cls=imp_ref[super_name], deep=1, script_text_crc=super_crc),
                          *(Dependency(cls=exp_ref[f"class:{class_name}"], deep=0,
                                      script_text_crc=script_text_crc(crlf_source))
                            if dep.casefold() == class_name.casefold() else
                            Dependency(cls=imp_ref[_add_import(b, dep)], deep=0,
                                      script_text_crc=_extra_dep_crc(b.env, dep))
                            for dep in b.extra_deps)),
            package_imports=(name_index[class_name], name_index["Core"]),
            class_within=imp_ref[within_key], class_config_name=name_index[config_name],
            default_props=write_props(lambda s: name_index[s],
                                      _resolve_default_refs(b.default_props, ref))))


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────
def _skip_defaultproperties_block(source: str, start: int) -> int:
    """Return the index right after the `}` that closes the `defaultproperties {...}` block whose
    keyword ends at `start`. Mirrors the real lexer's own skipping (`lexer.py` `_skip_line_comment`/
    `_skip_block_comment`/`_scan_string`/`_scan_name`) over the WHOLE scan -- including locating the
    opening `{` itself -- so a brace inside a `//`/`/* */` comment, a `"..."` string, or a `'...'`
    name literal never perturbs the depth count."""
    n = len(source)
    i, depth = start, 0
    while i < n:
        two = source[i:i + 2]
        if two == "//":
            nl = source.find("\n", i)
            i = n if nl == -1 else nl
            continue
        if two == "/*":
            cdepth, i = 1, i + 2
            while i < n and cdepth > 0:
                pair = source[i:i + 2]
                if pair == "/*":
                    cdepth += 1; i += 2
                elif pair == "*/":
                    cdepth -= 1; i += 2
                else:
                    i += 1
            continue
        c = source[i]
        if c == '"':
            i += 1
            while i < n and source[i] not in ('"', "\n"):
                if source[i] == "\\" and i + 1 < n and source[i + 1] != "\n":
                    i += 2
                else:
                    break
            i += 1
            continue
        if c == "'":
            i += 1
            while i < n and source[i] not in ("'", "\n"):
                i += 1
            i += 1
            continue
        if c == "{":
            depth += 1; i += 1
            continue
        if c == "}":
            depth -= 1; i += 1
            if depth == 0:
                return i
            continue
        i += 1
    raise NotImplementedError("unterminated defaultproperties block")


def _script_text(source: str) -> str:
    """The text UCC stores in `ScriptText`: the class source with the `defaultproperties {...}`
    block EXCISED (not merely truncated there) — declarations after it (a shape real source puts
    `defaultproperties` mid-file, before later functions, e.g. the real UT99 mutator
    `CrouchBlocksDamage`) still compile and their own Line/TextPos are measured against this SAME
    excised stream, confirmed byte-exact against a live UT99 UCC build: the block (keyword through
    its matching `}`) plus exactly one immediate trailing line terminator is removed as one unit,
    everything before and after stays untouched (no line-count "holdover" — text following the
    block is renumbered as if the block had never been there). With NO `defaultproperties` block,
    or nothing left after excising the one it has, UCC's own capture always ends with exactly ONE
    line terminator after the last real line, regardless of how many (including zero) the source
    file itself ends with — measured on two community shapes: `NoGunsMutator` (a trailing blank
    line, collapsed to one) and the real UT99 mutator `SeanMutator`'s `HelloMut.uc` (no trailing
    newline at all, one added)."""
    m = re.search(r"(?im)^[ \t]*defaultproperties\b", source)
    if m:
        close = _skip_defaultproperties_block(source, m.end())
        tail = close
        while tail < len(source) and source[tail] in " \t":
            tail += 1
        tail = tail + 2 if source[tail:tail + 2] == "\r\n" \
            else tail + 1 if source[tail:tail + 1] in ("\n", "\r") else close
        before, after = source[:m.start()], source[tail:]
        if after.strip() == "":
            return before   # defaultproperties was the last real content -- `before` needs no
                            # further normalisation, it already ends at a real source line's newline
        source = after     # real declarations follow -- normalise only THIS tail's own trailing
                            # blank line(s)/EOF the same way the no-block branch below does, then
                            # reattach `before` untouched (the seam itself is never collapsed)
    else:
        before = ""
    lines = source.splitlines()
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        return source   # no real content -- pathological, leave untouched rather than guess (only
                        # reachable via the no-defaultproperties path -- `before` is always "" there)
    return before + "\n".join(lines) + "\n"


def _to_crlf(text: str) -> str:
    """Normalise every lone `\\n` and `\\r\\n` to `\\r\\n` (the form UCC stores in `ScriptText`)."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


# ══ multi-class package compile (compile_package_dir) ═════════════════════════════════════════════
# Build a WHOLE package (many `.uc` -> one `.u`) with shared name/import/export tables. Like the
# single-class path, the final pass re-emits in UCC's real order via `reorder.true_order` (below) —
# this is NOT merely a stable "creation order". `perm_gate` remains the test suite's own bar for this
# path (order/case-tolerant), since a multi-class package hasn't had the same per-fixture scrutiny as
# the single-class corpus, not because the ordering here is architecturally weaker.

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
    probe_mask: int                   # accumulated EProbe bits (super's | this class's own overrides)
    extra_deps: tuple[str, ...]       # classes Context'd into (deep=0 Dependency entries), real-cased
    texture_keys: tuple[str, ...] = ()  # this class's own `#exec TEXTURE IMPORT` UTexture export keys


def _prepass_signatures(decls: dict[str, tuple[ClassDecl, str]], disk_graph: ClassGraph | None
                        ) -> dict[str, ClassSig]:
    """Pass 1 of the two-pass package compile: a `ClassSig` (own + inherited members/functions) for
    EVERY class in the package, built straight from its AST — no bytecode needed, since UnrealScript
    var/param/return types are explicit in source. Keyed by casefolded class name.

    This is what makes a MUTUAL same-package reference (class A calls into B, B calls into A) work:
    without it, resolving A's call into B needs B already built (its signature decoded from compiled
    bytes), and resolving B's call into A needs A already built — no build order satisfies both. Here
    every class's signature exists before any class's BYTECODE BODY is lowered, so lowering (pass 2,
    `compile_package_dir`'s loop) can resolve a call/member access into any sibling class regardless
    of which one is being compiled first. Only INHERITANCE needs a fixed order within this pass (a
    subclass's signature merges its super's) — safe, since class inheritance can't cycle in valid
    UnrealScript; resolved here by recursing into `sig_of`, memoized, with a cycle guard that raises
    rather than infinite-loop if that invariant is ever violated."""
    by_cf = {name.casefold(): name for name in decls}
    sigs: dict[str, ClassSig] = {}
    building: set[str] = set()

    def sig_of(name: str) -> ClassSig | None:
        cf = name.casefold()
        if cf in sigs:
            return sigs[cf]
        if cf not in by_cf:                               # a cross-package super/type
            return disk_graph.class_sig(name) if disk_graph is not None else None
        if cf in building:
            raise NotImplementedError(f"cyclic class inheritance involving {name!r}")
        building.add(cf)
        decl, _src = decls[by_cf[cf]]
        members: dict[str, str] = {}
        member_owner: dict[str, str] = {}
        member_meta: dict[str, str] = {}
        member_array_dim: dict[str, int] = {}
        functions: dict[str, FuncBody] = {}
        if decl.super_name:
            sup = sig_of(decl.super_name)
            if sup is not None:
                members.update(sup.members)
                member_owner.update(sup.member_owner)
                member_meta.update(sup.member_meta)
                member_array_dim.update(sup.member_array_dim)
                functions.update(sup.functions)
        enames = enum_type_names(decl.members)
        for n, label in members_of(decl.members, disk_graph).items():
            ncf = n.casefold()
            members[ncf] = label
            member_owner[ncf] = decl.name
        member_meta.update({n.casefold(): m for n, m in members_meta_of(decl.members).items()})
        for m in decl.members:
            if isinstance(m, VarDecl):
                dim = _dim_value(m.array_dim)
                for n in m.names:
                    member_array_dim[n.casefold()] = dim
        for f in local_funcs_of(decl.functions, disk_graph, enames):
            functions[f.name.casefold()] = FuncBody(
                name=f.name, package="", class_name=decl.name, script_size=0, tokens=(),
                inative=f.native_index or 0, precedence=0,
                flags=(_FUNC_MODIFIER_FLAGS["final"] if f.is_final else 0),
                param_types=f.param_types, return_type=f.return_type)
        enums = {tag.casefold(): ordinal for m in decl.members if isinstance(m, EnumDecl)
                for ordinal, tag in enumerate(m.values)}
        sig = ClassSig(name=decl.name, package="", super_name=decl.super_name,
                       members=members, member_owner=member_owner, functions=functions, enums=enums,
                       member_meta=member_meta, member_array_dim=member_array_dim)
        sigs[cf] = sig
        building.discard(cf)
        return sig

    for name in decls:
        sig_of(name)
    return sigs


class _PkgSigGraph(ClassGraph):
    """A `ClassGraph` that ALSO resolves an in-package class from its AST-derived signature
    (`_prepass_signatures`) when the disk-backed lookup (Core/Engine/other real packages on the search
    path — never this in-progress package, which has no compiled bytes of its own to read) doesn't
    know it. This is the single graph every class in a `compile_package_dir` compile shares, so a
    class sees the WHOLE package's signatures — own, super, and every sibling, including one that
    references it back — no matter which order classes are actually lowered in."""

    def __init__(self, package_paths: list[str], pkg_sigs: dict[str, ClassSig]) -> None:
        super().__init__(package_paths)
        self._pkg_sigs = pkg_sigs

    def class_sig(self, name: str) -> ClassSig | None:
        sig = super().class_sig(name)
        return sig if sig is not None else self._pkg_sigs.get(name.casefold())

    def enum_ordinal(self, tag: str) -> int | None:
        """An enum TAG is a globally-scoped identifier in real UCC (`ClassGraph.enum_ordinal` already
        scans every on-disk package's enums regardless of class) — extend that same global scope to
        this in-progress package's own classes, which have no compiled bytes yet for the disk-based
        scan to see. First disk package wins (matches `ClassGraph`'s own dict-first-wins semantics);
        otherwise the first in-package class (iteration order) declaring the tag."""
        ordinal = super().enum_ordinal(tag)
        if ordinal is not None:
            return ordinal
        cf = tag.casefold()
        for sig in self._pkg_sigs.values():
            if cf in sig.enums:
                return sig.enums[cf]
        return None


def compile_package_dir(classes: dict[str, str], env: InstallEnv, *,
                        package_name: str, texture_files: dict[str, bytes] | None = None
                        ) -> CompiledPackage:
    """Compile every `.uc` in a package (`{filename: source}`) into ONE `CompiledPackage` with shared
    tables. `package_name` is the package's own name (UCC takes it from EditPackages / the output
    filename — it heads every class's PackageImports and enters the name table). A same-package
    super/sibling reference (including a MUTUAL one between two classes) becomes an EXPORT ref, a
    cross-package one an import — see `_prepass_signatures`/`_PkgSigGraph` for how cross-class
    resolution stays independent of build order. `texture_files` maps a `#exec TEXTURE IMPORT FILE=`
    path (as written) to its PCX bytes. `perm_gate(serialize(...), ucc_golden)` is byte-exact modulo
    the documented exclusions (table order, GUID, FName case)."""
    from .serialize import serialize as _serialize      # local: avoid a compile<->serialize cycle

    decls: dict[str, tuple[ClassDecl, str]] = {}
    for src in classes.values():
        decl = parse(src)
        _reject_unsupported(decl)
        decls[decl.name] = (decl, decl.source or src)
    in_pkg_cf = {name.casefold() for name in decls}
    # `order`: still supers-first (an inheritance requirement) and still the gather-order source
    # `true_order` needs below — unrelated to cross-class resolution now (pass 1 handles that).
    order = _compile_order(decls, in_pkg_cf)
    extra_pkgs = _extra_super_packages(decls, env, in_pkg_cf)

    search_dir = env._search_dirs[0]
    base_pkgs = ("core.u", "Engine.u", *(f"{p}.u" for p in extra_pkgs))
    catalog = load_catalog(search_dir, packages=base_pkgs)
    base_paths = [os.path.join(search_dir, p) for p in base_pkgs]

    # Pass 1 (signatures): see `_prepass_signatures`. One shared graph for every class in pass 2.
    pkg_sigs = _prepass_signatures(decls, ClassGraph(base_paths))
    graph = _PkgSigGraph(base_paths, pkg_sigs)

    b = _Build(class_name="", env=env,
               in_pkg_class_names={name.casefold(): name for name in decls},
               in_pkg_decls={name.casefold(): decl for name, (decl, _src) in decls.items()})
    units: list[_ClassUnit] = []
    # Pass 2 (lowering): each class's bytecode body, in turn. `graph` already sees every class's
    # signature (pass 1), so a class may reference a sibling compiled EARLIER OR LATER in `order`.
    for cname in order:
        decl, src = decls[cname]
        unit = _build_class_unit(b, decl, src, env, in_pkg_cf, units, graph, catalog,
                                 package_name, texture_files or {})
        units.append(unit)
    pkg = _finalize_multi(b, units, package_name)
    # Re-emit in UCC's real name/import/export order (decode the provisional bytes, run the
    # dumped-global-index tie-break) — the same autonomous ordering the single-class path uses.
    # `order` (classes, supers-first = UCC's own compile order) + each class's true top-level
    # declaration order (from its own AST, not the compiled/binned Children chain) supply the
    # NAME-table gather order the decoded bytes alone can't recover (see `_top_level_name_order`).
    from .reorder import true_order
    top_level_by_class = {cname: _top_level_name_order(decls[cname][0]) for cname in order}
    names, imports, export_rows = true_order(_serialize(pkg), list(order), top_level_by_class)
    return _finalize_multi(b, units, package_name, override=(names, imports, export_rows))


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
    """Non-Core/Engine home packages of any class TYPE this package's own classes reference —
    supers, member/param/local var types, `array<T>` element types, and `class<T>` meta types —
    loaded into the lowering graph and catalog so inherited members/functions resolve. A
    `BrushBuilder` subclass pulls in `Editor` (the super case); a real UT99 mutator with
    `local UTTeleportEffect TelEff; TelEff.Destroy();` pulls in `Botpack` the same way — calling a
    method through ANY typed reference needs that reference's home package indexed, not just the
    compiling class's own super chain (found compiling the real `ASPMutator` community mutator,
    whose `Destroy()` call through a `Botpack`-typed local raised `unresolved method
    object:utteleporteffect.Destroy` — `ClassGraph` only resolves a class present in its own indexed
    package set, by design; the gap was this discovery pass never looking past the super chain). A
    discovered class's own `package_imports` (its complete transitive super-chain package set, e.g.
    `UTTeleportEffect`'s is `(Botpack, UnrealShare, Engine, Core)` — its super `PawnTeleportEffect`
    lives in UnrealShare, not Botpack) are added too, not just its own home package — one level of
    package discovery isn't enough for a transitive super chain crossing a third package."""
    out: list[str] = []

    def add(name: str | None) -> None:
        if name is None or name.casefold() in in_pkg_cf or name.casefold() in _SCALAR_KINDS \
                or name.casefold() in ("class", "array"):
            return
        info = env.resolve_class(name)
        if info is None:
            return
        for pkg in info.package_imports:
            if pkg.casefold() not in ("core", "engine") and pkg not in out:
                out.append(pkg)

    def add_type(tr) -> None:
        if tr is None:
            return
        add(tr.base)
        add_type(tr.inner)
        add(tr.meta_class)

    def add_expr_class_lits(e) -> None:
        """A CLASS LITERAL (`class'X'`) or metaclass cast (`class<X>(...)`) inside a function/state
        BODY, not just a declared var/param/local/return TYPE — needed because such a literal names
        its own package without any declaration anywhere naming it (found compiling the real
        `UTServerAdmin`: `class'UdpServerUplink'.default.DoUplink`, `UdpServerUplink` living in
        `IpServer`, a package no declared type in `UTServerAdmin` itself ever names)."""
        if e.op == "objref" and e.text.casefold() == "class" and e.value:
            add(str(e.value).rsplit(".", 1)[-1])
        elif e.op == "call" and e.children and e.children[0].op == "name" \
                and e.children[0].text.casefold().startswith("class<"):
            meta = e.children[0].text[len("class<"):-1].strip()
            if meta:
                add(meta.rsplit(".", 1)[-1])
        for c in e.children:
            add_expr_class_lits(c)

    def add_stmt_class_lits(stmts) -> None:
        for s in stmts:
            for e in s.exprs:
                add_expr_class_lits(e)
            for cond, body in s.clauses:
                if cond is not None:
                    add_expr_class_lits(cond)
                add_stmt_class_lits(body)
            add_stmt_class_lits(s.body)

    for decl, _src in decls.values():
        add(decl.super_name)
        for m in decl.members:
            if isinstance(m, VarDecl):
                add_type(m.type)
            elif isinstance(m, StructDecl):
                for sm in m.members:
                    add_type(sm.type)
        funcs = list(decl.functions) + [f for s in decl.states for f in s.funcs]
        for f in funcs:
            add_type(f.return_type)
            for p in f.params:
                add_type(p.type)
            for lv in f.locals:
                add_type(lv.type)
            add_stmt_class_lits(f.body)
        for s in decl.states:
            add_stmt_class_lits(s.body)
    return out


def _build_class_unit(b: _Build, decl: ClassDecl, src: str, env: InstallEnv, in_pkg_cf: set[str],
                      built: list[_ClassUnit], graph, catalog, package_name: str,
                      texture_files: dict[str, bytes]) -> _ClassUnit:
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
        super_probe_mask = super_unit.probe_mask
        super_config_name = super_unit.config_name
    else:
        info = env.resolve_class(super_name)
        if info is None:
            raise NotImplementedError(f"cannot resolve super class {super_name!r} on the search path")
        super_crc = info.self_crc
        super_class_flags = info.class_flags
        super_pkg_imports = info.package_imports
        super_probe_mask = info.probe_mask
        super_config_name = info.config_name

    b.prefix = f"{class_name}::"
    b.class_name = class_name
    b.chain_fields = []
    b.default_props = []
    b.member_class_flags = 0
    b.class_object_flags = _class_object_flags(decl)
    b.extra_deps = []
    b.local_enums = {m.name for m in decl.members if isinstance(m, EnumDecl)}
    b.local_structs = {m.name for m in decl.members if isinstance(m, StructDecl)}
    b.graph_override = graph
    b.catalog_override = catalog

    crlf_source = _to_crlf(_script_text(src))
    class_flags, config_name, within_key = _class_header(decl, env, super_config_name)
    b.emit_zero_defaults = _auto_emit_defaults(
        decl, class_flags | (super_class_flags & _CLASS_INHERIT_MASK), substrate=env.substrate)

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
    if decl.functions or decl.states:
        _build_callables(b, decl, super_name, crlf_source)
    _build_texture_imports(b, decl, texture_files)
    # A same-package sibling extra-dep needs no import (own package is already its 1st PackageImports
    # entry) -- see `_multi_class_export`'s extra_dep().
    for dep_name in b.extra_deps:
        if dep_name.casefold() not in b.in_pkg_class_names:
            _add_import(b, dep_name)

    class_flags |= b.member_class_flags | (super_class_flags & _CLASS_INHERIT_MASK)
    chain = tuple(_class_chain(b))
    # PackageImports = own package, then the super chain's transitive package deps (a class inherits
    # Engine from an in-package Texture subclass, IpDrv+Engine from a TcpLink subclass), then Core.
    # NOT "any other package this class references directly" (measured live against UWeb, 2026-09-13:
    # `var LevelInfo Level;`/a `class<WebApplication>` property spuriously added Engine/self to
    # PackageImports on 4 of 6 real classes whose super chain doesn't need it — a property/param/
    # local/return TYPE reference, a class-literal, or a `Texture'Pkg.Name'` still gets its own
    # IMPORT table entry, it just doesn't count toward PackageImports).
    # FName is case-insensitive: dedup Editor/editor, and spell each dep as its existing package
    # import so the name table doesn't carry both spellings (the super's PI may differ in case).
    imp_by_cf = {k.casefold(): b.imports[k].object_name for k in b.imports}
    deps: list[str] = []
    seen_cf = {package_name.casefold(), "core"}
    for p in super_pkg_imports:
        cf = p.casefold()
        if cf not in seen_cf:
            seen_cf.add(cf)
            deps.append(imp_by_cf.get(cf, p))
    package_imports = (package_name, *deps, "Core")
    probe_mask = super_probe_mask | _probe_bits(f.name for f in decl.functions)
    return _ClassUnit(
        name=class_name, class_key=b.okey(f"class:{class_name}"), st_key=b.okey("ScriptText"),
        super_name=super_name,
        super_export_key=(super_unit.class_key if in_package_super else None),
        super_crc=super_crc, crlf_source=crlf_source, class_flags=class_flags,
        config_name=config_name, within_key=within_key, chain=chain,
        default_props=tuple(b.default_props), package_imports=package_imports,
        self_crc=script_text_crc(crlf_source), object_flags=b.class_object_flags,
        probe_mask=probe_mask, extra_deps=tuple(b.extra_deps),
        texture_keys=tuple(k for k in b.textures if k.startswith(b.prefix)))


def _imports_by_display(b: _Build, display_order: list[tuple[str, str | None]]) -> list[str]:
    """Map an order of (display name, outer display name) import identity pairs — as
    `reorder.true_order` yields them — to `b.imports` KEYS — a function/member import is keyed
    `func:<Class>.<Name>`/`mem:<Class>.<Name>`, not its bare object name.

    Bare display name alone is AMBIGUOUS: a class and an inherited member field can share one (real
    UT99 `IpServer`: `GameInfo`'s own field `GameReplicationInfo` is named identically to its type,
    the class `Engine.GameReplicationInfo` — two distinct global engine objects, two distinct import
    rows). The outer disambiguates them, the same reason an `order_override`'s EXPORT rows carry an
    outer-chain (`_export_refs`'s docstring) instead of a bare name. Falls back to the bare-display
    map only when it is unambiguous (the common case — most imports are the only one of their name)."""
    def outer_disp(spec: _ImportSpec) -> str | None:
        return None if spec.outer is None else b.imports[spec.outer].object_name

    by_id: dict[tuple[str, str | None], str] = {}
    by_disp: dict[str, str] = {}
    disp_count: dict[str, int] = {}
    for key, spec in b.imports.items():
        disp_cf = spec.object_name.casefold()
        disp_count[disp_cf] = disp_count.get(disp_cf, 0) + 1
        od = outer_disp(spec)
        by_id.setdefault((disp_cf, None if od is None else od.casefold()), key)
        by_disp.setdefault(disp_cf, key)

    def resolve(disp: str, outer: str | None) -> str:
        disp_cf = disp.casefold()
        if disp_count.get(disp_cf, 0) > 1:
            return by_id[(disp_cf, None if outer is None else outer.casefold())]
        return by_disp[disp_cf]

    return [resolve(disp, outer) for disp, outer in display_order]


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
    for key, s in b.states.items():
        disp[key] = s.name; outer_key[key] = s.class_key
    for key, t in b.textures.items():
        disp[key] = t.name; outer_key[key] = None            # Outer=0: a top-level package object
        disp[t.palette_key] = t.palette_name; outer_key[t.palette_key] = None

    def chain(key: str) -> tuple[str, ...]:
        out, cur = [], outer_key[key]
        while cur is not None:
            out.append(disp[cur]); cur = outer_key.get(cur)
        return tuple(reversed(out))
    return {k: (d, chain(k)) for k, d in disp.items()}


def _finalize_multi(b: _Build, units: list[_ClassUnit], package_name: str,
                    override: tuple[list[str], list[tuple[str, str | None]],
                                    list[tuple[str, tuple[str, ...]]]] | None = None
                    ) -> CompiledPackage:
    """Order the shared tables and emit the linked `CompiledPackage`. Without `override` a provisional
    order is used (the caller re-derives the real order via `reorder.true_order` and calls again with
    `override=(names, imports, export_rows)`)."""
    if override is None:
        export_keys = _multi_export_order(b, units)
        imports_order = list(b.imports)
        names_order = _pool_cased_dedup(_multi_names(b, units, package_name))
    else:
        ov_names, ov_imports, ov_rows = override
        ident = {(d.casefold(), tuple(x.casefold() for x in path)): k
                 for k, (d, path) in _multi_key_identity(b, units).items()}
        export_keys = [ident[(d.casefold(), tuple(x.casefold() for x in path))] for d, path in ov_rows]
        imports_order = _imports_by_display(b, ov_imports)
        names_order = _pool_cased_dedup(ov_names)
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
    _multi_state_exports(b, next_lookup, nidx, name_cf, exp_ref, imp_ref, recs)
    _build_texture_exports(b, name_index, exp_ref, imp_ref, ref, recs)
    units_by_name = {u.name.casefold(): u for u in units}
    for u in units:
        recs[u.class_key] = _multi_class_export(b, u, name_index, exp_ref, imp_ref, ref, units_by_name)

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
        for tex_key in u.texture_keys:                    # this class's `#exec TEXTURE IMPORT`s
            add(b.textures[tex_key].palette_key)
            add(tex_key)
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
    for s in b.states.values():
        add(s.name)
        for ident in _token_refs(s.toks)[0]:
            add(ident)
    for t in b.textures.values():
        add(t.name)
        add(t.palette_name)
        for ident in _texture_prop_names(t):
            add(ident)
    for u in units:
        for prop in u.default_props:
            add(prop.name)                                # inherited-override names aren't in b.props
            if prop.ptype == PT_NAME and isinstance(prop.value, str):
                add(prop.value)
    return order


def _sibling_export_ref(b: _Build, ident: str, members_by_class: dict[str, dict[str, str]],
                        funcs_by_class: dict[str, dict[str, str]], exp_ref: dict[str, int]
                        ) -> int | None:
    """Resolve a `func:<Owner>.<Name>`/`mem:<Owner>.<Name>` obj identity to a SAME-PACKAGE export when
    `<Owner>` is one of this package's own classes — a sibling class's member/function, including one
    referenced MUTUALLY (two classes each calling into the other; see `_prepass_signatures`, the
    two-pass signature resolution that lets lowering resolve such a call regardless of build order).
    None when `<Owner>` isn't in-package, so the caller falls back to the import table (an inherited
    ancestor outside this package). A BARE ident (no `kind:`/`.`) is a class-literal reference
    (`class'WebRequest'`/`new(...) class'WebRequest'`) to a same-package sibling's own class export —
    same identity a same-package `var WebRequest x` property's type-tail already resolves to
    (`f"{real}::class:{real}"`, see `_resolve_var_type`). A `class:<Name>` ident (a cast/`class<T>()`/
    `class'X'` target, tagged at lower time — see `lower._call_named`/`_ex_objref`) resolves the SAME
    way: it can't be confused with a same-NAMED member/local (`var WebServer WebServer;` is legal
    UnrealScript; `WebServer(x)` still casts to the class), which is exactly why callers check this
    prefix before any member/local lookup, not after."""
    if ident.startswith("class:"):
        real = b.in_pkg_class_names.get(ident[len("class:"):].casefold())
        return exp_ref.get(f"{real}::class:{real}") if real else None
    if ":" not in ident:
        real = b.in_pkg_class_names.get(ident.casefold())
        return exp_ref.get(f"{real}::class:{real}") if real else None
    if "." not in ident:
        return None
    kind, rest = ident.split(":", 1)
    if kind not in ("func", "mem"):
        return None
    owner_cls, name = rest.rsplit(".", 1)
    if owner_cls.casefold() not in b.in_pkg_class_names:
        return None
    real_owner = b.in_pkg_class_names[owner_cls.casefold()]
    class_key = f"{real_owner}::class:{real_owner}"
    table = funcs_by_class if kind == "func" else members_by_class
    key = table.get(class_key, {}).get(name.casefold())
    if key is None:
        raise NotImplementedError(f"same-package {kind} ref {ident!r}: {real_owner}.{name} not found")
    return exp_ref[key]


def _resolve_class_ident(b: _Build, ident: str, members_by_class: dict[str, dict[str, str]],
                         funcs_by_class: dict[str, dict[str, str]], exp_ref: dict[str, int],
                         imp_ref: dict[str, int]) -> int | None:
    """A `class:<Name>` obj ident (a cast/`class<T>()`/`class'X'` target — see `_sibling_export_ref`'s
    docstring for why it's prefixed) resolves BEFORE any local/member/func lookup: a same-package class
    via `_sibling_export_ref`, else an import (pre-registered by `_register_cast_class_imports`, since
    an import discovered this late would miss the already-frozen import table). Returns None for any
    OTHER ident, so the caller continues its normal local/member/func/import resolution."""
    if not ident.startswith("class:"):
        return None
    sib = _sibling_export_ref(b, ident, members_by_class, funcs_by_class, exp_ref)
    if sib is not None:
        return sib
    return imp_ref[ident[len("class:"):]]


def _register_cast_class_imports(b: _Build, toks) -> None:
    """Pre-register an import for every `class:<Name>` cast/`class<T>()`/`class'X'` target (see
    `_sibling_export_ref`'s docstring) that ISN'T a same-package class — must run before the import
    table is frozen (`resolve_inv`'s later `class:` resolution, `_resolve_class_ident`, can only look
    an already-registered import up, not add one)."""
    def walk(t) -> None:
        if t.op in (EX_DYNAMIC_CAST, EX_METACAST, EX_OBJECT_CONST):
            ident = next((v for k, v in t.parts if k == "obj"), None)
            if isinstance(ident, str) and ident.startswith("class:"):
                name = ident[len("class:"):]
                if name.casefold() not in b.in_pkg_class_names:
                    _add_import(b, name)
        for kind, val in t.parts:
            if kind == "sub":
                walk(val)
            elif kind == "parms":
                for s in val:
                    walk(s)

    for t in toks:
        walk(t)


def _multi_function_exports(b: _Build, next_lookup, nidx, name_cf, exp_ref, imp_ref, recs) -> None:
    """One UFunction export per function; each script ref resolves within its OWN class (locals, own
    members, own funcs), then a same-package sibling class, then package imports. Cross-class
    INHERITED virtual calls are name refs (no object ref), so they need only the name table; a virtual
    call through a sibling's typed object is a name ref too, for the same reason."""
    members_by_class: dict[str, dict[str, str]] = {}
    funcs_by_class: dict[str, dict[str, str]] = {}
    for key, p in b.props.items():
        if p.in_class_chain and p.is_var:
            members_by_class.setdefault(p.outer_key, {})[p.name.casefold()] = key
    for f in b.funcs.values():
        funcs_by_class.setdefault(f.class_key, {})[f.name.casefold()] = f.key
    import_by_name = {k.casefold(): k for k in b.imports}
    # `#exec TEXTURE IMPORT` objects are top-level package objects (Outer=0), not class members --
    # a `Texture'Pkg.Name'` literal in ANY class of this package can reach one built by another.
    texture_by_name = {t.name.casefold(): t.key for t in b.textures.values()}

    def resolver(fn: _Func):
        own_members = members_by_class.get(fn.class_key, {})
        own_funcs = funcs_by_class.get(fn.class_key, {})

        def resolve_inv(kind: str, ident: str) -> int:
            if kind == "name":
                return name_cf[ident.casefold()]
            cls_ref = _resolve_class_ident(b, ident, members_by_class, funcs_by_class, exp_ref, imp_ref)
            if cls_ref is not None:
                return cls_ref
            cf = ident.casefold()
            if cf in fn.local_by_name:
                return exp_ref[fn.local_by_name[cf]]
            if cf in own_members:
                return exp_ref[own_members[cf]]
            if cf in own_funcs:
                return exp_ref[own_funcs[cf]]
            if cf in texture_by_name:
                return exp_ref[texture_by_name[cf]]
            sib = _sibling_export_ref(b, ident, members_by_class, funcs_by_class, exp_ref)
            if sib is not None:
                return sib
            if cf in import_by_name:
                return imp_ref[import_by_name[cf]]
            raise NotImplementedError(f"cannot resolve script ref {ident!r} in {fn.name!r}")
        return resolve_inv

    for fkey, fn in b.funcs.items():
        children = exp_ref[fn.child_keys[0]] if fn.child_keys else 0
        super_ref = 0
        if fn.super_ref_key:
            sib = _sibling_export_ref(b, fn.super_ref_key, members_by_class, funcs_by_class, exp_ref)
            super_ref = sib if sib is not None else imp_ref[fn.super_ref_key]
        recs[fkey] = Export(
            cls=imp_ref["Function"], super_ref=super_ref, outer=exp_ref[fn.class_key], name=nidx(fn.name),
            flags=_RF_FIELD,
            body=FunctionBody(
                super_field=super_ref,
                next_field=next_lookup.get(fkey, 0), children=children,
                friendly_name=nidx(fn.name), line=fn.line, text_pos=fn.text_pos,
                script=encode_script(list(fn.toks), resolver(fn)), script_size=fn.script_size,
                inative=0, oper_precedence=0, function_flags=fn.function_flags,
                rep_offset=fn.rep_offset))


def _multi_state_exports(b: _Build, next_lookup, nidx, name_cf, exp_ref, imp_ref, recs) -> None:
    """One UState export per state; each script ref resolves within its OWN class, same scoping as
    `_multi_function_exports`. See `_build_state_exports` (single-class path) for the
    `label_table_offset` note."""
    members_by_class: dict[str, dict[str, str]] = {}
    funcs_by_class: dict[str, dict[str, str]] = {}
    for key, p in b.props.items():
        if p.in_class_chain and p.is_var:
            members_by_class.setdefault(p.outer_key, {})[p.name.casefold()] = key
    for f in b.funcs.values():
        funcs_by_class.setdefault(f.class_key, {})[f.name.casefold()] = f.key
    import_by_name = {k.casefold(): k for k in b.imports}
    texture_by_name = {t.name.casefold(): t.key for t in b.textures.values()}

    def resolver(st: _State):
        own_members = members_by_class.get(st.class_key, {})
        own_funcs = funcs_by_class.get(st.class_key, {})

        def resolve_inv(kind: str, ident: str) -> int:
            if kind == "name":
                return name_cf[ident.casefold()]
            cls_ref = _resolve_class_ident(b, ident, members_by_class, funcs_by_class, exp_ref, imp_ref)
            if cls_ref is not None:
                return cls_ref
            cf = ident.casefold()
            if cf in own_members:
                return exp_ref[own_members[cf]]
            if cf in own_funcs:
                return exp_ref[own_funcs[cf]]
            if cf in texture_by_name:
                return exp_ref[texture_by_name[cf]]
            sib = _sibling_export_ref(b, ident, members_by_class, funcs_by_class, exp_ref)
            if sib is not None:
                return sib
            if cf in import_by_name:
                return imp_ref[import_by_name[cf]]
            raise NotImplementedError(f"cannot resolve script ref {ident!r} in state {st.name!r}")
        return resolve_inv

    for skey, st in b.states.items():
        resolve_inv = resolver(st)
        has_table = bool(st.toks) and st.toks[-1].op == EX_LABEL_TABLE
        label_table_offset = (sum(_mem_size(t) for t in st.toks[:-1]) + 1) if has_table else 0xFFFF
        recs[skey] = Export(
            cls=imp_ref["State"], super_ref=0, outer=exp_ref[st.class_key], name=nidx(st.name),
            flags=_RF_FIELD,
            body=StateBody(
                super_field=0, next_field=next_lookup.get(skey, 0), children=0,
                friendly_name=nidx(st.name), line=st.line, text_pos=st.text_pos,
                script=encode_script(list(st.toks), resolve_inv), script_size=st.script_size,
                probe_mask=0, ignore_mask=0xFFFFFFFFFFFFFFFF,
                label_table_offset=label_table_offset, state_flags=0))


def _multi_class_export(b: _Build, u: _ClassUnit, name_index, exp_ref, imp_ref, ref,
                        units_by_name: dict[str, "_ClassUnit"] | None = None) -> Export:
    super_ref = exp_ref[u.super_export_key] if u.super_export_key else imp_ref[u.super_name]
    children = exp_ref[u.chain[0]] if u.chain else 0
    self_dep = Dependency(cls=exp_ref[u.class_key], deep=1, script_text_crc=u.self_crc)
    super_dep = Dependency(cls=super_ref, deep=1, script_text_crc=u.super_crc)

    def extra_dep(dep: str) -> Dependency:
        sib = (units_by_name or {}).get(dep.casefold())
        if sib is not None:                               # a same-package sibling -> an EXPORT dep
            return Dependency(cls=exp_ref[sib.class_key], deep=0, script_text_crc=sib.self_crc)
        return Dependency(cls=imp_ref[_add_import(b, dep)], deep=0,
                          script_text_crc=_extra_dep_crc(b.env, dep))

    extra_deps = tuple(extra_dep(dep) for dep in u.extra_deps)
    return Export(
        cls=0, super_ref=super_ref, outer=0, name=name_index[u.name], flags=u.object_flags,
        body=ClassBody(
            super_field=super_ref, next_field=0, script_text=exp_ref[u.st_key],
            children=children, friendly_name=name_index[u.name],
            line=0xFFFFFFFF, text_pos=0xFFFFFFFF, script=b"",
            probe_mask=u.probe_mask, ignore_mask=0xFFFFFFFFFFFFFFFF, label_table_offset=0xFFFF,
            state_flags=0, class_flags=u.class_flags, class_guid=b"\x00" * 16,
            dependencies=(self_dep, super_dep, *extra_deps),
            package_imports=tuple(name_index[p] for p in u.package_imports),
            class_within=imp_ref[u.within_key], class_config_name=name_index[u.config_name],
            default_props=write_props(lambda s: name_index[s],
                                      _resolve_default_refs(u.default_props, ref))))
