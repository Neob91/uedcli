#!/usr/bin/env python3
"""The corpus half of the NYC_Bar N=119 fix: UnrealEd's lightmap walk skips 0-vertex nodes.

`LIGHT APPLY` allocates the world `LightMap` array by recursing `Editor.dll 0x100a4a90` from node 0,
allocating a record only when `node->NumVertices != 0 && !(surf->PolyFlags & 0x400081) &&
surf->iLightMap == -1`. A vertex-less node neither allocates nor CLAIMS its surf, so a surf that
also sits on a later non-empty node is allocated at that later position. Native's walk had the
vertex gate missing, which on NYC_Bar N=119 emitted surfs 174 and 178 at records 144/152 where UED22
emits them at 228/229.

Here the walk is re-run over every shipped Deus Ex world `Model`, predicting each Model's own
record→surf order from its own nodes and surfs: exact with the gate, wrong without it on three maps.
This lives in the harness because it needs the gitignored `dev/games/` maps; the instruction-byte
half of the pin is `uedcli/tests/test_engine_facts.py`, which runs in the suite.

Run: python3 test_lightmap_alloc_zero_vert_gate.py     (or via pytest)
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT))

import pytest                        # noqa: E402
import parity_gate as G              # noqa: E402
from model_dump import decode, find  # noqa: E402

CACHE = ROOT / "_scratch/actor-parity"
MAPS = ROOT / "dev/games/deusex/Maps"

PF_NO_LIGHTMAP = 0x400081
# model_dump's node tuple is (plane, zone_mask, node_flags, cis, iLeaf-bytes); cis positions:
I_SURF, I_FRONT, I_BACK, I_PLANE, NUM_VERTS = 1, 2, 3, 4, 9


def emit_order(decoded: dict, *, gate_zero_vert: bool) -> list[int]:
    """The allocate walk over one decoded Model, as a record -> surf-index list."""
    nodes, surfs = decoded["nodes"], decoded["surfs"]
    order: list[int] = []
    node_seen = [False] * len(nodes)
    claimed = [False] * len(surfs)
    stack = [0] if nodes else []
    while stack:
        ni = stack.pop()
        if not 0 <= ni < len(nodes) or node_seen[ni]:
            continue
        node_seen[ni] = True
        cis = nodes[ni][3]
        si = cis[I_SURF]
        if 0 <= si < len(surfs) and (not gate_zero_vert or cis[NUM_VERTS] != 0):
            if surfs[si][1] & PF_NO_LIGHTMAP == 0 and not claimed[si]:
                claimed[si] = True
                order.append(si)
        # Push reversed: iBack (the 2nd on-disk child) is visited first, then iFront, then iPlane.
        stack += [cis[I_PLANE], cis[I_FRONT], cis[I_BACK]]
    return order


def stored_order(decoded: dict) -> list[int] | None:
    """The Model's own record -> surf order, read back from the surfs' `iLightMap` links."""
    out: list[int | None] = [None] * len(decoded["lightmap"])
    for si, surf in enumerate(decoded["surfs"]):
        lm = surf[2][4]
        if 0 <= lm < len(out):
            if out[lm] is not None:
                return None            # two surfs share a record: not a clean editor build
            out[lm] = si
    return None if any(v is None for v in out) else out  # type: ignore[return-value]


def world_models(pkg: Path):
    p = G.load_package(str(pkg))
    for i, e in enumerate(p.exports):
        if p.names[e["nm"]].lower().startswith("model") and e["ssize"] >= 1000:
            try:
                yield decode(p, i)
            except Exception:          # a non-world Model export decodes short — skip it
                continue


def test_nyc_bar_n119_reference_needs_the_gate():
    ref = CACHE / "02_nyc_bar" / "ref_N119.dx"
    if not ref.exists():
        pytest.skip(f"{ref} absent")
    pkg = G.load_package(str(ref))
    model = decode(pkg, find(pkg, "model2"))
    want = stored_order(model)
    assert emit_order(model, gate_zero_vert=True) == want
    # Teeth: this is the level that caught the bug, so the ungated walk must actually differ.
    assert emit_order(model, gate_zero_vert=False) != want


def test_shipped_maps_record_order_matches_the_gated_walk():
    maps = sorted(glob.glob(str(MAPS / "*.dx")))
    if not maps:
        pytest.skip(f"{MAPS} absent")
    checked = ungated_wrong = 0
    for m in maps:
        for model in world_models(Path(m)):
            want = stored_order(model)
            if want is None or not model["nodes"]:
                continue
            checked += 1
            assert emit_order(model, gate_zero_vert=True) == want, f"{m}: gated walk != stored order"
            ungated_wrong += emit_order(model, gate_zero_vert=False) != want
    assert checked >= 150, f"only {checked} world Models decoded — corpus not actually exercised"
    assert ungated_wrong >= 3, f"the ungated walk must FAIL somewhere, failed on {ungated_wrong}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except BaseException as exc:                     # pytest.skip raises, so catch it here
                if type(exc).__name__ != "Skipped":
                    raise
                print(f"{name}: skipped ({exc})")
                continue
            print(f"{name}: ok")
