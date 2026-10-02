#!/usr/bin/env python3
"""Sort FLightMapIndex records by DataOffset and measure the true per-lightmap
byte size (offset gap), correlating it against f1c/f20 to pin the exact
row/size layout and per-lumel byte count.

The DECISIVE proof of the 1-bit/lumel/light format is `proof()` below: for every
unique-offset record the byte span to the next offset is exactly divisible by
ceil(USize/8)*VSize, and the quotient (=number of lights) equals the length of
the NULL-terminated iLightActors run in the Model->Lights (0xe4) array."""
import sys, os, collections
import lightmap_decode as LD
import umodel_parser as UP


def _full_walk(p):
    """Walk the whole Model body, returning surfs, FLightMapIndex recs, LightBits,
    and the 0xe4 Lights TArray<AActor*> (ci obj-refs)."""
    buf = open(p, "rb").read(); exp = UP.find_model_exports(p)[0]
    off, size = exp[3], exp[2]; data = buf[off:off+size]
    pos = UP._PREFIX
    _, pos = UP._parse_fvector_array(data, pos)      # Vectors
    _, pos = UP._parse_fvector_array(data, pos)      # Points
    _, pos = UP._parse_array(data, pos, UP._parse_node, "N")
    surfs, pos = UP._parse_array(data, pos, UP._parse_surf, "S")
    _, pos = UP._parse_array(data, pos, UP._parse_vert, "V")
    _, pos = UP._i32(data, pos); nz, pos = UP._i32(data, pos)
    pos = UP._skip_zone_data(data, pos, nz)
    _, pos = UP._ci(data, pos)                        # field_0x54
    cnt, pos = UP._ci(data, pos); recs = []
    for _ in range(cnt):
        r, pos = LD.parse_lightmap_index(data, pos); recs.append(r)
    bc, pos = UP._ci(data, pos); lumels = data[pos:pos+bc]; pos += bc
    cc, pos = UP._ci(data, pos); pos += cc * 25       # 0xc0 Bounds FBox
    lh, pos = UP._ci(data, pos); pos += lh * 4        # 0xcc LeafHulls INT
    _, pos = UP._parse_array(data, pos, UP._parse_leaf, "L")   # 0xd8 Leaves
    lgc, pos = UP._ci(data, pos); lights = []         # 0xe4 Lights TArray<AActor*>
    for _ in range(lgc):
        v, pos = UP._ci(data, pos); lights.append(v)
    return surfs, recs, lumels, lights


def proof(path):
    surfs, recs, lumels, lights = _full_walk(path)
    c = collections.Counter(r["DataOffset"] for r in recs)
    uoff = sorted(set(r["DataOffset"] for r in recs))
    gaps = {o: (uoff[i+1] if i+1 < len(uoff) else len(lumels)) - o for i, o in enumerate(uoff)}
    uniq = set(o for o, n in c.items() if n == 1)
    div = tot = runok = 0; qd = collections.Counter()
    for r in recs:
        o = r["DataOffset"]
        if o in uniq and o != 0:
            row = ((r["f1c"] + 7) // 8) * r["f20"]      # ceil(USize/8)*VSize bytes/light
            g = gaps[o]; tot += 1
            if row and g % row == 0:
                div += 1; N = g // row; qd[N] += 1
                base = r["f04"]                          # iLightActors
                if 0 <= base < len(lights):
                    k = 0
                    while base + k < len(lights) and lights[base + k] != 0:
                        k += 1
                    if k == N:
                        runok += 1
    print(f"\n=== PROOF ({os.path.basename(path)}) ===")
    print(f"  Lights(0xe4).Num={len(lights)}  unique-offset non-dark recs={tot}")
    print(f"  gap %% (ceil(USize/8)*VSize) == 0 : {div}/{tot}")
    print(f"  iLightActors run-length == numLights: {runok}/{tot}")
    print(f"  numLights distribution: {dict(sorted(qd.items())[:12])}")

def analyze(path):
    recs, lumels, surfs = LD.main(path)
    print("\n===== DataOffset-sorted gap analysis =====")
    order = sorted(range(len(recs)), key=lambda i: recs[i]["DataOffset"])
    # gaps
    rows = []
    for k in range(len(order)):
        i = order[k]
        r = recs[i]
        if k + 1 < len(order):
            nxt = recs[order[k+1]]["DataOffset"]
        else:
            nxt = len(lumels)
        gap = nxt - r["DataOffset"]
        rows.append((r["DataOffset"], gap, r["f1c"], r["f20"], r["f14"], r["f18"], r["f04"]))
    # Test hypotheses for gap:
    #  gap == f1c*f20         (1 byte/lumel, USize x VSize)
    #  gap == f1c*f20*3       (RGB)
    #  gap == ceil(f1c/?)*f20 (row padding)
    import math
    tests = {
        "f1c*f20": lambda f1c,f20: f1c*f20,
        "f1c*f20*3": lambda f1c,f20: f1c*f20*3,
        "(f1c)*f20 rowpad4": lambda f1c,f20: (((f1c+3)//4)*4)*f20,
        "f1c*(f20 pad)": lambda f1c,f20: f1c*(((f20+3)//4)*4),
        "(f1c+1)*(f20+1)": lambda f1c,f20: (f1c+1)*(f20+1),
    }
    for name, fn in tests.items():
        exact = sum(1 for (do,gap,f1c,f20,a,b,c) in rows if gap == fn(f1c,f20))
        print(f"  gap == {name:20s}: {exact}/{len(rows)} exact")
    # show the gap vs f1c*f20 delta distribution
    import collections
    deltas = collections.Counter()
    for (do,gap,f1c,f20,a,b,c) in rows:
        deltas[gap - f1c*f20] += 1
    print("  gap - f1c*f20 delta distribution (top 15):",
          dict(sorted(deltas.items(), key=lambda x:-x[1])[:15]))
    # per-row: is gap divisible by f20? by f1c?
    print("  sample sorted rows (DataOffset, gap, f1c(USize?), f20(VSize?), gap/f20, gap/f1c):")
    for (do,gap,f1c,f20,a,b,c) in rows[:12]:
        gd20 = gap/f20 if f20 else 0
        gd1c = gap/f1c if f1c else 0
        print(f"    off={do:>8} gap={gap:>6} f1c={f1c:>4} f20={f20:>4} gap/f20={gd20:.2f} gap/f1c={gd1c:.2f}")
    # Sum of gaps == total?
    print(f"  Sum(gap)={sum(g for _,g,_,_,_,_,_ in rows)}  total={len(lumels)}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/00_Intro.dx"
    analyze(path)
    proof(path)
