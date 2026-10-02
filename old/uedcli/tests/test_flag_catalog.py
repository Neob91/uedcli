"""Directional regression: every poly-flag the kb catalog documents must be settable.

Parses the flag-bit table in `dev/docs/unrealed/leveldesign/kb/textures.md` and asserts each of its
`PF_*` bits is present in `query.PF_NAMES` — a documented flag is always reachable via
`brush poly set --add-flag`. Subset, NOT equality: `PF_NAMES` legitimately carries bits the kb table
omits (`invisible` 0x1, `notsolid` 0x8, `semisolid` 0x20). Parse ONLY this file — the stale
`dev/docs/spikes/bspspike/flags.py` table has different (wrong) bit values.
"""
import re
from pathlib import Path

from uedcli.query import PF_NAMES

_KB = (Path(__file__).resolve().parents[2]
       / "dev/docs/unrealed/leveldesign/kb/textures.md")

# A table row pairs a hex value with its PF_* name, e.g. `| **Unlit** | `0x400000` (`PF_Unlit`) | … |`.
_ROW = re.compile(r"`(0x[0-9a-fA-F]+)`\s*\(`PF_\w+`\)")


def _kb_flag_bits() -> set[int]:
    return {int(m, 16) for m in _ROW.findall(_KB.read_text(encoding="utf-8"))}


def test_kb_documents_flag_bits():
    # Guard the parser itself: if the table format drifts and matches nothing, the subset check below
    # would pass vacuously.
    assert len(_kb_flag_bits()) >= 16


def test_every_documented_flag_is_settable():
    settable = {bit for bit, _ in PF_NAMES}
    assert _kb_flag_bits() <= settable, (
        "kb documents PF_* bits with no settable name: "
        f"{sorted(hex(b) for b in _kb_flag_bits() - settable)}")
