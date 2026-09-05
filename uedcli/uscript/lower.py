"""AST -> bytecode lowering: turn a parsed `FuncDecl` body into the exact `Tok` stream UCC emits.

`lower_function(func, scope, catalog)` walks the statements/expressions of one function and returns a
`list[Tok]` (see `bytecode.py`) identical (modulo FName case — see `toks_equal`) to the token list
UCC's compiler produces. The oracle is `natives.read_function`, which decodes UCC's own output.

Design:
- Expressions lower with TYPE INFERENCE (`_expr` returns `(Tok, type_label)`), needed to resolve
  overloaded operators/calls (`natives.Catalog`) and pick the const form.
- Statements lower to a flat top-level token stream. Control flow is flat too: `if`/`while`/`for`
  become `JumpIfNot`/`Jump` with absolute u16 MEMORY offsets, patched after sizing every token
  (`_mem_size` mirrors the codec's memory walk: obj/name refs count as 4 bytes).
- Every function body ends with an implicit `Return(Nothing)`.

Type labels are lowercase strings: `int float bool byte string name vector rotator object class none`.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .ast import ConstDecl, EnumDecl, Expr, FuncDecl, TypeRef, VarDecl
from .bytecode import Tok
from .natives import Catalog, FuncBody

# opcodes
EX_LOCAL_VARIABLE = 0x00
EX_INSTANCE_VARIABLE = 0x01
EX_RETURN = 0x04
EX_SWITCH = 0x05
EX_JUMP = 0x06
EX_CASE = 0x0A
EX_ARRAY_ELEMENT = 0x1A
EX_JUMP_IF_NOT = 0x07
EX_NOTHING = 0x0B
EX_NEW = 0x11
EX_LET = 0x0F
EX_SKIP = 0x18
EX_BOOL_VARIABLE = 0x2D
EX_LET_BOOL = 0x14
EX_END_FUNCTION_PARMS = 0x16
EX_SELF = 0x17
EX_CONTEXT = 0x19
EX_STRUCT_MEMBER = 0x36
EX_VIRTUAL_FUNCTION = 0x1B
EX_FINAL_FUNCTION = 0x1C
EX_METACAST = 0x13
EX_INT_CONST = 0x1D
EX_FLOAT_CONST = 0x1E
EX_STRING_CONST = 0x1F
EX_OBJECT_CONST = 0x20
EX_BYTE_CONST = 0x24
EX_DYNAMIC_CAST = 0x2E
EX_NAME_CONST = 0x21
EX_INT_ZERO = 0x25
EX_INT_ONE = 0x26
EX_TRUE = 0x27
EX_FALSE = 0x28
EX_NO_OBJECT = 0x2A
EX_INT_CONST_BYTE = 0x2C
EX_EXTENDED_NATIVE = 0x60
EX_FIRST_NATIVE = 0x70

_PRIMITIVE_TYPES = frozenset({"int", "float", "bool", "byte", "string", "name"})
# Built-in struct names, used to classify a declared type as struct vs object when no ClassGraph is
# available (the graph, when present, is authoritative via `is_struct_name`).
_BUILTIN_STRUCTS = frozenset({"vector", "rotator", "plane", "coords", "color", "region", "scale",
                              "box", "boundingbox", "quat", "matrix", "pointregion"})
_WORD_OPS = {"dot": "Dot", "cross": "Cross", "clockwisefrom": "ClockwiseFrom"}

# Size in bytes of a value on the VM stack, for a Context's bSize field (verified: Vector=12; the
# primitives are 4-byte DWORDs / refs). An unknown size raises LowerError rather than guessing.
_VALUE_SIZE: dict[str, int] = {"int": 4, "float": 4, "bool": 4, "name": 4, "class": 4, "byte": 1,
                               "none": 0, "string": 0, "vector": 12, "rotator": 12}


class LowerError(Exception):
    """A construct the lowerer cannot yet turn into bytecode, naming what it hit."""


# ── types + scope ───────────────────────────────────────────────────────────────
def _is_object(t: str) -> bool:
    return t.startswith("object:")


def _is_struct(t: str) -> bool:
    return t.startswith("struct:")


def _class_of(t: str) -> str | None:
    return t.split(":", 1)[1] if ":" in t else None


def _value_size(t: str, graph=None) -> int:
    if _is_struct(t):
        name = _class_of(t)
        n = _VALUE_SIZE.get(name.casefold())
        if n is None and graph is not None:
            n = graph.struct_size(name)                 # compute from the struct's members
        if n is None:
            raise LowerError(f"unknown value size for struct {t!r}")
        return n
    if _is_object(t):
        return 4
    n = _VALUE_SIZE.get(t)
    if n is None:
        raise LowerError(f"unknown value size for type {t!r}")
    return n


@dataclass(frozen=True, kw_only=True)
class Symbol:
    storage: str                    # "local" | "member"
    type: str


@dataclass(frozen=True, kw_only=True)
class CallTarget:
    """A resolved call target — script (Virtual/Final) or native — with its signature."""
    name: str
    is_final: bool
    native_index: int | None
    param_types: tuple[str, ...]
    return_type: str | None


def _target_of(x) -> CallTarget:
    if isinstance(x, CallTarget):
        return x
    if isinstance(x, LocalFunc):
        return CallTarget(name=x.name, is_final=x.is_final, native_index=x.native_index,
                          param_types=x.param_types, return_type=x.return_type)
    # a natives.FuncBody
    return CallTarget(name=x.name, is_final=x.is_final,
                      native_index=x.inative if x.is_native else None,
                      param_types=x.param_types, return_type=x.return_type)


@dataclass(frozen=True, kw_only=True)
class LocalFunc:
    name: str
    is_final: bool
    return_type: str | None
    param_types: tuple[str, ...]
    native_index: int | None = None


class Scope:
    """Resolve identifiers, members, and calls for one function. Locals/params and the class's own
    members/functions come from the AST; inherited members/functions and the fields/methods of other
    classes are resolved through a `natives.ClassGraph` (the super chain, across packages)."""

    def __init__(self, *, locals_: dict[str, str], own_members: dict[str, str],
                 own_funcs: dict[str, LocalFunc], class_name: str | None,
                 super_name: str | None, graph=None, enums: dict[str, int] | None = None,
                 consts: dict[str, Expr] | None = None) -> None:
        self._locals = {k.casefold(): v for k, v in locals_.items()}
        self._members = {k.casefold(): v for k, v in own_members.items()}
        self._funcs = {k.casefold(): v for k, v in own_funcs.items()}
        self._enums = {k.casefold(): v for k, v in (enums or {}).items()}
        self._consts = {k.casefold(): v for k, v in (consts or {}).items()}
        self.class_name = class_name
        self.super_name = super_name
        self.graph = graph

    def enum_value(self, name: str) -> int | None:
        cf = name.casefold()
        if cf in self._enums:
            return self._enums[cf]
        return self.graph.enum_ordinal(name) if self.graph else None

    def const_expr(self, name: str) -> Expr | None:
        cf = name.casefold()
        if cf in self._consts:
            return self._consts[cf]
        if self.graph:
            value = self.graph.const_value(name)
            if value is not None:
                return _parse_value_expr(value)
        return None

    def lookup(self, name: str) -> Symbol | None:
        cf = name.casefold()
        if cf in self._locals:
            return Symbol(storage="local", type=self._locals[cf])
        if cf in self._members:
            return Symbol(storage="member", type=self._members[cf])
        if self.graph and self.super_name:
            t = self.graph.member_type(self.super_name, name)
            if t is not None:
                return Symbol(storage="member", type=t)
        return None

    def func(self, name: str) -> CallTarget | None:
        cf = name.casefold()
        if cf in self._funcs:
            return _target_of(self._funcs[cf])
        if self.graph and self.super_name:
            fb = self.graph.function(self.super_name, name)
            if fb is not None:
                return _target_of(fb)
        return None

    def _is_own(self, cls: str | None) -> bool:
        return bool(cls and self.class_name and cls == self.class_name.casefold())

    def member_of(self, obj_type: str, field: str) -> str | None:
        cls = _class_of(obj_type)
        if _is_struct(obj_type):
            return self.graph.struct_member_type(cls, field) if (self.graph and cls) else None
        if self._is_own(cls):                           # the class being compiled
            cf = field.casefold()
            if cf in self._members:
                return self._members[cf]
            return self.graph.member_type(self.super_name, field) if (
                self.graph and self.super_name) else None
        return self.graph.member_type(cls, field) if (self.graph and cls) else None

    def method_of(self, obj_type: str, name: str) -> CallTarget | None:
        cls = _class_of(obj_type)
        if self._is_own(cls):
            return self.func(name)
        if not (self.graph and cls):
            return None
        fb = self.graph.function(cls, name)
        return _target_of(fb) if fb is not None else None

    def is_class_name(self, name: str) -> bool:
        return bool(self.graph and self.graph.class_sig(name) is not None)


def type_label(tr: TypeRef | None, graph=None, enum_names=frozenset()) -> str:
    """The lowering type label for a declared type (`object:X`/`struct:X`/primitive/`class`).
    An enum type resolves to `byte`. `enum_names` covers the class's own enums (not in the graph)."""
    if tr is None:
        return "none"
    base = tr.base
    low = base.casefold()
    if low in _PRIMITIVE_TYPES:
        return low
    if low == "class":
        return "class"
    if low == "array":
        return "array"
    if low in enum_names or (graph is not None and graph.is_enum_name(base)):
        return "byte"
    is_struct = graph.is_struct_name(base) if graph is not None else (low in _BUILTIN_STRUCTS)
    return f"struct:{low}" if is_struct else f"object:{low}"


