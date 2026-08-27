"""UModel (BSP) body: parse (self-check re-read) + write-from-arrays (Python oracle).

Promoted from `spikes/bspspike/umodel_parser.py` (byte-exact read, reaches EOF on real
maps) and `umodel_serialize.py` (byte-exact re-emit).  The parser feeds the always-on
self-check; `write_model_body` is the Python DEV ORACLE the Rust `model_write.rs` is
pinned to byte-for-byte (§6 gate 5).  It serializes a `Model` (all arrays held as
Python structures) into the UModel serial body — the from-scratch write the round-trip
harness did not need.

Serial order (ver > 61):
  UPrimitive prefix (42B: ci(None) + FBox 25 + FSphere 16)
  Vectors, Points          (TArray<FVector>)
  Nodes, Surfs, Verts      (TArray, ci count)
  i32 NumSharedSides, i32 NumZones
  NumZones * FZoneProperties (ci ZoneActor + 16 raw bytes)
  ci field_0x54
  TArray a8 (LightMap) / b4 (LightBits)  (lightmap bake; empty unlit)
  TArray c0 Bounds<FBox> / cc LeafHulls<INT>  (render/collision bounds; the Rust FilterBound port
                                               `passes::bsp_build_bounds` now populates BOTH — c0
                                               render FBoxes + cc box-sweep collision hulls)
  TArray<FBspLeaf> Leaves
  TArray e4                 (aux; empty)
  i32, i32                  (trailing)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .codec import (write_ci, read_ci, enc_i32, enc_u32, enc_u16, enc_u8,
                    enc_u64, enc_f32, enc_f32x3, enc_f32x4)

_PREFIX = 42


# --- element structures ----------------------------------------------------

@dataclass
class BspNode:
    plane: tuple            # (X, Y, Z, W)
    zone_mask: int = 0xFFFFFFFFFFFFFFFF
    node_flags: int = 0
    i_vert_pool: int = 0
    i_surf: int = 0
    i_front: int = -1
    i_back: int = -1
    i_plane: int = -1
    # On-disk FBspNode order (DX v68, spike 50-model-ondisk-layout-and-render.md):
    #   ...iPlane, iCollisionBound(ci), iRenderBound(ci), iZone[2](ci), NumVertices(ci),
    #      iLeaf[2](fixed i32).  Bounds indices are ci and precede iZone; iLeaf is a trailing
    #      fixed-i32 pair.  (-1 collision/render bound => renderer skips the bound test.)
    i_collision_bound: int = -1
    i_render_bound: int = -1
    i_zone: tuple = (0, 0)
    num_vertices: int = 0
    i_leaf: tuple = (-1, -1)


@dataclass
class BspSurf:
    texture_ref: int = 0    # obj-ref of the texture (import<0) or 0=none
    poly_flags: int = 0
    p_base: int = 0         # index into Points
    v_normal: int = 0       # index into Vectors
    v_texture_u: int = 0
    v_texture_v: int = 0
    i_actor: int = 0        # owning brush actor ref (0=none)
    i_brush_poly: int = -1
    # (PanU, PanV) — the surface's authored texture pan, two SWORDs on disk, read raw as unsigned
    # (a negative pan reads back as 65536+n).  Not a zone pair; the evidence is on the Rust
    # `model::BspSurf::pan`, the same struct.
    pan: tuple = (0, 0)
    i_light_map: int = -1   # +0x24 == iLightMap (-1 = unlit)


@dataclass
class BspVert:
    i_vertex: int           # index into Points
    i_side: int = -1


@dataclass
class BspLeaf:
    i_zone: int = 0
    i_permeating: int = -1
    i_volumetric: int = -1
    i_exclusive: int = 0


@dataclass
class Zone:
    actor_ref: int = 0
    connectivity: int = 0xFFFFFFFFFFFFFFFF
    visibility: int = 0xFFFFFFFFFFFFFFFF


@dataclass
class FBox:
    """UModel `Bounds` element (+0xc0; 25-byte serial = 6×f32 + 1 valid byte, 28 B in mem).
    Used for render-bound culling (`iRenderBound`); the native build now POPULATES this via the
    Rust FilterBound port (one valid FBox per interior node — spike section 50 / 82c)."""
    min: tuple = (0.0, 0.0, 0.0)
    max: tuple = (0.0, 0.0, 0.0)
    valid: int = 1


@dataclass
class LightMapIndex:
    """One `FLightMapIndex` (UModel+0xa8; the per-surface lumel-grid descriptor from the
    `LIGHT APPLY` bake — spike section 20-lighting-bake.md §4).  Serial order:
      raw_i32(data_offset), f32 pan(x,y,z), ci(u_size), ci(v_size), f32 u_scale/v_scale,
      raw_i32(i_light_actors)."""
    data_offset: int = 0
    i_light_actors: int = -1        # index into Model.lights; -1 = reached by no light (dark)
    pan: tuple = (0.0, 0.0, 0.0)    # (Umin-0.125, Vmin-0.125, 0)
    u_scale: float = 0.0
    v_scale: float = 0.0
    u_size: int = 0
    v_size: int = 0


@dataclass
class Model:
    vectors: list = field(default_factory=list)
    points: list = field(default_factory=list)
    nodes: list = field(default_factory=list)
    surfs: list = field(default_factory=list)
    verts: list = field(default_factory=list)
    num_shared_sides: int = 0
    zones: list = field(default_factory=list)      # list[Zone]
    field_0x54: int = 0
    # Collision/render bound arrays (spike section 50 §3 + re-raw-zones/linecheck-oracle.md).
    #   `bounds`     (UModel+0xc0, TArray<FBox>)  — render-bound culling; indexed by node
    #                 `i_render_bound`.  EMPTY for a native build (render works without it).
    #   `leaf_hulls` (UModel+0xcc, TArray<INT>)   — the per-solid-leaf CONVEX HULL the game's
    #                 box-sweep collision (`FBoxLineCheckInfo::BoxLineCheck` 0xf42f0) clips against,
    #                 indexed by node `i_collision_bound`.  Each run:
    #                 `[plane-node ref (|0x40000000 = FLIP), ..., -1, 6× raw-i32-bitcast f32 bbox]`.
    #                 REQUIRED for a walkable pawn (a box sweep has NO node-plane fallback — an
    #                 `i_collision_bound=-1` node is non-solid to any extent!=0 trace).
    bounds: list = field(default_factory=list)       # list[FBox]
    leaf_hulls: list = field(default_factory=list)    # list[int] (raw INT array, incl. bitcast bbox)
    leaves: list = field(default_factory=list)
    # LIGHT APPLY bake output (spike section 20).  Empty for an unlit build.  `light_map` is the
    # FLightMapIndex array (a8); `light_bits` the packed shadow planes (b4); `lights` the flattened
    # per-surf light runs (e4) — 0-based light INDICES + -1 NULL terminators until assembly
    # (`_patch_light_refs`) rewrites them to export object-refs.
    light_map: list = field(default_factory=list)   # list[LightMapIndex]
    light_bits: bytes = b""
    lights: list = field(default_factory=list)       # list[int]
    none_index: int = 0                            # name index of "None" (for the prefix)
    bbox_min: tuple = (0.0, 0.0, 0.0)
    bbox_max: tuple = (0.0, 0.0, 0.0)


# --- writer (Python oracle) ------------------------------------------------

def _enc_fvector_array(vecs) -> bytes:
    out = bytearray(write_ci(len(vecs)))
    for v in vecs:
        out += enc_f32x3(v)
    return bytes(out)


def _enc_node(n: BspNode) -> bytes:
    out = bytearray()
    out += enc_f32x4(n.plane)
    out += enc_u64(n.zone_mask)
    out += enc_u8(n.node_flags)
    out += write_ci(n.i_vert_pool)
    out += write_ci(n.i_surf)
    out += write_ci(n.i_front)
    out += write_ci(n.i_back)
    out += write_ci(n.i_plane)
    out += write_ci(n.i_collision_bound)   # ci: Bounds-array index (-1 => guard skips)
    out += write_ci(n.i_render_bound)      # ci: Bounds-array index (-1 => guard skips)
    out += write_ci(n.i_zone[0])
    out += write_ci(n.i_zone[1])
    out += write_ci(n.num_vertices)
    out += enc_i32(n.i_leaf[0])            # fixed i32: iLeaf[0]
    out += enc_i32(n.i_leaf[1])            # fixed i32: iLeaf[1]
    return bytes(out)


def _enc_surf(s: BspSurf) -> bytes:
    # FBspSurf on-disk order (VERIFIED vs real maps DXOnly/DX/Entry, 2026-07-16):
    #   Texture, PolyFlags, pBase, vNormal, vTextureU, vTextureV, **iLightMap**, iBrushPoly,
    #   PanU, PanV, **iActor**.  iLightMap is the 7th field (right after vTextureV) and
    #   the OWNING-BRUSH iActor is the LAST field — NOT the reverse.  Getting these two swapped
    #   made the game read iLightMap from our iActor slot (a large brush ref) → out-of-range
    #   Model.LightMap[] → garbage FLightMapIndex.iLightActors → bad Model.Lights[] pointer →
    #   the per-frame access violation in AddLight (Render.dll 0x10b08b4a).  The swap is invisible
    #   to the self-check (parse+encode share the order and still reach EOF).
    out = bytearray()
    out += write_ci(s.texture_ref)
    out += enc_u32(s.poly_flags)
    out += write_ci(s.p_base)
    out += write_ci(s.v_normal)
    out += write_ci(s.v_texture_u)
    out += write_ci(s.v_texture_v)
    out += write_ci(s.i_light_map)      # slot 7: iLightMap (index into Model.LightMap, or -1)
    out += write_ci(s.i_brush_poly)
    out += enc_u16(s.pan[0] & 0xFFFF)
    out += enc_u16(s.pan[1] & 0xFFFF)
    out += write_ci(s.i_actor)          # last: iActor (owning brush actor obj-ref, 0=none)
    return bytes(out)


def _enc_vert(v: BspVert) -> bytes:
    return write_ci(v.i_vertex) + write_ci(v.i_side)


def _enc_lightmap_index(l: LightMapIndex) -> bytes:
    return (enc_i32(l.data_offset) + enc_f32x3(l.pan)
            + write_ci(l.u_size) + write_ci(l.v_size)
            + enc_f32(l.u_scale) + enc_f32(l.v_scale) + enc_i32(l.i_light_actors))


def _enc_leaf(lf: BspLeaf) -> bytes:
    return (write_ci(lf.i_zone) + write_ci(lf.i_permeating)
            + write_ci(lf.i_volumetric) + enc_u64(lf.i_exclusive))


def _enc_array(elems, enc) -> bytes:
    out = bytearray(write_ci(len(elems)))
    for e in elems:
        out += enc(e)
    return bytes(out)


def _enc_prefix(m: Model) -> bytes:
    # ci(None) + FBox(6 f32 + 1 byte IsValid) + FSphere(3 f32 + 1 f32)
    out = bytearray(write_ci(m.none_index))
    if len(out) != 1:
        raise ValueError("Model 'None' name index must encode to a single byte "
                         f"(index {m.none_index}); keep it < 64")
    # FBox IsValid: UnrealEd leaves the level UModel's UPrimitive bbox uncomputed at save and
    # serializes IsValid=0 (verified vs DX/Maps/Test_Castle.dx prefix byte 25 == 0, 2026-07-18).
    out += enc_f32x3(m.bbox_min) + enc_f32x3(m.bbox_max) + enc_u8(0)   # FBox IsValid
    cx = (m.bbox_min[0] + m.bbox_max[0]) / 2.0
    cy = (m.bbox_min[1] + m.bbox_max[1]) / 2.0
    cz = (m.bbox_min[2] + m.bbox_max[2]) / 2.0
    out += enc_f32x3((cx, cy, cz)) + enc_f32(0.0)                      # FSphere
    assert len(out) == _PREFIX, len(out)
    return bytes(out)


def write_model_body(m: Model) -> bytes:
    out = bytearray()
    out += _enc_prefix(m)
    out += _enc_fvector_array(m.vectors)
    out += _enc_fvector_array(m.points)
    out += _enc_array(m.nodes, _enc_node)
    out += _enc_array(m.surfs, _enc_surf)
    out += _enc_array(m.verts, _enc_vert)
    out += enc_i32(m.num_shared_sides)
    out += enc_i32(len(m.zones))
    for z in m.zones:
        out += write_ci(z.actor_ref) + enc_u64(z.connectivity) + enc_u64(z.visibility)
    out += write_ci(m.field_0x54)
    # a8 LightMap (FLightMapIndex), b4 LightBits (BYTE array) — lightmap bake output (section 20);
    # empty for an unlit build (ci(0), byte-identical to the old stub).
    out += _enc_array(m.light_map, _enc_lightmap_index)
    out += write_ci(len(m.light_bits)) + bytes(m.light_bits)
    # c0 Bounds (TArray<FBox>): 6×f32 + 1 valid byte per element (25 B serial).  Populated on native.
    out += write_ci(len(m.bounds))
    for b in m.bounds:
        out += enc_f32x3(b.min) + enc_f32x3(b.max) + enc_u8(b.valid & 0xFF)
    # cc LeafHulls (TArray<INT>): the box-sweep collision hulls (raw INT array, incl. bitcast bbox).
    out += write_ci(len(m.leaf_hulls))
    for i in m.leaf_hulls:
        out += enc_i32(i)
    out += _enc_array(m.leaves, _enc_leaf)
    # e4 Lights (object-refs; 0-based light indices + -1 NULL terminators until _patch_light_refs).
    out += write_ci(len(m.lights))
    for r in m.lights:
        out += write_ci(r)
    out += enc_i32(0)       # trailing i32
    out += enc_i32(0)       # trailing i32
    return bytes(out)


# --- parser (self-check re-read) -------------------------------------------

def _f32x3(buf, pos):
    return struct.unpack_from("<fff", buf, pos), pos + 12


def _f32x4(buf, pos):
    return struct.unpack_from("<ffff", buf, pos), pos + 16


def _i32(buf, pos):
    return struct.unpack_from("<i", buf, pos)[0], pos + 4


def _u32(buf, pos):
    return struct.unpack_from("<I", buf, pos)[0], pos + 4


def _u16(buf, pos):
    return struct.unpack_from("<H", buf, pos)[0], pos + 2


def _u64(buf, pos):
    return struct.unpack_from("<Q", buf, pos)[0], pos + 8


def _fvector_array(buf, pos):
    count, pos = read_ci(buf, pos)
    vecs = []
    for _ in range(count):
        v, pos = _f32x3(buf, pos); vecs.append(v)
    return vecs, pos


def _parse_node(buf, pos):
    plane, pos = _f32x4(buf, pos)
    zone_mask, pos = _u64(buf, pos)
    node_flags = buf[pos]; pos += 1
    i_vert_pool, pos = read_ci(buf, pos)
    i_surf, pos = read_ci(buf, pos)
    i_front, pos = read_ci(buf, pos)
    i_back, pos = read_ci(buf, pos)
    i_plane, pos = read_ci(buf, pos)
    ic, pos = read_ci(buf, pos); ir, pos = read_ci(buf, pos)   # iCollisionBound, iRenderBound (ci)
    z0, pos = read_ci(buf, pos); z1, pos = read_ci(buf, pos)
    nv, pos = read_ci(buf, pos)
    l0, pos = _i32(buf, pos); l1, pos = _i32(buf, pos)          # iLeaf[0], iLeaf[1] (fixed i32)
    return BspNode(plane=plane, zone_mask=zone_mask, node_flags=node_flags,
                   i_vert_pool=i_vert_pool, i_surf=i_surf, i_front=i_front,
                   i_back=i_back, i_plane=i_plane,
                   i_collision_bound=ic, i_render_bound=ir,
                   i_zone=(z0, z1), num_vertices=nv, i_leaf=(l0, l1)), pos


def _parse_surf(buf, pos):
    # See _enc_surf for the verified field order: iLightMap is slot 7, iActor is last.
    texture_ref, pos = read_ci(buf, pos)
    poly_flags, pos = _u32(buf, pos)
    p_base, pos = read_ci(buf, pos)
    v_normal, pos = read_ci(buf, pos)
    v_u, pos = read_ci(buf, pos)
    v_v, pos = read_ci(buf, pos)
    i_light_map, pos = read_ci(buf, pos)      # slot 7: iLightMap
    i_brush_poly, pos = read_ci(buf, pos)
    pan_u, pos = _u16(buf, pos); pan_v, pos = _u16(buf, pos)
    i_actor, pos = read_ci(buf, pos)          # last: iActor
    return BspSurf(texture_ref=texture_ref, poly_flags=poly_flags, p_base=p_base,
                   v_normal=v_normal, v_texture_u=v_u, v_texture_v=v_v,
                   i_actor=i_actor, i_brush_poly=i_brush_poly, pan=(pan_u, pan_v),
                   i_light_map=i_light_map), pos


def _parse_vert(buf, pos):
    iv, pos = read_ci(buf, pos)
    isd, pos = read_ci(buf, pos)
    return BspVert(i_vertex=iv, i_side=isd), pos


def _parse_leaf(buf, pos):
    iz, pos = read_ci(buf, pos)
    ip, pos = read_ci(buf, pos)
    ivo, pos = read_ci(buf, pos)
    ie, pos = _u64(buf, pos)
    return BspLeaf(i_zone=iz, i_permeating=ip, i_volumetric=ivo, i_exclusive=ie), pos


def _parse_array(buf, pos, parse_elem):
    count, pos = read_ci(buf, pos)
    elems = []
    for _ in range(count):
        e, pos = parse_elem(buf, pos); elems.append(e)
    return elems, pos


def _parse_lightmap_index(buf, pos):
    data_offset, pos = _i32(buf, pos)
    pan, pos = _f32x3(buf, pos)
    u_size, pos = read_ci(buf, pos)
    v_size, pos = read_ci(buf, pos)
    u_scale, pos = struct.unpack_from("<f", buf, pos)[0], pos + 4
    v_scale, pos = struct.unpack_from("<f", buf, pos)[0], pos + 4
    i_light_actors, pos = _i32(buf, pos)
    return LightMapIndex(data_offset=data_offset, i_light_actors=i_light_actors, pan=pan,
                         u_scale=u_scale, v_scale=v_scale, u_size=u_size, v_size=v_size), pos


def _parse_a8(buf, pos):
    """LightMap (FLightMapIndex array) — retained (round-trips through the self-check/patch)."""
    count, pos = read_ci(buf, pos)
    lm = []
    for _ in range(count):
        e, pos = _parse_lightmap_index(buf, pos)
        lm.append(e)
    return lm, pos


def _parse_bulk_bytes(buf, pos):
    count, pos = read_ci(buf, pos)
    return bytes(buf[pos:pos + count]), pos + count


def _parse_c0(buf, pos):
    """Bounds (TArray<FBox>): 6×f32 + 1 valid byte per element (25 B serial)."""
    count, pos = read_ci(buf, pos)
    boxes = []
    for _ in range(count):
        mn, pos = _f32x3(buf, pos)
        mx, pos = _f32x3(buf, pos)
        valid = buf[pos]; pos += 1
        boxes.append(FBox(min=mn, max=mx, valid=valid))
    return boxes, pos


def _parse_cc(buf, pos):
    """LeafHulls (TArray<INT>): raw INT array (plane refs, -1 terminators, bitcast-f32 bbox)."""
    count, pos = read_ci(buf, pos)
    ints = list(struct.unpack_from("<%di" % count, buf, pos)) if count else []
    return ints, pos + count * 4


def _parse_e4(buf, pos):
    """Lights (object-ref array) — retained; entries are export/import refs (or the intermediate
    light-index + -1-terminator form before assembly patches them)."""
    count, pos = read_ci(buf, pos)
    refs = []
    for _ in range(count):
        r, pos = read_ci(buf, pos)
        refs.append(r)
    return refs, pos


def parse_model_body(buf: bytes, offset: int, size: int) -> Model:
    """Parse a UModel serial body to EOF; raises on any inconsistency (the self-check
    relies on the reach-EOF assertion)."""
    data = buf[offset:offset + size]
    pos = _PREFIX
    vectors, pos = _fvector_array(data, pos)
    points, pos = _fvector_array(data, pos)
    nodes, pos = _parse_array(data, pos, _parse_node)
    surfs, pos = _parse_array(data, pos, _parse_surf)
    verts, pos = _parse_array(data, pos, _parse_vert)
    num_shared, pos = _i32(data, pos)
    num_zones, pos = _i32(data, pos)
    zones = []
    for _ in range(num_zones):
        ref, pos = read_ci(data, pos)
        conn, pos = _u64(data, pos)
        vis, pos = _u64(data, pos)
        zones.append(Zone(actor_ref=ref, connectivity=conn, visibility=vis))
    field_0x54, pos = read_ci(data, pos)
    light_map, pos = _parse_a8(data, pos)
    light_bits, pos = _parse_bulk_bytes(data, pos)
    bounds, pos = _parse_c0(data, pos)
    leaf_hulls, pos = _parse_cc(data, pos)
    leaves, pos = _parse_array(data, pos, _parse_leaf)
    lights, pos = _parse_e4(data, pos)
    _, pos = _i32(data, pos)
    _, pos = _i32(data, pos)
    if pos != size:
        raise ValueError(f"UModel body did not reach EOF: {pos} != {size}")
    return Model(vectors=vectors, points=points, nodes=nodes, surfs=surfs,
                 verts=verts, num_shared_sides=num_shared, zones=zones,
                 field_0x54=field_0x54, bounds=bounds, leaf_hulls=leaf_hulls,
                 leaves=leaves, light_map=light_map,
                 light_bits=light_bits, lights=lights)
