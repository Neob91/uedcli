"""UED22 `appStrCrc` — the CRC stored in `UClass.Dependencies[].ScriptTextCRC`.

RE'd from `core.dll` (`appStrCrc` @ VA 0x1005c610, `GCRCTable` build @ 0x1005a38f): a non-reflected
CRC-32/BZIP2 (poly 0x04C11DB7, MSB-first, init 0xFFFFFFFF, final XOR 0xFFFFFFFF) over the string's
UTF-16LE bytes (this is a UNICODE build — two bytes per char, low then high), NOT uppercased, no
trailing NUL. Input is the class's STORED `ScriptText` (CRLF line endings, as UCC saves it). See
`dev/docs/unrealed/unrealscript/compile-model.md`.
"""
from __future__ import annotations

_POLY = 0x04C11DB7
_GCRC: list[int] = []
for _i in range(256):
    _c = (_i << 24) & 0xFFFFFFFF
    for _ in range(8):
        _c = ((_c << 1) ^ _POLY) & 0xFFFFFFFF if (_c & 0x80000000) else (_c << 1) & 0xFFFFFFFF
    _GCRC.append(_c)


def script_text_crc(text: str) -> int:
    """`appStrCrc(*text)` where `text` is the stored CRLF `ScriptText` (no trailing NUL)."""
    crc = 0xFFFFFFFF
    for ch in text:
        c = ord(ch)
        for b in (c & 0xFF, (c >> 8) & 0xFF):
            crc = ((crc << 8) ^ _GCRC[((crc >> 24) ^ b) & 0xFF]) & 0xFFFFFFFF
    return crc ^ 0xFFFFFFFF
