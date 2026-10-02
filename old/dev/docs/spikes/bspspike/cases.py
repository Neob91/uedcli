"""Discriminating parity corpus: brush sets where FindBestSplit's choice + real splits matter.

Each case is (name, [(builder_actor_args)]) producing brushes that enter via EDIT PASTE.
Geometry is also expressed as bsp_csg.Brush for the offline port.
"""
from __future__ import annotations

import bsp_port
import bsp_csg
from bsp_csg import Brush


def _box(cx, cy, cz, hx, hy, hz, csg, flags=0):
    return Brush(bsp_port.box(cx, cy, cz, hx, hy, hz, flags), csg, flags)


# Each case: name -> list[Brush] (offline) ; the live builder spec is derived in the oracle
CASES = {
    # 1. single subtract box — the slice-1 baseline (no real splits)
    "single_box": [
        _box(0, 0, 0, 128, 128, 128, "subtract"),
    ],
    # 2. two abutting subtract boxes sharing a face plane (x=128) — coplanar handling
    "abutting_subtracts": [
        _box(-128, 0, 0, 128, 128, 128, "subtract"),
        _box(128, 0, 0, 128, 128, 128, "subtract"),
    ],
    # 3. two overlapping subtract boxes (L-shaped room) — real straddling splits
    "overlapping_subtracts_L": [
        _box(0, 0, 0, 192, 96, 96, "subtract"),
        _box(0, 0, 0, 96, 192, 96, "subtract"),
    ],
    # 4. subtract room with an additive pillar inside — add refills carved space, straddles
    "room_with_pillar": [
        _box(0, 0, 0, 256, 256, 128, "subtract"),
        _box(0, 0, 0, 32, 32, 128, "add"),
    ],
    # 5. subtract room with an off-CENTER additive pillar (asymmetric Front/Back)
    "room_offset_pillar": [
        _box(0, 0, 0, 256, 256, 128, "subtract"),
        _box(96, 64, 0, 32, 32, 128, "add"),
    ],
}


def offline_counts(name):
    brushes = CASES[name]
    soup = bsp_csg.csg_world_surfaces(brushes)
    tree = bsp_port.split_poly_list(soup, optimization=bsp_port.OPTIMAL, balance=50, portal_bias=70)
    raw = bsp_port.count_nodes(tree)
    merged = bsp_csg.merge_coplanars(tree)
    return {
        "surfaces": len(soup),
        "raw_nodes": raw,
        "merged_nodes": bsp_port.count_nodes(merged),
        "surface_nodes": bsp_csg.count_surface_nodes(merged),
    }


if __name__ == "__main__":
    for name in CASES:
        print(f"{name:28s} {offline_counts(name)}")
