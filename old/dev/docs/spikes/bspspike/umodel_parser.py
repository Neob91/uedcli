"""P0-a/P0-b1 feasibility spike — parse the built UModel out of a .dx file.

Goal: go/no-go on whether we can reliably extract Vectors, Points, Nodes, Surfs,
Verts, Leaves from a built .dx and locate BSP issues (invisible walls, fall-through,
T-junction T-points). This is the spike; if go, it promotes to uedcli/bsp/umodel.py.

Usage:
    python3 umodel_parser.py <path-to-.dx> [--model-export=N]
"""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# FCompactIndex (same as dxpkg._read_compact_index)
# ---------------------------------------------------------------------------

def _ci(buf: bytes, pos: int) -> tuple[int, int]:
    b = buf[pos]; pos += 1
    neg = b & 0x80
    val = b & 0x3F
    if b & 0x40:
        shift = 6
        while True:
            b = buf[pos]; pos += 1
            val |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
    return (-val if neg else val), pos


# ---------------------------------------------------------------------------
# Primitive readers
# ---------------------------------------------------------------------------

def _f32x3(buf: bytes, pos: int) -> tuple[tuple[float, float, float], int]:
    x, y, z = struct.unpack_from("<fff", buf, pos)
    return (x, y, z), pos + 12


def _f32x4(buf: bytes, pos: int) -> tuple[tuple[float, float, float, float], int]:
    x, y, z, w = struct.unpack_from("<ffff", buf, pos)
    return (x, y, z, w), pos + 16


def _u64(buf: bytes, pos: int) -> tuple[int, int]:
    return struct.unpack_from("<Q", buf, pos)[0], pos + 8


def _i32(buf: bytes, pos: int) -> tuple[int, int]:
    return struct.unpack_from("<i", buf, pos)[0], pos + 4


def _u32(buf: bytes, pos: int) -> tuple[int, int]:
    return struct.unpack_from("<I", buf, pos)[0], pos + 4


def _u8(buf: bytes, pos: int) -> tuple[int, int]:
    return buf[pos], pos + 1


def _u16(buf: bytes, pos: int) -> tuple[int, int]:
    return struct.unpack_from("<H", buf, pos)[0], pos + 2


# ---------------------------------------------------------------------------
# Element parsers — verified empirically against Model312 in 01_NYC_UNATCOHQ.dx
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class BspNode:
    plane: tuple          # FPlane (X,Y,Z,W) — partition plane
    zone_mask: int        # 64-bit zone bitmask
    node_flags: int       # 1-byte flags
    i_vert_pool: int      # index into Verts array
    i_surf: int           # index into Surfs array
    i_front: int          # front child node index (-1=leaf)
    i_back: int           # back child node index (-1=leaf)
    i_plane: int          # coplanar chain next node (-1=end)
    # ⚠ NAMES MISLABELED (kept for this legacy harness's self-consistent round-trip; corrected in
    #   spikes/2026-07-15-native-materialize/sections/50-model-ondisk-layout-and-render.md):
    #   the ci pair below called `i_leaf` is really iCollisionBound,iRenderBound; the trailing i32
    #   pair called `i_collision_bound`/`i_render_bound` is really iLeaf[0],iLeaf[1]. Both halves are
    #   consistently mislabeled so the parser↔serializer round-trip is still byte-exact.
    i_leaf: tuple         # ci [2] — REALLY (iCollisionBound, iRenderBound)
    i_zone: tuple         # [2] zone indices
    num_vertices: int     # vertices in this node's poly
    i_collision_bound: int  # raw INT32 — REALLY iLeaf[0] (-1 = solid)
    i_render_bound: int     # raw INT32 — REALLY iLeaf[1] (-1 = solid)


