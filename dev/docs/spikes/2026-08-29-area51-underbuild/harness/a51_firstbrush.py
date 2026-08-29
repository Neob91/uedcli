#!/usr/bin/env python3
"""Isolate first-brush behavior: native build([Brush529]) vs golden Brush529 faces."""
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


def model_rings(m, si):
    rings = []
    for n in m.nodes:
        if n.i_surf != si:
            continue
        ring = [tuple(round(c, 1) for c in m.points[m.verts[n.i_vert_pool + k].i_vertex][:3])
                for k in range(n.num_vertices)]
        rings.append(ring)
    return rings


def main():
    pkg = load_package(GOLDEN)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    g = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    gi = [si for si, s in enumerate(g.surfs) if pkg.name_of_ref(s.i_actor) == "Brush529"]
    print(f"golden Brush529: {len(gi)} surfs")
    for si in gi:
        s = g.surfs[si]
        rings = model_rings(g, si)
        print(f"  surf#{si} ibp={s.i_brush_poly} pbase={tuple(round(c,1) for c in g.points[s.p_base][:3])}"
              f" N={tuple(round(c,2) for c in g.vectors[s.v_normal][:3])} nrings={len(rings)} rings={rings[:1]}")

    level, _ranks = trunk.read_level(Path(TRUNK))
    names = [n for n in level.order if level.actors[n].brush is not None]
    i529 = names.index("Brush529")
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg([ins[i529]])
    body = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(body, 0, len(body))
    print(f"\nnative [Brush529] alone: nodes={len(nm.nodes)} surfs={len(nm.surfs)} points={len(nm.points)}")
    print(f"  brush polys in marshalled input: {len(ins[i529][1])} sizes={ins[i529][1]}")


if __name__ == "__main__":
    main()