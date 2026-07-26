#!/usr/bin/env python3
"""SPIKE — render what each specified surface operation DOES, before any of it is built.

The verbs in `specs/2026-07-26-poly-surface-verbs.md` do not exist yet, so this computes each frame
straight from the spec's rules and renders the resulting texture mapping. Every face is drawn
STRAIGHT-ON (viewed down its own normal), so the face outline is undistorted and anything you see
bent, stretched, sheared or mirrored comes purely from the texture frame.

The test texture is deliberately orientable: an F (so rotation and mirroring are unmistakable), a
grid (so stretch and shear are measurable by eye), a RED top edge and a BLUE left edge.

    uv_preview.py --out-dir DIR
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

W = H = 256                                  # texture size, texels


# ----------------------------------------------------------------- the test texture
def make_texture() -> Image.Image:
    im = Image.new("RGB", (W, H), "#f2efe9")
    d = ImageDraw.Draw(im)
    for i in range(0, W, 32):                                  # grid
        d.line([(i, 0), (i, H)], fill="#c9c2b6", width=1)
        d.line([(0, i), (W, i)], fill="#c9c2b6", width=1)
    d.rectangle([0, 0, W - 1, 10], fill="#d0453b")             # TOP edge = red
    d.rectangle([0, 0, 10, H - 1], fill="#2f6fb0")             # LEFT edge = blue
    d.rectangle([56, 40, 84, 216], fill="#1d2228")             # the F: stem
    d.rectangle([56, 40, 190, 68], fill="#1d2228")             # upper arm
    d.rectangle([56, 116, 156, 142], fill="#1d2228")           # middle arm
    return im


TEX = make_texture()
PX = TEX.load()


# ----------------------------------------------------------------- small vector helpers
def sub(a, b): return tuple(a[i] - b[i] for i in range(3))
def add(a, b): return tuple(a[i] + b[i] for i in range(3))
def mul(a, s): return tuple(c * s for c in a)
def dot(a, b): return sum(a[i] * b[i] for i in range(3))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def norm(a): return math.sqrt(dot(a, a))
def unit(a):
    m = norm(a)
    return tuple(c / m for c in a)


def face_normal(vs):
    """Newell — the same rule `preview._face_normal` uses."""
    n = [0.0, 0.0, 0.0]
    for i in range(len(vs)):
        a, b = vs[i], vs[(i + 1) % len(vs)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return unit(tuple(n))


def proj(B, N):
    """The editor's projection — deliberately NOT renormalised (spec §2.3)."""
    return sub(B, mul(N, dot(N, B)))


AXES = [(1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0)]
# spec §2.3: FLOOR drops Z (U<-X, V<-Y); WALLX drops X (U<-Y, V<-Z); WALLY drops Y (U<-X, V<-Z)
PROJECTED = {2: (0, 1), 0: (1, 2), 1: (0, 2)}


# ----------------------------------------------------------------- the specified frames
def frame_projection(vs, axis):
    """`align floor` (axis=2) / `align wall` (axis=0 or 1) — spec §2.3."""
    N = face_normal(vs)
    iu, iv = PROJECTED[axis]
    TU = mul(proj(AXES[iu], N), -1.0)
    TV = mul(proj(AXES[iv], N), -1.0)
    d = dot(N, vs[0])
    O = [0.0, 0.0, 0.0]
    O[axis] = d / N[axis]
    return tuple(O), TU, TV


def wall_axis(N):
    """spec §2.3 — larger |N.A| of X/Y, ties to the lower index."""
    return 0 if abs(N[0]) >= abs(N[1]) else 1


