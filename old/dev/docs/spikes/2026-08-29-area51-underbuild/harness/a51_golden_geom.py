#!/usr/bin/env python3
"""Compare golden vs native per-brush per-node geometry for Brush1178 and Brush323.

For each surf keyed by i_actor, gather the RING VERTICES from the tree NODES that reference it
(nodes carry i_surf + i_vert_pool/num_vertices into verts -> points), then compare the golden
ring positions against what native produces.  This shows whether native's Brush1178 carve
(transformed with L = subsibel MainScale mirror) is displaced/reflected vs the golden."""
from __future__ import annotations

import os
import sys
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
from spike_classindex import class_index

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"
GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"
FOCUS = "Brush1178"


def ring_verts(m, s):
    """All ring polygons of the tree that reference surf s, in points coords."""
    out = []
    for n in m.nodes:
        if n.i_surf != s:
            continue
        ring = []
        for k in range(n.num_vertices):
            vi = m.verts[n.i_vert_pool + k].i_vertex
            ring.append(tuple(round(c, 1) for c in m.points[vi][:3]))
        out.append(ring)
    return out


def model_from_dx(path):
    pkg = load_package(path)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    return pkg, UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])


g_pkg, g = model_from_dx(GOLDEN)
print(f"golden: nodes={len(g.nodes)} surfs={len(g.surfs)}")

for label, m, nm_of in (("golden", g, g_pkg.name_of_ref),):
    by = {}
    for si, s in enumerate(m.surfs):
        nm = nm_of(s.i_actor)
        by.setdefault(nm, []).append(si)
    print(f"{label} {FOCUS} surfs:", len(by.get(FOCUS, [])))
    for si in by.get(FOCUS, [])[:16]:
        s = m.surfs[si]
        rings = ring_verts(m, si)
        print(f"  surf#{si} ibp={s.i_brush_poly} pbase={tuple(round(c,1) for c in m.points[s.p_base][:3])}"
              f" N={tuple(round(c,2) for c in m.vectors[s.v_normal][:3])} nrings={len(rings)}")
        for r in rings[:2]:
            print(f"    ring: {r}")