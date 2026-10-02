#!/usr/bin/env python3
"""Attribute each plane-bits-differing Pass-1 node (editor nfinal.bin vs native FULL:727-727)
to the brush whose CSG add created it (BRUSHSTATE node-count ranges; verified monotonic), then
cross-tab against the brush property table (`vdb_brush_props.py` output).

Usage: vdb_attrib_planes.py <editor-nfinal.bin> <native-full.log> <native-counts.log> <props.txt>
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
HARNESS29 = Path(__file__).resolve().parents[2] / "2026-08-29-unatco-repart-live-diff/harness"
sys.path.insert(0, str(HARNESS29))
from pass1_compare import parse_native, read_bin  # noqa: E402


def main() -> int:
    ed_bin, na_log, counts_log, props_txt = (Path(a) for a in sys.argv[1:5])
    ed = read_bin(ed_bin)
    _, na_nodes = parse_native(na_log)
    na = na_nodes[727]
    states, _ = parse_native(counts_log)
    prev = 0
    ranges = []  # (k, bi, lo, hi) node indices created during brush k
    for s in states:
        assert s["nodes"] >= prev, f"node count shrank at k={s['k']}: {prev} -> {s['nodes']}"
        ranges.append((s["k"], s["bi"], prev, s["nodes"]))
        prev = s["nodes"]

    props = {}
    for line in props_txt.read_text().splitlines():
        m = re.match(r"k=\s*(\S+) bi=\s*(\d+) (\S+)\s+oper=(\S+)\s+pf=\s*(\S+) npolys=\s*(\d+) "
                     r"scaled=(\d) mirror=(\S) sheer=(\S) det=(\S+)", line)
        if m:
            props[int(m.group(2))] = dict(name=m.group(3), oper=m.group(4), scaled=m.group(7),
                                          mirror=m.group(8), det=m.group(10))

    per_brush: dict[int, int] = {}
    first = None
    for i, (e, n) in enumerate(zip(ed, na)):
        if e == n:
            continue
        k, bi = next((k, bi) for k, bi, lo, hi in ranges if lo <= i < hi)
        per_brush[bi] = per_brush.get(bi, 0) + 1
        if first is None:
            first = (i, k, bi)
    i, k, bi = first
    p = props[bi]
    print(f"FIRST differing node: idx={i} created by k={k} bi={bi} {p['name']} "
          f"(oper={p['oper']} scaled={p['scaled']} mirror={p['mirror']} det={p['det']})")
    print(f"{len(per_brush)} brushes own differing nodes; top 20 by count:")
    for bi, c in sorted(per_brush.items(), key=lambda kv: -kv[1])[:20]:
        p = props[bi]
        print(f"  bi={bi:4d} {p['name']:14s} oper={p['oper']:13s} scaled={p['scaled']} "
              f"mirror={p['mirror']} det={p['det']:>10s} diffnodes={c}")
    n_scaled = sum(c for bi, c in per_brush.items() if props[bi]["scaled"] == "1")
    n_mirror = sum(c for bi, c in per_brush.items() if props[bi]["mirror"] == "1")
    total = sum(per_brush.values())
    print(f"diff nodes total={total} on-scaled={n_scaled} on-mirrored={n_mirror}")
    bs = sorted(per_brush)
    print(f"brush split: scaled={sum(1 for b in bs if props[b]['scaled'] == '1')}"
          f"/mirrored={sum(1 for b in bs if props[b]['mirror'] == '1')}"
          f"/unscaled={sum(1 for b in bs if props[b]['scaled'] == '0')} of {len(bs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
