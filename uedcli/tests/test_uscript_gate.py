"""The `.u` parity gate: byte verdict (GUID masked) + structured divergence diagnostics."""
from __future__ import annotations

from pathlib import Path

from uedcli.uscript.gate import _parse_header, gate

_CORE_U = Path(__file__).resolve().parents[2] / "uned" / "UED22" / "core.u"


def _core() -> bytes:
    return _CORE_U.read_bytes()


def test_self_compare_passes():
    b = _core()
    r = gate(b, b)
    assert r.passed, r.messages


def test_header_shape():
    h = _parse_header(_core())
    assert h.version == 69 and h.guid_range == (36, 52)


def test_guid_flip_is_masked():
    b = _core()
    h = _parse_header(b)
    g = bytearray(b)
    g[h.guid_range[0]] ^= 0xFF
    assert gate(bytes(g), b).passed


def test_body_flip_fails_and_locates():
    b = _core()
    bad = bytearray(b)
    bad[len(b) - 20] ^= 0xFF
    r = gate(bytes(bad), b)
    assert not r.passed
    assert any("offset" in m for m in r.messages)


def test_size_diff_reported():
    b = _core()
    r = gate(b + b"\x00", b)
    assert not r.passed
    assert any("SIZE differs" in m for m in r.messages)
