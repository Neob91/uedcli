#!/usr/bin/env python3
"""First 20 CSG brushes: oper, golden surf count, native surf count."""
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
    nm = UM.parse_model_body(body, 0, len(body))
    ncount = Counter(s.i_actor for s in nm.surfs)

    print(f"{'#':>3} {'brush':14s} {'oper':10s} {'polys':>5} {'golden':>6} {'native':>6}")
    for i in range(0, 20):
        n = names[i]
        act = level.actors[n]
        oper = dict(act.props).get("CsgOper")
        npolys = len(act.brush.polys)
        print(f"{i:3d} {n:14s} {str(oper):10s} {npolys:5d} {gcount.get(n,0):6d} {ncount[i]:6d}")


if __name__ == "__main__":
    main()