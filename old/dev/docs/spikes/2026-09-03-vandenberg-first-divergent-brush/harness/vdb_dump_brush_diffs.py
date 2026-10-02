#!/usr/bin/env python3
"""Dump the distinct (editor, native) differing node plane-bit pairs created by one brush.

Usage: vdb_dump_brush_diffs.py <bi> <editor-nfinal.bin> <native-full.log> <native-counts.log>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
HARNESS29 = Path(__file__).resolve().parents[2] / "2026-08-29-unatco-repart-live-diff/harness"
sys.path.insert(0, str(HARNESS29))
from pass1_compare import parse_native, read_bin  # noqa: E402


def main() -> int:
    want_bi = int(sys.argv[1])
    ed = read_bin(Path(sys.argv[2]))
    _, na_nodes = parse_native(Path(sys.argv[3]))
    na = na_nodes[727]
    states, _ = parse_native(Path(sys.argv[4]))
    ranges = []
    prev = 0
    for s in states:
        ranges.append((s["bi"], prev, s["nodes"]))
        prev = s["nodes"]
    seen = set()
    for i, (e, n) in enumerate(zip(ed, na)):
        if e == n:
            continue
        bi = next(bi for bi, lo, hi in ranges if lo <= i < hi)
        if bi != want_bi:
            continue
        pair = (e[:4], n[:4])
        if pair in seen:
            continue
        seen.add(pair)
        print(f"node {i}: editor={','.join(f'{v:08x}' for v in e[:4])} "
              f"native={','.join(f'{v:08x}' for v in n[:4])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
