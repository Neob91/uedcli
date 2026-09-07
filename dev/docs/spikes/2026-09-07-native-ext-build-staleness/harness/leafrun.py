#!/usr/bin/env python3
"""Print every leaf's permeating-light run (`Model.Lights` region 1) from one or more built packages.

    .venv/bin/python leafrun.py <a.dx> [<b.dx> ...]

Region-1 runs are `0`-terminated in the package (the light index is an ObjRef, so 0 = None), and the
values are Actors-array object indices, not the 0-based light order `permeating_lights.rs` traces.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"))
sys.path.insert(1, str(ROOT))

import model_dump as md  # noqa: E402
import parity_gate as pg  # noqa: E402

for path in sys.argv[1:]:
    p = pg.load_package(path)
    d = md.decode(p, md.find(p, "Model2"))
    leaves, lights = d["leaves"], d["lights"]
    print(f"== {path}  leaves={len(leaves)} lights={len(lights)}")
    for i, leaf in enumerate(leaves):
        zone, i_perm, _i_vol = leaf[0]
        if i_perm < 0:
            continue
        run = []
        j = i_perm
        while j < len(lights) and lights[j] != 0:
            run.append(lights[j])
            j += 1
        print(f"  leaf {i:3} zone={zone} iPerm={i_perm:4} run={run}")
