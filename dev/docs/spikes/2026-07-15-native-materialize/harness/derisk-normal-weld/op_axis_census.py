#!/usr/bin/env python3
"""Test the hypothesis: CSG_Subtract brushes -> editor RECOMPUTES normal via CalcNormal(local);
CSG_Add brushes -> KEEP authored. Castle-safe iff the castle has no SUBTRACT non-axis face whose
CalcNormal(local) != authored (native keeps authored & is byte-identical -> golden kept authored there).
For each level, tally (op, axis) and, for non-axis faces, whether calc_normal(local)==authored bits."""
import struct, re, glob, os, math, sys
def f32(x): return struct.unpack('<f', struct.pack('<f', x))[0]
def bits(x): return struct.unpack('<I', struct.pack('<f', f32(x)))[0]
def sub(a,b): return (f32(a[0]-b[0]),f32(a[1]-b[1]),f32(a[2]-b[2]))
def cross(a,b): return (f32(f32(a[1]*b[2])-f32(a[2]*b[1])),f32(f32(a[2]*b[0])-f32(a[0]*b[2])),f32(f32(a[0]*b[1])-f32(a[1]*b[0])))
def dot(a,b): return f32(f32(f32(a[0]*b[0])+f32(a[1]*b[1]))+f32(a[2]*b[2]))
def calc_normal(v):
    n=(0.0,0.0,0.0)
    for i in range(2,len(v)):
        c=cross(sub(v[i-1],v[0]),sub(v[i],v[0])); n=(f32(n[0]+c[0]),f32(n[1]+c[1]),f32(n[2]+c[2]))
    m=dot(n,n)
    if m<1e-8: return None
    inv=f32(1.0/f32(math.sqrt(float(m)))); return (f32(n[0]*inv),f32(n[1]*inv),f32(n[2]*inv))
def is_axis(n):
    c=sorted(abs(x) for x in n); return c[0]==0.0 and c[1]==0.0 and c[2]==1.0
def ulp(a,b):
    return abs(struct.unpack('<i',struct.pack('<I',bits(a)))[0]-struct.unpack('<i',struct.pack('<I',bits(b)))[0])

def parse(txt):
    op=(re.search(r'CsgOper=CSG_(\w+)',txt) or [None,'?'])[1] if re.search(r'CsgOper=CSG_(\w+)',txt) else '?'
    m=re.search(r'CsgOper=CSG_(\w+)',txt); op=m.group(1) if m else 'NONE'
    scaled = ('MainScale' in txt and re.search(r'MainScale=\(Scale',txt)) or re.search(r'PostScale=\(Scale',txt)
    rot = re.search(r'Rotation=\(',txt) is not None
    polys=[]
    for pm in re.finditer(r'Begin Polygon(.*?)End Polygon',txt,re.S):
        b=pm.group(1)
        nm=re.search(r'Normal\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)',b)
        if not nm: continue
        an=tuple(f32(float(x)) for x in nm.groups())
        verts=[tuple(f32(float(x)) for x in v) for v in re.findall(r'Vertex\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)',b)]
        if len(verts)<3: continue
        polys.append((an,verts))
    return op, bool(scaled), rot, polys

def run(trunk, label):
    from collections import Counter
    tally=Counter(); nonaxis_diff=Counter(); danger=[]
    for path in sorted(glob.glob(os.path.join(trunk,"*/actor.t3d"))):
        txt=open(path).read()
        if 'CsgOper' not in txt: continue
        op,scaled,rot,polys=parse(txt)
        if scaled or rot:   # only test the UNSCALED, identity-rotation class (where authored==stored for Add)
            optag=op+('/scaled' if scaled else '')+('/rot' if rot else '')
        else:
            optag=op
        for pi,(an,verts) in enumerate(polys):
            ax=is_axis(an)
            tally[(op, 'axis' if ax else 'slant', 'scaled' if scaled else ('rot' if rot else 'plain'))]+=1
            if ax: continue
            cl=calc_normal(verts)
            if cl is None: continue
            same=all(bits(cl[k])==bits(an[k]) for k in range(3))
            if not same:
                nonaxis_diff[(op,'scaled' if scaled else ('rot' if rot else 'plain'))]+=1
                if op=='Subtract' and not scaled and not rot:
                    u=max(ulp(cl[k],an[k]) for k in range(3))
                    danger.append((os.path.basename(os.path.dirname(path)),pi,u,
                                   [hex(bits(x)) for x in an],[hex(bits(x)) for x in cl]))
    print(f"\n===== {label} ({trunk}) =====")
    print("(op, axis?, xform) -> count:")
    for k in sorted(tally): print(f"   {k}: {tally[k]}")
    print("NON-AXIS faces where calc_normal(local) != authored, by (op,xform):")
    for k in sorted(nonaxis_diff): print(f"   {k}: {nonaxis_diff[k]}")
    print(f"CASTLE-SAFETY BREAKERS = SUBTRACT plain non-axis faces w/ calc!=authored: {len(danger)}")
    for d in danger[:20]: print("   ",d)

CASTLE="/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedcli/maps/foobar/actors"
UNATCO="/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/unatco/uedcli/maps/unatco/actors"
run(CASTLE,"CASTLE")
run(UNATCO,"UNATCO")
