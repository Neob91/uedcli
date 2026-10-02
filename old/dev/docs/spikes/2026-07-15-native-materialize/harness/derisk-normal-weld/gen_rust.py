#!/usr/bin/env python3
"""Extract a brush's full local face set from T3D → Rust FPoly literals for a de-risk test, and
report the minimum inter-vertex distance over the whole brush point set (to prove the bspAddPoint
weld, tolerance 0.002, is a NO-OP → reconstruction cannot change vertex VALUES, only order)."""
import sys, struct, re, math

def f32(x): return struct.unpack('<f', struct.pack('<f', x))[0]
def bits(x): return struct.unpack('<I', struct.pack('<f', f32(x)))[0]

def parse(path, want_idx=None):
    txt = open(path).read()
    polys = []
    for pm in re.finditer(r'Begin Polygon(.*?)End Polygon', txt, re.S):
        b = pm.group(1)
        nm = re.search(r'Normal\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)', b)
        og = re.search(r'Origin\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)', b)
        an = tuple(f32(float(x)) for x in nm.groups())
        base = tuple(f32(float(x)) for x in og.groups()) if og else None
        verts = [tuple(f32(float(x)) for x in v)
                 for v in re.findall(r'Vertex\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)', b)]
        polys.append((an, base, verts))
    return polys

def emit(name, polys, target_idx):
    print(f"    // {name}: {len(polys)} faces; target slanted/facet = poly {target_idx}")
    print(f"    let mut brush: Vec<FPoly> = Vec::new();")
    for i,(an,base,verts) in enumerate(polys):
        vlits = ", ".join(f"v({hex(bits(x))},{hex(bits(y))},{hex(bits(z))})" for (x,y,z) in verts)
        print(f"    {{ let mut p = FPoly::new(vec![{vlits}]);")
        print(f"      p.normal = v({hex(bits(an[0]))},{hex(bits(an[1]))},{hex(bits(an[2]))});")
        if base:
            print(f"      p.base = v({hex(bits(base[0]))},{hex(bits(base[1]))},{hex(bits(base[2]))});")
        print(f"      p.i_brush_poly = {i}; brush.push(p); }}")
    an = polys[target_idx][0]
    print(f"    // authored target normal bits: {[hex(bits(x)) for x in an]}")

# min inter-vertex distance over the whole brush
def min_dist(polys):
    pts = []
    for _,_,vs in polys:
        pts += vs
    m = 1e18; pair=None
    for i in range(len(pts)):
        for j in range(i+1,len(pts)):
            d = math.dist(pts[i],pts[j])
            if d>1e-9 and d<m: m=d; pair=(pts[i],pts[j])
    return m,pair

if __name__ == "__main__":
    path = sys.argv[1]; tgt = int(sys.argv[2]); name = sys.argv[3]
    polys = parse(path)
    m,pair = min_dist(polys)
    print(f"    // MIN inter-vertex distance over brush = {m:.6f} (weld tol 0.002 -> {'NO-OP' if m>0.002 else 'WELDS!'})")
    emit(name, polys, tgt)
