#!/usr/bin/env python3
"""Field-by-field compare our lit surfaces (NativeLit.dx) against a REAL lit map's
genuine lit records (Entry.dx) — hunting the emission divergence that makes the
render-time lightmap-projection matrix M degenerate (spike section 20 §13)."""
import sys, os, math

HARN = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HARN, "..", "..", "bspspike"))
# uedcli package (native.umodel) — repo root is Tools/uedcli
sys.path.insert(0, os.path.abspath(os.path.join(HARN, "..", "..", "..", "..", "..")))

import umodel_parser as UP  # noqa
from uedcli.native import umodel as UM  # noqa


def load_model(path):
    exps = UP.find_model_exports(path)
    i, name, size, offset = exps[0]
    buf = open(path, "rb").read()
    m = UM.parse_model_body(buf, offset, size)
    return m, name, size, offset


def vlen(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def describe_surf(m, si, label):
    s = m.surfs[si]
    n = m.vectors[s.v_normal]
    u = m.vectors[s.v_texture_u]
    v = m.vectors[s.v_texture_v]
    base = m.points[s.p_base]
    rec = m.light_map[s.i_light_map] if 0 <= s.i_light_map < len(m.light_map) else None
    print(f"  [{label}] surf#{si}  iLightMap={s.i_light_map}")
    print(f"      poly_flags=0x{s.poly_flags:08x}  texture_ref={s.texture_ref}  "
          f"i_zone={s.i_zone}  p_base={s.p_base} v_normal={s.v_normal} "
          f"v_tu={s.v_texture_u} v_tv={s.v_texture_v}")
    print(f"      N   = ({n[0]:+.5f},{n[1]:+.5f},{n[2]:+.5f})  |N|={vlen(n):.5f}")
    print(f"      TU  = ({u[0]:+.5f},{u[1]:+.5f},{u[2]:+.5f})  |TU|={vlen(u):.5f}")
    print(f"      TV  = ({v[0]:+.5f},{v[1]:+.5f},{v[2]:+.5f})  |TV|={vlen(v):.5f}")
    print(f"      base= ({base[0]:+.2f},{base[1]:+.2f},{base[2]:+.2f})")
    # orthogonality / handedness diagnostics
    uxv = cross(u, v)
    print(f"      TU.TV={dot(u,v):+.5f}  TU.N={dot(u,n):+.5f}  TV.N={dot(v,n):+.5f}  "
          f"|TU x TV|={vlen(uxv):.5f}  (TUxTV).N={dot(uxv,n):+.5f}")
    if rec:
        print(f"      REC DataOffset={rec.data_offset} iLightActors={rec.i_light_actors} "
              f"Pan=({rec.pan[0]:+.4f},{rec.pan[1]:+.4f},{rec.pan[2]:+.4f})")
        print(f"          USize={rec.u_size} VSize={rec.v_size} "
              f"UScale={rec.u_scale:.5f} VScale={rec.v_scale:.5f}")
        # The render builds M from texture basis scaled by 1/UScale,1/VScale (hypothesis).
        # Report the would-be scaled axes' lengths.
        if rec.u_scale != 0 and rec.v_scale != 0:
            print(f"          |TU|/UScale={vlen(u)/rec.u_scale:.6f}  "
                  f"|TV|/VScale={vlen(v)/rec.v_scale:.6f}")
    return s, rec, n, u, v, base


def lit_surfs(m):
    """surf indices whose record has iLightActors>=0 (genuine lit)."""
    out = []
    for si, s in enumerate(m.surfs):
        if 0 <= s.i_light_map < len(m.light_map):
            rec = m.light_map[s.i_light_map]
            if rec.i_light_actors >= 0:
                out.append(si)
    return out


def summarize(path, tag):
    print("=" * 78)
    m, name, size, offset = load_model(path)
    print(f"{tag}: {os.path.basename(path)}  Model={name} size={size} off={offset:#x}")
    print(f"  Vectors={len(m.vectors)} Points={len(m.points)} Nodes={len(m.nodes)} "
          f"Surfs={len(m.surfs)} LightMap={len(m.light_map)} "
          f"LightBits={len(m.light_bits)} Lights={len(m.lights)}")
    # Vectors/Points ranges
    def rng(arr):
        if not arr:
            return "empty"
        xs = [c for v in arr for c in v]
        return f"[{min(xs):.2f},{max(xs):.2f}]"
    print(f"  Vectors comp range={rng(m.vectors)}  Points comp range={rng(m.points)}")
    lit = lit_surfs(m)
    dark = sum(1 for s in m.surfs if 0 <= s.i_light_map < len(m.light_map)
               and m.light_map[s.i_light_map].i_light_actors < 0)
    unlit = sum(1 for s in m.surfs if s.i_light_map < 0)
    print(f"  lit surfs (iLA>=0): {len(lit)}   dark records: {dark}   unlit(iLM=-1): {unlit}")
    print(f"  Model.Lights sample: {m.lights[:12]}")
    return m, lit


def main():
    nat_path = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeLit.dx"
    ent_path = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Entry.dx"
    m_nat, lit_nat = summarize(nat_path, "OURS")
    print()
    m_ent, lit_ent = summarize(ent_path, "REAL")

    print("\n" + "#" * 78)
    print("# OUR lit surfaces (all)")
    print("#" * 78)
    for si in lit_nat:
        describe_surf(m_nat, si, "OURS")
        print()

    print("#" * 78)
    print("# REAL lit surfaces (Entry.dx, all iLA>=0)")
    print("#" * 78)
    for si in lit_ent:
        describe_surf(m_ent, si, "REAL")
        print()


if __name__ == "__main__":
    main()
