"""Replicate native's scaled-brush normal chain for Brush578's -y face in exact f32 semantics."""
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
import os
os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/bsp-parity-proj"
from uedcli import trunk
from uedcli import rotation as ROT
from uedcli.native import brush_marshal as BM

f32 = np.float32

def bits(x):
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]

level, _ = trunk.read_level(Path("/workspace/uedcli/_scratch/bsp-parity-proj/maps/unatco"))
a = level.actors["Brush578"]
L = ROT.actor_linear(a)
Linv = ROT.inverse(L)
NT = ROT.transpose(Linv)  # covariant_axes = (L^-1)^T
print("L =", L)
print("(L^-1)^T =", NT)
vx = [[f32(NT[r][c]) for c in range(3)] for r in range(3)]
for r in range(3):
    print("vx row", r, [f"{bits(v):08x}" for v in vx[r]])

# -y face local verts (authored): (-128,-192,-80),(128,-192,-80)... wait the -y face:
polys = a.brush.polys if a.brush else None
# find the poly with authored normal (0,-1,0)
target = None
for p in polys:
    n = p.normal
    if abs(n[0]) < 0.5 and n[1] < -0.5:
        target = p
        break
print("authored normal:", target.normal, "verts:", target.vertices)

# calc_normal: triangle-fan cross accumulation pivoted at V0, f32, then SafeNormalSlow-style
v = [np.array([f32(c) for c in vert], dtype=np.float32) for vert in target.vertices]
acc = np.zeros(3, dtype=np.float32)
for i in range(2, len(v)):
    e1 = (v[i - 1] - v[0]).astype(np.float32)
    e2 = (v[i] - v[0]).astype(np.float32)
    cr = np.array([
        f32(f32(e1[1] * e2[2]) - f32(e1[2] * e2[1])),
        f32(f32(e1[2] * e2[0]) - f32(e1[0] * e2[2])),
        f32(f32(e1[0] * e2[1]) - f32(e1[1] * e2[0])),
    ], dtype=np.float32)
    acc = (acc + cr).astype(np.float32)
print("fan acc:", acc, [f"{bits(x):08x}" for x in acc])

def safe_normal_slow(vec):
    sq = f32(f32(f32(vec[0] * vec[0]) + f32(vec[1] * vec[1])) + f32(vec[2] * vec[2]))
    size = f32(np.sqrt(np.float64(sq)))
    inv = f32(f32(1.0) / size)
    return np.array([f32(vec[0] * inv), f32(vec[1] * inv), f32(vec[2] * inv)], dtype=np.float32)

nl = safe_normal_slow(acc)
print("calc_normal local:", nl, [f"{bits(x):08x}" for x in nl])

def tvb(n, m):
    # transform_vector_by row-major m: out_i = sum_j m[i][j]*n[j]?  (check native convention)
    return np.array([
        f32(f32(f32(m[0][0] * n[0]) + f32(m[0][1] * n[1])) + f32(m[0][2] * n[2])),
        f32(f32(f32(m[1][0] * n[0]) + f32(m[1][1] * n[1])) + f32(m[1][2] * n[2])),
        f32(f32(f32(m[2][0] * n[0]) + f32(m[2][1] * n[1])) + f32(m[2][2] * n[2])),
    ], dtype=np.float32)

cov = tvb(nl, vx)
print("cov image:", cov, [f"{bits(x):08x}" for x in cov])
out = safe_normal_slow(cov)
print("final:", out, [f"{bits(x):08x}" for x in out])

# Editor side (the f32 BuildCoords chain): same covariant map built by `rotation.editor_vector_xform`
# — its y-entry is 0x3fcccce3 (1 ULP above the double-inverted 0x3fcccce2 above), and safe_normal_slow
# of THAT image lands the exact axis 0xbf800000 the editor stores (live-confirmed,
# pass1-normal-probe-unatco.log XFORM k=24).
EVX = ROT.editor_vector_xform(a)
for r in range(3):
    print("editor vx row", r, [f"{bits(v):08x}" for v in EVX[r]])
cov2 = tvb(nl, [[np.float32(EVX[i][j]) for j in range(3)] for i in range(3)])
print("editor-chain cov image:", [f"{bits(x):08x}" for x in cov2])
out2 = safe_normal_slow(cov2)
print("editor-chain final:", [f"{bits(x):08x}" for x in out2], "(expect bf800000 on y)")
