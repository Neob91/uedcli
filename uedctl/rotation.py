"""Pure rotation math for `actor rotate` (no editor). UE1 FRotator: Pitch about Y, Yaw about Z,
Roll about X, in Unreal units (UU: 65536 = 360°). The axis-application ORDER and signs match UE1's
convention as pinned by the spike (dev/docs/spikes/2026-06-19-frotator-convention.md); the
round-trip tests are convention-independent (self-consistency), the spike makes it match the editor.
Coords are Decimal (preserve authored fractions, finalized at 6-dp like emit.clean)."""
from __future__ import annotations

import math
import struct
from decimal import Decimal, ROUND_HALF_UP

_UU = 65536
_6DP = Decimal("0.000001")

# UE1 GMath integer sine table (spike 2026-06-19-group-rotate-exact-parity + §92 §41): the editor
# builds world geometry from a 16384-entry FLOAT32 table indexed by the 16-bit FRotator field shifted
# RIGHT by 2 (TRUNCATION, not rounding).  We reproduce the editor's `FGlobalMath::TrigFLOAT[]` values
# BIT-FOR-BIT (the two subtleties below).
#
# SCOPE OF THE BIT-PARITY (read before trusting "bit-exact"):
#   * The trig SOURCE (`gmath_sin`/`gmath_cos`) is bit-identical to the editor's `SinTab`/`CosTab`.
#   * A SINGLE-AXIS rotation (a lone yaw / pitch / roll) applies one axis matrix, so its transformed
#     vertex is bit-exact with the editor to the LAST BIT (verified: Brush639 `Yaw=32768` node-315
#     −312.0 → −311.99997, N=22 twins 0, §92 §41).
#   * A MULTI-AXIS FRotator composes `matmul(Rz, matmul(Ry, Rx))` in Python DOUBLE, whereas UE composes
#     in float32 `FCoords` — so IN GENERAL (arbitrary sin/cos) it is ULP-APPROXIMATE, NOT bit-exact.
#     BUT every rotated brush in the DX levels uses only CARDINAL components (0/90/180/270° on any axis),
#     including genuine multi-axis ones (e.g. UNATCO Brush253 `Yaw=32768,Roll=49152`); a cardinal matrix's
#     entries are {0, ±1, ±8.74e-8}, whose Python-double composition is BIT-IDENTICAL to an f32 FCoords
#     compose after the final f32 cast (cross-terms ~1e-15 ≪ the f32 ULP; verified 63/63 cardinal combos,
#     0 delta).  So DX's cardinal multi-axis brushes are bit-exact too.
#   * The ULP GAP therefore only bites a genuine NON-CARDINAL multi-axis FRotator (arbitrary angle on ≥2
#     axes).  DX content has NONE, so it is unexercised and UNMEASURED against the editor — a known gap
#     that a future non-cardinal rotated brush (or the group-rotate path) would need f32 FCoords to close.
# Net: bit-exact for every rotation DX content actually contains (single-axis + cardinal multi-axis);
# ULP-approximate only for non-cardinal multi-axis composition, which no DX level exercises.
#
# Two subtleties that a naive `f32(sin(idx·2π/N))` / `f32(cos(idx·2π/N))` gets WRONG (both pinned §92 §41,
# each worth ~1 float32 ULP in the transformed vertex — the entire UNATCO rotated-brush byte residual):
#
#   (1) THE ANGLE IS CAST TO FLOAT32 BEFORE `sin`.  UE1 builds the table with
#       `TrigFLOAT[k] = appSin((FLOAT)k * 2.f * PI / (FLOAT)NUM_ANGLES)`, and `appSin(FLOAT)` takes a
#       float32 parameter — so the double angle is ROUNDED TO float32 before the libm `sin`.  For k=8192
#       (180°) that float32 angle is `f32(π)=3.14159274` (8.7e-8 PAST π), so the stored sine is
#       `sin(f32(π)) = -8.742278e-08`, NOT the ~0 that `f32(sin(π_double))` yields.  That tiny nonzero
#       sin(180°), times a vertex coordinate, is exactly the 1-ULP transform shift the editor produces
#       and native did not (Brush639 node-315 plane offset −312.0 → −311.99997).
#
#   (2) COS IS `sin` OF A QUARTER-SHIFTED TABLE INDEX, not a separate `cos` call: UE1's `CosTab(i)` reads
#       `TrigFLOAT[((i>>2)+NUM_ANGLES/4)&mask]`.  Reading the same table (rather than `math.cos`) keeps
#       cos on the identical float32 quantization grid as sin.
#
# Stored FRotator field values are unaffected — this is the trig SOURCE only (feeds the R matrix that
# `native.materialize` hands to the Rust f32 CSG core, and uedctl's own previews/bounds/world_vertices).
_TRIG_N = 16384            # GMath NUM_ANGLES
_ANGLE_SHIFT = 2          # 16-bit field >> 2 → 14-bit table index (low 2 bits truncated)
_TRIG_MASK = _TRIG_N - 1
_TRIG_QUARTER = _TRIG_N // 4   # NUM_ANGLES/4 — CosTab's index offset from SinTab (a +90° phase)


