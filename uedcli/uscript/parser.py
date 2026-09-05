"""Recursive-descent parser for UED22 UnrealScript.

`parse(src)` turns one `.uc` class file into the `ClassDecl` AST (`ast.py`). It consumes the flat
token stream from `lex()` (`lexer.py`); UnrealScript keywords are contextual, so this classifies the
`Tok.IDENT` tokens by position, matching them case-insensitively as the compiler does.

The grammar covered is the full UED22 surface: the class header and its modifiers, `const`/`enum`/
`struct`/`var` members (in declaration order), functions/events/operators/delegates, states,
`replication`, `defaultproperties`, `cpptext`, and `#exec` directives. Statements and expressions use
the AST's generic `Stmt`/`Expr` nodes but keep operator identity, operands, and nesting so a later
bytecode emitter can walk them.

Errors raise `ParseError` naming the offending token with 1-based line/col.
"""
from __future__ import annotations

from .ast import (
    ClassDecl, ConstDecl, DefaultProp, EnumDecl, Expr, FuncDecl, Param, ReplBlock, StateDecl, Stmt,
    StructDecl, TypeRef, VarDecl,
)
from .lexer import lex
from .tokens import Tok, Token

__all__ = ["parse", "ParseError"]


class ParseError(Exception):
    """A token the parser cannot accept, with the offending spelling and 1-based line/col."""


# Keyword sets (matched case-insensitively against IDENT text).
_PRIMITIVES = {"int", "float", "bool", "byte", "string", "name"}
_FUNC_KW = {"function", "event", "delegate", "operator", "preoperator", "postoperator"}
_FUNC_MODS = {"static", "final", "simulated", "latent", "iterator", "singular", "exec", "private",
              "protected", "public", "const", "native", "intrinsic", "noexport", "reliable",
              "unreliable", "server", "client"}
_STATE_MODS = {"auto", "simulated"}
_CALLABLE_MODS = _FUNC_MODS | _STATE_MODS  # leading modifiers shared by functions and states
_PARAM_MODS = {"out", "optional", "coerce", "skip", "const"}
_VAR_MODS = {"const", "config", "globalconfig", "localized", "transient", "native", "intrinsic",
             "private", "protected", "public", "edfindable", "editconst", "editconstarray",
             "export", "noexport", "deprecated", "input", "travel", "cache", "automated",
             "editinline", "editinlinenotify", "editinlineuse", "edithide", "nocontraststrong",
             "duplicatetransient"}
_ASSIGN_OPS = {"=", "+=", "-=", "*=", "/=", "@=", "$="}
# Word-spelled infix operators and their UnrealScript precedences: Dot/Cross are 16 (like `*`),
# ClockwiseFrom is a bool comparison at 24.
_WORD_BINOPS = {"dot": 16, "cross": 16, "clockwisefrom": 24}

# Binary operator precedence, UnrealScript convention: LOWER number binds TIGHTER.
_BINOPS: dict[str, int] = {
    "**": 12,
    "*": 16, "/": 16,
    "%": 18,
    "+": 20, "-": 20,
    "<<": 22, ">>": 22, ">>>": 22,
    "<": 24, ">": 24, "<=": 24, ">=": 24, "==": 24, "~=": 24, "!=": 26,
    "&": 28, "|": 28, "^": 28,
    "&&": 30, "^^": 30,
    "||": 32,
    "$": 40, "@": 40,
}


def parse(src: str) -> ClassDecl:
    """Parse one UnrealScript class file into a `ClassDecl` (its `source` set to `src` verbatim)."""
    return _Parser(src).parse()


