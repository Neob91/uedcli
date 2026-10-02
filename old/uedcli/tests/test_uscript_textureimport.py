"""`#exec TEXTURE IMPORT` compiler integration: `uscript/texture_import.py` wired into
`compile.py`/`serialize.py`, verified against a live UED22 `UCC.exe` golden.

`dev/docs/spikes/2026-09-13-texture-import-re/spike.md` did the RE (PCX decode, property layout, mip
quantization); `test_uscript_textureimport_re.py` pins that algorithm offline against the spike's own
goldens. This file pins the PLUMBING: the compiler builds the `UPalette`/`UTexture` export pair,
threads `InternalTime` through `gate.py`'s new exclusion, and reproduces UCC's table order well
enough to pass the STRICT gate — not just `perm_gate`.

`UscTexAsym4x4` uses an asymmetric 4x4 block (no exact mip-average tie on any channel), so it is NOT
affected by the two open judgment calls (`texture_import.py`'s mip-quantization tie-break and
`MipZero` rounding at an exact `.5` — see spike.md's "Open: the tie-break rule" and
`compile-model.md`): a genuine tie only diverges on the few `MipZero`/mip-pixel bytes at stake, never
the structural/table-order machinery this file checks (confirmed live: an 8x8 all-`.5`-average probe
gates byte-identical except for `MipZero`'s 3 bytes).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_package
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import gate, perm_gate
from uedcli.uscript.serialize import serialize

_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript" / "realpkg" / "UscTexAsym4x4"
_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"


def _pcx_bytes() -> bytes:
    return (_FIX / "Textures" / "Asym4x4Tex.PCX").read_bytes()


def _compile() -> bytes:
    src = (_FIX / "UscTexAsym4x4.uc").read_text()
    env = InstallEnv([str(_UED22)])
    pkg = compile_package(src, env,
                          texture_files={"Textures\\Asym4x4Tex.PCX": _pcx_bytes()})
    return serialize(pkg)


def test_textureimport_strict_byte_exact():
    """No mip-average tie on any channel: the STRICT gate (table order included) passes clean."""
    mine = _compile()
    golden = (_FIX / "UscTexAsym4x4.u").read_bytes()
    r = gate(mine, golden)
    assert r.passed, " | ".join(r.messages)


def test_textureimport_perm_gate_also_passes():
    mine = _compile()
    golden = (_FIX / "UscTexAsym4x4.u").read_bytes()
    r = perm_gate(mine, golden)
    assert r.passed, " | ".join(r.messages)


def test_texture_file_not_found_names_the_path():
    src = ("class UscTexMissing expands Object;\n\n"
          "#exec TEXTURE IMPORT NAME=X FILE=Textures\\NoSuchFile.PCX LODSET=0\n")
    env = InstallEnv([str(_UED22)])
    with pytest.raises(NotImplementedError, match="NoSuchFile.PCX"):
        compile_package(src, env, texture_files={})


def test_unknown_directive_param_rejected():
    src = ("class UscTexBadParam expands Object;\n\n"
          "#exec TEXTURE IMPORT NAME=X FILE=Textures\\X.PCX GROUP=Foo\n")
    env = InstallEnv([str(_UED22)])
    with pytest.raises(NotImplementedError, match="GROUP"):
        compile_package(src, env, texture_files={"Textures\\X.PCX": b""})


# ── docker-gated fresh rebuild ────────────────────────────────────────────────────────────────────
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
def test_textureimport_matches_fresh_ucc(tmp_path):
    from uedcli.uscript.reference import ucc_compile, ucc_container
    src = (_FIX / "UscTexAsym4x4.uc").read_text()
    with ucc_container(state_dir=tmp_path) as c:
        fresh = ucc_compile(c, "UscTexAsym4x4", {"UscTexAsym4x4.uc": src},
                            extra_files={"Textures/Asym4x4Tex.PCX": _pcx_bytes()})
    r = gate(_compile(), fresh)
    assert r.passed, " | ".join(r.messages)
