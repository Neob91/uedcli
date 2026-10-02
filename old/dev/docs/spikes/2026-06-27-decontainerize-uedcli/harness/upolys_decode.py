"""Native decoder for UE1 `UPolys`/`FPoly` — a brush's authored polygons (verts + per-poly
texture object-ref + flags + pan + item). The native-`.dx`-read prerequisite (Spike 10).

Format from disassembling `UPolys::Serialize` (Engine.dll RVA 0x115240) +
`operator<<(FArchive&, FPoly&)` (0x16fb20), EOF-validated on 6566/6587 real UPolys exports.
`FPoly.texture` is an object ref → qualifies via the package import table.

Usage: python upolys_decode.py <map.dx>
"""
from __future__ import annotations

import struct
import sys

sys.path.insert(0, ".")
from utexture_decode import load_package, ci


def _f3(b, o):
    return struct.unpack_from("<3f", b, o), o + 12


def decode_fpoly(buf, pos):
    nv, pos = ci(buf, pos)
    base, pos = _f3(buf, pos)
    normal, pos = _f3(buf, pos)
    tu, pos = _f3(buf, pos)
    tv, pos = _f3(buf, pos)
    verts = []
    for _ in range(nv):
        v, pos = _f3(buf, pos)
        verts.append(v)
    flags = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    actor, pos = ci(buf, pos)
    texture, pos = ci(buf, pos)
    item, pos = ci(buf, pos)
    ilink, pos = ci(buf, pos)
    ibrushpoly, pos = ci(buf, pos)
    panu = struct.unpack_from("<H", buf, pos)[0]; pos += 2
    panv = struct.unpack_from("<H", buf, pos)[0]; pos += 2
    return dict(num_vertices=nv, base=base, normal=normal, texture_u=tu, texture_v=tv,
                verts=verts, poly_flags=flags, actor=actor, texture=texture,
                item=item, i_link=ilink, i_brush_poly=ibrushpoly,
                pan_u=panu, pan_v=panv), pos


def decode_upolys(buf, soff, ssize):
    """Return (polys, ok_eof). polys: list of FPoly dicts."""
    end = soff + ssize
    pos = soff
    _none, pos = ci(buf, pos)                      # property-list terminator
    num = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    _max = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    polys = []
    for _ in range(num):
        fp, pos = decode_fpoly(buf, pos)
        polys.append(fp)
    return polys, pos == end


def main(argv):
    p = load_package(argv[1])
    px = [i for i in range(len(p.exports))
          if p.class_of_export(i) == "Polys" and p.exports[i]["ssize"] > 20]
    ok = 0
    for i in px:
        e = p.exports[i]
        try:
            _polys, eof = decode_upolys(p.buf, e["soff"], e["ssize"])
            ok += eof
        except Exception:
            pass
    print(f"{argv[1].split('/')[-1]}: UPolys decoded to EOF {ok}/{len(px)}")
    if px:
        polys, eof = decode_upolys(p.buf, p.exports[px[0]]["soff"], p.exports[px[0]]["ssize"])
        f0 = polys[0]
        print(f"  sample poly: nverts={f0['num_vertices']} texture_ref={f0['texture']} "
              f"flags={f0['poly_flags']:#x} v0={tuple(round(c,1) for c in f0['verts'][0])}")


if __name__ == "__main__":
    main(sys.argv)
