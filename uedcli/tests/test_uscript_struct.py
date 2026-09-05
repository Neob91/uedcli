"""A class with a `struct` member compiles autonomously to identity-parity with UCC (board item
`autonomous-struct-class-compile-diverges-from`: Struct name RF_HighlightName + struct member Next
chain). Offline — uses the committed UCC golden."""
from __future__ import annotations

from pathlib import Path

from uedcli.uscript.compile import compile_package
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import perm_gate
from uedcli.uscript.serialize import serialize

_UED22 = str(Path(__file__).resolve().parents[2] / "uned" / "UED22")
_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "uscript" / "UscSt.u"
_SRC = ("class UscSt expands Object;\n"
        "struct SPoint { var int X; var int Y; };\n"
        "var SPoint Pt;\n"
        "var int Solo;\n")


def test_struct_class_autonomous_identity_parity():
    mine = serialize(compile_package(_SRC, InstallEnv([_UED22])))
    r = perm_gate(mine, _GOLDEN.read_bytes())
    assert r.passed, r.messages
