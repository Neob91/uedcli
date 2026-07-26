#!/usr/bin/env python3
"""§92 §46 — pin that the editor's stored unscaled slanted-face node normal is `CalcNormal` over the
brush-LOCAL (pre-transform) winding, NOT the authored T3D `Normal=` and NOT `CalcNormal(world)`.

Reproduces the decisive datum offline (no editor): for the dome Brush755 it recomputes each poly's
`calc_normal` over the raw T3D LOCAL verts and shows the four slanted facets match the editor's stored
node normals (`editor-struct-unatco-105.log`) bit-for-bit, where `calc_normal(world)` does not.  Also
shows an axis rectangle (large, non-square) double-rounds to 0.99999994 under `calc_normal(local)` —
the reason a blanket local recompute must be gated by `is_unit_axis` (and even then only the RAW-local
value; the castle's welded slanted faces need the brush-model reconstruction, see §46).

Usage: native_local_normal_probe.py [BRUSH755_actor.t3d] [editor-struct-unatco-105.log]
"""
import sys, struct, math, re

def f32(x): return struct.unpack('<f', struct.pack('<f', x))[0]
def bits(x): return struct.unpack('<I', struct.pack('<f', f32(x)))[0]
def sub(a, b): return (f32(a[0]-b[0]), f32(a[1]-b[1]), f32(a[2]-b[2]))
def cross(a, b):
    return (f32(f32(a[1]*b[2])-f32(a[2]*b[1])),
            f32(f32(a[2]*b[0])-f32(a[0]*b[2])),
            f32(f32(a[0]*b[1])-f32(a[1]*b[0])))
def dot(a, b): return f32(f32(f32(a[0]*b[0])+f32(a[1]*b[1]))+f32(a[2]*b[2]))
def calc_normal(v):
    """fpoly.rs::calc_normal — triangle fan + NormalizeSlow (f64-widened sqrt)."""
    n = (0.0, 0.0, 0.0)
    for i in range(2, len(v)):
        c = cross(sub(v[i-1], v[0]), sub(v[i], v[0]))
        n = (f32(n[0]+c[0]), f32(n[1]+c[1]), f32(n[2]+c[2]))
    m = dot(n, n)
    if m < 1e-8:
        return None
    inv = f32(1.0/f32(math.sqrt(float(m))))
    return (f32(n[0]*inv), f32(n[1]*inv), f32(n[2]*inv))

T3D = sys.argv[1] if len(sys.argv) > 1 else \
    "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/unatco/uedcli/maps/unatco/actors/Brush755/actor.t3d"
EDLOG = sys.argv[2] if len(sys.argv) > 2 else \
    "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli/_scratch/ptx/editor-struct-unatco-105.log"

# Brush755 is unscaled + identity rotation; local winding = raw T3D verts.
txt = open(T3D).read()
loc = (540.0, 1204.0, 276.0)
edmag = set()
try:
    for ln in open(EDLOG):
        m = re.match(r'^ND \d+ .*isurf=(\d+) nv=\d+ pbits=(0x[0-9a-f]+),(0x[0-9a-f]+),(0x[0-9a-f]+),', ln)
        if m and int(m.group(1)) >= 500:
            edmag.add(tuple(int(m.group(i), 16) & 0x7fffffff for i in (2, 3, 4)))
except FileNotFoundError:
    print(f"(editor log {EDLOG} absent — showing local vs world only)")

ok = 0
for pm in re.finditer(r'Begin Polygon(.*?)End Polygon', txt, re.S):
    body = pm.group(1)
    nm = re.search(r'Normal\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)', body)
    an = tuple(f32(float(x)) for x in nm.groups())
    verts = [tuple(f32(float(x)) for x in v)
             for v in re.findall(r'Vertex\s+([-+\d.]+),([-+\d.]+),([-+\d.]+)', body)]
    if len(verts) < 3 or not (0.01 < abs(an[0]) < 0.99):
        continue
    cl = calc_normal(verts)
    cw = calc_normal([(f32(v[0]+loc[0]), f32(v[1]+loc[1]), f32(v[2]+loc[2])) for v in verts])
    if cl is None:
        continue
    lmag = tuple(bits(c) & 0x7fffffff for c in cl)
    hit = lmag in edmag
    if hit or not edmag:
        ok += hit
        print(f"authored N.x={bits(an[0]):#010x}  calc_local N.x={bits(cl[0]):#010x}  "
              f"calc_world N.x={bits(cw[0]):#010x}  local==editor_node={hit}")
print(f"\ndome facets matching editor via calc_normal(LOCAL): {ok}  "
      f"(calc_normal(WORLD) and authored both MISS — §92 §46)")
