"""Native decoder for Deus Ex / Unreal-1 `UMesh` + `ULodMesh` export bodies.

Spike `2026-07-25-native-mesh-decode`. Builds on spike
`2026-06-27-decontainerize-uedctl/02-native-mesh-format.md`, which established that a Deus Ex
`FMeshVert` is **8 bytes** (`int16 X,Y,Z,pad`) rather than stock Unreal's 4-byte bit-packed dword,
and disassembled `ULodMesh::Serialize`'s member order. This harness decodes the WHOLE body.

The oracle is **consume-exactly-to-export-end**: an export's body occupies `[soff, soff+ssize)`, so
a parse that lands on the final byte for every mesh in a package is structurally correct — a wrong
field width or a missing/extra array desyncs and misses the end (by a lot, almost always).

Usage:
    python umesh.py <pkg.u> [--verbose] [--mesh NAME]
"""
from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
from uedctl.upackage import load_package, read_compact_index, read_property_tags  # noqa: E402


class MeshParseError(ValueError):
    """Structural desync while decoding a mesh body."""


# ---------------------------------------------------------------- primitives

def u8(b, p):   return b[p], p + 1
def i16(b, p):  return struct.unpack_from("<h", b, p)[0], p + 2
def u16(b, p):  return struct.unpack_from("<H", b, p)[0], p + 2
def i32(b, p):  return struct.unpack_from("<i", b, p)[0], p + 4
def u32(b, p):  return struct.unpack_from("<I", b, p)[0], p + 4
def f32(b, p):  return struct.unpack_from("<f", b, p)[0], p + 4


def fvec(b, p):
    x, y, z = struct.unpack_from("<3f", b, p)
    return (x, y, z), p + 12


def frotator(b, p):
    pi, ya, ro = struct.unpack_from("<3i", b, p)
    return (pi, ya, ro), p + 12


def fbox(b, p):
    mn, p = fvec(b, p)
    mx, p = fvec(b, p)
    valid, p = u8(b, p)
    return (mn, mx, valid), p


def fsphere(b, p):
    c, p = fvec(b, p)
    r, p = f32(b, p)
    return (c, r), p


def tarray(b, p, elem):
    """Plain `TArray<T>`: compact count, then `count` elements via `elem(buf, pos)`."""
    n, p = read_compact_index(b, p)
    if n < 0 or n > 1 << 24:
        raise MeshParseError(f"implausible TArray count {n} at {p}")
    out = []
    for _ in range(n):
        v, p = elem(b, p)
        out.append(v)
    return out, p


def lazy_array(b, p, elem, *, version):
    """`TLazyArray<T>`: an `INT SkipOffset` (absolute file offset just past the element data;
    serialized only for package version > 61), then a compact count, then the elements.

    The skip offset is a free per-array checksum: after reading `count` elements the position MUST
    equal it. That makes each lazy array independently self-verifying, which is how a wrong element
    width gets caught at the array that has it rather than 200 bytes downstream.
    """
    skip = None
    if version > 61:
        skip, p = i32(b, p)
    n, p = read_compact_index(b, p)
    if n < 0 or n > 1 << 24:
        raise MeshParseError(f"implausible lazy-array count {n} at {p}")
    out = []
    for _ in range(n):
        v, p = elem(b, p)
        out.append(v)
    if skip is not None and skip != p:
        raise MeshParseError(f"lazy-array skip mismatch: header says {skip}, parse ended at {p} "
                             f"(count={n}, delta={p - skip})")
    return out, p


# ------------------------------------------------------------ mesh elements

def mesh_vert_dx(b, p):
    """Deus Ex `FMeshVert`: int16 X, Y, Z + int16 pad (8 bytes) — the licensee change."""
    x, y, z, _pad = struct.unpack_from("<4h", b, p)
    return (x, y, z), p + 8


def mesh_vert_packed(b, p):
    """Stock Unreal `FMeshVert`: one bit-packed dword, X:11 Y:11 Z:10 (signed)."""
    d, p = u32(b, p)
    x = (d & 0x7FF); x -= 0x800 if x > 0x3FF else 0
    y = ((d >> 11) & 0x7FF); y -= 0x800 if y > 0x3FF else 0
    z = ((d >> 22) & 0x3FF); z -= 0x400 if z > 0x1FF else 0
    return (x, y, z), p


