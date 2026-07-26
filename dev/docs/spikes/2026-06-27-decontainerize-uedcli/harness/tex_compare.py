r"""Reproducible pixel-exact validation of the native texture decoder against UCC's
own `batchexport` PCX output. This is the committed proof behind Spike 1's
"pixel-EXACT vs UCC" claim.

Ground truth needs UCC (wine), so it is produced ONCE per package in a container and
compared host-side. The native side needs nothing but Python; the comparison needs
Pillow (repo venv) to decode UCC's PCX.

One-time ground-truth export (in the standing `dx-lum-uned` container):
    C=dx-lum-uned
    docker exec $C sh -c 'rm -rf /work/tv && mkdir -p /work/tv'
    docker exec $C wine /opt/UED22/UCC.exe batchexport <Package> Texture pcx 'Z:\work\tv'
    docker cp $C:/work/tv /tmp/tv

Then compare (repo venv has Pillow):
    /home/human/src/dx_lum/.venv-uedcli/bin/python tex_compare.py <Package.utx|.u> /tmp/tv

Result observed 2026-06-27 (all pixel-EXACT, 0 mismatches):
    CoreTexMetal.utx (v68): 175/175    CoreTexDetail.utx (v61): 17/17
    DeusExItems.u   (v68): 185/185 (1 PCX bare-name collided in this script's dict)

NOTE the corpus is the RETAIL v68/v61 install at
`uned/DeusExAssets/{Textures,System}` — NOT `uned/UED22/` (those are v69 stubs and
give different/contradictory numbers).
"""
from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, ".")
from utexture_decode import (load_package, textures, decode_texture,
                             decode_palette, export_index_of_ref, mip0_to_rgb)


def main(argv):
    utx, pcxdir = argv[1], argv[2]
    from PIL import Image  # repo venv
    pkg = load_package(utx)
    native = {}
    nonp8 = 0
    for i in textures(pkg):
        t = decode_texture(pkg, i)
        if t.fmt != 0 or not t.mips:
            nonp8 += 1
            continue
        pal = decode_palette(pkg, export_index_of_ref(pkg, t.palette_ref))
        native[t.name.lower()] = (t.mips[0].width, t.mips[0].height,
                                  mip0_to_rgb(t.mips[0], pal))
    exact = mism = dim = missing = 0
    details = []
    for pcx in glob.glob(os.path.join(pcxdir, "*.pcx")):
        bare = os.path.basename(pcx)[:-4].split(".")[-1].lower()  # strip group + .pcx
        if bare not in native:
            missing += 1
            continue
        w, h, rgb = native[bare]
        im = Image.open(pcx).convert("RGB")
        if im.size != (w, h):
            dim += 1
            details.append(f"DIM {bare}: {w}x{h} vs {im.size}")
            continue
        if im.tobytes() == rgb:
            exact += 1
        else:
            mism += 1
            a = im.tobytes()
            d = sum(1 for j in range(0, len(a), 3) if a[j:j + 3] != rgb[j:j + 3])
            details.append(f"MISMATCH {bare}: {d}/{w*h} px")
    print(f"{os.path.basename(utx)} (v{pkg.version}): EXACT={exact} mismatch={mism} "
          f"dim={dim} pcx_without_native={missing} nonP8_native={nonp8}")
    for d in details[:12]:
        print("  " + d)
    return 0 if mism == 0 and dim == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
