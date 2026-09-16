"""`GET /api/levels` payload (quad-layout Part 7, Task 24): every level under the project's maps
dir, flagging which one this app currently serves. Reuses `level_sources.list_levels` (the same
enumeration `level list`/`level list --json` already use) rather than a second one."""
from __future__ import annotations

from pathlib import Path

from ..cli import level_sources


def levels_payload(maps_root: Path, current: str) -> dict:
    """`{"levels": [{"name": n, "active": n == current}, ...], "current": current}` -- mirrors
    `level list --json`'s existing per-entry `{name, active}` shape."""
    names = level_sources.list_levels(maps_root)
    return {
        "levels": [{"name": n, "active": n == current} for n in names],
        "current": current,
    }
