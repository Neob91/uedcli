#!/usr/bin/env python3
"""GROUND-TRUTH raw-byte diff of the level `UModel` serial body: native vs UnrealEd.

This is the CORRECTIVE harness.  A long chain of prior diff tools compared
NORMALIZED / subset / fp-tolerant projections of the Model (plane-rounded multiset
keys, order-independent set compares, tolerance on floats) and reported many sections
"byte-exact".  Those claims are about the ORACLE projection, not the on-disk bytes.
This tool compares the **raw serialized body bytes** — nothing normalized, nothing
tolerated — so the numbers it prints are the true on-disk parity state.

What it does:
  1. Parse `NativeCastle.dx` (rebuild fresh with build_native_castle.py first) and
     `Test_Castle.dx`; pick each file's LARGEST `Model` export (the level BSP).
  2. Re-walk each Model body recording the exact byte [start,end) of every serialized
     SECTION (prefix, Vectors, Points, Nodes, Surfs, Verts, NumSharedSides, NumZones,
     Zones, field_0x54, LightMap a8, LightBits b4, Bounds c0, LeafHulls cc, Leaves,
     Lights e4, trailing).
  3. Whole-body diff: total bytes each side, first differing byte offset.
  4. Per-section byte-equality map: for each section, native vs editor byte length,
     whether the raw bytes are byte-identical, and the first differing byte within the
     section (offset relative to the section start).

The GUID + save timestamps live in the package WRAPPER (header), NOT in the Model body,
so the body diff already excludes them by construction — there is nothing to strip here.
(Wrapper-level parity is a separate harness, wrapper_diff.py.)

CAVEAT the report states plainly: several body sections embed OBJECT-REFS (Surf
texture/iActor, Zone actor, Lights) that are compressed-int INDICES into each file's own
export/import tables.  Those tables are numbered differently native-vs-editor (a
session-global counter the trunk cannot reproduce — see wrapper_diff.py), so a raw byte
diff of a ref-bearing section can differ *purely* from renumbering even when the geometry
is identical.  This tool reports the raw truth; the accompanying doc (sections/82 §11)
triages which differences are renumbering vs real.

Usage:
  .venv/bin/python .../harness/ground_truth_bytediff.py [NATIVE.dx] [EDITOR.dx]
Defaults: _scratch/gtruth/NativeCastle.dx  vs  DX/Maps/Test_Castle.dx
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))

from uedctl.native.codec import read_ci  # noqa: E402
import utexture_decode as UT  # noqa: E402

NATIVE = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/gtruth/NativeCastle.dx"
EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"

_PREFIX = 42


# --- byte-length-only walkers per element (mirror umodel.py exactly) --------

def _len_fvector_array(buf, pos):
    count, p = read_ci(buf, pos)
    return count, p + count * 12


def _node_end(buf, pos):
    p = pos + 16 + 8 + 1
    for _ in range(10):            # iVertPool iSurf iFront iBack iPlane iColl iRend z0 z1 nv
        _, p = read_ci(buf, p)
    p += 8                          # iLeaf[0], iLeaf[1]  (fixed i32 x2)
    return p


def _surf_end(buf, pos):
    p = pos
    _, p = read_ci(buf, p)          # texture_ref
    p += 4                          # poly_flags u32
    for _ in range(6):              # p_base v_normal v_u v_v i_light_map i_brush_poly
        _, p = read_ci(buf, p)
    p += 4                          # iZone u16 x2
    _, p = read_ci(buf, p)          # i_actor
    return p


def _vert_end(buf, pos):
    p = pos
    _, p = read_ci(buf, p)
    _, p = read_ci(buf, p)
    return p


def _leaf_end(buf, pos):
    p = pos
    _, p = read_ci(buf, p)          # i_zone
    _, p = read_ci(buf, p)          # i_permeating
    _, p = read_ci(buf, p)          # i_volumetric
    p += 8                          # i_exclusive u64
    return p


def _array_end(buf, pos, elem_end):
    count, p = read_ci(buf, pos)
    for _ in range(count):
        p = elem_end(buf, p)
    return count, p


def walk_sections(body: bytes):
    """Return (sections, total) where sections is a list of dicts:
    {name, start, end, count} covering the whole body with no gaps."""
    secs = []
    p = 0

    def mark(name, start, end, count=None):
        secs.append(dict(name=name, start=start, end=end, count=count))

    # prefix
    mark("prefix", 0, _PREFIX)
    p = _PREFIX
    # Vectors
    s = p; c, p = _len_fvector_array(body, p); mark("Vectors", s, p, c)
    # Points
    s = p; c, p = _len_fvector_array(body, p); mark("Points", s, p, c)
    # Nodes
    s = p; c, p = _array_end(body, p, _node_end); mark("Nodes", s, p, c)
    # Surfs
    s = p; c, p = _array_end(body, p, _surf_end); mark("Surfs", s, p, c)
    # Verts
    s = p; c, p = _array_end(body, p, _vert_end); mark("Verts", s, p, c)
    # NumSharedSides
    s = p; p += 4; mark("NumSharedSides", s, p)
    # NumZones
    s = p; nz = struct.unpack_from("<i", body, p)[0]; p += 4; mark("NumZones", s, p, nz)
    # Zones
    s = p
    for _ in range(nz):
        _, p = read_ci(body, p)     # actor_ref
        p += 16                     # connectivity u64 + visibility u64
    mark("Zones", s, p, nz)
    # field_0x54
    s = p; _, p = read_ci(body, p); mark("field_0x54(Polys)", s, p)
    # LightMap a8 (FLightMapIndex 32B serial each)
    s = p; c, p = read_ci(body, p)
    for _ in range(c):
        p += 4 + 12                 # data_offset i32 + pan f32x3
        _, p = read_ci(body, p)     # u_size
        _, p = read_ci(body, p)     # v_size
        p += 4 + 4 + 4              # u_scale, v_scale, i_light_actors
    mark("LightMap(a8)", s, p, c)
    # LightBits b4 (BYTE array)
    s = p; c, p = read_ci(body, p); p += c; mark("LightBits(b4)", s, p, c)
    # Bounds c0 (FBox 25B serial each)
    s = p; c, p = read_ci(body, p); p += c * 25; mark("Bounds(c0)", s, p, c)
    # LeafHulls cc (INT array)
    s = p; c, p = read_ci(body, p); p += c * 4; mark("LeafHulls(cc)", s, p, c)
    # Leaves
    s = p; c, p = _array_end(body, p, _leaf_end); mark("Leaves", s, p, c)
    # Lights e4 (obj-ref array, ci each)
    s = p; c, p = read_ci(body, p)
    for _ in range(c):
        _, p = read_ci(body, p)
    mark("Lights(e4)", s, p, c)
    # trailing i32 x2 (RootOutside, Linked)
    s = p; p += 8; mark("trailing(RootOutside,Linked)", s, p)
    return secs, p


# --- diff -------------------------------------------------------------------

def first_diff(a: bytes, b: bytes):
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    if len(a) != len(b):
        return n
    return None


def load_model_body(path: str):
    pkg = UT.load_package(path)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return bytes(pkg.buf[e["soff"]:e["soff"] + e["ssize"]]), pkg, mi


def main():
    nat_p = sys.argv[1] if len(sys.argv) > 1 else NATIVE
    ed_p = sys.argv[2] if len(sys.argv) > 2 else EDITOR
    print(f"NATIVE: {nat_p}")
    print(f"EDITOR: {ed_p}\n")

    nb, _, nmi = load_model_body(nat_p)
    eb, _, emi = load_model_body(ed_p)

    nsec, ntot = walk_sections(nb)
    esec, etot = walk_sections(eb)
    assert ntot == len(nb), (ntot, len(nb))
    assert etot == len(eb), (etot, len(eb))

    print("=" * 92)
    print("WHOLE-BODY RAW BYTE DIFF (Model serial body; GUID/timestamps are in the header, not here)")
    print("=" * 92)
    print(f"  native body bytes: {len(nb)}   (Model export #{nmi})")
    print(f"  editor body bytes: {len(eb)}   (Model export #{emi})")
    print(f"  delta            : {len(nb) - len(eb):+d}")
    fd = first_diff(nb, eb)
    print(f"  first differing byte offset (whole body): {fd}"
          + (f"  native=0x{nb[fd]:02x} editor=0x{eb[fd]:02x}" if fd is not None and fd < min(len(nb), len(eb)) else ""))
    # count matching bytes positionally over the common prefix (informational only)
    common = min(len(nb), len(eb))
    match_pos = sum(1 for i in range(common) if nb[i] == eb[i])
    print(f"  positional byte match over common prefix ({common} B): {match_pos} "
          f"({100.0*match_pos/common:.2f}%)   [NOTE: positional; shifts after 1st length-diff section]")

    print()
    print("=" * 92)
    print("PER-SECTION BYTE-EQUALITY MAP  (each section's own raw bytes, native slice vs editor slice)")
    print("=" * 92)
    print(f"  {'section':<28} {'nat len':>9} {'ed len':>9} {'nat #':>7} {'ed #':>7}  equal  first-diff(in-sec)")
    print(f"  {'-'*28} {'-'*9} {'-'*9} {'-'*7} {'-'*7}  -----  ------------------")
    ne = {s["name"]: s for s in nsec}
    ee = {s["name"]: s for s in esec}
    order = [s["name"] for s in nsec]
    eq_bytes = 0
    total_ed_bytes = 0
    for name in order:
        ns = ne[name]; es = ee[name]
        na = nb[ns["start"]:ns["end"]]
        ea = eb[es["start"]:es["end"]]
        d = first_diff(na, ea)
        equal = d is None
        nc = "" if ns["count"] is None else str(ns["count"])
        ec = "" if es["count"] is None else str(es["count"])
        mark = "YES " if equal else "no  "
        dd = "" if equal else f"@{d}" + (f" n=0x{na[d]:02x} e=0x{ea[d]:02x}" if d < min(len(na), len(ea)) else " (len)")
        print(f"  {name:<28} {len(na):>9} {len(ea):>9} {nc:>7} {ec:>7}  {mark}  {dd}")
        total_ed_bytes += len(ea)
        if equal:
            eq_bytes += len(ea)
    print(f"  {'-'*28}")
    print(f"  editor body total {total_ed_bytes} B; byte-identical sections sum {eq_bytes} B "
          f"({100.0*eq_bytes/total_ed_bytes:.2f}% of editor body in fully-identical sections)")


if __name__ == "__main__":
    main()
