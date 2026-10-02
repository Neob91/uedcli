"""Token model shared by the lexer and parser."""
from __future__ import annotations

import enum
from dataclasses import dataclass


class Tok(enum.Enum):
    IDENT = "ident"        # identifier or keyword (parser classifies keywords by context)
    INT = "int"            # integer literal (value: int)
    FLOAT = "float"        # float literal (value: float)
    STRING = "string"      # "..." literal (value: the decoded str, no quotes)
    NAME = "name"          # '...' name literal (value: the str, no quotes)
    OP = "op"              # operator / punctuation (text is the operator, e.g. "==", "{", ";")
    EXEC = "exec"          # a whole `#exec ...` directive line (text: the line without leading #exec)
    EOF = "eof"


@dataclass(frozen=True, kw_only=True)
class Token:
    kind: Tok
    text: str              # source spelling (for IDENT/OP) or raw lexeme
    value: object = None   # decoded value for INT/FLOAT/STRING/NAME; else None
    line: int = 0          # 1-based
    col: int = 0           # 1-based
