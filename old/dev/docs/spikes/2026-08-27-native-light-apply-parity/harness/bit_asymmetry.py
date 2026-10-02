#!/usr/bin/env python3
"""Which DIRECTION does the shadow bake err in, and is the error at shadow edges or in blobs?

Compares the per-(surface, light) bit-planes of two builds, aligning planes by LIGHT NAME inside each
`LightMap` record so a run-membership difference does not shift the comparison. Only bits `u <
USize` count: bits above `USize` in a row's last byte are padding neither side guarantees.

Reports
  * both lit / both dark / native-only-lit / editor-only-lit bit counts — a one-sided count says the
    bake is systematically over- or under-occluding rather than noisy,
  * for the disagreeing bits, whether they touch a bit the other side agrees is lit (a shadow EDGE,
    i.e. sub-lumel sampling) or sit in a solid blob (a line-of-sight rule difference),
  * the surfaces and surf `PolyFlags` carrying the loss.

Usage: bit_asymmetry.py NATIVE.dx EDITOR.dx [--top N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lightparity import _load, level_model, light_names, runs  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("native")
    ap.add_argument("editor")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()

    repo = str(Path(__file__).resolve().parents[5])
    upackage, umodel = _load(repo)
    npkg, nm = level_model(upackage, umodel, args.native)
    epkg, em = level_model(upackage, umodel, args.editor)
    nr, er = runs(nm, light_names(npkg, nm)), runs(em, light_names(epkg, em))
    rec_surf = {s.i_light_map: si for si, s in enumerate(em.surfs) if s.i_light_map >= 0}

    both_on = both_off = only_n = only_e = 0
    edge = blob = 0
    planes = ident = 0
    lost_by_surf: dict[int, int] = {}
    lost_by_pf: dict[int, int] = {}
    for k in range(min(len(nm.light_map), len(em.light_map))):
        a, b = nm.light_map[k], em.light_map[k]
        if (a.u_size, a.v_size) != (b.u_size, b.v_size):
            continue
        rb = (a.u_size + 7) // 8
        per = rb * a.v_size
        nmap = {ln: i for i, ln in enumerate(nr[k])}
        emap = {ln: i for i, ln in enumerate(er[k])}
        for ln in set(nmap) & set(emap):
            pa = bytes(nm.light_bits[a.data_offset + nmap[ln] * per:
                                     a.data_offset + (nmap[ln] + 1) * per])
            pb = bytes(em.light_bits[b.data_offset + emap[ln] * per:
                                     b.data_offset + (emap[ln] + 1) * per])
            if len(pa) < per or len(pb) < per:
                continue
            planes += 1

            def bit(p, u, v):
                return (p[v * rb + (u >> 3)] >> (u & 7)) & 1

            diff = []
            for v in range(a.v_size):
                for u in range(a.u_size):
                    x, y = bit(pa, u, v), bit(pb, u, v)
                    if x and y:
                        both_on += 1
                    elif x:
                        only_n += 1
                        diff.append((u, v, "n"))
                    elif y:
                        only_e += 1
                        diff.append((u, v, "e"))
                    else:
                        both_off += 1
            if not diff:
                ident += 1
                continue
            si = rec_surf.get(k, -1)
            lost = sum(1 for d in diff if d[2] == "e")
            if lost:
                lost_by_surf[si] = lost_by_surf.get(si, 0) + lost
                pf = em.surfs[si].poly_flags if si >= 0 else 0
                lost_by_pf[pf] = lost_by_pf.get(pf, 0) + lost
            for u, v, who in diff:
                agreed = pa if who == "e" else pb
                touching = any(bit(agreed, u + du, v + dv)
                               for du, dv in ((1, 0), (-1, 0), (0, 1), (0, -1))
                               if 0 <= u + du < a.u_size and 0 <= v + dv < a.v_size)
                if touching:
                    edge += 1
                else:
                    blob += 1

    tot = both_on + both_off + only_n + only_e
    print(f"planes compared {planes}, byte-identical {ident} "
          f"({100.0 * ident / (planes or 1):.1f}%)")
    print(f"lumel bits {tot}: both lit {100.0 * both_on / tot:.1f}%, "
          f"both dark {100.0 * both_off / tot:.1f}%")
    print(f"  native ONLY lit (native too permissive): {only_n} "
          f"({100.0 * only_n / tot:.3f}%)")
    print(f"  editor ONLY lit (native too occluded):   {only_e} "
          f"({100.0 * only_e / tot:.3f}%)")
    print(f"  disagreeing bits touching an agreed-lit neighbour (shadow edge): {edge}")
    print(f"  disagreeing bits in a blob (line-of-sight rule):                 {blob}")
    print(f"\nsurfaces losing lumels: {len(lost_by_surf)}; top {args.top}: "
          f"{sorted(lost_by_surf.items(), key=lambda kv: -kv[1])[:args.top]}")
    print(f"loss by surf PolyFlags: "
          f"{ {hex(k): v for k, v in sorted(lost_by_pf.items(), key=lambda kv: -kv[1])[:6]} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
