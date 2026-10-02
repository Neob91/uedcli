"""Autonomous `.u` compilation (no golden `order_override`) verified against UCC by the identity/
permutation parity gate (`gate.perm_gate`).

Three things are pinned here:
  1. Name-table FLAGS: `_name_flags` reproduces every committed golden's per-name u32 byte-exact,
     driven by the engine boot global name pool (`global_index.engine_name_pool`) — no masking.
  2. Autonomous ordering: `compile_package(src, env)` with NO override produces a VALID, loadable,
     self-consistent package for every member kind (scalar + enum/const/struct/array/object).
  3. `perm_gate`: identity-matches exports, requires each matched body byte-identical after ref
     canonicalisation, and matches name CONTENT+FLAGS / import CONTENT / export identity SET, modulo
     the documented exclusions (GUID + table ORDER + FName CASE). A genuine divergence still FAILS.
"""
from __future__ import annotations

import struct
from pathlib import Path

from uedcli.upackage import load_package, read_fstring
from uedcli.uscript.compile import _name_flags, compile_package
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import perm_gate
from uedcli.uscript.global_index import engine_name_pool
from uedcli.uscript.serialize import serialize

_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript"
_UED22 = str(Path(__file__).resolve().parents[2] / "uned" / "UED22")

# Scalar/declaration-only sources (no function lowering) — their autonomous compile is fully
# self-contained (matches the goldens the compile suite pins with an override).
_SCALAR_SOURCES = {
    "UscHello": "class UscHello expands Object;\n",
    "UscVars": ("class UscVars expands Object;\n\n"
                "var int Alpha;\nvar float Beta;\nvar string Gamma;\n\n"
                "defaultproperties\n{\n     Alpha=7\n     Beta=1.500000\n}\n"),
    "UscBB": ("class UscBB expands Object;\n\n"
              "var byte Bode;\nvar bool Blip;\nvar name Naym;\n\n"
              "defaultproperties\n{\n     Bode=3\n     Blip=True\n     Naym=Wobbl\n}\n"),
}

# Function classes: exercise the general (any-kind) autonomous ordering + bytecode. UscFn is the F1-F7
# spec set; UscW is a 21-function class (operators, if/else, while/for, break/continue, casts, own-
# member access, script/final/native calls).
_USC_FN_SRC = (
    "class UscFn expands Object;\n\n"
    "function F1() {}\n"
    "function F2() { return; }\n"
    "function int F3() { return 5; }\n"
    "function F4() { local int x; x = 3; }\n"
    "function int F5(int a, int b) { return a + b; }\n"
    "function F6() { Log(\"hi\"); }\n"
    "function bool F7(int a) { return a > 2; }\n"
)
_ALL_FIXTURES = ("UscHello", "UscVars", "UscBB", "UscFn", "UscW", "UscL")


def _env() -> InstallEnv:
    return InstallEnv([_UED22])


def _golden_name_flags(path: Path) -> list[tuple[str, int]]:
    buf = path.read_bytes()
    _tag, _ver, _fl, nc, no, _ec, _eo, _ic, _io = struct.unpack_from("<9I", buf, 0)
    out, pos = [], no
    for _ in range(nc):
        s, pos = read_fstring(buf, pos)
        out.append((s, struct.unpack_from("<I", buf, pos)[0]))
        pos += 4
    return out


# ── 1. name-table flags ─────────────────────────────────────────────────────────────────────────
def test_name_flags_reproduce_golden_byte_exact():
    """`_name_flags(name)` equals every committed golden's stored per-name u32 — the RF_Native
    (0x04000000) boot-pool bit included, no masking. Covers `UscW`'s `Add` (an intrinsic not present
    in any stock name table) and confirms `ScriptText`/`ReturnValue` stay unflagged."""
    for cls in ("UscHello", "UscVars", "UscBB", "UscFn", "UscW"):
        for name, flags in _golden_name_flags(_FIX / f"{cls}.u"):
            assert _name_flags(name) == flags, f"{cls}: {name!r} {_name_flags(name):#x} != {flags:#x}"