def mesh_tri(b, p):
    """`FMeshTri`: WORD iVertex[3]; FMeshUV Tex[3] (BYTE U,V); DWORD PolyFlags; INT TextureIndex."""
    iv = struct.unpack_from("<3H", b, p); p += 6
    uv = struct.unpack_from("<6B", b, p); p += 6
    flags, p = u32(b, p)
    tex, p = i32(b, p)
    return (iv, uv, flags, tex), p


def mesh_anim_notify(b, p):
    time, p = f32(b, p)
    fn, p = read_compact_index(b, p)          # FName index
    return (time, fn), p


def mesh_anim_seq(b, p):
    """`FMeshAnimSeq`: FName Name; FName Group; INT StartFrame; INT NumFrames;
    TArray<FMeshAnimNotify> Notifys; FLOAT Rate.

    TWO traps, both of which desync the entire body downstream:
    1. `Group` is a SINGLE FName, not UT's later `TArray<FName> Groups`. Every sequence with no
       group writes a 0 byte, which reads identically as an empty TArray — so the difference only
       surfaces on a mesh that actually uses groups (`DeusExCharacters.Pigeon` seq5 `Idle1`,
       Group=17; the TArray reading takes 17 as a count and detonates).
    2. The SERIALIZED order is not the declaration order: `Notifys` comes BEFORE `Rate`.
       (`DeusExDeco.Keypad3` seq0: Name=12, Group=None, Start=0, NumFrames=1, Notifys=[], Rate=30.)
    """
    name, p = read_compact_index(b, p)
    group, p = read_compact_index(b, p)
    start, p = i32(b, p)
    nframes, p = i32(b, p)
    notifys, p = tarray(b, p, mesh_anim_notify)
    rate, p = f32(b, p)
    return (name, group, start, nframes, rate, notifys), p


def mesh_vert_connect(b, p):
    """`FMeshVertConnect`: INT NumVertTriangles; INT TriangleListOffset."""
    a, p = i32(b, p)
    c, p = i32(b, p)
    return (a, c), p


def mesh_face(b, p):
    """`FMeshFace`: WORD iWedge[3]; WORD MaterialIndex."""
    w0, w1, w2, mat = struct.unpack_from("<4H", b, p)
    return ((w0, w1, w2), mat), p + 8


def mesh_wedge(b, p):
    """`FMeshWedge`: WORD iVertex; FMeshUV TexUV (BYTE U, BYTE V)."""
    iv, u, v = struct.unpack_from("<HBB", b, p)
    return (iv, u, v), p + 4


def mesh_material(b, p):
    """`FMeshMaterial`: DWORD PolyFlags; INT TextureIndex."""
    flags, p = u32(b, p)
    tex, p = i32(b, p)
    return (flags, tex), p


def detect_vert_stride(b, p, *, version):
    """Vertex bytes-per-element, read off the Verts TLazyArray header without decoding anything:
    `(skip_offset - first_element_offset) / count`. Returns None for an empty array (nothing to
    measure), so the caller can fall back. 8 = Deus Ex int16 quad, 4 = stock Unreal packed dword."""
    if version <= 61:
        return None
    skip = struct.unpack_from("<i", b, p)[0]
    n, dp = read_compact_index(b, p + 4)
    if n <= 0:
        return None
    span = skip - dp
    return span // n if span > 0 and span % n == 0 else None


# ------------------------------------------------------------------- parser

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
    dx_tail_verts: int = 0        # DX licensee trailing INT (== FrameVerts in every sample)
    vert_stride: int = 0          # 8 = Deus Ex int16 quad, 4 = stock Unreal packed dword


