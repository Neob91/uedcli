#!/usr/bin/env python3
"""List concrete zone-crossing (surf,light) pairs the editor lists but native misses.

Extends `pair_geometry.py`'s classification (native/editor run diff, per-pair light/surf BSP zone) to
print the CONCRETE identity of each "editor only" pair whose light zone != surf zone, plus the
light's world Location — everything `visible_surfs.rs`'s `UEDCLIVISGATE_TRACE_SURF`/`_LOC` probe
needs to reproduce one live.

Usage: zone_crossing_pairs.py NATIVE.dx EDITOR.dx --trunk <trunk-dir> [--limit N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026-08-27-native-light-apply-parity/harness"))
from lightparity import _load, level_model, light_names, runs  # noqa: E402
from pair_geometry import point_zone, surf_verts  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("native")
    ap.add_argument("editor")
    ap.add_argument("--trunk", required=True)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    repo = str(Path(__file__).resolve().parents[5])
    upackage, umodel = _load(repo)
    from uedcli import config, trunk as trunkmod
    from uedcli.classdefaults import ClassDefaults
    from uedcli.native.materialize import gather_lights
    from uedcli.packages import schema_resolver

    trunk_dir = Path(args.trunk).resolve()
    project = config.load_project(str(trunk_dir.parent.parent))
    lights = {n: (loc, r) for n, loc, r, _special in gather_lights(
        trunkmod.read_level(trunk_dir)[0],
        defaults=ClassDefaults(schema_resolver(project, config.load_user_config())))}

    npkg, nm = level_model(upackage, umodel, args.native)
    epkg, em = level_model(upackage, umodel, args.editor)
    nruns, eruns = runs(nm, light_names(npkg, nm)), runs(em, light_names(epkg, em))
    everts = surf_verts(em)
    rec_surf = {s.i_light_map: si for si, s in enumerate(em.surfs) if s.i_light_map >= 0}
    lzone = {n: point_zone(em, loc) for n, (loc, _r) in lights.items()}

    found = 0
    for k in range(min(len(nm.light_map), len(em.light_map))):
        si = rec_surf.get(k)
        if si is None or not everts[si]:
            continue
        vs = everts[si]
        cen = [sum(v[i] for v in vs) / len(vs) for i in range(3)]
        szone = point_zone(em, [c + em.vectors[em.surfs[si].v_normal][i] * 1.0
                                for i, c in enumerate(cen)])
        a, b = set(nruns[k]), set(eruns[k])
        for ln in sorted(b - a):
            if ln not in lights:
                continue
            loc, _r = lights[ln]
            lz = lzone[ln]
            if lz == szone:
                continue
            print(f"record={k} surf={si} light={ln} light_zone={lz} surf_zone={szone} "
                  f"light_loc={loc[0]:.4f},{loc[1]:.4f},{loc[2]:.4f} surf_centroid={cen}")
            found += 1
            if found >= args.limit:
                return 0
    if found == 0:
        print("no zone-crossing editor-only pairs found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
