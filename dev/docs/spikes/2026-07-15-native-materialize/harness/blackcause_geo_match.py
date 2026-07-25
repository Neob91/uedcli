#!/usr/bin/env python3
"""Geometry-matched, VALUE-level lightmap comparison: NativeCastle.dx vs Test_Castle.dx.

Matches each native surf to its editor TWIN by GEOMETRY (plane + texture + centroid),
NOT by array index (the two Models order their 485 surfs differently). Then compares the
ACTUAL baked lightmap content (set-bit count) to find the true native-dark-but-editor-lit
regressions. Settles the residual-black diagnosis conclusively (spike section 20 §18)."""
import sys, os, math

HARN = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl"
sys.path.insert(0, os.path.join(HARN, "dev/docs/spikes/bspspike"))
sys.path.insert(0, os.path.join(HARN, "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))
sys.path.insert(0, HARN)

import umodel_parser as UP
from uedctl.native import umodel as UM
import utexture_decode as UT

NAT = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCastle.dx"
ED = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"


def load(path):
    exps = UP.find_model_exports(path)
    # pick the Model export with the most surfs (the real world model)
    buf = open(path, "rb").read()
    best = None
    for (i, name, size, offset) in exps:
        try:
            m = UM.parse_model_body(buf, offset, size)
        except Exception:
            continue
        if best is None or len(m.surfs) > len(best[0].surfs):
            best = (m, name, size, offset)
    m = best[0]
    pkg = UT.load_package(path)
    return m, pkg


def tex_name(pkg, ref):
    if ref == 0:
        return "<none>"
    n = pkg.name_of_ref(ref)
    return n or f"<ref{ref}>"


def surf_verts(m):
    """Gather each surf's node-vertex world positions."""
    sv = [[] for _ in m.surfs]
    for n in m.nodes:
        si = n.i_surf
        if si < 0 or si >= len(m.surfs):
            continue
        for k in range(n.num_vertices):
            vi = m.verts[n.i_vert_pool + k].i_vertex
            sv[si].append(m.points[vi])
    return sv


def set_bits_of_record(m, rec):
    """Total set bits across all light planes of a record. Correctly walks the light run
    (terminator is 0 on-disk / -1 in native in-memory; both handled). Returns (nbits, nlights,
    total_lumel_planes_bytes)."""
    if rec is None:
        return -1, -1, 0
    if rec.i_light_actors < 0:
        return 0, 0, 0  # dark record: no run
    # count lights in run until NULL terminator (0) or -1
    n = 0
    j = rec.i_light_actors
    while j < len(m.lights):
        v = m.lights[j]
        if v == 0 or v == -1:
            break
        n += 1
        j += 1
    row_bytes = (rec.u_size + 7) // 8
    plane_bytes = row_bytes * rec.v_size
    total = n * plane_bytes
    span = m.light_bits[rec.data_offset: rec.data_offset + total]
    nbits = sum(bin(b).count("1") for b in span)
    return nbits, n, total


def describe(m, pkg, sv, si):
    s = m.surfs[si]
    nrm = m.vectors[s.v_normal]
    base = m.points[s.p_base]
    dist = nrm[0] * base[0] + nrm[1] * base[1] + nrm[2] * base[2]
    vs = sv[si]
    if vs:
        cx = sum(v[0] for v in vs) / len(vs)
        cy = sum(v[1] for v in vs) / len(vs)
        cz = sum(v[2] for v in vs) / len(vs)
        # area estimate via bounding extent
        ext = max(math.dist(a, (cx, cy, cz)) for a in vs)
    else:
        cx = cy = cz = 0.0
        ext = 0.0
    rec = m.light_map[s.i_light_map] if 0 <= s.i_light_map < len(m.light_map) else None
    nbits, nlights, total = set_bits_of_record(m, rec)
    return dict(
        si=si, normal=nrm, dist=dist, centroid=(cx, cy, cz), reach=ext,
        tex=tex_name(pkg, s.texture_ref), pf=s.poly_flags,
        i_light_map=s.i_light_map, nbits=nbits, nlights=nlights,
        lumelbytes=total, nverts=len(vs),
    )


def main():
    m_n, pkg_n = load(NAT)
    m_e, pkg_e = load(ED)
    sv_n = surf_verts(m_n)
    sv_e = surf_verts(m_e)

    dn = [describe(m_n, pkg_n, sv_n, si) for si in range(len(m_n.surfs))]
    de = [describe(m_e, pkg_e, sv_e, si) for si in range(len(m_e.surfs))]

    print(f"NATIVE surfs={len(dn)}  EDITOR surfs={len(de)}")

    def is_lightmapped(d):
        return d["i_light_map"] >= 0

    def is_dark(d):
        # render-black: lightmapped AND zero set bits
        return is_lightmapped(d) and d["nbits"] == 0

    n_lm = sum(is_lightmapped(d) for d in dn)
    e_lm = sum(is_lightmapped(d) for d in de)
    n_dark = sum(is_dark(d) for d in dn)
    e_dark = sum(is_dark(d) for d in de)
    print(f"NATIVE: lightmapped={n_lm}  render-dark(zero bits)={n_dark}  unlit(iLM=-1)={len(dn)-n_lm}")
    print(f"EDITOR: lightmapped={e_lm}  render-dark(zero bits)={e_dark}  unlit(iLM=-1)={len(de)-e_lm}")

    # Geometry match: for each native surf, find best editor twin.
    # Criteria: same texture; normal within 1e-2 (cos); plane dist within 2u; centroid within tol.
    def norm_unit(v):
        L = math.sqrt(sum(c * c for c in v)) or 1.0
        return (v[0] / L, v[1] / L, v[2] / L)

    matched = 0
    regressions = []       # native dark, editor lit
    inverse = []           # native lit, editor dark (for symmetry)
    both_dark = 0
    both_lit = 0
    unmatched = []

    for d in dn:
        nu = norm_unit(d["normal"])
        best = None
        bestscore = 1e18
        for e in de:
            if e["tex"] != d["tex"]:
                continue
            eu = norm_unit(e["normal"])
            cosd = nu[0] * eu[0] + nu[1] * eu[1] + nu[2] * eu[2]
            if cosd < 0.999:
                continue
            if abs(e["dist"] - d["dist"]) > 2.0:
                continue
            cd = math.dist(e["centroid"], d["centroid"])
            if cd < bestscore:
                bestscore = cd
                best = e
        if best is None or bestscore > 64.0:
            unmatched.append(d)
            continue
        matched += 1
        nd = is_dark(d)
        ed = is_dark(best)
        if nd and not ed:
            regressions.append((d, best, bestscore))
        elif ed and not nd:
            inverse.append((d, best, bestscore))
        elif nd and ed:
            both_dark += 1
        else:
            both_lit += 1

    print(f"\n=== GEOMETRY MATCH (native->editor twin) ===")
    print(f"native surfs matched to an editor twin: {matched}/{len(dn)}  (unmatched {len(unmatched)})")
    print(f"  both lit: {both_lit}   both dark: {both_dark}")
    print(f"  TRUE REGRESSIONS (native dark, editor LIT): {len(regressions)}")
    print(f"  inverse (native lit, editor dark):          {len(inverse)}")

    print(f"\n=== TRUE REGRESSIONS (native-dark but editor-twin-lit) ===")
    regressions.sort(key=lambda r: -r[0]["reach"])
    for d, e, sc in regressions:
        area = d["reach"] ** 2
        print(f" nat#{d['si']:>3} tex={d['tex']:<22} pf=0x{d['pf']:06x} "
              f"centroid=({d['centroid'][0]:+.0f},{d['centroid'][1]:+.0f},{d['centroid'][2]:+.0f}) "
              f"reach={d['reach']:.0f} nbits={d['nbits']} nlights={d['nlights']} "
              f"| ed#{e['si']} nbits={e['nbits']} nlights={e['nlights']} match_d={sc:.1f}")

    print(f"\n=== NATIVE render-dark surfs by size (top 25) ===")
    ddark = sorted([d for d in dn if is_dark(d)], key=lambda d: -d["reach"])
    for d in ddark[:25]:
        print(f" nat#{d['si']:>3} tex={d['tex']:<22} pf=0x{d['pf']:06x} "
              f"reach={d['reach']:.0f} centroid=({d['centroid'][0]:+.0f},{d['centroid'][1]:+.0f},{d['centroid'][2]:+.0f}) "
              f"iLM={d['i_light_map']} nlights={d['nlights']}")

    print(f"\n=== unmatched native surfs (top 15 by reach) ===")
    unmatched.sort(key=lambda d: -d["reach"])
    for d in unmatched[:15]:
        print(f" nat#{d['si']:>3} tex={d['tex']:<22} pf=0x{d['pf']:06x} reach={d['reach']:.0f} "
              f"dark={is_dark(d)} centroid=({d['centroid'][0]:+.0f},{d['centroid'][1]:+.0f},{d['centroid'][2]:+.0f})")


if __name__ == "__main__":
    main()
