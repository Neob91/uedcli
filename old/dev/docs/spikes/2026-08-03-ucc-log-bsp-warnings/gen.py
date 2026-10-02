#!/usr/bin/env python3
"""Emit builder-brush polylists (a full cube and an open cube missing its +Z face)
and the two Editor.ExecCommandlet scripts that subtract+rebuild them, to probe whether
UCC surfaces the D0 BSP-build warnings (drops / T-points / infinitesimal nodes)."""
import sys, pathlib

H = 128.0
# 6 faces of an axis-aligned cube [-H,H]^3, outward normals, CCW-from-outside winding.
FACES = {
    "-X": ((-1,0,0), [(-H,-H,-H),(-H,-H, H),(-H, H, H),(-H, H,-H)]),
    "+X": (( 1,0,0), [( H, H,-H),( H, H, H),( H,-H, H),( H,-H,-H)]),
    "-Y": ((0,-1,0), [( H,-H,-H),( H,-H, H),(-H,-H, H),(-H,-H,-H)]),
    "+Y": ((0, 1,0), [(-H, H,-H),(-H, H, H),( H, H, H),( H, H,-H)]),
    "-Z": ((0,0,-1), [(-H,-H,-H),(-H, H,-H),( H, H,-H),( H,-H,-H)]),
    "+Z": ((0,0, 1), [( H,-H, H),( H, H, H),(-H, H, H),(-H,-H, H)]),
}

def poly(normal, verts):
    nx,ny,nz = normal
    # pick a texture basis perpendicular to normal (crude but valid)
    if abs(nx) < 0.9: tu=(1,0,0)
    else: tu=(0,1,0)
    tv=(0,0,1) if abs(nz)<0.9 else (0,1,0)
    L=[]
    L.append("   Begin Polygon Flags=0")
    L.append(f"      Origin   {verts[0][0]:.6f},{verts[0][1]:.6f},{verts[0][2]:.6f}")
    L.append(f"      Normal   {nx:.6f},{ny:.6f},{nz:.6f}")
    L.append(f"      TextureU {tu[0]:.6f},{tu[1]:.6f},{tu[2]:.6f}")
    L.append(f"      TextureV {tv[0]:.6f},{tv[1]:.6f},{tv[2]:.6f}")
    for v in verts:
        L.append(f"      Vertex   {v[0]:.6f},{v[1]:.6f},{v[2]:.6f}")
    L.append("   End Polygon")
    return "\n".join(L)

def polylist(names):
    body = "\n".join(poly(*FACES[n]) for n in names)
    return "Begin PolyList\n" + body + "\nEnd PolyList\n"

out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
(out/"cube_full.polys.t3d").write_text(polylist(list(FACES)))
(out/"cube_open.polys.t3d").write_text(polylist([n for n in FACES if n!="+Z"]))

def script(polys, tag):
    return "\n".join([
        "MAP GRID X=1 Y=1 Z=1",
        "MAP NEW",
        f"BRUSH IMPORT FILE=Z:\\work\\{polys}",
        "BRUSH MOVETO X=0 Y=0 Z=0",
        "BRUSH SUBTRACT",
        "MAP REBUILD",
        f"MAP EXPORT FILE=Z:\\work\\{tag}.out.t3d",
        "",
    ])
(out/"full.txt").write_text(script("cube_full.polys.t3d","full"))
(out/"open.txt").write_text(script("cube_open.polys.t3d","open"))
print("wrote", out)