def _f32(x: float) -> float:
    """Round to float32 — the editor stores its sine table as `float`, so match it bit-for-bit."""
    return struct.unpack("f", struct.pack("f", x))[0]


# The editor's `FGlobalMath::TrigFLOAT[NUM_ANGLES]`, reproduced bit-exactly (see the two subtleties
# above).  `_f32(math.sin(_f32(...)))` mirrors `appSin((FLOAT)k*2f*PI/(FLOAT)N)`: the inner `_f32` is
# the FLOAT32 cast the `appSin(FLOAT)` parameter imposes on the angle; libm `sin` runs in double; the
# outer `_f32` is the FLOAT storage of `TrigFLOAT[k]`.
_TRIG = tuple(_f32(math.sin(_f32(k * 2.0 * math.pi / _TRIG_N))) for k in range(_TRIG_N))


def gmath_sin(uu: int) -> float:
    """`FGlobalMath::SinTab(uu)` — `TrigFLOAT[(uu>>2)&16383]`, bit-identical to the editor."""
    return _TRIG[(uu >> _ANGLE_SHIFT) & _TRIG_MASK]


def gmath_cos(uu: int) -> float:
    """`FGlobalMath::CosTab(uu)` — `TrigFLOAT[((uu>>2)+NUM_ANGLES/4)&16383]` (sin of a quarter-shifted
    index, NOT a separate `cos`), bit-identical to the editor."""
    return _TRIG[((uu >> _ANGLE_SHIFT) + _TRIG_QUARTER) & _TRIG_MASK]


def deg_to_uu(deg: float) -> int:
    return round(deg * _UU / 360.0) % _UU


def uu_to_deg(uu: int) -> float:
    return (uu % _UU) * 360.0 / _UU


def uu_field(x) -> int:
    """An FRotator field from CLI input already given in **unreal rotation units** (0..65535;
    16384 = 90°, 32768 = 180°, 65536 = a full turn). Rounds to the integer field and wraps mod
    65536 (so a negative delta like -16384 becomes 49152). This is the identity 'parse' for the
    `--rotate` / `--rot` / `actor rotate` inputs, which are UU — NOT degrees (contrast `deg_to_uu`,
    which the preview camera-pose grammar still uses)."""
    return round(float(x)) % _UU


# Axis matrices in UED22's VERIFIED convention (spike 2026-06-19-frotator-convention): yaw is the
# textbook Rz; pitch and roll have their sin sign FLIPPED vs textbook (the editor's pitch is
# (x,z)→(-z,x) and roll is (y,z)→(z,-y), corner-tracked from captured world geometry). Each takes a
# UU FRotator field and reads sin/cos from the GMath table so the matrix matches the editor exactly.
def _rx_uu(uu):  # roll, about X — sin flipped
    c, s = gmath_cos(uu), gmath_sin(uu)
    return [[1, 0, 0], [0, c, s], [0, -s, c]]


def _ry_uu(uu):  # pitch, about Y — sin flipped
    c, s = gmath_cos(uu), gmath_sin(uu)
    return [[c, 0, -s], [0, 1, 0], [s, 0, c]]


