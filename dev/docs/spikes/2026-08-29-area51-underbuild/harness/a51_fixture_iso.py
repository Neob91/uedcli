#!/usr/bin/env python3
"""Atomize the fixture divergence: isolate Brush3257 alone and with Brush529."""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance"
ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli import trunk
from uedcli.native import brush_marshal as BM
from uedcli.native import umodel as UM
import uedcli_native
from uedcli.utexture import load_package

GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"
TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"


def parse(built):
    body = uedcli_native.serialize_model(built)
    return UM.parse_model_body(body, 0, len(body))


def rings(m, names, nm):
    idx = names.index(nm)
    ss = [i for i, s in enumerate(m.surfs) if s.i_actor == idx]
    out = []
    for si in ss:
        r = []
        for n in m.nodes:
            if n.i_surf != si:
                continue
            r.append([tuple(round(c,1) for c in m.points[m.verts[n.i_vert_pool+k].i_vertex][:3])
                      for k in range(n.num_vertices)])
        out.append((si, r))
    return out


def main():
    pkg = load_package(GOLDEN)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    g = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    gcount = Counter()
    for s in g.surfs:
        nm = pkg.name_of_ref(s.i_actor)
        if nm is not None:
            gcount[nm] += 1

    level, _ranks = trunk.read_level(Path(TRUNK))
    names = [n for n in level.order if level.actors[n].brush is not None]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    byname = {n: i for i, n in enumerate(names)}

    for combo, lbl in ((["Brush529"], "529 alone"),
                       (["Brush3257"], "3257 alone"),
                       (["Brush529", "Brush3257"], "529+3257"),
                       (["Brush529", "Brush3257", "Brush3256"], "529+3257+3256")):
        idx = [byname[x] for x in combo]
        m = parse(uedcli_native.build_geometry_bspcsg([ins[i] for i in idx]))
        c = Counter(s.i_actor for s in m.surfs)
        gc = [gcount.get(x, 0) for x in combo]
        nn = [c.get(k, 0) for k in range(len(combo))]
        print(f"{lbl:16s}: nodes={len(m.nodes):3d} surfs={len(m.surfs):3d} "
              f"native={dict(zip(combo, nn))} golden={dict(zip(combo, gc))}")

    # geometries
    m = parse(uedcli_native.build_geometry_bspcsg([ins[byname['Brush529']], ins[byname['Brush3257']]]))
    print("\nnative [529+3257] per-brush face scraps:")
    for nm in ("Brush529", "Brush3257"):
        for si, rr in rings(m, ["Brush529", "Brush3257"], nm):
            print(f"  {nm} surf#{si}: {len(rr)} rings; first={rr[0] if rr else None}")
    print("\ngolden Brush3257 faces (from pool, by ibp):")
    for si, s in enumerate(g.surfs):
        if pkg.name_of_ref(s.i_actor) != "Brush3257":
            continue
        rings_ = []
        for n in g.nodes:
            if n.i_surf != si:
                continue
            rings_.append([tuple(round(c,1) for c in g.points[g.verts[n.i_vert_pool+k].i_vertex][:3])
                           for k in range(n.num_vertices)])
        print(f"  surf#{si} ibp={s.i_brush_poly} pbase={tuple(round(c,1) for c in g.points[s.p_base][:3])} nrings={len(rings_)} first={rings_[0] if rings_ else None}")


if __name__ == "__main__":
    main()