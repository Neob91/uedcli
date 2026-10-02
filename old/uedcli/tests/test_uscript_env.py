"""Dependency environment: class resolution + self-CRC against the stock install."""
from __future__ import annotations

from pathlib import Path

from uedcli.uscript.env import InstallEnv

_UED22 = str(Path(__file__).resolve().parents[2] / "uned" / "UED22")


def _env() -> InstallEnv:
    return InstallEnv([_UED22])


def test_resolve_object():
    info = _env().resolve_class("Object")
    assert info is not None
    assert info.package.casefold() == "core"
    assert info.self_crc == 0xD735B29C   # matches UscHello's imported Object dependency CRC


def test_resolve_is_case_insensitive():
    assert _env().resolve_class("object") is not None


def test_unknown_class_returns_none():
    assert _env().resolve_class("NoSuchClassXyz") is None
