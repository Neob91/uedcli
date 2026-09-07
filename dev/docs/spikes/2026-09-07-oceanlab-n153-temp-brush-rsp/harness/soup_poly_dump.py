#!/usr/bin/env python3
"""Dump a built package's world CSG-soup `FPoly`s with their vertices as f32 BITS.

`model_dump.py` diffs a Model's arrays; this prints the SOUP (`Polys@Model2`) side, which is where a
divergent CSG cut vertex is readable together with the poly's owning brush (`Actor`), `iLink` and
`iBrushPoly` -- what you need to say WHICH face got cut and by what.

Run from the repo root:
  soup_poly_dump.py <pkg.dx> [actor-substring]        # every poly, or only that brush's
  soup_poly_dump.py <pkg.dx> --near <x> <y> <z> <r>   # only polys with a vertex within r of a point
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"))

import parity_gate as pg                                            # noqa: E402
from uedcli.native.saveorder import _model_polys_map                # noqa: E402
from uedcli.upackage import read_compact_index, read_property_tags  # noqa: E402

RF_HAS_STACK = 0x02000000


def soup_polys(path: str, model_name: str = "Model2") -> list[dict]:
    p = pg.load_package(path)
    idt = pg.Ident(p)
    want = _model_polys_map(p)[model_name]
    idx = next(i for i, e in enumerate(p.exports)
               if (p.object_class_name(i + 1) or "") == "Polys" and p.names[e["nm"]] == want)
    e = p.exports[idx]
    buf, pos = p.buf, e["soff"]
    if e["flags"] & RF_HAS_STACK:
        _, pos = pg._stateframe(idt, pos)
    pos = read_property_tags(p, pos, e["soff"] + e["ssize"])[1]
    num = struct.unpack_from("<i", buf, pos)[0]
    pos += 8
    out = []
    for k in range(num):
        nv, pos = read_compact_index(buf, pos)
        base = struct.unpack_from("<3f", buf, pos)
        normal = struct.unpack_from("<3f", buf, pos + 12)
        verts = [struct.unpack_from("<3f", buf, pos + 48 + 12 * j) for j in range(nv)]
        pos += 48 + 12 * nv + 4
        actor, pos = read_compact_index(buf, pos)
        _texture, pos = read_compact_index(buf, pos)
        item, pos = read_compact_index(buf, pos)
        i_link, pos = read_compact_index(buf, pos)
        i_brush_poly, pos = read_compact_index(buf, pos)
        pos += 4
        out.append(dict(k=k, base=base, normal=normal, verts=verts,
                        actor=str(idt.ref_identity(actor)), item=p.names[item],
                        i_link=i_link, i_brush_poly=i_brush_poly))
    return out


def _bits(v) -> str:
    return ",".join(f"{struct.unpack('<I', struct.pack('<f', c))[0]:08x}" for c in v)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    near = None
    want = ""
    if len(sys.argv) > 2 and sys.argv[2] == "--near":
        cx, cy, cz, r = (float(a) for a in sys.argv[3:7])
        near = (cx, cy, cz, r)
    elif len(sys.argv) > 2:
        want = sys.argv[2].casefold()
    for d in soup_polys(path):
        if want and want not in d["actor"].casefold():
            continue
        if near and not any(
            sum((v[i] - near[i]) ** 2 for i in range(3)) <= near[3] ** 2 for v in d["verts"]
        ):
            continue
        print(f"poly[{d['k']}] actor={d['actor']} item={d['item']} "
              f"iLink={d['i_link']} iBrushPoly={d['i_brush_poly']}")
        print(f"   base=[{_bits(d['base'])}] normal=[{_bits(d['normal'])}]")
        for j, v in enumerate(d["verts"]):
            print(f"   v[{j}]=[{_bits(v)}] {v}")
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
