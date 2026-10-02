#!/usr/bin/env python3
"""Pre-repartition SOUP differential: native's post-merge soup vs the editor golden's `Model.Polys`.

This is the tool that localizes a CSG *fragment-set* divergence (as opposed to `node_diff.py`, which
compares the FINAL, post-repartition tree order).  The insight (measured 2026-07-17): the editor
golden `.dx`'s `Model.Polys` export is the editor's **post-merge, pre-`SplitPolyList` soup** — the
exact FPoly list `FindBestSplit` repartitions.  Native's equivalent is `bsp_merge_coplanars(
bsp_build_fpolys(model))`, exposed for the harness by the `UEDCLI_BSPCSG_SOUP_ONLY` env hook in
`bspcsg.rs` (it packs the merged soup as leaf nodes and returns before `bsp_build`).  Comparing the
two order-independent FACE multisets (plane + rounded vertex-set) answers: does our repartition INPUT
match the editor's?  If not, the repartition ROOT (and thus the whole `node_diff` prefix) cannot match
— fix the soup first.

Editor `Model.Polys` counts (measured): full castle 853 polys vs 1156 final nodes (post-merge < final,
confirming it is the SplitPolyList INPUT, not the final faces).  A face key is
`((nx,ny,nz,w rounded 1), sorted rounded-0 vertex tuples)`.

Usage:
  soup_cmp.py                 # full castle: native soup vs Test_Castle.dx Model.Polys
  soup_cmp.py --subsets A B   # per-N: native N-brush soup vs cached golden{N}.dx (castle-subset)
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli import trunk  # noqa: E402
from uedcli.native import materialize as M, umodel as UM  # noqa: E402
import uedcli_native  # noqa: E402
import utexture_decode as UT  # noqa: E402
import upolys_decode as UP  # noqa: E402

TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedcli/maps/foobar"
FULL_EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"
SUBSET = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle-subset"


def _face_key(nx, ny, nz, w, verts, ndp=1, ndv=0):
    pk = (round(nx, ndp), round(ny, ndp), round(nz, ndp), round(w, ndp))
    vk = tuple(sorted(tuple(round(c, ndv) for c in v) for v in verts))
    return (pk, vk)


def editor_soup(path):
    """(Counter face->mult, num_polys).  Editor golden Model.Polys == post-merge soup."""
    pkg = UT.load_package(path)
    pxs = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Polys"]
    if not pxs:
        return Counter(), 0
    pi = max(pxs, key=lambda i: pkg.exports[i]["ssize"])
    pe = pkg.exports[pi]
    polys, _ = UP.decode_upolys(pkg.buf, pe["soff"], pe["ssize"])
    c = Counter()
    for p in polys:
        n, b = p["normal"], p["base"]
        w = n[0] * b[0] + n[1] * b[1] + n[2] * b[2]
        c[_face_key(n[0], n[1], n[2], w, p["verts"])] += 1
    return c, len(polys)


def native_soup(bs):
    """(Counter face->mult, num_faces) — native post-merge soup via UEDCLI_BSPCSG_SOUP_ONLY."""
    os.environ["UEDCLI_BSPCSG_SOUP_ONLY"] = "1"
    try:
        m = uedcli_native.build_geometry_bspcsg(bs)
    finally:
        os.environ.pop("UEDCLI_BSPCSG_SOUP_ONLY", None)
    mm = UM.parse_model_body(uedcli_native.serialize_model(m), 0, len(uedcli_native.serialize_model(m)))
    c = Counter()
    for nd in mm.nodes:
        s = mm.surfs[nd.i_surf]
        base = mm.points[s.p_base]
        normal = mm.vectors[s.v_normal]
        w = normal[0] * base[0] + normal[1] * base[1] + normal[2] * base[2]
        verts = [mm.points[mm.verts[nd.i_vert_pool + k].i_vertex] for k in range(nd.num_vertices)]
        c[_face_key(normal[0], normal[1], normal[2], w, verts)] += 1
    return c, len(mm.nodes)


def _brushes(n=None):
    lvl, _ = trunk.read_level(Path(TRUNK))
    bo = [nm for nm in lvl.order if lvl.actors[nm].brush is not None]
    if n is not None:
        bo = bo[:n]
    return [M._build_brush_input(nm, lvl.actors[nm]) for nm in bo]


def _plane_only(counter):
    c = Counter()
    for (pk, _vk), n in counter.items():
        c[pk] += n
    return c


def _report(lbl, ef, ep, nf, nn):
    if ep == 0:
        print(f"{lbl:>5}  editor Polys EMPTY/corrupt (ep=0)")
        return
    sh = sum((ef & nf).values())
    oN = sum((nf - ef).values())
    oE = sum((ef - nf).values())
    top = ", ".join(f"{p}x{c}" for p, c in _plane_only(ef - nf).most_common(4))
    print(f"{lbl:>5} {ep:>5} {nn:>5} {sh:>5} {oN:>6} {oE:>6}  {top}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subsets", nargs=2, type=int, metavar=("A", "B"),
                    help="compare native N-brush soup vs cached golden{N}.dx for N in [A,B]")
    args = ap.parse_args()
    print(f"{'lbl':>5} {'edP':>5} {'natP':>5} {'shF':>5} {'onlyN':>6} {'onlyE':>6}  top-onlyE-planes")
    if args.subsets:
        for n in range(args.subsets[0], args.subsets[1] + 1):
            gp = f"{SUBSET}/golden{n}.dx"
            if not Path(gp).exists():
                print(f"{'N'+str(n):>5}  (no cached golden{n}.dx)")
                continue
            ef, ep = editor_soup(gp)
            nf, nn = native_soup(_brushes(n))
            _report(f"N{n}", ef, ep, nf, nn)
    else:
        ef, ep = editor_soup(FULL_EDITOR)
        nf, nn = native_soup(_brushes())
        _report("FULL", ef, ep, nf, nn)


if __name__ == "__main__":
    main()
