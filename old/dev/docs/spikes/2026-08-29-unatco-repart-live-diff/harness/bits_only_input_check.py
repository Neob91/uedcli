#!/usr/bin/env python3
"""Offline cross-check: for `LightMap` records where run/grid/pan/scale all match but shadow bits
don't (the "bits-only" bucket, `lightparity_buckets.py`), are the surface's own Base/TextureU/
TextureV/Normal (`Points`/`Vectors` pool entries) ALREADY bit-identical between native and the
editor golden?

Motivation (`native-light-apply-bake-where-it-stands-and`'s gap 2, "per-lumel shadow-ray precision"):
if the inputs to `lumel_axes` are already bit-identical, and `lumel_axes` is a pure function (proven
bit-identical to the editor's own `FCoords::Inverse` — see `lumel_axes_live_check.py` + the findings
ledger), then a surviving bits-only divergence for such a record CANNOT be `lumel_axes`'s fault — it
must be downstream (most likely the shadow ray's actual `linecheck::line_clear` BSP test).

Usage: bits_only_input_check.py NATIVE.dx EDITOR.dx [--limit N]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026-08-27-native-light-apply-parity/harness"))
from lightparity import _load, level_model, light_names, runs, planes  # noqa: E402


def surf_for_record(model, k):
    for si, s in enumerate(model.surfs):
        if s.i_light_map == k:
            return si, s
    return None, None


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    native, editor = sys.argv[1], sys.argv[2]
    limit = 20
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    repo = str(Path(__file__).resolve().parents[5])
    upackage, umodel = _load(repo)
    npkg, nm = level_model(upackage, umodel, native)
    epkg, em = level_model(upackage, umodel, editor)
    nruns = runs(nm, light_names(npkg, nm))
    eruns = runs(em, light_names(epkg, em))

    common = min(len(nm.light_map), len(em.light_map))
    found = all_eq = 0
    for k in range(common):
        a, b = nm.light_map[k], em.light_map[k]
        nr, er = nruns[k], eruns[k]
        if a.u_size != b.u_size or a.v_size != b.v_size or nr != er:
            continue
        if a.pan != b.pan or a.u_scale != b.u_scale or a.v_scale != b.v_scale:
            continue
        if planes(nm, a, len(nr)) == planes(em, b, len(er)):
            continue  # fully identical, not "bits-only"

        nsi, ns = surf_for_record(nm, k)
        esi, es = surf_for_record(em, k)
        if ns is None or es is None:
            continue
        nbase, ebase = nm.points[ns.p_base], em.points[es.p_base]
        ntu, etu = nm.vectors[ns.v_texture_u], em.vectors[es.v_texture_u]
        ntv, etv = nm.vectors[ns.v_texture_v], em.vectors[es.v_texture_v]
        nnorm, enorm = nm.vectors[ns.v_normal], em.vectors[es.v_normal]
        eqs = {"base": nbase == ebase, "tu": ntu == etu, "tv": ntv == etv, "norm": nnorm == enorm}
        found += 1
        all_eq += all(eqs.values())
        print(f"record {k}: surf n={nsi} e={esi}  {eqs}")
        for name, (nv, ev) in (("base", (nbase, ebase)), ("tu", (ntu, etu)),
                                ("tv", (ntv, etv)), ("norm", (nnorm, enorm))):
            if nv != ev:
                print(f"   {name} native={nv} editor={ev}")
        if found >= limit:
            break
    print(f"checked {found} bits-only records, {all_eq} with ALL FOUR inputs already bit-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
