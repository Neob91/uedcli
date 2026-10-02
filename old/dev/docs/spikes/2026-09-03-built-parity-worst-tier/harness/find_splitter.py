#!/usr/bin/env python3
"""Locate the plane that splits club Brush20's z=96 face natively (cut crosses edge x=1328
at y~-169.014) and compare its bits native vs editor. Method: walk the native tree path from
the root to the sliver nodes (2083/2084) and print every ancestor plane; then match each
ancestor's plane in the editor model by proximity and diff exact f32 bits."""
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
TARGET_NODES = [2083, 2084, 2085]


def bits(x):
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

    # parent map: child -> (parent, which)
    parent = {}
    for ni, node in enumerate(nm.nodes):
        for which, ch in (("front", node.i_front), ("back", node.i_back),
                          ("plane", node.i_plane)):
            if ch >= 0:
                parent[ch] = (ni, which)

    corner_a = (1328.0, -192.0, 96.0)
    corner_b = (1328.0, 64.0, 96.0)

    def pdist(plane, p):
        return plane[0] * p[0] + plane[1] * p[1] + plane[2] * p[2] - plane[3]

    for t in TARGET_NODES:
        chain = []
        cur = t
        while cur in parent:
            pi, which = parent[cur]
            chain.append((pi, which))
            cur = pi
        chain.reverse()
        print(f"\n=== native path to node {t} ({len(chain)} ancestors) ===")
        for pi, which in chain:
            node = nm.nodes[pi]
            pl = node.plane
            da, db = pdist(pl, corner_a), pdist(pl, corner_b)
            own = nm.surfs[node.i_surf].i_actor if 0 <= node.i_surf < len(nm.surfs) else -1
            oname = names[own] if 0 <= own < len(names) else own
            mark = " <== near-tangent" if (abs(da) < 1.0 or abs(db) < 1.0) and min(abs(da), abs(db)) > 1e-6 and da * db <= 0 else ""
            if abs(da) < 2.0 and abs(db) < 2.0:
                print(f"  node={pi:5} [{which:5}] owner={oname:12} plane={tuple(pl)} "
                      f"dA={da:+.6f} dB={db:+.6f}{mark}")

    # Same-owner plane in the editor model for any near-tangent owner found above:
    print("\n=== editor planes for candidate owner brushes ===")
    for ni, node in enumerate(em.nodes):
        pl = node.plane
        da, db = pdist(pl, corner_a), pdist(pl, corner_b)
        if abs(da) < 1.0 and abs(db) < 1.0:
            own = em.surfs[node.i_surf].i_actor if 0 <= node.i_surf < len(em.surfs) else None
            print(f"  node={ni:5} owner={pkg.name_of_ref(own):12} plane={tuple(pl)} "
                  f"bits=({bits(pl[0])},{bits(pl[1])},{bits(pl[2])},{bits(pl[3])}) "
                  f"dA={da:+.6f} dB={db:+.6f}")
    print("\n=== native planes near-tangent to the same corners ===")
    for ni, node in enumerate(nm.nodes):
        pl = node.plane
        da, db = pdist(pl, corner_a), pdist(pl, corner_b)
        if abs(da) < 1.0 and abs(db) < 1.0:
            own = nm.surfs[node.i_surf].i_actor if 0 <= node.i_surf < len(nm.surfs) else -1
            oname = names[own] if 0 <= own < len(names) else own
            print(f"  node={ni:5} owner={oname:12} plane={tuple(pl)} "
                  f"bits=({bits(pl[0])},{bits(pl[1])},{bits(pl[2])},{bits(pl[3])}) "
                  f"dA={da:+.6f} dB={db:+.6f}")


if __name__ == "__main__":
    main()
