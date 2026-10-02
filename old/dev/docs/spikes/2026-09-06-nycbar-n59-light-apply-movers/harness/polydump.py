#!/usr/bin/env python3
"""Dump a package's Polys export: per-poly (nv, polyflags, actor, texture, item, iLink, iBrushPoly)."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path("dev/docs/spikes/2026-09-03-incremental-actor-parity/harness").resolve()))
sys.path.insert(0, str(Path.cwd()))

import parity_gate as pg  # noqa: E402
from uedcli.upackage import read_compact_index, read_property_tags  # noqa: E402


def dump(path, want):
    p = pg.load_package(path)
    for i in range(len(p.exports)):
        nm = p.names[p.exports[i]["nm"]]
        if (p.object_class_name(i + 1) or "") != "Polys":
            continue
        # find owning model
        from uedcli.native.saveorder import _model_polys_map
        mp = _model_polys_map(p)
        owner = {v: k for k, v in mp.items()}.get(nm, "?")
        if want and want.casefold() not in owner.casefold() and want.casefold() not in nm.casefold():
            continue
        e = p.exports[i]
        pos, end = e["soff"], e["soff"] + e["ssize"]
        pos = read_property_tags(p, pos, end)[1]
        num = struct.unpack_from("<i", p.buf, pos)[0]
        pos += 8
        print(f"--- {nm} (owner {owner}) num={num}")
        for k in range(num):
            nv, pos = read_compact_index(p.buf, pos)
            base = struct.unpack_from("<3f", p.buf, pos)
            pos += 48 + 12 * nv
            pf = struct.unpack_from("<i", p.buf, pos)[0]
            pos += 4
            actor, pos = read_compact_index(p.buf, pos)
            tex, pos = read_compact_index(p.buf, pos)
            item, pos = read_compact_index(p.buf, pos)
            ilink, pos = read_compact_index(p.buf, pos)
            ibp, pos = read_compact_index(p.buf, pos)
            panu, panv = struct.unpack_from("<HH", p.buf, pos)
            pos += 4
            print(f"  [{k}] nv={nv} flags=0x{pf:x} actor={actor} tex={tex} "
                  f"item={p.names[item]} iLink={ilink} iBrushPoly={ibp} pan=({panu},{panv}) base={base}")


if __name__ == "__main__":
    dump(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
