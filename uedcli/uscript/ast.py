"""UnrealScript AST — the parser's output and the compiler's input.

One `ClassDecl` per `.uc`. Nodes keep enough source detail to compile byte-exactly: declaration
ORDER within the class is preserved (members is an ordered list of the mixed const/enum/struct/var
declarations as they appear), modifiers are kept verbatim (lowercased), and expressions retain their
literal form. Statements/expressions use a small generic shape — the bytecode emitter walks them.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ── types ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, kw_only=True)
class TypeRef:
    """A variable/parameter/return type as written."""
    base: str                       # "int","float","bool","byte","string","name","class",
                                    # "array", or a struct/enum/class identifier
    inner: "TypeRef | None" = None  # element type for array<...> / metaclass for class<...>
    string_size: int | None = None  # for `string[N]` fixed strings
    meta_class: str | None = None   # for class<Foo>
    array_size: int | None = None   # for the Deus Ex `array<T,N>` sized-array form


# ── expressions / statements (generic) ────────────────────────────────────────
@dataclass(frozen=True, kw_only=True)
class Expr:
    """A generic expression node. `op` names the shape (`lit`,`name`,`call`,`member`,`index`,
    `unary`,`binary`,`new`,`cast`,`self`,`super`,`default`,`static`,`global`,`paren`,`vector`,
    `rotator`,`nameconst`,`stringconst`,`intconst`,`floatconst`,`byteconst`,`boolconst`,`noneconst`).
    `value` holds a literal's decoded value; `text` a spelling; `children` sub-exprs."""
    op: str
    value: object = None
    text: str = ""
    children: tuple["Expr", ...] = ()


@dataclass(frozen=True, kw_only=True)
class Stmt:
    """A generic statement node. `kind` in {`local`,`assign`,`expr`,`if`,`for`,`while`,`do`,
    `switch`,`case`,`default`,`return`,`break`,`continue`,`goto`,`label`,`foreach`,`assert`,
    `block`,`stop`,`ignores`}. Fields used depend on kind; `exprs`/`body`/`text` carry the pieces."""
    kind: str
    text: str = ""
    exprs: tuple[Expr, ...] = ()
    body: tuple["Stmt", ...] = ()
    clauses: tuple[tuple[Expr | None, tuple["Stmt", ...]], ...] = ()   # if/switch arms
    local_type: TypeRef | None = None
    names: tuple[str, ...] = ()


# ── declarations ──────────────────────────────────────────────────────────────
@dataclass(frozen=True, kw_only=True)
class VarDecl:
    names: tuple[str, ...]          # `var int a, b;` declares two
    type: TypeRef
    modifiers: tuple[str, ...] = ()  # const/config/transient/native/private/... (lowercased)
    category: str | None = None      # the `var(Category)` group, "" for bare `var()`
    array_dim: int | str | None = None  # static array size (int) or a const-name


@dataclass(frozen=True, kw_only=True)
class ConstDecl:
    name: str
    value: Expr


@dataclass(frozen=True, kw_only=True)
class EnumDecl:
    name: str
    values: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class StructDecl:
    name: str
    base: str | None
    modifiers: tuple[str, ...]
    members: tuple[VarDecl, ...]


@dataclass(frozen=True, kw_only=True)
class Param:
    name: str
    type: TypeRef
    modifiers: tuple[str, ...] = ()  # out/optional/coerce/skip
    default: Expr | None = None


@dataclass(frozen=True, kw_only=True)
class FuncDecl:
    name: str
    kind: str                        # "function"/"event"/"operator"/"preoperator"/"postoperator"/"delegate"
    modifiers: tuple[str, ...] = ()  # static/final/native/simulated/latent/iterator/exec/...
    native_index: int | None = None
    oper_precedence: int | None = None   # for operators
    return_type: TypeRef | None = None
    params: tuple[Param, ...] = ()
    locals: tuple[VarDecl, ...] = ()
    body: tuple[Stmt, ...] = ()
    has_body: bool = True            # native/declared-only functions have no `{...}`


@dataclass(frozen=True, kw_only=True)
class StateDecl:
    name: str
    base: str | None
    modifiers: tuple[str, ...]
    ignores: tuple[str, ...]
    funcs: tuple[FuncDecl, ...]
    body: tuple[Stmt, ...]           # labels + statements


@dataclass(frozen=True, kw_only=True)
class ReplBlock:
    # each: (reliable:bool, condition Expr, replicated names)
    entries: tuple[tuple[bool, Expr, tuple[str, ...]], ...]


@dataclass(frozen=True, kw_only=True)
class DefaultProp:
    name: str
    array_index: int | None
    value: Expr


@dataclass(frozen=True, kw_only=True)
class ClassDecl:
    name: str
    super_name: str | None
    within: str | None = None
    modifiers: tuple[str, ...] = ()          # abstract/native/config(...)/transient/...
    # declaration-order stream of member declarations (const/enum/struct/var interleaved as written)
    members: tuple[object, ...] = ()         # VarDecl | ConstDecl | EnumDecl | StructDecl
    functions: tuple[FuncDecl, ...] = ()
    states: tuple[StateDecl, ...] = ()
    replication: ReplBlock | None = None
    default_props: tuple[DefaultProp, ...] = ()
    exec_directives: tuple[str, ...] = ()    # `#exec ...` lines, in order
    source: str = ""                         # the raw source text (for ScriptText / CRC)
    cpptext: str | None = None