def frame_one_tile(vs, orthogonalise: bool):
    """`align one-tile` — spec §2.6. Direction from the projection family; density fit to the face.

    `orthogonalise=False` is the ruling as originally worded ("normalised"), which leaves a SKEWED
    pair; True is the corrected form: keep V for the up-vector and Gram-Schmidt U against it
    (U = normalize(U - V(U.V))). NOT U = V x N, which picks its own sign and mirrors the image."""
    N = face_normal(vs)
    axis = max(range(3), key=lambda i: (abs(N[i]), -i))
    iu, iv = PROJECTED[axis]
    u_dir = unit(mul(proj(AXES[iu], N), -1.0))
    v_dir = unit(mul(proj(AXES[iv], N), -1.0))
    if orthogonalise:
        # Gram-Schmidt U against V: removes the skew while staying on the SAME side as the
        # original U, so the orientation the projection family chose is preserved (a bare
        # cross product picks a sign of its own and mirrors the image).
        u_dir = unit(sub(u_dir, mul(v_dir, dot(u_dir, v_dir))))
    us = [dot(v, u_dir) for v in vs]
    vsx = [dot(v, v_dir) for v in vs]
    eu, ev = max(us) - min(us), max(vsx) - min(vsx)
    TU, TV = mul(u_dir, W / eu), mul(v_dir, H / ev)
    O = add(mul(u_dir, min(us)), mul(v_dir, min(vsx)))
    O = add(O, mul(N, dot(N, vs[0])))            # put the anchor on the face plane
    return O, TU, TV


def recentre(vs, O, TU, TV, TU2, TV2):
    """Re-anchor so the centroid keeps its (U,V) — spec §3 of the step-1 plan."""
    C = tuple(sum(v[i] for v in vs) / len(vs) for i in range(3))
    D = sub(C, O)
    u, v = dot(D, TU), dot(D, TV)
    # solve D' with D'.TU2 = u and D'.TV2 = v, in the plane
    N = face_normal(vs)
    g11, g12, g22 = dot(TU2, TU2), dot(TU2, TV2), dot(TV2, TV2)
    det = g11 * g22 - g12 * g12
    a = (u * g22 - v * g12) / det
    b = (v * g11 - u * g12) / det
    D2 = add(mul(TU2, a), mul(TV2, b))
    return sub(C, D2)


def frame_rotate(vs, base, quarter_turns=1):
    """`poly rotate --by 16384*k` — U' = n x U, applied k times, centroid preserved."""
    N = face_normal(vs)
    O, TU, TV = base
    TU2, TV2 = TU, TV
    for _ in range(quarter_turns % 4):
        TU2, TV2 = cross(N, TU2), cross(N, TV2)
    return recentre(vs, O, TU, TV, TU2, TV2), TU2, TV2


def frame_scale(vs, base, fu, fv):
    """`poly scale --by fu,fv` — apparent size x f, so magnitudes DIVIDE. Centroid preserved."""
    O, TU, TV = base
    TU2, TV2 = mul(TU, 1.0 / fu), mul(TV, 1.0 / fv)
    return recentre(vs, O, TU, TV, TU2, TV2), TU2, TV2


# ----------------------------------------------------------------- render one face straight-on
def render(vs, frame, size=300, pad=26, bg="#12151a"):
    N = face_normal(vs)
    e1 = unit(sub(vs[1], vs[0]))
    e2 = unit(cross(N, e1))
    pts = [(dot(v, e1), dot(v, e2)) for v in vs]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    spanx, spany = max(xs) - min(xs), max(ys) - min(ys)
    s = (size - 2 * pad) / max(spanx, spany)
    O, TU, TV = frame
    img = Image.new("RGB", (size, size), bg)
    ip = img.load()

    def inside(px, py):
        c = False
        for i in range(len(pts)):
            x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % len(pts)]
            if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
                c = not c
        return c

    for sy in range(size):
        for sx in range(size):
            wx = (sx - pad) / s + min(xs)
            wy = (max(ys) - (sy - pad) / s)
            if not inside(wx, wy):
                continue
            P = add(add(mul(e1, wx), mul(e2, wy)), mul(N, dot(N, vs[0])))
            u = int(dot(sub(P, O), TU)) % W
            v = int(dot(sub(P, O), TV)) % H
            ip[sx, sy] = PX[u, v]
    ImageDraw.Draw(img).polygon([(pad + (x - min(xs)) * s, pad + (max(ys) - y) * s)
                                 for x, y in pts], outline="#5d6b7a")
    return img


# ----------------------------------------------------------------- the scenarios
def quad(*pts): return list(pts)


SCENARIOS = []


def scene(key, title, note, vs, frame):
    SCENARIOS.append((key, title, note, vs, frame))


