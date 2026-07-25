#!/usr/bin/env python3
"""Inputs are bit-identical (cmp_inputs). So the twin is the fan-sum ACCUMULATION order = the vertex
WINDING order fed to CalcNormal.  For each editor CN capture, match native's poly by vert-SET and
report: is the editor's ordered sequence IDENTICAL / a cyclic rotation / a reversal / a different
permutation of native's T3D order?  And does native's own calc_normal differ between the two orders?"""
import struct, sys, re
from pathlib import Path
ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS))
from uedctl import trunk
import unatco_subset as U

def f(bits): return struct.unpack("<f", struct.pack("<I", bits))[0]
def bits(x): return struct.unpack("<I", struct.pack("<f", x))[0]

def calc_normal(verts):
    """EXACT port of fpoly.rs calc_normal: triangle-fan Newell sum + f64-widened NormalizeSlow."""
    nx=ny=nz=0.0
    v0=verts[0]
    for i in range(2,len(verts)):
        a=(verts[i-1][0]-v0[0], verts[i-1][1]-v0[1], verts[i-1][2]-v0[2])
        b=(verts[i][0]-v0[0],   verts[i][1]-v0[1],   verts[i][2]-v0[2])
        # a x b, all f32
        cx=struct.unpack("<f",struct.pack("<f",a[1]*b[2]-a[2]*b[1]))[0]
        cy=struct.unpack("<f",struct.pack("<f",a[2]*b[0]-a[0]*b[2]))[0]
        cz=struct.unpack("<f",struct.pack("<f",a[0]*b[1]-a[1]*b[0]))[0]
        nx=struct.unpack("<f",struct.pack("<f",nx+cx))[0]
        ny=struct.unpack("<f",struct.pack("<f",ny+cy))[0]
        nz=struct.unpack("<f",struct.pack("<f",nz+cz))[0]
    mag2=struct.unpack("<f",struct.pack("<f",nx*nx+ny*ny+nz*nz))[0]
    import math
    inv=struct.unpack("<f",struct.pack("<f",1.0/struct.unpack("<f",struct.pack("<f",math.sqrt(float(mag2))))[0]))[0]
    return (bits(struct.unpack("<f",struct.pack("<f",nx*inv))[0]),
            bits(struct.unpack("<f",struct.pack("<f",ny*inv))[0]),
            bits(struct.unpack("<f",struct.pack("<f",nz*inv))[0]))

# subtract-brush verts are stored so materialize does f32 rounding; use raw T3D f32 here (local frame).
lvl,_=trunk.read_level(U.FULL_TRUNK)
b=lvl.actors["Brush755"].brush
native=[]
for p in b.polys:
    native.append([(bits(v[0]),bits(v[1]),bits(v[2])) for v in p.vertices])

cap=[]
for line in (ROOT/"_scratch/normfin/calcnormal.log").read_text().splitlines():
    if not line.startswith("CN "): continue
    vs=re.findall(r"V=(0x[0-9a-f]+),(0x[0-9a-f]+),(0x[0-9a-f]+)",line)
    cap.append([(int(a,16),int(bb,16),int(c,16)) for a,bb,c in vs])

def rots(seq):
    n=len(seq); out=[]
    for r in range(n): out.append(tuple(seq[(r+i)%n] for i in range(n)))
    rev=list(reversed(seq))
    for r in range(n): out.append(tuple(rev[(r+i)%n] for i in range(n)))
    return out

ident=rot=revd=perm=0
order_changes_normal=0
diffnormal_lines=[]
for ci,cv in enumerate(cap):
    cset=set(cv)
    # match native poly by identical vert-set and length
    m=[nv for nv in native if len(nv)==len(cv) and set(nv)==cset]
    if not m:
        perm+=1; continue
    nv=m[0]
    if tuple(nv)==tuple(cv): ident+=1
    elif tuple(cv) in [tuple(x) for x in rots(nv)]:
        if tuple(cv) in [tuple(nv[(r+i)%len(nv)] for i in range(len(nv))) for r in range(len(nv))]: rot+=1
        else: revd+=1
    else: perm+=1
    ne=calc_normal([ (f(a),f(b_),f(c)) for a,b_,c in cv])   # editor order
    nn=calc_normal([ (f(a),f(b_),f(c)) for a,b_,c in nv])   # native order
    if ne!=nn:
        order_changes_normal+=1
        if len(diffnormal_lines)<12:
            diffnormal_lines.append(f"  face{ci} nv={len(cv)}: editor-order N={ne[0]:#010x},{ne[1]:#010x},{ne[2]:#010x}  "
                                    f"native-order N={nn[0]:#010x},{nn[1]:#010x},{nn[2]:#010x}")

print(f"matched {ident+rot+revd+perm} caps;  identical-order={ident}  cyclic-rot={rot}  reversal={revd}  other-perm={perm}")
print(f"faces where native calc_normal(editor order) != calc_normal(native order): {order_changes_normal}")
for l in diffnormal_lines: print(l)
