"""Face math shared across modules: a face's outward normal from its winding, and where its authored
texture sits on it. Who reads what, today — `newell`: `preview.py`, `query.py`, `surface.py`,
`polyalign.py`; `world_uv_frame`: `preview_native.py` (the `level preview --native` backend) and
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

from .rotation import actor_matrix, actor_prepivot, matvec


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
    """The source poly's authored texture frame, transformed to world space:
    `base_w = Location + R·(Origin − PrePivot)`, `axes_w = R·axes`. Missing Origin → local
    zero; missing/zero axes → `tex_basis_default`."""
    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    pp = tuple(float(c) for c in actor_prepivot(actor))
    R = actor_matrix(actor)

    origin = tuple(float(c) for c in poly.origin) if poly.origin is not None else (0.0, 0.0, 0.0)
    rel = (origin[0] - pp[0], origin[1] - pp[1], origin[2] - pp[2])
    if R is not None:
        rel = matvec(R, rel)
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
    if R is not None:
        tu, tv = tuple(matvec(R, tu)), tuple(matvec(R, tv))
    pan = (float(poly.pan[0]), float(poly.pan[1])) if poly.pan else (0.0, 0.0)
    return base_w, tu, tv, pan