def build():
    # 1. floor, flat
    f = quad((0,0,0), (256,0,0), (256,256,0), (0,256,0))
    scene("floor-flat", "align floor — flat +Z face",
          "Baseline. 1 texel/uu, grid square, F upright.", f, frame_projection(f, 2))

    # 2. floor, 45-degree ramp -> the |proj| stretch
    r = quad((0,0,0), (256,0,0), (256,256,256), (0,256,256))
    scene("floor-ramp", "align floor — 45° ramp",
          "Projected DOWN Z onto a tilted face, so the texture stretches along the slope by "
          "1/|proj| = 1.41x. This is the editor's behaviour and it is why a ramp stays continuous "
          "with the floor it meets.", r, frame_projection(r, 2))

    # 3. wall +Y
    wy = quad((0,0,0), (256,0,0), (256,0,256), (0,0,256))
    scene("wall-front", "align wall — face pointing −Y",
          "V runs DOWNWARD (TextureV = −proj(Ẑ)), so a texture authored top-row-first renders "
          "upright. Note the red TOP edge is at the top.", wy, frame_projection(wy, wall_axis(face_normal(wy))))

    # 4. the same wall's back face -> mirroring
    wb = quad((0,0,0), (0,0,256), (256,0,256), (256,0,0))
    scene("wall-back", "align wall — the SAME plane, facing +Y",
          "Byte-identical frame to the one on its left — and because you are looking at it from the "
          "other side, it reads MIRRORED (the F is flipped, blue edge now right). The editor's "
          "family is polarity-blind by design; this is what deleting the co-orientation guard means.",
          wb, frame_projection(wb, wall_axis(face_normal(wb))))

    # 5. one-tile on a rectangle
    rect = quad((0,0,0), (192,0,0), (192,0,128), (0,0,128))
    scene("onetile-rect", "align one-tile — rectangular face",
          "Exactly one tile spans the face, stretched non-uniformly to fill it. 192×128 uu face, "
          "256×256 texture: the F is squashed horizontally, which is intended.",
          rect, frame_one_tile(rect, True))

    # 6/7. one-tile on a corner face: normalised (skewed) vs orthogonalised
    corner = [(256,0,0), (0,256,0), (0,0,256)]        # N = (1,1,1)/sqrt3 — all three components non-zero
    scene("onetile-skew", "one-tile on a corner face — NORMALISED (the ruling as worded)",
          "The two projected axes are 120° apart, so normalising leaves them SKEWED: the F leans and "
          "the grid is a rhombus. This is the defect all three reviewers found.",
          corner, frame_one_tile(corner, False))
    scene("onetile-ortho", "one-tile on a corner face — ORTHOGONALISED (adopted)",
          "Keep V for the up-vector and Gram-Schmidt U against it. Square grid, and the predictable "
          "up-vector the ruling was for is preserved.",
          corner, frame_one_tile(corner, True))

    # 8. one-tile on a triangle -> bounding box
    tri = [(0,0,0), (256,0,0), (0,0,192)]
    scene("onetile-tri", "align one-tile — triangular face",
          "One tile covers the face's BOUNDING BOX, so a triangle shows only part of the texture. "
          "Documented behaviour, not a bug.", tri, frame_one_tile(tri, True))

    # 9. rotate quarter turn
    base = frame_projection(f, 2)
    scene("rotate-90", "poly rotate --by 16384 (90°)",
          "Exact component swap, no trig: TextureU=+X,V=+Y becomes U=+Y,V=−X. The image turns WITH "
          "the frame, and the face centroid keeps its (U,V) so the texture spins in place.",
          f, frame_rotate(f, base, 1))

    # 10. scale --by 2,2
    scene("scale-2x", "poly scale --by 2,2",
          "The texture looks TWICE AS BIG, which DIVIDES the stored magnitudes. Named for what the "
          "author sees, not for what is stored.", f, frame_scale(f, base, 2.0, 2.0))

    # 11. scale non-uniform
    scene("scale-21", "poly scale --by 2,1",
          "Non-uniform. U doubles, V unchanged — and the centroid still holds its (U,V), which is "
          "what the Gram solve in the plan exists to guarantee on a skewed frame.",
          f, frame_scale(f, base, 2.0, 1.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    build()
    TEX.save(out / "_texture.png")
    for key, title, _note, vs, frame in SCENARIOS:
        render(vs, frame).save(out / f"{key}.png")
        print(f"  {key}: {title}")
    print(f"wrote {len(SCENARIOS)} scenarios + the test texture to {out}")


if __name__ == "__main__":
    main()