def _parse_node(buf: bytes, pos: int) -> tuple[BspNode, int]:
    plane, pos = _f32x4(buf, pos)
    zone_mask, pos = _u64(buf, pos)
    node_flags, pos = _u8(buf, pos)
    i_vert_pool, pos = _ci(buf, pos)
    i_surf, pos = _ci(buf, pos)
    i_front, pos = _ci(buf, pos)
    i_back, pos = _ci(buf, pos)
    i_plane, pos = _ci(buf, pos)
    i_leaf0, pos = _ci(buf, pos)
    i_leaf1, pos = _ci(buf, pos)
    i_zone0, pos = _ci(buf, pos)
    i_zone1, pos = _ci(buf, pos)
    num_v, pos = _ci(buf, pos)
    i_col, pos = _i32(buf, pos)
    i_ren, pos = _i32(buf, pos)
    return BspNode(
        plane=plane, zone_mask=zone_mask, node_flags=node_flags,
        i_vert_pool=i_vert_pool, i_surf=i_surf,
        i_front=i_front, i_back=i_back, i_plane=i_plane,
        i_leaf=(i_leaf0, i_leaf1), i_zone=(i_zone0, i_zone1),
        num_vertices=num_v,
        i_collision_bound=i_col, i_render_bound=i_ren,
    ), pos


@dataclass(frozen=True, kw_only=True)
class BspSurf:
    # Format derived by disassembling FBspSurf::Serialize in UED22 Engine.dll (RVA 0x16f760).
    # FPlane is in the in-memory struct at +0x28 but is NOT serialized in package files —
    # the conditional at 0x1016f817 only calls the FPlane serializer for transient/duplicate
    # archives (when both ArIsLoading and ArIsSaving are 0), never during normal load/save.
    # In-memory struct is 0x40 = 64 bytes (confirmed: shl eax,6 in loop at 0x1016ed0e).
    texture_ref: int      # ci obj ref at +0x00 (import = negative, 0=none)
    poly_flags: int       # raw DWORD at +0x04 (PF_NotSolid=8, PF_SemiSolid=0x20, PF_Portal=0x80)
    p_base: int           # ci at +0x08 — index into Points (-1=none)
    v_normal: int         # ci at +0x0C — index into Vectors (-1=none)
    v_texture_u: int      # ci at +0x10 — index into Vectors (-1=none)
    v_texture_v: int      # ci at +0x14 — index into Vectors (-1=none)
    i_actor: int          # ci at +0x18 — owning actor index (-1=none)
    i_brush_poly: int     # ci at +0x1C — brush polygon index (-1=none)
    i_zone: tuple         # raw2 × 2 at +0x20/+0x22 — zone indices
    i_field_0x24: int     # ci obj ref at +0x24 — iBrushActor or iLightMap


def _parse_surf(buf: bytes, pos: int) -> tuple[BspSurf, int]:
    # Serialization order from Engine.dll disasm (no FPlane in file):
    texture_ref, pos = _ci(buf, pos)          # ci obj ref
    poly_flags, pos = _u32(buf, pos)          # raw DWORD
    p_base, pos = _ci(buf, pos)               # ci
    v_normal, pos = _ci(buf, pos)             # ci
    v_texture_u, pos = _ci(buf, pos)          # ci
    v_texture_v, pos = _ci(buf, pos)          # ci
    i_actor, pos = _ci(buf, pos)              # ci (iActor at +0x18)
    i_brush_poly, pos = _ci(buf, pos)         # ci (iBrushPoly at +0x1C)
    i_zone0, pos = _u16(buf, pos)             # raw WORD
    i_zone1, pos = _u16(buf, pos)             # raw WORD
    i_field_0x24, pos = _ci(buf, pos)         # ci obj ref
    return BspSurf(
        texture_ref=texture_ref, poly_flags=poly_flags,
        p_base=p_base, v_normal=v_normal,
        v_texture_u=v_texture_u, v_texture_v=v_texture_v,
        i_actor=i_actor, i_brush_poly=i_brush_poly,
        i_zone=(i_zone0, i_zone1),
        i_field_0x24=i_field_0x24,
    ), pos


@dataclass(frozen=True, kw_only=True)
class BspVert:
    i_vertex: int   # index into Points
    i_side: int     # side index (for T-junction tracking)


