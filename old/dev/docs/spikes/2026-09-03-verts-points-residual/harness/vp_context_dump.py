#!/usr/bin/env python3
"""Dump a window of the Verts array (both sides) with coord / i_side / covering node — for
inspecting the neighborhood of an insertion found by vp_insertion_point.py.

Usage: .venv/bin/python vp_context_dump.py <OG.dx> <lo> <hi> [--golden-offset N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "2026-08-31-native-parity-report/harness"))

from vp_diff import load_pair  # noqa: E402
from vp_insertion_point import coord, covering_node  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dx_path")
    ap.add_argument("lo", type=int)
    ap.add_argument("hi", type=int)
    ap.add_argument("--golden-offset", type=int, default=0)
    args = ap.parse_args()
    native, golden = load_pair(Path(args.dx_path))
    for i in range(args.lo, args.hi):
        gv_i = i + args.golden_offset
        nrow = grow = "-"
        if 0 <= i < len(native.verts):
            v = native.verts[i]
            nrow = f"{coord(native, v)} side={v.i_side} node={covering_node(native, i)}"
        if 0 <= gv_i < len(golden.verts):
            v = golden.verts[gv_i]
            grow = f"{coord(golden, v)} side={v.i_side} node={covering_node(golden, gv_i)}"
        print(f"[{i:6d}] N {nrow}")
        print(f"[{gv_i:6d}] G {grow}")


if __name__ == "__main__":
    main()
