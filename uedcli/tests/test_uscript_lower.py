"""AST -> bytecode lowering: `lower_function` must reproduce UCC's exact token stream.

The oracle is UCC itself: `natives.read_function` decodes a compiled `UFunction`'s script back to
`list[Tok]` (index-independent — obj/name refs resolve to their NAME). A lowered function must equal
that, modulo FName case (`lower.toks_equal` / `canon` — the owner+opus FName-case exclusion, since the
editor spells locals from its boot name pool, e.g. `A` for source `a`).

Two tiers:
- OFFLINE (always runs): committed `.u` goldens (`fixtures/uscript/`) + the catalog read from the
  committed `uned/UED22/core.u`. No docker.
- DOCKER-GATED: recompile the same sources with UCC and re-check (keeps the goldens honest), plus a
  breadth smoke over real stock functions in `Extension.u`.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.upackage import load_package
from uedcli.uscript.bytecode import Tok
from uedcli.uscript.lower import (build_scope, canon, consts_of, enum_type_names, enums_of,
                                  local_funcs_of, lower_function, members_of, toks_equal)
from uedcli.uscript.natives import iter_functions, load_catalog, load_graph, read_function
from uedcli.uscript.parser import parse

_ROOT = Path(__file__).resolve().parents[2]
_UED22 = _ROOT / "uned" / "UED22"
_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript"

# The sources that produced the committed goldens (recompiled verbatim by the docker tests).
SRC_L = (
    "class UscL expands Object;\n"
    "function F1(){}\n"
    "function F2(){ return; }\n"
    "function int F3(){ return 5; }\n"
    "function F4(){ local int x; x=3; }\n"
    "function int F5(int a,int b){ return a+b; }\n"
    "function F6(){ Log(\"hi\"); }\n"
    "function bool F7(int a){ return a>2; }\n"
)
SRC_W = (_FIX / "UscW.uc").read_text() if (_FIX / "UscW.uc").exists() else None


def _catalog():
    return load_catalog(str(_UED22), packages=("core.u",))


def _lower_all(src: str, catalog, graph=None):
    """Lower every function in `src`; return {name: list[Tok]}."""
    decl = parse(src)
    enames = enum_type_names(decl.members)
    members = members_of(decl.members, graph)
    funcs = local_funcs_of(decl.functions, graph, enames)
    enums = enums_of(decl.members)
    consts = consts_of(decl.members)
    out = {}
    for f in decl.functions:
        scope = build_scope(f, members=members, funcs=funcs, class_name=decl.name,
                            super_name=decl.super_name, graph=graph, enums=enums, enum_names=enames,
                            consts=consts)
        out[f.name] = lower_function(f, scope, catalog)
    return out


def _gold_from_package(pkg):
    return {fb.name: list(fb.tokens) for fb in iter_functions(pkg)}


# ── the F1..F7 spec targets (from the lowering spec; obj names compared case-insensitively) ────────
def _ret_nothing():
    return Tok(0x04, (("sub", Tok(0x0B)),))


F_TARGETS = {
    "F1": [_ret_nothing()],
    "F2": [_ret_nothing(), _ret_nothing()],
    "F3": [Tok(0x04, (("sub", Tok(0x2C, (("raw", b"\x05"),))),)), _ret_nothing()],
    "F4": [Tok(0x0F, (("sub", Tok(0x00, (("obj", "x"),))),
                      ("sub", Tok(0x2C, (("raw", b"\x03"),))))), _ret_nothing()],
    "F5": [Tok(0x04, (("sub", Tok(0x92, (("parms", (
        Tok(0x00, (("obj", "a"),)), Tok(0x00, (("obj", "b"),)), Tok(0x16))),))),)), _ret_nothing()],
    "F6": [Tok(0xE7, (("parms", (Tok(0x1F, (("raw", b"hi\x00"),)), Tok(0x16))),)), _ret_nothing()],
    "F7": [Tok(0x04, (("sub", Tok(0x97, (("parms", (
        Tok(0x00, (("obj", "a"),)), Tok(0x2C, (("raw", b"\x02"),)), Tok(0x16))),))),)),
        _ret_nothing()],
}


def test_f1_f7_match_spec_targets():
    """F1..F7 lower to the exact token streams the spec measured from UCC."""
    lowered = _lower_all(SRC_L, _catalog())
    for name, target in F_TARGETS.items():
        assert toks_equal(lowered[name], target), name


def test_f1_f7_match_committed_golden():
    """F1..F7 equal UCC's own compiled bytecode (committed golden `UscL.u`)."""
    gold = _gold_from_package(load_package(str(_FIX / "UscL.u")))
    lowered = _lower_all(SRC_L, _catalog())
    for name in F_TARGETS:
        assert toks_equal(lowered[name], gold[name]), name


