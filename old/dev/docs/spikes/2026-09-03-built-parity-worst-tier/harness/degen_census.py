#!/usr/bin/env python3
"""Corpus census: per level, count DEGENERATE node rings (fewer than 3 distinct points, or
zero area) native vs editor golden — measuring how much of each node-count residual the
kept-degenerate-fragment mechanism explains.

Usage: degen_census.py [level ...]
"""
import json
import os
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[5]  # harness/<slug>/spikes/docs/dev -> repo root
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNKS = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache")
GOLDENS = Path("/tmp/uedcli-parity-cache")


def cross(o, a, b):
    ux, uy, uz = a[0] - o[0], a[1] - o[1], a[2] - o[2]
    vx, vy, vz = b[0] - o[0], b[1] - o[1], b[2] - o[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def ring_area2(pts):
    if len(pts) < 3:
        return 0.0
    sx = sy = sz = 0.0
    for i in range(1, len(pts) - 1):
        c = cross(pts[0], pts[i], pts[i + 1])
        sx += c[0]; sy += c[1]; sz += c[2]
    return (sx * sx + sy * sy + sz * sz) ** 0.5


def degen_count(model):
    n_lt3 = n_zero = 0
    for node in model.nodes:
        if node.num_vertices == 0:
            continue
        idxs = [model.verts[node.i_vert_pool + k].i_vertex for k in range(node.num_vertices)]
        pts = [model.points[i] for i in idxs]
        if len(set(idxs)) < 3:
            n_lt3 += 1
        elif ring_area2(pts) < 1e-4:
            n_zero += 1
    return n_lt3, n_zero


def main():
    metas = {}
    for meta in sorted(GOLDENS.glob("*/meta.json")):
        m = json.loads(meta.read_text())
        if m.get("status") == "complete" and (TRUNKS / meta.parent.name / "trunk/maps").is_dir():
            metas[m["level_name"]] = TRUNKS / meta.parent.name
    want = sys.argv[1:] or sorted(metas)
    os.environ.setdefault("UEDCLI_PROJECT", str(next(iter(metas.values())) / "trunk"))

    from uedcli import trunk as TR
    from uedcli.native import brush_marshal as BM
    from uedcli.native import umodel as UM
    import uedcli_native
    import utexture_decode as UT
    from spike_classindex import class_index
    ci = class_index()

    print(f"{'level':28} {'d_nodes':>8} {'nat<3':>6} {'ed<3':>6} {'natA0':>6} {'edA0':>6}")
    for name in want:
        cdir = metas[name]
        level, _ = TR.read_level(next((cdir / "trunk/maps").iterdir()))
        names = [n for n in level.order
                 if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
        ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
        built = uedcli_native.build_geometry_bspcsg(ins)
        body = uedcli_native.serialize_model(built)
        nm = UM.parse_model_body(body, 0, len(body))
        pkg = UT.load_package(str(GOLDENS / cdir.name / "golden.dx"))
        mods = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
        mi = max(mods, key=lambda i: pkg.exports[i]["ssize"])
        em = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
        na, nz = degen_count(nm)
        ea, ez = degen_count(em)
        print(f"{name:28} {len(nm.nodes)-len(em.nodes):>+8} {na:>6} {ea:>6} {nz:>6} {ez:>6}",
              flush=True)


if __name__ == "__main__":
    main()
