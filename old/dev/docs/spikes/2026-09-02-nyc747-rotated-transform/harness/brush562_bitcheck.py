#!/usr/bin/env python3
"""Bit-level check of the ONE genuine non-cardinal multi-axis rotation in NYC 747's world-CSG brush
set, `Brush562` (Pitch=32768, Yaw=32768, Roll=59392 -- Roll=59392/16384=3.625, not a multiple of 90
degrees; Pitch/Yaw ARE cardinal, so only one of the three axes is non-cardinal).

`uedcli/rotation.py`'s module header flags a THEORETICAL, previously UNMEASURED gap: composing the
three axis matrices in Python double (`matmul(Rz, matmul(Ry, Rx))`, what `euler_to_matrix_uu` does
and what `brush_marshal._build_brush_input` hands to the Rust `FPoly::transform` as `rot`) is only
PROVEN bit-identical to the real editor's float32 `FCoords` composition for single-axis or CARDINAL
multi-axis rotations. This directly simulates the editor's float32 composition (each axis matrix
rounded to f32, multiplied in f32 arithmetic at every step) and diffs it against the double-precision
`euler_to_matrix_uu` result the production code actually uses, entry by entry, at the bit level.

Companion to `nyc747_attrib.py`, which already found Brush562's own node-plane-ownership is IDENTICAL
between native and the golden (native=8, editor=8) -- i.e. this brush is NOT implicated in the
level's +68 node / -10 leaf residual regardless of what this script finds. This script exists to
settle the transform-math question on its own terms (as the task requires bit-level verification, not
just the attribution result) and to leave a permanent, reusable answer to the "is the theoretical
ULP gap real" question `rotation.py` flags but never measured.

Usage: .venv/bin/python brush562_bitcheck.py
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from uedcli import rotation as ROT  # noqa: E402


def f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def matmul_f32(A, B):
    """Simulate the editor's FCoords compose: every multiply-accumulate rounds to float32 at each
    step (an FMA-free scalar dot, matching the engine's x87/SSE scalar codegen for this era -- the
    same left-to-right, no-mul_add convention `fpoly.rs`'s module header documents for the Rust
    core's own dot products)."""
    out = [[0.0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            acc = 0.0
            for k in range(3):
                acc = f32(acc + f32(A[i][k] * B[k][j]))
            out[i][j] = acc
    return out


def axis_matrices_f32(pitch_uu, yaw_uu, roll_uu):
    """Each axis matrix built directly from the f32 GMath sin/cos table values (already f32 --
    `gmath_sin`/`gmath_cos` return `_TRIG[...]`, themselves float32-rounded) -- no extra rounding
    needed at this step, matches `rotation._rx_uu`/`_ry_uu`/`_rz_uu`'s entries exactly, just typed
    as float32 from the start."""
    def rx(uu):
        c, s = f32(ROT.gmath_cos(uu)), f32(ROT.gmath_sin(uu))
        return [[1.0, 0.0, 0.0], [0.0, c, s], [0.0, -s, c]]

    def ry(uu):
        c, s = f32(ROT.gmath_cos(uu)), f32(ROT.gmath_sin(uu))
        return [[c, 0.0, -s], [0.0, 1.0, 0.0], [s, 0.0, c]]

    def rz(uu):
        c, s = f32(ROT.gmath_cos(uu)), f32(ROT.gmath_sin(uu))
        return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]

    return rx(roll_uu), ry(pitch_uu), rz(yaw_uu)


def main():
    uu = (32768, 32768, 59392)  # Brush562: Pitch, Yaw, Roll
    pitch_uu, yaw_uu, roll_uu = uu
    print(f"Brush562 Rotation UU: Pitch={pitch_uu} Yaw={yaw_uu} Roll={roll_uu}")
    print(f"  Roll/16384 = {roll_uu / 16384:.4f} (non-cardinal iff not an integer)")

    # Production path: Python DOUBLE matmul, exactly what brush_marshal._build_brush_input feeds
    # the Rust FPoly::transform as `rot`.
    R_double = ROT.euler_to_matrix_uu(pitch_uu, yaw_uu, roll_uu)

    # Simulated editor path: float32 FCoords compose, same Rz*(Ry*Rx) association.
    Rx, Ry, Rz = axis_matrices_f32(pitch_uu, yaw_uu, roll_uu)
    R_f32 = matmul_f32(Rz, matmul_f32(Ry, Rx))

    print("\nEntry-by-entry compare (production double-precision R vs simulated f32-FCoords R):")
    max_ulp = 0
    any_diff = False
    for i in range(3):
        for j in range(3):
            d = R_double[i][j]
            fv = R_f32[i][j]
            d_as_f32 = f32(d)
            bits_d = struct.unpack("I", struct.pack("f", d_as_f32))[0]
            bits_f = struct.unpack("I", struct.pack("f", fv))[0]
            ulp = abs(bits_d - bits_f) if (bits_d < 2**31) == (bits_f < 2**31) else "sign-differs"
            mark = ""
            if bits_d != bits_f:
                any_diff = True
                mark = "  <-- DIFFERS"
                if isinstance(ulp, int):
                    max_ulp = max(max_ulp, ulp)
            print(f"  R[{i}][{j}]: double(->f32)={d_as_f32!r} (0x{bits_d:08x})  "
                  f"f32-compose={fv!r} (0x{bits_f:08x})  ulp={ulp}{mark}")

    print(f"\nany entry differs at f32 storage precision: {any_diff}")
    if any_diff:
        print(f"max ULP delta observed: {max_ulp}")
    else:
        print("Brush562's rotation matrix is BIT-IDENTICAL between the production double-precision "
              "compose and a simulated editor float32 FCoords compose -- the theoretical ULP gap "
              "`rotation.py` flags does NOT manifest for this specific brush's angles, despite Roll "
              "being genuinely non-cardinal.")


if __name__ == "__main__":
    raise SystemExit(main())
