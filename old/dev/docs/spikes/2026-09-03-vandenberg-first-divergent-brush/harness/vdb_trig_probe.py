#!/usr/bin/env python3
"""Test candidate GMath-table construction formulas against the editor SinTab bits solved from
Brush151's live node planes (idx 16128 -> 0xbdc8bd22, idx 3840 -> 0x3f7ec493)."""
import math
import struct


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def fb(u):
    return struct.unpack("<f", struct.pack("<I", u))[0]


def bits(x):
    return hex(struct.unpack("<I", struct.pack("<f", x))[0])


pi32 = fb(0x40490FDB)
twopi32 = f32(2.0 * pi32)
TGT = {16128: 0xBDC8BD22, 3840: 0x3F7EC493, 8192: struct.unpack("<I", struct.pack("<f", f32(math.sin(f32(8192 * 2.0 * math.pi / 16384)))))[0]}

VARIANTS = {
    "sin(f32(k*2pi_d/N)) [current]": lambda k: math.sin(f32(k * 2.0 * math.pi / 16384)),
    "sin(k*2*pi32/N) double": lambda k: math.sin(k * 2.0 * pi32 / 16384),
    "sin(f32(k*2*pi32/N))": lambda k: math.sin(f32(k * 2.0 * pi32 / 16384)),
    "sin(f32(f32(k*twopi32)/N))": lambda k: math.sin(f32(f32(k * twopi32) / 16384.0)),
    "sin(f32(f32(f32(k)*twopi32)/N))": lambda k: math.sin(f32(f32(f32(k) * twopi32) / f32(16384.0))),
    "sin(f32(k)*twopi32/N dbl)": lambda k: math.sin(f32(k) * twopi32 / 16384.0),
    "sin(f32(f32(k/N)*twopi32))": lambda k: math.sin(f32(f32(k / 16384.0) * twopi32)),
    "sin(f32(k/N)*twopi32 dbl)": lambda k: math.sin(f32(k / 16384.0) * twopi32),
    "sin(f32(f32(k*2.0)*pi32/N))": lambda k: math.sin(f32(f32(k * 2.0) * pi32 / 16384)),
    "sin(f32(f32(f32(k*2.0)*pi32)/N))": lambda k: math.sin(f32(f32(f32(k * 2.0) * pi32) / 16384.0)),
}

for name, fn in VARIANTS.items():
    vals = {k: bits(f32(fn(k))) for k in TGT}
    ok = all(struct.unpack("<I", struct.pack("<f", f32(fn(k))))[0] == v for k, v in TGT.items()
             if k != 8192)
    print(f"{name:36s} {'MATCH' if ok else 'no   '} {vals}")
print("targets:", {k: hex(v) for k, v in TGT.items()})
