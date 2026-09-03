#!/usr/bin/env python3
"""For a level and brush name(s): list every BSP node owned by that brush (native vs golden)
with its plane, vertex count, flags, and back-leaf/zone info — to see WHICH fragments differ
on the small-residual scaled-brush cases (club Brush20, chateau Brush80, helibase 3).

Usage: node_frag_diff.py <level_name> <BrushName> [BrushName ...]
"""
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


def main():
    name = sys.argv[1]
    targets = sys.argv[2:]
    cdir = None
    for meta in GOLDENS.glob("*/meta.json"):
        m = json.loads(meta.read_text())
        if m.get("level_name") == name and m.get("status") == "complete":
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

    def dump(model, owner_fn, target, points, vectors, verts):
        rows = []
        for ni, node in enumerate(model.nodes):
            if not (0 <= node.i_surf < len(model.surfs)):
                continue
            s = model.surfs[node.i_surf]
            if owner_fn(s.i_actor) != target:
                continue
            pl = tuple(round(v, 4) for v in node.plane) if hasattr(node, "plane") else None
            ring = [tuple(round(c, 3) for c in points[verts[node.i_vert_pool + k].i_vertex])
                    for k in range(node.num_vertices)] if hasattr(node, "i_vert_pool") else []
            rows.append((ni, node.i_surf, pl, node.num_vertices,
                         getattr(node, "node_flags", None), ring))
        return rows

    for t in targets:
        print(f"\n===== {name} / {t} =====")
        nn = dump(nm, lambda ia: names[ia] if 0 <= ia < len(names) else None, t,
                  nm.points, nm.vectors, nm.verts)
        ee = dump(em, lambda ia: pkg.name_of_ref(ia), t, em.points, em.vectors, em.verts)
        print(f"-- native: {len(nn)} nodes")
        for r in nn:
            print(f"   node={r[0]:6} surf={r[1]:5} nverts={r[3]:2} flags={r[4]} plane={r[2]}")
            print(f"      ring={r[5]}")
        print(f"-- editor: {len(ee)} nodes")
        for r in ee:
            print(f"   node={r[0]:6} surf={r[1]:5} nverts={r[3]:2} flags={r[4]} plane={r[2]}")
            print(f"      ring={r[5]}")


if __name__ == "__main__":
    main()
