"""Rebuild every `#exec TEXTURE IMPORT` probe fixture against a live UCC and refresh the committed
goldens in this directory. Needs docker + the committed UED22 substrate — not run by `bin/test`
(no test depends on live docker); run by hand to regenerate `golden_*.u` after a substrate change.

Each probe is a minimal one-class package whose only content is a single
`#exec TEXTURE IMPORT NAME=... FILE=Textures\\...PCX LODSET=0` directive, importing a tiny,
hand-built PCX. See `spike.md` for what each one measures.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))   # repo root -> import uedcli

from pcx import make_pcx, default_palette, grey_ramp_with_overrides
from uedcli.uscript.reference import ucc_compile, ucc_container

HERE = Path(__file__).resolve().parent

PROBES = {
    # name -> (pixels, palette). Every probe is a single class `class Usc<Name> expands Object;`
    # with one `#exec TEXTURE IMPORT NAME=<Name>Tex FILE=Textures\\<Name>Tex.PCX LODSET=0`.

    # 8x8, one solid color per row (indices 0..7) on the smooth `default_palette` -- exercises the
    # STRUCTURAL format (export/name/import tables, tagged properties, a real multi-level mip
    # chain 8x8/4x4/2x2/1x1) without pinning down the quantization algorithm (this palette's
    # entries all lie on one line through the origin, so "nearest point on the palette" and "plain
    # index average" coincide -- see `grey_ramp_with_overrides` probes for that).
    "Gradient8x8": ([[i] * 8 for i in range(8)], default_palette()),

    # 4x4 asymmetric block on the same linear palette -- a second structural/degenerate case
    # (2 mip-reduction steps), used to confirm the recursive box-average model end to end.
    "Asym4x4": ([[1, 2, 5, 5], [3, 4, 5, 5], [10, 20, 0, 0], [10, 20, 0, 1]], default_palette()),

    # 2x2, red (top row) / green (bottom row), on a grey ramp with 3 unrelated overrides -- pins
    # the mip-quantization weights: PALETTE SEARCH (not index-averaging) is the only theory that
    # survives this one (see spike.md).
    "RedGreen": ([[90, 90], [90, 90]], None),  # placeholder, replaced below (needs its own palette)
    "BlackWhite": ([[200, 200], [210, 210]], None),
    "RedBlue": ([[90, 90], [95, 95]], None),

    # 2x2, indices 3/4 on the linear palette -- averages to an EXACT tie (index 3.5); pins the
    # tie-break rule (lower index wins, not "nearest even").
    "Tie": ([[3, 3], [4, 4]], default_palette()),
}

_REDGREEN_PAL = grey_ramp_with_overrides({50: (255, 0, 0), 55: (0, 0, 255), 60: (0, 255, 0)})
_BLACKWHITE_PAL = grey_ramp_with_overrides({200: (0, 0, 0), 210: (255, 255, 255)})
_REDBLUE_PAL = grey_ramp_with_overrides({90: (255, 0, 0), 95: (0, 0, 255)})
PROBES["RedGreen"] = ([[50, 50], [60, 60]], _REDGREEN_PAL)
PROBES["BlackWhite"] = ([[200, 200], [210, 210]], _BLACKWHITE_PAL)
PROBES["RedBlue"] = ([[90, 90], [95, 95]], _REDBLUE_PAL)


def main() -> None:
    with ucc_container(state_dir=HERE / "_state") as c:
        for name, (pixels, palette) in PROBES.items():
            pkg = f"UscTex{name}"
            src = (f"class {pkg} expands Object;\n\n"
                   f"#exec TEXTURE IMPORT NAME={name}Tex FILE=Textures\\{name}Tex.PCX LODSET=0\n")
            pcx = make_pcx(pixels, palette)
            u = ucc_compile(c, pkg, {f"{pkg}.uc": src},
                            extra_files={f"Textures/{name}Tex.PCX": pcx})
            (HERE / f"golden_{name}.u").write_bytes(u)
            print(f"{name}: wrote golden_{name}.u ({len(u)} bytes)")


if __name__ == "__main__":
    main()
