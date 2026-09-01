#!/usr/bin/env python3
"""Build a structural-only (non-PF_Semisolid) copy of the nsfhq04 trunk under
_scratch/nsfhq04-structural-only/maps/nsfhq04, mirroring fc08's/smuggler's methodology
(freeclinic08-nsfhq04-1-surf-under-build-root) so PASS-A alone can be measured against a fresh
editor golden.
"""
import sys
import shutil
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))

from uedcli import trunk  # noqa: E402

SRC_PROJECT = ROOT / "_scratch/geo-confirm-nsfhq04-wk"
SRC_TRUNK = SRC_PROJECT / "maps/nsfhq04"
DST_PROJECT = ROOT / "_scratch/nsfhq04-structural-only"
DST_TRUNK = DST_PROJECT / "maps/nsfhq04"

PF_SEMISOLID = 32


def main():
    level, ranks = trunk.read_level(SRC_TRUNK)

    detail_names = set()
    for n in level.order:
        a = level.actors[n]
        if a.brush is None:
            continue
        pf = int(dict(a.props).get("PolyFlags", "0") or "0")
        if pf & PF_SEMISOLID:
            detail_names.add(n)

    print(f"total actors: {len(level.actors)}; detail (PF_Semisolid) brushes to drop: {len(detail_names)}")

    if DST_TRUNK.exists():
        shutil.rmtree(DST_TRUNK)
    DST_TRUNK.parent.mkdir(parents=True, exist_ok=True)

    new_order = [n for n in level.order if n not in detail_names]
    new_actors = {k: v for k, v in level.actors.items() if k not in detail_names}
    new_ranks = {k: v for k, v in ranks.items() if k not in detail_names}

    new_level = type(level)(actors=new_actors, order=new_order)
    trunk.write_level(DST_TRUNK, new_level, new_ranks)

    toml = DST_PROJECT / "uedcli.toml"
    toml.write_text('game = "deusex"\nmaps = "maps"\n')

    print(f"wrote structural-only trunk to {DST_TRUNK}: {len(new_level.order)} actors kept")


if __name__ == "__main__":
    raise SystemExit(main())