@pytest.mark.skipif(SRC_W is None, reason="UscW.uc source fixture missing")
def test_broad_constructs_match_committed_golden():
    """Members, all arithmetic/comparison/logical/bitwise ops, casts, if/else-if, while, for,
    break/continue, and script+final+native calls — each token-exact vs the committed `UscW.u`."""
    gold = _gold_from_package(load_package(str(_FIX / "UscW.u")))
    lowered = _lower_all(SRC_W, _catalog())
    mismatched = [n for n in lowered if not toks_equal(lowered[n], gold[n])]
    assert not mismatched, f"token mismatch in: {mismatched}"


def test_catalog_indices():
    """The native catalog resolves the measured operator/function indices."""
    cat = _catalog()
    assert cat.binary_operator("+", "int", "int").inative == 146
    assert cat.binary_operator(">", "int", "int").inative == 151
    assert cat.binary_operator("+", "float", "float").inative == 174
    assert cat.function("Log", ("string",)).inative == 231
    assert len(cat.funcs) > 100


# ── docker-gated: recompile with UCC and re-verify + breadth smoke ─────────────────────────────────
def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


_DOCKER = pytest.mark.skipif(
    not (_docker_up() and (_UED22 / "UCC.exe").is_file()),
    reason="needs a live docker daemon and the committed UED22 substrate (UCC.exe)")


@pytest.mark.integration
@_DOCKER
def test_recompiled_goldens_still_match(tmp_path):
    """Recompile SRC_L and SRC_W with UCC now and re-check — the committed goldens stay current."""
    from uedcli.uscript.reference import ucc_compile, ucc_container
    cat = _catalog()
    with ucc_container(state_dir=tmp_path) as c:
        for pkg_name, src in (("UscL", SRC_L), ("UscW", SRC_W)):
            u = ucc_compile(c, pkg_name, {f"{pkg_name}.uc": src})
            p = tmp_path / f"{pkg_name}.u"
            p.write_bytes(u)
            gold = _gold_from_package(load_package(str(p)))
            lowered = _lower_all(src, cat)
            bad = [n for n in lowered if not toks_equal(lowered[n], gold[n])]
            assert not bad, f"{pkg_name}: {bad}"


@pytest.mark.integration
@_DOCKER
def test_real_stock_functions_breadth(tmp_path):
    """Whole real functions from a decompiled stock package (`Extension`) lower token-exact. Records
    the pass rate; asserts a floor and ZERO mismatches among supported constructs (unsupported ones —
    member access, inherited symbols — raise `LowerError` and are excluded, not silently passed)."""
    from uedcli.uscript.lower import LowerError
    from uedcli.uscript.reference import ucc_container, ucc_decompile
    with ucc_container(state_dir=tmp_path) as c:
        srcs = ucc_decompile(c, "Extension")
    cat = load_catalog(str(_UED22), packages=("core.u", "Engine.u"))
    graph = load_graph(str(_UED22), packages=("core.u", "Engine.u", "Extension.u"))
    pkg = load_package(str(_UED22 / "Extension.u"))
    gold = {(read_function(pkg, i + 1).class_name, read_function(pkg, i + 1).name):
            read_function(pkg, i + 1).tokens
            for i, e in enumerate(pkg.exports) if pkg.name_of_ref(e["cls"]) == "Function"}
    npass = nmismatch = 0
    for src in srcs.values():
        decl = parse(src)
        enames = enum_type_names(decl.members)
        members = members_of(decl.members, graph)
        funcs = local_funcs_of(decl.functions, graph, enames)
        enums = enums_of(decl.members)
        consts = consts_of(decl.members)
        for fn in decl.functions:
            key = (decl.name, fn.name)
            if not fn.has_body or key not in gold:
                continue
            scope = build_scope(fn, members=members, funcs=funcs, class_name=decl.name,
                                super_name=decl.super_name, graph=graph, enums=enums,
                                enum_names=enames, consts=consts)
            try:
                mine = lower_function(fn, scope, cat)
            except LowerError:
                continue
            if toks_equal(mine, list(gold[key])):
                npass += 1
            else:
                nmismatch += 1
    assert nmismatch == 0, f"{nmismatch} real-function token mismatches"
    assert npass >= 55, f"only {npass} real Extension functions lowered token-exact"
