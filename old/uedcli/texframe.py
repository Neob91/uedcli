"""Face math shared across modules: a face's outward normal from its winding, and where its authored
texture sits on it. Who reads what, today — `newell`: `preview.py`, `query.py`, `surface.py`,
`polyalign.py`; `world_uv_frame`: `preview_native.py` (the `level photo --native` backend) and
`polyalign.py` (the align verbs); `poly_flags_int`: `preview_native.py`.

A LEAF, on purpose: stdlib, `uedcli.rotation` and `uedcli.builders` only. `preview.py` needs
`newell` and must run with no Rust extension and no game install, which taking it from
`preview_native.py` would have cost it (that module imports `utexture` and `uedcli_native`). Two
tests in `tests/test_texframe.py` pin it.

The UV frame is the engine's own convention, carried with its evidence in `unrealed/t3d.md` "The UV
convention"; its missing/zero-axis fallback is board item
`de-containerization-follow-on-spec-items` spec §5 — "a Python default matching
`builders._tex_basis`".
"""
from __future__ import annotations

import math

from .rotation import (actor_linear, actor_main_scale, actor_post_scale, actor_prepivot, inverse,
                       matvec, transpose)


def poly_flags_int(raw: dict) -> int:
    """An actor's own `PolyFlags` prop as an int; absent or unparseable → 0."""
    try:
        return int(raw.get("PolyFlags", "0"))
    except ValueError:
        return 0


def tex_basis_default(normal):
    """`world_uv_frame`'s basis when a poly's authored `TextureU`/`TextureV` is missing or zero: unit
    in-plane axes seeded from the world axis least aligned with `normal`. Its one caller is
    `world_uv_frame` below. What the wrapper buys is the FUNCTION-LOCAL `builders` import: importing
    `texframe` loads 7 `uedcli` modules, and only calling this loads the other 3."""
    from .builders import _tex_basis
    return _tex_basis(normal)


def newell(verts) -> tuple[float, float, float]:
    """Outward normal via Newell's method — NOT normalized. Its magnitude is twice the face's area
    only when the face is PLANAR. `query.py` reports `poly list`'s area as `0.5·|newell|`, so a
    non-planar face (reachable via `--from-t3d`) under-reports its area there."""
    n = [0.0, 0.0, 0.0]
    for i in range(len(verts)):
        a, b = verts[i], verts[(i + 1) % len(verts)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return tuple(n)


def world_uv_frame(actor, poly):
    """The source poly's authored texture frame, transformed to world space by the actor's FULL linear
    map `L = PostScale·R·MainScale` (`rotation.actor_linear`): `base_w = Location + L·(Origin −
    PrePivot)` because `Origin` is a POINT, and `axes_w = (L⁻¹)ᵀ·axes` because `TextureU`/`TextureV`
    are COVECTORS (the covariant map keeps texel density fixed under scale/sheer — same inverse-
    transpose `transform.bake` uses). Missing Origin → local zero; missing/zero axes →
    `tex_basis_default`.

    UNSCALED PATH IS BYTE-IDENTICAL to the old rotation-only frame: `actor_linear` returns exactly the
    rotation matrix when there is no scale, and for a pure rotation the axes use `L` directly (not the
    covariant map) so `matvec(L, axis)` reproduces the old `R·axis` bit-for-bit — `(L⁻¹)ᵀ` only differs
    from `L` once scale/sheer is present."""
    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    pp = tuple(float(c) for c in actor_prepivot(actor))
    L = actor_linear(actor)                          # None (identity) or PostScale·R·MainScale
    scaled = not (actor_main_scale(actor).is_identity() and actor_post_scale(actor).is_identity())

    origin = tuple(float(c) for c in poly.origin) if poly.origin is not None else (0.0, 0.0, 0.0)
    rel = (origin[0] - pp[0], origin[1] - pp[1], origin[2] - pp[2])
    if L is not None:
        rel = matvec(L, rel)                         # Origin is a POINT → full linear map
    base_w = (loc[0] + rel[0], loc[1] + rel[1], loc[2] + rel[2])

    tu = tuple(float(c) for c in poly.texture_u) if poly.texture_u is not None else None
    tv = tuple(float(c) for c in poly.texture_v) if poly.texture_v is not None else None

    def _zero(v):
        return v is None or (abs(v[0]) + abs(v[1]) + abs(v[2])) < 1e-12

    if _zero(tu) or _zero(tv):
        n = tuple(float(c) for c in poly.normal) if poly.normal is not None \
            else newell([tuple(float(c) for c in v) for v in poly.vertices])
        size = math.sqrt(sum(c * c for c in n)) or 1.0
        tu, tv = tex_basis_default(tuple(c / size for c in n))
    if L is not None:
        # Covectors: `(L⁻¹)ᵀ` under scale/sheer, `L` for a pure rotation (byte-identical old path).
        if scaled:                                   # a zero/degenerate scale axis makes L non-invertible
            from .transform import reject_degenerate  # → exit 2 naming the brush, not a bare inverse() crash
            reject_degenerate(L, getattr(actor, "name", "?"))
        axes_map = transpose(inverse(L)) if scaled else L
        tu, tv = tuple(matvec(axes_map, tu)), tuple(matvec(axes_map, tv))
    pan = (float(poly.pan[0]), float(poly.pan[1])) if poly.pan else (0.0, 0.0)
    return base_w, tu, tv, pan
