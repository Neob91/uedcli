#!/usr/bin/env python3
"""Characterise the (surface, light) pairs native gets wrong: is the divergence a RADIUS rule, a ZONE
rule, or a line-of-sight rule?

For every per-surface light run in both maps, classify each pair by
  * `d / worldRadius` where `worldRadius = (LightRadius + 1) * 25` and `d` is the light-to-surface
    distance (to the nearest surf vertex and to the centroid),
  * whether the light's BSP zone equals the surface's zone, and whether the two zones are marked
    connected in the built `Zones` connectivity mask,
and print the distributions for: pairs BOTH sides list, pairs only NATIVE lists, pairs only the
EDITOR lists. A rule native is missing shows up as a clean separation between those groups.

Light locations and radii come from the trunk (`gather_lights`), so this needs the trunk that both
maps were built from.

Usage: pair_geometry.py NATIVE.dx EDITOR.dx --trunk <trunk-dir>
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lightparity import _load, level_model, light_names, runs  # noqa: E402


def point_zone(model, p):
    """PointRegion descent: the zone number at world point `p` (0 = solid/outside)."""
    if not model.nodes:
        return 0
    ni = 0
    while True:
        n = model.nodes[ni]
        nx, ny, nz, w = n.plane
        side = 1 if (nx * p[0] + ny * p[1] + nz * p[2] - w) >= 0 else 0
        child = n.i_back if side == 1 else n.i_front
        if child == -1:
            lf = n.i_leaf[side]
            return model.leaves[lf].i_zone if 0 <= lf < len(model.leaves) else 0
        ni = child


def surf_verts(model):
    out = [[] for _ in model.surfs]
    for n in model.nodes:
        if 0 <= n.i_surf < len(model.surfs):
            for k in range(n.num_vertices):
                out[n.i_surf].append(model.points[model.verts[n.i_vert_pool + k].i_vertex])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("native")
    ap.add_argument("editor")
    ap.add_argument("--trunk", required=True)
    args = ap.parse_args()

    repo = str(Path(__file__).resolve().parents[5])
    upackage, umodel = _load(repo)
    from uedcli import config, trunk as trunkmod
    from uedcli.classdefaults import ClassDefaults
    from uedcli.native.materialize import gather_lights
    from uedcli.packages import schema_resolver

    trunk_dir = Path(args.trunk).resolve()
    project = config.load_project(str(trunk_dir.parent.parent))
    lights = {n: (loc, r) for n, loc, r in gather_lights(
        trunkmod.read_level(trunk_dir)[0],
        defaults=ClassDefaults(schema_resolver(project, config.load_user_config())))}

    npkg, nm = level_model(upackage, umodel, args.native)
    epkg, em = level_model(upackage, umodel, args.editor)
    nruns, eruns = runs(nm, light_names(npkg, nm)), runs(em, light_names(epkg, em))
    everts = surf_verts(em)
    # Which surf each record belongs to, on the EDITOR side (the geometry reference).
    rec_surf = {s.i_light_map: si for si, s in enumerate(em.surfs) if s.i_light_map >= 0}
    lzone = {n: point_zone(em, loc) for n, (loc, _r) in lights.items()}

    groups = {"both": [], "native only": [], "editor only": []}
    for k in range(min(len(nm.light_map), len(em.light_map))):
        si = rec_surf.get(k)
        if si is None or not everts[si]:
            continue
        vs = everts[si]
        cen = [sum(v[i] for v in vs) / len(vs) for i in range(3)]
        szone = point_zone(em, [c + em.vectors[em.surfs[si].v_normal][i] * 1.0
                                for i, c in enumerate(cen)])
        a, b = set(nruns[k]), set(eruns[k])
        for name, g in (("both", a & b), ("native only", a - b), ("editor only", b - a)):
            for ln in g:
                if ln not in lights:
                    continue
                loc, radius = lights[ln]
                wr = (radius + 1) * 25.0
                dc = math.dist(cen, loc)
                dv = min(math.dist(v, loc) for v in vs)
                groups[name].append((dc / wr, dv / wr, lzone[ln], szone))

    print(f"{'group':13} {'pairs':>7} {'d_cen/R median':>15} {'d_vert/R median':>16} "
          f"{'zone equal':>11} {'light zone 0':>13}")
    for name, rows in groups.items():
        if not rows:
            continue
        dc = sorted(r[0] for r in rows)
        dv = sorted(r[1] for r in rows)
        eq = sum(1 for r in rows if r[2] == r[3])
        z0 = sum(1 for r in rows if r[2] == 0)
        print(f"{name:13} {len(rows):7} {dc[len(dc) // 2]:15.3f} {dv[len(dv) // 2]:16.3f} "
              f"{100.0 * eq / len(rows):10.1f}% {100.0 * z0 / len(rows):12.1f}%")

    print("\nd_vert/R decile histogram (fraction of the group's pairs):")
    print(f"  {'group':13} " + " ".join(f"{i / 10:.1f}" for i in range(1, 13)))
    for name, rows in groups.items():
        if not rows:
            continue
        buckets = [0] * 12
        for _dc, d, _lz, _sz in rows:
            buckets[min(11, int(d * 10))] += 1
        print(f"  {name:13} " + " ".join(f"{100.0 * b / len(rows):3.0f}" for b in buckets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
