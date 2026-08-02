"""Sniff a `.umx` music package's embedded tracker-module TITLE, by magic.

A `.umx` is a UE1 container wrapping one `Music` object whose body is a raw tracker module
(Impulse Tracker / ScreamTracker 3 / FastTracker 2 / ProTracker). Each format carries a song
title at a fixed offset from its magic; this reader dispatches on the magic and returns
`(title, format)`. An unrecognised container returns `(None, "unknown")` — never a blank title
that reads as "this module has no title" (a wrong or silently-absent title is a half-answer,
`board/sound-corpus-remeasure/spec.md` §7).

Offsets (module magic scanned anywhere in the buffer, since the module is embedded inside the
package body):

| format | magic               | title field           |
|--------|---------------------|-----------------------|
| IT     | `IMPM`              | 26 bytes at magic +4  |
| S3M    | `SCRM` (at +0x2C)   | 28 bytes at magic −0x2C |
| XM     | `Extended Module: ` | 20 bytes at magic +17 |

Only IT is live-verified here (all 35 Deus Ex `.umx` are IT — `measure.py`); the S3M/XM offsets
are pinned by hand-built fixtures. Promoted from the spike reader `measure.py:_umx_title`.
"""
from __future__ import annotations


def _read_name(buf: bytes, start: int, length: int) -> str | None:
    """A latin-1 title field: `length` bytes at `start`, NUL-terminated, stripped. Empty → None
    (an all-NUL / blank field is an absent title, not the empty string)."""
    name = buf[start:start + length].split(b"\x00")[0].decode("latin-1", "replace").strip()
    return name or None


def sniff_title(buf: bytes) -> tuple[str | None, str]:
    """The embedded module `(title, format)` for a `.umx` package's raw bytes. Dispatches on the
    module magic (IT → S3M → XM); an unrecognised container is `(None, "unknown")`. `format` is
    always one of `IT`/`S3M`/`XM`/`unknown` so the caller can report what was found even when the
    title field is blank."""
    it = buf.find(b"IMPM")
    if it != -1:
        return _read_name(buf, it + 4, 26), "IT"
    s3m = buf.find(b"SCRM")
    if s3m >= 0x2C:                       # -1 (absent) and a magic too early to hold the name both fail
        return _read_name(buf, s3m - 0x2C, 28), "S3M"
    xm = buf.find(b"Extended Module: ")
    if xm != -1:
        return _read_name(buf, xm + 17, 20), "XM"
    return None, "unknown"