def _rz_uu(uu):  # yaw, about Z — textbook
    c, s = gmath_cos(uu), gmath_sin(uu)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def matmul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def matvec(M, v):
    return tuple(sum(M[i][k] * v[k] for k in range(3)) for i in range(3))


def euler_to_matrix_uu(pitch_uu: int, yaw_uu: int, roll_uu: int):
    """Rotation matrix for an FRotator delta given as UU fields, trig from the GMath table. Order =
    yaw→pitch→roll (UE1; spike-pinned): R = Rz(yaw) · Ry(pitch) · Rx(roll), so a point is rolled,
    then pitched, then yawed. Trig is the editor's bit-exact GMath table (module header): bit-exact with
    the editor for every rotation DX content contains (single-axis + CARDINAL multi-axis), because a
    cardinal matrix composes identically in Python double and UE f32; only a genuine NON-cardinal
    multi-axis FRotator is ULP-approximate (Python-double `matmul` ≠ UE f32 FCoords) — see the module
    header "SCOPE OF THE BIT-PARITY". Callers with integer fields (the orbit delta, the stored Rotation)
    use it directly."""
    return matmul(_rz_uu(yaw_uu), matmul(_ry_uu(pitch_uu), _rx_uu(roll_uu)))


def euler_to_matrix(pitch_deg: float, yaw_deg: float, roll_deg: float):
    """Rotation matrix for an FRotator delta in DEGREES. Quantizes to the integer UU field first
    (`deg_to_uu`) — exactly what gets stored and what the editor renders from — then builds via the
    GMath table, so a degree input and its stored field agree."""
    return euler_to_matrix_uu(deg_to_uu(pitch_deg), deg_to_uu(yaw_deg), deg_to_uu(roll_deg))


# NOTE: no `matrix_to_euler` is needed. The spike showed the editor composes the Rotation FIELD by
# per-component addition (see compose_uu), and the Location orbit only needs the FORWARD matrix
# (euler_to_matrix_uu → rotate_point) — nothing ever converts a matrix back to a FRotator. This also
# removes the gimbal-pole (pitch=±90°) concern entirely.


def compose_uu(delta_uu, base_uu) -> tuple[int, int, int]:
    """Compose two FRotators by PER-COMPONENT ADDITION (mod 65536) — this is what UnrealEd's gizmo
    does (spike 2026-06-19-multiactor-rotate-groundtruth: the editor adds the delta into each
    Pitch/Yaw/Roll field, NOT a matrix product). PARITY-FIRST (user decision 2026-06-19): match the
    editor, including its geometrically-naive result when re-rotating an ALREADY-tilted actor
    (off-axis, field-add ≠ the true composed orientation). For an upright or single-axis actor it
    equals the matrix compose, so the common case is exact. NOTE: only the Rotation FIELD composes
    this way; the Location ORBIT still uses `euler_to_matrix_uu` (the editor orbits Location by the
    real matrix — verified — so a group rotation is matrix-orbit + field-add-compose, exactly as
    the editor does). The result is mod-65536 (orientation-equivalent to the editor's immediate,
    possibly-signed value) because **uedctl** canonicalizes to the in-range representative and
    writes that into the trunk, so both sides of a compare agree — **NOT** because the editor does
    it. SUPERSEDED 2026-07-25: this docstring previously claimed "a materialize import normalizes
    mod 65536 anyway", which is FALSE. UnrealEd stores and re-serializes an FRotator field verbatim,
    over-range values included, through import, `MAP SAVE`, and the UCC re-export the H3 post-verify
    reads (live-probed on point actors via `MAP IMPORTADD` and brushes via `EDIT PASTE`:
    `dev/docs/spikes/2026-07-25-frotator-import-normalization/`). The reduction HERE is harmless, but
    the old justification would license adding a `% 65536` on the compare/emit path — which would
    rewrite most ingested rotators to zero and make post-verify unpassable. Reducing mod 65536 is
    fine for MEASURING orientation (`actor_rotation_uu`, `is_identity_uu`), never for anything
    written to the trunk or fed to the compare (`typedprops` decodes an FRotator component as a
    VERBATIM int for exactly this reason)."""
    return tuple((delta_uu[i] + base_uu[i]) % _UU for i in range(3))


