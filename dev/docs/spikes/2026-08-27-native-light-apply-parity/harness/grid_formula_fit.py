#!/usr/bin/env python3
"""Fit the editor's lumel-grid-sizing rule against ONE editor-built map — no native side involved.

For every lit `FLightMapIndex` record in an editor build, recompute that record's own surface's
texture-space extent from the map's own geometry (base-relative, per-vertex subtract before the dot,
as spike section 20 §22 pinned) and test each candidate `size = f(extent, lumel_scale)` against the
`UClamp`/`VClamp` the editor actually stored. A formula that is right is right on every record.

This exists because the two candidates in the record disagree on real content:
  A  `clamp(ceil(extent / scale), 2, 256)`                  -- section 20 §22, fitted on Test_Castle
  B  `clamp(trunc((extent - 0.25)/scale - 0.5) + 1, 2, 256)` -- section 20 §4, from the disassembly
They differ only where `extent` sits within 0.25 above an exact multiple of `scale`, which
axis-aligned test geometry never produces and a real level does constantly.

Usage: grid_formula_fit.py EDITOR.dx
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lightparity import _load, level_model  # noqa: E402

PF_INVISIBLE = 0x0000_0001
PF_FAKE_BACKDROP = 0x0000_0080
PF_LOW_SHADOW_DETAIL = 0x0000_8000
PF_UNLIT = 0x0040_0000
PF_HIGH_SHADOW_DETAIL = 0x0080_0000


def lumel_scale(pf: int) -> float:
    if pf & (PF_HIGH_SHADOW_DETAIL | PF_LOW_SHADOW_DETAIL) == \
            (PF_HIGH_SHADOW_DETAIL | PF_LOW_SHADOW_DETAIL):
        return 128.0
    if pf & PF_HIGH_SHADOW_DETAIL:
        return 16.0
    if pf & PF_LOW_SHADOW_DETAIL:
        return 64.0
    return 32.0


def f32(x: float) -> float:
    """Round a Python float to f32, so the fit runs at the precision the engine stores."""
    import struct
    return struct.unpack("<f", struct.pack("<f", x))[0]


def dot32(a, b) -> float:
    """`FVector operator|` — an f32 accumulate of x+y+z, left to right."""
    return f32(f32(f32(a[0] * b[0]) + f32(a[1] * b[1])) + f32(a[2] * b[2]))


CANDIDATES = {
    "A ceil(e/s)": lambda e, s: math.ceil(e / s),
    "B trunc((e-0.25)/s-0.5)+1": lambda e, s: int((e - 0.25) / s - 0.5) + 1,
    "C ceil((e-0.25)/s)": lambda e, s: math.ceil((e - 0.25) / s),
    "D round(e/s)": lambda e, s: int(e / s + 0.5),
    "E trunc(e/s)+1": lambda e, s: int(e / s) + 1,
    "F trunc(e/s-0.5)+1": lambda e, s: int(e / s - 0.5) + 1,
}


def main() -> int:
    repo = str(Path(__file__).resolve().parents[5])
    upackage, umodel = _load(repo)
    _pkg, m = level_model(upackage, umodel, sys.argv[1])

    verts = [[] for _ in m.surfs]
    for n in m.nodes:
        if 0 <= n.i_surf < len(m.surfs):
            for k in range(n.num_vertices):
                verts[n.i_surf].append(m.points[m.verts[n.i_vert_pool + k].i_vertex])

    hits = {k: 0 for k in CANDIDATES}
    scale_hits = {k: 0 for k in CANDIDATES}
    pan_hits = 0
    total = 0
    examples: list[tuple] = []
    for si, s in enumerate(m.surfs):
        if s.i_light_map < 0 or not verts[si]:
            continue
        rec = m.light_map[s.i_light_map]
        base = m.points[s.p_base]
        tu, tv = m.vectors[s.v_texture_u], m.vectors[s.v_texture_v]
        lo = [math.inf, math.inf]
        hi = [-math.inf, -math.inf]
        for v in verts[si]:
            d = (f32(v[0] - base[0]), f32(v[1] - base[1]), f32(v[2] - base[2]))
            for ax, t in enumerate((tu, tv)):
                x = dot32(d, t)
                lo[ax] = min(lo[ax], x)
                hi[ax] = max(hi[ax], x)
        sc = lumel_scale(s.poly_flags)
        pan_hits += (f32(lo[0] - 0.125) == rec.pan[0] and f32(lo[1] - 0.125) == rec.pan[1])
        for ax, (stored_size, stored_scale) in enumerate(
                ((rec.u_size, rec.u_scale), (rec.v_size, rec.v_scale))):
            total += 1
            extent = f32(hi[ax] - lo[ax])
            for name, fn in CANDIDATES.items():
                try:
                    got = max(2, min(256, fn(extent, sc)))
                except (ValueError, OverflowError):
                    continue
                if got == stored_size:
                    hits[name] += 1
                if f32(f32(extent + 0.25) / (got - 1)) == stored_scale:
                    scale_hits[name] += 1
            if max(2, min(256, CANDIDATES["A ceil(e/s)"](extent, sc))) != stored_size \
                    and len(examples) < 12:
                examples.append((si, ax, extent, sc, stored_size, stored_scale))

    print(f"{sys.argv[1]}: {total // 2} lit records, {total} axes")
    print(f"  Pan == min - 0.125 on both axes: {pan_hits}/{total // 2}")
    print(f"  {'formula':28} {'size exact':>12} {'+ scale exact':>14}")
    for name in CANDIDATES:
        print(f"  {name:28} {hits[name]:6}/{total} {scale_hits[name]:8}/{total}")
    if examples:
        print("\n  axes where candidate A (ceil(e/s)) misses:")
        for si, ax, e, sc, size, ssc in examples:
            print(f"    surf {si} axis {'UV'[ax]}: extent={e!r} lumel_scale={sc} "
                  f"stored size={size} stored scale={ssc!r}  e/s={e / sc!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
