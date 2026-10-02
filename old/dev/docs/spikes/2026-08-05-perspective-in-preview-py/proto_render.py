"""Prototype: PERSPECTIVE rasterizer in pure Python, grafted onto preview.py's machinery.

Purpose (spike 2026-08-05-perspective-in-preview-py): prove that a posed perspective camera
+ SHOT grammar fits preview.py's ORTHO even-odd affine scanline rasterizer, and measure the
pure-Python wall-time. Ported from uedcli-native/src/render.rs.

Key idea being tested: under a perspective projection, `1/d`, `u/d`, `v/d` are AFFINE in
screen space on a planar face (exactly what makes perspective-correct interpolation work).
So preview.py's `_affine_on_plane` + even-odd scanline (`_fill_face*`) can be reused verbatim
for the SCREEN-SPACE gradients; the only genuinely new pieces are (a) a camera-space
transform, (b) a near-plane Sutherland-Hodgman clip preview.py has no analog for, and
(c) ONE per-pixel divide (`u = (u/d)/(1/d)`) added to the inner fill loop.

Consumes the SAME `(polys, textures)` that `preview_native.build_scene` feeds the Rust
`render_frame`, so the Rust output is an exact apples-to-apples oracle.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

# Repo root, so `from uedcli.preview import ...` works when run from the committed location.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Reuse preview.py's affine solver unchanged — the load-bearing "reuse" claim.
from uedcli.preview import _affine_on_plane

BACKGROUND = (56, 56, 60)     # render.rs BACKGROUND
DEFAULT_GREY = (128, 128, 128)
NEAR = 4.0                    # render.rs NEAR
KEY_LIGHT = (-0.408, -0.577, 0.707)   # render.rs KEY_LIGHT


def _newell(verts):
    nx = ny = nz = 0.0
    n = len(verts)
    for i in range(n):
        ax, ay, az = verts[i]
        bx, by, bz = verts[(i + 1) % n]
        nx += (ay - by) * (az + bz)
        ny += (az - bz) * (ax + bx)
        nz += (ax - bx) * (ay + by)
    return (nx, ny, nz)


def _clip_near(poly):
    """Sutherland-Hodgman against d >= NEAR. `poly` is a list of (d, r, u, tu, tv)."""
    out = []
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        a_in = a[0] >= NEAR
        b_in = b[0] >= NEAR
        if a_in:
            out.append(a)
        if a_in != b_in:
            t = (NEAR - a[0]) / (b[0] - a[0])
            out.append((NEAR,
                        a[1] + t * (b[1] - a[1]),
                        a[2] + t * (b[2] - a[2]),
                        a[3] + t * (b[3] - a[3]),
                        a[4] + t * (b[4] - a[4])))
    return out


def _solve_affine(scr, vals):
    """Affine map `f = a*x + b*y + c` fitting all screen verts `scr` (each an (x,y)) with
    per-vertex `vals`. Uses preview.py `_affine_on_plane`; picks a non-degenerate vertex triple
    (a face may have near-collinear leading verts after clipping)."""
    n = len(scr)
    (x0, y0) = scr[0]
    for j in range(1, n - 1):
        for k in range(j + 1, n):
            ux, uy = scr[j][0] - x0, scr[j][1] - y0
            vx, vy = scr[k][0] - x0, scr[k][1] - y0
            det = ux * vy - vx * uy
            if abs(det) > 1e-9:
                return _affine_on_plane(vals[0], vals[j], vals[k],
                                        x0, y0, ux, uy, vx, vy, det)
    return None


def _fill(img, zbuf, w, h, scr, aff_inv, aff_u, aff_v, tex, shade):
    """Even-odd scanline fill (preview.py `_fill_face_textured` structure) with the perspective
    divide added. `zbuf` stores 1/d (larger = nearer). Per pixel: inv = aff_inv(x,y);
    u = aff_u(x,y)/inv; v = aff_v(x,y)/inv."""
    ai_a, ai_b, ai_c = aff_inv
    au_a, au_b, au_c = aff_u
    av_a, av_b, av_c = aff_v
    if tex is not None:
        tw, th, tdata = tex
    ys = [p[1] for p in scr]
    n = len(scr)
    y_lo = max(0, math.ceil(min(ys) - 0.5))
    y_hi = min(h - 1, math.floor(max(ys) - 0.5))
    for y in range(y_lo, y_hi + 1):
        yc = y + 0.5
        xs = []
        for i in range(n):
            ax, ay = scr[i]
            bx, by = scr[(i + 1) % n]
            if (ay <= yc) != (by <= yc):
                xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        xs.sort()
        row_inv = ai_b * yc + ai_c
        row_u = au_b * yc + au_c
        row_v = av_b * yc + av_c
        base = y * w
        for kk in range(0, len(xs) - 1, 2):
            x_lo = max(0, math.ceil(xs[kk] - 0.5))
            x_hi = min(w - 1, math.floor(xs[kk + 1] - 0.5))
            for x in range(x_lo, x_hi + 1):
                xc = x + 0.5
                inv = ai_a * xc + row_inv
                pi = base + x
                if inv <= zbuf[pi]:
                    continue
                zbuf[pi] = inv
                if tex is not None:
                    u = (au_a * xc + row_u) / inv
                    v = (av_a * xc + row_v) / inv
                    tx = int(math.floor(u)) % tw
                    ty = int(math.floor(v)) % th
                    ti = (ty * tw + tx) * 3
                    rr = tdata[ti]; gg = tdata[ti + 1]; bb = tdata[ti + 2]
                else:
                    rr, gg, bb = DEFAULT_GREY
                o = pi * 3
                img[o] = min(int(rr * shade), 255)
                img[o + 1] = min(int(gg * shade), 255)
                img[o + 2] = min(int(bb * shade), 255)


def render(polys, textures, camera, width, height):
    """`polys`/`textures` are exactly `preview_native.build_scene`'s output shape; `camera` is
    `(location, forward, right, up, fov_deg)`. Returns a `bytearray` RGB buffer (w*h*3)."""
    w, h = int(width), int(height)
    img = bytearray(bytes(BACKGROUND) * (w * h))
    zbuf = [0.0] * (w * h)     # 1/d; 0 = background
    loc, fwd, right, up, fov = camera
    lx, ly, lz = loc
    fx, fy, fz = fwd
    rx, ry, rz = right
    ux, uy, uz = up
    half_w = w / 2.0
    half_h = h / 2.0
    focal = half_w / math.tan(math.radians(fov) / 2.0)

    for (verts_flat, base_w, tu_ax, tv_ax, pan, tex_index) in polys:
        verts = [(verts_flat[i], verts_flat[i + 1], verts_flat[i + 2])
                 for i in range(0, len(verts_flat), 3)]
        if len(verts) < 3:
            continue
        nx, ny, nz = _newell(verts)
        nlen = math.sqrt(nx * nx + ny * ny + nz * nz)
        if nlen <= 1e-12:
            continue
        dot = nx * KEY_LIGHT[0] + ny * KEY_LIGHT[1] + nz * KEY_LIGHT[2]
        shade = 0.55 + 0.45 * abs(dot) / nlen

        bwx, bwy, bwz = base_w
        tux, tuy, tuz = tu_ax
        tvx, tvy, tvz = tv_ax
        pu, pv = pan
        cam = []
        for (px, py, pz) in verts:
            rlx, rly, rlz = px - lx, py - ly, pz - lz
            dpx, dpy, dpz = px - bwx, py - bwy, pz - bwz
            cam.append((rlx * fx + rly * fy + rlz * fz,   # d
                        rlx * rx + rly * ry + rlz * rz,   # r
                        rlx * ux + rly * uy + rlz * uz,   # u
                        dpx * tux + dpy * tuy + dpz * tuz + pu,   # tu
                        dpx * tvx + dpy * tvy + dpz * tvz + pv))  # tv
        clipped = _clip_near(cam)
        if len(clipped) < 3:
            continue

        scr = []
        q_inv = []
        q_u = []
        q_v = []
        for (d, r, u, tu, tv) in clipped:
            inv = 1.0 / d
            scr.append((half_w + r * focal * inv, half_h - u * focal * inv))
            q_inv.append(inv)
            q_u.append(tu * inv)
            q_v.append(tv * inv)
        aff_inv = _solve_affine(scr, q_inv)
        if aff_inv is None:
            continue
        tex = None
        if 0 <= tex_index < len(textures):
            tw, th, tdata = textures[tex_index]
            tex = (tw, th, tdata)
            aff_u = _solve_affine(scr, q_u)
            aff_v = _solve_affine(scr, q_v)
            if aff_u is None or aff_v is None:
                tex = None
        if tex is None:
            aff_u = aff_v = (0.0, 0.0, 0.0)
        _fill(img, zbuf, w, h, scr, aff_inv, aff_u, aff_v, tex, shade)
    return bytes(img)
