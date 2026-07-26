import math
import struct
from decimal import Decimal
from types import SimpleNamespace

from uedcli.rotation import (euler_to_matrix, euler_to_matrix_uu, deg_to_uu, uu_to_deg,
                             compose_uu, rotate_point, matvec, gmath_sin, gmath_cos, actor_matrix,
                             is_identity_uu, actor_prepivot, local_offset, world_vertices)
from uedcli.builders import cube, make_brush_actor


def _det(M):
    return (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1])
            - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
            + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))


def _f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


def test_gmath_trig_uses_truncated_16384_table_not_float():
    # The editor indexes a 16384-entry sine table by (field >> 2) & 16383 with TRUNCATION (spike
    # 2026-06-19-group-rotate-exact-parity). So fields 4092..4095 share index 1023, and 4096 jumps
    # to index 1024 — a property plain float sin(field/65536·2π) does NOT have.
    assert gmath_sin(4092) == gmath_sin(4095)                 # same truncated index 1023
    assert gmath_sin(4096) != gmath_sin(4095)                 # index 1024 ≠ 1023
    # Editor-exact table entry: appSin CASTS THE ANGLE TO FLOAT32 first (§92 §41), so the stored
    # value is f32(sin(f32(idx·2π/16384))), NOT f32(sin(idx·2π/16384)).
    assert gmath_sin(4095) == _f32(math.sin(_f32(1023 * 2 * math.pi / 16384)))   # truncate, not round
    assert gmath_sin(4095) != _f32(math.sin(1024 * 2 * math.pi / 16384))
    # cos is `sin` of a QUARTER-SHIFTED table index (CosTab(i)=TrigFLOAT[((i>>2)+N/4)&mask], §92 §41),
    # not a separate math.cos — it reads the very same float32 table entry, one quarter-turn along.
    assert gmath_cos(4095) == gmath_sin(4095 + 4 * 4096)      # +NUM_ANGLES/4 in field units (4096<<2)
    # diverges from naive float for a non-multiple-of-4 field (the whole reason for the table) —
    # checked where sin is steep (~22°); near 90° sin is flat and the error surfaces via cos instead.
    assert abs(gmath_sin(4095) - math.sin(4095 / 65536 * 2 * math.pi)) > 1e-4


def test_gmath_table_is_editor_exact_float32_yaw_180():
    # §92 §41 — the editor's `FGlobalMath::TrigFLOAT[]` is reproduced BIT-FOR-BIT, which requires two
    # things a naive `f32(sin(idx·2π/N))`/`f32(cos(idx·2π/N))` gets wrong (each ~1 float32 ULP in the
    # transformed vertex — the whole UNATCO rotated-brush byte residual):
    #
    #   (1) THE ANGLE IS CAST TO FLOAT32 BEFORE `sin` (appSin takes a FLOAT param). At Yaw=32768 (180°,
    #       table index 8192) the angle is f32(π)=3.14159274 (8.7e-8 PAST π), so sin(180°) is NOT ~0 —
    #       it is -8.742278e-08. That tiny nonzero sin(180°), times a vertex coord, is exactly the
    #       1-ULP shift the editor produces and native's old `f32(sin(π_double))` (≈1.2e-16) did not:
    #       it moved Brush639's +y face node-315 plane offset from a spuriously-exact −312.0 to the
    #       editor's −311.99997 = nextafter(−312, 0) (measured, §92 §41).
    #   (2) COS is `sin` of a quarter-shifted table index, keeping it on the identical f32 grid.
    #
    # A regression to double-reconstruction (dropping the inner f32 cast, or computing cos via
    # math.cos) reintroduces the UNATCO rotated-brush twins — this pins it.
    # INDEPENDENT anchors — the exact float32 literals the editor's table holds at the three cardinal
    # yaws DX brushes actually use (90/180/270°), HARD-CODED, not re-derived from gmath's own formula
    # (so a broken table construction — e.g. dropping the inner f32 angle-cast, which makes cos(90°)
    # collapse to ~6e-17 — trips this instead of silently agreeing with itself). The -8.742278e-08 is
    # the editor-MEASURED value: it is what makes Brush639's (Yaw=32768) +y face land at node-315 plane
    # offset −311.99997 = nextafter(−312, 0), where native's old double `sin(π)`≈0 gave a bogus −312.0
    # (committed-tree oracle, §92 §41). DX content is CARDINAL-only (no non-cardinal rotated brush in any
    # level — Brush253's Yaw=32768,Roll=49152 is multi-axis but still cardinal), so these three literals
    # cover the exercised space; the general formula rests on the UE1 `FGlobalMath` decode (§92 §41).
    assert gmath_sin(16384) == 1.0                        # sin(90°)
    assert gmath_cos(16384) == -8.742277657347586e-08     # cos(90°) — editor table, NOT ~0
    assert gmath_sin(32768) == -8.742277657347586e-08     # sin(180°) — editor table, NOT ~0
    assert gmath_cos(32768) == -1.0                       # cos(180°)
    assert gmath_sin(49152) == -1.0                       # sin(270°)
    assert gmath_cos(49152) == 0.0                        # cos(270°)
    assert gmath_sin(32768) != _f32(math.sin(math.pi))    # what native computed BEFORE (≈1.2e-16 → 0)
    # Structural fact (not tautological with the literals): cos IS `sin` read a quarter-turn (N/4) along
    # the SAME table — CosTab(i) = TrigFLOAT[((i>>2)+4096)&mask]. A field shift of 4·4096 = +90°.
    for uu in (0, 4, 4095, 8192, 16384, 32768, 49151, 60000):
        assert gmath_cos(uu) == gmath_sin(uu + 4 * 4096)