def enum_type_names(class_members) -> frozenset[str]:
    """Casefolded names of a `ClassDecl`'s own `EnumDecl` types."""
    return frozenset(m.name.casefold() for m in class_members if isinstance(m, EnumDecl))


def consts_of(class_members) -> dict[str, Expr]:
    """Name -> value `Expr` for a `ClassDecl`'s own `ConstDecl` members."""
    return {m.name: m.value for m in class_members if isinstance(m, ConstDecl)}


_VALUE_EXPR_CACHE: dict[str, Expr | None] = {}


def _parse_value_expr(text: str) -> Expr | None:
    """Parse a const's stored value text (e.g. `1`, `'Foo'`, `0.5`) into an `Expr`, cached."""
    if text in _VALUE_EXPR_CACHE:
        return _VALUE_EXPR_CACHE[text]
    from .parser import parse
    try:
        decl = parse(f"class _c;\nfunction _f(){{ _v = {text}; }}")
        expr = decl.functions[0].body[0].exprs[1]
    except Exception:
        expr = None
    _VALUE_EXPR_CACHE[text] = expr
    return expr


def members_of(class_members, graph=None) -> dict[str, str]:
    """Type-label map for a `ClassDecl`'s own `VarDecl` members."""
    enums = enum_type_names(class_members)
    out: dict[str, str] = {}
    for m in class_members:
        if isinstance(m, VarDecl):
            for n in m.names:
                out[n] = type_label(m.type, graph, enums)
    return out


