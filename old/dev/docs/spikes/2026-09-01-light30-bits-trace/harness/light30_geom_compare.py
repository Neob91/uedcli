#!/usr/bin/env python3
"""For each of Light30's 7 bad NYC Bar records/surfaces: compare NATIVE's own stored surf geometry
(p_base/v_normal/v_texture_u/v_texture_v -- the inputs `row_origins` builds the ray grid from)
against GOLDEN's, to test the hypothesis that native's real per-lumel bit mismatch (confirmed real by
`find_bad_light_records.py`, even though the ported `line_clear` algorithm is bit-perfect when fed
GOLDEN's own geometry, per `light30_offline_check.py`'s 100% in-range result) comes from a VALUE-level
geometry drift in the vectors feeding the ray grid, not from `line_clear` itself.

Usage: light30_geom_compare.py NATIVE.dx GOLDEN.dx --light NAME
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parents[1] / "2026-08-29-unatco-repart-live-diff/harness"
LIGHTH = HERE.parents[1] / "2026-08-27-native-light-apply-parity/harness"
sys.path.insert(0, str(OLD))
sys.path.insert(0, str(LIGHTH))
sys.path.insert(0, str(HERE.parents[4]))

import line_clear_v2_algorithm_check as V2  # noqa: E402
from lightparity import level_model, light_names, runs, planes, _load  # noqa: E402


def main() -> int:
    native_path, golden_path = sys.argv[1], sys.argv[2]
    target_light = None
    for i, a in enumerate(sys.argv):
        if a == "--light":
            target_light = sys.argv[i + 1]

    repo = str(HERE.parents[4])
    upackage, umodel = _load(repo)
    npkg, nm = level_model(upackage, umodel, native_path)
    epkg, em = level_model(upackage, umodel, golden_path)
    nnames, enames = light_names(npkg, nm), light_names(epkg, em)
    nruns, eruns = runs(nm, nnames), runs(em, enames)

    for k in range(len(em.light_map)):
        er = eruns.get(k, [])
        if target_light not in er:
            continue
        nr = nruns.get(k, [])
        nb = nm.light_map[k]
        eb = em.light_map[k]
        nsi, ns = V2.surf_for_record(nm, k)
        esi, es = V2.surf_for_record(em, k)
        print(f"\n=== record {k}  native_isurf={nsi} golden_isurf={esi} "
              f"run_match={nr == er} grid_match={(nb.u_size, nb.v_size) == (eb.u_size, eb.v_size)} "
              f"pan_match={(nb.pan) == (eb.pan)} "
              f"scale_match={(nb.u_scale, nb.v_scale) == (eb.u_scale, eb.v_scale)} ===")
        if ns is None or es is None:
            print("  surf lookup failed")
            continue
        np_base = nm.points[ns.p_base]
        ep_base = em.points[es.p_base]
        nv_n = nm.vectors[ns.v_normal]
        ev_n = em.vectors[es.v_normal]
        nv_u = nm.vectors[ns.v_texture_u]
        ev_u = em.vectors[es.v_texture_u]
        nv_v = nm.vectors[ns.v_texture_v]
        ev_v = em.vectors[es.v_texture_v]
        for label, nv, ev in (("p_base", np_base, ep_base), ("v_normal", nv_n, ev_n),
                              ("v_texture_u", nv_u, ev_u), ("v_texture_v", nv_v, ev_v)):
            match = nv == ev
            flag = "" if match else "  <-- DIFFERS"
            print(f"  {label:12} native={nv} golden={ev}{flag}")
        # Also compute the actual row_origin/u_step/v_step each side would use and the delta.
        n_bright = bool(ns.poly_flags & V2.PF_BRIGHT_CORNERS)
        e_bright = bool(es.poly_flags & V2.PF_BRIGHT_CORNERS)
        n_geo = V2.row_origins(nm, ns, nb, n_bright)
        e_geo = V2.row_origins(em, es, eb, e_bright)
        if n_geo and e_geo:
            for label, nv, ev in zip(("row_origin", "u_step", "v_step"), n_geo, e_geo):
                match = nv == ev
                flag = "" if match else "  <-- DIFFERS"
                print(f"  {label:12} native={nv} golden={ev}{flag}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
