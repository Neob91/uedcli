"""Does a real built node's vertex ring wind with or against its node plane normal?

UE1 `FPoly::CalcNormal`: Normal = sum over i>=2 of (V[i-1]-V[0]) x (V[i]-V[0]), normalized.
"""
import sys
sys.path.insert(0, '.')
from uedcli.bsp.builtmodel import load_model_from_dx

m = load_model_from_dx(open(sys.argv[1],'rb').read())
pts = m.points
same = opp = other = 0
for ni, n in enumerate(m.nodes):
    nv = n.num_vertices
    if nv < 3:
        continue
    ring = [pts[m.verts[n.i_vert_pool + k].i_vertex] for k in range(nv)]
    nx = ny = nz = 0.0
    ax, ay, az = ring[0]
    for i in range(2, nv):
        bx, by, bz = ring[i - 1]
        cx, cy, cz = ring[i]
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        nx += uy * vz - uz * vy
        ny += uz * vx - ux * vz
        nz += ux * vy - uy * vx
    d = nx * n.plane[0] + ny * n.plane[1] + nz * n.plane[2]
    if d > 1e-3:
        same += 1
    elif d < -1e-3:
        opp += 1
    else:
        other += 1
print("ring normal vs node plane normal:  same:", same, " opposite:", opp, " degenerate:", other)
