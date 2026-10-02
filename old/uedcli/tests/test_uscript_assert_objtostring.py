"""`assert` statement lowering (`EX_Assert`, 0x09) and the object/class -> string conversion
(`EX_ObjectToString`, 0x56) — two gaps found surveying real UT99 packages for the "30 byte-exact
packages" corpus goal (`USCRIPT-COMPILER.md`).

Both probed live against UED22 UCC: `EX_Assert`'s u16 operand is the 1-based source line of the
`assert` keyword itself (not a jump offset — confirmed by two `assert`s on different lines encoding
their own line number), and `EX_ObjectToString` (0x56) is the conversion opcode `string(SomeObject)`
lowers to, sitting between `EX_FloatToString` (0x55) and `EX_NameToString` (0x57) in UCC's own
0x39-0x5F conversion-opcode block.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_package_dir
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import gate
from uedcli.uscript.serialize import serialize

_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript"
_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
_SRC = (_FIX / "UscAssertObjToStr.uc").read_text()


def _compile() -> bytes:
    return serialize(compile_package_dir({"UscAssertObjToStr.uc": _SRC}, InstallEnv([str(_UED22)]),
                                         package_name="UscAssertObjToStr"))


def test_assert_and_object_to_string_byte_exact():
    golden = (_FIX / "UscAssertObjToStr.u").read_bytes()
    r = gate(_compile(), golden)
    assert r.passed, " | ".join(r.messages)


def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


@pytest.mark.integration
@pytest.mark.skipif(not (_docker_up() and (_UED22 / "UCC.exe").is_file()),
                    reason="needs a live docker daemon and the committed UED22 substrate (UCC.exe)")
def test_assert_and_object_to_string_matches_fresh_ucc(tmp_path):
    from uedcli.uscript.reference import ucc_compile, ucc_container
    with ucc_container(state_dir=tmp_path) as c:
        fresh = ucc_compile(c, "UscAssertObjToStr", {"UscAssertObjToStr.uc": _SRC})
    r = gate(_compile(), fresh)
    assert r.passed, " | ".join(r.messages)
