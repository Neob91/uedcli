#!/usr/bin/env python3
"""§92 §52 — analyze the rebuild CalcNormal capture (CN entry + NR tail), matched by `this`.

For each dome-facet CalcNormal call (verts in the Brush755 dome box):
  * the INPUT verts (bits) vs exact T3D local (per-component ULP) — the perturbation,
  * calc_normal(INPUT verts) == the NR output normal (validates offline calc_normal), and == the
    golden twin normal (PROVES the input verts are the twin source).

Usage: analyze_cn.py [log] [golden.dx]
"""
import sys, struct, math
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS))
import surf_class_diff as SCD           # noqa: E402
import unatco_subset as U               # noqa: E402
from uedcli import trunk                # noqa: E402

r32 = lambda x: struct.unpack("<f", struct.pack("<f", x))[0]
bits = lambda x: struct.unpack("<I", struct.pack("<f", x))[0]
ibits = lambda x: struct.unpack("<i", struct.pack("<f", x))[0]
f_of = lambda u: struct.unpack("<f", struct.pack("<I", u & 0xFFFFFFFF))[0]
fb = lambda t: tuple(bits(c) for c in t)
hx = lambda t: ",".join(f"{bits(c):#010x}" for c in t)


def cross(a, b):
    return (r32(r32(a[1]*b[2])-r32(a[2]*b[1])), r32(r32(a[2]*b[0])-r32(a[0]*b[2])), r32(r32(a[0]*b[1])-r32(a[1]*b[0])))


def sub(a, b):
    return (r32(a[0]-b[0]), r32(a[1]-b[1]), r32(a[2]-b[2]))


def calc_normal(vs):
    n = [0., 0., 0.]; v0 = vs[0]
    for i in range(2, len(vs)):
        c = cross(sub(vs[i-1], v0), sub(vs[i], v0)); n = [r32(n[0]+c[0]), r32(n[1]+c[1]), r32(n[2]+c[2])]
    m2 = r32(r32(r32(n[0]*n[0])+r32(n[1]*n[1]))+r32(n[2]*n[2]))
    if m2 <= 0:
        return None
    inv = r32(1.0/r32(math.sqrt(float(m2)))); return (r32(n[0]*inv), r32(n[1]*inv), r32(n[2]*inv))


