#!/usr/bin/env python3
"""Native per-prefix per-brush world surf counts for the first N Area51 CSG brushes.

Mirror of the editor probe (a51_editor_prefix.py): for each prefix N, build_geometry_bspcsg on the
first N world-CSG brushes, then count the world surfs attributed to each brush.  This is native's
"per-brush cumulative" curve to diff against the live-editor one.
"""
from __future__ import annotations
import os, sys
from collections import Counter
from pathlib import Path

os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance"
ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))

from uedcli import trunk, utexture
from uedcli.native import brush_marshal as BM
from uedcli.native import umodel as UM
import uedcli_native
from spike_classindex import class_index

GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"
TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"
PREFIXES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 18, 24, 36, 48]


def main():
    pkg = utexture.load_package(GOLDEN)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    g = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    gcount = Counter()
    for s in g.surfs:
        nm = pkg.name_of_ref(s.i_actor)
        if nm is not None:
            gcount[nm] += 1

    level, _ = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]

    print("=== golden final per-brush (full 1343 tree) ===")
    for i, n in enumerate(names[:48]):
        print(f"  idx{i} {n:12s} golden={gcount.get(n,0)}")
    print("=== end golden ===\n")

    for N in PREFIXES:
        idx = list(range(N))
        built = uedcli_native.build_geometry_bspcsg([ins[i] for i in idx])
        body = uedcli_native.serialize_model(built)
        m = UM.parse_model_body(body, 0, len(body))
        c = Counter(s.i_actor for s in m.surfs)
        print(f"### prefix N={N} nodes={len(m.nodes)} surfs={len(m.surfs)}")
        for i, n in enumerate(names[:N]):
            print(f"  idx{i} {n:12s} native_prefix={c.get(i,0)} golden_final={gcount.get(n,0)}")


if __name__ == "__main__":
    main()
