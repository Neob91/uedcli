#!/usr/bin/env python3
"""Across every cached editor reference: report each mover model's LightMap count, its Polys'
iLink/iBrushPoly, and the world Model2's surf/lightmap counts. Data for deriving the rule."""
import struct
import sys
from pathlib import Path

HARNESS = Path("dev/docs/spikes/2026-09-03-incremental-actor-parity/harness").resolve()
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path.cwd()))

import model_dump as MD  # noqa: E402
import parity_gate as pg  # noqa: E402
from uedcli.native.saveorder import _model_polys_map  # noqa: E402
from uedcli.upackage import read_compact_index, read_property_tags  # noqa: E402


def polys_of(p, idx):
    e = p.exports[idx]
    pos, end = e["soff"], e["soff"] + e["ssize"]
    pos = read_property_tags(p, pos, end)[1]
    num = struct.unpack_from("<i", p.buf, pos)[0]
    pos += 8
    out = []
    for _ in range(num):
        nv, pos = read_compact_index(p.buf, pos)
        pos += 48 + 12 * nv
        pf = struct.unpack_from("<i", p.buf, pos)[0]
        pos += 4
        for _k in range(3):
            _, pos = read_compact_index(p.buf, pos)
        ilink, pos = read_compact_index(p.buf, pos)
        ibp, pos = read_compact_index(p.buf, pos)
        pos += 4
        out.append((pf, ilink, ibp))
    return out


def scan(path):
    p = pg.load_package(path)
    mp = _model_polys_map(p)
    owner = {v: k for k, v in mp.items()}
    by_name = {p.names[p.exports[i]["nm"]]: i for i in range(len(p.exports))}
    rows = []
    world = None
    for i in range(len(p.exports)):
        nm = p.names[p.exports[i]["nm"]]
        if (p.object_class_name(i + 1) or "") != "Model":
            continue
        try:
            d = MD.decode(p, i)
            lm = len(d.get("lightmap") or [])
            surfs = len(d.get("surfs") or [])
            nodes = len(d.get("nodes") or [])
        except Exception as exc:  # noqa: BLE001
            print(f"   {nm}: decode error {exc}")
            continue
        pn = mp.get(nm)
        try:
            pl = polys_of(p, by_name[pn]) if pn in by_name else []
        except Exception as exc:  # noqa: BLE001
            pl = [("err", str(exc), "")]
        if nm.lower().startswith("model2"):
            world = (nm, nodes, surfs, lm, pl)
        elif "mover" in nm.lower():
            rows.append((nm, nodes, surfs, lm, pl))
    return world, rows


for path in sorted(sys.argv[1:]):
    try:
        world, rows = scan(path)
    except Exception as exc:  # noqa: BLE001
        print(f"{path}: ERROR {exc}")
        continue
    if not rows:
        continue
    wn, wnodes, wsurfs, wlm, wpl = world if world else ("?", 0, 0, 0, [])
    print(f"== {Path(path).name}  world nodes={wnodes} surfs={wsurfs} lightmap={wlm}")
    for nm, nodes, surfs, lm, pl in rows:
        print(f"   {nm}: nodes={nodes} surfs={surfs} lightmap={lm} "
              f"polys={[(hex(f), l, b) for f, l, b in pl]}")
