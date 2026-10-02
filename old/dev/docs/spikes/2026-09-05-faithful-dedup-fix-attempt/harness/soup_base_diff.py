#!/usr/bin/env python3
"""Diff the CSG-soup (`Model->Polys`) FPoly.Base tokens of two built packages, matched by identity.

Complements `2026-09-04-.../diff_n8.py` (which diffs the Model's nodes/surfs/points). WanChai N19's
whole Model is byte-identical yet the standalone `Polys@model model2` soup diverges -- this pinpoints
which soup poly's Base differs, by how much, and whether native's Base is a real entry of its own
Model.Points (i.e. native SNAPPED a raw base the editor kept distinct: the point-dedup class).

Run: `soup_base_diff.py <native.dx> <ued.dx>`
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
GATE = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
sys.path.insert(0, str(GATE))
sys.path.insert(0, str(ROOT))

import parity_gate as g  # noqa: E402
from uedcli.upackage import load_package  # noqa: E402


def main() -> int:
    A, B = load_package(sys.argv[1]), load_package(sys.argv[2])
    ia, ib = g.Ident(A), g.Ident(B)
    ids_a = {ia.export_identity(i): i for i in range(len(A.exports))}
    ids_b = {ib.export_identity(i): i for i in range(len(B.exports))}
    for ident in sorted(set(ids_a) & set(ids_b)):
        if not ident.startswith("polys"):
            continue
        ca, cb = g.canon_body(ia, ids_a[ident]), g.canon_body(ib, ids_b[ident])
        if g._bodies_equal(ca, cb):
            continue
        print(f"=== {ident} DIFFERS ===")
        pbi = 0
        for xa, xb in zip(ca[2], cb[2]):
            if xa[0] == "PB" or xb[0] == "PB":
                if xa != xb:
                    ba, bb = xa[1], xb[1]
                    d = sum((ba[k] - bb[k]) ** 2 for k in range(3)) ** 0.5
                    print(f" PB#{pbi} d={d:.6e}")
                    print(f"    nat={ba} in_own_model={xa[2]}")
                    print(f"    ued={bb} in_own_model={xb[2]}")
                pbi += 1
            elif xa != xb:
                print(f" non-PB token differs: {xa[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