def main():
    log = sys.argv[1] if len(sys.argv) > 1 else str(ROOT/"_scratch/normfin/rebuild_cn/oracle-105.log")
    gpath = sys.argv[2] if len(sys.argv) > 2 else str(ROOT/"_scratch/uedgolden/UEDGolden_unatco_world.dx")

    level, _ = trunk.read_level(U.FULL_TRUNK)
    a = level.actors["Brush755"]; loc = [float(c) for c in a.location]
    gold = SCD.load_model(gpath)
    gN = {}
    for s in gold.surfs:
        if s.i_actor == 2 and s.i_brush_poly not in gN:
            gN[s.i_brush_poly] = gold.vectors[s.v_normal]

    dome = []
    for pi, p in enumerate(a.brush.polys):
        lv = [(r32(float(v[0])), r32(float(v[1])), r32(float(v[2]))) for v in p.vertices]
        c0 = calc_normal(lv)
        if c0:
            dome.append((pi, lv, c0))

    DX = (506, 574); DY = (1170, 1238); DZ = (242, 310)
    in_dome = lambda v: DX[0] < v[0] < DX[1] and DY[0] < v[1] < DY[1] and DZ[0] < v[2] < DZ[1]

    # parse: CN this nv V..., NR this N=...  (match NR to the most recent CN with same this)
    nr = {}
    cn_calls = []
    ntotal = 0
    for ln in Path(log).read_text().splitlines():
        toks = ln.split()
        if ln.startswith("CN "):
            ntotal += 1
            d = {t.split("=")[0]: t for t in toks if "=" in t and not t.startswith("V=")}
            this = int(d["this"].split("=")[1], 16)
            verts = [(f_of(int(x, 16)), f_of(int(y, 16)), f_of(int(z, 16)))
                     for t in toks if t.startswith("V=") for x, y, z in [t[2:].split(",")]]
            cn_calls.append((this, verts))
        elif ln.startswith("NR "):
            d = {t.split("=")[0]: t for t in toks if "=" in t}
            this = int(d["this"].split("=")[1], 16)
            xu, yu, zu = d["N"].split("=")[1].split(",")
            nr[this] = (f_of(int(xu, 16)), f_of(int(yu, 16)), f_of(int(zu, 16)))
    print(f"CN calls total={ntotal}")

    dome_calls = [(t, v) for t, v in cn_calls if v and all(in_dome(w) for w in v)]
    print(f"dome-vert CN calls: {len(dome_calls)}")

    al = lambda ref, x: tuple((1.0 if sum(ref[k]*x[k] for k in range(3)) >= 0 else -1.0)*c for c in x)
    seen = {}
    for this, verts in dome_calls:
        best = max(dome, key=lambda d: abs(sum(d[2][k]*(calc_normal(verts) or (0, 0, 1))[k] for k in range(3))))
        cnv = calc_normal(verts)
        if cnv is None:
            continue
        key = fb(al((1, 1, 1), cnv))
        if key not in seen:
            seen[key] = (this, verts, cnv, best)

    twin = proven_g = proven_nr = 0
    scatter = []
    print("\n=== dome CalcNormal calls (dedup by output normal) ===")
    for key, (this, verts, cnv, best) in sorted(seen.items()):
        pi, lv, nl = best
        # reorient nl & cnv to a common sign via nl
        nl_a = al(nl, nl)
        cnv_a = al(nl, cnv)
        gn = gN.get(pi)
        gn_a = al(nl, gn) if gn else None
        out = nr.get(this)
        out_a = al(nl, out) if out else None
        is_twin = gn_a is not None and fb(nl_a) != fb(gn_a)
        hit_g = gn_a is not None and fb(cnv_a) == fb(gn_a)
        hit_nr = out_a is not None and fb(cnv_a) == fb(out_a)
        mx = 0
        for l in lv:
            bb = min(verts, key=lambda cv: abs(cv[0]-l[0])+abs(cv[1]-l[1])+abs(cv[2]-l[2]))
            for k in range(3):
                mx = max(mx, abs(ibits(bb[k])-ibits(l[k])))
        if is_twin:
            twin += 1; proven_g += hit_g; proven_nr += hit_nr
            for k in range(3):
                if abs(nl_a[k]) > 1e-6:
                    scatter.append(ibits(gn_a[k]) - ibits(nl_a[k]))
        print(f" poly{pi:2d} nv={len(verts)} {'TWIN' if is_twin else 'exact'} vertULP(vs exact-local)={mx}")
        print(f"    INPUT verts (bits): {[hx(v) for v in verts]}")
        print(f"    exact-local verts : {[hx(v) for v in lv]}")
        print(f"    calc_normal(INPUT)= {hx(cnv_a)}")
        print(f"    editor NR output  = {hx(out_a) if out_a else 'n/a'}   ==calc? {hit_nr}")
        print(f"    golden normal     = {hx(gn_a) if gn_a else 'n/a'}   ==calc(INPUT)? {hit_g}")
        print(f"    calc_normal(exact)= {hx(nl_a)}")

    print(f"\ndome facets(dedup)={len(seen)} twins={twin}")
    print(f"calc_normal(INPUT verts) == golden : {proven_g}/{twin} twins   (SOURCE PROVEN if high)")
    print(f"calc_normal(INPUT verts) == editor NR : {proven_nr}/{len([1 for k,(t,v,c,b) in seen.items() if nr.get(t)])} (validates offline calc_normal)")
    print(f"twin ULP scatter: {dict(Counter(scatter))}")


if __name__ == "__main__":
    main()
