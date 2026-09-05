"""`uedcli uscript compile` — the CLI wrapper over the native UnrealScript compiler.

Offline and editor-free: it wraps `uscript.compile.compile_package_dir`. Three properties are
load-bearing and pinned here: it writes a real `.u` (Unreal package magic) at exit 0, an
unsupported construct exits 2 with a clear message (never a traceback), and a bad source dir exits 2
naming it. The compile tests need the committed UED22 substrate (core.u / Engine.u) and skip
without it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from uedcli.cli import main as cli
from uedcli.cli.parsers.uscript import register

import argparse

_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
_HAVE_UED22 = (_UED22 / "core.u").is_file() and (_UED22 / "Engine.u").is_file()
_MAGIC = b"\xc1\x83\x2a\x9e"                         # 0x9E2A83C1 little-endian — Unreal package tag

_needs_ued22 = pytest.mark.skipif(not _HAVE_UED22,
                                  reason="needs the committed UED22 substrate (core.u/Engine.u)")


def _run(argv, capsys):
    rc = cli.main(argv)
    return rc, capsys.readouterr()


# ---- parse-args ----
def test_parser_accepts_compile_flags():
    p = argparse.ArgumentParser()
    register(p.add_subparsers(dest="cmd", required=True))
    args = p.parse_args(["uscript", "compile", "src", "-o", "Out.u",
                         "--package", "Pkg", "--deps", "d1", "--deps", "d2", "--json"])
    assert args.sub == "compile"
    assert args.src == "src" and args.out == "Out.u" and args.package == "Pkg"
    assert args.deps == ["d1", "d2"] and args.json is True


# ---- compile (needs the substrate) ----
@_needs_ued22
def test_compile_writes_a_real_u_package(tmp_path, capsys):
    src = tmp_path / "Classes"
    src.mkdir()
    (src / "Base.uc").write_text("class Base expands Object;\n\nvar int N;\n\n"
                                 "function int Get() { return N; }\n", encoding="utf-8")
    out = tmp_path / "Base.u"
    rc, cap = _run(["uscript", "compile", str(src), "-o", str(out)], capsys)
    assert rc == 0, cap.err
    assert out.read_bytes()[:4] == _MAGIC
    assert cap.out.strip() == str(out)               # the path is the only stdout line
    assert "class(es)" in cap.err                     # the human summary goes to stderr


@_needs_ued22
def test_compile_json(tmp_path, capsys):
    src = tmp_path / "Foo"
    src.mkdir()
    (src / "Foo.uc").write_text("class Foo expands Object;\n\nvar int X;\n", encoding="utf-8")
    out = tmp_path / "Foo.u"
    rc, cap = _run(["uscript", "compile", str(src), "-o", str(out), "--json"], capsys)
    assert rc == 0, cap.err
    import json
    obj = json.loads(cap.out)
    assert obj == {"package": "Foo", "classes": 1, "bytes": out.stat().st_size,
                   "path": str(out), "siblings": []}


@_needs_ued22
def test_unsupported_construct_exits_2_without_traceback(tmp_path, capsys):
    src = tmp_path / "Classes"
    src.mkdir()
    # A state block is a not-yet-supported construct — it must name itself, not traceback.
    (src / "Foo.uc").write_text("class Foo expands Object;\n\nstate S {\n}\n", encoding="utf-8")
    rc, cap = _run(["uscript", "compile", str(src), "-o", str(tmp_path / "Foo.u")], capsys)
    assert rc == 2
    assert "compile failed" in cap.err and "states" in cap.err
    assert "Traceback" not in cap.err


# ---- input errors (no substrate needed) ----
def test_missing_source_dir_exits_2(tmp_path, capsys):
    rc, cap = _run(["uscript", "compile", str(tmp_path / "nope")], capsys)
    assert rc == 2 and "not a directory" in cap.err


def test_empty_source_dir_exits_2(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    rc, cap = _run(["uscript", "compile", str(tmp_path / "empty")], capsys)
    assert rc == 2 and "no *.uc" in cap.err
    assert "Traceback" not in cap.err
