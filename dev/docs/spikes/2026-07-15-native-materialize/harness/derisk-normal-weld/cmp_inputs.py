#!/usr/bin/env python3
"""Decisive offline test: are the editor's captured CalcNormal INPUT verts bit-identical to native's
exact Brush755 T3D verts, or ~1e-4 perturbed?  If identical -> the twin is downstream of calc_normal
(some OTHER divergence).  If perturbed -> pin the perturbation magnitude/pattern (the honest source)."""
import struct, sys, re
from pathlib import Path
ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS))
from uedcli import trunk
import unatco_subset as U

def f(bits): return struct.unpack("<f", struct.pack("<I", bits))[0]

# --- native Brush755 T3D local verts ---
lvl, _ = trunk.read_level(U.FULL_TRUNK)
b = lvl.actors["Brush755"].brush
native_faces = []   # list of list[(x,y,z) f32-bit tuples]
for poly in b.polys:
    vs = [(struct.unpack("<I", struct.pack("<f", v[0]))[0],
           struct.unpack("<I", struct.pack("<f", v[1]))[0],
           struct.unpack("<I", struct.pack("<f", v[2]))[0]) for v in poly.vertices]
    native_faces.append(vs)
print(f"native Brush755: {len(native_faces)} polys, nv={[len(x) for x in native_faces]}")

# --- editor captured CN input sets ---
cap = []
for line in (ROOT/"_scratch/normfin/calcnormal.log").read_text().splitlines():
    if not line.startswith("CN "): continue
    vs = re.findall(r"V=(0x[0-9a-f]+),(0x[0-9a-f]+),(0x[0-9a-f]+)", line)
    cap.append([(int(a,16),int(b,16),int(c,16)) for a,b,c in vs])
print(f"editor captured: {len(cap)} CN calls, nv={sorted(set(len(x) for x in cap))}")

# collect the set of all distinct vert-bit-tuples on each side
def bagset(faces):
    s = {}
    for vs in faces:
        for t in vs:
            s[t] = s.get(t, 0) + 1
    return s
nat = bagset(native_faces); edt = bagset(cap)
print(f"\nnative distinct verts: {len(nat)};  editor distinct verts: {len(edt)}")

# exact bit-identical intersection
inter = set(nat) & set(edt)
print(f"BIT-IDENTICAL verts (native ∩ editor): {len(inter)} / editor {len(edt)}")

# for editor verts NOT bit-identical, find nearest native vert and report the delta
only_e = [t for t in edt if t not in nat]
print(f"editor verts NOT bit-matched to native: {len(only_e)}")
def nearest(t):
    tx,ty,tz = f(t[0]),f(t[1]),f(t[2])
    best=None;bd=1e30
    for u in nat:
        d=abs(f(u[0])-tx)+abs(f(u[1])-ty)+abs(f(u[2])-tz)
        if d<bd: bd=d;best=u
    return best,bd
maxd=0
for t in only_e[:40]:
    u,d=nearest(t); maxd=max(maxd,d)
    print(f"  E={f(t[0]):+.6f},{f(t[1]):+.6f},{f(t[2]):+.6f}  "
          f"nearestN={f(u[0]):+.6f},{f(u[1]):+.6f},{f(u[2]):+.6f}  L1Δ={d:.2e}  "
          f"bits E.x={t[0]:#010x} N.x={u[0]:#010x}")
print(f"\nMAX L1 delta over unmatched editor verts (first 40): {maxd:.3e}")
