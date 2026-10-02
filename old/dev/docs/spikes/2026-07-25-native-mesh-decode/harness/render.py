"""Render a natively-decoded mesh to a PNG — the spike's proof that the decode is not just
structurally sound but *usable* for catalog thumbnails, with no editor, no container, no umodel.

Pipeline: parse the mesh body (`umesh.py`) -> take animation frame 0 -> build triangles from
Faces -> Wedges -> Verts -> resolve each material's skin through uedcli's own `utexture` decoder ->
rasterize with a z-buffer and affine UV mapping + Lambert shading.

Usage:
    python render.py <pkg.u> <MeshName> [--out X.png] [--size 512] [--yaw 45] [--pitch 20]
                     [--flat] [--search DIR[:DIR...]]
"""
from __future__ import annotations

import math
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
from uedcli.upackage import load_package  # noqa: E402
from uedcli import utexture  # noqa: E402
import umesh  # noqa: E402

from PIL import Image  # noqa: E402


def arg(argv, flag, default=None, cast=str):
    return cast(argv[argv.index(flag) + 1]) if flag in argv else default


def frame_triangles(m, frame=0):
    """Triangles for one animation frame as (v0, v1, v2, uv0, uv1, uv2, material_index).

    A `ULodMesh`'s renderable geometry is in Faces/Wedges (its `Tris` array is empty) — Faces index
    Wedges, Wedges index Verts and carry the UV. `Verts` holds every frame back-to-back, so frame
    `f` starts at `f * FrameVerts`.

    CRITICAL: each frame begins with `SpecialVerts` attachment vertices that are NOT part of the
    model, so a wedge's `iVertex` is relative to `frame_base + SpecialVerts`. Omitting that shift
    silently renders a shredded mess for every mesh with attachments (`DeusExCharacters.GM_Trench`
    has 3; a static decoration has 0, which is why decorations look correct either way).
    """
    base = frame * m.frame_verts + m.special_verts
    tris = []
    if m.faces:
        for (iw, mat) in m.faces:
            try:
                w = [m.wedges[i] for i in iw]
            except IndexError:
                continue
            vs, uvs = [], []
            for (iv, u, v) in w:
                k = base + iv
                if k >= len(m.verts):
                    break
                vs.append(m.verts[k])
                uvs.append((u, v))
            if len(vs) == 3:
                tris.append((vs[0], vs[1], vs[2], uvs[0], uvs[1], uvs[2], mat))
    else:                                        # plain UMesh: geometry lives in Tris
        for (iv, uv, _flags, tex) in m.tris:
            vs = [m.verts[base + i] for i in iv if base + i < len(m.verts)]
            if len(vs) == 3:
                tris.append((vs[0], vs[1], vs[2],
                             (uv[0], uv[1]), (uv[2], uv[3]), (uv[4], uv[5]), tex))
    return tris


def skin_images(pkg, m, search_dirs):
    """material index -> (w, h, rgb bytes), resolved through uedcli's texture decoder.

    `Materials[i].TextureIndex` indexes the mesh's own `Textures` array, whose entries are package
    object refs; `object_path` turns each into the `Package.Name` ref the resolver takes.
    """
    files = []
    for d in search_dirs:
        if os.path.isdir(d):
            files += [os.path.join(d, f) for f in os.listdir(d)
                      if f.lower().endswith((".utx", ".u", ".dx", ".unr"))]
    resolver = utexture.TextureResolver(files)
    out = {}
    mats = m.materials or [(0, i) for i in range(max(1, len(m.textures)))]
    for mi, (_flags, tex_idx) in enumerate(mats):
        if not (0 <= tex_idx < len(m.textures)):
            continue
        path = pkg.object_path(m.textures[tex_idx])
        if not path:
            continue
        parts = path.split(".")
        ref = f"{parts[0]}.{parts[-1]}"          # Package.Name (drop any Group segment)
        got = resolver.resolve(ref)
        # `resolve` returns a TYPED result and its error object is TRUTHY, so `if got:` would
        # accept an error as a skin and rasterize it. Fail loudly naming the offending ref.
        if isinstance(got, utexture.TextureError):
            raise SystemExit(f"{m.name}: skin {ref} did not decode [{got.case}]: {got.detail}")
        out[mi] = (got.width, got.height, got.rgb)
    return out


