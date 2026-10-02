#!/usr/bin/env python3
"""Golden surfs whose geometry is adjacent to the dome faces, grouped by actor.

Finds which golden brushes bound the dome (their surfs' ring verts lie near the golden Brush323
faces), then looks up their native surf counts to see which surrounding solid is missing."""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict
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

GOLDEN = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/golden_area51.dx"
TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"

DOME_AABB = ((-576, -2656, -1312), (384, -960, 384))


def surf_rings(g, si):
    rings = []
    for n in g.nodes:
        if n.i_surf != si:
            continue
        ring = [tuple(g.points[g.verts[n.i_vert_pool + k].i_vertex][:3])
                for k in range(n.num_vertices)]
        rings.append(ring)
    return rings


def ring_near(aabb0, aabb1, ring, tol=8.0):
    xs = [v[0] for v in ring]; ys = [v[1] for v in ring]; zs = [v[2] for v in ring]
    lo = (min(xs), min(ys), min(zs)); hi = (max(xs), max(ys), max(zs))
    def near_pair(a0, a1, b0, b1):
        return all(a1[i] + tol >= b0[i] and b1[i] + tol >= a0[i] for i in range(3))
    return near_pair(aabb0, aabb1, lo, hi)


def main():
    pkg = load_package(GOLDEN)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    g = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])
    print(f"golden: nodes={len(g.nodes)} surfs={len(g.surfs)}")

    # golden surfs near the dome AABB, excluding Brush323 itself
    near = Counter()
    for si, s in enumerate(g.surfs):
        nm = pkg.name_of_ref(s.i_actor)
        if nm == "Brush323":
            continue
        for ring in surf_rings(g, si):
            if ring_near(DOME_AABB[0], DOME_AABB[1], ring):
                near[nm] += 1
                break
    print(f"{len(near)} actors have surfs adjacent to the dome AABB")
    for nm, c in near.most_common(30):
        print(f"  {nm}: {c}")

    # native counts for those actors
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    brushes = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(brushes)
    body = uedcli_native.serialize_model(built)
    nmodel = UM.parse_model_body(body, 0, len(body))
    ncount = Counter(s.i_actor for s in nmodel.surfs)
    print(f"\nnative counts for those actors:")
    for nm, c in near.most_common(30):
        idx = names.index(nm) if nm in names else None
        nc = ncount[idx] if idx is not None and 0 <= idx < len(names) else None
        print(f"  {nm}: golden={c} native={nc}")


if __name__ == "__main__":
    main()