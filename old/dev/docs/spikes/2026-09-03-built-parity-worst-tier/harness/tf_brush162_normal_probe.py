#!/usr/bin/env python3
"""Verification probe (post-321f5dd): recompute native's CURRENT surf normal for the
[Brush663, Brush1, Brush162] minimal oracle and compare against the editor bits pinned in
`trainingfinal-59-node-residual-brush162-recomputed-normal` (live-captured, immutable ground
truth -- editor behavior does not change, only native code does). No live editor rebuild needed:
counts for this oracle were already EXACT (50/29/25) pre-fix, so a fresh cached golden would only
re-confirm counts, not the normal bits, which are pinned as hex already.

Usage: tf_brush162_normal_probe.py
"""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prefix_search_lib as PSL  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
import uedcli_native  # noqa: E402

CACHE = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/f3e6539d9ed950dcf1dfb5929040e2da07b37f263727c360fdf2de63e2e73d27/trunk")

EDITOR_HEX = ["0xb3797439", "0x3f2a13c0", "0x3f3f5638"]  # pinned in the board item, live-captured


def f32_hex(x):
    return "0x" + struct.pack(">f", x).hex()


def main():
    wt = HERE.parents[4]
    ps = PSL.PrefixSearch("00_trainingfinal", CACHE / "maps/00_trainingfinal",
                           wt / "_scratch/tf-brush162-probe", CACHE)
    keep_brushes = {"Brush663", "Brush1", "Brush162"}
    ordered = [nm for nm in ps.brush_names if nm in keep_brushes]
    ins = [BM._build_brush_input(nm, ps.level.actors[nm]) for nm in ordered]
    built = uedcli_native.build_geometry_bspcsg(ins)
    body = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(body, 0, len(body))
    print(f"case {ordered}: native nodes={len(nm.nodes)} surfs={len(nm.surfs)} leaves={len(nm.leaves)}")

    matches = []
    for i, s in enumerate(nm.surfs):
        n = nm.vectors[s.v_normal]
        hexes = [f32_hex(c) for c in n]
        if hexes[0].startswith("0xb37974"):  # the x-component family (~-5.8e-8)
            matches.append((i, n, hexes))

    if not matches:
        print("NO candidate surf found with the target x-normal family -- oracle brush set/order "
              "may need adjusting.")
        return

    for i, n, hexes in matches:
        closed = hexes == EDITOR_HEX
        print(f"  surf[{i}] normal={n} hex={hexes} editor_hex={EDITOR_HEX} "
              f"{'CLOSED (bit-exact)' if closed else 'STILL DIVERGES'}")


if __name__ == "__main__":
    main()
