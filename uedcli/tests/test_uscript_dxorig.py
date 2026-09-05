"""Original Ion Storm Deus Ex (v1112fm) reference toolchain: `#exec CONVERSATION IMPORT` works and
is byte-reproducible. This is the substrate/golden the future `.con` emitter will match.

Unlike our /opt/UED22 substrate (OldUnreal, whose Editor.dll dropped the CONVERSATION handler and
no-ops it), the original DX build emits the Conversation/ConEvent/ConSpeech/… objects — into SIBLING
packages `<Pkg>Text.u` (the objects) and `<Pkg>Audio<pkg>.u` (audio list), not `<Pkg>.u` itself.

Substrate: `uned/DXORIG/System/` (fetched by `uedcli/uscript/fetch_dxorig.sh`, gitignored). Golden:
`fixtures/conversation/{Minimal.Con, ConvTest.u, ConvTestText.u, ConvTestAudioTestPack.u}` — a fresh
`ucc_compile_dxorig` of `class ConvTest expands Object; #exec CONVERSATION IMPORT FILE="Minimal.Con"`.
Every field is deterministic except the 16-byte package GUID at header offset 36, which is masked."""
from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.reference_dxorig import (UccError, dxorig_container, dxorig_substrate_dir,
                                             ucc_compile_dxorig)

_PKG_MAGIC = 0x9E2A83C1
_FIX = Path(__file__).resolve().parent / "fixtures" / "conversation"
_GOLDEN = ["ConvTest.u", "ConvTestText.u", "ConvTestAudioTestPack.u"]
_SRC = 'class ConvTest expands Object;\n\n#exec CONVERSATION IMPORT FILE="Minimal.Con"\n'


def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _substrate_present() -> bool:
    try:
        dxorig_substrate_dir()
        return True
    except UccError:
        return False


def _mask_guid(b: bytes) -> bytes:
    return b[:36] + b"\x00" * 16 + b[52:]


@pytest.mark.skipif(not (_docker_up() and _substrate_present()),
                    reason="needs a live docker daemon and the DX substrate "
                           "(uedcli/uscript/fetch_dxorig.sh)")
def test_conversation_import_matches_golden(tmp_path):
    con = (_FIX / "Minimal.Con").read_bytes()
    with dxorig_container(state_dir=tmp_path) as c:
        out = ucc_compile_dxorig(c, "ConvTest", {"ConvTest.uc": _SRC},
                                 con_files={"Minimal.Con": con})

    assert sorted(out) == sorted(_GOLDEN), f"unexpected output packages: {sorted(out)}"
    # The conversation objects land in the sibling Text package, not ConvTest.u — the handler proof.
    text = out["ConvTestText.u"]
    assert struct.unpack_from("<I", text, 0)[0] == _PKG_MAGIC
    assert b"Conversation" in text and b"TestConvo" in text, "no Conversation object emitted"

    for name in _GOLDEN:
        golden = (_FIX / name).read_bytes()
        assert _mask_guid(out[name]) == _mask_guid(golden), f"{name}: differs from golden (GUID masked)"