def test_euler_matrix_uu_reads_the_table_for_a_non_cardinal_field():
    # Yaw=16383 (just under 90°): the yaw matrix's cos/sin come straight from the GMath table.
    R = euler_to_matrix_uu(0, 16383, 0)
    assert R[0][0] == gmath_cos(16383) and R[1][0] == gmath_sin(16383)


def test_deg_uu_round_trip():
    assert deg_to_uu(90.0) == 16384 and deg_to_uu(360.0) == 0 and deg_to_uu(-90.0) == 49152
    assert abs(uu_to_deg(16384) - 90.0) < 1e-9


def test_yaw_90_rotates_x_axis_to_y_axis():
    # A 90° yaw (about Z) sends +X → +Y (within the verified convention). Tolerance is 1e-6, NOT
    # machine-zero: the editor-exact GMath table stores cos(90°) = f32(sin(f32(3π/2))) = -8.74e-8,
    # not 0 (the documented ~1e-5uu table floor; §92 §41). This is a FEATURE — it is what the editor
    # renders — so the cardinal-axis checks assert "within the table floor", never bit-zero.
    R = euler_to_matrix(0.0, 90.0, 0.0)        # pitch, yaw, roll (degrees)
    x = matvec(R, (1.0, 0.0, 0.0))
    assert abs(x[0]) < 1e-6 and abs(x[1] - 1.0) < 1e-6 and abs(x[2]) < 1e-6


def test_pitch_90_and_roll_90_match_the_editor_sign():
    # The editor's pitch is (x,z)→(-z,x); roll is (y,z)→(z,-y) (spike). Spot-check the corrected
    # _ry/_rx via euler_to_matrix (forward only — no matrix_to_euler exists).
    # 1e-6 not machine-zero: the near-zero component is cos(90°) = -8.74e-8, the GMath table floor
    # (§92 §41 — see test_yaw_90_rotates_x_axis_to_y_axis).
    px = matvec(euler_to_matrix(90.0, 0.0, 0.0), (1.0, 0.0, 0.0))   # +X under pitch 90 → +Z
    assert abs(px[2] - 1.0) < 1e-6 and abs(px[0]) < 1e-6
    ry = matvec(euler_to_matrix(0.0, 0.0, 90.0), (0.0, 0.0, 1.0))   # +Z under roll 90 → +Y
    assert abs(ry[1] - 1.0) < 1e-6 and abs(ry[2]) < 1e-6


