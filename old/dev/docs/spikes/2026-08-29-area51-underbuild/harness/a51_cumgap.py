#!/usr/bin/env python3
"""Cumulative surf-count gap (golden - native) vs brush index.

For each brush in order, delta = golden_count - native_count (final counts); print the running
total and the first indexes where it moves.  Locates the earliest cascade divergence."""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance"
ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli import trunk
from uedcli.native import brush_marshal as BM
from uedcli.native import umodel as UM
import uedcli_native
from uedcli.utexture import load_package
from spike_classindex import class_index

GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"
TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"


def main():
    pkg = load_package(GOLDEN)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    g = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    gcount = Counter()
    for s in g.surfs:
        nm = pkg.name_of_ref(s.i_actor)
        if nm is not None:
            gcount[nm] += 1

    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    body = uedcli_native.serialize_model(built)
    nmodel = UM.parse_model_body(body, 0, len(body))
    ncount = Counter(s.i_actor for s in nmodel.surfs)

    run = 0
    nzd = 0
    last_report = 0
    print("idx  brush          g    n   d  run  (first movements)")
    for i, n in enumerate(names):
        gc = gcount.get(n, 0)
        nc = ncount[i]
        d = gc - nc
        if d:
            nzd += 1
        run += d
        if d != 0 and (abs(run - last_report) != 0 or nzd < 8):
            print(f"{i:4d} {n:14s} {gc:3d} {nc:3d} {d:+3d} {run:+5d}")
            last_report = run
    print(f"\ntotal surf gap: golden={len(g.surfs)} native={len(nmodel.surfs)} diff={len(g.surfs)-len(nmodel.surfs)}")
    print(f"brushes with nonzero delta: {nzd}")


if __name__ == "__main__":
    main()