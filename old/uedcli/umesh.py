"""Deus Ex / Unreal-1 `UMesh` + `ULodMesh` export body decode.

`parse_mesh` is a thin wrapper over the native decoder (`uedcli_native.parse_mesh_raw`,
`uedcli-native/src/mesh_read.rs`) — see `dev/docs/board/done/port-ue1-mesh-geometry-decode-to-rust/`
for the port. `class show`'s mesh facts read the `Mesh.box`/`scale` this returns;
`tests/test_mesh_decode.py` pins the decode against the committed UED22 packages.

Usage:
    python umesh.py <pkg.u> [--verbose] [--mesh NAME]
"""
from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass, field

from .upackage import load_package, read_property_tags


class MeshParseError(ValueError):
    """Structural desync while decoding a mesh body."""


@dataclass
class Mesh:
    name: str
    is_lod: bool
    box: tuple = ()
    sphere: tuple = ()
    verts: list = field(default_factory=list)
    tris: list = field(default_factory=list)
    anim_seqs: list = field(default_factory=list)
    connects: list = field(default_factory=list)
    vert_links: list = field(default_factory=list)
    textures: list = field(default_factory=list)      # signed object refs
    frame_verts: int = 0
    anim_frames: int = 0
    scale: tuple = (1.0, 1.0, 1.0)
    origin: tuple = (0.0, 0.0, 0.0)
    rot_origin: tuple = (0, 0, 0)
    texture_lod: list = field(default_factory=list)
    # ULodMesh
    collapse_point_thus: list = field(default_factory=list)
    face_level: list = field(default_factory=list)
    faces: list = field(default_factory=list)
    collapse_wedge_thus: list = field(default_factory=list)
    wedges: list = field(default_factory=list)
    materials: list = field(default_factory=list)
    special_faces: list = field(default_factory=list)
    model_verts: int = 0
    special_verts: int = 0
    mesh_scale_max: float = 0.0
    lod_hysteresis: float = 0.0
    lod_strength: float = 0.0
    lod_min_verts: int = 0
    lod_morph: float = 0.0
    lod_z_displace: float = 0.0
    remap_anim_verts: list = field(default_factory=list)  # ULodMesh's TArray<WORD> RemapAnimVerts
    old_frame_verts: int = 0      # ULodMesh's trailing INT OldFrameVerts (== FrameVerts in DX/UT retail)
    vert_stride: int = 0          # 8 = Deus Ex int16 quad, 4 = stock Unreal packed dword


def parse_mesh(pkg, j, *, vert8=None, strict_end=True):
    """Decode export `j` (a `Mesh`/`LodMesh`) fully. Raises `MeshParseError` on any desync or if
    the parse does not consume exactly to the export's end.

    Thin wrapper (mirrors `upackage.read_property_tags`'s own shape): reads the property-tag
    prefix (already native), then decodes the whole body in one native call
    (`uedcli_native.parse_mesh_raw`, `uedcli-native/src/mesh_read.rs`) — see
    `dev/docs/board/done/port-ue1-mesh-geometry-decode-to-rust/`. `strict_end=False` is
    unused by every call site today; the native decoder always enforces consume-to-exact-end
    (baked into `parse_mesh_body`, not split across the FFI boundary), so on success `p` is always
    `end` — the `(m, p)` return shape is kept only for API compatibility with that dead path.
    """
    e = pkg.exports[j]
    so, end = e["soff"], e["soff"] + e["ssize"]
    cls = pkg.object_class_name(j + 1)
    is_lod = (cls == "LodMesh")

    _tags, p = read_property_tags(pkg, so, end)

    from .native_ext import import_native
    uedcli_native = import_native()
    try:
        raw = uedcli_native.parse_mesh_raw(pkg.buf, p, end, pkg.version, is_lod, vert8)
    except uedcli_native.PackageError as ex:
        raise MeshParseError(str(ex)) from ex

    (box, sphere, verts, tris, anim_seqs, connects, vert_links, textures,
     frame_verts, anim_frames, scale, origin), \
    (rot_origin, texture_lod, collapse_point_thus, face_level, faces, collapse_wedge_thus,
     wedges, materials, special_faces, model_verts, special_verts, mesh_scale_max), \
    (lod_hysteresis, lod_strength, lod_min_verts, lod_morph, lod_z_displace,
     remap_anim_verts, old_frame_verts, vert_stride) = raw

    m = Mesh(
        name=pkg.names[e["nm"]], is_lod=is_lod,
        box=box, sphere=sphere, verts=verts, tris=tris, anim_seqs=anim_seqs, connects=connects,
        vert_links=vert_links, textures=textures, frame_verts=frame_verts, anim_frames=anim_frames,
        scale=scale, origin=origin, rot_origin=rot_origin, texture_lod=texture_lod,
        collapse_point_thus=collapse_point_thus, face_level=face_level, faces=faces,
        collapse_wedge_thus=collapse_wedge_thus, wedges=wedges, materials=materials,
        special_faces=special_faces, model_verts=model_verts, special_verts=special_verts,
        mesh_scale_max=mesh_scale_max, lod_hysteresis=lod_hysteresis, lod_strength=lod_strength,
        lod_min_verts=lod_min_verts, lod_morph=lod_morph, lod_z_displace=lod_z_displace,
        remap_anim_verts=remap_anim_verts, old_frame_verts=old_frame_verts,
        vert_stride=vert_stride,
    )
    return (m, end) if not strict_end else m


def mesh_exports(pkg):
    return [j for j in range(len(pkg.exports))
            if pkg.object_class_name(j + 1) in ("LodMesh", "Mesh")]


def main(argv):
    path = argv[1]
    verbose = "--verbose" in argv
    only = argv[argv.index("--mesh") + 1] if "--mesh" in argv else None
    pkg = load_package(path)
    js = mesh_exports(pkg)
    ok = 0
    fails = []
    for j in js:
        nm = pkg.names[pkg.exports[j]["nm"]]
        if only and nm.lower() != only.lower():
            continue
        try:
            m = parse_mesh(pkg, j)
            ok += 1
            if verbose or only:
                print(f"  {m.name:24s} verts={len(m.verts):5d} frameverts={m.frame_verts:5d} "
                      f"frames={m.anim_frames:3d} tris={len(m.tris):5d} "
                      f"wedges={len(m.wedges):5d} faces={len(m.faces):5d} "
                      f"mats={len(m.materials)} texs={len(m.textures)} "
                      f"scale={tuple(round(v, 3) for v in m.scale)}")
        except (MeshParseError, struct.error, IndexError, ValueError) as ex:
            fails.append((nm, str(ex)))
    total = len([j for j in js if not only or pkg.names[pkg.exports[j]["nm"]].lower() == only.lower()])
    print(f"{os.path.basename(path)}: v{pkg.version} meshes={len(js)}  parsed_ok={ok}/{total}")
    for nm, why in fails[:12]:
        print(f"    FAIL {nm}: {why}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
