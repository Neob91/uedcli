"""Mean RGB of every Texture in a package — used to pick two visually unmistakable probe skins.

    python3 tex_means.py <pkg.u|.utx>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli import utexture  # noqa: E402
from uedcli.upackage import load_package  # noqa: E402

path = sys.argv[1]
pkg = load_package(path)
resolver = utexture.TextureResolver([path])
for i in range(len(pkg.exports)):
    ref = i + 1
    if (pkg.object_class_name(ref) or "").casefold() != "texture":
        continue
    full = pkg.object_path(ref)
    got = resolver.resolve(full)
    if isinstance(got, utexture.TextureError):
        continue
    rgb = got.rgb
    n = len(rgb) // 3
    if not n:
        continue
    r = sum(rgb[0::3]) / n
    g = sum(rgb[1::3]) / n
    b = sum(rgb[2::3]) / n
    print(f"{full:<40} {got.width}x{got.height}  mean=({r:6.1f},{g:6.1f},{b:6.1f})  masked={got.b_masked}")