def local_funcs_of(class_funcs, graph=None, enum_names=frozenset()) -> list[LocalFunc]:
    out: list[LocalFunc] = []
    for f in class_funcs:
        if not f.has_body and f.kind not in ("function", "event"):
            continue
        out.append(LocalFunc(
            name=f.name, is_final="final" in f.modifiers,
            return_type=type_label(f.return_type, graph, enum_names) if f.return_type else None,
            param_types=tuple(type_label(p.type, graph, enum_names) for p in f.params),
            native_index=f.native_index))
    return out


def enums_of(class_members) -> dict[str, int]:
    """Enum-tag -> ordinal map for a `ClassDecl`'s own `EnumDecl` members."""
    out: dict[str, int] = {}
    for m in class_members:
        if isinstance(m, EnumDecl):
            for ordinal, tag in enumerate(m.values):
                out.setdefault(tag, ordinal)
    return out


def build_scope(func: FuncDecl, *, members: dict[str, str] | None = None,
                funcs: list[LocalFunc] | None = None, class_name: str | None = None,
                super_name: str | None = None, graph=None,
                enums: dict[str, int] | None = None, enum_names=frozenset(),
                consts: dict[str, Expr] | None = None) -> Scope:
    """Scope from a function's params + locals plus the class's own members/functions/enums and, via
    `graph`, its inherited symbols, other classes' fields/methods, and imported enum tags.
    `enums` maps own enum tags to ordinals; `enum_names` are the own enum TYPE names."""
    locals_: dict[str, str] = {}
    for p in func.params:
        locals_[p.name] = type_label(p.type, graph, enum_names)
    for vd in func.locals:
        for n in vd.names:
            locals_[n] = type_label(vd.type, graph, enum_names)
    own_funcs = {f.name: f for f in (funcs or [])}
    return Scope(locals_=locals_, own_members=dict(members or {}), own_funcs=own_funcs,
                 class_name=class_name, super_name=super_name, graph=graph, enums=enums,
                 consts=consts)


# ── conversions (EExprToken 0x39..0x5F) — each opcode VERIFIED against a UCC compile ─────────────
_CONV: dict[tuple[str, str], int] = {
    ("byte", "int"): 0x3A, ("byte", "float"): 0x3C,
    ("int", "byte"): 0x3D, ("int", "bool"): 0x3E, ("int", "float"): 0x3F,
    ("float", "int"): 0x44,
    ("string", "int"): 0x4A, ("string", "float"): 0x4C,
    ("int", "string"): 0x53, ("bool", "string"): 0x54, ("float", "string"): 0x55,
    ("name", "string"): 0x57,
}


# ── flat body builder with jump patching ───────────────────────────────────────
@dataclass
class _Emit:
    """One entry in the flat top-level stream: a final Tok, or a jump awaiting a target offset."""
    tok: Tok | None = None
    jump_kind: str | None = None            # "jump" | "jumpifnot"
    cond: Tok | None = None
    target: int | None = None               # a label id


