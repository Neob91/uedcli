#!/usr/bin/env python3
"""Counts-only A/B over the four verts/points-residual levels, one env config per run.

Usage: .venv/bin/python vp_counts_ab.py [LEVEL.dx ...]
Env flags to A/B are set by the caller. Prints d(nodes/surfs/leaves/verts/points/vectors)
per level. Each level builds in a fresh subprocess so Rust env-var reads are per-run clean.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_LEVELS = ["03_NYC_UNATCOHQ.dx", "09_NYC_ShipFan.dx", "04_NYC_Underground.dx",
                  "08_NYC_FreeClinic.dx"]
MAPS = Path("/workspace/uedcli/dev/games/deusex/Maps")

CHILD = r"""
import sys
from pathlib import Path
sys.path.insert(0, "{harness}")
sys.path.insert(0, "{pr_harness}")
import parity_lib as pl, parity_compare as pc, sweep_lib as sl
dx = Path(sys.argv[1])
h = pl.content_hash(dx)
layout = pl.cache_layout(pl.CACHE_ROOT_DEFAULT, h)
trunk = next((sl.shared_trunk_cache_root(Path("{harness}")) / h / "trunk" / "maps").iterdir())
native, _ = pc.build_native_model(trunk)
golden = pc.parse_dx_model(layout.golden)
n, g = pc.geometry_counts(native), pc.geometry_counts(golden)
print(f"{{dx.name:26s}} d_nodes={{n.nodes-g.nodes:+d}} d_surfs={{n.surfs-g.surfs:+d}} "
      f"d_leaves={{n.leaves-g.leaves:+d}} d_verts={{n.verts-g.verts:+d}} "
      f"d_points={{n.points-g.points:+d}} d_vectors={{n.vectors-g.vectors:+d}}")
"""


def main() -> None:
    levels = sys.argv[1:] or DEFAULT_LEVELS
    pr = HERE.parents[1] / "2026-08-31-native-parity-report/harness"
    code = CHILD.format(harness=HERE, pr_harness=pr)
    py = HERE.parents[4] / ".venv/bin/python"
    for lv in levels:
        subprocess.run([str(py), "-c", code, str(MAPS / lv)], check=True)


if __name__ == "__main__":
    main()
