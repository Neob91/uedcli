#!/usr/bin/env python3
"""Check whether native bspcsg surfs have FLIPPED normals vs the editor twins. A flipped
surf normal -> game backface-culls the surface (undrawn -> black void) AND the bake's
backface cull lists the wrong lights. Match native->editor by plane POSITION (|cos|>0.999,
either sign) + texture + centroid, then report sign agreement."""
import sys, os, math
HARN = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli"
sys.path.insert(0, os.path.join(HARN, "dev/docs/spikes/bspspike"))
sys.path.insert(0, os.path.join(HARN, "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
sys.path.insert(0, HARN)
import umodel_parser as UP
from uedcli.native import umodel as UM
import utexture_decode as UT

def load(p):
    exps = UP.find_model_exports(p); buf = open(p, "rb").read(); best = None
    for (i, name, size, off) in exps:
        try: m = UM.parse_model_body(buf, off, size)
        except: continue
        if best is None or len(m.surfs) > len(best.surfs): best = m
    return best, UT.load_package(p)

def unit(v):
    L = math.sqrt(sum(c*c for c in v)) or 1.0
    return (v[0]/L, v[1]/L, v[2]/L)

def surf_centroids(m):
    sv = [[] for _ in m.surfs]
    for n in m.nodes:
        si = n.i_surf
        if 0 <= si < len(m.surfs):
            for k in range(n.num_vertices):
                sv[si].append(m.points[m.verts[n.i_vert_pool+k].i_vertex])
    cen = []
    for vs in sv:
        if vs:
            cen.append((sum(v[0] for v in vs)/len(vs), sum(v[1] for v in vs)/len(vs), sum(v[2] for v in vs)/len(vs)))
        else:
            cen.append(None)
    return cen

def texname(pkg, ref):
    return pkg.name_of_ref(ref) or f"<{ref}>" if ref else "<none>"

m_n, pk_n = load("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCastle.dx")
m_e, pk_e = load("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx")
cn = surf_centroids(m_n); ce = surf_centroids(m_e)

# editor surf features
ef = []
for si, s in enumerate(m_e.surfs):
    nu = unit(m_e.vectors[s.v_normal])
    base = m_e.points[s.p_base]
    ef.append((si, nu, texname(pk_e, s.texture_ref), ce[si]))

flipped = 0; aligned = 0; nomatch = 0
flip_list = []
for si, s in enumerate(m_n.surfs):
    nu = unit(m_n.vectors[s.v_normal])
    tex = texname(pk_n, s.texture_ref)
    c = cn[si]
    if c is None:
        continue
    best = None; bestd = 1e18
    for (esi, enu, etex, ec) in ef:
        if etex != tex or ec is None:
            continue
        cosd = nu[0]*enu[0]+nu[1]*enu[1]+nu[2]*enu[2]
        if abs(cosd) < 0.999:
            continue
        d = math.dist(c, ec)
        if d < bestd:
            bestd = d; best = (esi, enu, cosd)
    if best is None or bestd > 48:
        nomatch += 1
        continue
    if best[2] > 0:
        aligned += 1
    else:
        flipped += 1
        flip_list.append((si, tex, c, bestd))

print(f"native surfs: aligned-normal twins={aligned}  FLIPPED-normal twins={flipped}  nomatch={nomatch}")
print("FLIPPED (native normal opposite editor twin) — first 20:")
for (si, tex, c, d) in flip_list[:20]:
    print(f"  nat#{si} tex={tex} centroid=({c[0]:+.0f},{c[1]:+.0f},{c[2]:+.0f}) matchdist={d:.1f}")
