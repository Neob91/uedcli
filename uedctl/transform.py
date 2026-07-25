"""Scale / sheer / permanent-transform algebra — the pure math behind `brush scale`,
`brush apply-transform` (renamed from `actor …` 2026-07-20), and the model-side USE of
`MainScale`/`PostScale`.

The spike-verified actor→world transform is
    world = Location + PostScale · R · MainScale · (v − PrePivot)
where `MainScale` is LOCAL (pre-rotation), `PostScale` is WORLD (post-rotation), `R` is the FRotator
matrix (`rotation.euler_to_matrix_uu`), and each of MainScale/PostScale is an `FScale` = a `Scale`
FVector + `SheerRate` + `SheerAxis`. Grounding:
`dev/docs/spikes/2026-06-25-scale-transform-mechanics.md` (emission rule §1, bake formula §2, sheer
axis + exact `sheer_coeff` §3, mirror/winding §4) and
`dev/docs/spikes/2026-06-25-mainscale-postscale-applytransform.md` (Main=local/Post=world, the bake
chain).

This module owns: parsing/emitting an `FScale`, the `sheer_coeff` snap, the FScale→3×3 linear map,
and the `apply-transform` bake. `rotation.py` composes the three into the full linear part
(`actor_linear`) and inverts it for the world→local edit path.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from decimal import Decimal

from .model import Actor, Vec3

_ZERO = Decimal(0)
_ONE = Decimal(1)

# The `Scale` struct's off-diagonal for a `SHEER_<A><B>` axis: shear target axis B by source axis A
# (`B += k·A`), so the matrix row index is B, the column index is A (spike §3, all pairs live).
_AXIS_IDX = {"X": 0, "Y": 1, "Z": 2}
_SHEER_OFFDIAG = {
    "SHEER_XY": (1, 0), "SHEER_XZ": (2, 0), "SHEER_YX": (0, 1),
    "SHEER_YZ": (2, 1), "SHEER_ZX": (0, 2), "SHEER_ZY": (1, 2),
}
DEFAULT_SHEER_AXIS = "SHEER_ZX"

# Below this a scale factor is degenerate (collapses the brush / non-invertible transform); the CLI
# rejects it (spec §7 "disallow zero or sub-epsilon scale").
SCALE_EPS = Decimal("0.0001")


@dataclass(frozen=True)
class FScale:
    """A `MainScale`/`PostScale` value: the `Scale` FVector, `SheerRate`, `SheerAxis`. Identity is
    unit scale + zero rate (the axis alone — `SHEER_ZX` — is the editor's identity-shear default)."""
    scale: Vec3 = (_ONE, _ONE, _ONE)
    sheer_rate: Decimal = _ZERO
    sheer_axis: str = DEFAULT_SHEER_AXIS

    def is_identity(self) -> bool:
        return (all(_as_dec(c) == _ONE for c in self.scale)
                and _as_dec(self.sheer_rate) == _ZERO)


IDENTITY = FScale()


def _as_dec(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


# ── parse / emit ──────────────────────────────────────────────────────────────────────────────

_AXIS_RE = re.compile(r"\b([XYZ])=(-?\d+\.?\d*)")
_SCALE_INNER_RE = re.compile(r"Scale=\(([^)]*)\)")
_RATE_RE = re.compile(r"SheerRate=(-?\d+\.?\d*)")
_SHEER_AXIS_RE = re.compile(r"SheerAxis=(SHEER_[A-Z]+)")


def parse_fscale(text: str) -> FScale:
    """Parse a T3D `MainScale`/`PostScale` value `( [Scale=(X=,Y=,Z=),] [SheerRate=,] SheerAxis= )`.
    An absent Scale axis defaults to 1.0 (identity component), absent SheerRate to 0, absent SheerAxis
    to SHEER_ZX (the editor omits identity components on export — spike §1)."""
    scale = [_ONE, _ONE, _ONE]
    m = _SCALE_INNER_RE.search(text)
    if m:
        for ax, val in _AXIS_RE.findall(m.group(1)):
            scale[_AXIS_IDX[ax]] = Decimal(val)
    rate = _ZERO
    mr = _RATE_RE.search(text)
    if mr:
        rate = Decimal(mr.group(1))
    axis = DEFAULT_SHEER_AXIS
    ma = _SHEER_AXIS_RE.search(text)
    if ma:
        axis = ma.group(1)
    return FScale(scale=(scale[0], scale[1], scale[2]), sheer_rate=rate, sheer_axis=axis)


def _fmt6(d) -> str:
    """6-dp fixed as the editor emits scale/sheer components; a clean -0 prints as 0."""
    d = _as_dec(d)
    if d == 0:
        d = _ZERO
    return f"{d:.6f}"


def emit_fscale(fs: FScale) -> str:
    """The editor's exact serialization (spike §1, H3-critical): a `Scale` axis is written iff ≠1.0
    (negatives ARE written), the whole `Scale=(...)` omitted when all axes 1.0; `SheerRate` iff ≠0.0;
    `SheerAxis` ALWAYS. 6-dp throughout. This MUST byte-match the editor or H3 post-verify fails."""
    parts: list[str] = []
    axes = [(name, _as_dec(c)) for name, c in zip("XYZ", fs.scale)]
    if any(c != _ONE for _, c in axes):
        inner = ",".join(f"{name}={_fmt6(c)}" for name, c in axes if c != _ONE)
        parts.append(f"Scale=({inner})")
    if _as_dec(fs.sheer_rate) != _ZERO:
        parts.append(f"SheerRate={_fmt6(fs.sheer_rate)}")
    parts.append(f"SheerAxis={fs.sheer_axis}")
    return "(" + ",".join(parts) + ")"


# ── sheer coefficient (disassembled piecewise snap, engine-fact) ────────────────────────────────

def sheer_coeff(rate) -> float:
    """The editor's `SheerRate` → sheer-matrix coefficient `k`, an EXACT closed form disassembled
    from `core.dll` `0x1001e7c0` and validated against a 20-point live scan (spike §3). Antisymmetric
    in `r`; a deliberate GUI snap (deadzone + a snap-to-0.5 notch). Pinned in test_engine_facts."""
    r = float(rate)
    a = abs(r)
    if a <= 0.05:
        k = 0.0
    elif a <= 0.55:
        k = a - 0.05
    elif a <= 0.65:
        k = 0.5
    else:
        k = a - 0.15
    return math.copysign(k, r) if k != 0.0 else 0.0


# ── linear maps ─────────────────────────────────────────────────────────────────────────────────

_I3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def fscale_matrix(fs: FScale) -> list[list[float]]:
    """The FScale as a 3×3 point transform `M` (`v ↦ M·v`, float): scale each axis, then apply the
    sheer on the scaled coords — `M = Sheer · Scale`, so for `SHEER_AB` the target `B_new = s_B·B +
    k·(s_A·A)`. det(M) = product of the scale axes (the sheer is unit-triangular). The pure-scale and
    pure-sheer cases match the live spike exactly; the combined scale+sheer ORDER is an offline choice
    validated by the integration differential harness (uedctl authors scale-only, so this is only hit
    by ingested Main+Post+sheer brushes)."""
    sx, sy, sz = (float(c) for c in fs.scale)
    M = [[sx, 0.0, 0.0], [0.0, sy, 0.0], [0.0, 0.0, sz]]
    k = sheer_coeff(fs.sheer_rate)
    if k != 0.0:
        off = _SHEER_OFFDIAG.get(fs.sheer_axis)
        if off is not None:
            r, c = off                                # B += k·A → row B, col A, applied to Scale·v
            # (Sheer · Scale): the off-diagonal multiplies the already-scaled source column.
            M[r][c] += k * M[c][c]
    return M


def det3(M) -> float:
    return (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1])
            - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
            + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))


