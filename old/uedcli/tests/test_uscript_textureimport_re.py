"""Pins the RE finding for UCC's `#exec TEXTURE IMPORT` mip-chain quantization (8bpp palette
textures): `dev/docs/spikes/2026-09-13-texture-import-re/spike.md`. Offline — reads the committed
golden `.u` files (built once from a live UCC by `harness/rebuild_probes.py`) and the palette/pixel
inputs that produced them, and checks the harness's derived formula (`harness/mip_formula.py`)
reproduces every mip level's actual bytes. No docker, no compiler integration yet (that's tracked
separately — see the spike for the open items this does NOT cover: the class/property table
serialization, and the exact sub-integer rounding of the `MipZero`/`MaxColor` summary fields).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from uedcli import utexture

_SPIKE = Path(__file__).resolve().parents[2] / "dev/docs/spikes/2026-09-13-texture-import-re"
_HARNESS = _SPIKE / "harness"

pytestmark = pytest.mark.skipif(not _HARNESS.is_dir(), reason="spike harness not present")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_pcx = _load("_ti_re_pcx", _HARNESS / "pcx.py")
_mip = _load("_ti_re_mip_formula", _HARNESS / "mip_formula.py")

# (probe name, mip0 pixel grid, palette) -- must match `harness/rebuild_probes.py`'s PROBES exactly;
# duplicated here (not imported) so a probe-table edit there doesn't silently desync this test.
#
# "BlackWhite" is a KNOWN, UNRESOLVED gap, not a formula bug: its averaged target (127.5 on every
# channel) is an EXACT tie under the weighted-distance search, like "Asym4x4" (2.5) and "Tie" (3.5)
# below -- but where those two both resolve to the LOWER candidate (matching the formula's
# tie-break), this one resolves to the HIGHER one (128, not 127). Three real ties, two different
# outcomes; no rule found yet that explains both directions (spike.md, "Open: the tie-break rule").
_CASES = [
    ("Gradient8x8", [[i] * 8 for i in range(8)], _pcx.default_palette()),
    ("Asym4x4", [[1, 2, 5, 5], [3, 4, 5, 5], [10, 20, 0, 0], [10, 20, 0, 1]], _pcx.default_palette()),
    ("RedGreen", [[50, 50], [60, 60]],
     _pcx.grey_ramp_with_overrides({50: (255, 0, 0), 55: (0, 0, 255), 60: (0, 255, 0)})),
    pytest.param("BlackWhite", [[200, 200], [210, 210]],
                 _pcx.grey_ramp_with_overrides({200: (0, 0, 0), 210: (255, 255, 255)}),
                 marks=pytest.mark.xfail(reason="tie-break direction unresolved, spike.md", strict=True)),
    ("RedBlue", [[90, 90], [95, 95]],
     _pcx.grey_ramp_with_overrides({90: (255, 0, 0), 95: (0, 0, 255)})),
    ("Tie", [[3, 3], [4, 4]], _pcx.default_palette()),
]


def _golden_mip_indices(name: str) -> list[list[list[int]]]:
    path = _HARNESS / f"golden_{name}.u"
    pkg = utexture.load_package(str(path), stem=f"UscTex{name}")
    tex_idxs = utexture.textures(pkg)
    assert len(tex_idxs) == 1, f"{name}: expected exactly one Texture export, found {tex_idxs}"
    t = utexture.decode_texture(pkg, tex_idxs[0])
    levels = []
    for m in t.mips:
        levels.append([list(m.data[y * m.width:(y + 1) * m.width]) for y in range(m.height)])
    return levels


def _case_values(c) -> tuple:
    return c.values if hasattr(c, "values") else c


@pytest.mark.parametrize("name,pixels,palette", _CASES,
                         ids=[_case_values(c)[0] for c in _CASES])
def test_mip_formula_matches_live_ucc_golden(name, pixels, palette):
    predicted = _mip.mip_chain(pixels, palette)
    actual = _golden_mip_indices(name)
    assert predicted == actual, (
        f"{name}: derived mip-quantization formula diverges from the live UCC golden "
        f"(dev/docs/spikes/2026-09-13-texture-import-re/spike.md)")


def test_mip0_is_the_source_pixels_verbatim():
    """Every probe's level 0 is the imported PCX pixels unchanged (no quantization on the base
    level) -- the one part of the mip chain that never needs the formula above."""
    for c in _CASES:
        name, pixels, _palette = _case_values(c)
        actual = _golden_mip_indices(name)
        assert actual[0] == pixels, f"{name}: mip0 does not match the source PCX pixels"
