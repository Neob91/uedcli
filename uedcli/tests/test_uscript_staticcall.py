"""`X.static.Method(...)` -- a static function called through an instance expression. Found
compiling the real UT99 `IpServer` package (`USCRIPT-COMPILER.md`): `UdpServerQuery.GetPlayer` has
`P.static.GetMultiSkin(P, SkinName, FaceName)`.

Probed live against UED22 UCC: `X.static.Method(args)` and `X.Method(args)` compile to
BYTE-IDENTICAL bytecode -- `.static.` is a compile-time-only permission marker, not a separate
opcode. `lower.py`'s `_ex_call` unwraps a `.static.` member sitting between a call target and its
base, dropping straight to an ordinary method call.

This fixture asserts the FUNCTION-LEVEL bytecode (`Foo`, which uses `.static.`, and `Foo2`, the
plain-call control) byte-exact against a fresh UED22 UCC build, rather than a whole-package `gate()`
verdict: the fixture's class-level body hits an unrelated, pre-existing Dependencies-array gap (a
same-class-typed parameter's Context apparently needs an entry our self/super-skip heuristic drops --
`dev/docs/board/inbox/uscript-same-class-typed-param-context-under/`), orthogonal to this fix.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from uedcli.upackage import load_package, read_compact_index as _rci
from uedcli.uscript.bytecode import decode_script
from uedcli.uscript.compile import compile_package_dir
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.serialize import serialize

_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript"
_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
_SRC = (_FIX / "UscStaticThroughInstance.uc").read_text()
_PKG = "UscStaticThroughInstance"


def _compile() -> bytes:
    return serialize(compile_package_dir({f"{_PKG}.uc": _SRC}, InstallEnv([str(_UED22)]),
                                         package_name=_PKG))


def _resolve(pkg):
    def resolve(kind, index):
        if kind == "name":
            return pkg.names[index] if 0 <= index < len(pkg.names) else f"?name{index}"
        if index == 0:
            return "None"
        return f"{pkg.object_class_name(index)}'{pkg.object_path(index)}'"
    return resolve


def _function_tokens(u_bytes: bytes) -> dict[str, tuple]:
    """{function name -> decoded top-level tokens} for every UFunction/UState export."""
    pkg = load_package_from_bytes(u_bytes)
    resolve = _resolve(pkg)
    out = {}
    for e in pkg.exports:
        if pkg.name_of_ref(e["cls"]) not in ("Function", "State") or e["ssize"] <= 0:
            continue
        sym = pkg.names[e["nm"]]
        buf, p = pkg.buf, e["soff"]
        for _ in range(6):
            _, p = _rci(buf, p)
        p += 8
        script_size = struct.unpack_from("<I", buf, p)[0]
        p += 4
        toks, _ = decode_script(buf, p, script_size, resolve)
        out[sym] = tuple(toks)
    return out


def load_package_from_bytes(u_bytes: bytes):
    """Write to a file named exactly `<_PKG>.u` -- `load_package` derives each decoded object's
    "package" path segment from the file's own stem, and the golden was built as `_PKG`, so a
    differently-named scratch file would make otherwise-identical tokens compare unequal."""
    import tempfile
    d = tempfile.mkdtemp()
    path = Path(d) / f"{_PKG}.u"
    path.write_bytes(u_bytes)
    return load_package(str(path))


def test_static_through_instance_functions_byte_exact():
    golden = (_FIX / "UscStaticThroughInstance.u").read_bytes()
    mine_funcs = _function_tokens(_compile())
    golden_funcs = _function_tokens(golden)
    for name in ("Foo", "Foo2", "Bar"):
        assert name in mine_funcs, f"{name} missing from my compile"
        assert mine_funcs[name] == golden_funcs[name], f"{name} bytecode diverges from golden"


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
def test_static_through_instance_functions_match_fresh_ucc(tmp_path):
    from uedcli.uscript.reference import ucc_compile, ucc_container
    with ucc_container(state_dir=tmp_path) as c:
        fresh = ucc_compile(c, _PKG, {f"{_PKG}.uc": _SRC})
    mine_funcs = _function_tokens(_compile())
    fresh_funcs = _function_tokens(fresh)
    for name in ("Foo", "Foo2", "Bar"):
        assert mine_funcs[name] == fresh_funcs[name], f"{name} bytecode diverges from fresh UCC"
