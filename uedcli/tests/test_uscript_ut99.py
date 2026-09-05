"""UT99 corpus: uedcli's compiler is byte-exact vs UT99's own UCC, via `gate.perm_gate`.

Two layers:
  1. The UT99 reference toolchain (`reference_ut99`): UT99's own `UCC.exe`+DLLs+`.u` (fetched by
     `uedcli/uscript/fetch_ut99.sh` into `uned/UT99/System/`, gitignored) compile/decompile UT99
     packages. Needs docker + the substrate.
  2. uedcli's `compile_package_dir` vs a committed UCC golden. Each fixture is
     `fixtures/uscript/ut99/<Pkg>/`: the `.uc` sources plus `<Pkg>.u`, a fresh `ucc_compile_ut99` of
     exactly those sources. The OFFLINE check needs no docker but does need the substrate `.u` on the
     search path (to resolve supers); a DOCKER-gated check rebuilds the golden and re-gates.

Fixtures (each isolates a compiler gap fixed for the first UT99 packages):
  - `Fire`         - 6 native texture classes: a non-scalar struct member (ESpark in `Spark`),
                     `array<Spark>`, native-class ObjectFlags/ClassFlags/PackageImports, explicit-only
                     defaults.
  - `UscEnumDef`   - an inherited enum-name default (`RemoteRole=ROLE_SimulatedProxy`) resolved to its
                     byte ordinal against the inherited `ENetRole`.
  - `UscTextPos`   - function Line/TextPos located by the actual declaration, not a bare name-`(`
                     substring (here `Beta` is called before it is declared).
"""
from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_package_dir
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import perm_gate
from uedcli.uscript.reference_ut99 import (UccError, ucc_compile_ut99, ucc_decompile_ut99,
                                           ut99_container, ut99_substrate_dir)
from uedcli.uscript.serialize import serialize

_PKG_MAGIC = 0x9E2A83C1
_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript" / "ut99"

# (package, export count) - the byte-parity corpus; count pins export-identity coverage.
_PACKAGES = [("Fire", 108), ("UscEnumDef", 2), ("UscTextPos", 12)]


def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _substrate_present() -> bool:
    try:
        ut99_substrate_dir()
        return True
    except UccError:
        return False


def _sources(pkg: str) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted((_FIX / pkg).glob("*.uc"))}


def _compile(pkg: str) -> bytes:
    env = InstallEnv([str(ut99_substrate_dir())])
    return serialize(compile_package_dir(_sources(pkg), env, package_name=pkg))


# ── offline: compiler vs committed golden (needs the substrate .u, not docker) ────────────────────
@pytest.mark.skipif(not _substrate_present(),
                    reason="needs the fetched UT99 substrate (uedcli/uscript/fetch_ut99.sh)")
@pytest.mark.parametrize("pkg,exports", _PACKAGES)
def test_ut99_offline_byte_exact(pkg: str, exports: int):
    golden = (_FIX / pkg / f"{pkg}.u").read_bytes()
    mine = _compile(pkg)
    assert struct.unpack_from("<I", mine, 0)[0] == _PKG_MAGIC
    assert struct.unpack_from("<I", golden, 20)[0] == exports, f"{pkg}: golden export count"
    r = perm_gate(mine, golden)
    assert r.passed, f"{pkg}: " + " | ".join(r.messages)


# ── docker-gated: rebuild the golden with UT99's UCC and re-gate (guards golden drift) ─────────────
@pytest.mark.skipif(not (_docker_up() and _substrate_present()),
                    reason="needs a live docker daemon and the fetched UT99 substrate")
@pytest.mark.parametrize("pkg,exports", _PACKAGES)
def test_ut99_matches_fresh_ucc(pkg: str, exports: int, tmp_path):
    with ut99_container(state_dir=tmp_path) as c:
        fresh = ucc_compile_ut99(c, pkg, _sources(pkg))
    r = perm_gate(_compile(pkg), fresh)
    assert r.passed, f"{pkg} vs fresh UCC: " + " | ".join(r.messages)


# ── the UT99 reference toolchain is self-consistent (compile/decompile round-trip) ────────────────
@pytest.mark.skipif(not (_docker_up() and _substrate_present()),
                    reason="needs a live docker daemon and the fetched UT99 substrate")
def test_trivial_compile(tmp_path):
    with ut99_container(state_dir=tmp_path) as c:
        u = ucc_compile_ut99(c, "UscHelloUT",
                             {"UscHelloUT.uc": "class UscHelloUT expands Object;\n"})
    assert len(u) > 64
    assert struct.unpack_from("<I", u, 0)[0] == _PKG_MAGIC


@pytest.mark.skipif(not (_docker_up() and _substrate_present()),
                    reason="needs a live docker daemon and the fetched UT99 substrate")
def test_ipserver_roundtrips(tmp_path):
    """A code-only stock package decompiles then recompiles under UT99's own toolchain."""
    with ut99_container(state_dir=tmp_path) as c:
        sources = ucc_decompile_ut99(c, "IpServer")
        assert sources, "no classes decompiled from IpServer"
        u = ucc_compile_ut99(c, "IpServer", sources)
    assert len(u) > 64
    assert struct.unpack_from("<I", u, 0)[0] == _PKG_MAGIC
