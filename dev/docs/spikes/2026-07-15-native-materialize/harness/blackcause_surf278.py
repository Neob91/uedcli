#!/usr/bin/env python3
"""Characterize the lone lighting regression surf#278 (native dark / editor twin lit):
is it (a) backface-culled (no in-front light) or (b) LOS over-occluded (in-front+in-range
light exists but every lumel fails line_clear)?"""
import sys, os, struct, math
HARN = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli"
sys.path.insert(0, os.path.join(HARN, "dev/docs/spikes/bspspike"))
sys.path.insert(0, os.path.join(HARN, "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
sys.path.insert(0, HARN)
import umodel_parser as UP
from uedcli.native import umodel as UM
from utexture_decode import load_package, ci, read_props

RF_HasStack = 0x02000000

def skip_stateframe(buf, pos):
    node, pos = ci(buf, pos); stnode, pos = ci(buf, pos); pos += 12
    if node != 0:
        _off, pos = ci(buf, pos)
    return pos

def lights_of(path):
    p = load_package(path)
    out = []
    for i, e in enumerate(p.exports):
        c = p.class_of_export(i) or ""
        if "Light" not in c:
            continue
        pos = e["soff"]
        if e["flags"] & RF_HasStack:
            pos = skip_stateframe(p.buf, pos)
        props, _ = read_props(p.buf, pos, e["soff"]+e["ssize"], p.names)
        loc = (0.0, 0.0, 0.0); rad = 0
        if "Location" in props:
            v = props["Location"]
            raw = v[1] if isinstance(v, tuple) else v
            if isinstance(raw, (bytes, bytearray)) and len(raw) >= 12:
                loc = struct.unpack_from("<3f", raw, 0)
        if "LightRadius" in props:
            r = props["LightRadius"]
            rad = r[1] if isinstance(r, tuple) else r
        # LightType present & != None -> participates; assume all these do
        out.append((p.names[e["nm"]], loc, rad))
    return out

def load(path):
    exps = UP.find_model_exports(path); buf = open(path, "rb").read(); best = None
    for (i, n, s, o) in exps:
        try: m = UM.parse_model_body(buf, o, s)
        except: continue
        if best is None or len(m.surfs) > len(best.surfs): best = m
    return best

m = load("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCastle.dx")
lights = lights_of("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCastle.dx")
si = 278
s = m.surfs[si]
nrm = m.vectors[s.v_normal]; base = m.points[s.p_base]
Ln = math.sqrt(sum(c*c for c in nrm))
nu = tuple(c/Ln for c in nrm)
# centroid
vs = []
for n in m.nodes:
    if n.i_surf == si:
        for k in range(n.num_vertices):
            vs.append(m.points[m.verts[n.i_vert_pool+k].i_vertex])
cx = sum(v[0] for v in vs)/len(vs); cy = sum(v[1] for v in vs)/len(vs); cz = sum(v[2] for v in vs)/len(vs)
print(f"surf#{si} tex_ref={s.texture_ref} pf=0x{s.poly_flags:x}")
print(f"  normal(unit)=({nu[0]:+.3f},{nu[1]:+.3f},{nu[2]:+.3f}) base=({base[0]:.1f},{base[1]:.1f},{base[2]:.1f}) centroid=({cx:.0f},{cy:.0f},{cz:.0f})")
print(f"  nlights_total={len(lights)}")
infront = []
for (nm, loc, rad) in lights:
    wr = (rad + 1) * 25.0
    d = math.dist((cx, cy, cz), loc)
    signed = (loc[0]-base[0])*nu[0] + (loc[1]-base[1])*nu[1] + (loc[2]-base[2])*nu[2]
    if signed > 0 and d - 30 <= wr:  # in front & roughly in range of the ~29-reach surf
        infront.append((nm, loc, rad, d, signed, wr))
print(f"  in-front & in-radius lights: {len(infront)}")
for (nm, loc, rad, d, signed, wr) in sorted(infront, key=lambda t: t[3])[:8]:
    print(f"    {nm} loc=({loc[0]:.0f},{loc[1]:.0f},{loc[2]:.0f}) rad={rad} dist={d:.0f} frontdist={signed:.1f} worldR={wr:.0f}")
