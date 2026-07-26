#!/usr/bin/env python3
"""§92 §46 DE-RISK (a): castle slanted-face normal — does WINDING REORDER (the only thing a
brush-model reconstruction can do to a distinct-vert convex brush) reproduce the AUTHORED normal
where calc_normal(raw T3D order) does not?

For every castle brush poly:
  - parse authored Normal + Vertices (local, pre-transform),
  - compute calc_normal(raw local winding) in the exact native f32 op-order,
  - classify axis vs non-axis; for non-axis, measure ULP(calc_raw vs authored),
  - for the 'authored is essentially the winding normal but N ULP off' class (dot>0.9999, N small):
    test whether ANY cyclic rotation OR reversal of the winding gives calc_normal == authored bits.

If NO rotation of a castle slanted face reproduces authored, then (since its verts are distinct →
the brush-model bspAddPoint weld is a no-op → reconstruction only reorders) the '§46 weld' hypothesis
CANNOT make the castle stay byte-exact.  Report that.
"""
import sys, struct, math, re, glob, os

def f32(x): return struct.unpack('<f', struct.pack('<f', x))[0]
def bits(x): return struct.unpack('<I', struct.pack('<f', f32(x)))[0]
def sub(a, b): return (f32(a[0]-b[0]), f32(a[1]-b[1]), f32(a[2]-b[2]))
def cross(a, b):
    return (f32(f32(a[1]*b[2])-f32(a[2]*b[1])),
            f32(f32(a[2]*b[0])-f32(a[0]*b[2])),
            f32(f32(a[0]*b[1])-f32(a[1]*b[0])))
def dot(a, b): return f32(f32(f32(a[0]*b[0])+f32(a[1]*b[1]))+f32(a[2]*b[2]))
def calc_normal(v):
    n = (0.0, 0.0, 0.0)
    for i in range(2, len(v)):
        c = cross(sub(v[i-1], v[0]), sub(v[i], v[0]))
        n = (f32(n[0]+c[0]), f32(n[1]+c[1]), f32(n[2]+c[2]))
    m = dot(n, n)
    if m < 1e-8:
        return None
    inv = f32(1.0/f32(math.sqrt(float(m))))
    return (f32(n[0]*inv), f32(n[1]*inv), f32(n[2]*inv))

def ulp_bits(a, b):
    """crude ULP-ish distance between two f32 by raw bit magnitude on the dominant component."""
    return abs((struct.unpack('<i', struct.pack('<I', bits(a)))[0]) -
               (struct.unpack('<i', struct.pack('<I', bits(b)))[0]))

def is_axis(n):
    comps = sorted(abs(c) for c in n)
    return comps[0] == 0.0 and comps[1] == 0.0 and comps[2] == 1.0

def parse_polys(txt):
    out = []
    for pm in re.finditer(r'Begin Polygon(.*?)End Polygon', txt, re.S):
        body = pm.group(1)
        nm = re.search(r'Normal\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)', body)
        if not nm: continue
        an = tuple(f32(float(x)) for x in nm.groups())
        verts = [tuple(f32(float(x)) for x in v)
                 for v in re.findall(r'Vertex\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)', body)]
        if len(verts) < 3: continue
        out.append((an, verts))
    return out

def all_orderings(verts):
    """every cyclic rotation of the ring, forward and reversed."""
    n = len(verts)
    outs = []
    for r in range(n):
        rot = verts[r:] + verts[:r]
        outs.append(('rot%d' % r, rot))
        rev = list(reversed(rot))
        outs.append(('rev%d' % r, rev))
    return outs

TRUNK = sys.argv[1] if len(sys.argv) > 1 else \
    "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedcli/maps/foobar/actors"

nonaxis = 0          # non-axis faces with a valid winding normal
authored_kept = 0    # dot(calc_raw, authored) > 0.9999  (native keeps authored → must stay byte-exact)
raw_exact = 0        # calc_normal(raw order) == authored bit-exact
reorder_hits = 0     # some rotation/reversal reproduces authored bit-exact
reorder_miss = []    # faces where NO ordering reproduces authored (the danger class)

for path in sorted(glob.glob(os.path.join(TRUNK, "*/actor.t3d"))):
    name = os.path.basename(os.path.dirname(path))
    txt = open(path).read()
    if 'CsgOper' not in txt: continue
    for pi, (an, verts) in enumerate(parse_polys(txt)):
        if is_axis(an):
            continue
        cl = calc_normal(verts)
        if cl is None: continue
        nonaxis += 1
        d = dot(cl, an)
        raw_is_exact = all(bits(cl[k]) == bits(an[k]) for k in range(3))
        if raw_is_exact:
            raw_exact += 1
        if d <= 0.9999:
            continue  # native OVERRIDES with calc_raw (stale-authored, e.g. spire) — not this class
        authored_kept += 1
        if raw_is_exact:
            reorder_hits += 1
            continue
        # authored kept but calc_raw != authored bits → does a reorder reproduce authored?
        hit = None
        for tag, order in all_orderings(verts):
            c2 = calc_normal(order)
            if c2 is None: continue
            if all(bits(c2[k]) == bits(an[k]) for k in range(3)):
                hit = tag
                break
        if hit:
            reorder_hits += 1
        else:
            ud = max(ulp_bits(cl[k], an[k]) for k in range(3))
            reorder_miss.append((name, pi, ud, an, cl))

print(f"castle non-axis faces (valid winding): {nonaxis}")
print(f"  authored-kept (dot>0.9999, native stores authored): {authored_kept}")
print(f"    calc_normal(RAW order) already == authored bits:   {raw_exact}")
print(f"    reproduced by SOME rotation/reversal:              {reorder_hits}")
print(f"    NO ordering reproduces authored (DANGER class):    {len(reorder_miss)}")
print()
if reorder_miss:
    print("DANGER faces (authored kept, calc_raw != authored, no reorder hits authored):")
    for name, pi, ud, an, cl in reorder_miss[:40]:
        print(f"  {name} poly{pi} maxUlp~{ud}  authored={[hex(bits(x)) for x in an]}  calc_raw={[hex(bits(x)) for x in cl]}")
