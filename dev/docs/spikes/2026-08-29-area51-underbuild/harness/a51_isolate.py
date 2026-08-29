#!/usr/bin/env python3
"""Isolation probe: build [big solid box] + [Brush323 subtract]; attribute surfs by i_actor.

Decides whether Brush323's 0-surf drop is INTRINSIC (loop1/filter drops its polys even against
clean surrounding solid) or CONTEXTUAL (native's full world lacks the solid the dome carves into)."""
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
from spike_classindex import class_index

TRUNK = "/workspace/uedcli/_scratch/geo-confirm-area51-entrance/maps/area51-entrance"
FOCUS = sys.argv[1:] or ["Brush323"]


def box_brush_input(lo, hi):
    """6-quad CSG_Add box from world bounds lo..hi."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    faces = [  # (normal, verts-CCW seen from outside)
        ((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
        ((-1, 0, 0), [(x0, y0, z1), (x0, y1, z1), (x0, y1, z0), (x0, y0, z0)]),
        ((0, 1, 0), [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]),
        ((0, -1, 0), [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)]),
        ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
        ((0, 0, -1), [(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)]),
    ]
    verts, sizes, normals = [], [], []
    for n, vv in faces:
        sizes.append(len(vv))
        normals += [float(c) for c in n]
        for v in vv:
            verts += [float(c) for c in v]
    I = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    return (verts, sizes, normals, 1, 0, [0.0, 0.0, 0.0], I, [0.0, 0.0, 0.0],
            [1.0, 1.0, 1.0], [0] * 6, [], ([], [], [], []))


def build(brushes, names):
    built = uedcli_native.build_geometry_bspcsg(brushes)
    body = uedcli_native.serialize_model(built)
    return UM.parse_model_body(body, 0, len(body))


def attr(model, names):
    c = Counter(s.i_actor for s in model.surfs)
    return {names[idx]: n for idx, n in c.items() if 0 <= idx < len(names)}


def main():
    level, _ranks = trunk.read_level(Path(TRUNK))
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    brushes = [BM._build_brush_input(n, level.actors[n]) for n in names]

    # Dome brush = Box + Brush323 (mirror the full build's brush order: box first).
    focus_brushes = []
    focus_names = ["BOX"]
    focus_brushes.append(box_brush_input((-4000, -6000, -5000), (4000, 5000, 4000)))
    for f in FOCUS:
        i = names.index(f)
        focus_names.append(f)
        focus_brushes.append(brushes[i])

    m = build(focus_brushes, focus_names)
    a = attr(m, focus_names)
    print(f"isolated: nodes={len(m.nodes)} surfs={len(m.surfs)} points={len(m.points)}")
    for nm in focus_names:
        print(f"  {nm}: {a.get(nm, 0)} surfs")

    # Also: full-build re-attribute just to confirm focus brushes' full-build counts.
    fullm = build(brushes, names)
    fa = attr(fullm, names)
    print(f"full: nodes={len(fullm.nodes)} surfs={len(fullm.surfs)}")
    for f in FOCUS:
        print(f"  {f}: full={fa.get(f, 0)} surfs")
    nzero = sum(1 for n in names if fa.get(n, 0) == 0)
    print(f"  full-build brushes with 0 surfs: {nzero}")


if __name__ == "__main__":
    main()