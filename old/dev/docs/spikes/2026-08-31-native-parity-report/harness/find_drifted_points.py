#!/usr/bin/env python3
"""Dump native points/vectors that don't VALUE-match any golden point/vector (multiset compare),
for NYC Bar. One-off diagnostic for the lighting-bits-only-divergence-localizes-to grid-only bucket
investigation -- not a standing test, see spikes.md's "one-off decision" exception.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import parity_compare as pc  # noqa: E402

TRUNK = Path(sys.argv[1])
GOLDEN = Path(sys.argv[2])

native_model, level = pc.build_native_model(TRUNK)
golden_model = pc.parse_dx_model(GOLDEN)

print(f"native points={len(native_model.points)} golden points={len(golden_model.points)}")
print(f"native vectors={len(native_model.vectors)} golden vectors={len(golden_model.vectors)}")

golden_points_set = set(golden_model.points)
mismatched = [(i, p) for i, p in enumerate(native_model.points) if p not in golden_points_set]
print(f"\n{len(mismatched)} native points value-mismatched (multiset)")
for i, p in mismatched[:80]:
    print(f"  native[{i}] = {p!r}")

golden_vecs_set = set(golden_model.vectors)
vmismatched = [(i, v) for i, v in enumerate(native_model.vectors) if v not in golden_vecs_set]
print(f"\n{len(vmismatched)} native vectors value-mismatched (multiset)")
for i, v in vmismatched[:40]:
    print(f"  native[{i}] = {v!r}")
