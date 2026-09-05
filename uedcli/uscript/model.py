"""The resolved compiled-package model — the contract between the compiler front-end (which assigns
name/import/export ORDER and every object ref) and the byte serializer (`serialize.py`).

Everything here is already LINKED: names are in final table order, imports/exports in final table
order, and every cross-object reference is an already-resolved signed objref (0=None, >0 export
1-based, <0 import `-idx-1`). The serializer is then purely mechanical — no ordering or resolution
decisions happen at serialization time, so byte-parity is decided by the compiler that builds this
model, and the serializer just has to encode it faithfully.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, kw_only=True)
class Name:
    text: str
    flags: int          # the full u32 written after the string (incl the 0x10 low bit)


@dataclass(frozen=True, kw_only=True)
class Import:
    class_package: int  # name index
    class_name: int     # name index
    package_index: int  # signed objref of the outer
    object_name: int    # name index


@dataclass(frozen=True, kw_only=True)
class Dependency:
    cls: int            # signed objref
    deep: int
    script_text_crc: int


@dataclass(frozen=True, kw_only=True)
class TextBufferBody:
    pos: int
    top: int
    text: str           # stored verbatim (already CRLF-normalised by the compiler)


@dataclass(frozen=True, kw_only=True)
class ClassBody:
    super_field: int
    next_field: int
    script_text: int        # objref of the ScriptText export
    children: int           # objref of the first child field (0 if none)
    friendly_name: int      # name index
    line: int
    text_pos: int
    script: bytes           # emitted bytecode (empty for a class — classes hold no code directly)
    probe_mask: int
    ignore_mask: int
    label_table_offset: int
    state_flags: int
    class_flags: int
    class_guid: bytes       # 16 bytes (all-zero in practice)
    dependencies: tuple[Dependency, ...]
    package_imports: tuple[int, ...]   # name indices
    class_within: int       # objref
    class_config_name: int  # name index
    default_props: bytes    # already-serialised None-terminated tagged-property list


@dataclass(frozen=True, kw_only=True)
class PropertyBody:
    """A UProperty member var. Body layout (RE'd byte-exact, `class-schema.md`):
    `ci(None) + ci(SuperField=0) + ci(Next) + u32 ArrayDim + u32 PropertyFlags + ci(Category) +
    [type tail]`. The type tail is the subclass ref stream: ByteProperty → ci(Enum); ObjectProperty →
    ci(PropertyClass); ClassProperty → ci(Class) + ci(MetaClass); StructProperty → ci(Struct);
    ArrayProperty → ci(Inner); scalar int/float/bool/name/str → empty."""
    next_field: int         # objref of the next sibling field (0 if last)
    array_dim: int          # 1 for a scalar var, N for `var T x[N]`
    property_flags: int
    category: int = 0       # name index of the var() category (0 = None)
    type_tail: tuple[int, ...] = ()  # subclass type-ref stream (see above)


@dataclass(frozen=True, kw_only=True)
class EnumBody:
    """A UEnum export (`enum EFoo {...}`). Body: `ci(None) + ci(SuperField=0) + ci(Next) +
    ci(count) + count × ci(value name index)` (tag names in declaration order)."""
    next_field: int
    values: tuple[int, ...]  # name indices of the enum tags, in declaration order


@dataclass(frozen=True, kw_only=True)
class ConstBody:
    """A UConst export (`const K = expr;`). Body: `ci(None) + ci(SuperField=0) + ci(Next) +
    FString(value)`. `value` is the verbatim source text between `=` and `;`, trailing-trimmed."""
    next_field: int
    value: str


@dataclass(frozen=True, kw_only=True)
class StructBody:
    """A UStruct export (`struct SFoo {...}`). Body: `ci(None) + ci(SuperField) + ci(Next) +
    ci(ScriptText=0) + ci(Children) + ci(FriendlyName) + u32 Line + u32 TextPos + u32 ScriptSize`.
    No StructFlags / no script bytes in UE1 (RE'd byte-exact). Members are child UProperty exports."""
    super_field: int
    next_field: int
    children: int           # objref of the first member property (0 if none)
    friendly_name: int      # name index of the struct name
    line: int = 0
    text_pos: int = 0
    script_size: int = 0


@dataclass(frozen=True, kw_only=True)
class FunctionBody:
    """A UFunction export (`function F(){...}`). Body (RE'd byte-exact, `bytecode.md`):
    `ci(None) + ci(SuperField) + ci(Next) + ci(ScriptText=0) + ci(Children) + ci(FriendlyName) +
    u32 Line + u32 TextPos + u32 ScriptSize + <script bytecode> + u16 iNative + u8 OperPrecedence +
    u32 FunctionFlags + [u16 RepOffset iff FunctionFlags & FUNC_Net(0x40)]`. Params/return/locals are
    child UProperty exports (Outer = this function), chained by `children`/Next in the order
    params → ReturnValue → locals. `ParmsSize`/`NumParms`/`ReturnValueOffset` are NOT serialized (the
    engine relinks them from the Children properties at load)."""
    super_field: int        # 0 unless the function overrides an inherited one (then its UFunction ref)
    next_field: int         # objref of the next class-Children field (0 if last)
    children: int           # objref of the first child property (0 if none)
    friendly_name: int      # name index of the function name
    line: int               # 1-based source line of the declaration
    text_pos: int           # byte offset into ScriptText of the first executable statement
    script: bytes           # on-disk bytecode stream
    script_size: int        # in-memory ScriptSize (the memory-walk size, not len(script))
    inative: int            # 0 for a script function
    oper_precedence: int    # 0 for a non-operator
    function_flags: int     # FUNC_*
    rep_offset: int | None = None   # written iff FUNC_Net (0x40) is set


@dataclass(frozen=True, kw_only=True)
class ObjectBody:
    """A plain (non-code) UObject instance body — e.g. a `ConSys` conversation object emitted by
    `#exec CONVERSATION IMPORT` (`conimport.py`). Just its None-terminated tagged-property list,
    already serialized (names/refs resolved by the compiler), plus any native-`Serialize` `trailer`
    (a `ConAudioList` appends a one-byte empty-array count). Unlike the code-object bodies it carries
    NO leading None ref."""
    props: bytes            # already-serialised None-terminated tagged-property list
    trailer: bytes = b""    # native Serialize tail (empty for all but ConAudioList)


@dataclass(frozen=True, kw_only=True)
class Export:
    cls: int
    super_ref: int
    outer: int
    name: int               # name index
    flags: int              # RF_* object flags
    body: (TextBufferBody | ClassBody | PropertyBody | EnumBody | ConstBody | StructBody
           | FunctionBody | ObjectBody)


@dataclass(frozen=True, kw_only=True)
class CompiledPackage:
    version: int
    licensee: int
    package_flags: int
    names: tuple[Name, ...]
    imports: tuple[Import, ...]
    exports: tuple[Export, ...]
    guid: bytes = field(default=b"\x00" * 16)   # excluded from parity; real value irrelevant