class _Body:
    def __init__(self) -> None:
        self.items: list[_Emit] = []
        self.labels: dict[int, int] = {}    # label id -> item index it precedes
        self._next = 0

    def new_label(self) -> int:
        self._next += 1
        return self._next

    def place(self, label: int) -> None:
        self.labels[label] = len(self.items)

    def tok(self, t: Tok) -> None:
        self.items.append(_Emit(tok=t))

    def jump(self, target: int) -> None:
        self.items.append(_Emit(jump_kind="jump", target=target))

    def jump_if_not(self, cond: Tok, target: int) -> None:
        self.items.append(_Emit(jump_kind="jumpifnot", cond=cond, target=target))

    def case(self, value: Tok, next_case: int) -> None:
        """A `switch` case guard: fall through to the body if the subject matches `value`, else jump
        to `next_case` (the following Case token)."""
        self.items.append(_Emit(jump_kind="case", cond=value, target=next_case))

    def case_default(self) -> None:
        self.items.append(_Emit(jump_kind="casedefault"))

    def finish(self) -> list[Tok]:
        sizes = [self._size(it) for it in self.items]
        prefix = [0]
        for s in sizes:
            prefix.append(prefix[-1] + s)
        offset = {lbl: prefix[idx] for lbl, idx in self.labels.items()}
        out: list[Tok] = []
        for it in self.items:
            if it.tok is not None:
                out.append(it.tok)
            elif it.jump_kind == "jump":
                out.append(Tok(EX_JUMP, (("raw", struct.pack("<H", offset[it.target])),)))
            elif it.jump_kind == "jumpifnot":
                out.append(Tok(EX_JUMP_IF_NOT,
                               (("raw", struct.pack("<H", offset[it.target])), ("sub", it.cond))))
            elif it.jump_kind == "case":
                out.append(Tok(EX_CASE,
                               (("raw", struct.pack("<H", offset[it.target])), ("sub", it.cond))))
            else:                                       # case default (0xFFFF marker, no value)
                out.append(Tok(EX_CASE, (("raw", b"\xff\xff"),)))
        return out

    @staticmethod
    def _size(it: _Emit) -> int:
        if it.tok is not None:
            return _mem_size(it.tok)
        if it.jump_kind == "jump":
            return 3
        if it.jump_kind == "casedefault":
            return 3
        return 3 + _mem_size(it.cond)                   # jumpifnot / case: op + u16 + value/cond


def _mem_size(tok: Tok) -> int:
    """In-memory size of a token (the codec's memory cursor): op byte + parts, obj/name refs = 4."""
    n = 1
    for part in tok.parts:
        kind = part[0]
        if kind == "raw":
            n += len(part[1])
        elif kind in ("obj", "name"):
            n += 4
        elif kind == "sub":
            n += _mem_size(part[1])
        elif kind == "parms":
            n += sum(_mem_size(t) for t in part[1])
    return n


# ── the lowerer ────────────────────────────────────────────────────────────────
def lower_function(func: FuncDecl, scope: Scope, catalog: Catalog) -> list[Tok]:
    """Lower one function body to its token stream (with the trailing implicit Return(Nothing))."""
    low = _Lowerer(scope, catalog, type_label(func.return_type) if func.return_type else "none")
    for stmt in func.body:
        low.stmt(stmt)
    low.body.tok(Tok(EX_RETURN, (("sub", Tok(EX_NOTHING)),)))
    return low.body.finish()


