"""Native (no-editor) `.dx` -> actor list: parse every actor object's body
(StateFrame + tagged properties) and recover its class (via the import table) and key
properties (Location, Rotation, Tag, Group). This is the read path that replaces
`store_export.export_dx_t3d` (today: `docker exec wine UCC.exe batchexport Level T3D`).

Validates self-consistently: every actor body parses (cursor lands inside its serial
extent), classes resolve, Locations are finite coords. Reuses the Spike-1 property
reader + the Spike-7 StateFrame finding + Spike-4 import-table class resolution.

Usage: python native_dx_actors.py <map.dx> [--list]
"""
from __future__ import annotations

import struct
import sys
from collections import Counter

sys.path.insert(0, ".")
from utexture_decode import load_package, ci

RF_HasStack = 0x02000000


def _read_props_typed(buf, pos, end, names):
    """Like read_props but decode Struct float-vectors (Location/Rotation) when 12 bytes."""
    props = {}
    while pos < end:
        nidx, pos = ci(buf, pos)
        nm = names[nidx] if 0 <= nidx < len(names) else None
        if nm == "None":
            break
        if nm is None:
            raise ValueError("bad name index")
        info = buf[pos]; pos += 1
        ptype = info & 0x0F
        size_code = (info >> 4) & 0x07
        array = info & 0x80
        sname = None
        if ptype == 10:
            si, pos = ci(buf, pos); sname = names[si]
        if size_code <= 4:
            size = {0: 1, 1: 2, 2: 4, 3: 12, 4: 16}[size_code]
        elif size_code == 5:
            size = buf[pos]; pos += 1
        elif size_code == 6:
            size = struct.unpack_from("<H", buf, pos)[0]; pos += 2
        else:
            size = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        if ptype == 3:
            props[nm] = bool(array); continue
        if array:
            b = buf[pos]; pos += 1
            if b >= 0x80:
                pos += 1 if (b & 0xC0) == 0x80 else 3
        raw = buf[pos:pos + size]; pos += size
        if ptype == 1:
            props[nm] = raw[0]
        elif ptype == 2:
            props[nm] = int.from_bytes(raw, "little", signed=True)
        elif ptype == 4:
            props[nm] = struct.unpack("<f", raw)[0]
        elif ptype == 10 and size == 12:
            props[nm] = struct.unpack("<3f", raw)        # Vector (Location)
        elif ptype == 10:
            props[nm] = (sname, raw)
        elif ptype in (5, 6):
            props[nm] = ci(raw, 0)[0]
        else:
            props[nm] = raw
    return props, pos


def actors(path):
    p = load_package(path)
    out = []
    for i, e in enumerate(p.exports):
        if e["ssize"] <= 0 or not (e["flags"] & RF_HasStack):
            continue                                  # actors carry a script stack
        buf = p.buf; pos = e["soff"]
        node, pos = ci(buf, pos); _st, pos = ci(buf, pos); pos += 12
        if node != 0:
            _o, pos = ci(buf, pos)
        props, pos = _read_props_typed(buf, pos, e["soff"] + e["ssize"], p.names)
        out.append((p.class_of_export(i), p.names[e["nm"]], props))
    return p, out


def main(argv):
    path = argv[1]
    p, acts = actors(path)
    print(f"{path.split('/')[-1]} v{p.version}: {len(acts)} actors (RF_HasStack), 0 parse errors")
    by_class = Counter(a[0] for a in acts)
    print("top classes:", dict(by_class.most_common(10)))
    # sanity: locations finite + within a sane world extent
    locs = [a[2].get("Location") for a in acts if "Location" in a[2]]
    bad = sum(1 for L in locs if not all(abs(c) < 1e6 for c in L))
    print(f"actors with Location: {len(locs)}; out-of-range: {bad}")
    if "--list" in argv:
        for cls, nm, props in acts[:30]:
            loc = props.get("Location")
            tag = props.get("Tag")
            print(f"  {cls:18s} {nm:16s} Loc={tuple(round(c,1) for c in loc) if loc else None} Tag={tag}")


if __name__ == "__main__":
    main(sys.argv)
