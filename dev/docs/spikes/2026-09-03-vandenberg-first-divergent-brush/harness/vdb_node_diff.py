#!/usr/bin/env python3
"""Bit-compare the editor's Pass-1 node array (a `p1nodes/*.bin` gdb dump) against native's
`P1NODE` FULL dump at the same k: count differing nodes, split plane-bits-only vs linkage
diffs, and attribute each differing node to its owning brush via the surf's actor (not
dumped) -- so report per-node field diffs + summary instead.

Usage: vdb_node_diff.py <editor.bin> <native-full.log> <k> [--list N]
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
HARNESS29 = Path(__file__).resolve().parents[2] / "2026-08-29-unatco-repart-live-diff/harness"
sys.path.insert(0, str(HARNESS29))
from pass1_compare import parse_native, read_bin  # noqa: E402


def main() -> int:
    ed_bin, na_log, k = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
    list_n = int(sys.argv[sys.argv.index("--list") + 1]) if "--list" in sys.argv else 10
    ed = read_bin(ed_bin)
    _, na_nodes = parse_native(na_log)
    na = na_nodes[k]
    print(f"editor {len(ed)} nodes, native {len(na)} nodes")
    plane_only = linkage = 0
    listed = 0
    for i, (e, n) in enumerate(zip(ed, na)):
        if e == n:
            continue
        pdiff = e[:4] != n[:4]
        ldiff = e[4:] != n[4:]
        plane_only += pdiff and not ldiff
        linkage += ldiff
        if listed < list_n:
            listed += 1
            fields = ("plx", "ply", "plz", "plw", "iF", "iB", "iP", "isurf", "nv")
            ds = [f"{nm}:{ev:08x}/{nv_:08x}" if nm.startswith("pl") else f"{nm}:{ev}/{nv_}"
                  for nm, ev, nv_ in zip(fields, e, n) if ev != nv_]
            print(f"  node {i}: " + " ".join(ds))
    print(f"differing nodes: plane-bits-only={plane_only} with-linkage-diff={linkage} "
          f"of {min(len(ed), len(na))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
