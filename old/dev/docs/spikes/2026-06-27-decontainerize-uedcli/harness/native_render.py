"""Native (no-editor) textured render of a built `.dx`: parse the level `Model`, resolve
+ decode every surface texture natively, and rasterize a top-down ortho view with affine
UV texture mapping. Proves the editor's display role is natively replaceable with an
actual image — pure Python, no editor/engine.

Pipeline (all proven in sibling spikes): Model read (bspspike/umodel_parser) + texture
import-resolve (Spike 4) + native texture decode (Spike 1) + UV from FBspSurf vectors.

Usage:
    python native_render.py <map.dx> <install_textures_dir> <install_system_dir> <out.png> [PX]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "../../bspspike")
import umodel_parser as U
from package_rw import Pkg
from utexture_decode import (load_package, textures as tex_exports, decode_texture,
                             decode_palette, export_index_of_ref, mip0_to_rgb, write_png)


def _nm(p, i):
    return p.names[i][0].split(b"\x00", 1)[0].decode("latin-1")


def build_texture_cache(dx, texdir, sysdir):
    """surf.texture_ref -> (w,h,rgb-bytes) decoded natively, via the .dx import table."""
    p = Pkg(dx)

    def imp_pkg(j):
        cur = p.imports[j]
        for _ in range(64):
            cp, cn, pi, on = cur
            if pi == 0:
                return _nm(p, on)
            if pi < 0:
                cur = p.imports[-pi - 1]
            else:
                return None

    def locate(pkg):
        want = {(pkg + e).lower() for e in (".utx", ".u")}
        for d in (texdir, sysdir):
            try:
                for fn in os.listdir(d):
                    if fn.lower() in want:
                        return os.path.join(d, fn)
            except OSError:
                pass

    cache, pkgs = {}, {}
    for ref in set():
        pass
    return p, imp_pkg, locate, cache, pkgs


def decode_for_ref(p, imp_pkg, locate, pkgs, ref):
    if ref >= 0:
        return None
    j = -ref - 1
    pkg, tname = imp_pkg(j), _nm(p, p.imports[j][3])
    if not pkg:
        return None
    path = locate(pkg)
    if not path:
        return None
    if path not in pkgs:
        try:
            pkgs[path] = load_package(path)
        except Exception:
            pkgs[path] = None
    tp = pkgs[path]
    if tp is None:
        return None
    ti = next((i for i in tex_exports(tp)
               if tp.names[tp.exports[i]["nm"]].lower() == tname.lower()), None)
    if ti is None:
        return None
    t = decode_texture(tp, ti)
    if t.fmt != 0 or not t.mips:
        return None
    pal = decode_palette(tp, export_index_of_ref(tp, t.palette_ref))
    return (t.mips[0].width, t.mips[0].height, mip0_to_rgb(t.mips[0], pal))


def main(argv):
    dx, texdir, sysdir, out = argv[1], argv[2], argv[3], argv[4]
    PX = int(argv[5]) if len(argv) > 5 else 1200
    buf = open(dx, "rb").read()
    me = U.find_model_exports(dx)
    _exp, _name, _size, _off = me[0]
    m = U.parse_model_serial(buf, _off, _size)
    pts, vecs, verts, surfs, nodes = m.points, m.vectors, m.verts, m.surfs, m.nodes

    p, imp_pkg, locate, _c, pkgs = build_texture_cache(dx, texdir, sysdir)
    texcache = {}

    def tex_for(surf_ref):
        if surf_ref not in texcache:
            texcache[surf_ref] = decode_for_ref(p, imp_pkg, locate, pkgs, surf_ref)
        return texcache[surf_ref]

    # world bbox over points (x,y)
    xs = [pt[0] for pt in pts]; ys = [pt[1] for pt in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    scale = (PX - 4) / max(maxx - minx, maxy - miny)
    W = int((maxx - minx) * scale) + 4
    H = int((maxy - miny) * scale) + 4
    img = bytearray(W * H * 3)               # black bg
    zbuf = [-1e30] * (W * H)                 # painter via z (top-down: higher z wins)

    def sx(P): return int((P[0] - minx) * scale) + 2
    def sy(P): return int((P[1] - miny) * scale) + 2

    def dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
    def sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

    drawn = skipped = 0
    for n in nodes:
        if not (0 <= n.i_surf < len(surfs)):
            skipped += 1; continue
        s = surfs[n.i_surf]
        nv = n.num_vertices
        if nv < 3 or n.i_vert_pool < 0 or n.i_vert_pool + nv > len(verts):
            skipped += 1; continue
        idx = [verts[n.i_vert_pool + k].i_vertex for k in range(nv)]
        if any(not (0 <= vi < len(pts)) for vi in idx):
            skipped += 1; continue
        poly = [pts[vi] for vi in idx]
        if not (0 <= s.p_base < len(pts) and 0 <= s.v_texture_u < len(vecs)
                and 0 <= s.v_texture_v < len(vecs)):
            skipped += 1; continue
        tex = tex_for(s.texture_ref)
        base, tu, tv = pts[s.p_base], vecs[s.v_texture_u], vecs[s.v_texture_v]
        # screen + uv per vertex
        scr = [(sx(P), sy(P), dot(sub(P, base), tu), dot(sub(P, base), tv), P[2]) for P in poly]
        # triangulate fan, rasterize affine
        for k in range(1, nv - 1):
            _raster_tri(img, zbuf, W, H, scr[0], scr[k], scr[k + 1], tex)
        drawn += 1
    write_png(out, W, H, bytes(img))
    print(f"{os.path.basename(dx)}: {W}x{H}px, drew {drawn} node-polys, skipped {skipped} "
          f"(textures decoded: {sum(1 for v in texcache.values() if v)}/{len(texcache)})")
    print(f"wrote {out}")


def _raster_tri(img, zbuf, W, H, a, b, c, tex):
    # a,b,c = (sx,sy,u,v,z). Affine UV + z. Barycentric scanline.
    (x0, y0, u0, v0, z0), (x1, y1, u1, v1, z1), (x2, y2, u2, v2, z2) = a, b, c
    minx = max(min(x0, x1, x2), 0); maxx = min(max(x0, x1, x2), W - 1)
    miny = max(min(y0, y1, y2), 0); maxy = min(max(y0, y1, y2), H - 1)
    if minx > maxx or miny > maxy:
        return
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if den == 0:
        return
    inv = 1.0 / den
    if tex:
        tw, th, trgb = tex
    for y in range(miny, maxy + 1):
        for x in range(minx, maxx + 1):
            w0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) * inv
            w1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) * inv
            w2 = 1 - w0 - w1
            if w0 < 0 or w1 < 0 or w2 < 0:
                continue
            z = w0 * z0 + w1 * z1 + w2 * z2
            pi = y * W + x
            if z <= zbuf[pi]:
                continue
            zbuf[pi] = z
            if tex:
                u = int(w0 * u0 + w1 * u1 + w2 * u2) % tw
                v = int(w0 * v0 + w1 * v1 + w2 * v2) % th
                ti = (v * tw + u) * 3
                r, g, b = trgb[ti], trgb[ti + 1], trgb[ti + 2]
            else:
                r = g = b = 128
            o = pi * 3
            img[o] = r; img[o + 1] = g; img[o + 2] = b


if __name__ == "__main__":
    main(sys.argv)
