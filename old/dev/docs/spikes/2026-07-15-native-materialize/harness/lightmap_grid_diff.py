#!/usr/bin/env python3
"""Per-record LightMap (FLightMapIndex) diff: native vs editor golden, aligned by walk order.

The `LightMap` array is emitted in the same editor BSP-tree-walk order on both sides (spike §20
§21), so record k on native corresponds to record k on the editor golden = the SAME lit surface.
This tool decodes both and compares, per record: UClamp (u_size), VClamp (v_size), Pan, and the
u/v texture scales. It reports how many records match each field exactly and the ±delta histogram
of the grid-dim divergence (the ~134 records off by ±1 that cascade into LightBits).

It also cross-links each record to its surf's geometry (via iLightMap) so a diverging record can be
inspected: poly_flags (=> lumel scale), texture-space extent, etc.

Usage:
  .venv/bin/python .../harness/lightmap_grid_diff.py [NATIVE.dx] [EDITOR.dx] [--dump N]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))

from uedcli.native import umodel as UM  # noqa: E402
from uedcli.native.pkg_write import parse_package  # noqa: E402

NATIVE = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/gtruth/NativeCastle.dx"
EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"
PF_NO_LIGHTMAP = 0x0040_0081


def load_model(path: str) -> UM.Model:
    pkg = parse_package(Path(path).read_bytes())
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def record_to_surf(m: UM.Model) -> list[int]:
    d = {s.i_light_map: si for si, s in enumerate(m.surfs) if s.i_light_map >= 0}
    return [d[k] for k in range(len(m.light_map))]


def lumel_scale(pf: int) -> float:
    HI, LO = 0x0080_0000, 0x0000_8000
    if (pf & (HI | LO)) == (HI | LO):
        return 128.0
    if pf & HI:
        return 16.0
    if pf & LO:
        return 64.0
    return 32.0


def surf_extent(m: UM.Model, si: int):
    """Return (umin,umax,vmin,vmax) in base-relative texture space for surf si, or None."""
    s = m.surfs[si]
    tu = m.vectors[s.v_texture_u]
    tv = m.vectors[s.v_texture_v]
    base = m.points[s.p_base]
    bu = base[0]*tu[0] + base[1]*tu[1] + base[2]*tu[2]
    bv = base[0]*tv[0] + base[1]*tv[1] + base[2]*tv[2]
    # gather surf verts from nodes referencing this surf
    pts = []
    for n in m.nodes:
        if n.i_surf == si:
            for k in range(n.num_vertices):
                vi = m.verts[n.i_vert_pool + k].i_vertex
                pts.append(m.points[vi])
    if not pts:
        return None
    us = [p[0]*tu[0]+p[1]*tu[1]+p[2]*tu[2]-bu for p in pts]
    vs = [p[0]*tv[0]+p[1]*tv[1]+p[2]*tv[2]-bv for p in pts]
    return (min(us), max(us), min(vs), max(vs), lumel_scale(s.poly_flags), s.poly_flags)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("native", nargs="?", default=NATIVE)
    ap.add_argument("editor", nargs="?", default=EDITOR)
    ap.add_argument("--dump", type=int, default=0, help="dump first N diverging records in detail")
    args = ap.parse_args()

    mn = load_model(args.native)
    me = load_model(args.editor)
    print(f"native records={len(mn.light_map)}  editor records={len(me.light_map)}")
    n = min(len(mn.light_map), len(me.light_map))

    r2s_n = record_to_surf(mn)
    r2s_e = record_to_surf(me)

    u_match = v_match = pan_match = uscale_match = vscale_match = both_grid = 0
    du_hist: Counter = Counter()
    dv_hist: Counter = Counter()
    diverging = []
    for k in range(n):
        a = mn.light_map[k]
        b = me.light_map[k]
        du = a.u_size - b.u_size
        dv = a.v_size - b.v_size
        du_hist[du] += 1
        dv_hist[dv] += 1
        if du == 0:
            u_match += 1
        if dv == 0:
            v_match += 1
        if du == 0 and dv == 0:
            both_grid += 1
        else:
            diverging.append(k)
        # pan/scale exact float compare
        if a.pan == b.pan:
            pan_match += 1
        if a.u_scale == b.u_scale:
            uscale_match += 1
        if a.v_scale == b.v_scale:
            vscale_match += 1

    print(f"\n=== grid dims (aligned by walk order, {n} records) ===")
    print(f"  UClamp (u_size) exact: {u_match}/{n}")
    print(f"  VClamp (v_size) exact: {v_match}/{n}")
    print(f"  BOTH grid dims exact : {both_grid}/{n}   (diverging: {n-both_grid})")
    print(f"  du = native-editor histogram: {dict(sorted(du_hist.items()))}")
    print(f"  dv = native-editor histogram: {dict(sorted(dv_hist.items()))}")
    print(f"\n=== pan / scale (exact float bits) ===")
    print(f"  Pan     exact: {pan_match}/{n}")
    print(f"  u_scale exact: {uscale_match}/{n}")
    print(f"  v_scale exact: {vscale_match}/{n}")

    if args.dump:
        print(f"\n=== first {args.dump} diverging records (grid dims) ===")
        for k in diverging[:args.dump]:
            a = mn.light_map[k]
            b = me.light_map[k]
            sn = r2s_n[k]
            se = r2s_e[k]
            en = surf_extent(mn, sn)
            ee = surf_extent(me, se)
            print(f"  rec {k}: native surf {sn} u/v={a.u_size}/{a.v_size} scale={a.u_scale:.5f}/{a.v_scale:.5f} pan=({a.pan[0]:.4f},{a.pan[1]:.4f})")
            print(f"          editor surf {se} u/v={b.u_size}/{b.v_size} scale={b.u_scale:.5f}/{b.v_scale:.5f} pan=({b.pan[0]:.4f},{b.pan[1]:.4f})")
            if en:
                print(f"          nat extent u[{en[0]:.4f},{en[1]:.4f}] v[{en[2]:.4f},{en[3]:.4f}] lscale={en[4]} pf={en[5]:#x}")
            if ee:
                print(f"          ed  extent u[{ee[0]:.4f},{ee[1]:.4f}] v[{ee[2]:.4f},{ee[3]:.4f}] lscale={ee[4]} pf={ee[5]:#x}")


if __name__ == "__main__":
    main()