class _Parser:
    def __init__(self, src: str) -> None:
        self.raw = src
        # The lexer strips a leading BOM; mirror it so token line/col map onto this string.
        self._body = src[1:] if src.startswith("﻿") else src
        self.toks = lex(src)
        self.pos = 0
        self._line_starts = self._compute_line_starts(self._body)
        # Inline enum/struct declared as a struct member's type is class-scoped in UnrealScript;
        # collected here and appended to ClassDecl.members so its definition is never dropped.
        self._hoisted: list[object] = []

    # ── low-level cursor ────────────────────────────────────────────────────
    @staticmethod
    def _compute_line_starts(text: str) -> list[int]:
        starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                starts.append(i + 1)
        return starts

    def _offset(self, tok: Token) -> int:
        """Absolute index of `tok` in the (BOM-stripped) source, for verbatim raw slices."""
        return self._line_starts[tok.line - 1] + tok.col - 1

    def _peek(self, ahead: int = 0) -> Token:
        i = self.pos + ahead
        return self.toks[i] if i < len(self.toks) else self.toks[-1]

    def _advance(self) -> Token:
        tok = self.toks[self.pos]
        if tok.kind is not Tok.EOF:
            self.pos += 1
        return tok

    def _error(self, msg: str, tok: Token | None = None) -> ParseError:
        tok = tok or self._peek()
        shown = tok.text if tok.kind is not Tok.EOF else "<eof>"
        return ParseError(f"{msg}: {shown!r} at line {tok.line}, col {tok.col}")

    def _kw(self, tok: Token | None = None) -> str | None:
        """The lowercased keyword of an IDENT token, else None."""
        tok = tok or self._peek()
        return tok.text.lower() if tok.kind is Tok.IDENT else None

    def _at_op(self, *ops: str) -> bool:
        tok = self._peek()
        return tok.kind is Tok.OP and tok.text in ops

    def _at_kw(self, *kws: str) -> bool:
        return self._kw() in kws

    def _expect_op(self, op: str) -> Token:
        if not self._at_op(op):
            raise self._error(f"expected {op!r}")
        return self._advance()

    def _expect_ident(self) -> str:
        tok = self._peek()
        if tok.kind is not Tok.IDENT:
            raise self._error("expected identifier")
        return self._advance().text

    def _eat_kw(self, *kws: str) -> str | None:
        """Consume and return the lowercased keyword if it matches, else None."""
        if self._at_kw(*kws):
            return self._advance().text.lower()
        return None

    def _expect_gt(self) -> None:
        """Consume one closing `>`, splitting a `>>`/`>>>` token so nested `array<class<X>>` closes."""
        tok = self._peek()
        if tok.kind is not Tok.OP or not tok.text.startswith(">"):
            raise self._error("expected '>'")
        rest = tok.text[1:]
        if rest:
            self.toks[self.pos] = Token(kind=Tok.OP, text=rest, line=tok.line, col=tok.col + 1)
        else:
            self._advance()

    # ── top level ───────────────────────────────────────────────────────────
    def parse(self) -> ClassDecl:
        name, super_name, within, modifiers = self._parse_header()
        members: list[object] = []
        functions: list[FuncDecl] = []
        states: list[StateDecl] = []
        replication: ReplBlock | None = None
        default_props: tuple[DefaultProp, ...] = ()
        exec_directives: list[str] = []
        cpptext_parts: list[str] = []

        while self._peek().kind is not Tok.EOF:
            tok = self._peek()
            if tok.kind is Tok.EXEC:
                exec_directives.append(self._advance().text)
                continue
            if tok.kind is Tok.OP and tok.text == ";":
                self._advance()
                continue
            kw = self._kw()
            if kw == "const":
                members.append(self._parse_const())
            elif kw == "enum":
                members.append(self._parse_enum())
                self._eat_op_optional(";")
            elif kw == "struct":
                members.append(self._parse_struct())
                self._eat_op_optional(";")
            elif kw == "var":
                members.extend(self._parse_var())
            elif kw == "replication":
                replication = self._parse_replication()
            elif kw == "defaultproperties":
                default_props = self._parse_defaultproperties()
            elif kw in ("cpptext", "structcpptext"):
                cpptext_parts.append(self._parse_cpptext())
            else:
                decl = self._parse_callable_or_state()
                if isinstance(decl, StateDecl):
                    states.append(decl)
                else:
                    functions.append(decl)

        members.extend(self._hoisted)  # inline enum/struct lifted out of struct members
        return ClassDecl(
            name=name, super_name=super_name, within=within, modifiers=tuple(modifiers),
            members=tuple(members), functions=tuple(functions), states=tuple(states),
            replication=replication, default_props=default_props,
            exec_directives=tuple(exec_directives), source=self.raw,
            cpptext="\n".join(cpptext_parts) if cpptext_parts else None)

    def _eat_op_optional(self, op: str) -> None:
        if self._at_op(op):
            self._advance()

    def _parse_header(self) -> tuple[str, str | None, str | None, list[str]]:
        if self._eat_kw("class") is None:
            raise self._error("expected 'class' at file start")
        name = self._expect_ident()
        super_name: str | None = None
        within: str | None = None
        modifiers: list[str] = []
        while not self._at_op(";"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated class header (missing ';')")
            kw = self._kw()
            if kw in ("extends", "expands"):
                self._advance()
                super_name = self._parse_dotted_name()
            elif kw == "within":
                self._advance()
                within = self._parse_dotted_name()
            else:
                modifiers.append(self._parse_modifier())
        self._advance()  # ';'
        return name, super_name, within, modifiers

    def _parse_dotted_name(self) -> str:
        """A class/super name, possibly `Package.Class`."""
        parts = [self._expect_ident()]
        while self._at_op("."):
            self._advance()
            parts.append(self._expect_ident())
        return ".".join(parts)

    def _parse_modifier(self) -> str:
        """One class/struct modifier, lowercased keyword with its `(args)` kept verbatim."""
        tok = self._peek()
        if tok.kind is not Tok.IDENT:
            raise self._error("expected class modifier")
        self._advance()
        kw = tok.text.lower()
        if self._at_op("("):
            return kw + self._raw_paren_group()
        return kw

    def _raw_paren_group(self) -> str:
        """Consume a balanced `(...)` and return its source text verbatim, parens included."""
        open_tok = self._expect_op("(")
        depth = 1
        while depth:
            t = self._peek()
            if t.kind is Tok.EOF:
                raise self._error("unterminated '(' group", open_tok)
            if t.kind is Tok.OP and t.text == "(":
                depth += 1
            elif t.kind is Tok.OP and t.text == ")":
                depth -= 1
            self._advance()
            if depth == 0:
                close_tok = t
        return self._body[self._offset(open_tok):self._offset(close_tok) + 1]

    # ── types ─────────────────────────────────────────────────────────────
    def _parse_type(self) -> TypeRef:
        tok = self._peek()
        kw = self._kw()
        if kw == "array":
            self._advance()
            self._expect_op("<")
            inner = self._parse_type()
            array_size: int | None = None
            if self._at_op(","):  # Deus Ex sized array `array<T,N>`
                self._advance()
                array_size = self._parse_int_dim()
            self._expect_gt()
            return TypeRef(base="array", inner=inner, array_size=array_size)
        if kw == "class":
            self._advance()
            if self._at_op("<"):
                self._advance()
                meta = self._parse_dotted_name()
                self._expect_gt()
                return TypeRef(base="class", meta_class=meta)
            return TypeRef(base="class")
        if kw == "string":
            self._advance()
            if self._at_op("["):
                self._advance()
                size = self._parse_int_dim()
                self._expect_op("]")
                return TypeRef(base="string", string_size=size)
            return TypeRef(base="string")
        if tok.kind is not Tok.IDENT:
            raise self._error("expected a type")
        self._advance()
        base = tok.text
        # A struct/enum/class type may be qualified (`Package.Type`); preserve the dotted form.
        if self._at_op(".") and kw not in _PRIMITIVES:
            parts = [base]
            while self._at_op("."):
                self._advance()
                parts.append(self._expect_ident())
            base = ".".join(parts)
        return TypeRef(base=base)

    def _parse_int_dim(self) -> int:
        tok = self._peek()
        if tok.kind is not Tok.INT:
            raise self._error("expected an integer size")
        self._advance()
        return int(tok.value)

    def _parse_paren_int(self) -> int:
        """`( INT )` — the count in `native(N)`/`operator(N)`; a non-int raises ParseError."""
        self._expect_op("(")
        n = self._parse_int_dim()
        self._expect_op(")")
        return n

    # ── members: const / enum / struct / var ────────────────────────────────
    def _parse_const(self) -> ConstDecl:
        self._advance()  # 'const'
        name = self._expect_ident()
        self._expect_op("=")
        value = self._parse_expr()
        self._eat_op_optional(";")
        return ConstDecl(name=name, value=value)

    def _parse_enum(self) -> EnumDecl:
        self._advance()  # 'enum'
        return self._parse_enum_body()

    def _parse_enum_body(self) -> EnumDecl:
        name = self._expect_ident()
        self._expect_op("{")
        values: list[str] = []
        while not self._at_op("}"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated enum body")
            values.append(self._expect_ident())
            if not self._at_op(","):
                break
            self._advance()
        self._expect_op("}")
        return EnumDecl(name=name, values=tuple(values))

    def _parse_struct(self) -> StructDecl:
        self._advance()  # 'struct'
        return self._parse_struct_body()

    def _parse_struct_body(self) -> StructDecl:
        # `struct [modifiers...] NAME [extends BASE] { members }` — the last ident before `extends`
        # or `{` is the name; earlier idents are modifiers.
        idents: list[str] = []
        while self._peek().kind is Tok.IDENT and not self._at_kw("extends", "expands"):
            idents.append(self._advance().text)
            if self._at_op("{"):
                break
        if not idents:
            raise self._error("expected a struct name")
        name = idents[-1]
        modifiers = tuple(m.lower() for m in idents[:-1])
        base: str | None = None
        if self._eat_kw("extends", "expands") is not None:
            base = self._parse_dotted_name()
        self._expect_op("{")
        members: list[VarDecl] = []
        while not self._at_op("}"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated struct body")
            if self._at_kw("var"):
                for decl in self._parse_var():
                    (members if isinstance(decl, VarDecl) else self._hoisted).append(decl)
            elif self._at_kw("structcpptext", "cpptext"):
                self._parse_cpptext()
            elif self._at_op(";"):
                self._advance()
            else:
                raise self._error("expected 'var' inside struct")
        self._expect_op("}")
        return StructDecl(name=name, base=base, modifiers=modifiers, members=tuple(members))

    def _parse_var(self) -> list[object]:
        """Parse a `var`/`local`-style declaration. Returns the VarDecl(s) plus any inline
        enum/struct declared as the type (those come first, so they register as members too)."""
        self._advance()  # 'var' (or 'local')
        category: str | None = None
        if self._at_op("("):
            inner = self._raw_paren_group()
            category = inner[1:-1]  # strip the parens; "" for a bare `var()`
        modifiers: list[str] = []
        while self._kw() in _VAR_MODS:
            modifiers.append(self._advance().text.lower())

        extra: list[object] = []
        if self._at_kw("enum"):
            self._advance()
            enum_decl = self._parse_enum_body()
            extra.append(enum_decl)
            vtype = TypeRef(base=enum_decl.name)
        elif self._at_kw("struct"):
            self._advance()
            struct_decl = self._parse_struct_body()
            extra.append(struct_decl)
            vtype = TypeRef(base=struct_decl.name)
        else:
            vtype = self._parse_type()

        named = self._parse_var_names()
        self._eat_op_optional(";")
        decls = self._build_var_decls(named, vtype, tuple(modifiers), category)
        return extra + decls

    @staticmethod
    def _build_var_decls(named: list[tuple[str, int | str | None]], vtype: TypeRef,
                         modifiers: tuple[str, ...], category: str | None) -> list[object]:
        """Group names sharing a type into one VarDecl; split out any with a distinct static dim so
        no per-name array size is lost."""
        if all(dim is None for _, dim in named) and len(named) > 1:
            return [VarDecl(names=tuple(n for n, _ in named), type=vtype, modifiers=modifiers,
                            category=category, array_dim=None)]
        return [VarDecl(names=(n,), type=vtype, modifiers=modifiers, category=category,
                        array_dim=dim) for n, dim in named]

    def _parse_var_names(self) -> list[tuple[str, int | str | None]]:
        names: list[tuple[str, int | str | None]] = []
        while True:
            name = self._expect_ident()
            dim: int | str | None = None
            if self._at_op("["):
                self._advance()
                dtok = self._peek()
                if dtok.kind is Tok.INT:
                    dim = int(self._advance().value)
                elif dtok.kind is Tok.IDENT:
                    dim = self._parse_dotted_name()
                else:
                    raise self._error("expected an array size")
                self._expect_op("]")
            names.append((name, dim))
            if not self._at_op(","):
                return names
            self._advance()

    # ── functions / operators / states ──────────────────────────────────────
    def _parse_callable_or_state(self) -> FuncDecl | StateDecl:
        modifiers: list[str] = []
        native_index: int | None = None
        while self._kw() in _CALLABLE_MODS and not self._at_kw(*_FUNC_KW, "state"):
            kw = self._advance().text.lower()
            if kw in ("native", "intrinsic") and self._at_op("("):
                native_index = self._parse_paren_int()
            modifiers.append(kw)
        if self._at_kw("state"):
            return self._parse_state(modifiers)
        if self._at_kw(*_FUNC_KW):
            return self._parse_function(modifiers, native_index)
        raise self._error("expected a function, operator, or state")

    def _parse_function(self, modifiers: list[str], native_index: int | None) -> FuncDecl:
        kind = self._advance().text.lower()
        oper_precedence: int | None = None
        if kind == "operator" and self._at_op("("):
            oper_precedence = self._parse_paren_int()

        if self._eat_kw("coerce") is not None:  # a coerced return type (rare)
            modifiers.append("coerce")
        return_type, name = self._parse_return_and_name(kind in ("operator", "preoperator",
                                                                  "postoperator"))
        params = self._parse_params()
        if self._at_op(";"):
            self._advance()
            return FuncDecl(name=name, kind=kind, modifiers=tuple(modifiers),
                            native_index=native_index, oper_precedence=oper_precedence,
                            return_type=return_type, params=params, has_body=False)
        locals_, body = self._parse_func_body()
        return FuncDecl(name=name, kind=kind, modifiers=tuple(modifiers), native_index=native_index,
                        oper_precedence=oper_precedence, return_type=return_type, params=params,
                        locals=locals_, body=body, has_body=True)

    def _parse_return_and_name(self, is_operator: bool) -> tuple[TypeRef | None, str]:
        if is_operator:
            if self._peek().kind is Tok.IDENT:
                rtype = self._parse_type()
                if self._at_op("("):
                    return None, rtype.base
                return rtype, self._parse_operator_name()
            return None, self._parse_operator_name()
        rtype = self._parse_type()
        if self._at_op("("):
            return None, rtype.base
        return rtype, self._expect_ident()

    def _parse_operator_name(self) -> str:
        tok = self._peek()
        if tok.kind in (Tok.OP, Tok.IDENT):
            return self._advance().text
        raise self._error("expected an operator name")

    def _parse_params(self) -> tuple[Param, ...]:
        self._expect_op("(")
        params: list[Param] = []
        while not self._at_op(")"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated parameter list")
            mods: list[str] = []
            while self._kw() in _PARAM_MODS:
                mods.append(self._advance().text.lower())
            ptype = self._parse_type()
            pname = self._expect_ident()
            if self._at_op("["):  # array parameter (rare) — consume the size, keep the name
                self._advance()
                self._parse_var_names_dim()
                self._expect_op("]")
            default: Expr | None = None
            if self._at_op("="):
                self._advance()
                default = self._parse_expr()
            params.append(Param(name=pname, type=ptype, modifiers=tuple(mods), default=default))
            if not self._at_op(","):
                break
            self._advance()
        self._expect_op(")")
        return tuple(params)

    def _parse_var_names_dim(self) -> None:
        tok = self._peek()
        if tok.kind in (Tok.INT, Tok.IDENT):
            self._advance()

    def _parse_func_body(self) -> tuple[tuple[VarDecl, ...], tuple[Stmt, ...]]:
        self._expect_op("{")
        locals_: list[VarDecl] = []
        body: list[Stmt] = []
        while not self._at_op("}"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated function body")
            if self._at_kw("local"):
                locals_.extend(self._parse_local())
                continue
            stmt = self._parse_statement()
            if stmt is not None:
                body.append(stmt)
        self._expect_op("}")
        return tuple(locals_), tuple(body)

    def _parse_local(self) -> list[VarDecl]:
        self._advance()  # 'local'
        vtype = self._parse_type()
        named = self._parse_var_names()
        self._eat_op_optional(";")
        return [d for d in self._build_var_decls(named, vtype, (), None) if isinstance(d, VarDecl)]

    def _parse_state(self, modifiers: list[str]) -> StateDecl:
        self._advance()  # 'state'
        if self._at_op("("):
            self._raw_paren_group()  # editable `state()` marker — no content we track
        name = self._expect_ident()
        base: str | None = None
        if self._eat_kw("extends", "expands") is not None:
            base = self._parse_dotted_name()
        self._expect_op("{")
        ignores: list[str] = []
        funcs: list[FuncDecl] = []
        body: list[Stmt] = []
        while not self._at_op("}"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated state body")
            if self._at_kw("ignores"):
                ignores.extend(self._parse_ignores())
                continue
            fn = self._try_parse_state_function()
            if fn is not None:
                funcs.append(fn)
                continue
            stmt = self._parse_statement()
            if stmt is not None:
                body.append(stmt)
        self._expect_op("}")
        return StateDecl(name=name, base=base, modifiers=tuple(modifiers), ignores=tuple(ignores),
                         funcs=tuple(funcs), body=tuple(body))

    def _parse_ignores(self) -> list[str]:
        self._advance()  # 'ignores'
        names: list[str] = []
        while not self._at_op(";"):
            names.append(self._expect_ident())
            if self._at_op(","):
                self._advance()
            elif not self._at_op(";"):
                raise self._error("expected ',' or ';' in ignores")
        self._advance()  # ';'
        return names

    def _try_parse_state_function(self) -> FuncDecl | None:
        """A state body mixes function definitions with labelled statements; commit to a function
        only if a modifier run leads to a function keyword, else rewind for statement parsing."""
        start = self.pos
        while self._kw() in _FUNC_MODS and not self._at_kw(*_FUNC_KW):
            self._advance()
        if self._at_kw(*_FUNC_KW):
            self.pos = start
            decl = self._parse_callable_or_state()
            assert isinstance(decl, FuncDecl), "modifier run led to 'state' inside a state body"
            return decl
        self.pos = start
        return None

    # ── replication / defaultproperties / cpptext ───────────────────────────
    def _parse_replication(self) -> ReplBlock:
        self._advance()  # 'replication'
        self._expect_op("{")
        entries: list[tuple[bool, Expr, tuple[str, ...]]] = []
        while not self._at_op("}"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated replication block")
            reliable = True
            rel = self._eat_kw("reliable", "unreliable")
            if rel is not None:
                reliable = rel == "reliable"
            if self._eat_kw("if") is None:
                raise self._error("expected 'if' in replication entry")
            self._expect_op("(")
            cond = self._parse_expr()
            self._expect_op(")")
            names: list[str] = []
            while not self._at_op(";"):
                names.append(self._expect_ident())
                if self._at_op(","):
                    self._advance()
                elif not self._at_op(";"):
                    raise self._error("expected ',' or ';' in replication names")
            self._advance()  # ';'
            entries.append((reliable, cond, tuple(names)))
        self._expect_op("}")
        return ReplBlock(entries=tuple(entries))

    def _parse_cpptext(self) -> str:
        self._advance()  # 'cpptext' / 'structcpptext'
        open_tok = self._expect_op("{")
        depth = 1
        close_tok = open_tok
        while depth:
            t = self._peek()
            if t.kind is Tok.EOF:
                raise self._error("unterminated cpptext block", open_tok)
            if t.kind is Tok.OP and t.text == "{":
                depth += 1
            elif t.kind is Tok.OP and t.text == "}":
                depth -= 1
            self._advance()
            if depth == 0:
                close_tok = t
        return self._body[self._offset(open_tok) + 1:self._offset(close_tok)]

    def _parse_defaultproperties(self) -> tuple[DefaultProp, ...]:
        self._advance()  # 'defaultproperties'
        self._expect_op("{")
        props: list[DefaultProp] = []
        while not self._at_op("}"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated defaultproperties block")
            name = self._expect_ident()
            index: int | None = None
            if self._at_op("("):
                self._advance()
                index = self._parse_int_dim()
                self._expect_op(")")
            elif self._at_op("["):
                self._advance()
                index = self._parse_int_dim()
                self._expect_op("]")
            eq = self._expect_op("=")
            # A defaultproperties assignment is one line; a value on a later line means it is empty
            # (native/pointer fields decompile as `Name=` with nothing after the `=`).
            if self._peek().line != eq.line or self._at_op("}"):
                value: Expr = Expr(op="empty")
            else:
                value = self._parse_default_value()
            props.append(DefaultProp(name=name, array_index=index, value=value))
        self._expect_op("}")
        return tuple(props)

    def _parse_default_value(self) -> Expr:
        if self._at_op("("):
            return self._parse_struct_literal()
        return self._parse_default_scalar()

    def _parse_struct_literal(self) -> Expr:
        self._expect_op("(")
        fields: list[Expr] = []
        while not self._at_op(")"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated struct literal")
            if self._peek().kind is Tok.IDENT and (self._peek(1).kind is Tok.OP
                                                   and self._peek(1).text in ("=", "(", "[")):
                key = self._advance().text
                idx: int | None = None
                if self._at_op("(", "["):
                    close = ")" if self._advance().text == "(" else "]"
                    idx = self._parse_int_dim()
                    self._expect_op(close)
                self._expect_op("=")
                val = self._parse_default_value()
                fields.append(Expr(op="field", text=key, value=idx, children=(val,)))
            else:
                fields.append(Expr(op="field", text="", children=(self._parse_default_value(),)))
            if self._at_op(","):
                self._advance()
            elif not self._at_op(")"):
                raise self._error("expected ',' or ')' in struct literal")
        self._expect_op(")")
        return Expr(op="struct", children=tuple(fields))

    def _parse_default_scalar(self) -> Expr:
        sign = ""
        if self._at_op("-", "+"):
            sign = self._advance().text
        tok = self._peek()
        if tok.kind is Tok.INT:
            self._advance()
            return Expr(op="intconst", value=-tok.value if sign == "-" else tok.value,
                        text=sign + tok.text)
        if tok.kind is Tok.FLOAT:
            self._advance()
            return Expr(op="floatconst", value=-tok.value if sign == "-" else tok.value,
                        text=sign + tok.text)
        if tok.kind is Tok.STRING:
            self._advance()
            return Expr(op="stringconst", value=tok.value, text=tok.text)
        if tok.kind is Tok.NAME:
            self._advance()
            return Expr(op="nameconst", value=tok.value, text=tok.text)
        if tok.kind is Tok.IDENT:
            ident = self._advance().text
            low = ident.lower()
            if self._peek().kind is Tok.NAME:  # object literal `Texture'Pkg.Name'`
                nt = self._advance()
                return Expr(op="objref", text=ident, value=nt.value)
            if low in ("true", "false"):
                return Expr(op="boolconst", value=low == "true", text=ident)
            if low == "none":
                return Expr(op="noneconst", text=ident)
            return Expr(op="name", text=ident)
        raise self._error("expected a default value")

    # ── statements ───────────────────────────────────────────────────────────
    def _parse_statement(self) -> Stmt | None:
        tok = self._peek()
        if tok.kind is Tok.OP and tok.text == ";":
            self._advance()
            return None
        if tok.kind is Tok.OP and tok.text == "{":
            return Stmt(kind="block", body=self._parse_block())
        kw = self._kw()
        if kw == "local":
            decls = self._parse_local()
            return Stmt(kind="local", local_type=decls[0].type if decls else None,
                        names=tuple(n for d in decls for n in d.names))
        handler = {
            "if": self._parse_if, "for": self._parse_for, "while": self._parse_while,
            "do": self._parse_do, "switch": self._parse_switch, "return": self._parse_return,
            "break": self._parse_break, "continue": self._parse_continue, "goto": self._parse_goto,
            "foreach": self._parse_foreach, "assert": self._parse_assert, "stop": self._parse_stop,
        }.get(kw)
        # `stop`/`break`/`continue` are bare keywords; if one is used as an identifier (a `Stop()`
        # call, `break.x`, `continue[i]`), fall through to expression parsing.
        if handler is not None and kw in ("stop", "break", "continue") and (
                self._peek(1).kind is Tok.OP and self._peek(1).text in ("(", ".", "[")):
            handler = None
        if handler is not None:
            return handler()
        # A label is `IDENT :` at statement start.
        if tok.kind is Tok.IDENT and self._peek(1).kind is Tok.OP and self._peek(1).text == ":":
            self._advance()
            self._advance()
            return Stmt(kind="label", names=(tok.text,))
        return self._parse_expr_statement()

    def _parse_block(self) -> tuple[Stmt, ...]:
        self._expect_op("{")
        body: list[Stmt] = []
        while not self._at_op("}"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated block")
            stmt = self._parse_statement()
            if stmt is not None:
                body.append(stmt)
        self._expect_op("}")
        return tuple(body)

    def _parse_embedded(self) -> tuple[Stmt, ...]:
        """The controlled statement of if/for/while/foreach: a `{ }` block or a single statement."""
        if self._at_op("{"):
            return self._parse_block()
        stmt = self._parse_statement()
        return (stmt,) if stmt is not None else ()

    def _parse_if(self) -> Stmt:
        self._advance()  # 'if'
        self._expect_op("(")
        cond = self._parse_expr()
        self._expect_op(")")
        clauses: list[tuple[Expr | None, tuple[Stmt, ...]]] = [(cond, self._parse_embedded())]
        while self._at_kw("else"):
            self._advance()
            if self._at_kw("if"):
                self._advance()
                self._expect_op("(")
                econd = self._parse_expr()
                self._expect_op(")")
                clauses.append((econd, self._parse_embedded()))
            else:
                clauses.append((None, self._parse_embedded()))
                break
        return Stmt(kind="if", clauses=tuple(clauses))

    def _parse_for(self) -> Stmt:
        self._advance()  # 'for'
        self._expect_op("(")
        init = self._parse_expr_or_assign() if not self._at_op(";") else Expr(op="empty")
        self._expect_op(";")
        cond = self._parse_expr() if not self._at_op(";") else Expr(op="empty")
        self._expect_op(";")
        update = self._parse_expr_or_assign() if not self._at_op(")") else Expr(op="empty")
        self._expect_op(")")
        return Stmt(kind="for", exprs=(init, cond, update), body=self._parse_embedded())

    def _parse_while(self) -> Stmt:
        self._advance()  # 'while'
        self._expect_op("(")
        cond = self._parse_expr()
        self._expect_op(")")
        return Stmt(kind="while", exprs=(cond,), body=self._parse_embedded())

    def _parse_do(self) -> Stmt:
        self._advance()  # 'do'
        body = self._parse_embedded()
        if self._eat_kw("until") is None:
            raise self._error("expected 'until' after do-body")
        self._expect_op("(")
        cond = self._parse_expr()
        self._expect_op(")")
        self._eat_op_optional(";")
        return Stmt(kind="do", exprs=(cond,), body=body)

    def _parse_switch(self) -> Stmt:
        self._advance()  # 'switch'
        self._expect_op("(")
        subject = self._parse_expr()
        self._expect_op(")")
        self._expect_op("{")
        clauses: list[tuple[Expr | None, tuple[Stmt, ...]]] = []
        while not self._at_op("}"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated switch body")
            if self._eat_kw("case") is not None:
                label: Expr | None = self._parse_expr()
                self._expect_op(":")
            elif self._eat_kw("default") is not None:
                label = None
                self._expect_op(":")
            else:
                raise self._error("expected 'case' or 'default' in switch")
            stmts: list[Stmt] = []
            while not self._at_op("}") and not self._at_kw("case", "default"):
                stmt = self._parse_statement()
                if stmt is not None:
                    stmts.append(stmt)
            clauses.append((label, tuple(stmts)))
        self._expect_op("}")
        return Stmt(kind="switch", exprs=(subject,), clauses=tuple(clauses))

    def _parse_return(self) -> Stmt:
        self._advance()  # 'return'
        exprs = () if self._at_op(";") else (self._parse_expr(),)
        self._expect_op(";")
        return Stmt(kind="return", exprs=exprs)

    def _parse_break(self) -> Stmt:
        self._advance()
        self._expect_op(";")
        return Stmt(kind="break")

    def _parse_continue(self) -> Stmt:
        self._advance()
        self._expect_op(";")
        return Stmt(kind="continue")

    def _parse_stop(self) -> Stmt:
        self._advance()
        self._expect_op(";")
        return Stmt(kind="stop")

    def _parse_goto(self) -> Stmt:
        self._advance()  # 'goto'
        target = self._parse_expr()
        self._expect_op(";")
        # Normalise the label spelling to match a `label` Stmt: `goto 'Begin'` and `goto Begin`
        # both carry text "Begin".
        label = str(target.value) if target.op == "nameconst" else target.text
        return Stmt(kind="goto", exprs=(target,), text=label)

    def _parse_foreach(self) -> Stmt:
        self._advance()  # 'foreach'
        iterator = self._parse_expr()
        return Stmt(kind="foreach", exprs=(iterator,), body=self._parse_embedded())

    def _parse_assert(self) -> Stmt:
        self._advance()  # 'assert'
        self._expect_op("(")
        cond = self._parse_expr()
        self._expect_op(")")
        self._eat_op_optional(";")
        return Stmt(kind="assert", exprs=(cond,))

    def _parse_expr_statement(self) -> Stmt:
        lhs = self._parse_expr()
        if self._peek().kind is Tok.OP and self._peek().text in _ASSIGN_OPS:
            op = self._advance().text
            rhs = self._parse_expr()
            self._expect_op(";")
            return Stmt(kind="assign", text=op, exprs=(lhs, rhs))
        self._expect_op(";")
        return Stmt(kind="expr", exprs=(lhs,))

    def _parse_expr_or_assign(self) -> Expr:
        lhs = self._parse_expr()
        if self._peek().kind is Tok.OP and self._peek().text in _ASSIGN_OPS:
            op = self._advance().text
            return Expr(op="assign", text=op, children=(lhs, self._parse_expr()))
        return lhs

    # ── expressions ───────────────────────────────────────────────────────────
    def _parse_expr(self) -> Expr:
        return self._parse_ternary()

    def _parse_ternary(self) -> Expr:
        cond = self._parse_binary(999)
        if self._at_op("?"):
            self._advance()
            then = self._parse_expr()
            self._expect_op(":")
            other = self._parse_ternary()
            return Expr(op="ternary", children=(cond, then, other))
        return cond

    def _binop_prec(self) -> int | None:
        tok = self._peek()
        if tok.kind is Tok.OP:
            return _BINOPS.get(tok.text)
        if tok.kind is Tok.IDENT:
            return _WORD_BINOPS.get(tok.text.lower())
        return None

    def _parse_binary(self, max_prec: int) -> Expr:
        """Precedence climbing; UnrealScript convention has LOWER precedence numbers bind tighter."""
        left = self._parse_unary()
        while (prec := self._binop_prec()) is not None and prec <= max_prec:
            op = self._advance().text
            right = self._parse_binary(prec - 1)
            left = Expr(op="binary", text=op, children=(left, right))
        return left

    def _parse_unary(self) -> Expr:
        tok = self._peek()
        if tok.kind is Tok.OP and tok.text in ("!", "-", "+", "~", "++", "--"):
            self._advance()
            return Expr(op="unary", text=tok.text, children=(self._parse_unary(),))
        return self._parse_postfix()

    def _parse_postfix(self) -> Expr:
        expr = self._parse_primary()
        while True:
            if self._at_op("."):
                self._advance()
                field = self._expect_ident()
                expr = Expr(op="member", text=field, children=(expr,))
            elif self._at_op("("):
                expr = self._parse_call(expr)
            elif self._at_op("["):
                self._advance()
                index = self._parse_expr()
                self._expect_op("]")
                expr = Expr(op="index", children=(expr, index))
            elif self._at_op("++", "--"):
                op = self._advance().text
                expr = Expr(op="postfix", text=op, children=(expr,))
            else:
                return expr

    def _parse_call(self, callee: Expr) -> Expr:
        self._expect_op("(")
        args: list[Expr] = []
        while not self._at_op(")"):
            if self._peek().kind is Tok.EOF:
                raise self._error("unterminated call arguments")
            if self._at_op(","):  # a skipped optional argument
                args.append(Expr(op="empty"))
                self._advance()
                continue
            args.append(self._parse_expr())
            if self._at_op(","):
                self._advance()
            elif not self._at_op(")"):
                raise self._error("expected ',' or ')' in call arguments")
        self._expect_op(")")
        return Expr(op="call", children=(callee, *args))

    def _parse_primary(self) -> Expr:
        tok = self._peek()
        if tok.kind is Tok.INT:
            self._advance()
            return Expr(op="intconst", value=tok.value, text=tok.text)
        if tok.kind is Tok.FLOAT:
            self._advance()
            return Expr(op="floatconst", value=tok.value, text=tok.text)
        if tok.kind is Tok.STRING:
            self._advance()
            return Expr(op="stringconst", value=tok.value, text=tok.text)
        if tok.kind is Tok.NAME:
            self._advance()
            return Expr(op="nameconst", value=tok.value, text=tok.text)
        if tok.kind is Tok.OP and tok.text == "(":
            self._advance()
            inner = self._parse_expr_or_assign()  # assignment is a value-producing expr in UE
            self._expect_op(")")
            return Expr(op="paren", children=(inner,))
        if tok.kind is Tok.IDENT:
            return self._parse_ident_primary()
        raise self._error("expected an expression")

    def _parse_ident_primary(self) -> Expr:
        tok = self._advance()
        low = tok.text.lower()
        if low in ("true", "false"):
            return Expr(op="boolconst", value=low == "true", text=tok.text)
        if low == "none":
            return Expr(op="noneconst", text=tok.text)
        if low == "self":
            return Expr(op="self", text=tok.text)
        if low in ("default", "static", "global"):
            return Expr(op=low, text=tok.text)
        if low == "super":
            if self._at_op("("):
                parent = self._raw_paren_group()[1:-1].strip()
                return Expr(op="super", text=parent)
            return Expr(op="super", text="")
        if low == "new":
            args: list[Expr] = []
            if self._at_op("("):
                self._advance()
                while not self._at_op(")"):
                    args.append(self._parse_expr())
                    if self._at_op(","):
                        self._advance()
                self._expect_op(")")
            args.append(self._parse_unary())  # the class expression
            return Expr(op="new", children=tuple(args))
        if low == "class" and self._at_op("<"):  # metaclass cast target `class<Meta>(expr)`
            self._advance()
            meta = self._parse_dotted_name()
            self._expect_gt()
            return Expr(op="name", text=f"class<{meta}>")
        if self._peek().kind is Tok.NAME:  # object literal `Texture'Pkg.Name'`
            nt = self._advance()
            return Expr(op="objref", text=tok.text, value=nt.value)
        return Expr(op="name", text=tok.text)
