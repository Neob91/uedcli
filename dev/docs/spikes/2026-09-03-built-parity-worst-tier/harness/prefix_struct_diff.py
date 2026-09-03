#!/usr/bin/env python3
"""Structural diff of a prefix step: native build of the first N world-CSG brushes vs the live
prefix golden the bisection built (`_scratch/<tag>-prefix/nNNNN/golden_nNNNN.dx`). Reports per-brush
node ownership diffs, degenerate-ring census, one synchronized tree walk (divergence origins), and
optional per-brush fragment dumps. Generalizes `wg_n40_diff.py` (Garage-specific first cut).

Usage: prefix_struct_diff.py <level_name> <cache_hash> <tag> <N> [walk] [BrushName ...]
  e.g. prefix_struct_diff.py 00_trainingfinal f3e6539d... tf 687 walk Brush162
"""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prefix_search_lib as PSL  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402
import utexture_decode as UT  # noqa: E402
import uedcli_native  # noqa: E402

CACHES = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache")


def degen(model):
    out = []
    for ni, node in enumerate(model.nodes):
        if node.num_vertices == 0:
            continue
        idxs = [model.verts[node.i_vert_pool + k].i_vertex for k in range(node.num_vertices)]
        if len(set(idxs)) < 3:
            out.append(ni)
    return out


def owners(model, name_of):
    c = Counter()
    for node in model.nodes:
        if 0 <= node.i_surf < len(model.surfs):
            c[name_of(model.surfs[node.i_surf].i_actor)] += 1
    return c


def subtree_size(model, i):
    if i < 0:
        return 0
    n = 1 + subtree_size(model, model.nodes[i].i_front) + subtree_size(model, model.nodes[i].i_back)
    j = model.nodes[i].i_plane
    while j >= 0:
        n += 1
        j = model.nodes[j].i_plane
    return n


def sync_walk(nm, em):
    """Pair nodes from the root by position (iFront/iBack/iPlane); report each divergence ORIGIN —
    the first position whose paired planes differ — with both planes and paired-subtree sizes."""
    origins = []

    def rec(a, b, path):
        if a < 0 or b < 0:
            if a != b and (a >= 0 or b >= 0):
                origins.append((path, a, b, None, None))
            return
        na, nb = nm.nodes[a], em.nodes[b]
        pa, pb = na.plane, nb.plane
        dot = sum(pa[i] * pb[i] for i in range(3))
        if dot < 0.999999 or abs(pa[3] - pb[3]) > 0.01:
            origins.append((path, a, b, pa, pb))
            return
        rec(na.i_front, nb.i_front, path + "F")
        rec(na.i_back, nb.i_back, path + "B")
        rec(na.i_plane, nb.i_plane, path + "P")

    rec(0, 0, "")
    print(f"sync walk: {len(origins)} divergence origin(s)")
    for path, a, b, pa, pb in origins[:20]:
        sa = subtree_size(nm, a) if a >= 0 else 0
        sb = subtree_size(em, b) if b >= 0 else 0
        print(f"  at '{path or 'root'}': native node {a} (subtree {sa}) vs editor node {b} "
              f"(subtree {sb})")
        if pa:
            print(f"    native plane {tuple(round(v, 5) for v in pa)}")
            print(f"    editor plane {tuple(round(v, 5) for v in pb)}")


def dump_owner(model, name_of, target, points, verts, label):
    print(f"-- {target} fragments [{label}]:")
    for ni, node in enumerate(model.nodes):
        if not (0 <= node.i_surf < len(model.surfs)):
            continue
        if name_of(model.surfs[node.i_surf].i_actor) != target:
            continue
        pl = tuple(round(v, 4) for v in node.plane)
        ring = [tuple(round(c, 2) for c in points[verts[node.i_vert_pool + k].i_vertex])
                for k in range(node.num_vertices)]
        print(f"   node={ni:4} surf={node.i_surf:4} nv={node.num_vertices:2} "
              f"flags={node.node_flags:#04x} plane={pl}")
        print(f"      ring={ring}")


def main():
    level_name, cache_hash, tag, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    extra = sys.argv[5:]
    cache = CACHES / cache_hash / "trunk"
    wt = HERE.parents[4]
    ps = PSL.PrefixSearch(level_name, cache / f"maps/{level_name}",
                          wt / f"_scratch/{tag}-prefix", cache)
    names = ps.brush_names[:n]
    ins = [BM._build_brush_input(nm_, ps.level.actors[nm_]) for nm_ in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    body = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(body, 0, len(body))

    gpath = wt / f"_scratch/{tag}-prefix/n{n:04d}/golden_n{n:04d}.dx"
    pkg = UT.load_package(str(gpath))
    mods = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(mods, key=lambda i: pkg.exports[i]["ssize"])
    em = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])

    print(f"native {len(nm.nodes)}/{len(nm.surfs)}/{len(nm.leaves)}  "
          f"editor {len(em.nodes)}/{len(em.surfs)}/{len(em.leaves)}")
    dn, de = degen(nm), degen(em)
    print(f"degenerate(<3 distinct pts) nodes: native {len(dn)} editor {len(de)}")

    nat_name = lambda ia: names[ia] if 0 <= ia < len(names) else f"?{ia}"  # noqa: E731
    ed_name = lambda ia: pkg.name_of_ref(ia)  # noqa: E731
    no, eo = owners(nm, nat_name), owners(em, ed_name)
    for nm_ in sorted(set(no) | set(eo), key=lambda k: names.index(k) if k in names else 10**6):
        if no.get(nm_, 0) != eo.get(nm_, 0):
            print(f"  owner diff {nm_}: native {no.get(nm_, 0)} editor {eo.get(nm_, 0)} "
                  f"({no.get(nm_, 0) - eo.get(nm_, 0):+d})")

    if "walk" in extra:
        sync_walk(nm, em)
    for target in extra:
        if target == "walk":
            continue
        dump_owner(nm, nat_name, target, nm.points, nm.verts, "native")
        dump_owner(em, ed_name, target, em.points, em.verts, "editor")


if __name__ == "__main__":
    main()
