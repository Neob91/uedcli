"""Prove the data pipeline for a native (no-editor) textured render exists: for a real
map's built `Model`, resolve every surface's texture to its package+name (the map's own
import table), decode those textures natively from the install, and compute surface UVs
from the Model's geometry — i.e. confirm everything a renderer needs is natively in hand.

Composes: Model read (bspspike/umodel_parser) + import resolution (qualify) + texture
decode (utexture). Reports texture-resolution + decode coverage and a UV sanity check.

Usage: python native_render_data.py <map.dx> <install_textures_dir> [<install_system_dir>]
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, ".")
sys.path.insert(0, "../../bspspike")  # umodel_parser lives in the bspspike dir
import umodel_parser as U
from package_rw import Pkg
from utexture_decode import (load_package, textures as tex_exports, decode_texture,
                             decode_palette, export_index_of_ref, mip0_to_rgb)


def _name(p, i):
    return p.names[i][0].split(b"\x00", 1)[0].decode("latin-1")


def surf_texture_refs(dx_path):
    """Map each surf's texture object-ref to (package, name) via the .dx import table."""
    p = Pkg(dx_path)
    def imp_pkg(j):
        cur = p.imports[j]
        for _ in range(64):
            cp, cn, pi, on = cur
            if pi == 0:
                return _name(p, on)
            if pi < 0:
                cur = p.imports[-pi - 1]
            else:
                return None
        return None
    def resolve(ref):
        if ref >= 0:
            return None                          # 0/none or a local export (myLevel tex)
        j = -ref - 1
        return (imp_pkg(j), _name(p, p.imports[j][3]))
    return resolve


def main(argv):
    dx, texdir = argv[1], argv[2]
    buf = open(dx, "rb").read()
    me = U.find_model_exports(dx)
    exp_idx, name, size, offset = me[0]
    m = U.parse_model_serial(buf, offset, size)
    resolve = surf_texture_refs(dx)

    # distinct texture refs across surfs
    refs = Counter()
    for s in m.surfs:
        r = resolve(s.texture_ref)
        refs[r] += 1
    distinct = [r for r in refs if r and r[0]]
    print(f"{os.path.basename(dx)}: {len(m.surfs)} surfs, {len(distinct)} distinct external textures")

    # try to locate + native-decode each distinct texture from the install
    # case-insensitive package locator (Wine/NTFS semantics, like dxpkg)
    def locate(pkg):
        want = {(pkg + e).lower() for e in (".utx", ".u", ".uax", ".umx")}
        for d in (texdir, argv[3] if len(argv) > 3 else texdir):
            try:
                for fn in os.listdir(d):
                    if fn.lower() in want:
                        return os.path.join(d, fn)
            except OSError:
                pass
        return None

    pkgcache = {}
    decoded = 0
    failed = []
    for pkg, tname in distinct:
        path = locate(pkg)
        if not path:
            failed.append((pkg, tname, "package-missing")); continue
        if path not in pkgcache:
            pkgcache[path] = load_package(path)
        tp = pkgcache[path]
        ti = next((i for i in tex_exports(tp)
                   if tp.names[tp.exports[i]["nm"]].lower() == tname.lower()), None)
        if ti is None:
            failed.append((pkg, tname, "texture-not-in-package")); continue
        t = decode_texture(tp, ti)
        if t.fmt == 0 and t.mips:
            decode_palette(tp, export_index_of_ref(tp, t.palette_ref))
            decoded += 1
        else:
            failed.append((pkg, tname, f"fmt={t.fmt}"))
    print(f"natively decodable textures: {decoded}/{len(distinct)} "
          f"(covers {sum(refs[r] for r in distinct if (r[0]+'',) )} surf refs)")
    if failed:
        print(f"  unresolved ({len(failed)}): {failed[:6]}")

    # UV sanity: for a few surfs, compute UV at the surf's base point (should be ~0)
    ok_uv = 0
    sample = 0
    for s in m.surfs[:200]:
        if not (0 <= s.p_base < len(m.points)) or not (0 <= s.v_texture_u < len(m.vectors)):
            continue
        base = m.points[s.p_base]
        tu = m.vectors[s.v_texture_u]
        # U at base = (base-base)·tu = 0; check tu is a finite unit-ish vector
        if all(abs(c) < 1e6 for c in tu) and any(c != 0 for c in tu):
            ok_uv += 1
        sample += 1
    print(f"UV vectors valid on {ok_uv}/{sample} sampled surfs (TextureU finite & non-zero)")


if __name__ == "__main__":
    main(sys.argv)