class _Lowerer:
    def __init__(self, scope: Scope, catalog: Catalog, return_type: str) -> None:
        self.scope = scope
        self.cat = catalog
        self.return_type = return_type
        self.body = _Body()
        self.break_targets: list[int] = []      # loops AND switch push here
        self.continue_targets: list[int] = []   # only loops push here

    # ── statements ────────────────────────────────────────────────────────────
    def stmt(self, s) -> None:
        method = getattr(self, f"_st_{s.kind}", None)
        if method is None:
            raise LowerError(f"statement {s.kind!r} not supported yet")
        method(s)

    def _st_local(self, s) -> None:
        pass                                            # declaration only; no code

    def _st_block(self, s) -> None:
        for inner in s.body:
            self.stmt(inner)

    def _st_expr(self, s) -> None:
        tok, _ = self.expr(s.exprs[0])
        self.body.tok(tok)

    def _st_assign(self, s) -> None:
        lhs, rhs = s.exprs
        ltok, ltype = self.expr(lhs)
        if s.text == "=":
            rtok, rtype = self.expr(rhs)
            rtok = self._coerce(rtok, rtype, ltype, fold=True)
            op = EX_LET_BOOL if ltype == "bool" else EX_LET
            self.body.tok(Tok(op, (("sub", ltok), ("sub", rtok))))
            return
        # compound assignment (`+=` …) is an operator over (out lhs, rhs)
        rtok, rtype = self.expr(rhs)
        self.body.tok(self._binary(s.text, ltok, ltype, rtok, rtype)[0])

    def _st_return(self, s) -> None:
        if not s.exprs:
            self.body.tok(Tok(EX_RETURN, (("sub", Tok(EX_NOTHING)),)))
            return
        tok, ty = self.expr(s.exprs[0])
        tok = self._coerce(tok, ty, self.return_type, fold=True)
        self.body.tok(Tok(EX_RETURN, (("sub", tok),)))

    def _st_if(self, s) -> None:
        end = self.body.new_label()
        clauses = list(s.clauses)
        for i, (cond, arm) in enumerate(clauses):
            last = i == len(clauses) - 1
            if cond is None:                            # else
                for inner in arm:
                    self.stmt(inner)
                continue
            skip = self.body.new_label()
            ctok, _ = self.expr(cond)
            self.body.jump_if_not(ctok, skip)
            for inner in arm:
                self.stmt(inner)
            if not last:
                self.body.jump(end)
            self.body.place(skip)
        self.body.place(end)

    def _st_while(self, s) -> None:
        top = self.body.new_label()
        end = self.body.new_label()
        self.body.place(top)
        ctok, _ = self.expr(s.exprs[0])
        self.body.jump_if_not(ctok, end)
        self.break_targets.append(end)
        self.continue_targets.append(top)
        for inner in s.body:
            self.stmt(inner)
        self.continue_targets.pop()
        self.break_targets.pop()
        self.body.jump(top)
        self.body.place(end)

    def _st_for(self, s) -> None:
        init, cond, update = s.exprs
        if init.op != "empty":
            self.body.tok(self._value(init))
        top = self.body.new_label()
        cont = self.body.new_label()
        end = self.body.new_label()
        self.body.place(top)
        if cond.op != "empty":
            ctok, _ = self.expr(cond)
            self.body.jump_if_not(ctok, end)
        self.break_targets.append(end)
        self.continue_targets.append(cont)
        for inner in s.body:
            self.stmt(inner)
        self.continue_targets.pop()
        self.break_targets.pop()
        self.body.place(cont)
        if update.op != "empty":
            self.body.tok(self._value(update))
        self.body.jump(top)
        self.body.place(end)

    def _st_switch(self, s) -> None:
        subject, = s.exprs
        stok, stype = self.expr(subject)
        self.body.tok(Tok(EX_SWITCH,
                          (("raw", bytes((_value_size(stype, self.scope.graph),))), ("sub", stok))))
        end = self.body.new_label()
        self.break_targets.append(end)
        for label, stmts in s.clauses:
            nxt = self.body.new_label()
            if label is None:                           # default
                self.body.case_default()
            else:
                vtok, vtype = self.expr(label)
                self.body.case(self._coerce(vtok, vtype, stype), nxt)
            for inner in stmts:
                self.stmt(inner)
            self.body.place(nxt)
        if not any(label is None for label, _ in s.clauses):
            self.body.case_default()                    # UCC emits an implicit body-less default
        self.break_targets.pop()
        self.body.place(end)

    def _st_break(self, s) -> None:
        if not self.break_targets:
            raise LowerError("break outside a loop/switch")
        self.body.jump(self.break_targets[-1])

    def _st_continue(self, s) -> None:
        if not self.continue_targets:
            raise LowerError("continue outside a loop")
        self.body.jump(self.continue_targets[-1])

    # ── expressions ───────────────────────────────────────────────────────────
    def _value(self, e: Expr) -> Tok:
        """A statement-position expression (for/init, for/update) as one token."""
        if e.op == "assign":
            ltok, ltype = self.expr(e.children[0])
            if e.text == "=":
                rtok, rtype = self.expr(e.children[1])
                rtok = self._coerce(rtok, rtype, ltype, fold=True)
                op = EX_LET_BOOL if ltype == "bool" else EX_LET
                return Tok(op, (("sub", ltok), ("sub", rtok)))
            rtok, rtype = self.expr(e.children[1])
            return self._binary(e.text, ltok, ltype, rtok, rtype)[0]
        return self.expr(e)[0]

    def expr(self, e: Expr) -> tuple[Tok, str]:
        method = getattr(self, f"_ex_{e.op}", None)
        if method is None:
            raise LowerError(f"expression {e.op!r} not supported yet")
        return method(e)

    def _ex_paren(self, e):
        return self.expr(e.children[0])

    def _ex_intconst(self, e):
        return _int_const(int(e.value)), "int"

    def _ex_floatconst(self, e):
        return Tok(EX_FLOAT_CONST, (("raw", struct.pack("<f", float(e.value))),)), "float"

    def _ex_stringconst(self, e):
        return Tok(EX_STRING_CONST,
                   (("raw", str(e.value).encode("latin-1", "replace") + b"\x00"),)), "string"

    def _ex_boolconst(self, e):
        return Tok(EX_TRUE if e.value else EX_FALSE), "bool"

    def _ex_nameconst(self, e):
        return Tok(EX_NAME_CONST, (("name", str(e.value)),)), "name"

    def _ex_noneconst(self, e):
        return Tok(EX_NO_OBJECT), "none"

    def _ex_new(self, e):
        """`new(outer,name,flags) ClassExpr` -> EX_New: four sub-exprs (outer, name, flags, class);
        an omitted paren arg is EX_Nothing. Returns a generic object instance."""
        *args, cls_expr = e.children
        ctok, _ctype = self.expr(cls_expr)
        targets = ("object:object", "name", "int")           # outer, name, flags
        subs = []
        for i in range(3):
            if i < len(args):
                atok, atype = self.expr(args[i])
                subs.append(("sub", self._coerce(atok, atype, targets[i], fold=True)))
            else:
                subs.append(("sub", Tok(EX_NOTHING)))
        subs.append(("sub", ctok))
        return Tok(EX_NEW, tuple(subs)), "object:object"

    def _ex_objref(self, e):
        """`Texture'Pkg.Name'` -> ObjectConst(0x20); the ref decodes to the object's leaf name."""
        val = e.value
        if val is None or str(val).casefold() == "none":
            return Tok(EX_NO_OBJECT), "none"
        leaf = str(val).rsplit(".", 1)[-1]
        ty = "class" if e.text.casefold() == "class" else f"object:{e.text.casefold()}"
        return Tok(EX_OBJECT_CONST, (("obj", leaf),)), ty

    def _ex_self(self, e):
        cls = (self.scope.class_name or "Object").casefold()
        return Tok(EX_SELF), f"object:{cls}"

    def _ex_name(self, e):
        sym = self.scope.lookup(e.text)
        if sym is None:
            ordinal = self.scope.enum_value(e.text)     # an enum tag -> ByteConst(ordinal)
            if ordinal is not None:
                return Tok(EX_BYTE_CONST, (("raw", bytes((ordinal & 0xFF,))),)), "byte"
            cexpr = self.scope.const_expr(e.text)        # a const -> its literal value
            if cexpr is not None:
                return self.expr(cexpr)
            raise LowerError(f"unresolved identifier {e.text!r}")
        op = EX_INSTANCE_VARIABLE if sym.storage == "member" else EX_LOCAL_VARIABLE
        return self._var(op, e.text, sym.type), sym.type

    @staticmethod
    def _var(op: int, field: str, ty: str) -> Tok:
        """A variable access, wrapped in BoolVariable when the field is bool."""
        var = Tok(op, (("obj", field),))
        return Tok(EX_BOOL_VARIABLE, (("sub", var),)) if ty == "bool" else var

    def _ex_member(self, e):
        """`base.field`: struct field -> StructMember(0x36); object field -> Context(0x19)."""
        base_tok, base_type = self.expr(e.children[0])
        field = e.text
        if _is_struct(base_type):
            ftype = self.scope.member_of(base_type, field)
            if ftype is None:
                raise LowerError(f"unresolved struct member {base_type}.{field}")
            tok = Tok(EX_STRUCT_MEMBER, (("obj", field), ("sub", base_tok)))
            if ftype == "bool":                         # a bool struct field reads via BoolVariable
                tok = Tok(EX_BOOL_VARIABLE, (("sub", tok),))
            return tok, ftype
        if _is_object(base_type):
            ftype = self.scope.member_of(base_type, field)
            if ftype is None:
                raise LowerError(f"unresolved member {base_type}.{field}")
            member = self._var(EX_INSTANCE_VARIABLE, field, ftype)
            return self._context(base_tok, member, ftype), ftype
        raise LowerError(f"member access on non-object/struct type {base_type!r}")

    def _context(self, base: Tok, member: Tok, member_type: str) -> Tok:
        size = _value_size(member_type, self.scope.graph)
        skip = struct.pack("<H", _mem_size(member)) + bytes((size,))
        return Tok(EX_CONTEXT, (("sub", base), ("raw", skip), ("sub", member)))

    def _ex_index(self, e):
        """`base[index]` -> ArrayElement(0x1A) = [index_expr][base_expr]; result is the element type
        (for a static array the element type is the variable's declared type label)."""
        base_tok, base_type = self.expr(e.children[0])
        idx_tok, idx_type = self.expr(e.children[1])
        if base_type == "array":
            raise LowerError("dynamic array element type unknown")
        idx_tok = self._coerce(idx_tok, idx_type, "int")  # index must be int (FloatToInt etc.)
        return Tok(EX_ARRAY_ELEMENT, (("sub", idx_tok), ("sub", base_tok))), base_type

    def _ex_unary(self, e):
        operand, ty = self.expr(e.children[0])
        if e.text in ("-", "+"):                         # unary +/- of a numeric literal folds
            cv = _const_num(operand)
            if cv is not None and ty in ("int", "float", "byte"):
                return _num_const(-cv if e.text == "-" else cv, ty), ty
        sym = _WORD_OPS.get(e.text.lower(), e.text)
        fb = self.cat.unary_operator(sym, ty, pre=True)
        if fb is None:
            raise LowerError(f"no preoperator {e.text!r} for {ty}")
        arg = self._coerce(operand, ty, fb.param_types[0], fold=True)
        return _native_call(fb, (arg,)), fb.return_type or ty

    def _ex_postfix(self, e):
        operand, ty = self.expr(e.children[0])
        fb = self.cat.unary_operator(e.text, ty, pre=False)
        if fb is None:
            raise LowerError(f"no postoperator {e.text!r} for {ty}")
        arg = self._coerce(operand, ty, fb.param_types[0])
        return _native_call(fb, (arg,)), fb.return_type or ty

    def _ex_binary(self, e):
        ltok, ltype = self.expr(e.children[0])
        rtok, rtype = self.expr(e.children[1])
        return self._binary(e.text, ltok, ltype, rtok, rtype)

    def _binary(self, op: str, ltok, ltype, rtok, rtype) -> tuple[Tok, str]:
        sym = _WORD_OPS.get(op.lower(), op)
        fb = self.cat.binary_operator(sym, ltype, rtype)
        if fb is None:
            raise LowerError(f"no operator {op!r} for ({ltype}, {rtype})")
        # UCC folds a constant LEFT operand into the param type, but converts the right at runtime.
        a = self._coerce(ltok, ltype, fb.param_types[0], fold=True)
        b = self._coerce(rtok, rtype, fb.param_types[1])
        if sym in ("&&", "||"):                          # short-circuit: skip the right operand
            b = Tok(EX_SKIP, (("raw", struct.pack("<H", _mem_size(b) + 1)), ("sub", b)))
        return _native_call(fb, (a, b)), fb.return_type or ltype

    def _ex_call(self, e):
        callee = e.children[0]
        args = e.children[1:]
        if callee.op == "name":
            return self._call_named(callee.text, args)
        if callee.op == "member":
            base = callee.children[0]
            if base.op == "super":                      # super.Method() / Super(Class).Method()
                return self._call_super(base.text, callee.text, args)
            return self._call_method(base, callee.text, args)
        raise LowerError(f"call target {callee.op!r} not supported yet")

    def _call_super(self, super_class: str, name: str, args) -> tuple[Tok, str]:
        """A super call resolves to the parent's function by NAME via FinalFunction (no virtual
        dispatch). `super_class` is the explicit `Super(Class)` target, else the immediate super."""
        base_cls = super_class or self.scope.super_name
        tgt = None
        if self.scope.graph and base_cls:
            fb = self.scope.graph.function(base_cls, name)
            if fb is not None:
                tgt = _target_of(fb)
        arg_toks, arg_types = self._lower_args(args)
        if tgt is not None:
            coerced = self._coerce_args(arg_toks, arg_types, tgt.param_types)
            ret = tgt.return_type or "none"
        elif arg_toks:
            raise LowerError(f"unresolved super call {base_cls}.{name} with args")
        else:
            coerced, ret = arg_toks, "none"
        run = tuple(coerced) + (Tok(EX_END_FUNCTION_PARMS),)
        return Tok(EX_FINAL_FUNCTION, (("obj", name), ("parms", run))), ret

    def _lower_args(self, args) -> tuple[list[Tok], list[str]]:
        toks: list[Tok] = []
        types: list[str] = []
        for a in args:
            if a.op == "empty":                         # a skipped optional argument
                toks.append(Tok(EX_NOTHING))
                types.append("none")
                continue
            tok, ty = self.expr(a)
            toks.append(tok)
            types.append(ty)
        return toks, types

    def _call_named(self, name: str, args) -> tuple[Tok, str]:
        low = name.casefold()
        if low in _PRIMITIVE_TYPES and len(args) == 1:  # primitive cast `int(x)`
            tok, ty = self.expr(args[0])
            return self._coerce(tok, ty, low), low
        if low.startswith("class<") and len(args) == 1:  # metaclass cast `class<Actor>(c)`
            meta = name[len("class<"):-1].strip().rsplit(".", 1)[-1]
            inner, _ = self.expr(args[0])
            return Tok(EX_METACAST, (("obj", meta), ("sub", inner))), "class"
        if len(args) == 1 and self.scope.is_class_name(name):   # object cast `Pawn(x)`
            inner, _ = self.expr(args[0])
            return Tok(EX_DYNAMIC_CAST, (("obj", name), ("sub", inner))), f"object:{low}"
        arg_toks, arg_types = self._lower_args(args)
        tgt = self.scope.func(name)
        if tgt is None:
            fb = self.cat.function(name, tuple(arg_types))
            if fb is None:
                raise LowerError(f"unresolved function {name!r}")
            tgt = _target_of(fb)
        return self._emit_target(tgt, arg_toks, arg_types)

    def _call_method(self, base: Expr, name: str, args) -> tuple[Tok, str]:
        base_tok, base_type = self.expr(base)
        if not _is_object(base_type):
            raise LowerError(f"method call on non-object type {base_type!r}")
        tgt = self.scope.method_of(base_type, name)
        if tgt is None:
            raise LowerError(f"unresolved method {base_type}.{name}")
        arg_toks, arg_types = self._lower_args(args)
        call, ret = self._emit_target(tgt, arg_toks, arg_types)
        return self._context(base_tok, call, ret), ret

    def _emit_target(self, tgt: CallTarget, arg_toks, arg_types) -> tuple[Tok, str]:
        coerced = self._coerce_args(arg_toks, arg_types, tgt.param_types)
        ret = tgt.return_type or "none"
        if tgt.native_index:
            return _emit_native(tgt.native_index, tgt.name, coerced), ret
        run = tuple(coerced) + (Tok(EX_END_FUNCTION_PARMS),)
        if tgt.is_final:
            return Tok(EX_FINAL_FUNCTION, (("obj", tgt.name), ("parms", run))), ret
        return Tok(EX_VIRTUAL_FUNCTION, (("name", tgt.name), ("parms", run))), ret

    # ── helpers ───────────────────────────────────────────────────────────────
    def _coerce_args(self, toks, types, params) -> tuple[Tok, ...]:
        """Coerce each argument to its parameter type (function calls fold numeric constants); extra
        args (optional params) pass through."""
        fixed = tuple(self._coerce(t, at, pt, fold=True) for t, at, pt in zip(toks, types, params))
        return fixed + tuple(toks[len(params):])

    def _coerce(self, tok: Tok, ftype: str, ttype: str | None, *, fold: bool = False) -> Tok:
        """Coerce `tok` from `ftype` to `ttype`. `fold` folds a numeric literal into the target const
        form (return/assignment/function-arg context); operators keep the runtime conversion."""
        if ttype is None or ftype == ttype or ttype == "none":
            return tok
        if (_is_object(ftype) or ftype == "class") and (_is_object(ttype) or ttype == "class"):
            return tok                                  # object/class ref: no conversion
        if ftype == "none" and (_is_object(ttype) or _is_struct(ttype)
                                or ttype in ("class", "name")):
            return tok                                  # NoObject already the right null const
        if fold and ttype in ("int", "float", "byte"):
            cv = _const_num(tok)                        # a numeric literal folds at compile time
            if cv is not None:
                return _num_const(cv, ttype)
        op = _CONV.get((ftype, ttype))
        if op is not None:
            return Tok(op, (("sub", tok),))
        raise LowerError(f"no conversion {ftype!r} -> {ttype!r}")