def _parse_vert(buf: bytes, pos: int) -> tuple[BspVert, int]:
    # Both fields are compact_index (confirmed: Engine.dll 0x1010c1a0 uses [0x101f90ac] twice).
    # In-memory FBspVert is 8 bytes (2×INT), but serialized as ci+ci.
    i_vertex, pos = _ci(buf, pos)
    i_side, pos = _ci(buf, pos)
    return BspVert(i_vertex=i_vertex, i_side=i_side), pos


@dataclass(frozen=True, kw_only=True)
class BspLeaf:
    # Serial format from Engine.dll 0x1016f930 disassembly (element serializer for the
    # TArray<FBspLeaf> at UModel+0xd8, which has 20-byte in-memory elements).
    # Three ci fields then an 8-byte raw QWORD (iExclusive lighting bitmask).
    i_zone: int         # ci at mem+0x00 — zone index
    i_permeating: int   # ci at mem+0x04
    i_volumetric: int   # ci at mem+0x08
    i_exclusive: int    # raw QWORD at mem+0x0c (8 bytes; lighting exclusion bitmask)


def _parse_leaf(buf: bytes, pos: int) -> tuple[BspLeaf, int]:
    # Serialization from Engine.dll 0x1016f930: 3×ci via [0x101f90ac] then 8-byte raw.
    i_zone, pos = _ci(buf, pos)
    i_permeating, pos = _ci(buf, pos)
    i_volumetric, pos = _ci(buf, pos)
    i_exclusive, pos = _u64(buf, pos)   # raw 8 bytes (QWORD)
    return BspLeaf(
        i_zone=i_zone, i_permeating=i_permeating,
        i_volumetric=i_volumetric, i_exclusive=i_exclusive,
    ), pos


# ---------------------------------------------------------------------------
# TArray skippers for intermediate arrays before FBspLeaf at UModel+0xd8
# ---------------------------------------------------------------------------

def _skip_array_0xa8(data: bytes, pos: int) -> int:
    """Skip TArray<FLightMesh> at UModel+0xa8 (40-byte in-memory elements).
    Per-element serial (from Engine.dll 0x1016f9f0): 4raw + ci + ci + ci + 4raw + 4raw + 4raw
    = 16 + 3×ci bytes each.  Count via ci.
    """
    count, pos = _ci(data, pos)
    for _ in range(count):
        pos += 4              # raw 4 bytes at mem+0x00
        pos += 12             # 0x1010c160 reads 3×4 RAW bytes (NOT a ci) at mem+0x08/0x0c/0x10
        _, pos = _ci(data, pos)   # ci at mem+0x1c
        _, pos = _ci(data, pos)   # ci at mem+0x20
        pos += 4              # raw 4 bytes at mem+0x14
        pos += 4              # raw 4 bytes at mem+0x18
        pos += 4              # raw 4 bytes at mem+0x04
    return pos


def _skip_array_0xb4(data: bytes, pos: int) -> int:
    """Skip TArray<BYTE> at UModel+0xb4 (1-byte elements, bulk-serialized).
    Serial: ci count + count×1 bytes.
    """
    count, pos = _ci(data, pos)
    pos += count
    return pos


def _skip_array_0xc0(data: bytes, pos: int) -> int:
    """Skip TArray<FBox> at UModel+0xc0 (28-byte in-memory elements).
    Per-element serial (from Engine.dll 0x1016d550): 6×float32 + 1×BYTE = 25 bytes fixed.
    Count via ci.
    """
    count, pos = _ci(data, pos)
    pos += count * 25
    return pos


def _skip_array_0xcc(data: bytes, pos: int) -> int:
    """Skip TArray<INT> at UModel+0xcc (4-byte elements, raw-serialized).
    Serial: ci count + count×4 bytes raw.
    """
    count, pos = _ci(data, pos)
    pos += count * 4
    return pos


