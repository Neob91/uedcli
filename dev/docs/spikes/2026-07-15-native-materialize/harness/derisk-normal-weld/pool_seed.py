#!/usr/bin/env python3
"""Why does the editor STORE authored f7 (0x3f3504f7) for the castle bastion (0.707,0.707,0) faces,
while it RECOMPUTES the dome (stores CalcNormal-local, not authored)?  Hypothesis: bspAddVector's
first-wins pool (tol THRESH_NORMALS_ARE_SAME=2e-5) — some CLEAN f7 vector enters the pool before the
bastions' recomputed f3, so the recomputed f3 welds back to f7.  This scans every castle face for:
  - authored Normal and TextureU/TextureV that are EXACTLY (±f7,±f7,0),
  - and the CalcNormal(raw-local) of each non-axis face,
to see what value first represents the (0.707,0.707,0)-family direction in add order.
"""
import struct, re, glob, os, math
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

F7=0x3f3504f7; F3=0x3f3504f3
def is45(t):  # (±0.7071..,±0.7071..,0) family within 2e-5
    return abs(abs(t[0])-0.70710677)<2e-5 and abs(abs(t[1])-0.70710677)<2e-5 and abs(t[2])<2e-5

TRUNK="/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedctl/maps/foobar/actors"
# process in the SAME csg_order the build uses? We don't have it; just tally sources of an EXACT f7.
exact_f7_normals=0; exact_f7_texu=0; exact_f7_texv=0
calc_hits_f7=0; calc_hits_f3=0; calc_other={}
for path in sorted(glob.glob(os.path.join(TRUNK,"*/actor.t3d"))):
    txt=open(path).read()
    if 'CsgOper' not in txt: continue
    for pm in re.finditer(r'Begin Polygon(.*?)End Polygon', txt, re.S):
        b=pm.group(1)
        def g(tag):
            m=re.search(tag+r'\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)',b)
            return tuple(f32(float(x)) for x in m.groups()) if m else None
        an=g('Normal'); tu=g('TextureU'); tv=g('TextureV')
        verts=[tuple(f32(float(x)) for x in v) for v in re.findall(r'Vertex\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)',b)]
        if an and is45(an) and bits(abs(an[0]))==F7: exact_f7_normals+=1
        if tu and is45(tu) and bits(abs(tu[0]))==F7: exact_f7_texu+=1
        if tv and is45(tv) and bits(abs(tv[0]))==F7: exact_f7_texv+=1
        if an and is45(an) and len(verts)>=3:
            cl=calc_normal(verts)
            if cl:
                bx=bits(abs(cl[0]))
                if bx==F7: calc_hits_f7+=1
                elif bx==F3: calc_hits_f3+=1
                else: calc_other[hex(bx)]=calc_other.get(hex(bx),0)+1

print("Among 45-degree (0.707,0.707,0)-family castle faces:")
print(f"  authored Normal == EXACT f7 (0x3f3504f7): {exact_f7_normals}")
print(f"  authored TextureU == EXACT f7:            {exact_f7_texu}")
print(f"  authored TextureV == EXACT f7:            {exact_f7_texv}")
print(f"  CalcNormal(raw local) lands on f7:        {calc_hits_f7}")
print(f"  CalcNormal(raw local) lands on f3:        {calc_hits_f3}")
print(f"  CalcNormal(raw local) lands elsewhere:    {calc_other}")