def negate_uu(uu: tuple[int, int, int]) -> tuple[int, int, int]:
    """Per-component FRotator negation, mod 65536. The additive inverse of compose_uu."""
    return tuple((-c) % _UU for c in uu)


def subtract_uu(a: tuple[int, int, int], b: tuple[int, int, int]) -> tuple[int, int, int]:
    """Per-component FRotator subtraction a-b, mod 65536 — inverse of compose_uu(delta, base)."""
    return compose_uu(a, negate_uu(b))


def parse_frotator(s: str) -> tuple[int, int, int]:
    """`(Pitch=..,Yaw=..,Roll=..)` (zero fields omitted) -> UU tuple; absent fields default 0."""
    import re
    g = {m.group(1).lower(): int(m.group(2)) % _UU
         for m in re.finditer(r"(Pitch|Yaw|Roll)=(-?\d+)", s)}
    return (g.get("pitch", 0), g.get("yaw", 0), g.get("roll", 0))


def emit_frotator(uu: tuple[int, int, int]) -> str:
    """UU tuple -> `(Pitch=..,Yaw=..,Roll=..)` integer fields, ZERO FIELDS OMITTED (editor form;
    e.g. KeyRot(1)=(Yaw=16384)). All-zero -> `()` (callers must omit a wholly-zero key entirely)."""
    parts = [f"{name}={v}" for name, v in zip(("Pitch", "Yaw", "Roll"), uu) if v]
    return "(" + ",".join(parts) + ")"


def parse_fvector(s: str) -> tuple[Decimal, Decimal, Decimal]:
    """`(X=..,Y=..,Z=..)` (zero axes omitted) -> Decimal triple; absent axes default 0."""
    import re
    g = {m.group(1): Decimal(m.group(2))
         for m in re.finditer(r"([XYZ])=(-?\d+\.?\d*)", s)}
    z = Decimal(0)
    return (g.get("X", z), g.get("Y", z), g.get("Z", z))


def emit_fvector(v: tuple) -> str:
    """Decimal triple -> `(X=..,Y=..,Z=..)` 6-dp, ZERO AXES OMITTED (editor form; e.g.
    KeyPos(1)=(Z=256.000000)). Uses emit.fmt_loc for 6-dp/clean. All-zero -> `()`."""
    from .emit import fmt_loc
    parts = [f"{ax}={fmt_loc(c)}" for ax, c in zip("XYZ", v) if Decimal(str(c)) != 0]
    return "(" + ",".join(parts) + ")"


def rotate_point(p, R, pivot):
    """World point p (Decimal triple) rotated by R about pivot (Decimal triple) → Decimal triple
    at 6-dp."""
    rel = [float(p[i]) - float(pivot[i]) for i in range(3)]
    out = matvec(R, rel)
    # quantize at 6-dp with ROUND_HALF_UP to match emit.clean/fmt_loc (the repo's exact-Decimal
    # rounding); emit.clean then re-snaps sub-grid noise to the integer grid.
    return tuple(Decimal(str(out[i] + float(pivot[i]))).quantize(_6DP, ROUND_HALF_UP)
                 for i in range(3))


def actor_rotation_uu(actor) -> tuple[int, int, int]:
    """The actor's Rotation FRotator in UU (pitch,yaw,roll), (0,0,0) if absent. Parses the
    `Rotation=(Pitch=..,Yaw=..,Roll=..)` prop. Each component is reduced mod 65536 so a full-turn
    value (Yaw=65536, orientation-identical to identity) reads as (0,0,0). Omitted components
    default to 0 (UnrealEd omits zero fields on export). NB: "is this rotated?" is decided by
    `is_identity_uu` (table-truncation-aware), NOT a raw `== (0,0,0)`, since fields 1..3 render
    identity too."""
    import re
    for k, v in actor.props:
        if k == "Rotation":
            g = {m.group(1).lower(): int(m.group(2)) % _UU
                 for m in re.finditer(r"(Pitch|Yaw|Roll)=(-?\d+)", v)}
            return (g.get("pitch", 0), g.get("yaw", 0), g.get("roll", 0))
    return (0, 0, 0)


