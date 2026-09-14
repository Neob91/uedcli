"""`byte -> string` conversion (`EX_ByteToString`, 0x52) — the gap found compiling the real UT99
`IpServer` package (`USCRIPT-COMPILER.md`): `GetPlayer` reads `P.PlayerReplicationInfo.Team` (a
`byte`) through a `$` string concat, which lowers a `string()` cast.

Probed live against UED22 UCC: 0x52 sits one slot BEFORE `EX_IntToString` (0x53) in UCC's own
0x39-0x5F conversion-opcode block — a free slot the earlier "fully-packed, no free slot" assumption
(`dev/docs/board/inbox/uscript-byte-to-string-conversion-missing/`) missed.
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
_SRC = (_FIX / "UscByteToStr.uc").read_text()


def _compile() -> bytes:
    return serialize(compile_package_dir({"UscByteToStr.uc": _SRC}, InstallEnv([str(_UED22)]),
                                         package_name="UscByteToStr"))


def test_byte_to_string_byte_exact():
    golden = (_FIX / "UscByteToStr.u").read_bytes()
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
def test_byte_to_string_matches_fresh_ucc(tmp_path):
    from uedcli.uscript.reference import ucc_compile, ucc_container
    with ucc_container(state_dir=tmp_path) as c:
        fresh = ucc_compile(c, "UscByteToStr", {"UscByteToStr.uc": _SRC})
    r = gate(_compile(), fresh)
    assert r.passed, " | ".join(r.messages)
