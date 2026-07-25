"""Spike: serialize a built UModel (BSP) body back to bytes, byte-identically.

The de-containerization "native geometry write" path needs proof that a UModel
body can be re-serialized from its parsed structure byte-for-byte. The READ
parser (`umodel_parser.parse_model_serial`) is validated byte-exact (reaches EOF
on real maps); this module builds and validates the WRITE (the mechanical
inverse).

Design (the whole point of the spike):
  - The GEOMETRY arrays (Vectors, Points, Nodes, Surfs, Verts, the
    NumSharedSides/NumZones scalars, the FZoneProperties zone block, field_0x54,
    and the FBspLeaf Leaves array) are RE-EMITTED FROM STRUCTURE — each dataclass
    field round-trips through an inverse primitive encoder.
  - The arrays the parser only SKIPS (the 42-byte UPrimitive prefix, the
    0xa8/0xb4/0xc0/0xcc aux arrays, the 0xe4 array, the two trailing INTs) are
    captured as RAW (start, end) byte spans during a recording walk and spliced
    back verbatim.

A single recording pass walks the body exactly like `parse_model_serial` but
emits a list of segments; each segment is either a structured re-encode or a raw
byte span. The serializer concatenates them; the result must equal the original
body `buf[offset:offset+size]` exactly.

Usage:
    python3 umodel_serialize.py                 # validate the corpus
    python3 umodel_serialize.py <path.dx>       # validate one map's models
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import umodel_parser as P


# ---------------------------------------------------------------------------
# Inverse primitive encoders
# ---------------------------------------------------------------------------

def enc_ci(value: int) -> bytes:
    """Encode an FCompactIndex (canonical-minimal, matching the engine writer).

    Byte 0:  bit7 = sign(value<0), bit6 = "more bytes follow", bits0-5 = low 6 bits.
    Byte 1+: bit7 = "more bytes follow", bits0-6 = next 7 bits.

    Inverse of `umodel_parser._ci`. Engine output is canonical-minimal: the
    continuation bit is set iff there is a non-zero remainder to encode.
    """
    neg = value < 0
    v = -value if neg else value
    out = bytearray()
    b0 = (0x80 if neg else 0) | (v & 0x3F)
    v >>= 6
    if v:
        b0 |= 0x40  # continuation
    out.append(b0)
    while v:
        b = v & 0x7F
        v >>= 7
        if v:
            b |= 0x80  # continuation
        out.append(b)
    return bytes(out)


def enc_f32x3(t: tuple[float, float, float]) -> bytes:
    return struct.pack("<fff", *t)


def enc_f32x4(t: tuple[float, float, float, float]) -> bytes:
    return struct.pack("<ffff", *t)


def enc_u64(v: int) -> bytes:
    return struct.pack("<Q", v)


def enc_i32(v: int) -> bytes:
    return struct.pack("<i", v)


def enc_u32(v: int) -> bytes:
    return struct.pack("<I", v)


def enc_u8(v: int) -> bytes:
    return struct.pack("<B", v)


def enc_u16(v: int) -> bytes:
    return struct.pack("<H", v)


# ---------------------------------------------------------------------------
# Per-element structured encoders (inverse of the parser's _parse_* fns)
# ---------------------------------------------------------------------------

def enc_node(n: P.BspNode) -> bytes:
    out = bytearray()
    out += enc_f32x4(n.plane)
    out += enc_u64(n.zone_mask)
    out += enc_u8(n.node_flags)
    out += enc_ci(n.i_vert_pool)
    out += enc_ci(n.i_surf)
    out += enc_ci(n.i_front)
    out += enc_ci(n.i_back)
    out += enc_ci(n.i_plane)
    out += enc_ci(n.i_leaf[0])
    out += enc_ci(n.i_leaf[1])
    out += enc_ci(n.i_zone[0])
    out += enc_ci(n.i_zone[1])
    out += enc_ci(n.num_vertices)
    out += enc_i32(n.i_collision_bound)
    out += enc_i32(n.i_render_bound)
    return bytes(out)


def enc_surf(s: P.BspSurf) -> bytes:
    out = bytearray()
    out += enc_ci(s.texture_ref)
    out += enc_u32(s.poly_flags)
    out += enc_ci(s.p_base)
    out += enc_ci(s.v_normal)
    out += enc_ci(s.v_texture_u)
    out += enc_ci(s.v_texture_v)
    out += enc_ci(s.i_actor)
    out += enc_ci(s.i_brush_poly)
    out += enc_u16(s.i_zone[0])
    out += enc_u16(s.i_zone[1])
    out += enc_ci(s.i_field_0x24)
    return bytes(out)


def enc_vert(v: P.BspVert) -> bytes:
    return enc_ci(v.i_vertex) + enc_ci(v.i_side)


def enc_leaf(lf: P.BspLeaf) -> bytes:
    out = bytearray()
    out += enc_ci(lf.i_zone)
    out += enc_ci(lf.i_permeating)
    out += enc_ci(lf.i_volumetric)
    out += enc_u64(lf.i_exclusive)
    return bytes(out)


def enc_fvector_array(vecs: list) -> bytes:
    out = bytearray()
    out += enc_ci(len(vecs))
    for v in vecs:
        out += enc_f32x3(v)
    return bytes(out)


def enc_elem_array(elems: list, enc_elem) -> bytes:
    out = bytearray()
    out += enc_ci(len(elems))
    for e in elems:
        out += enc_elem(e)
    return bytes(out)


# ---------------------------------------------------------------------------
# Recording walk — emits an ordered list of segment bytes
#
# Structured segments are produced by re-encoding parsed structure; raw segments
# are captured as the original (start, end) span within the body and spliced
# back verbatim.
# ---------------------------------------------------------------------------

# Two observed UPrimitive-prefix lengths (raw passthrough either way):
#   42 = ci(None) + FBox(25) + FSphere(16)              — the common level/brush model
#   57 = 15-byte lead block + ci(None) + FBox(25) + FSphere(16)  — a Deus Ex variant
# The lead block (byte0 != 0x02) precedes the standard prefix on 243/72419 models.
# Both are non-geometry and pass through verbatim; only the LENGTH must be detected.
_PREFIX_STD = 42
_PREFIX_VARIANT = 57


def _walk_arrays(data: bytes, size: int, prefix: int) -> int:
    """Walk Vectors..trailing-INTs from `prefix`; return end pos (or -1 on failure)."""
    pos = prefix
    try:
        _, pos = P._parse_fvector_array(data, pos)            # Vectors
        _, pos = P._parse_fvector_array(data, pos)            # Points
        _, pos = P._parse_array(data, pos, P._parse_node, "N")
        _, pos = P._parse_array(data, pos, P._parse_surf, "S")
        _, pos = P._parse_array(data, pos, P._parse_vert, "V")
        _, pos = P._i32(data, pos)                            # NumSharedSides
        num_zones, pos = P._i32(data, pos)
        if not (0 <= num_zones <= 100000):
            return -1
        pos = P._skip_zone_data(data, pos, num_zones)
        _, pos = P._ci(data, pos)                             # field_0x54
        pos = P._skip_array_0xa8(data, pos)
        pos = P._skip_array_0xb4(data, pos)
        pos = P._skip_array_0xc0(data, pos)
        pos = P._skip_array_0xcc(data, pos)
        _, pos = P._parse_array(data, pos, P._parse_leaf, "L")
        pos = P._skip_array_0xe4(data, pos)
        _, pos = P._i32(data, pos)
        _, pos = P._i32(data, pos)
        return pos
    except Exception:  # noqa: BLE001
        return -1


def detect_prefix(data: bytes, size: int) -> int:
    """Return the UPrimitive prefix length (42 or 57) that walks the body to EOF.

    Disambiguates cleanly on the whole corpus: every model walks to EOF with
    exactly one of the two, never both, never neither.
    """
    # byte0 == 0x02 is the standard ci(None) start; anything else carries the lead block.
    primary, secondary = (
        (_PREFIX_STD, _PREFIX_VARIANT) if data[0] == 0x02
        else (_PREFIX_VARIANT, _PREFIX_STD)
    )
    if _walk_arrays(data, size, primary) == size:
        return primary
    if _walk_arrays(data, size, secondary) == size:
        return secondary
    raise ValueError(
        f"UModel prefix not resolvable (size={size}, byte0={data[0]:#04x})"
    )


def serialize_model(buf: bytes, offset: int, size: int) -> bytes:
    """Re-serialize the UModel body at (offset, size); returns the body bytes.

    Geometry arrays are re-emitted from parsed structure; the prefix, the
    0xa8/0xb4/0xc0/0xcc/0xe4 aux arrays, and the two trailing INTs are spliced
    back as raw spans.
    """
    data = buf[offset:offset + size]
    out = bytearray()

    pos = 0

    # UPrimitive prefix (42 or 57 bytes) — raw passthrough.
    prefix = detect_prefix(data, size)
    out += data[pos:pos + prefix]
    pos += prefix

    # Vectors, Points — structured.
    vectors, pos = P._parse_fvector_array(data, pos)
    out += enc_fvector_array(vectors)

    points, pos = P._parse_fvector_array(data, pos)
    out += enc_fvector_array(points)

    # Nodes, Surfs, Verts — structured.
    nodes, pos = P._parse_array(data, pos, P._parse_node, "Nodes")
    out += enc_elem_array(nodes, enc_node)

    surfs, pos = P._parse_array(data, pos, P._parse_surf, "Surfs")
    out += enc_elem_array(surfs, enc_surf)

    verts, pos = P._parse_array(data, pos, P._parse_vert, "Verts")
    out += enc_elem_array(verts, enc_vert)

    # NumSharedSides, NumZones — structured (raw i32 each, identical bytes).
    num_shared_sides, pos = P._i32(data, pos)
    out += enc_i32(num_shared_sides)

    num_zones, pos = P._i32(data, pos)
    out += enc_i32(num_zones)

    # FZoneProperties[NumZones] — structured (ci + 16 raw bytes each). The 16
    # raw Connectivity/Visibility bytes are spliced from the original span; the
    # ci ZoneActor ref is re-encoded.
    for _ in range(num_zones):
        zone_ref, after_ci = P._ci(data, pos)
        out += enc_ci(zone_ref)
        out += data[after_ci:after_ci + 16]
        pos = after_ci + 16

    # field_0x54 — structured ci.
    field_0x54, pos = P._ci(data, pos)
    out += enc_ci(field_0x54)

    # The four aux TArrays before Leaves — RAW passthrough (parser only skips).
    aux_start = pos
    pos = P._skip_array_0xa8(data, pos)
    pos = P._skip_array_0xb4(data, pos)
    pos = P._skip_array_0xc0(data, pos)
    pos = P._skip_array_0xcc(data, pos)
    out += data[aux_start:pos]

    # FBspLeaf Leaves — structured.
    leaves, pos = P._parse_array(data, pos, P._parse_leaf, "Leaves")
    out += enc_elem_array(leaves, enc_leaf)

    # 0xe4 array + the two trailing INTs — RAW passthrough to EOF.
    out += data[pos:size]

    return bytes(out)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _first_diff(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    if len(a) != len(b):
        return n
    return -1


def validate_model(buf: bytes, offset: int, size: int) -> tuple[bool, int]:
    """Re-serialize and compare. Returns (is_exact, first_diff_offset_or_-1)."""
    original = buf[offset:offset + size]
    reser = serialize_model(buf, offset, size)
    if reser == original:
        return True, -1
    return False, _first_diff(original, reser)


def validate_map(dx_path: str, *, all_models: bool = True) -> list[tuple]:
    """Validate every Model export (or just the largest) in a map.

    Returns a list of (name, size, is_exact, first_diff) tuples.
    """
    buf = open(dx_path, "rb").read()
    try:
        exports = P.find_model_exports(dx_path)
    except Exception as e:  # noqa: BLE001 — a package-header parse failure (e.g. Entry.dx)
        return [("<header>", 0, False, -3, repr(e))]
    targets = exports if all_models else exports[:1]
    results = []
    for exp_idx, name, size, off in targets:
        try:
            ok, diff = validate_model(buf, off, size)
        except Exception as e:  # noqa: BLE001 — spike: report, don't crash the sweep
            results.append((name, size, False, -2, repr(e)))
            continue
        results.append((name, size, ok, diff, None))
    return results


# ---------------------------------------------------------------------------
# Unit tests for the primitive encoders (ci is the load-bearing one)
# ---------------------------------------------------------------------------

def _test_primitives() -> None:
    import random

    # ci round-trip on boundary + random values, including signed/negative-zero.
    vals = [0, 1, -1, 63, 64, -63, -64, 65, 8191, 8192, -8192,
            0x7FFFFFFF, -0x7FFFFFFF, 0x40, 0x3F, 1 << 20, -(1 << 20)]
    for _ in range(20000):
        vals.append(random.randint(-(2**31 - 1), 2**31 - 1))
    for v in vals:
        enc = enc_ci(v)
        dec, pos = P._ci(enc, 0)
        assert dec == v and pos == len(enc), f"ci roundtrip fail {v}: {enc.hex()} -> {dec}"

    # Negative zero: enc_ci(0) is non-negative-zero canonical; there is no -0 int.
    assert enc_ci(0) == b"\x00", enc_ci(0).hex()
    # A value of 0 must never set the sign bit.
    assert not (enc_ci(0)[0] & 0x80)

    # Fixed-width primitives.
    for v in [0, 1, 2**63, 2**64 - 1]:
        assert P._u64(enc_u64(v), 0)[0] == v
    for v in [0, -1, 1, 2**31 - 1, -(2**31)]:
        assert P._i32(enc_i32(v), 0)[0] == v
    for v in [0, 1, 2**32 - 1]:
        assert P._u32(enc_u32(v), 0)[0] == v
    for v in [0, 1, 255]:
        assert P._u8(enc_u8(v), 0)[0] == v
    for v in [0, 1, 65535]:
        assert P._u16(enc_u16(v), 0)[0] == v
    for t in [(1.0, 2.0, 3.0), (-0.5, 0.0, 1e9)]:
        assert P._f32x3(enc_f32x3(t), 0)[0] == t
    for t in [(1.0, 2.0, 3.0, 4.0)]:
        assert P._f32x4(enc_f32x4(t), 0)[0] == t

    print("primitive encoder unit tests: PASS")


# ---------------------------------------------------------------------------
# Corpus runner
# ---------------------------------------------------------------------------

_MAPS_DIR = Path(
    "/home/human/src/dx_lum/Tools/uedctl/uned/DeusExAssets/Maps"
)

# A spread of small→large maps; every Model export in each is validated.
_SAMPLE = [
    "00_Intro.dx", "00_Training.dx",
    "01_NYC_UNATCOIsland.dx", "01_NYC_UNATCOHQ.dx",
    "02_NYC_Bar.dx", "02_NYC_BatteryPark.dx", "03_NYC_747.dx",
    "04_NYC_UNATCOHQ.dx", "06_HongKong_WanChai_Street.dx",
    "10_Paris_Catacombs.dx", "15_Area51_Bunker.dx",
    "12_Vandenberg_Cmd.dx",
]


def _run_corpus() -> int:
    _test_primitives()

    print("\n=== Sample maps (every Model export) ===")
    total = exact = 0
    for fn in _SAMPLE:
        path = _MAPS_DIR / fn
        if not path.exists():
            print(f"  MISSING {fn}")
            continue
        for name, size, ok, diff, err in validate_map(str(path), all_models=True):
            total += 1
            tag = "EXACT" if ok else (
                f"MISMATCH@{diff}" if err is None else f"ERROR {err}"
            )
            if ok:
                exact += 1
            else:
                print(f"  {fn:32s} {name:12s} size={size:>9,}  {tag}")
        print(f"  {fn:32s} done")
    print(f"\n  sample: {exact}/{total} Model exports byte-exact")

    print("\n=== All maps: EVERY Model export in every map ===")
    all_paths = sorted(_MAPS_DIR.glob("*.dx"))
    atotal = aexact = 0
    levels_total = levels_exact = 0
    mismatches = []
    header_fail = []
    for path in all_paths:
        try:
            exports = P.find_model_exports(str(path))
        except Exception as e:  # noqa: BLE001
            header_fail.append((path.name, repr(e)))
            continue
        buf = open(path, "rb").read()
        for i, (exp_idx, name, size, off) in enumerate(exports):
            atotal += 1
            is_level = (i == 0)  # exports are sorted size-desc; [0] is the level model
            if is_level:
                levels_total += 1
            try:
                ok, diff = validate_model(buf, off, size)
            except Exception as e:  # noqa: BLE001
                mismatches.append((path.name, name, size, f"ERROR {e!r}"))
                continue
            if ok:
                aexact += 1
                if is_level:
                    levels_exact += 1
            else:
                mismatches.append((path.name, name, size, f"MISMATCH@{diff}"))
    for m in mismatches:
        print(f"  {m[0]:36s} {m[1]:12s} size={m[2]:>10,}  {m[3]}")
    if header_fail:
        print("\n  package-header parse failures (NOT a Model-serialize issue):")
        for fn, e in header_fail:
            print(f"    {fn}: {e}")
    print(f"\n  ALL Model exports: {aexact}/{atotal} byte-exact")
    print(f"  LEVEL (largest) Models: {levels_exact}/{levels_total} byte-exact")

    print(f"\n{aexact}/{atotal} models byte-exact")
    return 0 if (aexact == atotal) else 1


def main(argv) -> int:
    if len(argv) >= 2:
        _test_primitives()
        for arg in argv[1:]:
            print(f"\n=== {arg} ===")
            for name, size, ok, diff, err in validate_map(arg, all_models=True):
                tag = "EXACT" if ok else (
                    f"MISMATCH@{diff}" if err is None else f"ERROR {err}"
                )
                print(f"  {name:12s} size={size:>10,}  {tag}")
        return 0
    return _run_corpus()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
