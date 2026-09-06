"""Whole-package compile (`uscript.compile.compile_package_dir`): many `.uc` -> ONE `.u` with shared
name/import/export tables, byte-exact vs UCC under the identity/permutation gate (`gate.perm_gate`).

The offline tests run `compile_package_dir` and `perm_gate` against committed UCC goldens (built by
`UCC make`, see `test_goldens_match_ucc` for the recipe). They pin:
  - same-package super: `Derived expands Base` -> Base is an EXPORT ref, not an import (`pkg_TwoCls`);
  - same-package super CHAIN `A<-B<-C` with virtual calls up the chain (`pkg_ChainPkg`);
  - a non-Core super (`BrushBuilder` in Editor) across two classes: the shared Editor import and the
    per-class `[<pkg>, Editor, Core]` PackageImports (`pkg_TwoBB`).

`test_goldens_match_ucc` (docker-gated) rebuilds the goldens with UCC and re-gates, so the committed
fixtures can't silently drift from the compiler.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_package_dir
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import perm_gate
from uedcli.uscript.serialize import serialize

_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript"
_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

# package name -> {filename: source}. The source UCC compiled each committed golden from.
_PACKAGES: dict[str, dict[str, str]] = {
    "TwoCls": {
        "Base.uc": "class Base expands Object;\n\nvar int N;\n\nfunction int Get() { return N; }\n",
        "Derived.uc": "class Derived expands Base;\n\nfunction int GetPlus() { return Get() + 1; }\n",
    },
    "ChainPkg": {
        "A.uc": "class A expands Object;\n\nvar int N;\n\nfunction int Get() { return N; }\n",
        "B.uc": "class B expands A;\n\nfunction int GetB() { return Get() + 1; }\n",
        "C.uc": "class C expands B;\n\nfunction int GetC() { return GetB() * 2; }\n",
    },
    "TwoBB": {
        "BBAlpha.uc": "class BBAlpha expands BrushBuilder;\n\nvar int Alpha;\n",
        "BBBeta.uc": "class BBBeta expands BrushBuilder;\n\nvar float Beta;\n",
    },
}


def _env() -> InstallEnv:
    return InstallEnv([str(_UED22)])


def _compile(name: str) -> bytes:
    return serialize(compile_package_dir(_PACKAGES[name], _env(), package_name=name))


def _check(name: str) -> None:
    golden = (_FIX / f"pkg_{name}.u").read_bytes()
    r = perm_gate(_compile(name), golden)
    assert r.passed, f"{name}: " + " | ".join(r.messages)


def test_two_class_same_package_super():
    """`Derived expands Base` (same package) + a cross-class virtual call `Get()`. Base is an export
    ref (SuperField/Dependency), not an import."""
    _check("TwoCls")


def test_three_class_chain():
    """A 3-class same-package chain `A<-B<-C` with virtual calls up the chain — exercises the
    incremental in-package graph (each class sees its already-compiled supers)."""
    _check("ChainPkg")


def test_two_class_noncore_super():
    """Two classes expanding `BrushBuilder` (Editor): one shared Editor import, and each class's
    PackageImports = `[TwoBB, Editor, Core]`."""
    _check("TwoBB")


def test_perm_gate_catches_wrong_body():
    """A genuine divergence FAILS: compiling `Base.Get` as `return N + 1` must not pass against the
    `return N` golden."""
    pkg = dict(_PACKAGES["TwoCls"])
    pkg["Base.uc"] = pkg["Base.uc"].replace("return N;", "return N + 1;")
    mine = serialize(compile_package_dir(pkg, _env(), package_name="TwoCls"))
    r = perm_gate(mine, (_FIX / "pkg_TwoCls.u").read_bytes())
    assert not r.passed
    assert any("BODY" in m for m in r.messages)


def test_inherited_default_now_compiles():
    """Setting an INHERITED member in `defaultproperties` (a `BrushBuilder` subclass's
    `BitmapFilename`, inherited from `BrushBuilder`) now compiles — the type is resolved across the
    super chain and the override tag emitted. (Was a NotImplementedError frontier; fixed alongside
    the brush-builder corpus work — ExtendedBuilders exercises it end-to-end.)"""
    src = ("class Foo expands BrushBuilder;\n\n"
           "defaultproperties\n{\n     BitmapFilename=\"x\"\n}\n")
    out = serialize(compile_package_dir({"Foo.uc": src}, _env(), package_name="Foo"))
    assert out[:4] == b"\xc1\x83\x2a\x9e"   # a valid UE1 package, no exception


# ── docker-gated: rebuild the goldens with UCC and re-gate (keeps the fixtures honest) ──────────────
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
@pytest.mark.parametrize("name", list(_PACKAGES))
def test_goldens_match_ucc(tmp_path, name):
    """`perm_gate(compile_package_dir(...), UCC.make(...))` is byte-exact for a FRESH UCC build — and
    the committed golden matches that fresh build. Recipe: `UCC make` over `<pkg>/Classes/*.uc`."""
    from uedcli.uscript.reference import ucc_compile, ucc_container
    with ucc_container(state_dir=tmp_path) as container:
        fresh = ucc_compile(container, name, _PACKAGES[name])
    assert perm_gate(_compile(name), fresh).passed, f"{name}: compile != fresh UCC"
    assert perm_gate((_FIX / f"pkg_{name}.u").read_bytes(), fresh).passed, \
        f"{name}: committed golden != fresh UCC (regenerate the fixture)"
