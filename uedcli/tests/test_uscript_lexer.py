"""Unit + smoke tests for the UnrealScript lexer (`uedcli.uscript.lexer`).

The unit tests are pure Python. The real-source smoke test decompiles stock packages through UCC and
so needs docker + the UED22 substrate; it gates the same way `test_uscript_reference.py` does.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.lexer import LexError, lex
from uedcli.uscript.tokens import Tok


def _no_eof(src: str) -> list:
    toks = lex(src)
    assert toks[-1].kind is Tok.EOF
    return toks[:-1]


def test_ends_with_eof():
    toks = lex("")
    assert len(toks) == 1 and toks[0].kind is Tok.EOF


def test_identifiers_are_ident_keywords_not_special():
    toks = _no_eof("class Foo expands Object")
    assert [t.kind for t in toks] == [Tok.IDENT] * 4
    assert [t.text for t in toks] == ["class", "Foo", "expands", "Object"]


def test_int_decimal_and_hex():
    toks = _no_eof("42 0x1F 0Xff 0")
    assert [(t.kind, t.value) for t in toks] == [
        (Tok.INT, 42), (Tok.INT, 0x1F), (Tok.INT, 0xFF), (Tok.INT, 0)]


def test_floats_various_forms():
    toks = _no_eof("1.5 .5 1. 1e3 1.5e-2 2.0f 3F .25E+1")
    assert all(t.kind is Tok.FLOAT for t in toks)
    assert [t.value for t in toks] == [1.5, 0.5, 1.0, 1000.0, 0.015, 2.0, 3.0, 2.5]


def test_member_dot_is_op_not_float():
    toks = _no_eof("Actor.Location")
    assert [t.kind for t in toks] == [Tok.IDENT, Tok.OP, Tok.IDENT]
    assert toks[1].text == "."


def test_int_then_member_dot_when_dot_not_adjacent_to_digit():
    # `5 .foo` — space breaks adjacency, so the dot after a letter-follow is a member OP.
    toks = _no_eof("foo .bar")
    assert [(t.kind, t.text) for t in toks] == [
        (Tok.IDENT, "foo"), (Tok.OP, "."), (Tok.IDENT, "bar")]


def test_string_escapes():
    (t,) = _no_eof(r'"a\"b\\c\n\t\q"')
    assert t.kind is Tok.STRING
    assert t.value == 'a"b\\c\n\tq'


def test_name_literal_verbatim():
    (t,) = _no_eof("'Engine.Texture'")
    assert t.kind is Tok.NAME and t.value == "Engine.Texture"


def test_unterminated_string_raises_with_position():
    with pytest.raises(LexError) as e:
        lex('foo\n  "unclosed')
    assert "line 2" in str(e.value) and "col 3" in str(e.value)


def test_unterminated_name_raises():
    with pytest.raises(LexError):
        lex("'unclosed")


@pytest.mark.parametrize("src", [
    "==", "!=", "<=", ">=", "&&", "||", "^^", "<<", ">>", ">>>", "**",
    "+=", "-=", "*=", "/=", "~=", "$=", "@=", "::", "++", "--",
    "+", "-", "*", "/", "%", "=", "<", ">", "!", "&", "|", "^", "~", "$", "@",
    "?", ":", ";", ",", ".", "(", ")", "{", "}", "[", "]",
])
def test_operator_greedy_longest_match(src):
    toks = _no_eof(src)
    assert len(toks) == 1 and toks[0].kind is Tok.OP and toks[0].text == src


def test_shift_operators_greedy_boundary():
    # `>>>` must beat `>>` beat `>`; `a>>>b` is three-char shift, not `>>` + `>`.
    toks = _no_eof("a>>>b a>>b a>b")
    ops = [t.text for t in toks if t.kind is Tok.OP]
    assert ops == [">>>", ">>", ">"]


def test_line_comment_skipped():
    toks = _no_eof("a // comment ; = {\nb")
    assert [t.text for t in toks] == ["a", "b"]


def test_block_comment_skipped_and_nests():
    # If comments did not nest, the trailing `*/` would tokenize as `*` `/`.
    toks = _no_eof("a /* outer /* inner */ still */ b")
    assert [t.text for t in toks] == ["a", "b"]


def test_unterminated_block_comment_raises():
    with pytest.raises(LexError):
        lex("a /* never closed")


def test_exec_captures_rest_of_line_verbatim():
    toks = _no_eof("#exec TEXTURE IMPORT FILE=Tex\\x.pcx  NAME=x\nclass Foo")
    assert toks[0].kind is Tok.EXEC
    assert toks[0].text == "TEXTURE IMPORT FILE=Tex\\x.pcx  NAME=x"
    assert [t.kind for t in toks[1:]] == [Tok.IDENT, Tok.IDENT]


def test_exec_with_leading_whitespace_still_recognized():
    (t,) = _no_eof("   #exec FONT IMPORT")
    assert t.kind is Tok.EXEC and t.text == "FONT IMPORT"


def test_hash_not_at_line_start_is_error():
    with pytest.raises(LexError):
        lex("foo #exec BAR")


def test_line_col_tracking():
    toks = _no_eof("foo\n  bar baz")
    by_text = {t.text: (t.line, t.col) for t in toks}
    assert by_text["foo"] == (1, 1)
    assert by_text["bar"] == (2, 3)
    assert by_text["baz"] == (2, 7)


def test_bom_is_stripped():
    toks = _no_eof("\ufeffclass Foo")
    assert toks[0].text == "class" and toks[0].col == 1


def test_defaultproperties_snippet():
    src = "insertColor=(R=0,G=0,B=0,A=0)\ntex=Texture'Extension.Solid'"
    toks = _no_eof(src)
    assert Tok.NAME in {t.kind for t in toks}
    assert any(t.kind is Tok.INT and t.value == 0 for t in toks)


# ---- real-source smoke test (docker + UED22 substrate) ----

_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"


def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


@pytest.mark.skipif(
    not (_docker_up() and (_UED22 / "UCC.exe").is_file()),
    reason="needs a live docker daemon and the committed UED22 substrate (UCC.exe)")
def test_lexes_real_decompiled_source(tmp_path):
    """Decompile stock `FrameBuilder`, `ConSys`, `Extension` and lex every class: no `LexError`, a
    trailing `Tok.EOF`, and at least one token beyond it."""
    from uedcli.uscript.reference import ucc_container, ucc_decompile

    with ucc_container(state_dir=tmp_path) as container:
        sources: dict[str, str] = {}
        for pkg in ("FrameBuilder", "ConSys", "Extension"):
            sources.update(ucc_decompile(container, pkg))

    assert len(sources) > 10, f"expected many classes, got {len(sources)}"
    for name, src in sources.items():
        toks = lex(src)
        assert toks[-1].kind is Tok.EOF, name
        assert len(toks) > 1, name
