#!/usr/bin/env python3
"""Per-brush attribution for `12_Vandenberg_Gas.dx`'s residual (post `d07622e`+`4b7b186`,
re-measured fresh 2026-09-01): nodes native=11289 golden=10683 d=+606; surfs native=4556
golden=4554 d=+2; leaves native=3334 golden=3468 d=-134; verts d=+9480; points d=+696;
vectors d=+130. Unlike the OceanLab/NYC747 residuals, surfs is barely nonzero (+2) while
nodes/leaves/verts show a real tree-SHAPE divergence (LENGTH MISMATCH on all three).

Two attributions, same pattern as `fc08_surf_diff.py`/`nyc747_surf_diff.py` (surf count) and
`fc08_node_owner_diff.py` (node-plane-owner via node.i_surf -> surf.i_actor):
  1. surf-count per brush (native BspSurf.i_actor vs golden's resolved via epkg.name_of_ref)
  2. node-plane-owner-count per brush (native/golden node.i_surf -> surf.i_actor, Counter diff)

Usage: .venv/bin/python vandenberg_attrib.py
"""
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/vandenberg-gas-parity")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

CACHE = ROOT / "_scratch/uedcli-parity-cache/7d06dd6155e5daa7c78e76ed19a66068852973670d1c56dddd9628b2ca393c13"
TRUNK = CACHE / "trunk/maps/12_vandenberg_gas"
GOLDEN = Path("/tmp/uedcli-parity-cache/7d06dd6155e5daa7c78e76ed19a66068852973670d1c56dddd9628b2ca393c13/golden.dx")
os.environ.setdefault("UEDCLI_PROJECT", str(CACHE / "trunk"))

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

    # 1. surf-count per brush
    nc = Counter(names[s.i_actor] if 0 <= s.i_actor < len(names) else s.i_actor
                 for s in nm.surfs)
    ec = Counter(epkg.name_of_ref(s.i_actor) for s in em.surfs)

    all_names = set(nc) | set(ec)
    surf_diffs = [(nam, nc.get(nam, 0), ec.get(nam, 0)) for nam in all_names
                  if nc.get(nam, 0) != ec.get(nam, 0)]
    surf_diffs.sort(key=lambda t: names.index(t[0]) if t[0] in names else -1)
    print(f"\n=== SURF-COUNT: {len(surf_diffs)} brushes differ (native, editor) ===")
    for nam, n, e in surf_diffs:
        idx = names.index(nam) if nam in names else -1
        a = level.actors[nam] if nam in level.actors else None
        p = dict(a.props) if a else {}
        cls = p.get("CsgOper", "?")
        flags = p.get("PolyFlags", "?")
        npolys = len(a.brush.polys) if a and a.brush else "?"
        print(f"  idx={idx:4} {nam:20s} native={n:4} editor={e:4} d={n-e:+d}  "
              f"CsgOper={cls} PolyFlags={flags} npolys={npolys}")

    # 2. node-plane-owner-count per brush: node.i_surf -> surf.i_actor
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
    for nam, n, e in node_diffs[:40]:
        idx = names.index(nam) if nam in names else -1
        a = level.actors[nam] if nam in level.actors else None
        p = dict(a.props) if a else {}
        cls = p.get("CsgOper", "?")
        flags = p.get("PolyFlags", "?")
        npolys = len(a.brush.polys) if a and a.brush else "?"
        print(f"  idx={idx:4} {str(nam):20s} native={n:4} editor={e:4} d={n-e:+d}  "
              f"CsgOper={cls} PolyFlags={flags} npolys={npolys}")

    print("\nnode/leaf/surf totals: native", len(nm.nodes), len(nm.surfs), len(nm.leaves),
          " editor", len(em.nodes), len(em.surfs), len(em.leaves))


if __name__ == "__main__":
    raise SystemExit(main())