def _skip_array_0xe4(data: bytes, pos: int) -> int:
    """Skip TArray<INT> at UModel+0xe4 (4-byte in-memory elements, ci-serialized).
    Per-element serial (from Engine.dll 0x10167400): ci each.  Count via ci.
    """
    count, pos = _ci(data, pos)
    for _ in range(count):
        _, pos = _ci(data, pos)
    return pos


# ---------------------------------------------------------------------------
# TArray parser (compact_index count + N elements)
# ---------------------------------------------------------------------------

def _parse_array(buf: bytes, pos: int, parse_elem, label: str) -> tuple[list, int]:
    count, pos = _ci(buf, pos)
    elems = []
    for _ in range(count):
        elem, pos = parse_elem(buf, pos)
        elems.append(elem)
    return elems, pos


def _parse_fvector_array(buf: bytes, pos: int) -> tuple[list, int]:
    count, pos = _ci(buf, pos)
    vecs = []
    for _ in range(count):
        v, pos = _f32x3(buf, pos)
        vecs.append(v)
    return vecs, pos


# ---------------------------------------------------------------------------
# Export table parser (to find the largest Model export)
# ---------------------------------------------------------------------------

_MAGIC = 0x9E2A83C1


def _parse_export_table(buf: bytes):
    tag, ver_l, _flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff = \
        struct.unpack_from("<9I", buf, 0)
    assert tag == _MAGIC, f"bad magic {tag:#010x}"
    version = ver_l & 0xFFFF

    # Read name table
    pos = nameoff

    def _read_name(p):
        length, p = _ci(buf, p)
        if length < 0:
            nbytes = (-length) * 2
            s = buf[p:p+nbytes].decode("utf-16-le", "replace").split("\x00", 1)[0]
        else:
            nbytes = length
            s = buf[p:p+nbytes].split(b"\x00", 1)[0].decode("latin-1")
        return s, p + nbytes + 4

    names = []
    for _ in range(namecnt):
        s, pos = _read_name(pos)
        names.append(s)

    # Read export table: each entry is the UPackage export entry
    # Format (v69): ClassIndex(ci) SuperIndex(ci) PackageIndex(i32) ObjectName(ci)
    #               ObjectFlags(u32) SerialSize(ci) SerialOffset(ci)
    exports = []
    pos = expoff
    for _ in range(expcnt):
        class_idx, pos = _ci(buf, pos)
        super_idx, pos = _ci(buf, pos)
        pkg_idx = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        obj_name, pos = _ci(buf, pos)
        obj_flags, pos = _u32(buf, pos)
        serial_size, pos = _ci(buf, pos)
        serial_offset, pos = _ci(buf, pos)
        exports.append((class_idx, super_idx, pkg_idx, obj_name, obj_flags,
                        serial_size, serial_offset))

    return names, exports


def find_model_exports(dx_path: str) -> list[tuple]:
    """Return all exports whose name starts with 'Model', sorted by serial_size descending."""
    buf = open(dx_path, "rb").read()
    names, exports = _parse_export_table(buf)
    result = []
    for i, (ci, si, pi, name_idx, flags, size, offset) in enumerate(exports):
        name = names[name_idx] if 0 <= name_idx < len(names) else f"<{name_idx}>"
        if name.startswith("Model") or name == "Model":
            result.append((i, name, size, offset))
    result.sort(key=lambda x: -x[2])
    return result


# ---------------------------------------------------------------------------
# UPrimitive / UModel prefix
# UPrimitive prepends: None(ci=1B) + FBox(25B) + FSphere(16B) = 42 bytes total
# ---------------------------------------------------------------------------

_PREFIX = 42


@dataclass
class ParsedModel:
    vectors: list
    points: list
    nodes: list[BspNode]
    surfs: list[BspSurf]
    verts: list[BspVert]
    leaves: list[BspLeaf]
    num_shared_sides: int  # raw INT32 after Verts
    num_zones: int         # raw INT32 after NumSharedSides
    # validation helpers
    raw_offset: int   # serial offset in the .dx
    raw_size: int     # serial size in the .dx


