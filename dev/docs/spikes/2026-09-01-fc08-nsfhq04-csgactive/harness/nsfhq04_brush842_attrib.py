#!/usr/bin/env python3
"""Per-brush node/surf-owner attribution at the n=513 prefix (structural-only, post-`CsgOper::
Active`) -- same method as `area51_attrib.py`/`fc08_node_owner_diff.py`, applied to NSFHQ04's
`Brush842`, the brush localized by `nsfhq04_prefix_search2.py`'s binary search
(n=512 exact, n=513 diverges `d_nodes=+131 d_surfs=+0 d_leaves=+38`).

Unlike the raw `filter_ed_poly` LEAF-add count during Brush842's own incremental CSG-add (which is
PRE the one-time world-level `bspBuildFPolys`->`bspMergeCoplanars`->`bspBuild` repartition that
`build_geometry_bspcsg` always runs -- see `UEDCLI_BSPCSG_STAGE_COUNTS`'s `post-repartition` stage,
confirmed present on every call including subset builds), this attributes the FINAL, POST-
repartition node/surf ownership (`node.i_surf -> surf.i_actor`) per brush -- the same basis
`area51_attrib.py` used to localize Area51's residual to `Brush1852` specifically (its "26 vs 17
terminal fragments" figure). Requires the editor golden `golden_n0513.dx` already built by
`nsfhq04_prefix_search2.py 513` (or `--search`) under `_scratch/nsfhq04-prefix2/n0513/`.
"""
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]  # harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> ROOT
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNK = ROOT / "_scratch/nsfhq04-structural-only2/maps/nsfhq04"
GOLDEN = ROOT / "_scratch/nsfhq04-prefix2/n0513/golden_n0513.dx"
os.environ["UEDCLI_PROJECT"] = str(TRUNK.parent.parent)

from uedcli import trunk  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
import uedcli_native  # noqa: E402
import utexture_decode as UT  # noqa: E402
from spike_classindex import class_index  # noqa: E402


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
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)][:513]
    assert names[512] == "Brush842", names[512]

    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))

    epkg, em = parse_golden(GOLDEN)

    print(f"n=513: native nodes={len(nm.nodes)} surfs={len(nm.surfs)} leaves={len(nm.leaves)}  "
          f"editor nodes={len(em.nodes)} surfs={len(em.surfs)} leaves={len(em.leaves)}")
    print(f"delta: d_nodes={len(nm.nodes)-len(em.nodes):+d} d_surfs={len(nm.surfs)-len(em.surfs):+d} "
          f"d_leaves={len(nm.leaves)-len(em.leaves):+d}")

    nc = Counter(names[s.i_actor] if 0 <= s.i_actor < len(names) else s.i_actor for s in nm.surfs)
    ec = Counter(epkg.name_of_ref(s.i_actor) for s in em.surfs)
    print(f"\nBrush842 surf count: native={nc.get('Brush842', 0)} editor={ec.get('Brush842', 0)}")

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
    print(f"Brush842 node-plane-owner count: native={n_owner.get('Brush842', 0)} "
          f"editor={e_owner.get('Brush842', 0)}")

    all_owner_names = set(n_owner) | set(e_owner)
    node_diffs = [(nam, n_owner.get(nam, 0), e_owner.get(nam, 0)) for nam in all_owner_names
                  if n_owner.get(nam, 0) != e_owner.get(nam, 0)]
    node_diffs.sort(key=lambda t: -abs(t[1] - t[2]))
    total_abs = sum(abs(n - e) for _, n, e in node_diffs)
    net = sum(n - e for _, n, e in node_diffs)
    print(f"\n=== NODE-PLANE-OWNER: {len(node_diffs)}/{len(names)} brushes differ, "
          f"abs-sum={total_abs}, net={net:+d} ===")
    for nam, n, e in node_diffs[:25]:
        idx = names.index(nam) if nam in names else -1
        a = level.actors[nam] if nam in level.actors else None
        p = dict(a.props) if a else {}
        cls = p.get("CsgOper", "?")
        flags = p.get("PolyFlags", "?")
        npolys = len(a.brush.polys) if a and a.brush else "?"
        print(f"  idx={idx:4} {str(nam):20s} native={n:4} editor={e:4} d={n-e:+d}  "
              f"CsgOper={cls} PolyFlags={flags} npolys={npolys}")


if __name__ == "__main__":
    raise SystemExit(main())
