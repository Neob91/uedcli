#!/usr/bin/env python3
"""The unbuilt byte-parity GATE: full-file compare of a (table-oracle-seeded) native package
against the editor MAP IMPORT golden, modulo the owner-ruled exclusion masks:

  * the header GUID (16 bytes),
  * every actor StateFrame's LatentAction u32 (editor stack garbage; proven nondeterministic),
  * LevelInfo's TimeSeconds/AIProfile tag VALUES (session clock/counters),
  * the ULevel body's TimeSeconds float,
  * the six viewport Camera bodies (editor viewport state; proven nondeterministic).

Exit 0 + "BYTE PARITY: YES" iff nothing outside the masks differs. Prints every unmasked
difference region otherwise (bounded).

Usage: byte_gate.py <native.dx> <golden.dx>
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from uedcli.upackage import load_package, read_compact_index, read_property_tags  # noqa: E402


def mask_ranges(p) -> list[tuple[int, int, str]]:
    """Excluded byte ranges for one parsed package."""
    out = [(36, 52, "guid")]
    li_export = 0                                     # export 0 is always the LevelInfo
    for i, e in enumerate(p.exports):
        cls = p.object_class_name(i + 1) or ""
        if cls == "Camera":
            out.append((e["soff"], e["soff"] + e["ssize"], f"camera:{p.names[e['nm']]}"))
            continue
        if e["flags"] & 0x02000000:                    # StateFrame LatentAction
            pos = e["soff"]
            node, pos = read_compact_index(p.buf, pos)
            _, pos = read_compact_index(p.buf, pos)
            pos += 8
            out.append((pos, pos + 4, "latent"))
        if cls == "Level":
            # TimeSeconds float sits at a fixed distance from the body END: f32 + ci(0)
            # FirstDeleted + 16 ci(0) slots + ci(0) TravelInfo = 22 bytes of tail (all single-byte
            # zero cis in an unbuilt save; `level_write.write_level_body`).
            end = e["soff"] + e["ssize"]
            out.append((end - 22, end - 18, "level-timeseconds"))
    return out


def li_value_masks(p) -> list[tuple[int, int, str]]:
    """LevelInfo TimeSeconds/AIProfile VALUE spans, by re-walking the tag stream manually."""
    e = p.exports[0]
    pos = e["soff"]
    node, pos = read_compact_index(p.buf, pos)
    _, pos = read_compact_index(p.buf, pos)
    pos += 12
    if node != 0:
        _, pos = read_compact_index(p.buf, pos)
    out = []
    buf, end = p.buf, e["soff"] + e["ssize"]
    while pos < end:
        nidx, pos = read_compact_index(buf, pos)
        name = p.names[nidx]
        if name == "None":
            break
        info = buf[pos]; pos += 1
        ptype, size_code, bit7 = info & 0x0F, (info >> 4) & 0x07, bool(info & 0x80)
        if ptype == 10:
            _, pos = read_compact_index(buf, pos)
        size = {0: 1, 1: 2, 2: 4, 3: 12, 4: 16}.get(size_code)
        if size is None:
            if size_code == 5:
                size = buf[pos]; pos += 1
            elif size_code == 6:
                size = struct.unpack_from("<H", buf, pos)[0]; pos += 2
            else:
                size = struct.unpack_from("<I", buf, pos)[0]; pos += 4
        if ptype == 3:
            size = 0
        elif bit7:
            _, pos = read_compact_index(buf, pos)      # array index
        if name in ("TimeSeconds", "AIProfile"):
            out.append((pos, pos + size, f"li-{name}"))
        pos += size
    return out


def main() -> int:
    a_path, b_path = sys.argv[1], sys.argv[2]
    A, B = load_package(a_path), load_package(b_path)
    if len(A.buf) != len(B.buf):
        print(f"SIZE differs: {len(A.buf)} vs {len(B.buf)} -- structural gap, not maskable")
    masks_a = mask_ranges(A) + li_value_masks(A)
    masks_b = mask_ranges(B) + li_value_masks(B)

    def masked(pos, masks):
        return any(lo <= pos < hi for lo, hi, _ in masks)

    n = min(len(A.buf), len(B.buf))
    diffs = []
    i = 0
    while i < n:
        if A.buf[i] != B.buf[i] and not (masked(i, masks_a) or masked(i, masks_b)):
            j = i
            while j < n and (A.buf[j] != B.buf[j] or j - i < 4) and j - i < 64:
                j += 1
            diffs.append((i, j))
            i = j
        else:
            i += 1
        if len(diffs) > 40:
            break
    if not diffs and len(A.buf) == len(B.buf):
        print("BYTE PARITY: YES (modulo guid/latent/timeseconds/aiprofile/camera-body masks)")
        return 0
    print(f"BYTE PARITY: NO — {len(diffs)}{'+' if len(diffs) > 40 else ''} unmasked diff regions")
    for lo, hi in diffs[:15]:
        print(f"  @{lo:#x}..{hi:#x}: A={A.buf[lo:min(hi, lo+12)].hex()} "
              f"B={B.buf[lo:min(hi, lo+12)].hex()}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