def _skip_zone_data(data: bytes, pos: int, num_zones: int) -> int:
    """Skip the FZoneProperties[NumZones] block after NumZones.

    FZoneProperties serial format (confirmed from Engine.dll 0x1010c240):
      ci(ZoneActor obj-ref) + raw QWORD(Connectivity at +0x08) + raw QWORD(Visibility at +0x10)
    = ci + 8 + 8 bytes per zone.
    """
    for _ in range(num_zones):
        _zone_ref, pos = _ci(data, pos)   # ZoneActor object reference (compact_index)
        pos += 16                          # Connectivity (8) + Visibility (8)
    return pos


def parse_model_serial(buf: bytes, offset: int, size: int) -> ParsedModel:
    """Parse the serialized UModel data starting at `offset` in `buf`.

    Serial order (version > 61, confirmed from Engine.dll 0x1705a0 disassembly):
      UPrimitive prefix (42 bytes)
      → Vectors (TArray<FVector> at UModel+0x78)
      → Points  (TArray<FVector> at UModel+0x88)
      → Nodes   (TArray<FBspNode> at UModel+0x58)
      → Surfs   (TArray<FBspSurf> at UModel+0x98; no FPlane in file serial)
      → Verts   (TArray<FBspVert> at UModel+0x68; ci+ci per element)
      → NumSharedSides (raw INT32 at UModel+0xfc)
      → NumZones (raw INT32 at UModel+0x100)
      → FZoneProperties[NumZones] (ci+QWORD+QWORD each; from zone loop at 0x101707d8)
      → [conditional old-surfs block at 0x1017080b — skipped for normal saved .dx]
      → TArray<FLightMesh> at UModel+0xa8 (40-byte elems; 16+3ci serial each)
      → TArray<BYTE>       at UModel+0xb4 (1-byte elems; bulk)
      → TArray<FBox>       at UModel+0xc0 (28-byte elems; 25-byte serial each)
      → TArray<INT>        at UModel+0xcc (4-byte elems; 4-byte raw each)
      → TArray<FBspLeaf>   at UModel+0xd8 (20-byte elems; 3ci+8raw each) ← LEAVES
      → TArray<INT>        at UModel+0xe4 (4-byte elems; ci each)
      → raw INT32 at UModel+0xf0
      → raw INT32 at UModel+0xf4
    (From Engine.dll 0x10170820–0x101708c1, confirmed by disassembly.)
    """
    data = buf[offset:offset+size]
    pos = _PREFIX  # skip UPrimitive prefix

    vectors, pos = _parse_fvector_array(data, pos)
    points, pos = _parse_fvector_array(data, pos)
    nodes, pos = _parse_array(data, pos, _parse_node, "Nodes")
    surfs, pos = _parse_array(data, pos, _parse_surf, "Surfs")
    verts, pos = _parse_array(data, pos, _parse_vert, "Verts")

    num_shared_sides, pos = _i32(data, pos)
    num_zones, pos = _i32(data, pos)
    pos = _skip_zone_data(data, pos, num_zones)

    # After zone loop, UModel::Serialize ALWAYS serializes UModel+0x54 as ci (Engine.dll
    # 0x10170649: lea ecx,[esi+0x54]; call vtable[6](ci); this is the loop exit point).
    # The subsequent "old-surfs" conditional at 0x1017080b only executes its body when
    # loading (ArIsLoading) and [edi+0x18]=0, which is not the case for file-load archives.
    _field_0x54, pos = _ci(data, pos)

    # Skip 4 intermediate TArrays then parse FBspLeaf
    pos = _skip_array_0xa8(data, pos)
    pos = _skip_array_0xb4(data, pos)
    pos = _skip_array_0xc0(data, pos)
    pos = _skip_array_0xcc(data, pos)
    leaves, pos = _parse_array(data, pos, _parse_leaf, "Leaves")
    pos = _skip_array_0xe4(data, pos)

    return ParsedModel(
        vectors=vectors, points=points, nodes=nodes,
        surfs=surfs, verts=verts, leaves=leaves,
        num_shared_sides=num_shared_sides, num_zones=num_zones,
        raw_offset=offset, raw_size=size,
    )


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