def canon(tok: Tok) -> Tok:
    """Casefold every obj/name identity in a token tree. UE1 `FName` is case-insensitive but the
    editor spells locals/params from its boot global name pool (e.g. `A`, `X`), not the source — the
    owner+opus-blessed FName-case exclusion. Comparing canon() forms ignores that spelling."""
    parts = []
    for part in tok.parts:
        match part:
            case ("obj", ident) | ("name", ident):
                parts.append((part[0], ident.casefold()))
            case ("sub", t):
                parts.append(("sub", canon(t)))
            case ("parms", run):
                parts.append(("parms", tuple(canon(t) for t in run)))
            case _:
                parts.append(part)
    return Tok(tok.op, tuple(parts))


def toks_equal(a: list[Tok], b: list[Tok]) -> bool:
    """Token-stream equality modulo FName case (see `canon`)."""
    return [canon(t) for t in a] == [canon(t) for t in b]


def _const_num(tok: Tok):
    """The numeric value of a constant token (int/float/byte const), else None."""
    op = tok.op
    if op == EX_INT_ZERO:
        return 0
    if op == EX_INT_ONE:
        return 1
    if op in (EX_INT_CONST_BYTE, EX_BYTE_CONST):
        return tok.parts[0][1][0]
    if op == EX_INT_CONST:
        return struct.unpack("<i", tok.parts[0][1])[0]
    if op == EX_FLOAT_CONST:
        return struct.unpack("<f", tok.parts[0][1])[0]
    return None


