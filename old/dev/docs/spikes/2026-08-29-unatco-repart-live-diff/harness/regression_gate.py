#!/usr/bin/env python3
"""Hard regression gate for the repartition_frontier coplanar-merge fix: full geometry compare
against UNATCO and Wanchai's world-only goldens. Both must stay/become node-exact.

Usage: .venv/bin/python regression_gate.py
"""
import os
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402

CASES = [
    ("UNATCO", "/workspace/uedcli/_scratch/bsp-parity-proj", "maps/unatco",
     "/workspace/uedcli/_scratch/bsp-parity-proj/golden_unatco_control.dx"),
    ("Wanchai", "/workspace/uedcli/dev/games/trunks/tmp-wanchai-market", None,
     "/workspace/uedcli/_scratch/golden_wanchai_world.dx"),
]


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    return UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])


def main():
    ok = True
    for name, project, subpath, golden_path in CASES:
        os.environ["UEDCLI_PROJECT"] = project
        proj = Path(project)
        if subpath:
            trunk_path = proj / subpath
        elif (proj / "actors").exists():
            trunk_path = proj  # trunk IS the project root (no maps/ nesting)
        else:
            trunk_path = next((proj / "maps").iterdir())
        level, _ = trunk.read_level(trunk_path)
        ci = class_index()
        names = [n for n in level.order
                 if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
        ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
        built = uedcli_native.build_geometry_bspcsg(ins)
        nbody = uedcli_native.serialize_model(built)
        nm = UM.parse_model_body(nbody, 0, len(nbody))
        gm = parse_golden(golden_path)
        d_nodes = len(nm.nodes) - len(gm.nodes)
        d_surfs = len(nm.surfs) - len(gm.surfs)
        d_leaves = len(nm.leaves) - len(gm.leaves)
        d_verts = len(nm.verts) - len(gm.verts)
        d_points = len(nm.points) - len(gm.points)
        d_vectors = len(nm.vectors) - len(gm.vectors)
        exact = d_nodes == 0 and d_surfs == 0 and d_leaves == 0
        print(f"{name}: nodes {len(nm.nodes)} (golden {len(gm.nodes)}, d={d_nodes:+d})  "
              f"surfs d={d_surfs:+d}  leaves d={d_leaves:+d}  verts d={d_verts:+d}  "
              f"points d={d_points:+d}  vectors d={d_vectors:+d}  {'EXACT' if exact else 'NOT EXACT'}")
        ok = ok and exact
    print("GATE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
