#!/usr/bin/env python3
"""Section 92 §1 — profile a real level's brush composition (CsgOper split, DETAIL-brush count) and
run the order-independent face/plane multiset diff native-vs-golden.

Reproduces §92's §1 finding: UNATCO has 733 structural (519 Add / 214 Subtract) + **377 detail
(NotSolid|Semisolid)** brushes + 28 movers, vs the castle's 91 structural + 4 (flat, carve-nothing)
detail brushes — so a real level exercises the semisolid second incremental layer ~100x harder than
the castle can.

Usage: reallevel_brush_profile.py [native.dx] [golden.dx]   (defaults to the cached UNATCO builds)
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedctl import trunk
from uedctl.native import umodel as UM
from uedctl.native.pkg_write import parse_package
import soup_diff

TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/_scratch/unatco/uedctl/maps/unatco"
CASTLE_TRUNK_CANDS = [
    "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/_scratch/castle/uedctl/maps/castle",
    "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/maps/castle",
]

PF_NOTSOLID = 0x8
PF_SEMISOLID = 0x20
PF_PORTAL = 0x4000000


def load_model(path):
    pkg = parse_package(Path(path).read_bytes())
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def profile_trunk(trunk_dir, label):
    lvl, _ = trunk.read_level(Path(trunk_dir))
    opers = Counter()
    clses = Counter()
    detail = 0
    portal = 0
    nbrush = 0
    polycount = Counter()
    for name, a in lvl.actors.items():
        if a.brush is None or not a.brush.polys:
            continue
        polys = a.brush.polys
        nbrush += 1
        clses[a.cls] += 1
        props = dict(a.props)
        opers[props.get("CsgOper", "?")] += 1
        pf_or = 0
        for p in polys:
            pf_or |= getattr(p, "flags", 0) or 0
        if pf_or & (PF_NOTSOLID | PF_SEMISOLID):
            detail += 1
        if pf_or & PF_PORTAL:
            portal += 1
        polycount[len(polys)] += 1
    print(f"    classes: {dict(clses)}")
    print(f"--- {label}: {nbrush} brush-bearing actors ---")
    print(f"    CsgOper: {dict(opers)}")
    print(f"    detail (NotSolid|Semisolid): {detail}   portal-flag: {portal}")
    print(f"    poly-count histogram (top): {dict(polycount.most_common(8))}")
    return lvl


def main():
    for cand in CASTLE_TRUNK_CANDS:
        if Path(cand).exists():
            profile_trunk(cand, "CASTLE")
            break
    else:
        print("(castle trunk not found; skipping)")
    profile_trunk(TRUNK, "UNATCO")

    print()
    native = load_model(sys.argv[1] if len(sys.argv) > 1 else
                        str(ROOT / "_scratch/uedgolden/Native_unatco.dx"))
    golden = load_model(sys.argv[2] if len(sys.argv) > 2 else
                        str(ROOT / "_scratch/uedgolden/UEDGolden_unatco_world_zones.dx"))
    print(f"native surfs={len(native.surfs)} golden surfs={len(golden.surfs)}")
    soup_diff.report(native, golden)


if __name__ == "__main__":
    main()
