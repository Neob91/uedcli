import sys, struct
sys.path.insert(0, "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
from uedcli.native.pkg_write import parse_package
from uedcli.native.codec import read_ci

def load(path):
    buf = open(path, "rb").read()
    p = parse_package(buf)
    mi = [i for i in range(len(p.exports)) if p.class_of_export(i) == "Model"]
    mi.sort(key=lambda i: p.exports[i]["ssize"], reverse=True)
    i = mi[0]
    e = p.exports[i]
    return p.buf[e["soff"]:e["soff"]+e["ssize"]], e["ssize"]

def skip_vec(data,pos):
    n,pos=read_ci(data,pos); return n, pos+n*12

def parse(tag, path):
    data, size = load(path)
    print(f"\n===== {tag} size={size} =====")
    pos=42
    nv,pos=skip_vec(data,pos)
    npt,pos=skip_vec(data,pos)
    # nodes
    nn,pos=read_ci(data,pos); pos += nn*43
    # surfs: parse each properly (variable). Instead re-derive via umodel. Simpler: use known node size 43 (const here)
    # surfs - variable length; parse
    ns,pos=read_ci(data,pos)
    for _ in range(ns):
        _,pos=read_ci(data,pos)  # tex
        pos+=4                    # polyflags u32
        for _ in range(6): _,pos=read_ci(data,pos)  # pBase,vN,vU,vV,iActor,iBrushPoly
        pos+=4                    # iZone u16 u16
        _,pos=read_ci(data,pos)  # iLightMap
    # verts
    nvert,pos=read_ci(data,pos)
    for _ in range(nvert):
        _,pos=read_ci(data,pos); _,pos=read_ci(data,pos)
    numshared=struct.unpack_from("<i",data,pos)[0]; pos+=4
    numzones=struct.unpack_from("<i",data,pos)[0]; pos+=4
    print(f"NumSharedSides={numshared} NumZones={numzones}")
    for _ in range(numzones):
        _,pos=read_ci(data,pos); pos+=16
    polys,pos=read_ci(data,pos)
    print(f"Polys objref (parser field_0x54) = {polys}")
    # LightMap array (a8): count, per elem 4+12+ci+ci+12
    n,pos=read_ci(data,pos); print(f"LightMap[FLightMapIndex] count={n}")
    for _ in range(n):
        pos+=4+12; _,pos=read_ci(data,pos); _,pos=read_ci(data,pos); pos+=12
    # LightBits (b4): bytes
    n,pos=read_ci(data,pos); print(f"LightBits[BYTE] count={n}"); pos+=n
    # Bounds (c0): FBox count*25
    n,pos=read_ci(data,pos); print(f"Bounds[FBox] count={n}")
    bstart=pos
    for i in range(n):
        bb=struct.unpack_from("<ffffff",data,pos); valid=data[pos+24]; pos+=25
        if i<8 or i>=n-2:
            print(f"   Bounds[{i}] min=({bb[0]:.0f},{bb[1]:.0f},{bb[2]:.0f}) max=({bb[3]:.0f},{bb[4]:.0f},{bb[5]:.0f}) valid={valid}")
    # LeafHulls (cc): INT count*4
    n,pos=read_ci(data,pos); print(f"LeafHulls[INT] count={n}")
    hulls=[struct.unpack_from("<i",data,pos+4*i)[0] for i in range(n)]
    pos+=n*4
    print(f"   LeafHulls values = {hulls}")
    # Leaves
    n,pos=read_ci(data,pos); print(f"Leaves[FBspLeaf] count={n}")
    for _ in range(n):
        iz,pos=read_ci(data,pos); ip,pos=read_ci(data,pos); iv,pos=read_ci(data,pos); pos+=8
    # e4 array
    n,pos=read_ci(data,pos); print(f"post-leaf array count={n}")
    for _ in range(n): _,pos=read_ci(data,pos)
    a=struct.unpack_from("<i",data,pos)[0]; pos+=4
    b=struct.unpack_from("<i",data,pos)[0]; pos+=4
    print(f"trailing i32 (RootOutside,Linked?) = {a},{b}")
    print(f"reached pos={pos} of size={size}  {'OK' if pos==size else 'MISMATCH'}")

parse("DXOnly","/home/neob91/Games/LutrisDX/drive_c/DX/Maps/DXOnly.dx")
parse("NativeCSG","/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCSG.dx")
