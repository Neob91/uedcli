#!/usr/bin/env python3
"""Breadth geometry-parity sweep: `uedcli_native.build_geometry_bspcsg` direct (bypassing
`level materialize`'s CLI — these trunks aren't class-qualified) against every world-only
editor golden `.dx` currently on disk under `_scratch/geo-confirm-*`, in one run.

Same comparison `regression_gate.py` does for UNATCO+Wanchai (that script stays the hard
regression gate for those two; this one is the wide survey). "Exact" = nodes/surfs/leaves all
match; verts/points/vectors are reported but not part of the exact gate (known separate
residual, `unatco-verts-points-residual-after-the-zone`).

Usage: .venv/bin/python breadth_gate.py
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

SCRATCH = ROOT / "_scratch"

# (label, project dir, subpath under maps/ (None = project root), golden .dx path)
CASES = [
    ("UNATCO", SCRATCH / "bsp-parity-proj", "maps/unatco",
     SCRATCH / "bsp-parity-proj/golden_unatco_control.dx"),
    ("Wanchai (tmp-wanchai-market)", ROOT / "dev/games/trunks/tmp-wanchai-market", None,
     SCRATCH / "golden_wanchai_world.dx"),
    ("Wanchai (geo-confirm chunked)", SCRATCH / "geo-confirm-wanchaimkt-wk", "maps/wanchaimkt",
     SCRATCH / "geo-confirm-wanchaimkt-wk/golden_wanchaimkt_chunked.dx"),
    ("smuggler", SCRATCH / "geo-confirm-smuggler", "maps/smuggler",
     SCRATCH / "geo-confirm-smuggler/golden_smuggler_resume.dx"),
    ("paris-chateau", SCRATCH / "geo-confirm-paris-chateau", "maps/paris-chateau",
     SCRATCH / "geo-confirm-paris-chateau/golden_paris-chateau.dx"),
    ("training-final", SCRATCH / "geo-confirm-training-final", "maps/training-final",
     SCRATCH / "geo-confirm-training-final/golden_training-final.dx"),
    ("hk-helibase", SCRATCH / "geo-confirm-hk-helibase", "maps/hk-helibase",
     SCRATCH / "geo-confirm-hk-helibase/golden_hk-helibase.dx"),
    ("area51-entrance (known under-build)", SCRATCH / "geo-confirm-area51-entrance", "maps/area51-entrance",
     SCRATCH / "geo-confirm-area51-entrance/golden_area51.dx"),
    ("dx (intro)", SCRATCH / "geo-confirm-dx", "maps/dx",
     SCRATCH / "geo-confirm-dx/golden_dx.dx"),
    ("nyc-street", SCRATCH / "geo-confirm-nyc-street", "maps/nyc-street",
     SCRATCH / "geo-confirm-nyc-street/golden_nyc-street_resume.dx"),
    ("freeclinic08", SCRATCH / "geo-confirm-freeclinic08-wk", "maps/freeclinic08",
     SCRATCH / "geo-confirm-freeclinic08-wk/golden_freeclinic08.dx"),
    ("freeclinic08 (generous golden)", SCRATCH / "geo-confirm-freeclinic08-wk", "maps/freeclinic08",
     SCRATCH / "geo-confirm-freeclinic08-wk/golden_freeclinic08_generous.dx"),
    ("nsfhq04", SCRATCH / "geo-confirm-nsfhq04-wk", "maps/nsfhq04",
     SCRATCH / "geo-confirm-nsfhq04-wk/golden_nsfhq04.dx"),
]


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    return UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])


def main():
    rows = []
    for name, project, subpath, golden_path in CASES:
        if not Path(golden_path).exists():
            print(f"{name}: SKIP (no golden at {golden_path})")
            continue
        os.environ["UEDCLI_PROJECT"] = str(project)
        proj = Path(project)
        if subpath:
            trunk_path = proj / subpath
        elif (proj / "actors").exists():
            trunk_path = proj
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
        rows.append((name, len(gm.nodes), len(nm.nodes), d_nodes, d_surfs, d_leaves,
                     d_verts, d_points, d_vectors, exact))
        print(f"{name}: brushes={len(names)} nodes {len(nm.nodes)} (golden {len(gm.nodes)}, "
              f"d={d_nodes:+d})  surfs d={d_surfs:+d}  leaves d={d_leaves:+d}  verts d={d_verts:+d}  "
              f"points d={d_points:+d}  vectors d={d_vectors:+d}  {'EXACT' if exact else 'NOT EXACT'}")
    n_exact = sum(1 for r in rows if r[-1])
    print(f"\n{n_exact}/{len(rows)} exact (nodes/surfs/leaves)")


if __name__ == "__main__":
    main()
