"""Integration test for the UCC reference toolchain (`uedcli.uscript.reference`).

Needs a live docker daemon + the committed UED22 substrate (the build container's compiler). It
gates the SAME way `test_import_verb.py` does — a module-level `skipif` — so `-k uscript_reference`
runs it when docker is up and skips cleanly otherwise, rather than erroring on collection.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.reference import ucc_compile, ucc_container

_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
_PKG_MAGIC = 0x9E2A83C1


def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not (_docker_up() and (_UED22 / "UCC.exe").is_file()),
    reason="needs a live docker daemon and the committed UED22 substrate (UCC.exe)")


def test_compiles_a_trivial_package(tmp_path):
    """`class UscHello expands Object;` compiles to a real UE1 package: magic 0x9E2A83C1 and larger
    than a 64-byte empty/failed stub."""
    with ucc_container(state_dir=tmp_path) as container:
        u = ucc_compile(container, "UscHello",
                        {"UscHello.uc": "class UscHello expands Object;\n"})
    assert len(u) > 64, f"output .u is only {len(u)} bytes (empty/failed compile)"
    assert struct.unpack_from("<I", u, 0)[0] == _PKG_MAGIC