def test_compose_uu_is_per_field_addition_matching_the_editor():
    # PARITY (spike): the editor adds the delta into each FRotator field, not a matrix product.
    assert compose_uu((0, 16384, 0), (0, 16384, 0)) == (0, 32768, 0)   # two yaws add
    # onto an ALREADY-tilted actor: yaw delta lands in Yaw, Pitch is untouched (the editor's
    # field-add — NOT the true composed orientation, by design/parity).
    assert compose_uu((0, 16384, 0), (4096, 0, 0)) == (4096, 16384, 0)
    assert compose_uu((0, 49152, 0), (0, 32768, 0)) == (0, 16384, 0)   # wraps mod 65536


def test_rotate_point_orbits_the_pivot():
    R = euler_to_matrix(0.0, 90.0, 0.0)        # yaw 90°
    p = rotate_point((Decimal(64), Decimal(0), Decimal(0)), R, (Decimal(0), Decimal(0), Decimal(0)))
    assert abs(float(p[0])) < 1e-3 and abs(float(p[1]) - 64.0) < 1e-3   # (64,0,0) → (0,64,0)


def test_euler_to_matrix_degrees_quantizes_to_the_uu_table():
    # The degrees entry point snaps to the integer UU field and reads the table — so it agrees with
    # the UU path for a non-cardinal angle (not float sin of the raw degrees).
    assert euler_to_matrix(0.0, 89.999, 0.0) == euler_to_matrix_uu(0, deg_to_uu(89.999), 0)


def test_orbit_matrix_is_table_driven_not_float():
    # A non-multiple-of-4 field must orbit a 256uu arm to a DIFFERENT spot than float trig would —
    # proves the orbit reads the GMath table; a regression to float `sin` would collapse this gap.
    rad = 4095 / 65536 * 2 * math.pi
    float_R = [[math.cos(rad), -math.sin(rad), 0], [math.sin(rad), math.cos(rad), 0], [0, 0, 1]]
    p_tab = matvec(euler_to_matrix_uu(0, 4095, 0), (256.0, 0.0, 0.0))
    p_flt = matvec(float_R, (256.0, 0.0, 0.0))
    assert max(abs(p_tab[i] - p_flt[i]) for i in range(3)) > 1e-2


def test_euler_to_matrix_uu_is_a_proper_rotation_not_a_reflection():
    # det +1 (proper rotation); a sign/handedness/reflection bug flips it to −1. Columns orthonormal.
    R = euler_to_matrix_uu(4095, 8191, 2731)             # non-cardinal, all three axes
    assert abs(_det(R) - 1.0) < 1e-4
    for j in range(3):
        assert abs(sum(R[i][j] ** 2 for i in range(3)) - 1.0) < 1e-4
    # signed handedness: a small +yaw sends +X toward +Y, not −Y
    assert matvec(euler_to_matrix_uu(0, 1024, 0), (1.0, 0.0, 0.0))[1] > 0


def test_actor_matrix_normalizes_negative_and_wrapped_rotation_fields():
    def _light(rot):
        return SimpleNamespace(props=[("Rotation", rot)], brush=None, location=None)
    # Yaw=-1 and Yaw=65535 are the same orientation → identical matrix (mod-65536 normalization).
    assert actor_matrix(_light("(Yaw=-1)")) == actor_matrix(_light("(Yaw=65535)"))
    # a full turn (65536) is identity → the None fast-path sentinel, not a near-identity matrix.
    assert actor_matrix(_light("(Yaw=65536)")) is None


def test_actor_prepivot_parses_and_defaults():
    a = SimpleNamespace(props=[("PrePivot", "(X=10.000000,Y=-4.000000,Z=2.500000)")])
    assert actor_prepivot(a) == (Decimal("10.000000"), Decimal("-4.000000"), Decimal("2.500000"))
    assert actor_prepivot(SimpleNamespace(props=[])) == (Decimal(0), Decimal(0), Decimal(0))


