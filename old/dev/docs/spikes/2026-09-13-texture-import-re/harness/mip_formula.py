"""The reverse-engineered mip-chain quantization formula for UCC's `#exec TEXTURE IMPORT`
(8bpp palette textures). See `spike.md` for the derivation and evidence.

Mip 0 is the source PCX pixels verbatim. Each further mip level's pixel is:
  1. the recursive box-average (2x2) of the TRUE RGB colors of the corresponding source block,
     resolved through the texture's own palette, carried in float from the ORIGINAL pixels (never
     re-quantized between levels: level 2 averages the true colors of its 16 source pixels, not
     four already-quantized level-1 bytes -- these happen to coincide when the average lands away
     from a tie, but a `spike.md`-documented probe (`Asym4x4`) separates them).
  2. quantized back to a palette INDEX by searching the WHOLE 256-entry palette for the entry
     minimizing a LUMA-WEIGHTED squared distance: weights (79, 158, 19) for (R, G, B) (summing to
     256 -- almost certainly the source's fixed-point weights, scaled for a `>>8`). Ties (an exact
     equal distance) go to the LOWER index.
"""
from __future__ import annotations

_WR, _WG, _WB = 79, 158, 19


def _dist2(rgb: tuple[int, int, int], target: tuple[float, float, float]) -> float:
    r, g, b = rgb
    tr, tg, tb = target
    return _WR * (r - tr) ** 2 + _WG * (g - tg) ** 2 + _WB * (b - tb) ** 2


def nearest_palette_index(target: tuple[float, float, float], palette: list[tuple[int, int, int]]) -> int:
    """The palette index minimizing the luma-weighted squared distance to `target`; ties favor the
    LOWER index (first strictly-better candidate wins, later equal candidates do not replace it)."""
    best_i, best_d = 0, _dist2(palette[0], target)
    for i in range(1, len(palette)):
        d = _dist2(palette[i], target)
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def box_average(rgb_grid: list[list[tuple[int, int, int]]]) -> list[list[tuple[float, float, float]]]:
    """One 2x2-box downsample step, in float RGB (no quantization)."""
    h, w = len(rgb_grid), len(rgb_grid[0])
    out = []
    for y in range(0, h, 2):
        row = []
        for x in range(0, w, 2):
            rs = gs = bs = 0.0
            for dy in (0, 1):
                for dx in (0, 1):
                    r, g, b = rgb_grid[y + dy][x + dx]
                    rs += r; gs += g; bs += b
            row.append((rs / 4.0, gs / 4.0, bs / 4.0))
        out.append(row)
    return out


def mip_chain(mip0_indices: list[list[int]], palette: list[tuple[int, int, int]]) -> list[list[list[int]]]:
    """Every mip level's INDEX grid, mip0 first, down to 1x1. `mip0_indices` is the source pixel
    grid (palette indices, as imported verbatim)."""
    levels = [mip0_indices]
    rgb_grid = [[palette[idx] for idx in row] for row in mip0_indices]
    while len(rgb_grid) > 1 or len(rgb_grid[0]) > 1:
        rgb_grid = box_average(rgb_grid)
        levels.append([[nearest_palette_index(px, palette) for px in row] for row in rgb_grid])
    return levels
