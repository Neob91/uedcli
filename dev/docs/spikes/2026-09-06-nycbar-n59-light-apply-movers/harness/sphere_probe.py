#!/usr/bin/env python3
"""Replay `UModel::PrecomputeSphereFilter` per mover over a built world model and compare the
resulting node flags against a reference package."""
import math
import struct
import sys
from pathlib import Path

HARNESS = Path("dev/docs/spikes/2026-09-03-incremental-actor-parity/harness").resolve()
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path("dev/docs/spikes/2026-07-15-native-materialize/harness").resolve()))
sys.path.insert(0, str(Path.cwd()))

import actor_parity as ap  # noqa: E402
import parity_gate as pg  # noqa: E402
from uedcli import rotation as ROT, trunk  # noqa: E402
from spike_classindex import class_index  # noqa: E402
from uedcli.movers import is_mover  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def world_verts(actor):
    """Mover brush polys transformed to world space: `Location + L*(v - PrePivot)`."""
    return [tuple(f32(c) for c in v) for v in ROT.world_vertices(actor)]


def fsphere(points):
    """UE1 `FSphere(FVector*, INT)`: bbox midpoint, radius = sqrt(max dist^2) * 1.001."""
    mn = tuple(min(p[i] for p in points) for i in range(3))
    mx = tuple(max(p[i] for p in points) for i in range(3))
    c = tuple(f32(f32(mn[i] + mx[i]) * 0.5) for i in range(3))
    w = 0.0
    for p in points:
        d = f32(f32(f32(f32(p[0] - c[0]) * f32(p[0] - c[0]))
                    + f32(f32(p[1] - c[1]) * f32(p[1] - c[1])))
                + f32(f32(p[2] - c[2]) * f32(p[2] - c[2])))
        if d > w:
            w = d
    return c, f32(math.sqrt(w) * f32(1.001))


def precompute_sphere_filter(nodes, center, radius):
    """`UModel::PrecomputeSphereFilter` (Engine 0x101af030 / helper 0x101aefb0)."""
    if not nodes:
        return
    stack = [0]
    while stack:
        i = stack.pop()
        while i != -1:
            n = nodes[i]
            n.node_flags &= 0x3F
            d = f32(f32(n.plane[0] * center[0] + n.plane[1] * center[1]
                        + n.plane[2] * center[2]) - n.plane[3])
            if -radius > d:
                n.node_flags |= 0x80
                i = n.i_front           # memory +0x20
            elif d > radius:
                n.node_flags |= 0x40
                i = n.i_back            # memory +0x24
            else:
                if n.i_front != -1:
                    stack.append(n.i_front)
                i = n.i_back


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 59
    full, name = ap._resolve_trunk(Path("/workspace/uedcli/dev/games/deusex/Maps/02_NYC_Bar.dx"),
                                   "deusex")
    level, _ = trunk.read_level(full)
    order = level.order[:n]
    ci = class_index()
    movers = [level.actors[a] for a in order
              if level.actors[a].brush and is_mover(level.actors[a], ci)]
    print("movers (actor order):", [m.name for m in movers])

    ref = pg.load_package(str(ap.ref_path(name, n)))
    import model_dump as MD
    idx = next(i for i in range(len(ref.exports))
               if ref.names[ref.exports[i]["nm"]].lower().startswith("model2"))
    body_nodes = MD.decode(ref, idx)["nodes"]
    print("ued node flags:", [hex(t[2]) for t in body_nodes])

    # Rebuild the model nodes from the reference (planes/children are identical to native's).
    nodes = []
    for plane, _zm, _flags, ints, _tail in body_nodes:
        bn = UM.BspNode(plane=plane)
        (bn.i_vert_pool, bn.i_surf, bn.i_front, bn.i_back, bn.i_plane) = ints[:5]
        bn.node_flags = 0
        nodes.append(bn)

    for m in reversed(movers):
        pts = world_verts(m)
        c, r = fsphere(pts)
        print(f"  {m.name}: sphere center={c} radius={r}")
        precompute_sphere_filter(nodes, c, r)
    print("replay flags:  ", [hex(x.node_flags) for x in nodes])


main()
