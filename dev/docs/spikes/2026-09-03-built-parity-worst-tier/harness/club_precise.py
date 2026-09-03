#!/usr/bin/env python3
"""Full-precision ring dump for club Brush20's surf-89 fragments (native nodes 2083/2084/2085,
editor node 1170) + their tree ancestry planes at full precision."""
import json
import os
import struct
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[5]  # harness/<slug>/spikes/docs/dev -> repo root
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

TRUNKS = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache")
GOLDENS = Path("/tmp/uedcli-parity-cache")
LEVEL = "10_paris_club"


def hx(x):
    return hex(struct.unpack("<I", struct.pack("<f", x))[0])


def main():
    cdir = None
    for meta in GOLDENS.glob("*/meta.json"):
        m = json.loads(meta.read_text())
        if m.get("level_name") == LEVEL and m.get("status") == "complete":
            cdir = meta.parent.name
    os.environ.setdefault("UEDCLI_PROJECT", str(TRUNKS / cdir / "trunk"))

    from uedcli import trunk as TR
    from uedcli.native import brush_marshal as BM
    from uedcli.native import umodel as UM
    import uedcli_native
    import utexture_decode as UT
    from spike_classindex import class_index

    level, _ = TR.read_level(next((TRUNKS / cdir / "trunk/maps").iterdir()))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    body = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(body, 0, len(body))

    pkg = UT.load_package(str(GOLDENS / cdir / "golden.dx"))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    em = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])

    def show(model, label, node_ids):
        print(f"--- {label} ---")
        parent = {}
        for ni, node in enumerate(model.nodes):
            for which, ch in (("F", node.i_front), ("B", node.i_back), ("P", node.i_plane)):
                if ch >= 0:
                    parent[ch] = (ni, which)
        for t in node_ids:
            node = model.nodes[t]
            print(f" node {t}: plane={node.plane} flags={node.node_flags} "
                  f"nverts={node.num_vertices}")
            for k in range(node.num_vertices):
                p = model.points[model.verts[node.i_vert_pool + k].i_vertex]
                print(f"    v[{k}] = ({p[0]!r}, {p[1]!r}, {p[2]!r})  "
                      f"({hx(p[0])},{hx(p[1])},{hx(p[2])})  ptidx={model.verts[node.i_vert_pool+k].i_vertex}")
            chain = []
            cur = t
            while cur in parent:
                pi, w = parent[cur]
                chain.append((pi, w))
                cur = pi
            chain.reverse()
            print(f"    ancestry ({len(chain)}):")
            for pi, w in chain:
                nd = model.nodes[pi]
                print(f"      [{w}] node={pi} plane={tuple(nd.plane)}")

    show(nm, "native", [2083, 2084, 2085])
    show(em, "editor", [1170])


if __name__ == "__main__":
    main()
