#!/usr/bin/env python3
"""Cause-2 TRIGGER discriminator — quantify, per level, the OVERLAPPING-ADDITIVE density that the
shattered-tree diagnosis predicts drives native's over-solidification.

The pinned mechanism (shatter_probe.py + §87): native's `is_csg_filter` (bspcsg.rs:437) drops the
engine's `NumVertices>0` clause, so an FWTB-DEAD world face (a face BURIED inside a later brush,
NumVertices set to 0 but the node kept as a splitter) is wrongly treated as a CSG solid-divider and
flips `Outside`.  For a SUBTRACT the dead face still bounds solid, so the hack is (net) correct.  For
two OVERLAPPING ADDITIVE brushes the buried face has solid on BOTH sides — not a boundary at all —
so the false Outside-flip mis-carves genuine void into solid.  Therefore the trigger is the count of
BURIED ADDITIVE FACES, proxied here by ADDITIVE-brush AABB overlaps.

For each trunk this reports: brush counts by CsgOper; additive-additive AABB-overlapping pairs (the
buried-face proxy) both raw and per-additive-brush; and the add:subtract ratio — so the discriminator
can be read against the measured over-solidification ([A] in shatter_probe.py).

Usage: overlap_discriminator.py <trunk-dir> [<trunk-dir> ...]
"""
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))

from uedcli import trunk  # noqa: E402
from uedcli import rotation as ROT  # noqa: E402

_CSG = {"CSG_Active": 0, "CSG_Add": 1, "CSG_Subtract": 2, "CSG_Intersect": 3, "CSG_Deintersect": 4}


def _vec3(s, d=(0.0, 0.0, 0.0)):
    if not s:
        return d
    f = {}
    for part in str(s).strip("()").split(","):
        if "=" in part:
            k, v = part.split("=")
            try:
                f[k.strip().upper()] = float(v)
            except ValueError:
                pass
    return (f.get("X", d[0]), f.get("Y", d[1]), f.get("Z", d[2]))


def brush_world_aabb(name, actor):
    """World-space AABB of a brush, via the same transform the native build uses:
    world = Location + R*(v - PrePivot)."""
    raw = dict(actor.props)
    Rm = ROT.actor_matrix(actor)
    R = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]] if Rm is None else [[float(x) for x in r] for r in Rm]
    loc = tuple(float(c) for c in actor.location) if actor.location else (0.0, 0.0, 0.0)
    pp = _vec3(raw.get("PrePivot"))
    mn = [1e30, 1e30, 1e30]
    mx = [-1e30, -1e30, -1e30]
    got = False
    for poly in actor.brush.polys:
        for v in poly.vertices:
            vx, vy, vz = float(v[0]) - pp[0], float(v[1]) - pp[1], float(v[2]) - pp[2]
            wx = loc[0] + R[0][0] * vx + R[0][1] * vy + R[0][2] * vz
            wy = loc[1] + R[1][0] * vx + R[1][1] * vy + R[1][2] * vz
            wz = loc[2] + R[2][0] * vx + R[2][1] * vy + R[2][2] * vz
            for i, w in enumerate((wx, wy, wz)):
                if w < mn[i]:
                    mn[i] = w
                if w > mx[i]:
                    mx[i] = w
            got = True
    if not got:
        return None
    return (tuple(mn), tuple(mx))


def aabb_overlap(a, b, margin=0.0):
    (amn, amx), (bmn, bmx) = a, b
    for i in range(3):
        if amx[i] < bmn[i] - margin or bmx[i] < amn[i] - margin:
            return False
    return True


def analyze(trunk_dir):
    lvl, _ = trunk.read_level(Path(trunk_dir))
    adds, subs = [], []
    n_by_oper = {}
    for name, a in lvl.actors.items():
        if a.brush is None:
            continue
        oper = _CSG.get(dict(a.props).get("CsgOper", "CSG_Add"), 1)
        n_by_oper[oper] = n_by_oper.get(oper, 0) + 1
        box = brush_world_aabb(name, a)
        if box is None:
            continue
        if oper == 1:
            adds.append(box)
        elif oper == 2:
            subs.append(box)

    # additive-additive overlapping pairs (buried-additive-face proxy).  O(n^2) but n<=~1000.
    add_add = 0
    add_with_overlap = set()
    for i in range(len(adds)):
        for j in range(i + 1, len(adds)):
            if aabb_overlap(adds[i], adds[j]):
                add_add += 1
                add_with_overlap.add(i)
                add_with_overlap.add(j)
    # additive brushes that overlap ANY subtract (buried into carved void = where the hack mis-fires)
    add_in_sub = 0
    for i, ab in enumerate(adds):
        if any(aabb_overlap(ab, sb) for sb in subs):
            add_in_sub += 1

    n_add = n_by_oper.get(1, 0)
    n_sub = n_by_oper.get(2, 0)
    print(f"== {Path(trunk_dir).name}")
    print(f"   brushes by CsgOper: {dict(sorted(n_by_oper.items()))}  "
          f"(1=Add {n_add}, 2=Sub {n_sub}, ratio {n_add / max(n_sub, 1):.2f}:1)")
    print(f"   ADD-ADD AABB-overlapping pairs: {add_add}  "
          f"({add_add / max(n_add, 1):.2f} per additive brush)")
    print(f"   additive brushes overlapping >=1 other additive: {len(add_with_overlap)} "
          f"({100 * len(add_with_overlap) / max(n_add, 1):.1f}% of adds)")
    print(f"   additive brushes overlapping >=1 subtract: {add_in_sub} "
          f"({100 * add_in_sub / max(n_add, 1):.1f}% of adds)")


if __name__ == "__main__":
    for d in sys.argv[1:]:
        analyze(d)
