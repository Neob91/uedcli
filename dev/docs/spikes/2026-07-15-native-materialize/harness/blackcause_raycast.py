#!/usr/bin/env python3
"""Raycast the four preview poses into BOTH the native and editor Models and classify each
pixel's hit surface as baked-DARK / LIT / VOID(miss). Distinguishes the two black causes:
  - hit a baked-DARK surface  -> lighting-bake black (texture x 0)
  - hit NOTHING (void)         -> surface not drawn / backdrop black (render/topology)
Uses the EXACT game camera basis (uedcli.rotation) + 75deg H-FOV, aspect 1280x960."""
import sys, os, math

HARN = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli"
sys.path.insert(0, os.path.join(HARN, "dev/docs/spikes/bspspike"))
sys.path.insert(0, os.path.join(HARN, "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
sys.path.insert(0, HARN)

import umodel_parser as UP
from uedcli.native import umodel as UM
from uedcli.rotation import deg_to_uu, euler_to_matrix_uu, matvec
from PIL import Image

NAT = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCastle.dx"
ED = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"
POSES = {
    "s76": ((0.0, 0.0, 120.0), -89.0, 0.0),
    "s34": ((0.0, 200.0, 60.0), -20.0, 90.0),
    "s69": ((0.0, 455.0, 10.0), -15.0, 90.0),
    "s07": ((0.0, 0.0, 50.0), 0.0, 270.0),
}
# Pure-Python brute-force ray/tri is slow: 200x150 x4 poses x2 models ~ 15 min; 120x90 ~ 4 min.
W, H = 120, 90
HFOV = 75.0


def load(path):
    exps = UP.find_model_exports(path)
    buf = open(path, "rb").read()
    best = None
    for (i, name, size, offset) in exps:
        try:
            m = UM.parse_model_body(buf, offset, size)
        except Exception:
            continue
        if best is None or len(m.surfs) > len(best.surfs):
            best = m
    return best


def set_bits(m, rec):
    if rec is None or rec.i_light_actors < 0:
        return 0
    n = 0; j = rec.i_light_actors
    while j < len(m.lights):
        v = m.lights[j]
        if v == 0 or v == -1:
            break
        n += 1; j += 1
    rb = (rec.u_size + 7) // 8
    span = m.light_bits[rec.data_offset: rec.data_offset + n * rb * rec.v_size]
    return sum(bin(b).count("1") for b in span)


def surf_state(m):
    st = {}
    for si, s in enumerate(m.surfs):
        if s.i_light_map < 0:
            st[si] = "unlit"
        else:
            rec = m.light_map[s.i_light_map] if s.i_light_map < len(m.light_map) else None
            st[si] = "dark" if set_bits(m, rec) == 0 else "lit"
    return st


def tris(m):
    T0, E1, E2, SI = [], [], [], []
    for n in m.nodes:
        si = n.i_surf
        if si < 0 or si >= len(m.surfs):
            continue
        pts = [m.points[m.verts[n.i_vert_pool + k].i_vertex] for k in range(n.num_vertices)]
        for k in range(1, len(pts) - 1):
            a, b, c = pts[0], pts[k], pts[k + 1]
            T0.append(a)
            E1.append((b[0]-a[0], b[1]-a[1], b[2]-a[2]))
            E2.append((c[0]-a[0], c[1]-a[1], c[2]-a[2]))
            SI.append(si)
    return T0, E1, E2, SI


def cast(m, T0, E1, E2, SI, st, eye, pitch, yaw):
    R = euler_to_matrix_uu(deg_to_uu(pitch), deg_to_uu(yaw), 0)
    fwd = matvec(R, (1.0, 0.0, 0.0)); right = matvec(R, (0.0, 1.0, 0.0)); up = matvec(R, (0.0, 0.0, 1.0))
    sx = math.tan(math.radians(HFOV)/2.0); sy = sx*(H/W)
    ntri = len(SI)
    ex, ey, ez = eye
    counts = {"lit": 0, "dark": 0, "unlit": 0, "void": 0}
    hit = [None]*(W*H)
    for py in range(H):
        ndc_y = 1.0 - (py+0.5)/H*2.0
        uy = ndc_y*sy
        for px in range(W):
            ndc_x = (px+0.5)/W*2.0 - 1.0
            ux = ndc_x*sx
            dx = fwd[0]+ux*right[0]+uy*up[0]
            dy = fwd[1]+ux*right[1]+uy*up[1]
            dz = fwd[2]+ux*right[2]+uy*up[2]
            bestt = 1e30; bestsi = -1
            for i in range(ntri):
                e1 = E1[i]; e2 = E2[i]
                # p = d x e2
                px_ = dy*e2[2]-dz*e2[1]; py_ = dz*e2[0]-dx*e2[2]; pz_ = dx*e2[1]-dy*e2[0]
                det = e1[0]*px_+e1[1]*py_+e1[2]*pz_
                if -1e-7 < det < 1e-7:
                    continue
                inv = 1.0/det
                t0 = T0[i]
                tvx = ex-t0[0]; tvy = ey-t0[1]; tvz = ez-t0[2]
                u = (tvx*px_+tvy*py_+tvz*pz_)*inv
                if u < -1e-4 or u > 1.0001:
                    continue
                qx = tvy*e1[2]-tvz*e1[1]; qy = tvz*e1[0]-tvx*e1[2]; qz = tvx*e1[1]-tvy*e1[0]
                v = (dx*qx+dy*qy+dz*qz)*inv
                if v < -1e-4 or u+v > 1.0001:
                    continue
                t = (e2[0]*qx+e2[1]*qy+e2[2]*qz)*inv
                if 1e-3 < t < bestt:
                    bestt = t; bestsi = i
            if bestsi < 0:
                counts["void"] += 1; hit[py*W+px] = ("void", -1)
            else:
                si = SI[bestsi]; s = st[si]
                counts[s] += 1; hit[py*W+px] = (s, si)
    return counts, hit


COL = {"lit": (180, 180, 180), "dark": (0, 0, 0), "unlit": (60, 60, 120), "void": (200, 0, 200)}


def savepng(hit, path):
    img = Image.new("RGB", (W, H))
    img.putdata([COL[h[0]] for h in hit])
    img.save(path)


def main():
    os.makedirs(os.path.join(HARN, "_scratch/blackfix/rc"), exist_ok=True)
    m_n = load(NAT); m_e = load(ED)
    stn = surf_state(m_n); ste = surf_state(m_e)
    tn = tris(m_n); te = tris(m_e)
    print(f"native tris={len(tn[3])} editor tris={len(te[3])}", flush=True)
    for name, (eye, pitch, yaw) in POSES.items():
        cn, hn = cast(m_n, *tn, stn, eye, pitch, yaw)
        ce, he = cast(m_e, *te, ste, eye, pitch, yaw)
        tot = W*H
        pn = {k: f"{100*v/tot:.1f}%" for k, v in cn.items()}
        pe = {k: f"{100*v/tot:.1f}%" for k, v in ce.items()}
        print(f"\n[{name}] eye={eye} pitch={pitch} yaw={yaw}", flush=True)
        print(f"  NATIVE {pn}", flush=True)
        print(f"  EDITOR {pe}", flush=True)
        cd = {"lit": 0, "dark": 0, "unlit": 0, "void": 0}
        cv = {"lit": 0, "dark": 0, "unlit": 0, "void": 0}
        for i in range(tot):
            nk = hn[i][0]
            if nk == "dark":
                cd[he[i][0]] += 1
            elif nk == "void":
                cv[he[i][0]] += 1
        print(f"    native-DARK pixels -> editor hits: {cd}", flush=True)
        print(f"    native-VOID pixels -> editor hits: {cv}", flush=True)
        from collections import Counter
        blk = Counter(hn[i][1] for i in range(tot) if hn[i][0] == "dark")
        print(f"    top native DARK surfs: {blk.most_common(8)}", flush=True)
        savepng(hn, os.path.join(HARN, f"_scratch/blackfix/rc/{name}_nat.png"))
        savepng(he, os.path.join(HARN, f"_scratch/blackfix/rc/{name}_ed.png"))


if __name__ == "__main__":
    main()
