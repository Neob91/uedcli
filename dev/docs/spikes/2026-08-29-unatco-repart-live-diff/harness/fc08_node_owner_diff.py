#!/usr/bin/env python3
"""Per-brush NODE-plane-owner attribution for freeclinic08 (native under-builds nodes by -20).

Each interior BSP node's splitting plane came from some surf (node.i_surf), which is owned by
some brush (surf.i_actor). This is not a literal 1:1 "this brush caused N nodes" map (repartition
reshapes the whole tree), but a concentration signal: if the -20 node deficit traces to a handful
of brushes it's a local bug; if it's smeared across many brushes proportional to brush count it
looks like the same systemic "differing soup" class as UNATCO/Area51.

Usage: .venv/bin/python fc08_node_owner_diff.py
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
os.environ.setdefault("UEDCLI_PROJECT", "/workspace/uedcli/_scratch/geo-confirm-freeclinic08-wk")

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-freeclinic08-wk/maps/freeclinic08"
GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-freeclinic08-wk/golden_freeclinic08_generous.dx"


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return pkg, m


def node_owner_counts(model, actor_of):
    c = Counter()
    for n in model.nodes:
        if 0 <= n.i_surf < len(model.surfs):
            s = model.surfs[n.i_surf]
            c[actor_of(s.i_actor)] += 1
    return c


def leaf_owner_counts_via_parent(model, actor_of):
    # FBspLeaf count per zone isn't brush-attributable directly; skip.
    return None


def main():
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]

    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))
    epkg, em = parse_golden(GOLDEN)

    nc = node_owner_counts(nm, lambda ia: names[ia] if 0 <= ia < len(names) else ia)
    ec = node_owner_counts(em, lambda ia: epkg.name_of_ref(ia))

    all_names = set(nc) | set(ec)
    diffs = [(nam, nc.get(nam, 0), ec.get(nam, 0)) for nam in all_names]
    diffs = [(nam, n, e, n - e) for nam, n, e in diffs if n != e]
    diffs.sort(key=lambda t: abs(t[3]), reverse=True)
    print(f"total nodes: native={len(nm.nodes)} editor={len(em.nodes)} d={len(nm.nodes)-len(em.nodes):+d}")
    print(f"{len(diffs)} brushes have differing node-plane-owner counts (of {len(names)} total brushes)")
    print("sum of |d| across differing brushes:", sum(abs(t[3]) for t in diffs))
    print("\nTop 30 by |delta|:")
    for nam, n, e, d in diffs[:30]:
        idx = names.index(nam) if nam in names else -1
        print(f"  idx={idx:4} {nam:20s} native={n:4} editor={e:4} d={d:+d}")


if __name__ == "__main__":
    raise SystemExit(main())