def test_local_offset_subtracts_prepivot_before_rotating():
    v = (Decimal(32), Decimal(8), Decimal(-4))
    z = (Decimal(0), Decimal(0), Decimal(0))
    # zero prepivot + identity → byte-identical (the unrotated/unpivoted fast path)
    assert local_offset(None, z, v) == v
    # prepivot subtracts in the local frame (no rotation)
    assert local_offset(None, (Decimal(10), Decimal(0), Decimal(0)), v) == (Decimal(22), Decimal(8), Decimal(-4))
    # with rotation: R·(v − prepivot) — yaw 90° of (v − (10,8,-4)) = (22,0,0) → (0,22,0)
    R = euler_to_matrix_uu(0, 16384, 0)
    out = local_offset(R, (Decimal(10), Decimal(8), Decimal(-4)), v)
    # 1e-5 not 1e-6: the near-zero component is cos(90°)·22 ≈ 1.9e-6, the GMath table floor scaled by
    # the 22uu arm (§92 §41 — the editor renders exactly this, it is not error).
    assert abs(float(out[0])) < 1e-5 and abs(float(out[1]) - 22.0) < 1e-5


def test_world_vertices_honours_prepivot():
    a = make_brush_actor("B", cube(64, 64, 64), location=(Decimal(100), Decimal(0), Decimal(0)))
    base = set(world_vertices(a))
    a.props.append(("PrePivot", "(X=10.000000,Y=0.000000,Z=0.000000)"))
    # PrePivot=(10,0,0): world = Location + (v − prepivot) → every vertex shifts −10 in X.
    assert set(world_vertices(a)) == {(x - 10.0, y, z) for (x, y, z) in base}


def test_world_to_local_point_inverts_the_actor_transform():
    from uedcli.rotation import world_to_local_point, local_offset, actor_matrix, actor_prepivot
    from uedcli.emit import clean
    a = make_brush_actor("B", cube(64, 64, 64), location=(Decimal(100), Decimal(0), Decimal(0)))
    a.props.append(("Rotation", "(Yaw=16384)"))           # 90° yaw
    a.props.append(("PrePivot", "(X=8.000000,Y=0.000000,Z=0.000000)"))
    R, pp, loc = actor_matrix(a), actor_prepivot(a), a.location
    v = a.brush.polys[0].vertices[0]
    w = local_offset(R, pp, v)                            # forward: world = Location + R·(v − pp)
    world = tuple(loc[i] + w[i] for i in range(3))
    back = world_to_local_point(a, world)                 # inverse recovers the local corner
    assert tuple(clean(c) for c in back) == tuple(clean(c) for c in v)


def test_world_to_local_delta_rotates_a_delta_into_the_local_frame():
    from uedcli.rotation import world_to_local_delta
    a = make_brush_actor("B", cube(2, 2, 2))
    a.props.append(("Rotation", "(Yaw=16384)"))           # yaw 90°: local +X → world +Y
    d = world_to_local_delta(a, (Decimal(10), Decimal(0), Decimal(0)))  # a world +X delta
    assert abs(float(d[0])) < 1e-6 and abs(float(d[1]) + 10.0) < 1e-6   # → local −Y


def test_world_to_local_point_inverts_non_cardinal_rotation_at_large_extent():
    # At a non-cardinal angle (Yaw=8192=45°, where Rᵀ ≠ R⁻¹ for the float32 GMath matrix) and a large
    # map extent (±32768), `transpose` drifts the inverse past CLEAN_EPS; the TRUE matrix inverse
    # keeps the round-trip exact. Regression for the float32-orthonormality assumption (GPT review).
    from uedcli.rotation import world_to_local_point, local_offset, actor_matrix, actor_prepivot
    a = make_brush_actor("B", cube(65536, 65536, 65536), location=(Decimal(0), Decimal(0), Decimal(0)))
    a.props.append(("Rotation", "(Yaw=8192)"))            # 45°
    R, pp, loc = actor_matrix(a), actor_prepivot(a), a.location
    v = a.brush.polys[0].vertices[0]                      # a corner at ±32768
    w = local_offset(R, pp, v)
    world = tuple(loc[i] + w[i] for i in range(3))
    back = world_to_local_point(a, world)
    assert max(abs(float(back[i]) - float(v[i])) for i in range(3)) < 1e-4


