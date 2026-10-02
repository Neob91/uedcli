#!/usr/bin/env python3
"""Re-decode the bspAddPoint / FindNearestVertex / csgRebuild facts from the UED22 DLLs.

Prints the load-bearing constants and byte-patterns the spike relies on, straight from
`uned/UED22/{Editor,Engine}.dll` (ImageBase 0x10000000). Static only. Run:

    python3 decode_dedup.py            # assert every pinned fact, print a table

Reuses the shared PE helper committed at `dev/docs/spikes/bspspike/pe.py`.
"""
from __future__ import annotations
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "dev/docs/spikes/bspspike"))
import pe  # noqa: E402

ED = str(ROOT / "uned/UED22/Editor.dll")
EN = str(ROOT / "uned/UED22/Engine.dll")


def f32(dll: str, va: int) -> float:
    return struct.unpack("<f", pe.read_at_va(dll, va, 4))[0]


CHECKS = [
    # (label, actual, expected)
    ("bspAddPoint Points tol  Exact=1 (0x100dcaf8)", f32(ED, 0x100DCAF8), 0.0020000000949949026),
    ("bspAddPoint Points tol  Exact=0 (0x100dcafc)", f32(ED, 0x100DCAFC), 0.014999999664723873),
    ("bspAddVector Vectors tol Exact=1 (0x100dcaf0)", f32(ED, 0x100DCAF0), 1.9999999494757503e-05),
    ("bspAddVector Vectors tol Exact=0 (0x100dcaf4)", f32(ED, 0x100DCAF4), 0.00039999998989515007),
    # csgRebuild sets GFastRebuild (Editor+0x10c bit0) at entry, clears at exit
    ("csgRebuild  `or eax,1`            @0x4a6a5", pe.read_at_va(ED, 0x1004A6A5, 3).hex(), "83c801"),
    ("csgRebuild  `and [ebx+0x10c],~1`  @0x4aac6", pe.read_at_va(ED, 0x1004AAC6, 7).hex(), "83a30c010000fe"),
    # FindNearestVertex: gate on Model->Nodes count at +0x5c, miss-sentinel -1.0f
    ("FindNearestVertex `cmp [ecx+0x5c],0` @0x1adee3", pe.read_at_va(EN, 0x101ADEE3, 4).hex(), "83795c00"),
    ("FindNearestVertex miss `mov [ebp+0x14],-1.0f` @0x1adf0d", pe.read_at_va(EN, 0x101ADF0D, 7).hex(), "c74514000080bf"),
]


def main() -> int:
    ok = True
    for label, actual, expected in CHECKS:
        good = actual == expected
        ok = ok and good
        print(f"[{'OK ' if good else 'BAD'}] {label}: {actual!r}")
    print("\nAll pinned dedup/base-provenance disasm facts hold." if ok else "\nMISMATCH — a DLL fact drifted.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
