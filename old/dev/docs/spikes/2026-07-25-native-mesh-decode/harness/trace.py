"""Step-by-step trace of a single mesh body, dumping the position + hex window after each
serialized member — the instrument used to find where the guessed `UMesh::Serialize` field order
desyncs from what Deus Ex actually writes.

Usage: python trace.py <pkg.u> <MeshName>
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
from uedcli.upackage import load_package, read_compact_index, read_property_tags  # noqa: E402
import umesh  # noqa: E402


def hexw(b, p, n=32):
    return " ".join(f"{c:02x}" for c in b[p:p + n])


def main(argv):
    pkg = load_package(argv[1])
    want = argv[2].lower()
    j = next(j for j in umesh.mesh_exports(pkg)
             if pkg.names[pkg.exports[j]["nm"]].lower() == want)
    e = pkg.exports[j]
    b, ver = pkg.buf, pkg.version
    so, end = e["soff"], e["soff"] + e["ssize"]
    print(f"{argv[2]}: class={pkg.object_class_name(j + 1)} body=[{so},{end}) size={e['ssize']}")

    _tags, p = read_property_tags(pkg, so, end)
    print(f"  after props        pos={p} (+{p - so})  {hexw(b, p)}")

    box, p = umesh.fbox(b, p)
    sph, p = umesh.fsphere(b, p)
    print(f"  box={box[0]}..{box[1]} sphere={sph}")
    print(f"  after prim         pos={p} (+{p - so})  {hexw(b, p)}")

    def step(label, fn):
        nonlocal p
        v, p = fn(b, p)
        n = len(v) if isinstance(v, list) else v
        print(f"  {label:18s} -> {n!r:>28.28}  pos={p} (+{p - so})  {hexw(b, p, 24)}")
        return v

    lazy = lambda elem: (lambda b, p: umesh.lazy_array(b, p, elem, version=ver))   # noqa: E731
    steps = [
        ("Verts(lazy,8B)", lazy(umesh.mesh_vert_dx)),
        ("Tris(lazy,20B)", lazy(umesh.mesh_tri)),
        ("AnimSeqs(TArray)", lambda b, p: umesh.tarray(b, p, umesh.mesh_anim_seq)),
        ("Connects(lazy,8B)", lazy(umesh.mesh_vert_connect)),
        ("BoundingBox(inline)", umesh.fbox),
        ("BoundingSphere(inl)", umesh.fsphere),
        ("VertLinks(lazy,4B)", lazy(umesh.i32)),
        ("Textures(TArray)", lambda b, p: umesh.tarray(b, p, read_compact_index)),
        ("BoundingBoxes(TArr)", lambda b, p: umesh.tarray(b, p, umesh.fbox)),
        ("BoundingSpheres", lambda b, p: umesh.tarray(b, p, umesh.fsphere)),
        ("FrameVerts", umesh.i32),
        ("AnimFrames", umesh.i32),
        ("AndFlags", umesh.u32),
        ("OrFlags", umesh.u32),
        ("Scale", umesh.fvec),
        ("Origin", umesh.fvec),
        ("RotOrigin", umesh.frotator),
        ("CurPoly", umesh.i32),
        ("CurVertex", umesh.i32),
        ("TextureLOD(TArray)", lambda b, p: umesh.tarray(b, p, umesh.f32)),
        ("CollapsePointThus", lambda b, p: umesh.tarray(b, p, umesh.u16)),
        ("FaceLevel", lambda b, p: umesh.tarray(b, p, umesh.u16)),
        ("Faces(8B)", lambda b, p: umesh.tarray(b, p, umesh.mesh_face)),
        ("CollapseWedgeThus", lambda b, p: umesh.tarray(b, p, umesh.u16)),
        ("Wedges(4B)", lambda b, p: umesh.tarray(b, p, umesh.mesh_wedge)),
        ("Materials(8B)", lambda b, p: umesh.tarray(b, p, umesh.mesh_material)),
        ("SpecialFaces(8B)", lambda b, p: umesh.tarray(b, p, umesh.mesh_face)),
        ("ModelVerts", umesh.i32),
        ("SpecialVerts", umesh.i32),
        ("MeshScaleMax", umesh.f32),
        ("LODHysteresis", umesh.f32),
        ("LODStrength", umesh.f32),
        ("LODMinVerts", umesh.i32),
        ("LODMorph", umesh.f32),
        ("LODZDisplace", umesh.f32),
    ]
    for label, fn in steps:
        try:
            step(label, fn)
        except Exception as ex:                      # noqa: BLE001 — a probe: show and stop
            print(f"  {label:18s} !! {type(ex).__name__}: {ex}")
            break
    print(f"  --- remaining {end - p} bytes to export end ({end}) ---")
    print(f"  from pos: {hexw(b, p, 64)}")
    print(f"  end-48  : {hexw(b, max(so, end - 48), 48)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
