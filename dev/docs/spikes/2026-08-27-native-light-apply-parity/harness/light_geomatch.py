#!/usr/bin/env python3
"""Per-surface lighting compare that does NOT need the two BSP trees to agree.

Comparing `LightMap` record *k* against record *k* only works when both sides split the world into
the same surfaces. When the surf pools differ (native 3616 vs an editor build's 3705 on UNATCO), a
positional compare reports every record as wrong and says nothing about the bake. This matches
surfaces by GEOMETRY instead — same plane (unit-normal `cos > 0.999`, plane distance <= 2 uu), same
owning-brush count of vertices ignored, nearest centroid — the method spike section 20 §19 used, and
then compares only the bake outputs of matched pairs:

  * the grid descriptor (`USize`/`VSize`/`Pan`/`UScale`/`VScale`),
  * the light RUN (as export names, so object-ref renumbering is not a difference),
  * the packed shadow bits, when grid and run length agree.

A surface's world vertices come from its BSP nodes' vert pools, so a surface split differently on
the two sides has a different centroid and simply does not match — those are reported as unmatched
rather than silently paired.

Usage: light_geomatch.py NATIVE.dx EDITOR.dx [--pairs N]
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lightparity import _load, level_model, light_names, planes, runs  # noqa: E402


def surf_geometry(model):
    """`surf index -> (unit normal, plane distance, centroid, vertex count)` from its node verts."""
    acc = [[0.0, 0.0, 0.0, 0] for _ in model.surfs]
    for n in model.nodes:
        if n.i_surf < 0 or n.i_surf >= len(model.surfs):
            continue
        a = acc[n.i_surf]
        for k in range(n.num_vertices):
            v = model.points[model.verts[n.i_vert_pool + k].i_vertex]
            a[0] += v[0]
            a[1] += v[1]
            a[2] += v[2]
            a[3] += 1
    out = {}
    for si, s in enumerate(model.surfs):
        cnt = acc[si][3]
        if not cnt:
            continue
        nx, ny, nz = model.vectors[s.v_normal]
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        nrm = (nx / ln, ny / ln, nz / ln)
        base = model.points[s.p_base]
        dist = nrm[0] * base[0] + nrm[1] * base[1] + nrm[2] * base[2]
        cen = (acc[si][0] / cnt, acc[si][1] / cnt, acc[si][2] / cnt)
        out[si] = (nrm, dist, cen, cnt)
    return out


def match(ng, eg, *, cos_min=0.999, dist_tol=2.0, cen_tol=48.0):
    """Pair native surfs to editor surfs by plane + nearest centroid. Greedy, one-to-one."""
    # Bucket editor surfs by a coarse quantized plane so the search is not O(n^2) over everything.
    buckets: dict[tuple, list[int]] = {}
    for ei, (nrm, dist, cen, _c) in eg.items():
        key = (round(nrm[0], 1), round(nrm[1], 1), round(nrm[2], 1), round(dist / 8.0))
        buckets.setdefault(key, []).append(ei)
    taken, pairs = set(), {}
    for ni, (nrm, dist, cen, _c) in ng.items():
        best, bestd = None, cen_tol
        for dx in (-1, 0, 1):
            for kx in (round(nrm[0], 1),):
                key = (kx, round(nrm[1], 1), round(nrm[2], 1), round(dist / 8.0) + dx)
                for ei in buckets.get(key, ()):
                    if ei in taken:
                        continue
                    enrm, edist, ecen, _ = eg[ei]
                    if (nrm[0] * enrm[0] + nrm[1] * enrm[1] + nrm[2] * enrm[2]) <= cos_min:
                        continue
                    if abs(dist - edist) > dist_tol:
                        continue
                    d = math.dist(cen, ecen)
                    if d < bestd:
                        best, bestd = ei, d
        if best is not None:
            taken.add(best)
            pairs[ni] = best
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("native")
    ap.add_argument("editor")
    ap.add_argument("--pairs", type=int, default=10, help="diverging pairs to print (default 10)")
    args = ap.parse_args()

    repo = str(Path(__file__).resolve().parents[5])
    upackage, umodel = _load(repo)
    npkg, nm = level_model(upackage, umodel, args.native)
    epkg, em = level_model(upackage, umodel, args.editor)
    nnames, enames = light_names(npkg, nm), light_names(epkg, em)
    nruns, eruns = runs(nm, nnames), runs(em, enames)

    ng, eg = surf_geometry(nm), surf_geometry(em)
    pairs = match(ng, eg)
    print(f"native surfs with geometry {len(ng)}, editor {len(eg)}, matched {len(pairs)}")

    stats = dict(both_lightmapped=0, only_native_lm=0, only_editor_lm=0, neither=0,
                 grid_ok=0, pan_ok=0, scale_ok=0, run_ok=0, bits_ok=0, cmp_bits=0,
                 both_dark=0, native_dark_editor_lit=0, native_lit_editor_dark=0)
    same_bits = tot_bits = 0
    run_delta = 0
    detail = []
    for ni, ei in sorted(pairs.items()):
        nlm, elm = nm.surfs[ni].i_light_map, em.surfs[ei].i_light_map
        if nlm < 0 and elm < 0:
            stats["neither"] += 1
            continue
        if nlm < 0:
            stats["only_editor_lm"] += 1
            continue
        if elm < 0:
            stats["only_native_lm"] += 1
            continue
        stats["both_lightmapped"] += 1
        a, b = nm.light_map[nlm], em.light_map[elm]
        nr, er = nruns[nlm], eruns[elm]
        run_delta += len(nr) - len(er)
        grid = (a.u_size, a.v_size) == (b.u_size, b.v_size)
        stats["grid_ok"] += grid
        stats["pan_ok"] += (a.pan == b.pan)
        stats["scale_ok"] += ((a.u_scale, a.v_scale) == (b.u_scale, b.v_scale))
        stats["run_ok"] += (sorted(nr) == sorted(er))
        pa, pb = planes(nm, a, len(nr)), planes(em, b, len(er))
        if not nr and not er:
            stats["both_dark"] += 1
        elif not any(pa) and any(pb):
            stats["native_dark_editor_lit"] += 1
        elif any(pa) and not any(pb):
            stats["native_lit_editor_dark"] += 1
        if grid and len(nr) == len(er):
            stats["cmp_bits"] += 1
            stats["bits_ok"] += (pa == pb)
            for x, y in zip(pa, pb):
                same_bits += 8 - bin(x ^ y).count("1")
                tot_bits += 8
        if (not grid or sorted(nr) != sorted(er)) and len(detail) < args.pairs:
            detail.append((ni, ei, a, b, nr, er))

    n = stats["both_lightmapped"] or 1
    print(f"\nboth lightmapped: {stats['both_lightmapped']}   "
          f"only native: {stats['only_native_lm']}   only editor: {stats['only_editor_lm']}   "
          f"neither: {stats['neither']}")
    for k in ("grid_ok", "pan_ok", "scale_ok", "run_ok"):
        print(f"  {k:9} {stats[k]:6}/{stats['both_lightmapped']} = "
              f"{100.0 * stats[k] / n:.1f}%")
    print(f"  run entries: native - editor = {run_delta:+d} over matched pairs")
    print(f"  dark/lit: both dark {stats['both_dark']}, native-dark-editor-lit "
          f"{stats['native_dark_editor_lit']}, native-lit-editor-dark "
          f"{stats['native_lit_editor_dark']}")
    if stats["cmp_bits"]:
        print(f"  bit-comparable pairs (grid+run len equal): {stats['cmp_bits']}, "
              f"byte-identical planes {stats['bits_ok']} "
              f"({100.0 * stats['bits_ok'] / stats['cmp_bits']:.1f}%)")
        print(f"  shadow bits equal: {same_bits}/{tot_bits} = "
              f"{100.0 * same_bits / tot_bits:.2f}%")

    for ni, ei, a, b, nr, er in detail:
        print(f"\n  native surf {ni} <-> editor surf {ei}")
        print(f"     native u={a.u_size} v={a.v_size} pan={a.pan} us={a.u_scale!r} "
              f"vs={a.v_scale!r}\n            run={sorted(nr)}")
        print(f"     editor u={b.u_size} v={b.v_size} pan={b.pan} us={b.u_scale!r} "
              f"vs={b.v_scale!r}\n            run={sorted(er)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