def is_identity_uu(uu) -> bool:
    """True when the FRotator renders as identity in the editor. The GMath table truncates the low
    2 bits (`(c>>2)&16383`), so EVERY component value 0..3 maps to table index 0 → sin=0/cos=1 →
    identity. So `Yaw=2` renders exactly as unrotated as `Yaw=0`. uedctl's identity fast-path AND
    the brush-edit guards key off THIS (not a raw `== (0,0,0)`), so a low-bit-only field is treated
    as unrotated to match the editor — otherwise `brush clip`/`vertex move` would refuse a brush the
    engine renders straight. The stored field is left intact (never rewritten)."""
    return all(((c >> 2) & _TRIG_MASK) == 0 for c in uu)


def actor_matrix(actor):
    """The actor's Rotation as a 3×3, None (renders identity) when absent or low-bit-only. The
    per-poly/per-corner consumers share this MATRIX with world_vertices (they apply it slightly
    differently — see rotate_local's 6dp quantize vs world_vertices' raw matvec — so world coords
    can differ at ~1e-7, well under CLEAN_EPS=0.001, harmless)."""
    uu = actor_rotation_uu(actor)
    if is_identity_uu(uu):
        return None                       # IDENTITY sentinel — callers skip rotation entirely
    return euler_to_matrix_uu(*uu)        # integer fields → GMath table (bit-exact single-axis; see hdr)


def actor_main_scale(actor):
    """The actor's `MainScale` as a `transform.FScale` (identity when the field is None/absent).
    LOCAL / pre-rotation (spike 2026-06-25)."""
    from .transform import IDENTITY
    return actor.main_scale if actor.main_scale is not None else IDENTITY


def actor_post_scale(actor):
    """The actor's `PostScale` as a `transform.FScale` (identity when absent). WORLD / post-rotation."""
    from .transform import IDENTITY
    return actor.post_scale if actor.post_scale is not None else IDENTITY