def test_world_to_local_point_unrotated_is_exact_decimal():
    from uedcli.rotation import world_to_local_point
    a = make_brush_actor("B", cube(64, 64, 64), location=(Decimal(100), Decimal(0), Decimal(0)))
    a.props.append(("PrePivot", "(X=10.000000,Y=0.000000,Z=0.000000)"))
    # unrotated: world − Location + PrePivot, exact Decimal (so integer corners match exactly)
    assert world_to_local_point(a, (Decimal(132), Decimal(32), Decimal(8))) == (Decimal(42), Decimal(32), Decimal(8))


def test_is_identity_uu_treats_low_bit_fields_as_identity():
    # The GMath table truncates the low 2 bits, so fields 0..3 (per axis) ALL render as identity —
    # uedcli must treat them as unrotated to match the editor (else the brush-edit guards refuse a
    # brush the engine renders straight). 4 is the first value that actually rotates.
    assert is_identity_uu((0, 0, 0)) and is_identity_uu((1, 2, 3)) and is_identity_uu((0, 3, 0))
    assert is_identity_uu((65536, 0, 0))                      # a full turn (>>2 → index 0)
    assert not is_identity_uu((0, 4, 0)) and not is_identity_uu((0, 0, 16384))
    # and the matrix fast-path agrees: a low-bit field returns the None sentinel.
    def _light(rot):
        return SimpleNamespace(props=[("Rotation", rot)], brush=None, location=None)
    assert actor_matrix(_light("(Yaw=2)")) is None
    assert actor_matrix(_light("(Yaw=4)")) is not None


def test_it_negates_frotator_fields_mod_65536():
    from uedcli import rotation as r
    assert r.negate_uu((0, 16384, 0)) == (0, 49152, 0)
    assert r.negate_uu((0, 0, 0)) == (0, 0, 0)


def test_it_subtracts_frotator_fields_as_inverse_of_compose():
    from uedcli import rotation as r
    base = (4096, 16384, 8192)
    delta = (1024, 49152, 256)
    composed = r.compose_uu(delta, base)
    assert r.subtract_uu(composed, base) == delta          # subtract undoes compose
    assert r.subtract_uu(base, base) == (0, 0, 0)


def test_it_parses_an_frotator_string_with_omitted_zero_fields():
    from uedcli import rotation as r
    assert r.parse_frotator("(Yaw=16384)") == (0, 16384, 0)
    assert r.parse_frotator("(Pitch=4096,Yaw=49152,Roll=8192)") == (4096, 49152, 8192)
    assert r.parse_frotator("") == (0, 0, 0)


def test_it_emits_an_frotator_string_omitting_zero_fields():
    from uedcli import rotation as r
    assert r.emit_frotator((0, 16384, 0)) == "(Yaw=16384)"
    assert r.emit_frotator((4096, 49152, 8192)) == "(Pitch=4096,Yaw=49152,Roll=8192)"
    assert r.emit_frotator((0, 0, 0)) == "()"          # all-zero — see note in Step 3


def test_it_parses_an_fvector_string_with_omitted_zero_axes():
    from uedcli import rotation as r
    from decimal import Decimal
    assert r.parse_fvector("(Z=256.000000)") == (Decimal(0), Decimal(0), Decimal("256"))
    assert r.parse_fvector("(X=32.500000,Z=-64.000000)") == (
        Decimal("32.5"), Decimal(0), Decimal("-64"))


def test_it_emits_an_fvector_string_omitting_zero_axes_at_six_dp():
    from uedcli import rotation as r
    from decimal import Decimal
    assert r.emit_fvector((Decimal(0), Decimal(0), Decimal("256"))) == "(Z=256.000000)"
    assert r.emit_fvector((Decimal("32.5"), Decimal(0), Decimal("-64"))) == (
        "(X=32.500000,Z=-64.000000)")
    assert r.emit_fvector((Decimal(0), Decimal(0), Decimal(0))) == "()"
