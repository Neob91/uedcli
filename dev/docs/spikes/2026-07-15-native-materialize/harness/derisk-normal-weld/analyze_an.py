#!/usr/bin/env python3
"""§92 §52 — analyze the AN (bspAddNode) dome capture from `rebuild_dome_an.py`.

For each dome-facet bspAddNode FPoly (stored Normal N + polygon Verts, world-pooled):
  * re-localize the verts (subtract Brush755 loc), compute calc_normal, and test == N (the FPoly's
    own stored normal).  If it holds, the stored twin normal IS calc_normal over the re-localized
    pooled verts -> the perturbation SOURCE is the world-CSG bspAddPoint pool, PROVEN.
  * compare N to the golden surf normal (should match; same rebuild) and to calc_normal(exact T3D
    local) (the twin reference) — and report the per-vertex ULP delta pool-vs-exact.

Usage: analyze_an.py [log] [golden.dx]
"""
import sys, struct, math
from collections import Counter, defaultdict
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
    m2 = r32(r32(r32(n[0]*n[0])+r32(n[1]*n[1]))+r32(n[2]*n[2])); inv = r32(1.0/r32(math.sqrt(float(m2))))
    return (r32(n[0]*inv), r32(n[1]*inv), r32(n[2]*inv))


def parse_n(tok):
    a, b, c = tok.split("=")[1].split(","); return (f_of(int(a, 16)), f_of(int(b, 16)), f_of(int(c, 16)))


def main():
    log = sys.argv[1] if len(sys.argv) > 1 else str(ROOT/"_scratch/normfin/dome_an.log")
    gpath = sys.argv[2] if len(sys.argv) > 2 else str(ROOT/"_scratch/uedgolden/UEDGolden_unatco_world.dx")

    level, _ = trunk.read_level(U.FULL_TRUNK)
    a = level.actors["Brush755"]; loc = [float(c) for c in a.location]
    gold = SCD.load_model(gpath)
    gsurfs = [(gold.vectors[s.v_normal],
               sum(gold.vectors[s.v_normal][k]*gold.points[s.p_base][k] for k in range(3)))
              for s in gold.surfs]

    dome = []
    for pi, p in enumerate(a.brush.polys):
        lv = [(r32(float(v[0])), r32(float(v[1])), r32(float(v[2]))) for v in p.vertices]
        dome.append((pi, lv, calc_normal(lv)))

    def match_gold(nl, base_world):
        dw = r32(sum(r32(nl[k]*base_world[k]) for k in range(3)))
        best = None
        for n, off in gsurfs:
            d = sum(n[k]*nl[k] for k in range(3)); s = 1.0 if d >= 0 else -1.0
            if abs(d) < 0.9995 or abs(off - s*dw) > 0.5:
                continue
            sc = abs(abs(d)-1)
            if best is None or sc < best[0]:
                best = (sc, tuple(s*c for c in n))
        return best[1] if best else None

    DX = (506, 574); DY = (1170, 1238); DZ = (242, 310)  # Brush755 dome world box
    in_dome = lambda v: DX[0] < v[0] < DX[1] and DY[0] < v[1] < DY[1] and DZ[0] < v[2] < DZ[1]
    rets = Counter()
    rows = []
    total = 0
    for ln in Path(log).read_text().splitlines():
        if not (ln.startswith("AN ") or ln.startswith("ADD ")):
            continue
        total += 1
        toks = ln.split()
        d = {t.split("=")[0]: t for t in toks if "=" in t}
        ret = int(d.get("ret", "ret=0x0").split("=")[1], 16) if "ret" in d else 0
        nrm = parse_n(d["N"]); base = parse_n(d["B"])
        verts = [(f_of(int(x, 16)), f_of(int(y, 16)), f_of(int(z, 16)))
                 for t in toks if t.startswith("V=") for x, y, z in [t[2:].split(",")]]
        if not verts or not all(in_dome(v) for v in verts):
            continue
        rets[hex(ret)] += 1
        rows.append((ret, nrm, base, verts))
    print(f"total ADD lines: {total}   dome-vert lines: {len(rows)}   ret sites: {dict(rets)}")

    al = lambda ref, t: tuple((1.0 if sum(ref[k]*t[k] for k in range(3)) >= 0 else -1.0)*c for c in t)
    # dedupe by (stored-normal-bits); PREFER the world-CSG phase (ret=0x34924 SubtractBrushFromWorld)
    # whose verts are the pre-final-repartition state the surf normal was computed over.
    seen = {}
    for ret, nrm, base, verts in rows:
        if not verts:
            continue
        key = fb(nrm)
        cur = seen.get(key)
        if cur is None or (ret == 0x10034924 and cur[0] != 0x10034924):
            seen[key] = (ret, nrm, base, verts)

    twin = proven = exact = 0
    gmatch = 0
    ulp_scatter = []
    print("\n=== per dome facet (dedup by stored normal) ===")
    for key, (ret, nrm, base, verts) in sorted(seen.items()):
        # match exact T3D poly by direction
        best = max(dome, key=lambda d: abs(sum(nrm[k]*d[2][k] for k in range(3))))
        pi, lv, nl = best
        nl_a = al(nrm, nl)
        reloc = [(r32(v[0]-loc[0]), r32(v[1]-loc[1]), r32(v[2]-loc[2])) for v in verts]
        cn_reloc = al(nrm, calc_normal(reloc))
        cn_world = al(nrm, calc_normal(verts))
        # plane offset for golden-match: use a captured GEOMETRY vertex (Base is the texture origin)
        gold_n = match_gold(nl, verts[0])
        gold_a = al(nrm, gold_n) if gold_n else None
        is_twin = fb(nl_a) != fb(nrm)
        hit_reloc = fb(cn_reloc) == fb(nrm)
        hit_gold = gold_a is not None and fb(gold_a) == fb(nrm)
        # ULP delta reloc vs exact local
        mx = 0
        for l in lv:
            bb = min(reloc, key=lambda cv: abs(cv[0]-l[0])+abs(cv[1]-l[1])+abs(cv[2]-l[2]))
            for k in range(3):
                mx = max(mx, abs(ibits(bb[k])-ibits(l[k])))
        if gold_a is not None and is_twin:
            for k in range(3):
                if abs(nl_a[k]) > 1e-6:
                    ulp_scatter.append(ibits(nrm[k]) - ibits(nl_a[k]))
        if is_twin:
            twin += 1
            proven += hit_reloc
        else:
            exact += 1
        gmatch += hit_gold
        print(f" poly{pi:2d} nv={len(verts)} ret={hex(ret)} {'TWIN' if is_twin else 'exact'} vertULP={mx}")
        print(f"    stored N (AN)             = {hx(nrm)}   ==golden? {hit_gold}")
        print(f"    calc_normal(exact local)  = {hx(nl_a)}")
        print(f"    calc_normal(RE-LOC pooled)= {hx(cn_reloc)}   ==stored? {hit_reloc}")
        print(f"    calc_normal(WORLD pooled) = {hx(cn_world)}")

    print(f"\nfacets={len(seen)} twins={twin} exact={exact}")
    print(f"AN stored-normal == golden          : {gmatch}/{len(seen)}")
    print(f"calc_normal(RE-LOC pooled)==stored  : {proven}/{twin} twins")
    print(f"twin (stored - exactlocal) ULP scatter: {dict(Counter(ulp_scatter))}")


if __name__ == "__main__":
    main()