def actor_linear(actor):
    """The actor's FULL linear part `L = PostScale · R · MainScale` as a 3×3, or None (renders as
    identity) when rotation AND both scales are identity. This is the linear half of the spike-verified
    `world = Location + L·(v − PrePivot)`: `MainScale` multiplies in the brush LOCAL frame (before
    rotation), `PostScale` in the WORLD frame (after). Returns EXACTLY `actor_matrix` when there is no
    scale, so every existing unscaled/rotated path is byte-identical (the None fast path is preserved
    for the common unscaled case). Shared by world_vertices + every world-geometry consumer."""
    from .transform import fscale_matrix
    R = actor_matrix(actor)                           # None or the rotation 3×3
    ms = actor_main_scale(actor)
    ps = actor_post_scale(actor)
    ms_id, ps_id = ms.is_identity(), ps.is_identity()
    if R is None and ms_id and ps_id:
        return None                                   # IDENTITY sentinel — unchanged fast path
    L = R if R is not None else [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    if not ms_id:
        L = matmul(L, fscale_matrix(ms))              # R · MainScale (MainScale is innermost/local)
    if not ps_id:
        L = matmul(fscale_matrix(ps), L)              # PostScale · (R · MainScale)  (world/outermost)
    return L


def rotate_local(R, v):
    """Rotate a LOCAL Decimal vertex by R (None=identity), returning a Decimal triple. None
    short-circuits to the unchanged Decimal so the unrotated path is byte-identical (exact integers
    stay integers — keeps query.list_vertices' Decimal contract + its existing tests)."""
    if R is None:
        return tuple(v)
    f = matvec(R, (float(v[0]), float(v[1]), float(v[2])))
    return tuple(Decimal(str(c)).quantize(_6DP, ROUND_HALF_UP) for c in f)


_ZERO3 = (Decimal(0), Decimal(0), Decimal(0))


def actor_prepivot(actor) -> tuple[Decimal, Decimal, Decimal]:
    """The actor's PrePivot (X,Y,Z) as Decimal, (0,0,0) if absent. PrePivot shifts the local origin:
    a world vertex is `Location + R·(v − PrePivot)`, NOT `Location + R·v`. uedctl never WRITES
    PrePivot (invariant D8) but must honour it when MEASURING imported brushes (bounds/preview/world
    verts). Omitted components default to 0 (UnrealEd omits zero fields on export)."""
    import re
    for k, v in actor.props:
        if k == "PrePivot":
            g = {m.group(1).lower(): Decimal(m.group(2))
                 for m in re.finditer(r"(X|Y|Z)=(-?[0-9.]+)", v)}
            return (g.get("x", Decimal(0)), g.get("y", Decimal(0)), g.get("z", Decimal(0)))
    return _ZERO3


def local_offset(R, prepivot, v):
    """A LOCAL vertex's offset from the actor Location, honouring Rotation + PrePivot: R·(v −
    prepivot). R=None is identity; a zero prepivot skips the subtraction so the unrotated/unpivoted
    path stays byte-identical. Returns a Decimal triple (callers add Location)."""
    if prepivot != _ZERO3:
        v = tuple(v[i] - prepivot[i] for i in range(3))
    return rotate_local(R, v)


def transpose(M):
    return [[M[j][i] for j in range(3)] for i in range(3)]


def inverse(M):
    """True 3×3 inverse (adjugate/determinant). `R` is built from the float32 GMath table, so it is
    only APPROXIMATELY orthonormal — `Rᵀ` is a ~1e-7-off inverse, which at large map extents
    (±32768) drifts a world→local POINT by up to ~1e-3uu (past CLEAN_EPS → a rotated vertex-move
    misses / a clip shaves a sliver). `R⁻¹·R = I` exactly, so points/deltas round-trip. (A plane
    NORMAL still uses `transpose` — `Rᵀ` is its EXACT pullback for any invertible R, not an
    approximation.)"""
    (a, b, c), (d, e, f), (g, h, i) = M
    A, B, C = (e * i - f * h), (f * g - d * i), (d * h - e * g)
    det = a * A + b * B + c * C
    return [[A / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [B / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [C / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def _as_dec(x):
    return x if isinstance(x, Decimal) else Decimal(str(x))


def world_to_local_point(actor, world):
    """Invert the actor transform: a WORLD point → the brush's LOCAL vertex coord,
    `local = L⁻¹·(world − Location) + PrePivot` where `L = PostScale·R·MainScale` (the full linear
    part incl. scale/sheer). The inverse of `Location + local_offset`. Uses the TRUE matrix inverse so
    a point round-trips exactly even at large extent / non-cardinal angles / non-uniform scale (the
    float32 L isn't perfectly orthonormal). Unscaled+unrotated → **exact Decimal** (`world − Location
    + PrePivot`), so an integer corner matches the stored vertex exactly; scaled/rotated → float
    inversion quantized to 6dp, which `emit.clean` snaps back to an integer corner (a *fractional*
    corner on a *scaled/rotated* brush may not round-trip — a known limit). Used by `brush clip`/
    `vertex move` to map world args to the local frame so they edit a scaled brush directly."""
    loc = actor.location or _ZERO3
    pp = actor_prepivot(actor)
    L = actor_linear(actor)
    if L is None:
        return tuple(_as_dec(world[i]) - _as_dec(loc[i]) + pp[i] for i in range(3))
    rel = matvec(inverse(L), tuple(float(world[i]) - float(loc[i]) for i in range(3)))
    return tuple(Decimal(str(rel[i] + float(pp[i]))).quantize(_6DP, ROUND_HALF_UP) for i in range(3))


def world_to_local_delta(actor, world_delta):
    """A WORLD displacement (a `--by` delta) → the brush LOCAL frame: `L⁻¹·delta` (no translation,
    no PrePivot; `L` includes scale/sheer). A delta is a difference of points, so it uses the same
    TRUE inverse as `world_to_local_point`. Unscaled+unrotated → unchanged (the same triple)."""
    L = actor_linear(actor)
    if L is None:
        return tuple(world_delta)
    return matvec(inverse(L), tuple(float(c) for c in world_delta))


def world_to_local_normal(actor, world_normal):
    """A WORLD plane normal → the brush LOCAL frame: `Lᵀ·normal` (L = PostScale·R·MainScale). A
    normal is a COVECTOR: the local→world normal map is the inverse-transpose `(L⁻¹)ᵀ`, so its INVERSE
    (world→local) is `Lᵀ` (the transpose). For a pure rotation this is `Rᵀ` (today's behavior); under
    non-uniform scale it is the correct pullback (a world plane `x+y=c` under `diag(2,1)` has local
    normal `(2,1)` = `Lᵀ·(1,1)`, which `brush clip` needs). Unscaled+unrotated → unchanged."""
    L = actor_linear(actor)
    if L is None:
        return tuple(world_normal)
    return matvec(transpose(L), tuple(float(c) for c in world_normal))


def world_vertices(actor) -> list[tuple[float, float, float]]:
    """A brush's vertices in WORLD space: `Location + L·(v − PrePivot)` where
    `L = PostScale·R·MainScale` (`actor_linear`). Honours the stored Rotation field (rotation is NOT
    vertex-baked — spec), PrePivot (the actor→world origin shift; uedctl never writes it but must
    measure it), AND scale/sheer (`MainScale`/`PostScale`, spike 2026-06-25). Empty for a non-brush.
    An unscaled+unrotated brush keeps the L=None fast path (byte-identical to plain Location + v)."""
    if actor.brush is None:
        return []
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    lx, ly, lz = float(loc[0]), float(loc[1]), float(loc[2])
    pp = actor_prepivot(actor)
    px, py, pz = float(pp[0]), float(pp[1]), float(pp[2])      # 0.0 when absent → unchanged math
    L = actor_linear(actor)
    out = []
    for poly in actor.brush.polys:
        for v in poly.vertices:
            vx, vy, vz = float(v[0]) - px, float(v[1]) - py, float(v[2]) - pz
            if L is None:
                rx, ry, rz = vx, vy, vz
            else:
                rx, ry, rz = matvec(L, (vx, vy, vz))
            out.append((lx + rx, ly + ry, lz + rz))
    return out


def _v2(c: Decimal) -> int:
    """2-adic grid alignment of a coord: largest k with c an integer multiple of 2^k; 0 → big
    (any power divides it); a non-integer → -1 (below the integer grid)."""
    if c != c.to_integral_value():
        return -1
    n = abs(int(c))
    if n == 0:
        return 64                       # 0 is divisible by every power of 2
    k = 0
    while n % 2 == 0:
        n //= 2
        k += 1
    return k


def best_grid_pivot(actors):
    """The selection's most grid-aligned candidate point (spec): brush WORLD vertices + point-actor
    Locations, scored by min-over-XYZ 2-adic valuation; max wins, ties → nearest bbox centre, then
    lexicographic. Fallback (all fractional) → bbox centre snapped to the nearest integer."""
    pts: list[tuple[Decimal, Decimal, Decimal]] = []
    for a in actors:
        if a.brush is not None:
            # brushes contribute their WORLD VERTICES — NOT their Location. A brush Location
            # (often the origin for builder brushes) scores align=64 (v2(0)=∞) and would beat
            # every real vertex, collapsing the pivot to the origin. Only point actors (no brush)
            # contribute their Location.
            pts += [tuple(Decimal(str(round(c, 6))) for c in w) for w in world_vertices(a)]
        elif a.location is not None:
            pts.append(tuple(a.location))
    if not pts:
        return (Decimal(0), Decimal(0), Decimal(0))
    xs = [float(p[0]) for p in pts]; ys = [float(p[1]) for p in pts]; zs = [float(p[2]) for p in pts]
    cx, cy, cz = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2

    def score(p):
        align = min(_v2(p[0]), _v2(p[1]), _v2(p[2]))
        dist = (float(p[0]) - cx) ** 2 + (float(p[1]) - cy) ** 2 + (float(p[2]) - cz) ** 2
        return (align, -dist, tuple(-float(c) for c in p))    # max align, then nearest, then lex

    best = max(pts, key=score)
    if min(_v2(best[0]), _v2(best[1]), _v2(best[2])) < 0:      # all fractional → grid-snap centre
        return (Decimal(round(cx)), Decimal(round(cy)), Decimal(round(cz)))
    return best
