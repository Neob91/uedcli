#!/usr/bin/env python3
"""Count the BSP nodes in a built `.dx`/`.unr` map file, offline.

This is the SPIKE'S MEASURING INSTRUMENT. `dev/docs/unrealed/quirks.md` "How brushes enter the
level" records that a brush which entered the level via `MAP IMPORTADD` never gets its `Bound`
computed, so CSG skips it and `MAP REBUILD` produces a world Model with **zero nodes** — a map
that still saves, still parses and still draws its wireframe in the editor, but whose world is
solid, so the real game cannot spawn the player in it. Node count is therefore the unambiguous
offline tell for "did this brush actually participate in CSG".

    bspnodes.py <map.dx> [...]        -> one `<nodes> <surfs> <path>` line per file

Exit 0 always; the caller reads the numbers.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(_REPO))

from uedcli.native.pkg_write import parse_package                      # noqa: E402
from uedcli.native.umodel import parse_model_body                      # noqa: E402


def count(path: str) -> tuple[int, int]:
    """(nodes, surfs) of the LARGEST `Model` export — the level's world model.

    A package holds one `Model` per brush (each brush's authored polylist) plus the built world
    model; the world model is the largest, which is how `test_native_materialize` locates it too.
    A map with no world geometry at all still has its brush models, so 'largest' stays well defined
    — and that is exactly the case this spike has to measure, so the rule must not assume nodes.

    Uses uedcli's own in-tree `native.umodel` parser (no spike-harness dependency); cross-checked
    against the independent `spikes/bspspike/umodel_parser` on these same files — identical counts.
    """
    raw = Path(path).read_bytes()
    p = parse_package(raw)
    models = [(i, e) for i, e in enumerate(p.exports) if p.class_of_export(i) == "Model"]
    if not models:
        return (-1, -1)
    _, e = max(models, key=lambda t: t[1]["ssize"])
    m = parse_model_body(raw, e["soff"], e["ssize"])
    return (len(m.nodes), len(m.surfs))


def main() -> int:
    for arg in sys.argv[1:]:
        try:
            n, s = count(arg)
            print(f"{n}\t{s}\t{arg}", flush=True)
        except Exception as exc:                      # a probe tool: never a bare traceback
            print(f"ERR\tERR\t{arg}\t{type(exc).__name__}: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
