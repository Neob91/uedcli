#!/usr/bin/env python3
"""Identify the generating formula of the live-captured SinTab (`logs/sintab-live.bin`)."""
import math
import struct
from pathlib import Path

data = (Path(__file__).resolve().parent.parent / "logs/sintab-live.bin").read_bytes()
tab = struct.unpack("<16384f", data)


def bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def fb(u):
    return struct.unpack("<f", struct.pack("<I", u))[0]


pi32 = fb(0x40490FDB)
twopi32 = f32(2.0 * pi32)

CANDS = {
    "sin(f32(k*2*pi32/N))": lambda k: f32(math.sin(f32(k * 2.0 * pi32 / 16384))),
    "sin(f32(f32(k*twopi32)/N))": lambda k: f32(math.sin(f32(f32(k * twopi32) / 16384.0))),
    "sin(k*2*pi32/N) dbl": lambda k: f32(math.sin(k * 2.0 * pi32 / 16384)),
    "sin(f32(k)*twopi32/N dbl)": lambda k: f32(math.sin(f32(k) * twopi32 / 16384.0)),
    "sin(f32(k*2pi_d/N)) [rotation.py]": lambda k: f32(math.sin(f32(k * 2.0 * math.pi / 16384))),
    "sin(k*2pi_d/N) pure dbl": lambda k: f32(math.sin(k * 2.0 * math.pi / 16384)),
}

for name, fn in CANDS.items():
    bad = [k for k in range(16384) if bits(fn(k)) != bits(tab[k])]
    print(f"{name:36s} mismatches: {len(bad)}"
          + (f"  first: {bad[:5]}" if bad else ""))
