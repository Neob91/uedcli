"""`state` blocks (labels + the `EX_LabelTable`/`EX_Nothing`-padding formula) and `foreach`
(`EX_Iterator`) compile byte-exact vs UCC. Offline — uses the committed golden; see
`compile-model.md` "UState label tables" / "EX_Nothing padding" for the RE'd rules this pins."""
from __future__ import annotations

from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_package_dir
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import gate
from uedcli.uscript.lower import LowerError, Scope, lower_state_body
from uedcli.uscript.natives import load_catalog, load_graph
from uedcli.uscript.parser import parse
from uedcli.uscript.serialize import serialize

_UED22 = str(Path(__file__).resolve().parents[2] / "uned" / "UED22")
_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript"
_SRC = (_FIX / "UscStateForeach.uc").read_text()
_GOLDEN = _FIX / "UscStateForeach.u"


def test_state_and_foreach_strict_byte_exact():
    """A `Trigger`-triggered `state` (label + `Sleep`/`GotoState('')`) plus a `foreach
    AllActors(...)` loop, in one class, both byte-exact vs a fresh UCC build."""
    mine = serialize(compile_package_dir({"UscStateForeach.uc": _SRC}, InstallEnv([_UED22]),
                                         package_name="UscStateForeach"))
    r = gate(mine, _GOLDEN.read_bytes())
    assert r.passed, r.messages


# ── EX_Nothing padding formula (RE'd 2026-09-13, `compile-model.md`) ─────────────────────────────
# pad = (#GotoState/FinishAnim calls - #explicit `Stop;` statements + 2) % 4. Pinned here at the
# token level (no docker) against every controlled case that established/verified the formula.
_PAD_CASES = {
    "no calls": ("Begin:\n Sleep(1.0);\n", 2),
    "one GotoState": ("Begin:\n GotoState('');\n", 3),
    "two GotoState": ("Begin:\n GotoState('');\n GotoState('');\n", 0),
    "one FinishAnim": ("Begin:\n FinishAnim();\n", 3),
    "one explicit Stop": ("Begin:\n Stop;\n", 1),
    "two explicit Stop": ("Begin:\n Stop;\n Stop;\n", 0),
    "GotoState then Stop": ("Begin:\n GotoState('');\n Stop;\n", 2),
}


@pytest.mark.parametrize("body,expected_pad", _PAD_CASES.values(), ids=_PAD_CASES.keys())
def test_state_nothing_padding_formula(body: str, expected_pad: int):
    src = f"class UscStPad expands Actor;\nstate Active {{\n{body}}}\n"
    decl = parse(src)
    scope = Scope(locals_={}, own_members={}, own_funcs={}, class_name="UscStPad",
                 super_name="Actor", graph=load_graph(_UED22))
    toks = lower_state_body(decl.states[0], scope, load_catalog(_UED22))
    assert sum(1 for t in toks if t.op == 0x0B) == expected_pad
