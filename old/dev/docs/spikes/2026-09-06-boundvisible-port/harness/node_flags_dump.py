#!/usr/bin/env python3
"""Print each package's `Model2` BSP-node `NodeFlags`, so a `NF_BoxOccluded` (0x10) write is visible.

The parity gate masks `node_flags & ~0x18`, so a flag divergence never shows up there; this is the
direct read. Usage: node_flags_dump.py <a.dx> <b.dx> [model-name]
"""
from __future__ import annotations

import sys
from pathlib import Path

LADDER = Path(__file__).resolve().parents[2] / "2026-09-03-incremental-actor-parity/harness"
sys.path.insert(0, str(LADDER))

import model_dump as md  # noqa: E402
import parity_gate as pg  # noqa: E402


def flags(path: Path, model_name: str) -> list[int]:
    p = pg.load_package(path)
    return [n[2] for n in md.decode(p, md.find(p, model_name))["nodes"]]


def main() -> int:
    model = sys.argv[3] if len(sys.argv) > 3 else "Model2"
    a, b = flags(Path(sys.argv[1]), model), flags(Path(sys.argv[2]), model)
    print(f"{len(a)} vs {len(b)} nodes")
    for i in range(max(len(a), len(b))):
        av, bv = (a[i] if i < len(a) else None), (b[i] if i < len(b) else None)
        if (av or 0) & 0x18 or (bv or 0) & 0x18 or av != bv:
            print(f"  node {i:5d}  A={av if av is None else hex(av)}  "
                  f"B={bv if bv is None else hex(bv)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
