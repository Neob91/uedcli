"""Real stock UnrealScript packages compiled byte-exact vs UCC, via `gate.perm_gate`.

These are the first entries of the byte-parity corpus: pure-script brush-builder packages from
`uned/UED22` (no `native noexport`), so their UCC-decompiled sources recompile under UCC. Each
fixture is `fixtures/uscript/realpkg/<Pkg>/`: the decompiled `.uc` sources plus `<Pkg>.u`, a FRESH
`UCC make` of exactly those sources (the reference — NOT the shipped package, whose class default
block is editor-serialized and drops own zero-valued props).

Two checks per package:
  1. OFFLINE (no docker): `perm_gate(compile_package_dir(sources), committed_golden)` is byte-exact
     modulo the documented exclusions (GUID + name/import/export table ORDER + FName CASE).
  2. DOCKER-GATED: rebuild the golden with UCC from the committed sources and re-gate, catching any
     drift between the committed golden and today's UCC.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_package_dir
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import gate, perm_gate
from uedcli.uscript.serialize import serialize

_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript" / "realpkg"
_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

# (package, class count) — pins the export identity coverage per package.
_PACKAGES = [("FrameBuilder", 1), ("RahnemBrushBuilders", 1), ("ExtendedBuilders", 2),
             ("DavesBrushBuilders", 1)]


def _sources(pkg: str) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted((_FIX / pkg).glob("*.uc"))}


def _compile(pkg: str) -> bytes:
    return serialize(compile_package_dir(_sources(pkg), InstallEnv([str(_UED22)]), package_name=pkg))


def _class_count(u: bytes) -> int:
    import tempfile, os
    from uedcli.upackage import load_package
    fd, p = tempfile.mkstemp(suffix=".u", dir=os.environ.get("TMPDIR")); os.close(fd)
    try:
        Path(p).write_bytes(u)
        pk = load_package(p)
        return sum(1 for e in pk.exports if e["cls"] == 0)
    finally:
        os.unlink(p)


@pytest.mark.parametrize("pkg,classes", _PACKAGES)
def test_realpkg_offline_byte_exact(pkg: str, classes: int):
    """Autonomous compile of the committed sources passes `perm_gate` against the committed UCC
    golden, and carries the expected class count."""
    mine = _compile(pkg)
    assert _class_count(mine) == classes
    r = perm_gate(mine, (_FIX / pkg / f"{pkg}.u").read_bytes())
    assert r.passed, f"{pkg}: " + " | ".join(r.messages)


@pytest.mark.parametrize("pkg", ["FrameBuilder", "RahnemBrushBuilders"])
def test_realpkg_strict_byte_exact(pkg: str):
    """These two also pass the STRICT gate (name/import/export table ORDER included, not just
    content) with no `order_override` — `RahnemBrushBuilders` pins the value-only-name gather-order
    fix (a package self-name in `PackageImports` registers at class-header time; a defaultproperties
    tag VALUE registers after every member/function, per `ordering._gather_names`/`late_name_refs`).
    `ExtendedBuilders` still fails on raw byte count (unrelated, likely multi-class); `DavesBrush
    Builders` fails on name-table order (an enum-value sub-ordering gap) — both open, not this fix."""
    r = gate(_compile(pkg), (_FIX / pkg / f"{pkg}.u").read_bytes())
    assert r.passed, f"{pkg}: " + " | ".join(r.messages)


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
@pytest.mark.parametrize("pkg,classes", _PACKAGES)
def test_realpkg_matches_fresh_ucc(pkg: str, classes: int, tmp_path):
    """A fresh `UCC make` of the committed sources still matches our compile — guards against golden
    drift from today's toolchain."""
    from uedcli.uscript.reference import ucc_compile, ucc_container
    sources = _sources(pkg)
    with ucc_container(state_dir=tmp_path) as container:
        fresh = ucc_compile(container, pkg, sources)
    r = perm_gate(_compile(pkg), fresh)
    assert r.passed, f"{pkg} vs fresh UCC: " + " | ".join(r.messages)
