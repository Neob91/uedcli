"""Hand-decode one v61 (original 1998/Gold Unreal) brush's private `UModel` body, printing every
field as it's read — the exploratory script that found the two format differences from the ver>61
(DX/UT99/UnrealGold-later) layout `uedcli/native/umodel.py` otherwise targets:

1. The `UPrimitive` prefix is 38 bytes, not 42 (`FSphere::operator<<` drops its `W` float entirely
   at `Ar.Ver()<=61` — a real engine bug, per the real v61 engine source, `fgsfdsfgs/UE1`
   `Engine/Inc/UnMath.h`).
2. `Vectors`/`Points`/`Nodes`/`Surfs`/`Verts`/`Polys` are each a separate `UDatabase`-subclass
   export, referenced from the `UModel` body by object ref (`fgsfdsfgs/UE1`
   `Engine/Inc/UnObj.h` + `Engine/Src/UnModel.cpp`) — not inline `TArray`s.

The production fix lives in `uedcli/native/umodel.py::parse_model_body` (a `version<=61` branch)
and `uedcli/mapimport.py::brush_of` (passes `pkg.version` through); this script is kept as the
byte-level trace that found it, not as a second decoder. `sweep_v61_brushes.py` (same dir) is the
corpus-wide check; `uedcli/tests/test_v61_model_decode.py` is the pinned regression.

Usage: `python3 decode_v61_model.py <path-to-.unr>` (from the repo root, or anywhere — sys.path is
fixed up below). Picks the first `Engine.Brush` actor it finds.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli.mapimport import _skip_state_frame
from uedcli.upackage import PT_OBJECT, load_package, read_compact_index, read_property_tags


def ci(buf, pos):
    return read_compact_index(buf, pos)


def find_first_brush_ref(pkg):
    for e in pkg.exports:
        if pkg.object_path(e["cls"]) != "Engine.Brush":
            continue
        start = _skip_state_frame(pkg, e)
        tags, _pos = read_property_tags(pkg, start, e["soff"] + e["ssize"])
        for tag in tags:
            if tag.name == "Brush" and tag.ptype == PT_OBJECT:
                ref, _ = read_compact_index(tag.raw, 0)
                return pkg.names[e["nm"]], ref
    raise SystemExit("no Engine.Brush actor with a Brush= ref found")


def main(path: str) -> None:
    pkg = load_package(path)
    print("package version", pkg.version)
    name, brush_ref = find_first_brush_ref(pkg)
    print("brush", name, "brush_ref", brush_ref)

    me = pkg.exports[brush_ref - 1]
    mstart = _skip_state_frame(pkg, me)
    end = me["soff"] + me["ssize"]
    buf = pkg.buf

    pos = mstart
    none_idx, pos = ci(buf, pos)
    pos += 25 + 12  # FBox + FSphere-as-FVector (v61: Ar.Ver()<=61 drops FSphere.W)
    assert pos - mstart == 38, pos - mstart
    print("prefix ok, pos", pos)

    refs = {}
    for n in ["vectors", "points", "nodes", "surfs", "verts", "polys"]:
        refs[n], pos = ci(buf, pos)
        print(n, "ref", refs[n])

    for arrname in ["light_map", "light_bits", "bounds", "leaf_hulls", "leaves", "lights"]:
        cnt, pos = ci(buf, pos)
        print(arrname, "count", cnt)

    leafzone_ref, pos = ci(buf, pos)
    leafleaf_ref, pos = ci(buf, pos)
    print("leafzone", leafzone_ref, "leafleaf", leafleaf_ref)

    root_outside = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    linked = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    print("root_outside", root_outside, "linked", linked)

    print("pos", pos, "end", end, "match:", pos == end)

    # Resolve each ref and print its own UDatabase header (property-list None + DbNum + DbMax) —
    # confirms each ref names a real, correctly-typed export, without recursively decoding it.
    for n in ["vectors", "points", "nodes", "surfs", "verts", "polys"]:
        ref = refs[n]
        if ref == 0:
            print(n, "ref=0 (none)")
            continue
        e = pkg.exports[ref - 1]
        estart = _skip_state_frame(pkg, e)
        eend = e["soff"] + e["ssize"]
        p = estart
        _none, p = ci(buf, p)
        dbnum, dbmax = struct.unpack_from("<ii", buf, p); p += 8
        print(f"{n}: export={pkg.names[e['nm']]} class={pkg.object_path(e['cls'])} "
              f"dbnum={dbnum} dbmax={dbmax} bodysize={eend - estart} "
              f"remaining_after_header={eend - p}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} <path-to-.unr>")
    main(sys.argv[1])
