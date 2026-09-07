"""The verified `Mesh`/`LodMesh` vertex-to-world placement formula, plus a literal transliteration
of the UE1 v200 `FCoords` machinery it was derived from — kept side by side so the closed form can
be checked against the engine's own operator sequence, not just hand algebra.

Source: `Source/Engine/Src/UnMesh.cpp` `UMesh::GetFrame` (`fgsfdsfgs/UE1`, the v200 retail tree —
same package lineage as Deus Ex, already this project's primary RE source for `UnSprite.cpp`/
`UnEdCam.cpp`, see `dev/docs/spikes/2026-07-21-unrealed-sprite-radii-rendering.md`):

```cpp
Coords = Coords * (Owner->Location + Owner->PrePivot) * Owner->Rotation * RotOrigin
                 * FScale(Scale * DrawScale, 0.0, SHEER_None);
...
*ResultVerts = (CachedVerts[i] - Origin).TransformPointBy(Coords);
```

`FCoords` (`UnMath.h`) is a world-to-frame basis (`Origin`, `XAxis`, `YAxis`, `ZAxis`); `TransformPointBy`
computes `((p - Origin)·XAxis, (p - Origin)·YAxis, (p - Origin)·ZAxis)`. Composing it with `*=` chains
"transform this frame by X" for `FVector` (translate), `FRotator` (three single-axis steps, each the
per-axis INVERSE-rotation matrix — the UE1 idiom used throughout the engine for building a world→view
matrix by walking outward from the camera through each parent's placement) and `FScale` (component-wise
axis scale + reciprocal origin scale, no proper matrix). Algebraically composing all four steps (see the
spike README's "Derivation") telescopes to a plain LOCAL-TO-WORLD affine map:

    world = Location + PrePivot + R · Ro · diag(Scale · DrawScale) · (v - Origin)

- `v`        — the raw mesh-local vertex (`FMeshVert`, decoded by `uedcli/umesh.py`)
- `Origin`   — the mesh's own `Origin` FVector (translation, subtracted first)
- `Scale`    — the mesh's own per-axis `Scale` FVector
- `DrawScale`— the ACTOR's uniform scalar `DrawScale` (multiplies all three axes alike)
- `Ro`       — rotation matrix for the mesh's own `RotOrigin` FRotator
- `R`        — rotation matrix for the ACTOR's `Rotation` FRotator
- `Location`, `PrePivot` — the actor's FVectors, added as a PLAIN WORLD-SPACE offset (UNROTATED —
  contrast `uedcli`'s brush/CSG convention `Location + R·(v - PrePivot)`, where PrePivot sits INSIDE
  the rotation; mesh rendering is a different call site with a different convention for the same field,
  confirmed against `AActor::ToWorld()` in `AActor.h`, which has no PrePivot term at all: `GMath.UnitCoords
  * Location * Rotation`. PrePivot is folded in per-consumer, not by a shared base method.)

`R`/`Ro` use the SAME FRotator→matrix convention as `uedcli/rotation.py`'s `euler_to_matrix_uu`
(`Rz(yaw)·Ry(pitch)·Rx(roll)`, pitch/roll sin-flipped) — verified by re-deriving each of `UnMath.h`'s
three per-axis `FCoords::operator*=(FRotator)` step matrices and finding them IDENTICAL to
`rotation._rx_uu`/`_ry_uu`/`_rz_uu` term-for-term (see the README). So this harness reuses
`rotation.euler_to_matrix_uu`/`matvec` directly rather than re-implementing rotation matrices.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))   # repo root, for `uedcli.rotation`

from uedcli.rotation import euler_to_matrix_uu, gmath_cos, gmath_sin, matvec  # noqa: E402

Vec3 = tuple[float, float, float]


def mesh_vertex_to_world(
    v: Vec3,
    *,
    mesh_scale: Vec3,
    mesh_origin: Vec3,
    mesh_rot_origin: tuple[int, int, int],
    actor_location: Vec3,
    actor_rotation_uu: tuple[int, int, int] = (0, 0, 0),
    actor_prepivot: Vec3 = (0.0, 0.0, 0.0),
    draw_scale: float = 1.0,
) -> Vec3:
    """The closed-form formula: `Location + PrePivot + R·Ro·diag(Scale·DrawScale)·(v - Origin)`."""
    r = euler_to_matrix_uu(*actor_rotation_uu)
    ro = euler_to_matrix_uu(*mesh_rot_origin)
    w = tuple((v[i] - mesh_origin[i]) * mesh_scale[i] * draw_scale for i in range(3))
    rotated = matvec(r, matvec(ro, w))
    return tuple(rotated[i] + actor_location[i] + actor_prepivot[i] for i in range(3))


# --------------------------------------------------------------------------------------------
# Literal transliteration of UE1's FCoords machinery (UnMath.h), used ONLY to cross-check the
# closed form above against the engine's actual operator sequence — not meant to be the "nice"
# API. Every function here mirrors one named C++ operator/method.
# --------------------------------------------------------------------------------------------

def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _identity_coords() -> dict:
    return {"origin": (0.0, 0.0, 0.0), "x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def _transform_point_by(p: Vec3, c: dict) -> Vec3:
    """`FVector::TransformPointBy`."""
    t = tuple(p[i] - c["origin"][i] for i in range(3))
    return (_dot(t, c["x"]), _dot(t, c["y"]), _dot(t, c["z"]))


def _transform_vector_by(v: Vec3, c: dict) -> Vec3:
    """`FVector::TransformVectorBy` — ignores Origin."""
    return (_dot(v, c["x"]), _dot(v, c["y"]), _dot(v, c["z"]))


def _coords_mul_coords(c: dict, s: dict) -> dict:
    """`FCoords::operator*=(const FCoords&)`."""
    return {
        "origin": _transform_point_by(c["origin"], s),
        "x": _transform_vector_by(c["x"], s),
        "y": _transform_vector_by(c["y"], s),
        "z": _transform_vector_by(c["z"], s),
    }


def _coords_mul_vector(c: dict, p: Vec3) -> dict:
    """`FCoords::operator*=(const FVector&)` — `Origin -= Point`."""
    return {**c, "origin": tuple(c["origin"][i] - p[i] for i in range(3))}


def _coords_mul_rotator(c: dict, pitch_uu: int, yaw_uu: int, roll_uu: int) -> dict:
    """`FCoords::operator*=(const FRotator&)` — yaw step, then pitch step, then roll step, each
    the per-axis matrix literally transcribed from `UnMath.h`."""
    cy, sy = gmath_cos(yaw_uu), gmath_sin(yaw_uu)
    c = _coords_mul_coords(c, {"origin": (0.0, 0.0, 0.0),
                                "x": (cy, sy, 0.0), "y": (-sy, cy, 0.0), "z": (0.0, 0.0, 1.0)})
    cp, sp = gmath_cos(pitch_uu), gmath_sin(pitch_uu)
    c = _coords_mul_coords(c, {"origin": (0.0, 0.0, 0.0),
                                "x": (cp, 0.0, sp), "y": (0.0, 1.0, 0.0), "z": (-sp, 0.0, cp)})
    cr, sr = gmath_cos(roll_uu), gmath_sin(roll_uu)
    c = _coords_mul_coords(c, {"origin": (0.0, 0.0, 0.0),
                                "x": (1.0, 0.0, 0.0), "y": (0.0, cr, -sr), "z": (0.0, sr, cr)})
    return c


def _coords_mul_scale(c: dict, scale_xyz: Vec3) -> dict:
    """`FCoords::operator*=(const FScale&)` with `SHEER_None` (the sheer sub-step is then a no-op
    identity multiply). Component-wise, NOT a matrix product — this is `UnMath.h`'s literal
    `XAxis *= Scale.Scale; ...; Origin.X /= Scale.Scale.X; ...`."""
    sx, sy, sz = scale_xyz
    return {
        "origin": (c["origin"][0] / sx, c["origin"][1] / sy, c["origin"][2] / sz),
        "x": (c["x"][0] * sx, c["x"][1] * sy, c["x"][2] * sz),
        "y": (c["y"][0] * sx, c["y"][1] * sy, c["y"][2] * sz),
        "z": (c["z"][0] * sx, c["z"][1] * sy, c["z"][2] * sz),
    }


def mesh_vertex_to_world_literal(
    v: Vec3,
    *,
    mesh_scale: Vec3,
    mesh_origin: Vec3,
    mesh_rot_origin: tuple[int, int, int],
    actor_location: Vec3,
    actor_rotation_uu: tuple[int, int, int] = (0, 0, 0),
    actor_prepivot: Vec3 = (0.0, 0.0, 0.0),
    draw_scale: float = 1.0,
) -> Vec3:
    """Line-for-line `UMesh::GetFrame`, with the camera `Coords` fixed at identity (isolating the
    object-placement part the closed form above claims to equal)."""
    c = _identity_coords()
    t1 = tuple(actor_location[i] + actor_prepivot[i] for i in range(3))
    c = _coords_mul_vector(c, t1)
    c = _coords_mul_rotator(c, *actor_rotation_uu)
    c = _coords_mul_rotator(c, *mesh_rot_origin)
    c = _coords_mul_scale(c, tuple(s * draw_scale for s in mesh_scale))
    w = tuple(v[i] - mesh_origin[i] for i in range(3))
    return _transform_point_by(w, c)
