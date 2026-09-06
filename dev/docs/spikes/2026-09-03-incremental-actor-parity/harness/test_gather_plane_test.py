#!/usr/bin/env python3
"""Pins the gather pass's perpendicular plane test — the OceanLab N=44 fix.

`Editor 0x100a4e87`-`0x100a4ef7` drops a light from a surf's lightmap run when the PERPENDICULAR
distance from the light to the surf's infinite plane exceeds `WorldLightRadius = (LightRadius+1)*25`.
Native applied it only to the empty-run/dark decision, not to the raytrace loop, so a light just
past the radius still lit lumels (the raytrace samples at `plane + Normal*4`, the self-shadow bias)
and entered the run: OceanLab N=44's world `Model2` carried `Light111`/`Light121` on `Brush1419`'s
surf 228 where UED22 carries neither.

Two claims, both checked here:
  1. the arithmetic on that surf (pure numbers, no build needed), and
  2. NO editor reference package emits a pair violating the predicate — over every cached
     `ref_N*.dx`, and over `native_N*.dx` too when present.

Run: python3 test_gather_plane_test.py     (or via pytest)
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT))

import parity_gate as G          # noqa: E402
from model_dump import decode, find  # noqa: E402
from uedcli.upackage import read_property_tags  # noqa: E402

CACHE = ROOT / "_scratch/actor-parity"
DEFAULT_LIGHT_RADIUS = 64        # Engine.Light's class default, omitted from the export when unset
RF_HAS_STACK = 0x02000000


def world_radius(light_radius: int) -> float:
    return (light_radius + 1) * 25.0


def test_oceanlab_surf228_arithmetic():
    # Brush1419's surf 228: plane y = -96, inward normal +Y (values read off both N=44 packages).
    plane_y = -96.0
    for name, light_y, radius, listed in (("Light111", 930.305359, 40, False),
                                          ("Light121", 931.683289, 40, False),
                                          ("Light106", 647.804321, 30, True)):
        dot = abs(light_y - plane_y)
        assert (dot <= world_radius(radius)) is listed, (name, dot, world_radius(radius))


def _light_props(p) -> dict[int, tuple[tuple[float, float, float], int]]:
    """Every Light-ish export's (Location, LightRadius), keyed by 1-based export index."""
    out = {}
    for i, e in enumerate(p.exports):
        if "light" not in (p.object_class_name(i + 1) or "").casefold():
            continue
        pos = e["soff"]
        if e["flags"] & RF_HAS_STACK:
            _, pos = G._stateframe(G.Ident(p), pos)
        tags, _ = read_property_tags(p, pos, e["soff"] + e["ssize"])
        loc, radius = (0.0, 0.0, 0.0), DEFAULT_LIGHT_RADIUS
        for t in tags:
            if t.name == "Location":
                loc = struct.unpack_from("<3f", t.raw, 0)
            elif t.name == "LightRadius":
                radius = t.raw[0]
        out[i + 1] = (loc, radius)
    return out


def violating_pairs(path: Path) -> list[tuple[int, str, float, float]]:
    """(surf, light, |PlaneDot|, WorldLightRadius) for every run member past its plane's radius."""
    p = G.load_package(str(path))
    d = decode(p, find(p, "model2"))
    idt = G.Ident(p)
    props = _light_props(p)
    starts = [struct.unpack_from("<i", tail, 8)[0] for _, _, _, tail in d["lightmap"]]
    bad = []
    for si, (_tex, _flags, ci, _pan, _act) in enumerate(d["surfs"]):
        ilm = ci[4]
        if not 0 <= ilm < len(starts) or starts[ilm] < 0:
            continue
        base, normal = d["points"][ci[0]], d["vectors"][ci[1]]
        j = starts[ilm]
        while j < len(d["lights"]) and d["lights"][j] > 0:
            ref = d["lights"][j]
            loc, radius = props[ref]
            dot = abs(sum((loc[k] - base[k]) * normal[k] for k in range(3)))
            if dot > world_radius(radius):
                bad.append((si, idt.ref_identity(ref), dot, world_radius(radius)))
            j += 1
    return bad


def test_no_cached_package_violates_the_predicate():
    checked = 0
    for pkg in sorted(CACHE.glob("*/*_N*.dx")):
        assert not violating_pairs(pkg), pkg
        checked += 1
    if not checked:
        print("skip: no cached actor-parity packages")


if __name__ == "__main__":
    n = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_") and callable(f):
            f(); n += 1; print(f"ok {k}")
    print(f"{n} passed")
