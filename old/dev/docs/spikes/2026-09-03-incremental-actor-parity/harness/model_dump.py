#!/usr/bin/env python3
"""Decode one UModel export's arrays (Vectors/Points/Nodes/Surfs/Verts/...) and diff two packages.

Usage: model_dump.py <a.dx> <b.dx> <model-name>       # e.g. Model2
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import parity_gate as pg  # noqa: E402
from uedcli.upackage import read_compact_index, read_property_tags  # noqa: E402

RF_HasStack = 0x02000000


def decode(p, i0: int) -> dict:
    buf = p.buf
    e = p.exports[i0]
    pos, end = e["soff"], e["soff"] + e["ssize"]
    if e["flags"] & RF_HasStack:
        idt = pg.Ident(p)
        _, pos = pg._stateframe(idt, pos)
    pos = read_property_tags(p, pos, end)[1]
    out: dict = {}
    out["bbox"] = buf[pos:pos + 25]; pos += 25
    out["sphere"] = buf[pos:pos + 16]; pos += 16
    n, pos = read_compact_index(buf, pos)
    out["vectors"] = [struct.unpack_from("<3f", buf, pos + 12 * k) for k in range(n)]; pos += 12 * n
    n, pos = read_compact_index(buf, pos)
    out["points"] = [struct.unpack_from("<3f", buf, pos + 12 * k) for k in range(n)]; pos += 12 * n
    n, pos = read_compact_index(buf, pos)
    nodes = []
    for _ in range(n):
        plane = struct.unpack_from("<4f", buf, pos); pos += 16
        zm = struct.unpack_from("<Q", buf, pos)[0]; pos += 8
        nf = buf[pos]; pos += 1
        cis = []
        for _ in range(10):
            v, pos = read_compact_index(buf, pos)
            cis.append(v)
        tail = buf[pos:pos + 8]; pos += 8
        nodes.append((plane, zm, nf, cis, tail))
    out["nodes"] = nodes
    n, pos = read_compact_index(buf, pos)
    surfs = []
    for _ in range(n):
        tex, pos = read_compact_index(buf, pos)
        flags = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        ci = []
        for _ in range(6):
            v, pos = read_compact_index(buf, pos)
            ci.append(v)
        lm = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        act, pos = read_compact_index(buf, pos)
        surfs.append((tex, flags, ci, lm, act))
    out["surfs"] = surfs
    n, pos = read_compact_index(buf, pos)
    verts = []
    for _ in range(n):
        a, pos = read_compact_index(buf, pos)
        b, pos = read_compact_index(buf, pos)
        verts.append((a, b))
    out["verts"] = verts
    out["numsharedsides"] = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    nz = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    zones = []
    for _ in range(nz):
        z, pos = read_compact_index(buf, pos)
        zones.append((z, buf[pos:pos + 16])); pos += 16
    out["zones"] = zones
    polys, pos = read_compact_index(buf, pos)
    out["polys_ref"] = polys
    n, pos = read_compact_index(buf, pos)
    lm = []
    for _ in range(n):
        raw = buf[pos:pos + 16]; pos += 16
        a, pos = read_compact_index(buf, pos)
        b, pos = read_compact_index(buf, pos)
        lm.append((raw, a, b, buf[pos:pos + 12])); pos += 12
    out["lightmap"] = lm
    n, pos = read_compact_index(buf, pos); out["lightbits"] = buf[pos:pos + n]; pos += n
    n, pos = read_compact_index(buf, pos)
    out["bounds"] = [buf[pos + 25 * k:pos + 25 * (k + 1)] for k in range(n)]; pos += 25 * n
    n, pos = read_compact_index(buf, pos)
    out["leafhulls"] = list(struct.unpack_from(f"<{n}i", buf, pos)) if n else []; pos += 4 * n
    n, pos = read_compact_index(buf, pos)
    leaves = []
    for _ in range(n):
        t = []
        for _ in range(3):
            v, pos = read_compact_index(buf, pos)
            t.append(v)
        leaves.append((tuple(t), buf[pos:pos + 8])); pos += 8
    out["leaves"] = leaves
    n, pos = read_compact_index(buf, pos)
    lights = []
    for _ in range(n):
        v, pos = read_compact_index(buf, pos)
        lights.append(v)
    out["lights"] = lights
    out["tail"] = buf[pos:pos + 8]; pos += 8
    assert pos == end, (pos, end)
    return out


def find(p, name: str) -> int:
    for i, e in enumerate(p.exports):
        if p.names[e["nm"]].casefold() == name.casefold():
            return i
    raise SystemExit(f"no export named {name}")


def main() -> int:
    a, b, name = sys.argv[1], sys.argv[2], sys.argv[3]
    P, Q = pg.load_package(a), pg.load_package(b)
    da, db = decode(P, find(P, name)), decode(Q, find(Q, name))
    for k in da:
        va, vb = da[k], db[k]
        if va == vb:
            print(f"{k:14s} SAME  ({len(va) if hasattr(va,'__len__') else ''})")
            continue
        la = len(va) if hasattr(va, "__len__") else "-"
        lb = len(vb) if hasattr(vb, "__len__") else "-"
        print(f"{k:14s} DIFF  len {la} vs {lb}")
        if isinstance(va, list) and isinstance(vb, list):
            for i in range(min(len(va), len(vb))):
                if va[i] != vb[i]:
                    print(f"   [{i}] a={va[i]}")
                    print(f"       b={vb[i]}")
            for i in range(min(len(va), len(vb)), max(len(va), len(vb))):
                src = va if len(va) > len(vb) else vb
                print(f"   [{i}] only-{'a' if len(va)>len(vb) else 'b'}={src[i]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
