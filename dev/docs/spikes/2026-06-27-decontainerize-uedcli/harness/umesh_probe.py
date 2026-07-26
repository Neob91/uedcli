"""Probe the DeusEx mesh (LodMesh/Mesh) on-disk vertex format and confirm it
differs from stock Unreal/UT. Pure Python, no wine/umodel at runtime (umodel was
used only to produce ground-truth counts during the spike).

FINDING (confirmed on 178/178 DeusExDeco.u meshes): a DeusEx mesh's first vertex
array stores each vertex as **4 x int16 = 8 bytes** (X, Y, Z, pad), uncompressed —
NOT the stock Unreal `FMeshVert` 32-bit bit-packed dword (X:11, Y:11, Z:10). umodel
down-converts the 8-byte DeusEx verts to 4-byte packed dwords (rescaling + adjusting
MeshScale) when it exports `_a.3d`. This 8-vs-4-byte vertex stride is exactly the
"different mesh format" that makes stock Unreal/UT tools (and the UT-lineage UED22
editor) unable to read DeusEx meshes — one concrete reason the stub pipeline runs
umodel.

UMesh body layout decoded so far (DeusEx, package v68):
    <tagged property list> None        # usually empty
    FBox PrimitiveBox        25 bytes  # Min FVec(12) + Max FVec(12) + IsValid(1)
    FSphere PrimitiveSphere  16 bytes  # center FVec(12) + radius f32(4)
    Verts : TLazyArray<FMeshVertDeusEx>
        i32 SkipOffset                 # absolute file offset just past the data
        ci  Count                      # number of vertices
        Count x 8 bytes                # FMeshVertDeusEx = int16 X,Y,Z,pad
    ... (Tris / AnimSeqs / Connects / Textures / scale / LOD — plain TArrays,
         not parsed here; a full native decoder is a bounded follow-up.)

Usage: python umesh_probe.py <pkg.u> [--all]
"""
from __future__ import annotations

import struct
import sys

sys.path.insert(0, ".")
from utexture_decode import load_package, read_props, ci


def _f(buf, o):
    return struct.unpack_from("<f", buf, o)[0]


def probe_mesh(pkg, j, verbose=False):
    """Return (ok, count, elem_size) for the vertex array of mesh export j (0-based)."""
    e = pkg.exports[j]
    buf = pkg.buf
    so, sz = e["soff"], e["ssize"]
    end = so + sz
    _props, pos = read_props(buf, so, end, pkg.names)
    minv = (_f(buf, pos), _f(buf, pos + 4), _f(buf, pos + 8))
    maxv = (_f(buf, pos + 12), _f(buf, pos + 16), _f(buf, pos + 20))
    pos += 25 + 16                              # FBox + FSphere
    skip = struct.unpack_from("<i", buf, pos)[0]
    count, dp = ci(buf, pos + 4)               # TLazyArray: skip int, ci count
    span = skip - dp
    if count <= 0 or span <= 0 or span % count:
        return (False, count, None, minv, maxv)
    esz = span // count
    inside = True
    verts = []
    for k in range(count):
        x, y, z, pad = struct.unpack_from("<4h", buf, dp + k * esz) if esz == 8 \
            else (0, 0, 0, 0)
        verts.append((x, y, z))
        if not (minv[0] - 1 <= x <= maxv[0] + 1 and minv[1] - 1 <= y <= maxv[1] + 1
                and minv[2] - 1 <= z <= maxv[2] + 1):
            inside = False
    if verbose:
        print(f"  {pkg.names[e['nm']]:22s} box={minv}..{maxv} verts={count} "
              f"elem={esz} all_inside={inside}")
        print(f"    first verts: {verts[:6]}")
    return (esz == 8 and inside, count, esz, minv, maxv)


def main(argv):
    pkg = load_package(argv[1])
    meshes = [j for j in range(len(pkg.exports))
              if pkg.class_of_export(j) in ("LodMesh", "Mesh")]
    print(f"{argv[1]}: v{pkg.version}  meshes={len(meshes)}")
    if "--all" in argv:
        ok = sum(probe_mesh(pkg, j)[0] for j in meshes)
        print(f"  8-byte-int16 verts within FBox: {ok}/{len(meshes)}")
    else:
        for j in meshes[:8]:
            probe_mesh(pkg, j, verbose=True)


if __name__ == "__main__":
    main(sys.argv)
