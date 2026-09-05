"""Byte-exact round-trip oracle for the UnrealScript bytecode codec (`uscript.bytecode`).

The oracle needs no ordering/emit knowledge: for every real `UFunction`/`UState` export in the
git-tracked UED22 corpus, locate its compiled script byte range and assert
`encode_script(decode_script(original)) == original`. A miss means an unhandled opcode or a wrong
operand shape — the failure names the package, symbol, and first differing offset.

Object/name compact refs are made index-INDEPENDENT via `resolve`, then re-indexed via `resolve_inv`
(a per-package bijection built here); duplicate name-table slots — `ubrowser.u`/`uwindow.u` carry 26
`None`s — are disambiguated with a `#<index>` suffix, which `bytecode._is_none_name` strips for
LabelTable-terminator detection.
"""
from __future__ import annotations

import struct

import pytest

from uedcli.upackage import load_package, read_compact_index, read_compact_index as _rci
from uedcli.uprops.ufield import _skip_script
from uedcli.uscript.bytecode import Tok, decode_script, encode_script, write_compact_index

from .conftest import ued22_root

# Packages known to carry UFunction/UState exports; `ubrowser`/`uwindow` exercise the duplicate-None
# LabelTable-terminator path.
_CORPUS = [
    "Engine", "core", "ConSys", "UnrealShare", "Extension", "FrameBuilder",
    "DeusEx", "editor", "ubrowser", "uwindow",
]

pytestmark = pytest.mark.skipif(
    not (ued22_root() / "Engine.u").is_file(),
    reason="git-tracked UED22/Engine.u not present")


def _build_resolvers(pkg):
    """Per-package bijective identity maps. Object identity = `Class'Path'`; name identity = the
    name string. Rare human-string collisions (an object path shared by two refs, or a duplicate
    name slot) get a `#<index>` suffix so the inverse stays exact."""
    obj_to_id: dict[int, str] = {}
    used: dict[str, int] = {}
    refs = [0] + list(range(1, len(pkg.exports) + 1)) + [-(j + 1) for j in range(len(pkg.imports))]
    for idx in refs:
        human = "None" if idx == 0 else f"{pkg.object_class_name(idx)}'{pkg.object_path(idx)}'"
        if used.get(human, idx) != idx:
            human = f"{human}#{idx}"
        used[human] = idx
        obj_to_id[idx] = human
    id_to_obj = {v: k for k, v in obj_to_id.items()}

    name_to_id: dict[int, str] = {}
    nused: set[str] = set()
    for i, s in enumerate(pkg.names):
        key = s if s not in nused else f"{s}#{i}"
        nused.add(key)
        name_to_id[i] = key
    id_to_name = {v: k for k, v in name_to_id.items()}

    def resolve(kind: str, index: int) -> str:
        return obj_to_id[index] if kind == "obj" else name_to_id[index]

    def resolve_inv(kind: str, ident: str) -> int:
        return id_to_obj[ident] if kind == "obj" else id_to_name[ident]

    return resolve, resolve_inv


def _script_range(pkg, e) -> tuple[int, int, int]:
    """(disk start, disk end, ScriptSize) of a UFunction/UState body's compiled script. Body =
    [None][SuperField][Next][ScriptText][Children][FriendlyName][Line u32][TextPos u32]
    [ScriptSize u32][script…]. The disk end comes from the reference skip walker."""
    buf, p = pkg.buf, e["soff"]
    for _ in range(6):                          # None, Super, Next, ScriptText, Children, FriendlyName
        _, p = _rci(buf, p)
    p += 8                                       # Line + TextPos
    script_size = struct.unpack_from("<I", buf, p)[0]; p += 4
    return p, _skip_script(pkg, p, script_size), script_size


