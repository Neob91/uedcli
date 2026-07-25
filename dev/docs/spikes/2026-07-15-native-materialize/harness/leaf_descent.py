"""Simulate the engine's BSP point descent (proven convention: side=1 when PlaneDot>=0,
recurse iChild[side]; iChild[0]=+0x20=i_front=BACK, iChild[1]=+0x24=i_back=FRONT).
Show which leaf a point resolves to, before vs after the fix."""
import sys
from uedctl.native import pkg_write, umodel
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import leaf_fix_classify as FX

def descend(m, p):
    """Return (leaf_index_or_solid, path). leaf 'S' = solid (iLeaf=-1)."""
    ni = 0
    path = []
    while True:
        n = m.nodes[ni]
        nx, ny, nz, w = n.plane
        pd = nx*p[0] + ny*p[1] + nz*p[2] - w
        side = 1 if pd >= 0 else 0            # 1=front(+0x24=i_back), 0=back(+0x20=i_front)
        child = n.i_back if side == 1 else n.i_front
        leaf  = n.i_leaf[side]
        path.append((ni, 'F' if side else 'B', child))
        if child == -1:
            return ('leaf %d' % leaf if leaf != -1 else 'SOLID'), path
        ni = child

pts = {'interior(0,0,0)': (0,0,0),
       'below floor(0,0,-200)': (0,0,-200),
       'outside +X(300,0,0)': (300,0,0),
       'above ceiling(0,0,300)': (0,0,300)}

NC = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCSG.dx"
DX = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/DXOnly.dx"

print("### DXOnly (known-good) ###")
dx = FX.load(DX)
for name,p in pts.items():
    r,path = descend(dx,p); print(f"  {name:24s} -> {r:8s}  path={[e[0] for e in path]}")

print("\n### NativeCSG BEFORE fix ###")
nc = FX.load(NC)
for name,p in pts.items():
    r,path = descend(nc,p); print(f"  {name:24s} -> {r:8s}  path={[e[0] for e in path]}")

print("\n### NativeCSG AFTER fix ###")
nc2 = FX.apply_fix(FX.load(NC))
for name,p in pts.items():
    r,path = descend(nc2,p); print(f"  {name:24s} -> {r:8s}  path={[e[0] for e in path]}")
