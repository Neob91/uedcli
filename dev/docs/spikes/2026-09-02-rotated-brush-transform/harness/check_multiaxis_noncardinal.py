"""Does `rotation.py`'s double-precision `matmul(Rz, matmul(Ry, Rx))` compose-then-cast-to-f32
diverge from a GENUINE per-step float32 compose, for a real DX brush whose FRotator has TWO
non-cardinal axes simultaneously non-identity?

`uedcli/rotation.py`'s own module header claims this case ("a genuine NON-cardinal multi-axis
FRotator") is UNVERIFIED / ULP-approximate in general, but asserts "DX content has NONE" of it.
`scan_noncardinal.py` (this dir) found that claim is FALSE: OceanLab Lab's `Brush1849`
(`Rotation=(Yaw=-8192,Roll=-15360)`) and `Brush1081`/`Brush2409`, plus NYC Underground04's
`Brush134`, are real world-CSG brushes with two simultaneously non-cardinal FRotator axes.
OceanLab Lab has an OPEN node/leaf-count residual (+465 nodes/+86 leaves per the 2026-09-02
breadth table), so this is a concrete, previously-unexamined candidate for the "upstream
vertex/normal float divergence" hypothesis this spike investigates -- not proof, but the first
lead that isn't ruled out by the module's own bit-exactness argument.

This script does NOT need a live editor or disassembly: it computes the SAME rotation matrix two
ways and diffs the bits.
  (a) `rotation.euler_to_matrix_uu` -- Python double compose, final result cast to f32 (what
      native's `brush_marshal.py` actually feeds the Rust core today).
  (b) A per-step float32 compose: round sin/cos (already f32, from the GMath table) is a no-op;
      the risk is in the 3x3xf32 MATRIX MULTIPLY itself -- `Rz @ Ry`, then `@ Rx`, each product
      rounded to f32 after every multiply-accumulate, mirroring what an f32 FCoords compose in
      the real engine would do if it forms the product with intermediate f32 rounding (still not
      proof the real editor does exactly this -- that needs the ABrush::BuildCoords disassembly
      this spike also attempts -- but establishes whether the CURRENT double-then-cast approach
      is even SELF-consistent with the most natural f32-native alternative).
"""
import struct
import sys

sys.path.insert(0, "/workspace/uedcli/.claude/worktrees/agent-a4ff899b7854f717f")
from uedcli import rotation as ROT  # noqa: E402


def f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def matmul_f32(A, B):
    """3x3 matrix product with EVERY multiply-accumulate rounded to f32 (mirrors a native f32
    FCoords compose, if the real editor forms the product step-by-step rather than in a wider
    intermediate)."""
    return [[f32(sum(f32(A[i][k] * B[k][j]) for k in range(3))) for j in range(3)] for i in range(3)]


def matmul_f32_fma_style(A, B):
    """Alternate rounding model: accumulate the row in f32 one term at a time (mul, round, add,
    round) rather than summing three f32 products then rounding once -- the two accumulation
    orders can differ by 1 ULP on some inputs."""
    out = [[0.0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            acc = 0.0
            for k in range(3):
                acc = f32(acc + f32(A[i][k] * B[k][j]))
            out[i][j] = acc
    return out


def report(name, uu):
    pitch_uu, yaw_uu, roll_uu = uu
    rz = ROT._rz_uu(yaw_uu)
    ry = ROT._ry_uu(pitch_uu)
    rx = ROT._rx_uu(roll_uu)

    # (a) current production path: double matmul, values already f64 (Python), cast per-entry to f32
    # only implicitly when crossing into Rust (brush_marshal.py: `[float(x) for x in row]` -- still
    # f64 in Python, PyO3 narrows to f32 at the FFI boundary). Simulate that narrowing here.
    double_compose = ROT.matmul(rz, ROT.matmul(ry, rx))
    double_then_f32 = [[f32(v) for v in row] for row in double_compose]

    # (b) genuine per-step f32 compose, two accumulation orders
    ry_rx_f32 = matmul_f32(ry, rx)
    f32_compose_a = matmul_f32(rz, ry_rx_f32)

    ry_rx_f32b = matmul_f32_fma_style(ry, rx)
    f32_compose_b = matmul_f32_fma_style(rz, ry_rx_f32b)

    print(f"--- {name}  uu=(pitch={pitch_uu},yaw={yaw_uu},roll={roll_uu}) ---")
    max_ulp_diff = 0
    for i in range(3):
        for j in range(3):
            a = double_then_f32[i][j]
            b = f32_compose_a[i][j]
            c = f32_compose_b[i][j]
            bits_a = struct.unpack("I", struct.pack("f", a))[0]
            bits_b = struct.unpack("I", struct.pack("f", b))[0]
            bits_c = struct.unpack("I", struct.pack("f", c))[0]
            if bits_a != bits_b or bits_a != bits_c:
                print(
                    f"  [{i}][{j}] double->f32={a!r} (0x{bits_a:08x})  "
                    f"f32-step-sum={b!r} (0x{bits_b:08x})  "
                    f"f32-step-acc={c!r} (0x{bits_c:08x})"
                )
                max_ulp_diff = max(max_ulp_diff, abs(bits_a - bits_b), abs(bits_a - bits_c))
    if max_ulp_diff == 0:
        print("  IDENTICAL across all three compose strategies (0 ULP)")
    else:
        print(f"  MAX bit-pattern delta observed: {max_ulp_diff}")


def main():
    cases = {
        "OceanLab Brush1849 (Yaw=-8192,Roll=-15360)": (0, -8192 % 65536, -15360 % 65536),
        "OceanLab Brush1081 (Pitch=-2968,Yaw=-3072)": (-2968 % 65536, -3072 % 65536, 0),
        "OceanLab Brush2409 (Yaw=9216,Roll=15360)": (0, 9216, 15360),
        "NYCu04 Brush134 (Pitch=-8192,Yaw=39936)": (-8192 % 65536, 39936, 0),
        "control: Area51 Brush1852 (Yaw=-49152, cardinal)": (0, -49152 % 65536, 0),
        "control: cardinal 2-axis (Pitch=16384,Yaw=32768)": (16384, 32768, 0),
    }
    for name, uu in cases.items():
        report(name, uu)


if __name__ == "__main__":
    main()
