#!/usr/bin/env python3
"""Section 92 §3 — attribute native's real-level (UNATCO) `+82 surfs / +146 vectors` residual by
polyflag CLASS (solid / semisolid / notsolid / portal) and by a geometric surf-SET diff.

Key finding (reproduces §92's §3 table): the +82 net surfs splits ~+38 solid (structural CSG) + ~+46
semisolid (the 377-brush detail second layer), and is BIDIRECTIONAL (174 only-native / 92 only-editor),
i.e. NOT a pure under-merge.  Also confirms the surf/vector residual is basis-independent (both the
1x-`MAP REBUILD` and 2-step-OPTIMAL goldens carry 3616 surfs / 599 vectors).

Usage: surf_class_diff.py <native.dx> <golden.dx>
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
from uedcli.native import umodel as UM
from uedcli.native.pkg_write import parse_package

PF_NOTSOLID = 0x8
PF_SEMISOLID = 0x20
PF_PORTAL = 0x4000000


def load_model(path):
    pkg = parse_package(Path(path).read_bytes())
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def surf_class(pf):
    if pf & PF_PORTAL:
        return "portal"
    if pf & PF_SEMISOLID:
        return "semisolid"
    if pf & PF_NOTSOLID:
        return "notsolid"
    return "solid"


def surf_pf_hist(m, label):
    c = Counter(surf_class(s.poly_flags) for s in m.surfs)
    print(f"  {label}: total={len(m.surfs)}  {dict(c)}")
    return c


def surf_geokey(m, s, ndp=2, ndn=3):
    base = m.points[s.p_base]
    n = m.vectors[s.v_normal]
    return (tuple(round(c, ndn) for c in n),
            round(n[0] * base[0] + n[1] * base[1] + n[2] * base[2], ndp),  # plane offset
            surf_class(s.poly_flags))


def main():
    native = load_model(sys.argv[1] if len(sys.argv) > 1 else
                        str(ROOT / "_scratch/uedgolden/Native_unatco.dx"))
    golden = load_model(sys.argv[2] if len(sys.argv) > 2 else
                        str(ROOT / "_scratch/uedgolden/UEDGolden_unatco_world_zones.dx"))
    print("=== surf polyflags composition ===")
    cn = surf_pf_hist(native, "native")
    cg = surf_pf_hist(golden, "golden")
    print("  delta (native - golden):", {k: cn[k] - cg[k] for k in set(cn) | set(cg)})

    print("=== geometric surf-set diff (normal, plane-offset, class) ===")
    kn = Counter(surf_geokey(native, s) for s in native.surfs)
    kg = Counter(surf_geokey(golden, s) for s in golden.surfs)
    onlyN = kn - kg
    onlyE = kg - kn
    print(f"  shared surf-instances : {sum((kn & kg).values())}")
    print(f"  only-native           : {sum(onlyN.values())}")
    print(f"  only-editor           : {sum(onlyE.values())}")
    # break the divergence down by class
    print("  only-native by class:", dict(Counter(k[2] for k, c in onlyN.items() for _ in range(c))))
    print("  only-editor by class:", dict(Counter(k[2] for k, c in onlyE.items() for _ in range(c))))
    # top only-native planes
    print("  top only-native (normal,offset,class):")
    for k, c in onlyN.most_common(15):
        print(f"    {k}  x{c}")


if __name__ == "__main__":
    main()
