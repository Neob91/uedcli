"""Minimal UUIDv7 (RFC 9562): 48-bit ms timestamp + version 7 + random.
Lexicographic string order tracks creation time, so filenames sort chronologically.
"""
from __future__ import annotations

import os
import time


def uuid7(ms: int | None = None) -> str:
    if ms is None:
        ms = time.time_ns() // 1_000_000
    rand = os.urandom(10)
    b = bytearray(16)
    b[0:6] = ms.to_bytes(6, "big")
    # version 7 in the high nibble of byte 6
    b[6] = 0x70 | (rand[0] & 0x0F)
    b[7] = rand[1]
    # variant 0b10 in the high bits of byte 8
    b[8] = 0x80 | (rand[2] & 0x3F)
    b[9:16] = rand[3:10]
    h = b.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
