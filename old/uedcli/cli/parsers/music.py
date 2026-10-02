"""`music` command-family parser. The catalog family is the shared `sound.build_family` keyed to
`kind="music"`; `music` permanently lacks `preview`/`prewarm`/`--similar` (a module has no picture),
so it ships exactly `list`/`show`/`search`/`classify`. `music show`/`list --json` additionally carry
each module's embedded title + format (`umxtitle`). The absence of `music preview` is asserted by the
tests, as the class arm asserts its own absences."""
from __future__ import annotations

from .sound import build_family


def register(sub) -> None:
    build_family(sub, "music")
