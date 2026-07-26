#!/usr/bin/env python3
"""A pure-Python reference model of UnrealEd 2.2's `POLY TEXALIGN <mode>`, as measured.

`frame(mode, ...)` returns the `(base, TextureU, TextureV, Pan)` the editor produces for one
selected BSP surface, in WORLD space, given:

  n_surf   the BSP SURFACE normal — for a subtractive brush this is the REVERSE of the brush
           polygon's outward normal (CSG flips a subtractive brush's polys), i.e. it points into
           the empty space the surface is seen from;
  n_poly   the master brush polygon's own outward normal (what `FPoly::Finalize` recomputes from
           the polygon winding);
  verts    the master brush polygon's vertices, world space, in winding order;
  base/tu/tv/pan   the surface's CURRENT world frame (only WALLPAN reads it);
  vsize    the bound texture's VSize in texels (only CLAMP reads it).

Returns None when the mode leaves the surface untouched.
"""
from __future__ import annotations

import math

AXIS = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]

# .rdata constants of UEditorEngine::polyTexAlign (Editor.dll): the two guard thresholds.
THRESH_AXIS = 0.05        # |N[axis]| must EXCEED this for FLOOR / WALLX / WALLY
THRESH_WALL = 0.95        # |N.Z| must be BELOW this for WALLDIR / WALLPAN

# ETexAlign values, from the exec parser (Editor.dll 0x68984..0x68aff)
ETEXALIGN = {"DEFAULT": 0, "FLOOR": 1, "WALLDIR": 2, "WALLPAN": 3, "ONETILE": 4,
             "WALLCOLUMN": 5, "WALLX": 6, "WALLY": 7, "CLAMP": 8}

# mode -> (anchor axis, U source axis, V source axis) for the three ORTHOGRAPHIC-PROJECTION modes
PROJECTED = {"FLOOR": (2, 0, 1), "WALLX": (0, 1, 2), "WALLY": (1, 0, 2)}


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    m = math.sqrt(_dot(a, a))
    return _mul(a, 1.0 / m) if m > 1e-12 else a


def _winding_frame(n_poly, verts):
    """`FPoly::Finalize`'s generated texture frame: U from the first non-degenerate
    (Vertex[0] - Vertex[i]) x Normal, V = Normal x U."""
    for i in range(1, len(verts)):
        u = _cross(_sub(verts[0], verts[i]), n_poly)
        if _dot(u, u) > 1e-9:
            u = _unit(u)
            v = _unit(_cross(n_poly, u))
            if _dot(u, u) > 0.001 and _dot(v, v) > 0.001:
                return u, v
    raise ValueError("degenerate polygon")


def frame(mode, n_surf, n_poly, verts, base, tu, tv, pan, vsize):
    mode = mode.upper()
    if mode in ("ONETILE", "WALLCOLUMN", "NONE"):
        return None                                     # no alignment at all in UED22

    if mode in ("DEFAULT", "CLAMP"):
        u, v = _winding_frame(n_poly, verts)
        return base, u, v, (0, (vsize - 1) if mode == "CLAMP" else 0)

    if mode in PROJECTED:
        a, iu, iv = PROJECTED[mode]
        if abs(n_surf[a]) <= THRESH_AXIS:
            return None
        # ANY point of the plane serves; take a VERTEX rather than `base`. The surface's stored
        # Origin is normally in-plane, but nothing enforces it — an authored or hand-edited frame can
        # sit off the face's plane, and using it would silently place the anchor on the wrong plane.
        d = _dot(verts[0], n_surf)
        nb = [0.0, 0.0, 0.0]
        nb[a] = d / n_surf[a]
        au, av = AXIS[iu], AXIS[iv]
        u = _mul(_sub(au, _mul(n_surf, _dot(n_surf, au))), -1.0)
        v = _mul(_sub(av, _mul(n_surf, _dot(n_surf, av))), -1.0)
        return (nb[0], nb[1], nb[2]), u, v, (0, 0)

    if mode == "WALLDIR":
        if abs(n_surf[2]) >= THRESH_WALL:
            return None
        u = _unit((n_surf[1], -n_surf[0], 0.0))
        v = _unit(_cross(u, n_surf))
        if v[2] > 0.0:
            u, v = _mul(u, -1.0), _mul(v, -1.0)
        return base, u, v, (0, 0)

    if mode == "WALLPAN":
        if abs(n_surf[2]) >= THRESH_WALL or abs(tv[2]) <= THRESH_AXIS:
            return None
        return _add(base, _mul(tv, -base[2] / tv[2])), tu, tv, pan

    raise ValueError(f"unknown mode {mode!r}")