PF_INVISIBLE   = 0x0001
PF_NOT_SOLID   = 0x0008
PF_SEMI_SOLID  = 0x0020
PF_PORTAL      = 0x0080


def sanity_check(m: ParsedModel) -> list[str]:
    issues = []

    # Index bounds checks
    n_pts  = len(m.points)
    n_vecs = len(m.vectors)
    n_verts = len(m.verts)
    n_surfs = len(m.surfs)
    n_nodes = len(m.nodes)

    vert_ivertex_oob = sum(1 for v in m.verts if not (0 <= v.i_vertex < n_pts))
    if vert_ivertex_oob:
        issues.append(f"FAIL: {vert_ivertex_oob} Verts have out-of-bounds i_vertex (max={n_pts-1})")

    node_isurf_oob = sum(1 for n in m.nodes if not (0 <= n.i_surf < n_surfs))
    if node_isurf_oob:
        issues.append(f"FAIL: {node_isurf_oob} Nodes have out-of-bounds i_surf (max={n_surfs-1})")

    node_ivert_oob = 0
    for n in m.nodes:
        end = n.i_vert_pool + n.num_vertices
        if n.i_vert_pool < 0 or end > n_verts:
            node_ivert_oob += 1
    if node_ivert_oob:
        issues.append(f"FAIL: {node_ivert_oob} Nodes have out-of-bounds i_vert_pool range")

    # -1 is a valid "null" sentinel in UE1 for all index fields
    surf_pbase_oob = sum(1 for s in m.surfs if not (-1 <= s.p_base < n_pts))
    if surf_pbase_oob:
        issues.append(f"FAIL: {surf_pbase_oob} Surfs have out-of-bounds p_base (max={n_pts-1})")

    surf_vnorm_oob = sum(1 for s in m.surfs if not (-1 <= s.v_normal < n_vecs))
    if surf_vnorm_oob:
        issues.append(f"FAIL: {surf_vnorm_oob} Surfs have out-of-bounds v_normal (max={n_vecs-1})")

    # PolyFlags is a raw DWORD — any 32-bit value is valid. Flag consistency check: if the
    # high 16 bits are set on more than 10% of surfs, something is probably off.
    high_flags = sum(1 for s in m.surfs if s.poly_flags & 0xFFFF0000)
    if n_surfs and high_flags > n_surfs * 0.9:
        issues.append(f"WARN: {high_flags}/{n_surfs} Surfs have flags in high 16 bits "
                      f"(may indicate wrong parsing)")

    # Leaf iZone bounds
    n_leaves = len(m.leaves)
    if n_leaves and m.num_zones > 0:
        leaf_zone_oob = sum(1 for lf in m.leaves if not (-1 <= lf.i_zone < m.num_zones))
        if leaf_zone_oob > n_leaves * 0.5:
            issues.append(f"WARN: {leaf_zone_oob}/{n_leaves} Leaves have i_zone outside "
                          f"[-1,{m.num_zones}) — may indicate parse error")

    return issues


