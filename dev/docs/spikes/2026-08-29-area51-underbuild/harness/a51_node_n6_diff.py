#!/usr/bin/env python3
"""Offline N=5/N=6 per-brush surf diff, reusing the already-captured editor prefix goldens
(`_scratch/a51-editor-trace/a51_prefix_0{5,6}.dx`, from `a51_editor_prefix.py`) — no live editor
needed. Confirms the exact divergence point and gives per-brush attribution at N=6.

Usage: .venv/bin/python a51_node_n6_diff.py
"""
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
os.environ.setdefault("UEDCLI_PROJECT", "/workspace/uedcli/_scratch/geo-confirm-area51-entrance")

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"
PREFIX_DIR = Path("/workspace/uedcli/_scratch/a51-editor-trace")


def parse_model(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return pkg, m


def main():
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    print("first 7 brushes:", names[:7])

    for N in (5, 6):
        epkg, em = parse_model(PREFIX_DIR / f"a51_prefix_{N:02d}.dx")
        built = uedcli_native.build_geometry_bspcsg(ins[:N])
        nbody = uedcli_native.serialize_model(built)
        nm = UM.parse_model_body(nbody, 0, len(nbody))
        print(f"N={N}: editor nodes={len(em.nodes)} surfs={len(em.surfs)}   "
              f"native nodes={len(nm.nodes)} surfs={len(nm.surfs)}")

    N = 6
    epkg, em = parse_model(PREFIX_DIR / f"a51_prefix_{N:02d}.dx")
    ec = Counter(epkg.name_of_ref(s.i_actor) for s in em.surfs)
    built = uedcli_native.build_geometry_bspcsg(ins[:N])
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))
    nc = Counter(names[s.i_actor] if 0 <= s.i_actor < len(names[:N]) else s.i_actor
                 for s in nm.surfs)

    print("\nPer-brush surf counts at N=6:")
    for i, nam in enumerate(names[:N]):
        print(f"  idx{i} {nam:12s} editor={ec.get(nam, 0):3}  native={nc.get(nam, 0):3}")


if __name__ == "__main__":
    raise SystemExit(main())