def parse_mesh(pkg, j, *, vert8=None, strict_end=True):
    """Decode export `j` (a `Mesh`/`LodMesh`) fully. Raises `MeshParseError` on any desync or if
    the parse does not consume exactly to the export's end."""
    e = pkg.exports[j]
    b, ver = pkg.buf, pkg.version
    so, end = e["soff"], e["soff"] + e["ssize"]
    cls = pkg.object_class_name(j + 1)
    m = Mesh(name=pkg.names[e["nm"]], is_lod=(cls == "LodMesh"))

    _tags, p = read_property_tags(pkg, so, end)

    # --- UPrimitive
    m.box, p = fbox(b, p)
    m.sphere, p = fsphere(b, p)

    # --- UMesh
    # The vertex stride is SELF-DESCRIBING, so it never has to be configured per substrate: Verts
    # is a TLazyArray, whose header carries both the element count and the absolute offset just
    # past the data, so stride = (skip - data_start) / count. 8 ⇒ Deus Ex's int16 quad, 4 ⇒ stock
    # Unreal's bit-packed dword. That is what lets ONE decoder read Deus Ex `.u` and stock
    # Unreal/UT `.u` without a flag.
    stride = detect_vert_stride(b, p, version=ver)
    if stride is not None:
        vert8 = (stride == 8)
    elif vert8 is None:
        raise MeshParseError("cannot determine vertex stride (empty Verts array)")
    m.vert_stride = 8 if vert8 else 4
    vert = mesh_vert_dx if vert8 else mesh_vert_packed
    m.verts, p = lazy_array(b, p, vert, version=ver)
    m.tris, p = lazy_array(b, p, mesh_tri, version=ver)
    m.anim_seqs, p = tarray(b, p, mesh_anim_seq)
    m.connects, p = lazy_array(b, p, mesh_vert_connect, version=ver)
    # UMesh re-serializes its OWN bounds INLINE here (duplicating UPrimitive's, which were read
    # above) — not as arrays. Then the per-animation-frame bounds follow later as PLAIN TArrays
    # (only Verts/Tris/Connects/VertLinks — the big ones — are TLazyArrays).
    _own_box, p = fbox(b, p)
    _own_sphere, p = fsphere(b, p)
    m.vert_links, p = lazy_array(b, p, i32, version=ver)
    m.textures, p = tarray(b, p, read_compact_index)
    _bboxes, p = tarray(b, p, fbox)
    _bspheres, p = tarray(b, p, fsphere)
    m.frame_verts, p = i32(b, p)
    m.anim_frames, p = i32(b, p)
    _and_flags, p = u32(b, p)
    _or_flags, p = u32(b, p)
    m.scale, p = fvec(b, p)
    m.origin, p = fvec(b, p)
    m.rot_origin, p = frotator(b, p)
    _cur_poly, p = i32(b, p)
    _cur_vertex, p = i32(b, p)
    if ver == 65:
        _f, p = f32(b, p)
    elif ver >= 66:
        m.texture_lod, p = tarray(b, p, f32)

    # --- ULodMesh
    if m.is_lod:
        m.collapse_point_thus, p = tarray(b, p, u16)
        m.face_level, p = tarray(b, p, u16)
        m.faces, p = tarray(b, p, mesh_face)
        m.collapse_wedge_thus, p = tarray(b, p, u16)
        m.wedges, p = tarray(b, p, mesh_wedge)
        m.materials, p = tarray(b, p, mesh_material)
        m.special_faces, p = tarray(b, p, mesh_face)
        m.model_verts, p = i32(b, p)
        m.special_verts, p = i32(b, p)
        m.mesh_scale_max, p = f32(b, p)
        m.lod_hysteresis, p = f32(b, p)
        m.lod_strength, p = f32(b, p)
        m.lod_min_verts, p = i32(b, p)
        m.lod_morph, p = f32(b, p)
        m.lod_z_displace, p = f32(b, p)
        # --- Deus Ex licensee tail (5 bytes past where UT's ULodMesh ends).
        # An empty TArray (count 0 in every mesh of every DX package sampled) plus an INT that
        # equals FrameVerts/ModelVerts in 174/174 DeusExDeco meshes. Present on LodMesh ONLY —
        # the 4 plain `Mesh` exports consume exactly to the end without it. Element type of the
        # array is unknown-but-moot while the count is always 0; a non-zero count is a hard error
        # rather than a guess, so the corpus tells us if one ever appears.
        n_dx, p = read_compact_index(b, p)
        if n_dx != 0:
            raise MeshParseError(f"DX LodMesh tail array is non-empty (count={n_dx}) — element "
                                 f"layout unknown; re-probe this mesh")
        m.dx_tail_verts, p = i32(b, p)

    if strict_end and p != end:
        raise MeshParseError(f"{m.name}: consumed to {p}, export ends at {end} (delta {p - end})")
    return (m, p) if not strict_end else m


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