def report_model(m: ParsedModel, label: str) -> None:
    print(f"\n=== {label} ===")
    print(f"  Vectors:        {len(m.vectors)}")
    print(f"  Points:         {len(m.points)}")
    print(f"  Nodes:          {len(m.nodes)}")
    print(f"  Surfs:          {len(m.surfs)}")
    print(f"  Verts:          {len(m.verts)}")
    print(f"  Leaves:         {len(m.leaves)}")
    print(f"  NumSharedSides: {m.num_shared_sides}")
    print(f"  NumZones:       {m.num_zones}")

    issues = sanity_check(m)
    if issues:
        for iss in issues:
            print(f"  {iss}")
    else:
        print("  All sanity checks PASS")

    # Sample values
    if m.vectors:
        print(f"  Vectors[0]: {m.vectors[0]}")
        print(f"  Vectors[1]: {m.vectors[1]}")
    if m.points:
        print(f"  Points[0]: {m.points[0]}")
    if m.nodes:
        n = m.nodes[0]
        print(f"  Nodes[0]: plane={n.plane} iSurf={n.i_surf} iVertPool={n.i_vert_pool} nVerts={n.num_vertices}")
    if m.surfs:
        s = m.surfs[0]
        print(f"  Surfs[0]: polyFlags={s.poly_flags:#010x} pBase={s.p_base} vNormal={s.v_normal} "
              f"vTexU={s.v_texture_u} vTexV={s.v_texture_v} iActor={s.i_actor} "
              f"iBrushPoly={s.i_brush_poly} iZone={s.i_zone}")
    if m.verts:
        v = m.verts[0]
        print(f"  Verts[0]: iVertex={v.i_vertex} iSide={v.i_side}")
    if m.leaves:
        lf = m.leaves[0]
        print(f"  Leaves[0]: iZone={lf.i_zone} iPermeating={lf.i_permeating} "
              f"iVolumetric={lf.i_volumetric} iExclusive={lf.i_exclusive:#018x}")

    # P0-b1: T-junction reconstruction probe
    # Check a few Nodes' vertex chains
    n_pts = len(m.points)
    n_verts = len(m.verts)
    reconstructable = 0
    for i, n in enumerate(m.nodes[:20]):
        if n.i_vert_pool < 0 or n.i_vert_pool + n.num_vertices > n_verts:
            continue
        ok = all(0 <= m.verts[n.i_vert_pool + j].i_vertex < n_pts
                 for j in range(n.num_vertices))
        if ok:
            reconstructable += 1
    print(f"  T-junction probe: {reconstructable}/{min(20, len(m.nodes))} sampled nodes "
          "have valid vertex chains (iVertPool→Verts→Points)")

    # BSP issue candidates from PolyFlags
    not_solid = [i for i, s in enumerate(m.surfs) if s.poly_flags & PF_NOT_SOLID]
    semi_solid = [i for i, s in enumerate(m.surfs) if s.poly_flags & PF_SEMI_SOLID]
    portal = [i for i, s in enumerate(m.surfs) if s.poly_flags & PF_PORTAL]
    if not_solid:
        print(f"  PF_NotSolid surfs (fall-through candidates): {len(not_solid)}")
    if semi_solid:
        print(f"  PF_SemiSolid surfs: {len(semi_solid)}")
    if portal:
        print(f"  PF_Portal surfs: {len(portal)}")
    if m.surfs:
        flags_sample = sorted({s.poly_flags for s in m.surfs[:20]})
        print(f"  PolyFlags sample (first 20 surfs): {[hex(f) for f in flags_sample]}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv):
    if len(argv) < 2:
        print("usage: umodel_parser.py <path.dx> [--model-export=N]")
        return 1

    dx_path = argv[1]
    buf = open(dx_path, "rb").read()

    model_exports = find_model_exports(dx_path)
    if not model_exports:
        print("No Model exports found")
        return 1

    print(f"Found {len(model_exports)} Model exports:")
    for i, (exp_idx, name, size, offset) in enumerate(model_exports[:8]):
        print(f"  [{i}] exp[{exp_idx}] {name:20s} size={size:>10,}  offset={offset:#010x}")

    # Parse the target model(s)
    # By default parse the 3 smallest (for sanity) + the largest (the level BSP)
    targets = model_exports[-3:] + [model_exports[0]]  # 3 smallest + largest
    seen = set()
    for exp_idx, name, size, offset in targets:
        if exp_idx in seen:
            continue
        seen.add(exp_idx)
        print(f"\nParsing exp[{exp_idx}] {name} (size={size}, offset={offset:#010x})…")
        try:
            m = parse_model_serial(buf, offset, size)
            report_model(m, f"exp[{exp_idx}] {name}")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