# ── permanent transform (`brush apply-transform`) ───────────────────────────────────────────────

def _reset_rotation(out: Actor) -> None:
    """Reset the baked actor's `Rotation` field to an EXPLICIT zero — the rotation now lives in the
    vertices, so the actor itself must be unrotated.

    Written out rather than dropped, and only when the actor HAD a `Rotation` (an actor that never
    carried one keeps whatever its class says, exactly as before the bake). An omitted property does
    not re-import as zero — it re-imports as the CLASS DEFAULT, and `TNM.LavaSpitter` defaults
    `Rotation=(Pitch=16384,Yaw=0,Roll=0)` — so dropping the line here would bake the geometry flat
    and then let the engine rotate it again (2026-07-25; same shape as the `PrePivot` case below).
    No placeable brush/mover class defaults `Rotation` today, so this is a rule fix, not an observed
    bug."""
    if not any(k == "Rotation" for k, _ in out.props):
        return
    out.props = [(k, v) for k, v in out.props if k != "Rotation"]
    out.props.append(("Rotation", "(Pitch=0,Yaw=0,Roll=0)"))


def bake(actor: Actor, *, lock_textures: bool = True) -> Actor:
    """Fold `MainScale + Rotation + PostScale` into the PolyList and reset the fields — the offline
    `ACTOR APPLYTRANSFORM` (spike §2). Returns a NEW Actor (the caller replaces the level entry). The
    linear part `L = PostScale·R·MainScale` transforms every vertex `v' = L·v` and `PrePivot' =
    L·PrePivot` (transformed, NOT zeroed — D8's explicit carve-out); `Location` is UNCHANGED and
    `MainScale`/`PostScale`/`Rotation` reset to identity. Winding is reversed per-poly when det(L)<0
    (an odd number of mirror axes / sheer) so the baked solid is not inside-out (CSG-crashing). With
    `lock_textures` the per-poly `Origin`/`TextureU`/`TextureV` transform by `L` too (the editor's
    TEXTURELOCK); without it they are left as-is (the texture slides)."""
    from . import rotation as ROT
    from .emit import clean

    out = copy.deepcopy(actor)
    L = ROT.actor_linear(actor)
    if L is None:                                     # identity transform — nothing to bake
        out.main_scale = IDENTITY
        out.post_scale = IDENTITY
        _reset_rotation(out)
        return out

    pp = ROT.actor_prepivot(actor)
    flip = det3(L) < 0

    def apply_point(p) -> Vec3:
        f = ROT.matvec(L, (float(p[0]), float(p[1]), float(p[2])))
        return (clean(f[0]), clean(f[1]), clean(f[2]))

    # Texture axes are COVECTORS (the texel coord is `(vertex − Origin)·TextureU`). For the mapping to
    # stay glued as vertices/Origin bake by L, a texture axis must transform by the INVERSE-TRANSPOSE
    # `(L⁻¹)ᵀ` (Unreal's normal/direction xform; §4 "normals use inverse-transpose"), NOT L — under a
    # pure rotation both coincide, but under scale/sheer only the inverse-transpose keeps the texture
    # density fixed. (Exact editor TEXTURELOCK parity is the integration differential's job.)
    NT = ROT.transpose(ROT.inverse(L))

    def apply_dir(p):
        f = ROT.matvec(NT, (float(p[0]), float(p[1]), float(p[2])))
        return (float(f[0]), float(f[1]), float(f[2]))

    if out.brush is not None:
        for poly in out.brush.polys:
            poly.vertices = [apply_point(v) for v in poly.vertices]
            if flip:
                poly.vertices.reverse()               # FPoly::Transform: reverse on Orientation<0
            if lock_textures:
                if poly.origin is not None:
                    poly.origin = tuple(float(c) for c in apply_point(poly.origin))   # a POINT → L
                if poly.texture_u is not None:
                    poly.texture_u = apply_dir(poly.texture_u)                         # covector
                if poly.texture_v is not None:
                    poly.texture_v = apply_dir(poly.texture_v)
            poly.normal = None                        # winding defines the face; editor recomputes

    # PrePivot' = L·PrePivot (rewritten, per spike §2 — apply-transform's explicit intent).
    if pp != (_ZERO, _ZERO, _ZERO):
        ppw = apply_point(pp)
        out.props = [(k, v) for k, v in out.props if k != "PrePivot"]
        _reset_rotation(out)
        # Written even when the transform maps the pivot to (0,0,0) (a degenerate/zero-scale L).
        # Dropping the property does NOT mean "no pre-pivot": an omitted property re-imports as
        # the CLASS DEFAULT, and 17 actor classes default `PrePivot` non-zero — so the actor whose
        # pivot we just baked to the origin would come back offset by the class's own pivot
        # (2026-07-25, same shape as the `Rotation`/`Location` omissions).
        from .emit import fmt_loc
        out.props.append(
            ("PrePivot", f"(X={fmt_loc(ppw[0])},Y={fmt_loc(ppw[1])},Z={fmt_loc(ppw[2])})"))
    else:
        _reset_rotation(out)

    out.main_scale = IDENTITY
    out.post_scale = IDENTITY
    return out
