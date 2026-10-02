#!/usr/bin/env python3
"""Diff two built packages' per-(lightmap, light) shadow BIT PLANES lumel by lumel.

`lightrun_diff.py` answers "which lights does each surf list"; this answers "which LUMELS of a
listed light's plane differ", which is what a `LightBits`-only divergence needs.

Usage: lightbits_diff.py <a.dx> <b.dx> [model-name]     # default Model2
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import model_dump as md  # noqa: E402
import parity_gate as pg  # noqa: E402


def records(dec: dict) -> list[dict]:
    out = []
    for i, (raw, u_size, v_size, tail) in enumerate(dec["lightmap"]):
        off = struct.unpack_from("<i", raw, 0)[0]
        pan = struct.unpack_from("<3f", raw, 4)
        u_scale, v_scale, i_light = struct.unpack_from("<ffi", tail, 0)
        out.append(dict(idx=i, off=off, pan=pan, u_size=u_size, v_size=v_size,
                        u_scale=u_scale, v_scale=v_scale, i_light=i_light))
    return out


def run_of(dec: dict, i_light: int) -> list[int]:
    """The NULL-terminated light run at `i_light`. `Model.Lights` holds export object refs after
    Python assembly, so the terminator is 0 (NULL), not -1."""
    if i_light < 0:
        return []
    run = []
    k = i_light
    while k < len(dec["lights"]) and dec["lights"][k] != 0:
        run.append(dec["lights"][k])
        k += 1
    return run


def planes(dec: dict, rec: dict) -> list[bytes]:
    """One packed bit plane per light in this record's run."""
    row = (rec["u_size"] + 7) // 8
    size = row * rec["v_size"]
    n = len(run_of(dec, rec["i_light"]))
    return [bytes(dec["lightbits"][rec["off"] + k * size: rec["off"] + (k + 1) * size])
            for k in range(n)]


def lumels(plane: bytes, u_size: int, v_size: int) -> list[list[int]]:
    row = (u_size + 7) // 8
    return [[(plane[v * row + (u >> 3)] >> (u & 7)) & 1 for u in range(u_size)]
            for v in range(v_size)]


def main() -> int:
    a, b = sys.argv[1], sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else "Model2"
    P, Q = pg.load_package(a), pg.load_package(b)
    da, db = md.decode(P, md.find(P, name)), md.decode(Q, md.find(Q, name))

    ra, rb = records(da), records(db)
    print(f"lightmap records {len(ra)} vs {len(rb)}; lights {len(da['lights'])} vs "
          f"{len(db['lights'])}; lightbits {len(da['lightbits'])} vs {len(db['lightbits'])}")
    # surf -> lightmap record, both sides (model_dump's surf tuple is
    # (texture, poly_flags, ci[6], pan_bytes, i_actor); ci[4] is iLightMap)
    surf_of_a = {s[2][4]: i for i, s in enumerate(da["surfs"]) if s[2][4] >= 0}
    surf_of_b = {s[2][4]: i for i, s in enumerate(db["surfs"]) if s[2][4] >= 0}

    ndiff = 0
    for i in range(min(len(ra), len(rb))):
        A, B = ra[i], rb[i]
        runa, runb = run_of(da, A["i_light"]), run_of(db, B["i_light"])
        geom_same = (A["u_size"], A["v_size"], A["u_scale"], A["v_scale"], A["pan"]) == \
                    (B["u_size"], B["v_size"], B["u_scale"], B["v_scale"], B["pan"])
        pa, pb = planes(da, A), planes(db, B)
        if len(runa) == len(runb) and pa == pb and geom_same:
            continue
        ndiff += 1
        print(f"\n== record {i}  surf {surf_of_a.get(i)}/{surf_of_b.get(i)}  "
              f"grid {A['u_size']}x{A['v_size']} vs {B['u_size']}x{B['v_size']}  "
              f"pan {A['pan']} vs {B['pan']}")
        if len(runa) != len(runb):
            print(f"   RUN LENGTH differs: {len(runa)} vs {len(runb)}  "
                  f"(refs {runa} vs {runb})")
        for k in range(min(len(pa), len(pb))):
            if pa[k] == pb[k]:
                continue
            la = lumels(pa[k], A["u_size"], A["v_size"])
            lb = lumels(pb[k], B["u_size"], B["v_size"])
            cells = [(v, u) for v in range(min(len(la), len(lb)))
                     for u in range(min(len(la[v]), len(lb[v]))) if la[v][u] != lb[v][u]]
            print(f"   light {runa[k] if k < len(runa) else '?'}: "
                  f"{sum(1 for x, y in zip(pa[k], pb[k]) if x != y)} differing bytes, "
                  f"{len(cells)} differing lumels")
            for v, u in cells[:40]:
                print(f"      lumel (u={u},v={v}) a={la[v][u]} b={lb[v][u]}")
            if len(cells) > 40:
                print(f"      ... {len(cells) - 40} more")
    print(f"\n{ndiff} differing records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
