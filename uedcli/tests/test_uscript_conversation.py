"""`#exec CONVERSATION IMPORT` — the sibling-package emitter (`uscript.conimport`).

Two layers:
- Offline (needs the DX substrate for ConSys class schemas, but no docker): the committed Minimal
  golden — `build_conversation_packages` of `Minimal.Con` is byte-exact (via `perm_gate`) against the
  committed `ConvTestText.u` / `ConvTestAudioTestPack.u`.
- Docker-gated: a fresh DX-UCC build of the comprehensive `AllEvents.con` (every byte-exact event
  type) must match uedcli's emitter body-for-body.

`perm_gate` is byte-exact modulo the documented exclusions (package GUID, name/import/export table
ORDER, FName case) — table order differs because UCC refcount-sorts and we emit creation order.

Residual (NOT covered): `ConEventComment.commentText` — the DX handler writes corrupt bytes for it (a
deterministic buffer over-read: a bit-7 length prefix + trailing junk); uedcli emits the correct
FString instead, so it is deliberately absent from the comprehensive fixture. `ConEventTrade`/
`ConEventRandomLabel` are also excluded (the ConEdit writer emits no Trade payload; RandomLabel's
field mapping is unverified). `bDisplayAsSpeech` choice→speech synthesis is unimplemented.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_conversation_siblings, compile_package_dir
from uedcli.uscript.conimport import build_conversation_packages, parse_con
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import perm_gate
from uedcli.uscript.reference_dxorig import (UccError, dxorig_container, dxorig_substrate_dir,
                                             ucc_compile_dxorig)
from uedcli.uscript.serialize import serialize

_FIX = Path(__file__).resolve().parent / "fixtures" / "conversation"


def _substrate_dir() -> Path | None:
    try:
        return dxorig_substrate_dir()
    except UccError:
        return None


def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


_SUBSTRATE = _substrate_dir()
_needs_substrate = pytest.mark.skipif(
    _SUBSTRATE is None, reason="needs the DX substrate for ConSys schemas (fetch_dxorig.sh)")


# ── offline: the .con parser ──────────────────────────────────────────────────────────────────────
def test_parse_con_minimal():
    con = parse_con((_FIX / "Minimal.Con").read_bytes())
    assert con.audio_package == "TestPack"
    assert con.missions == (0,)
    assert len(con.conversations) == 1
    c = con.conversations[0]
    assert c.id == 0 and c.con_name == "TestConvo" and c.owner_name == "TestPawn"
    assert c.bools["display_once"] and c.bools["invoke_bump"] and c.bools["invoke_frob"]
    assert not c.bools["first_person"]
    assert [(f.name, f.value) for f in c.flag_refs] == [("TestFlag4", True)]
    assert c.events == ()


def test_parse_con_rejects_bad_header():
    with pytest.raises(ValueError, match="not a Deus Ex .con file"):
        parse_con(b"not a con file" + b"\x00" * 40)


def test_parse_con_rejects_truncated():
    """A valid header but a body that runs past EOF must raise ValueError (which the CLI turns into a
    clean exit 2), never a bare struct.error traceback."""
    truncated = (_FIX / "Minimal.Con").read_bytes()[:40]
    with pytest.raises(ValueError, match="truncated|bad string length"):
        parse_con(truncated)


# ── offline: the Minimal golden, byte-exact ────────────────────────────────────────────────────────
@_needs_substrate
def test_minimal_siblings_byte_exact():
    env = InstallEnv([str(_SUBSTRATE)])
    con = parse_con((_FIX / "Minimal.Con").read_bytes())
    sibs = build_conversation_packages(con, "ConvTest", env)
    assert sorted(sibs) == ["ConvTestAudioTestPack", "ConvTestText"]
    for name in sibs:
        golden = (_FIX / f"{name}.u").read_bytes()
        r = perm_gate(serialize(sibs[name]), golden)
        assert r.passed, f"{name}: {r.messages}"


@_needs_substrate
def test_naming_rule():
    """`<base>Text`, `<base>Audio<audioPackage>`, `ConAudioList_<audioPackage>`."""
    env = InstallEnv([str(_SUBSTRATE)])
    con = parse_con((_FIX / "Minimal.Con").read_bytes())
    sibs = build_conversation_packages(con, "MyPkg", env)
    assert set(sibs) == {"MyPkgText", "MyPkgAudioTestPack"}
    audio = sibs["MyPkgAudioTestPack"]
    assert any(n.text == "ConAudioList_TestPack" for n in audio.names)


@_needs_substrate
def test_main_package_ignores_directive():
    """A class carrying `#exec CONVERSATION IMPORT` still compiles its own package (the directive adds
    nothing to it) — the sibling objects go only to the sibling packages."""
    env = InstallEnv([str(_SUBSTRATE)])
    src = 'class ConvTest expands Object;\n\n#exec CONVERSATION IMPORT FILE="Minimal.Con"\n'
    pkg = compile_package_dir({"ConvTest.uc": src}, env, package_name="ConvTest")
    names = {n.text for n in pkg.names}
    assert "ConvTest" in names and "ScriptText" in names
    assert "Conversation" not in names          # no conversation objects leaked into the main package
    sibs = compile_conversation_siblings(
        {"ConvTest.uc": src}, env, package_name="ConvTest",
        con_files={"Minimal.Con": (_FIX / "Minimal.Con").read_bytes()})
    assert sorted(sibs) == ["ConvTestAudioTestPack", "ConvTestText"]


# ── docker-gated: every byte-exact event type, freshly built ───────────────────────────────────────
@pytest.mark.integration
@pytest.mark.skipif(not (_docker_up() and _SUBSTRATE is not None),
                    reason="needs a live docker daemon and the DX substrate")
def test_all_events_fresh_build(tmp_path):
    data = (_FIX / "AllEvents.con").read_bytes()
    src = 'class AllEv expands Object;\n\n#exec CONVERSATION IMPORT FILE="AllEvents.con"\n'
    with dxorig_container(state_dir=tmp_path) as c:
        ucc = ucc_compile_dxorig(c, "AllEv", {"AllEv.uc": src},
                                 con_files={"AllEvents.con": data})
    env = InstallEnv([str(_SUBSTRATE)])
    sibs = build_conversation_packages(parse_con(data), "AllEv", env)
    assert sorted(sibs) == ["AllEvAudioTestPack", "AllEvText"]
    for name in sibs:
        r = perm_gate(serialize(sibs[name]), ucc[f"{name}.u"])
        assert r.passed, f"{name}: {r.messages}"
