#!/usr/bin/env python3
"""Per-brush attribution for 00_TrainingFinal.dx's residual (current master, fresh build
2026-09-01): nodes native=11227 golden=11122 d=+105; surfs EXACT d=+0; leaves native=861
golden=848 d=+13.
"""
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-fresh")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache/"
             "f3e6539d9ed950dcf1dfb5929040e2da07b37f263727c360fdf2de63e2e73d27/trunk/maps/00_trainingfinal")
GOLDEN = Path("/tmp/uedcli-parity-cache/f3e6539d9ed950dcf1dfb5929040e2da07b37f263727c360fdf2de63e2e73d27/golden.dx")
os.environ["UEDCLI_PROJECT"] = str(TRUNK.parent.parent)

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return pkg, m


def main():
    level, _ranks = trunk.read_level(TRUNK)
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    print("total world-csg brushes:", len(names))

    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))

    epkg, em = parse_golden(GOLDEN)

    print(f"native surfs={len(nm.surfs)}  editor surfs={len(em.surfs)}")
    print(f"native nodes={len(nm.nodes)}  editor nodes={len(em.nodes)}")
    print(f"native leaves={len(nm.leaves)}  editor leaves={len(em.leaves)}")

    def node_owner_counts(model, surf_owner_fn):
        c = Counter()
        for node in model.nodes:
            if 0 <= node.i_surf < len(model.surfs):
                c[surf_owner_fn(model.surfs[node.i_surf].i_actor)] += 1
            else:
                c[None] += 1
        return c

    n_owner = node_owner_counts(nm, lambda ia: names[ia] if 0 <= ia < len(names) else ia)
    e_owner = node_owner_counts(em, lambda ia: epkg.name_of_ref(ia))

    all_owner_names = set(n_owner) | set(e_owner)
    node_diffs = [(nam, n_owner.get(nam, 0), e_owner.get(nam, 0)) for nam in all_owner_names
                  if n_owner.get(nam, 0) != e_owner.get(nam, 0)]
    node_diffs.sort(key=lambda t: -abs(t[1] - t[2]))
    total_abs = sum(abs(n - e) for _, n, e in node_diffs)
    net = sum(n - e for _, n, e in node_diffs)
    print(f"\n=== NODE-PLANE-OWNER: {len(node_diffs)}/{len(names)} brushes differ, "
          f"abs-sum={total_abs}, net={net:+d} (full node delta={len(nm.nodes)-len(em.nodes):+d}) ===")
    for nam, n, e in node_diffs[:30]:
        idx = names.index(nam) if nam in names else -1
        a = level.actors[nam] if nam in level.actors else None
        p = dict(a.props) if a else {}
        cls = p.get("CsgOper", "?")
        npolys = len(a.brush.polys) if a and a.brush else "?"
        print(f"  idx={idx:4} {str(nam):20s} native={n:4} editor={e:4} d={n-e:+d}  CsgOper={cls} npolys={npolys}")


if __name__ == "__main__":
    raise SystemExit(main())