def _num_const(value, ttype: str) -> Tok:
    if ttype == "float":
        return Tok(EX_FLOAT_CONST, (("raw", struct.pack("<f", float(value))),))
    if ttype == "byte":
        return Tok(EX_BYTE_CONST, (("raw", bytes((int(value) & 0xFF,))),))
    return _int_const(int(value))


def _int_const(v: int) -> Tok:
    if v == 0:
        return Tok(EX_INT_ZERO)
    if v == 1:
        return Tok(EX_INT_ONE)
    if 0 <= v <= 255:
        return Tok(EX_INT_CONST_BYTE, (("raw", bytes((v,))),))
    return Tok(EX_INT_CONST, (("raw", struct.pack("<i", v)),))


def _native_call(fb: FuncBody, args: tuple[Tok, ...]) -> Tok:
    return _emit_native(fb.inative, fb.name, args)


def _emit_native(idx: int, name: str, args: tuple[Tok, ...]) -> Tok:
    """A native-opcode call: single-byte (0x70..0xFF) or ExtendedNative (0x60|hi, lo byte)."""
    run = args + (Tok(EX_END_FUNCTION_PARMS),)
    if EX_FIRST_NATIVE <= idx <= 0xFF:
        return Tok(idx, (("parms", run),))
    if 0x100 <= idx <= 0xFFF:
        return Tok(EX_EXTENDED_NATIVE | (idx >> 8),
                   (("raw", bytes((idx & 0xFF,))), ("parms", run)))
    raise LowerError(f"native index {idx} out of the 0x70..0xFFF call range ({name!r})")
