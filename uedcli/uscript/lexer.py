"""UnrealScript lexer for UED22 `.uc` source.

Produces the flat `Token` stream the parser consumes (`tokens.py`). Keywords are NOT recognised
here — they lex as `Tok.IDENT` and the parser classifies them by context, as UnrealScript itself
does (its keywords are contextual). Calibrated against real decompiled stock source (`FrameBuilder`,
`ConSys`, `Extension` via `reference.py`).

Lexical rules:
- Identifiers `[A-Za-z_][A-Za-z0-9_]*`.
- Ints (decimal / `0x` hex) vs floats (a `.`, an exponent, or a trailing `f`/`F`); a `.` is only
  part of a number when a digit sits next to it, else it is the member-access operator.
- `"..."` strings (escapes `\" \\ \n \t`, any other `\c` -> `c`) and `'...'` name literals (verbatim
  inner text).
- Operators, longest-match-first (see `_OPS3`/`_OPS2`/`_OPS1`).
- `//` line and `/* */` block comments; block comments NEST (verified: UCC compiles
  `/* /* */ */`). Skipped, no token.
- `#exec` directive lines -> one `Tok.EXEC` carrying the rest of the line verbatim.
"""
from __future__ import annotations

from .tokens import Tok, Token

__all__ = ["lex", "LexError"]

_OPS3 = (">>>",)
_OPS2 = ("==", "!=", "<=", ">=", "&&", "||", "^^", "<<", ">>", "**",
         "+=", "-=", "*=", "/=", "~=", "$=", "@=", "::", "++", "--")
_OPS1 = set("+-*/%=<>!&|^~$@?:;,.(){}[]")

_HEX = set("0123456789abcdefABCDEF")
_STRING_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}


class LexError(Exception):
    """A character the lexer cannot form a token from, with 1-based line/col and the offending
    context (e.g. an unterminated string or a stray `#`)."""


