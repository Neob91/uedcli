#!/usr/bin/env python3
"""Brush755 = identity transform + translation to (540,1204,276).  Test: does calc_normal over the
WORLD winding (local+loc, f32) differ from calc_normal over the LOCAL winding?  If ~33 differ, the 33
residual twins = the editor computing the surf plane over world-space verts (bspAddNode), not local."""
import struct, sys, math
from pathlib import Path
ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS))
from uedctl import trunk
import unatco_subset as U
r32=lambda x: struct.unpack("<f",struct.pack("<f",x))[0]
bits=lambda x: struct.unpack("<I",struct.pack("<f",x))[0]

def calc_normal(verts):
    nx=ny=nz=0.0; v0=verts[0]
    for i in range(2,len(verts)):
        a=(r32(verts[i-1][0]-v0[0]),r32(verts[i-1][1]-v0[1]),r32(verts[i-1][2]-v0[2]))
        b=(r32(verts[i][0]-v0[0]),  r32(verts[i][1]-v0[1]),  r32(verts[i][2]-v0[2]))
        nx=r32(nx+r32(r32(a[1]*b[2])-r32(a[2]*b[1])))
        ny=r32(ny+r32(r32(a[2]*b[0])-r32(a[0]*b[2])))
        nz=r32(nz+r32(r32(a[0]*b[1])-r32(a[1]*b[0])))
    mag2=r32(r32(r32(nx*nx)+r32(ny*ny))+r32(nz*nz))
    inv=r32(1.0/r32(math.sqrt(float(mag2))))
    return (bits(r32(nx*inv)),bits(r32(ny*inv)),bits(r32(nz*inv)))

lvl,_=trunk.read_level(U.FULL_TRUNK)
a=lvl.actors["Brush755"]; loc=[float(c) for c in a.location]
ndiff=0; details=[]
for pi,p in enumerate(a.brush.polys):
    local=[(r32(float(v[0])),r32(float(v[1])),r32(float(v[2]))) for v in p.vertices]
    world=[(r32(v[0]+loc[0]),r32(v[1]+loc[1]),r32(v[2]+loc[2])) for v in local]
    nl=calc_normal(local); nw=calc_normal(world)
    if nl!=nw:
        ndiff+=1
        if len(details)<40:
            details.append(f"  poly{pi:2d} nv={len(local)}: local N={nl[0]:#010x},{nl[1]:#010x},{nl[2]:#010x}  "
                           f"world N={nw[0]:#010x},{nw[1]:#010x},{nw[2]:#010x}")
print(f"Brush755: {len(a.brush.polys)} polys;  local vs world calc_normal DIFFER on {ndiff}")
for d in details: print(d)
