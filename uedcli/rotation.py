"""Pure rotation math for `actor rotate` (no editor). UE1 FRotator: Pitch about Y, Yaw about Z,
Roll about X, in Unreal units (UU: 65536 = 360°). The axis-application ORDER and signs match UE1's
convention as pinned by the spike (dev/docs/spikes/2026-06-19-frotator-convention.md); the
round-trip tests are convention-independent (self-consistency), the spike makes it match the editor.
Coords are Decimal (preserve authored fractions, finalized at 6-dp like emit.clean)."""
from __future__ import annotations

import math
import struct
from decimal import Decimal

# Shared with the write path so a huge coordinate exits 2 naming the value instead of
# raising a bare decimal.InvalidOperation here (rotation quantizes at three sites of its
# own, which `emit.clean` never sees). `emit` does not import `rotation`, so no cycle.
from .emit import quantize6

_UU = 65536

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
# `native.brush_marshal` hands to the Rust f32 CSG core, and uedcli's own previews/bounds/world_vertices).
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
    possibly-signed value) because **uedcli** canonicalizes to the in-range representative and
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
    return tuple(quantize6(Decimal(str(out[i] + float(pivot[i]))))
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
    identity. So `Yaw=2` renders exactly as unrotated as `Yaw=0`. uedcli's identity fast-path AND
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
    return tuple(quantize6(Decimal(str(c))) for c in f)


_ZERO3 = (Decimal(0), Decimal(0), Decimal(0))


def actor_prepivot(actor) -> tuple[Decimal, Decimal, Decimal]:
    """The actor's PrePivot (X,Y,Z) as Decimal, (0,0,0) if absent. PrePivot shifts the local origin:
    a world vertex is `Location + R·(v − PrePivot)`, NOT `Location + R·v`. uedcli never WRITES
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
    return tuple(quantize6(Decimal(str(rel[i] + float(pp[i])))) for i in range(3))


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
    vertex-baked — spec), PrePivot (the actor→world origin shift; uedcli never writes it but must
    measure it), AND scale/sheer (`MainScale`/`PostScale`, spike 2026-06-25). Empty for a non-brush.
    An unscaled+unrotated brush keeps the L=None fast path (byte-identical to plain Location + v)."""
    if actor.brush is None:
        return []
    from .transform import apply_linear
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    lx, ly, lz = float(loc[0]), float(loc[1]), float(loc[2])
    pp = actor_prepivot(actor)
    px, py, pz = float(pp[0]), float(pp[1]), float(pp[2])      # 0.0 when absent → unchanged math
    L = actor_linear(actor)
    out = []
    for poly in actor.brush.polys:
        rel = [(float(v[0]) - px, float(v[1]) - py, float(v[2]) - pz) for v in poly.vertices]
        xf = rel if L is None else apply_linear(rel, L)        # L=None fast path: float pass-through
        out.extend((lx + r[0], ly + r[1], lz + r[2]) for r in xf)
    return out


_TIE_EPS = 1e-6            # equidistant-from-centre grouping; symmetric sets tie EXACTLY
_ORIGIN = (Decimal(0), Decimal(0), Decimal(0))


def actor_own_pivot(actor, class_default):
    """The world point that stays fixed when THIS actor turns about itself — its `Location`, because
    `world = Location + PostScale·R·MainScale·(v − PrePivot)` maps `v == PrePivot` to `Location`
    exactly. An AUTHORED coordinate: whatever grid the designer built on, it is already on it.

    The Location is taken as authored — there is NO filtering on whether it sits near the actor's own
    geometry. A raw-CSG brush (`Location=(0,0,0)` with world-space vertices, as five `revolve` brushes
    in the TubePlatform trunk are) therefore contributes the world origin, and a set of only those
    rotates about the origin. Owner decision, 2026-07-26: use the Location of the closest brush in the
    set. `--pivot X,Y,Z` / `--pivot-actor` are the escape hatch.

    EVERY actor has one, as an EFFECTIVE value: an unauthored property takes its **class default**.
    So an actor carrying no `Location` is wherever its class puts it — not "missing a pivot". This
    never returns None, and there is no case to fall back from.

    `class_default` is that resolved default: a Decimal triple, or `None` **only** in the one case
    that is a real answer rather than a missing one — the class does not default `Location` at all,
    so the effective value is the property type's zero. It is a parameter rather than a lookup
    because this module is offline and schema-free; the caller owns the package search path.

    **REQUIRED, deliberately.** As `class_default=None` it read "no resolver supplied → assume the
    origin", which is a fallback for an unavailable `<package>.<name>` resource and is forbidden
    (`direction/conventions.md`). It is the worst shape of one: silent, and invisible to every test
    of the wired-up verb, because the wired-up verb always passes a resolver. Omitting it is now a
    `TypeError` at author time instead of a wrong pivot at run time.

    **"A vector defaults to (0,0,0)" is FALSE and must not be reinstated** — `Engine.Camera` defaults
    `Location=(X=-500,Y=-300,Z=300)` (verified live), and `dev/docs/architecture.md` names assuming
    "the default is zero" as *the bug the typed compare exists to remove*: an all-zero Location
    cleared to None once re-imported a Camera 655 uu away. Justifying this on "the emitter always
    writes a Location line" is likewise wrong — true of uedcli's own output, but an emission detail
    that says nothing about an imported or hand-written T3D."""
    loc = actor.location
    if loc is None:
        # `None` here means the CLASS does not default Location — a resolved answer, not a missing
        # one, so the type zero is correct. An unresolvable class never reaches this: the resolver
        # raises, and the verb exits 2 naming the actor.
        return _ORIGIN if class_default is None else tuple(class_default)
    # Normalised to Decimal: a caller that built the Actor in memory can hold floats, and the
    # arithmetic downstream is Decimal.
    return tuple(c if isinstance(c, Decimal) else Decimal(str(c)) for c in loc)


def best_grid_pivot(actors, class_default):
    """The pivot for `--by`: **the own-pivot (`Location`) of the set member nearest the selection's
    bbox centre**, so rotation turns about an AUTHORED point rather than a synthesized one. Grid
    alignment is therefore inherited — a Location the designer placed on the 16-grid keeps the set on
    the 16-grid — instead of being computed and rounded, which is what previously left a rotated set
    misaligned.

    - **Brushes win.** If the set has any brush, only brush Locations are candidates; otherwise point
      actors' Locations are. So a lone point actor (or several sharing one Location) pivots on its own
      Location EXACTLY — misaligned props turn in place and are never dragged onto a grid.
    - **Ties take the alphabetically first actor Name** (owner ruling, 2026-07-26): equidistant
      candidates are not averaged — an authored Location is used verbatim, whichever way the tie
      falls. Name order is independent of the set's order, so the pivot does not change with the order
      names arrive in the pipe.
    - Locations are used **as authored, unfiltered** (owner decision, 2026-07-26). A set of raw-CSG
      brushes (`Location=(0,0,0)`, world-space vertices) therefore pivots about the world origin;
      `--pivot`/`--pivot-actor` is the escape hatch for that.

    `class_default` is a REQUIRED `actor -> Decimal triple | None` callable supplying a class's
    default `Location`, consulted ONLY for an actor that does not state one (`Engine.Camera` defaults
    it to `(-500,-300,300)`, so assuming zero would pivot 655 uu from where the engine puts the
    actor). It is not optional and has no "good enough" stand-in: guessing the origin for a class
    whose package could not be loaded is exactly the fallback `direction/conventions.md` forbids for
    a `<package>.<name>` resource. A set whose actors all state a Location never invokes it, so an
    ordinary rotate still needs no package.

    There is NO fallback rule: every actor has an effective Location, so a non-empty set always has a
    pivot. An empty set is the only other case, and it is the world origin.

    `--pivot X,Y,Z` and `--pivot-actor NAME` override this entirely."""
    if not actors:
        return _ORIGIN
    # The centre comes from `writes.union_bounds` — THE selection bbox, the same one `actor bbox`
    # reports and `--within-bbox` tests against. Re-deriving it here drifted: a hand-rolled loop that
    # skipped point actors whose Location is unauthored measured a different box than either, so the
    # "nearest the centre" candidate was chosen against a centre no other verb agreed with.
    # Local import: `writes` imports `rotation` (`writes.actor_bounds`), so this direction must not
    # be a module-level edge.
    from . import writes
    lo, hi = writes.union_bounds(actors)
    cx, cy, cz = ((float(lo[i]) + float(hi[i])) / 2 for i in range(3))

    # Candidates carry their Name, because Name breaks ties. Brushes when the set has any.
    def _pivot(a):
        # `class_default` is resolved ONLY for an actor that does not state a Location — the schema
        # (and so a resolvable package path) is needed exactly then, not on every rotate. It takes
        # the ACTOR, not the class name, so a schema failure can name the actor the user has to fix.
        return actor_own_pivot(a, None if a.location is not None or class_default is None
                               else class_default(a))

    own = [(a.name or "", _pivot(a)) for a in actors if a.brush is not None]
    if not own:
        own = [(a.name or "", _pivot(a)) for a in actors]

    def _d2(nq):
        q = nq[1]
        return (float(q[0]) - cx) ** 2 + (float(q[1]) - cy) ** 2 + (float(q[2]) - cz) ** 2

    near = min(_d2(nq) for nq in own)
    # Equidistant candidates take the alphabetically first Name (owner ruling, 2026-07-26) — the
    # pivot stays an authored Location rather than an average of several, which would divide by the
    # number tied and land off the grid its inputs were on. Casefolded first, since names resolve
    # case-insensitively everywhere else, with the raw name as the final discriminator.
    return min((nq for nq in own if _d2(nq) - near <= _TIE_EPS),
               key=lambda nq: (nq[0].casefold(), nq[0]))[1]