def render(m, pkg, *, size=512, yaw=45.0, pitch=20.0, flat=False, search_dirs=()):
    tris = frame_triangles(m)
    if not tris:
        raise SystemExit(f"{m.name}: no triangles (verts={len(m.verts)} faces={len(m.faces)})")
    sx, sy, sz = m.scale if any(m.scale) else (1.0, 1.0, 1.0)

    cy, sy_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))

    def view(v):
        # UE1 is X forward, Y right, Z up; scale, yaw about Z, then pitch, into a Y-down raster.
        x, y, z = v[0] * sx, v[1] * sy, v[2] * sz
        x, y = x * cy - y * sy_, x * sy_ + y * cy
        y, z = y * cp - z * sp, y * sp + z * cp
        return (x, -z, y)                          # screen x, screen y (down), depth

    pts = [view(v) for t in tris for v in t[:3]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    k = (size * 0.86) / span
    ox = size / 2 - (min(xs) + max(xs)) / 2 * k
    oy = size / 2 - (min(ys) + max(ys)) / 2 * k

    W = H = size
    img = Image.new("RGB", (W, H), (26, 28, 32))
    px = img.load()
    zbuf = [1e30] * (W * H)
    skins = {} if flat else skin_images(pkg, m, search_dirs)
    light = (0.35, -0.5, 0.79)

    for (a, b, c, ua, ub, uc, mat) in tris:
        va, vb, vc = view(a), view(b), view(c)
        # face normal in view space, for Lambert shading + backface culling
        e1 = (vb[0] - va[0], vb[1] - va[1], vb[2] - va[2])
        e2 = (vc[0] - va[0], vc[1] - va[1], vc[2] - va[2])
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2],
             e1[0] * e2[1] - e1[1] * e2[0])
        nl = math.sqrt(sum(q * q for q in n)) or 1.0
        n = tuple(q / nl for q in n)
        lam = max(0.0, sum(n[i] * light[i] for i in range(3)))
        shade = 0.30 + 0.70 * lam

        p0 = (va[0] * k + ox, va[1] * k + oy, va[2])
        p1 = (vb[0] * k + ox, vb[1] * k + oy, vb[2])
        p2 = (vc[0] * k + ox, vc[1] * k + oy, vc[2])
        area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
        if abs(area) < 1e-9:
            continue
        skin = skins.get(mat)
        minx, maxx = max(0, int(min(p0[0], p1[0], p2[0]))), min(W - 1, int(max(p0[0], p1[0], p2[0])) + 1)
        miny, maxy = max(0, int(min(p0[1], p1[1], p2[1]))), min(H - 1, int(max(p0[1], p1[1], p2[1])) + 1)
        for Y in range(miny, maxy + 1):
            for X in range(minx, maxx + 1):
                fx, fy = X + 0.5, Y + 0.5
                w0 = ((p1[0] - p0[0]) * (fy - p0[1]) - (fx - p0[0]) * (p1[1] - p0[1])) / area
                w1 = ((fx - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (fy - p0[1])) / area
                w2 = 1.0 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                depth = w2 * p0[2] + w1 * p1[2] + w0 * p2[2]
                idx = Y * W + X
                if depth >= zbuf[idx]:
                    continue
                zbuf[idx] = depth
                if skin:
                    tw, th, rgb = skin
                    u = (w2 * ua[0] + w1 * ub[0] + w0 * uc[0]) * tw / 256.0
                    v = (w2 * ua[1] + w1 * ub[1] + w0 * uc[1]) * th / 256.0
                    tu, tv = int(u) % tw, int(v) % th
                    o = (tv * tw + tu) * 3
                    col = (rgb[o], rgb[o + 1], rgb[o + 2])
                else:
                    col = (170, 172, 178)
                px[X, Y] = (min(255, int(col[0] * shade)), min(255, int(col[1] * shade)),
                            min(255, int(col[2] * shade)))
    return img, len(tris), len(skins)


def main(argv):
    path, name = argv[1], argv[2]
    pkg = load_package(path)
    j = next((j for j in umesh.mesh_exports(pkg)
              if pkg.names[pkg.exports[j]["nm"]].lower() == name.lower()), None)
    if j is None:
        raise SystemExit(f"no mesh named {name} in {path}")
    m = umesh.parse_mesh(pkg, j)
    search = arg(argv, "--search", os.path.join(os.path.dirname(path), "..", "Textures"))
    dirs = [d for d in search.split(":")] + [os.path.dirname(path)]
    img, ntris, nskins = render(
        m, pkg,
        size=arg(argv, "--size", 512, int), yaw=arg(argv, "--yaw", 45.0, float),
        pitch=arg(argv, "--pitch", 20.0, float), flat="--flat" in argv, search_dirs=dirs)
    out = arg(argv, "--out", f"{name}.png")
    img.save(out)
    print(f"{name}: verts={len(m.verts)} frameverts={m.frame_verts} frames={m.anim_frames} "
          f"tris={ntris} wedges={len(m.wedges)} mats={len(m.materials)} skins_resolved={nskins} "
          f"scale={tuple(round(v, 4) for v in m.scale)} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
