"""Render a CLASS thumbnail natively: class defaults -> Mesh + MultiSkins -> decode -> rasterize.

This is the shape a class catalog actually needs. A mesh's own `Textures` array is only the
fallback skin set; for Deus Ex characters it is usually empty, and the real skins come from the
CLASS's `MultiSkins[i]` (per material index) or `Skin`. uedcli already resolves class defaults
offline (`uprops.resolve_class_defaults`), so the whole thumbnail is offline, editor-free.

Usage:
    python render_class.py <Package.ClassName> [--out X.png] [--size 512] [--yaw 45] [--pitch 20]
                           [--system DIR] [--textures DIR]
"""
from __future__ import annotations

import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
from uedcli.upackage import load_package  # noqa: E402
from uedcli import uprops, utexture  # noqa: E402
import umesh  # noqa: E402
import render as R  # noqa: E402

from PIL import Image  # noqa: E402

OBJREF = re.compile(r"^\s*(\w+)'([^']+)'\s*$")     # e.g.  LodMesh'DeusExCharacters.GM_Trench'


def objref(text):
    """`LodMesh'Pkg.Group.Name'` -> ('LodMesh', 'Pkg.Group.Name'); None for 'None'/unparseable."""
    m = OBJREF.match(text or "")
    return (m.group(1), m.group(2)) if m else None


class StemResolver:
    """Minimal package resolver: stem -> path, over the given dirs."""

    def __init__(self, dirs):
        self.files = {}
        for d in dirs:
            for f in glob.glob(os.path.join(d, "*.u")) + glob.glob(os.path.join(d, "*.utx")):
                self.files.setdefault(os.path.splitext(os.path.basename(f))[0], f)

    def __call__(self, stem):
        return self.files.get(stem)

    def path_for(self, stem):
        return self.files.get(stem)


def main(argv):
    fqcn = argv[1]
    DX = R.arg(argv, "--dx", "/home/neob91/Games/LutrisDX/drive_c/DX")
    sysdir = R.arg(argv, "--system", os.path.join(DX, "System"))
    texdir = R.arg(argv, "--textures", os.path.join(DX, "Textures"))
    resolver = StemResolver([sysdir, texdir])

    defs = uprops.resolve_class_defaults(fqcn, resolver=resolver, _pkgs={})
    mesh_ref = objref(defs.get(("mesh", 0), ""))
    if not mesh_ref:
        raise SystemExit(f"{fqcn}: no Mesh default (DrawType={defs.get(('drawtype', 0))!r}) — "
                         f"only DT_Mesh classes get a mesh thumbnail")
    _cls, path = mesh_ref
    parts = path.split(".")
    pkg_stem, mesh_name = parts[0], parts[-1]
    pkg_path = resolver.path_for(pkg_stem)
    if not pkg_path:
        raise SystemExit(f"{fqcn}: mesh package {pkg_stem} not found on the search path")

    pkg = load_package(pkg_path)
    j = next((j for j in umesh.mesh_exports(pkg)
              if pkg.names[pkg.exports[j]["nm"]].lower() == mesh_name.lower()), None)
    if j is None:
        raise SystemExit(f"{fqcn}: mesh {mesh_name} not in {pkg_stem}")
    m = umesh.parse_mesh(pkg, j)

    # Skins: start from the mesh's own Textures, then let the class's MultiSkins/Skin override
    # per material index — the class is the authority (characters carry no mesh-side skins).
    dirs = [texdir, sysdir]
    skins = R.skin_images(pkg, m, dirs)
    files = [p for p in resolver.files.values()]
    tres = utexture.TextureResolver(files)
    overridden = 0
    for (prop, idx), val in defs.items():
        if prop not in ("multiskins", "skin"):
            continue
        ref = objref(val)
        if not ref:
            continue
        rp = ref[1].split(".")
        got = tres.resolve(f"{rp[0]}.{rp[-1]}")
        if got:
            skins[idx if prop == "multiskins" else 0] = got
            overridden += 1

    img, ntris, _n = R.render(m, pkg, size=R.arg(argv, "--size", 512, int),
                              yaw=R.arg(argv, "--yaw", 45.0, float),
                              pitch=R.arg(argv, "--pitch", 20.0, float), flat=True)
    # re-rasterize with the merged skin set (render() built its own; redo with ours)
    img = _rasterize(m, skins, size=R.arg(argv, "--size", 512, int),
                     yaw=R.arg(argv, "--yaw", 45.0, float),
                     pitch=R.arg(argv, "--pitch", 20.0, float))
    out = R.arg(argv, "--out", f"{fqcn.split('.')[-1]}.png")
    img.save(out)
    print(f"{fqcn}: mesh={path} tris={ntris} mats={len(m.materials)} "
          f"mesh_skins={len(R.skin_images(pkg, m, dirs))} class_skin_overrides={overridden} -> {out}")
    return 0


def _rasterize(m, skins, *, size, yaw, pitch):
    """R.render() with an externally supplied skin map (class MultiSkins merged in)."""
    import math
    tris = R.frame_triangles(m)
    sx, sy, sz = m.scale if any(m.scale) else (1.0, 1.0, 1.0)
    cy, sy_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))

    def view(v):
        x, y, z = v[0] * sx, v[1] * sy, v[2] * sz
        x, y = x * cy - y * sy_, x * sy_ + y * cy
        y, z = y * cp - z * sp, y * sp + z * cp
        return (x, -z, y)

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
    light = (0.35, -0.5, 0.79)
    for (a, b, c, ua, ub, uc, mat) in tris:
        va, vb, vc = view(a), view(b), view(c)
        e1 = tuple(vb[i] - va[i] for i in range(3))
        e2 = tuple(vc[i] - va[i] for i in range(3))
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2],
             e1[0] * e2[1] - e1[1] * e2[0])
        nl = math.sqrt(sum(q * q for q in n)) or 1.0
        n = tuple(q / nl for q in n)
        shade = 0.30 + 0.70 * max(0.0, sum(n[i] * light[i] for i in range(3)))
        p0 = (va[0] * k + ox, va[1] * k + oy, va[2])
        p1 = (vb[0] * k + ox, vb[1] * k + oy, vb[2])
        p2 = (vc[0] * k + ox, vc[1] * k + oy, vc[2])
        area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
        if abs(area) < 1e-9:
            continue
        skin = skins.get(mat)
        minx = max(0, int(min(p0[0], p1[0], p2[0])));  maxx = min(W - 1, int(max(p0[0], p1[0], p2[0])) + 1)
        miny = max(0, int(min(p0[1], p1[1], p2[1])));  maxy = min(H - 1, int(max(p0[1], p1[1], p2[1])) + 1)
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
                    o = ((int(v) % th) * tw + (int(u) % tw)) * 3
                    col = (rgb[o], rgb[o + 1], rgb[o + 2])
                else:
                    col = (170, 172, 178)
                px[X, Y] = tuple(min(255, int(col[i] * shade)) for i in range(3))
    return img


if __name__ == "__main__":
    sys.exit(main(sys.argv))
