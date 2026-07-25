#!/usr/bin/env python3
"""Validate the byte-verified repartition FindBestSplit params (Balance=12, PortalBias=0, Opt=GOOD
stride NumPolys/10) by reconstructing the editor's OWN repartition soup (Model.Polys export) for a
subset golden and re-running a faithful SplitPolyList on it — the result should equal the editor
golden's node planes (in order).  This proves the tree-builder is faithful GIVEN the editor's soup
and the corrected params, isolating any remaining gap to the CSG soup (bspBrushCSG).

Usage: validate_params.py N [balance] [portal_bias] [opt]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

import utexture_decode as UT
import upolys_decode as UP
import fbs_score as F
import spl_reorder as SP
import subset_diff as S


def editor_soup(golden_path):
    """Reconstruct the editor's repartition soup (Model.Polys) in order from a golden .dx."""
    pkg = UT.load_package(str(golden_path))
    # the level Model's Polys = the largest Polys export.
    polyexps = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Polys"]
    best = max(polyexps, key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[best]
    polys, ok = UP.decode_upolys(pkg.buf, e["soff"], e["ssize"])
    return [F.Poly(tuple(p["base"]), tuple(p["normal"]), [tuple(v) for v in p["verts"]],
                   p["poly_flags"], tag=f"iL{p['i_link']}") for p in polys], ok


def run(N, balance=12, portal_bias=0, opt=1):
    soup, ok = editor_soup(S.golden_path(N))
    ed = S.load_editor_model(S.golden_path(N))
    ed_planes = [tuple(round(c, 1) for c in n.plane) for n in ed.nodes]

    orig = F.find_best_split
    F.find_best_split = lambda ps, verbose=False: orig(ps, balance=balance, portal_bias=portal_bias, opt=opt)
    nodes = []
    SP.split_poly_list(list(soup), nodes)
    F.find_best_split = orig
    got = [tuple(round(c, 1) for c in n.plane) for n in nodes]

    match = got == ed_planes
    print(f"N={N}: soup={len(soup)} (eof_ok={ok})  editor_golden={len(ed_planes)} nodes  "
          f"SplitPolyList(Balance={balance},PB={portal_bias},opt={opt})={len(got)} nodes  "
          f"{'MATCH ✓' if match else 'DIFFER'}")
    if not match:
        # first mismatch index
        for i in range(min(len(got), len(ed_planes))):
            if got[i] != ed_planes[i]:
                print(f"    first plane mismatch @ node[{i}]: got={got[i]} editor={ed_planes[i]}")
                break
        else:
            print(f"    prefix matches; length differs (got {len(got)} vs editor {len(ed_planes)})")
    return match


if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    bal = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    pb = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    opt = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    run(N, bal, pb, opt)