class _Lexer:
    def __init__(self, src: str) -> None:
        # Strip a leading UTF-8 BOM; the caller already handed us a decoded str otherwise.
        self.src = src[1:] if src.startswith("\ufeff") else src
        self.n = len(self.src)
        self.i = 0
        self.line = 1
        self.line_start = 0          # src index of the current line's first char (for col)
        self.line_has_content = False  # any non-whitespace seen on this line (for #exec detection)
        self.tokens: list[Token] = []

    def _col(self, at: int) -> int:
        return at - self.line_start + 1

    def _error(self, msg: str, at: int) -> LexError:
        return LexError(f"{msg} at line {self.line}, col {self._col(at)}")

    def _newline(self) -> None:
        self.line += 1
        self.line_start = self.i + 1
        self.line_has_content = False

    def lex(self) -> list[Token]:
        while self.i < self.n:
            c = self.src[self.i]
            if c == "\n":
                self._newline()
                self.i += 1
                continue
            if c in " \t\r\f":
                self.i += 1
                continue
            two = self.src[self.i:self.i + 2]
            if two == "//":
                self._skip_line_comment()
            elif two == "/*":
                self._skip_block_comment()
            elif c == "#" and not self.line_has_content and self.src[self.i:self.i + 5] == "#exec":
                self._scan_exec()
            elif c == '"':
                self._scan_string()
            elif c == "'":
                self._scan_name()
            elif c.isdigit() or (c == "." and self._peek_is_digit(self.i + 1)):
                self._scan_number()
            elif c.isalpha() or c == "_":
                self._scan_ident()
            else:
                self._scan_operator()
        self.tokens.append(Token(kind=Tok.EOF, text="", line=self.line, col=self._col(self.i)))
        return self.tokens

    def _peek_is_digit(self, at: int) -> bool:
        return at < self.n and self.src[at].isdigit()

    def _skip_line_comment(self) -> None:
        self.line_has_content = True
        end = self.src.find("\n", self.i)
        self.i = self.n if end == -1 else end

    def _skip_block_comment(self) -> None:
        self.line_has_content = True
        start = self.i
        depth = 0
        while self.i < self.n:
            if self.src[self.i] == "\n":
                self._newline()
                self.i += 1
                continue
            two = self.src[self.i:self.i + 2]
            if two == "/*":
                depth += 1
                self.i += 2
            elif two == "*/":
                depth -= 1
                self.i += 2
                if depth == 0:
                    return
            else:
                self.i += 1
        raise self._error("unterminated block comment", start)

    def _scan_exec(self) -> None:
        col = self._col(self.i)
        line = self.line
        end = self.src.find("\n", self.i)
        end = self.n if end == -1 else end
        rest = self.src[self.i + 5:end]        # after the literal `#exec`
        text = rest.lstrip(" \t")              # drop the gap; internal spacing kept verbatim
        self.tokens.append(Token(kind=Tok.EXEC, text=text, line=line, col=col))
        self.i = end
        self.line_has_content = True

    def _scan_string(self) -> None:
        col = self._col(self.i)
        line = self.line
        start = self.i
        self.i += 1
        out: list[str] = []
        while self.i < self.n:
            c = self.src[self.i]
            if c == '"':
                self.i += 1
                self.tokens.append(Token(kind=Tok.STRING, text=self.src[start:self.i],
                                         value="".join(out), line=line, col=col))
                self.line_has_content = True
                return
            if c == "\n":
                break
            if c == "\\":
                if self.i + 1 >= self.n or self.src[self.i + 1] == "\n":
                    break
                nxt = self.src[self.i + 1]
                out.append(_STRING_ESCAPES.get(nxt, nxt))
                self.i += 2
                continue
            out.append(c)
            self.i += 1
        raise self._error("unterminated string literal", start)

    def _scan_name(self) -> None:
        col = self._col(self.i)
        start = self.i
        self.i += 1
        while self.i < self.n and self.src[self.i] not in ("'", "\n"):
            self.i += 1
        if self.i >= self.n or self.src[self.i] == "\n":
            raise self._error("unterminated name literal", start)
        inner = self.src[start + 1:self.i]
        self.i += 1
        self.tokens.append(Token(kind=Tok.NAME, text=self.src[start:self.i], value=inner,
                                 line=self.line, col=col))
        self.line_has_content = True

    def _scan_number(self) -> None:
        col = self._col(self.i)
        start = self.i
        if self.src[self.i] == "0" and self.src[self.i + 1:self.i + 2] in ("x", "X"):
            self.i += 2
            digits = self.i
            while self.i < self.n and self.src[self.i] in _HEX:
                self.i += 1
            if self.i == digits:
                raise self._error(f"malformed hex literal {self.src[start:self.i]!r}", start)
            text = self.src[start:self.i]
            self.tokens.append(Token(kind=Tok.INT, text=text, value=int(text, 16),
                                     line=self.line, col=col))
            self.line_has_content = True
            return

        is_float = False
        while self.i < self.n and self.src[self.i].isdigit():
            self.i += 1
        if self.i < self.n and self.src[self.i] == ".":
            is_float = True
            self.i += 1
            while self.i < self.n and self.src[self.i].isdigit():
                self.i += 1
        if self.i < self.n and self.src[self.i] in ("e", "E") and self._exponent_follows():
            is_float = True
            self.i += 1
            if self.src[self.i] in ("+", "-"):
                self.i += 1
            while self.i < self.n and self.src[self.i].isdigit():
                self.i += 1
        if self.i < self.n and self.src[self.i] in ("f", "F"):
            is_float = True
            self.i += 1

        text = self.src[start:self.i]
        if is_float:
            self.tokens.append(Token(kind=Tok.FLOAT, text=text, value=float(text.rstrip("fF")),
                                     line=self.line, col=col))
        else:
            self.tokens.append(Token(kind=Tok.INT, text=text, value=int(text),
                                     line=self.line, col=col))
        self.line_has_content = True

    def _exponent_follows(self) -> bool:
        """`e`/`E` is an exponent only if a digit (optionally after a sign) follows — otherwise it is
        the start of an identifier (e.g. `1.Enum`)."""
        at = self.i + 1
        if at < self.n and self.src[at] in ("+", "-"):
            at += 1
        return at < self.n and self.src[at].isdigit()

    def _scan_ident(self) -> None:
        col = self._col(self.i)
        start = self.i
        self.i += 1
        while self.i < self.n and (self.src[self.i].isalnum() or self.src[self.i] == "_"):
            self.i += 1
        self.tokens.append(Token(kind=Tok.IDENT, text=self.src[start:self.i],
                                 line=self.line, col=col))
        self.line_has_content = True

    def _scan_operator(self) -> None:
        col = self._col(self.i)
        three = self.src[self.i:self.i + 3]
        two = self.src[self.i:self.i + 2]
        c = self.src[self.i]
        if three in _OPS3:
            op, width = three, 3
        elif two in _OPS2:
            op, width = two, 2
        elif c in _OPS1:
            op, width = c, 1
        else:
            raise self._error(f"unexpected character {c!r}", self.i)
        self.tokens.append(Token(kind=Tok.OP, text=op, line=self.line, col=col))
        self.i += width
        self.line_has_content = True


def lex(src: str) -> list[Token]:
    """Tokenize UnrealScript `src` into a `Token` list ending in a `Tok.EOF`.

    Raises `LexError` (with 1-based line/col and the offending context) on an unterminated
    string/name/block-comment or an unexpected character.
    """
    return _Lexer(src).lex()