def test_engine_pool_shape():
    """The pool is casefolded; native intrinsics are in, package-created names are out."""
    pool = engine_name_pool()
    assert "add" in pool and "tag" in pool and "core" in pool and "intproperty" in pool
    assert "scripttext" not in pool and "returnvalue" not in pool
    assert all(n == n.casefold() for n in pool)


# ── 2. autonomous ordering produces a valid package ───────────────────────────────────────────────
def _assert_loads_consistent(buf: bytes, class_name: str) -> None:
    import os, tempfile
    fd, p = tempfile.mkstemp(suffix=".u", dir=os.environ.get("TMPDIR"))
    os.close(fd)
    try:
        Path(p).write_bytes(buf)
        pkg = load_package(p)
    finally:
        os.unlink(p)
    for e in pkg.exports:                                # every name index + outer ref in range
        assert 0 <= e["nm"] < len(pkg.names)
        assert -len(pkg.imports) <= e["outer"] <= len(pkg.exports)
    assert [pkg.names[e["nm"]] for e in pkg.exports if e["cls"] == 0] == [class_name]


def test_autonomous_general_order_loads():
    """A class using every non-scalar kind (enum/const/struct/static-array/dynamic-array/object)
    compiles with NO override and loads self-consistently — the general ordering path."""
    src = ("class UscGen expands Object;\n\n"
           "enum EColor { EC_Red, EC_Green, EC_Blue };\n"
           "const K = 5;\n"
           "struct SPoint { var int X; var int Y; };\n"
           "var int Nums[3];\n"
           "var array<int> Dyn;\n"
           "var EColor Col;\n"
           "var SPoint Pt;\n")
    _assert_loads_consistent(serialize(compile_package(src, _env())), "UscGen")


# ── 3. perm_gate ──────────────────────────────────────────────────────────────────────────────────
def test_perm_gate_self_identity():
    """`perm_gate(golden, golden)` passes for every committed fixture (includes function classes, so
    the script-decode path is exercised)."""
    for cls in _ALL_FIXTURES:
        buf = (_FIX / f"{cls}.u").read_bytes()
        r = perm_gate(buf, buf)
        assert r.passed, f"{cls} self-identity: {r.messages}"


def test_autonomous_compile_passes_perm_gate():
    """The end-to-end proof: `perm_gate(serialize(compile_package(src, env)), golden)` — compiled
    AUTONOMOUSLY (no order_override) — passes for the scalar classes and the function classes
    (UscFn, UscW)."""
    cases = dict(_SCALAR_SOURCES)
    cases["UscFn"] = _USC_FN_SRC
    cases["UscW"] = (_FIX / "UscW.uc").read_text()
    for cls, src in cases.items():
        golden = (_FIX / f"{cls}.u").read_bytes()
        mine = serialize(compile_package(src, _env()))   # NO override
        r = perm_gate(mine, golden)
        assert r.passed, f"{cls}: " + " | ".join(r.messages)


def test_perm_gate_catches_wrong_default():
    """A genuine body divergence FAILS: compiling UscVars with `Alpha=8` must not pass against the
    `Alpha=7` golden — the gate is not a rubber stamp."""
    bad_src = _SCALAR_SOURCES["UscVars"].replace("Alpha=7", "Alpha=8")
    mine = serialize(compile_package(bad_src, _env()))
    r = perm_gate(mine, (_FIX / "UscVars.u").read_bytes())
    assert not r.passed
    assert any("BODY" in m for m in r.messages)


def test_perm_gate_catches_wrong_name_flag():
    """A wrong name-table FLAG FAILS (RF_Native bit forced off) — flags are compared, not excluded."""
    buf = bytearray((_FIX / "UscHello.u").read_bytes())
    _tag, _ver, _fl, nc, no, *_ = struct.unpack_from("<9I", buf, 0)
    pos = no
    for _ in range(nc):
        _s, pos = read_fstring(bytes(buf), pos)
        struct.pack_into("<I", buf, pos, struct.unpack_from("<I", buf, pos)[0] & ~0x04000000)
        pos += 4
    r = perm_gate((_FIX / "UscHello.u").read_bytes(), bytes(buf))
    assert not r.passed
    assert any("FLAGS" in m for m in r.messages)