@pytest.mark.parametrize("stem", _CORPUS)
def test_roundtrip_all_functions_and_states(stem):
    path = ued22_root() / f"{stem}.u"
    if not path.is_file():
        pytest.skip(f"{stem}.u not in checkout")
    pkg = load_package(str(path))
    resolve, resolve_inv = _build_resolvers(pkg)

    n = 0
    for e in pkg.exports:
        if pkg.name_of_ref(e["cls"]) not in ("Function", "State") or e["ssize"] <= 0:
            continue
        n += 1
        sym = pkg.names[e["nm"]]
        start, end, ssz = _script_range(pkg, e)
        original = pkg.buf[start:end]

        toks, new_pos = decode_script(pkg.buf, start, ssz, resolve)
        assert new_pos == end, f"{stem}.{sym}: decode stopped at {new_pos}, script ends {end}"

        encoded = encode_script(toks, resolve_inv)
        if encoded != original:
            diff = next((i for i in range(min(len(encoded), len(original)))
                         if encoded[i] != original[i]), min(len(encoded), len(original)))
            pytest.fail(f"{stem}.{sym}: re-encode differs at +{diff} "
                        f"(orig {len(original)}B, got {len(encoded)}B)")
    assert n > 0, f"{stem}.u had no UFunction/UState exports"


def test_full_corpus_no_unhandled_opcode():
    """Sweep EVERY package under `uned/UED22`, decoding+re-encoding every function/state. One
    assertion over the whole corpus so an unhandled opcode anywhere fails loudly with its symbol."""
    total = exact = 0
    failures: list[str] = []
    for path in sorted(ued22_root().glob("*.u")):
        pkg = load_package(str(path))
        resolve, resolve_inv = _build_resolvers(pkg)
        for e in pkg.exports:
            if pkg.name_of_ref(e["cls"]) not in ("Function", "State") or e["ssize"] <= 0:
                continue
            total += 1
            sym = f"{path.stem}.{pkg.names[e['nm']]}"
            try:
                start, end, ssz = _script_range(pkg, e)
                toks, new_pos = decode_script(pkg.buf, start, ssz, resolve)
                if new_pos != end or encode_script(toks, resolve_inv) != pkg.buf[start:end]:
                    failures.append(sym)
                else:
                    exact += 1
            except Exception as ex:                     # noqa: BLE001 — report, don't mask
                failures.append(f"{sym}: {ex!r}")
    assert not failures, f"{exact}/{total} byte-exact; {len(failures)} failed: {failures[:20]}"
    assert total > 3000, f"corpus sweep saw only {total} functions/states"


def test_write_compact_index_inverts_reader():
    for v in list(range(-70000, 70001)) + [1 << 20, -(1 << 24), (1 << 30) - 1]:
        got, pos = read_compact_index(write_compact_index(v), 0)
        assert got == v and pos == len(write_compact_index(v)), v


def test_encode_is_exact_inverse_of_decode_on_hand_stream():
    """A tiny synthetic stream exercising a native call, a NameConst, and a LabelTable terminator,
    round-tripped through trivial identity resolvers."""
    names = {0: "None", 1: "Tick", 2: "MyLabel"}
    name_inv = {v: k for k, v in names.items()}
    # 0x76 native( NameConst name=1 ) EndParms ; Stop ; LabelTable{ MyLabel,0 ; None,0xFFFF }
    stream = bytes([0x76, 0x21, 0x01, 0x16, 0x08,
                    0x0C, 0x02, 0, 0, 0, 0, 0x00, 0xFF, 0xFF, 0, 0])
    # ScriptSize (in-memory): 0x76(1)+NameConst(1+4)+EndParms(1)+Stop(1)+LabelTable(1)+2*(4+4) = 26
    ssz = 1 + 5 + 1 + 1 + 1 + 16

    def resolve(kind, index):
        assert kind == "name"
        return names[index]

    def resolve_inv(kind, ident):
        assert kind == "name"
        return name_inv[ident]

    toks, pos = decode_script(stream, 0, ssz, resolve)
    assert pos == len(stream)
    assert encode_script(toks, resolve_inv) == stream
    assert isinstance(toks[0], Tok)
