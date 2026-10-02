#!/usr/bin/env python3
"""Per-brush surf/node diff for an 11_paris_underground prefix already built by
`pu_prefix_search.py` (uses its saved `golden_n{N:04d}.dx`). Usage: pu_prefix_diff.py N"""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prefix_search_lib as PSL  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
import utexture_decode as UT  # noqa: E402

TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/bdf66b5dc02df008a53f5018b5aeab950cf13481c2a49bd0f683dd714429c718/trunk")


def main():
    n = int(sys.argv[1])
    wt = HERE.parents[4]
    ps = PSL.PrefixSearch("11_paris_underground", TRUNK / "maps/11_paris_underground",
                          wt / "_scratch/pu-prefix", TRUNK)
    nm = ps.native_counts(n)
    golden = wt / f"_scratch/pu-prefix/n{n:04d}/golden_n{n:04d}.dx"
    pkg = UT.load_package(str(golden))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    em = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    names = ps.brush_names[:n]

    def surf_counts(model, owner):
        return Counter(owner(s.i_actor) for s in model.surfs)

    def node_counts(model, owner):
        c = Counter()
        for node in model.nodes:
            if 0 <= node.i_surf < len(model.surfs):
                c[owner(model.surfs[node.i_surf].i_actor)] += 1
        return c

    nsc = surf_counts(nm, lambda ia: names[ia] if 0 <= ia < len(names) else f"?{ia}")
    esc = surf_counts(em, lambda ia: pkg.name_of_ref(ia))
    nnc = node_counts(nm, lambda ia: names[ia] if 0 <= ia < len(names) else f"?{ia}")
    enc = node_counts(em, lambda ia: pkg.name_of_ref(ia))
    print(f"n={n}: native nodes={len(nm.nodes)} surfs={len(nm.surfs)} leaves={len(nm.leaves)} | "
          f"editor nodes={len(em.nodes)} surfs={len(em.surfs)} leaves={len(em.leaves)}")
    for b in names:
        if nsc.get(b, 0) != esc.get(b, 0) or nnc.get(b, 0) != enc.get(b, 0):
            print(f"  {b:12} idx={names.index(b):3} surfs {nsc.get(b,0)}/{esc.get(b,0)}  "
                  f"nodes {nnc.get(b,0)}/{enc.get(b,0)}")


if __name__ == "__main__":
    main()
