#!/usr/bin/env python3
"""Corpus-wide brush-property census over the cached parity trunks: what distinguishes the
worst-parity tier (nodes non-exact) from the node-exact tier?

Per level, over its WORLD-CSG brush set (same `_in_world_csg` selection materialize uses):
scaled (MainScale/PostScale non-identity, sheer, mirror det<0), rotation class (cardinal
single/multi-axis, non-cardinal 1-axis / 2+-axis), CsgOper histogram (incl. absent =
CSG_Active), semisolid count, PF_Portal poly count, plus mover counts (excluded from CSG).

Reads the breadth-parity-check worktree's `_scratch/uedcli-parity-cache/<hash>/trunk` caches;
no editor, no native ext.
"""
import os
import sys
from collections import Counter
from pathlib import Path

WT = Path(__file__).resolve().parents[5]  # harness/<slug>/spikes/docs/dev -> repo root
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

CACHE = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache")

PF_PORTAL = 0x4000000
PF_SEMISOLID = 0x20
CARDINAL = 16384


def rot_class(uu):
    nz = [c for c in uu if c % 65536 != 0]
    if not nz:
        return "none"
    noncard = [c for c in nz if c % CARDINAL != 0]
    axes = len(nz)
    if not noncard:
        return "cardinal-1ax" if axes == 1 else "cardinal-multi"
    return f"noncard-{min(len(noncard), 3)}ax" if axes > 1 else "noncard-1ax"


def main():
    import json
    metas = {}
    for meta in sorted(Path("/tmp/uedcli-parity-cache").glob("*/meta.json")):
        m = json.loads(meta.read_text())
        if m.get("status") == "complete" and (CACHE / meta.parent.name / "trunk/maps").is_dir():
            metas[m["level_name"]] = CACHE / meta.parent.name

    first_trunk = next(iter(metas.values())) / "trunk"
    os.environ.setdefault("UEDCLI_PROJECT", str(first_trunk))
    from uedcli import trunk as TR
    from uedcli import rotation as ROT
    from uedcli.native import brush_marshal as BM
    from uedcli import movers as MV
    from spike_classindex import class_index
    ci = class_index()

    rows = []
    for name, cdir in sorted(metas.items()):
        lvl_dirs = list((cdir / "trunk/maps").iterdir())
        level, _ = TR.read_level(lvl_dirs[0])
        world, mover_total, mover_with_csgoper = [], 0, 0
        for n in level.order:
            a = level.actors[n]
            if a.brush is None:
                continue
            if BM._in_world_csg(a, ci):
                world.append((n, a))
            elif MV.is_mover(a, ci):
                mover_total += 1
                if any(k == "CsgOper" for k, _ in a.props):
                    mover_with_csgoper += 1
        c = Counter()
        oper = Counter()
        rc = Counter()
        for n, a in world:
            props = dict(a.props)
            oper[props.get("CsgOper", "<absent>")] += 1
            ms, ps = ROT.actor_main_scale(a), ROT.actor_post_scale(a)
            if not (ms.is_identity() and ps.is_identity()):
                c["scaled"] += 1
                if any(s.sheer_rate != 0 for s in (ms, ps)):
                    c["sheered"] += 1
                L = ROT.actor_linear(a)
                det = (L[0][0] * (L[1][1] * L[2][2] - L[1][2] * L[2][1])
                       - L[0][1] * (L[1][0] * L[2][2] - L[1][2] * L[2][0])
                       + L[0][2] * (L[1][0] * L[2][1] - L[1][1] * L[2][0]))
                if det < 0:
                    c["mirrored"] += 1
            rc[rot_class(ROT.actor_rotation_uu(a))] += 1
            try:
                pf = int(props.get("PolyFlags", "0"))
            except ValueError:
                pf = 0
            if pf & PF_SEMISOLID:
                c["semisolid"] += 1
            for p in a.brush.polys:
                if p.flags & PF_PORTAL:
                    c["portal_polys"] += 1
        rows.append((name, len(world), c, oper, rc, mover_total, mover_with_csgoper))

    hdr = ("level", "ncsg", "scaled", "sheer", "mirror", "semis", "portalP",
           "opAbsent", "rotC1", "rotCm", "rotNc1", "rotNcM", "movers", "movCsg")
    print(("{:28}" + "{:>8}" * (len(hdr) - 1)).format(*hdr))
    for name, ncsg, c, oper, rc, mt, mc in rows:
        print(("{:28}" + "{:>8}" * (len(hdr) - 1)).format(
            name, ncsg, c["scaled"], c["sheered"], c["mirrored"], c["semisolid"],
            c["portal_polys"], oper["<absent>"], rc["cardinal-1ax"], rc["cardinal-multi"],
            rc["noncard-1ax"], rc["noncard-2ax"] + rc["noncard-3ax"], mt, mc))
        odd = {k: v for k, v in oper.items() if k not in ("CSG_Add", "CSG_Subtract")}
        if odd:
            print(f"{'':28}  oper-other: {dict(odd)}")


if __name__ == "__main__":
    main()
