#!/usr/bin/env python3
"""Per-brush divergence attribution x brush properties, corpus-wide, fully offline.

For each cached level: build native `build_geometry_bspcsg` in process, parse the cached
editor golden, diff per-brush surf counts and node-plane-owner counts (the established
`vandenberg_attrib.py` method), then cross-tab the divergent brush set against brush
properties (scaled / mirrored / sheer / rotation class / semisolid / CsgOper) to find what
enriches among divergent brushes vs the level's base rate.

Usage: attrib_props.py [level_name ...]   (default: all cached levels)
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

WT = Path(__file__).resolve().parents[5]  # harness/<slug>/spikes/docs/dev -> repo root
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNKS = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache")
GOLDENS = Path("/tmp/uedcli-parity-cache")

CARDINAL = 16384


def rot_class(uu):
    nz = [c for c in uu if c % 65536 != 0]
    if not nz:
        return "none"
    noncard = [c for c in nz if c % CARDINAL != 0]
    if not noncard:
        return "cardinal-1ax" if len(nz) == 1 else "cardinal-multi"
    return "noncard-1ax" if len(nz) == 1 else f"noncard-multi({len(noncard)}nc)"


def brush_props(a):
    from uedcli import rotation as ROT
    props = dict(a.props)
    ms, ps = ROT.actor_main_scale(a), ROT.actor_post_scale(a)
    scaled = not (ms.is_identity() and ps.is_identity())
    mirrored = False
    if scaled:
        L = ROT.actor_linear(a)
        det = (L[0][0] * (L[1][1] * L[2][2] - L[1][2] * L[2][1])
               - L[0][1] * (L[1][0] * L[2][2] - L[1][2] * L[2][0])
               + L[0][2] * (L[1][0] * L[2][1] - L[1][1] * L[2][0]))
        mirrored = det < 0
    try:
        pf = int(props.get("PolyFlags", "0"))
    except ValueError:
        pf = 0
    return {
        "scaled": scaled,
        "mirrored": mirrored,
        "rot": rot_class(ROT.actor_rotation_uu(a)),
        "semisolid": bool(pf & 0x20),
        "oper": props.get("CsgOper", "<absent>"),
        "npolys": len(a.brush.polys) if a.brush else 0,
    }


def parse_golden(path):
    import utexture_decode as UT
    from uedcli.native import umodel as UM
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    m = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    return pkg, m


def run_level(name, cdir, ci):
    from uedcli import trunk as TR
    from uedcli.native import brush_marshal as BM
    from uedcli.native import umodel as UM
    import uedcli_native

    lvl_dir = next((cdir / "trunk/maps").iterdir())
    level, _ = TR.read_level(lvl_dir)
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))
    epkg, em = parse_golden(GOLDENS / cdir.name / "golden.dx")

    props = {n: brush_props(level.actors[n]) for n in names}

    def surf_counts(model, owner):
        return Counter(owner(s.i_actor) for s in model.surfs)

    def node_owner_counts(model, owner):
        c = Counter()
        for node in model.nodes:
            if 0 <= node.i_surf < len(model.surfs):
                c[owner(model.surfs[node.i_surf].i_actor)] += 1
            else:
                c[None] += 1
        return c

    n_owner = lambda ia: names[ia] if 0 <= ia < len(names) else f"?{ia}"
    e_owner = lambda ia: epkg.name_of_ref(ia)

    nsc, esc = surf_counts(nm, n_owner), surf_counts(em, e_owner)
    nnc, enc = node_owner_counts(nm, n_owner), node_owner_counts(em, e_owner)

    surf_diff = {b: (nsc.get(b, 0), esc.get(b, 0)) for b in set(nsc) | set(esc)
                 if nsc.get(b, 0) != esc.get(b, 0)}
    node_diff = {b: (nnc.get(b, 0), enc.get(b, 0)) for b in set(nnc) | set(enc)
                 if nnc.get(b, 0) != enc.get(b, 0)}

    print(f"\n===== {name} =====")
    print(f"totals native/editor: nodes {len(nm.nodes)}/{len(em.nodes)} "
          f"(d={len(nm.nodes)-len(em.nodes):+d})  surfs {len(nm.surfs)}/{len(em.surfs)} "
          f"(d={len(nm.surfs)-len(em.surfs):+d})  leaves {len(nm.leaves)}/{len(em.leaves)} "
          f"(d={len(nm.leaves)-len(em.leaves):+d})")

    def xtab(diff, label):
        div = [b for b in diff if b in props]
        base, dvp = Counter(), Counter()
        for n in names:
            p = props[n]
            for k in ("scaled", "mirrored", "semisolid"):
                base[k] += p[k]
            base[p["rot"]] += 1
        for b in div:
            p = props[b]
            for k in ("scaled", "mirrored", "semisolid"):
                dvp[k] += p[k]
            dvp[p["rot"]] += 1
        nb, nd = len(names), len(div)
        print(f"  [{label}] divergent brushes: {nd}/{nb} "
              f"abs-sum={sum(abs(a-b) for a, b in diff.values())} "
              f"net={sum(a-b for a, b in diff.values()):+d}")
        if not nd:
            return
        keys = ["scaled", "mirrored", "semisolid", "cardinal-1ax", "cardinal-multi",
                "noncard-1ax"] + sorted(k for k in set(base) | set(dvp) if k.startswith("noncard-multi"))
        for k in keys:
            br, dr = base[k] / nb, dvp[k] / nd
            if base[k] or dvp[k]:
                print(f"      {k:22} base {base[k]:4}/{nb} ({br:5.1%})   divergent {dvp[k]:4}/{nd} "
                      f"({dr:5.1%})   enrich x{dr/br if br else float('inf'):.2f}")
        # earliest divergent brush in world-CSG order
        idxs = sorted(names.index(b) for b in div)
        first = names[idxs[0]]
        print(f"      earliest divergent: idx={idxs[0]} {first} {props[first]} "
              f"native/editor={diff[first]}")
        top = sorted(div, key=lambda b: -abs(diff[b][0] - diff[b][1]))[:8]
        for b in top:
            a, e = diff[b]
            print(f"      top d={a-e:+5d} idx={names.index(b):4} {b:18} {props[b]}")

    xtab(surf_diff, "surf-count")
    xtab(node_diff, "node-owner")
    return name


def main():
    metas = {}
    for meta in sorted(GOLDENS.glob("*/meta.json")):
        m = json.loads(meta.read_text())
        if m.get("status") == "complete" and (TRUNKS / meta.parent.name / "trunk/maps").is_dir():
            metas[m["level_name"]] = TRUNKS / meta.parent.name
    want = sys.argv[1:] or sorted(metas)
    os.environ.setdefault("UEDCLI_PROJECT", str(next(iter(metas.values())) / "trunk"))
    from spike_classindex import class_index
    ci = class_index()
    for name in want:
        run_level(name, metas[name], ci)


if __name__ == "__main__":
    main()
