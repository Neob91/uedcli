"""`#exec TEXTURE IMPORT NAME=X FILE=Textures\\X.PCX LODSET=n` — decode the referenced PCX and build
the `UTexture`/`UPalette` data UCC would import, byte-exact.

RE'd in `dev/docs/spikes/2026-09-13-texture-import-re/spike.md` (PCX decode, property list, mip-chain
quantization); this module is the production implementation `compile.py` wires in — see
`dev/docs/unrealed/unrealscript/compile-model.md` ("`#exec TEXTURE IMPORT`") for the property/body
layout this feeds.

Two formulas here are JUDGMENT CALLS on an unresolved exact-tie edge case (documented in the spike
and in `compile-model.md`, not claimed as verified):
  - the mip-quantization tie-break (`_nearest_palette_index`): equal-distance ties favor the LOWER
    palette index.
  - `MipZero`'s per-channel rounding at an exact `.5` average: floors (matches the only unambiguous,
    non-tie evidence — `Asym4x4`'s `.8125` truncates; three of five measured EXACT ties round the
    other way, and no rule reproduces all of them).
Real (non-degenerate) content is exceedingly unlikely to hit either tie.
"""
from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass

# ── PCX decode (8bpp, single-plane, RLE, trailing 256-color VGA palette) ────────────────────────────
_PCX_HEADER_SIZE = 128
_PCX_PALETTE_MARKER = 0x0C


def decode_pcx(data: bytes) -> tuple[int, int, list[list[int]], list[tuple[int, int, int]]]:
    """Decode an 8bpp RLE PCX -> `(width, height, pixel_rows, palette)`. `pixel_rows[y][x]` is a
    palette index 0-255; `palette` is exactly 256 `(r, g, b)` tuples. Raises `NotImplementedError`
    for any PCX shape this hasn't been verified against (not 8bpp/1-plane/RLE, or no trailing VGA
    palette) — UE1 texture import only ever uses this shape."""
    if len(data) < _PCX_HEADER_SIZE + 1:
        raise NotImplementedError(f"PCX file too small ({len(data)} bytes)")
    if data[0] != 0x0A:
        raise NotImplementedError(f"not a PCX file (bad manufacturer byte {data[0]:#x})")
    encoding, bpp = data[2], data[3]
    xmin, ymin, xmax, ymax = struct.unpack_from("<HHHH", data, 4)
    nplanes = data[65]
    bytes_per_line = struct.unpack_from("<H", data, 66)[0]
    if encoding != 1:
        raise NotImplementedError(f"PCX encoding {encoding} not supported (only RLE=1)")
    if bpp != 8 or nplanes != 1:
        raise NotImplementedError(f"PCX bpp={bpp} nplanes={nplanes} not supported "
                                  "(only 8bpp/1-plane, the only shape UE1 texture import reads)")
    width, height = xmax - xmin + 1, ymax - ymin + 1
    pos = _PCX_HEADER_SIZE
    rows: list[list[int]] = []
    for _ in range(height):
        row = bytearray()
        while len(row) < bytes_per_line:
            if pos >= len(data):
                raise NotImplementedError(f"PCX RLE body truncated at row {len(rows)}")
            b = data[pos]; pos += 1
            if (b & 0xC0) == 0xC0:
                count = b & 0x3F
                val = data[pos]; pos += 1
                row += bytes([val]) * count
            else:
                row.append(b)
        rows.append(list(row[:width]))
    if len(data) < pos + 769 or data[pos] != _PCX_PALETTE_MARKER:
        # tolerate trailing padding between the RLE body and the palette marker only up to EOF-769
        marker_at = len(data) - 769
        if marker_at < pos or data[marker_at] != _PCX_PALETTE_MARKER:
            raise NotImplementedError("PCX has no trailing 256-color VGA palette (0x0C marker)")
        pos = marker_at
    pal_bytes = data[pos + 1:pos + 769]
    palette = [(pal_bytes[i * 3], pal_bytes[i * 3 + 1], pal_bytes[i * 3 + 2]) for i in range(256)]
    return width, height, rows, palette


# ── mip-chain quantization (ported from `harness/mip_formula.py`; see spike.md for the derivation)──
_WR, _WG, _WB = 79, 158, 19  # luma weights, sum to 256 (a `>>8` fixed-point scale)


def _dist2(rgb: tuple[int, int, int], target: tuple[float, float, float]) -> float:
    r, g, b = rgb
    tr, tg, tb = target
    return _WR * (r - tr) ** 2 + _WG * (g - tg) ** 2 + _WB * (b - tb) ** 2


def _nearest_palette_index(target: tuple[float, float, float],
                           palette: list[tuple[int, int, int]]) -> int:
    """Luma-weighted nearest palette entry. JUDGMENT CALL (spike.md "Open: the tie-break rule"): an
    exact tie favors the LOWER index — matches 2 of 3 measured live-UCC ties, not confirmed for all."""
    best_i, best_d = 0, _dist2(palette[0], target)
    for i in range(1, len(palette)):
        d = _dist2(palette[i], target)
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def _box_average(rgb_grid: list[list[tuple[int, int, int]]]) -> list[list[tuple[float, float, float]]]:
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


def _mip_chain(mip0_indices: list[list[int]],
               palette: list[tuple[int, int, int]]) -> list[list[list[int]]]:
    """Every mip level's palette-INDEX grid, mip0 first, down to 1x1."""
    if len(mip0_indices) & (len(mip0_indices) - 1) or len(mip0_indices[0]) & (len(mip0_indices[0]) - 1):
        raise NotImplementedError(
            f"texture dimensions {len(mip0_indices[0])}x{len(mip0_indices)} are not both powers of "
            "two (unverified mip-chain behavior)")
    levels = [mip0_indices]
    rgb_grid = [[palette[idx] for idx in row] for row in mip0_indices]
    while len(rgb_grid) > 1 or len(rgb_grid[0]) > 1:
        rgb_grid = _box_average(rgb_grid)
        levels.append([[_nearest_palette_index(px, palette) for px in row] for row in rgb_grid])
    return levels


# ── MipZero / MaxColor (RE'd 2026-09-13, not in the original spike write-up — see compile-model.md)─
def _round_channel(x: float) -> int:
    """The general (non-tie) rule is unambiguous: FLOOR (`Asym4x4`'s `.8125` truncates to `39`, not a
    boundary case at all). An exact `.5` average is a separate, genuinely unresolved tie (5 measured
    cases: 2 floor, 3 ceil) -- this JUDGMENT CALL rounds a `.5` tie UP, the direction the majority of
    that partial evidence leans; see the module docstring and `compile-model.md`."""
    frac = x - math.floor(x)
    if abs(frac - 0.5) < 1e-9:
        return math.ceil(x)
    return math.floor(x)


def _mip_zero(mip0_indices: list[list[int]], palette: list[tuple[int, int, int]]
             ) -> tuple[int, int, int]:
    """The flat TRUE average of every mip0 pixel's resolved RGB, rounded per channel (`_round_channel`,
    unresolved at an exact `.5` -- see module docstring)."""
    pixels = [palette[idx] for row in mip0_indices for idx in row]
    n = len(pixels)
    r = _round_channel(sum(p[0] for p in pixels) / n)
    g = _round_channel(sum(p[1] for p in pixels) / n)
    b = _round_channel(sum(p[2] for p in pixels) / n)
    return r, g, b


def _max_color(levels: list[list[list[int]]], palette: list[tuple[int, int, int]]
              ) -> tuple[int, int, int]:
    """The per-channel INDEPENDENT maximum over every pixel in the whole mip chain (every level),
    resolved through the palette. No tie ambiguity (a hard integer max)."""
    r_max = g_max = b_max = 0
    for level in levels:
        for row in level:
            for idx in row:
                r, g, b = palette[idx]
                r_max, g_max, b_max = max(r_max, r), max(g_max, g), max(b_max, b)
    return r_max, g_max, b_max


# ── the assembled result compile.py needs ───────────────────────────────────────────────────────────
@dataclass(frozen=True, kw_only=True)
class TextureMip:
    width: int
    height: int
    indices: bytes    # row-major palette-index bytes


@dataclass(frozen=True, kw_only=True)
class TextureImportResult:
    palette: tuple[tuple[int, int, int], ...]   # exactly 256 (r, g, b) entries
    mips: tuple[TextureMip, ...]                 # mip0 first, down to 1x1
    lodset: int
    usize: int
    vsize: int
    ubits: int
    vbits: int
    mip_zero: tuple[int, int, int]
    max_color: tuple[int, int, int]


def palette_trailer_bytes(palette: tuple[tuple[int, int, int], ...]) -> bytes:
    """`UPalette`'s body tail: `ci(count)` then `count * (R, G, B, 0xFF)` -- alpha always `0xFF`."""
    from ..native.codec import write_ci
    out = bytearray(write_ci(len(palette)))
    for r, g, b in palette:
        out += bytes((r, g, b, 0xFF))
    return bytes(out)


MAX_COLOR_DEFAULT = (255, 255, 255)   # Engine.Texture's own class default -- compile.py omits the
                                       # MaxColor tag when the computed value equals it (UE1's usual
                                       # "tagged properties omit a value equal to the CDO" rule)


def import_texture(pcx_bytes: bytes, *, lodset: int) -> TextureImportResult:
    """Decode `pcx_bytes` and build everything `compile.py` needs to emit a byte-exact
    `UTexture`/`UPalette` pair for one `#exec TEXTURE IMPORT`."""
    width, height, mip0, palette = decode_pcx(pcx_bytes)
    levels = _mip_chain(mip0, palette)
    mips = tuple(
        TextureMip(width=len(level[0]), height=len(level), indices=bytes(v for row in level for v in row))
        for level in levels)
    return TextureImportResult(
        palette=tuple(palette), mips=mips, lodset=lodset, usize=width, vsize=height,
        ubits=width.bit_length() - 1, vbits=height.bit_length() - 1,
        mip_zero=_mip_zero(mip0, palette), max_color=_max_color(levels, palette))


# ── `#exec TEXTURE IMPORT` directive parsing ─────────────────────────────────────────────────────
_HEAD_RE = re.compile(r"^\s*TEXTURE\s+IMPORT\s+(.*)$", re.IGNORECASE)
_KNOWN_PARAMS = frozenset({"NAME", "FILE", "LODSET"})


@dataclass(frozen=True, kw_only=True)
class TextureImportDirective:
    name: str      # the texture's object name (NAME=)
    file: str      # the referenced PCX path, as written (FILE=), e.g. "Textures\\X.PCX"
    lodset: int    # LODSET= (defaults to 0; unverified whether UCC allows omitting it)


def parse_texture_import(directive: str) -> TextureImportDirective | None:
    """Parse one `#exec` directive text; `None` if it isn't `TEXTURE IMPORT`. Raises
    `NotImplementedError` for a param this hasn't been RE'd against (anything but NAME/FILE/LODSET)."""
    m = _HEAD_RE.match(directive)
    if m is None:
        return None
    params: dict[str, str] = {}
    for tok in m.group(1).split():
        if "=" not in tok:
            raise NotImplementedError(f"#exec TEXTURE IMPORT: malformed parameter {tok!r}")
        k, _, v = tok.partition("=")
        params[k.upper()] = v
    unknown = sorted(set(params) - _KNOWN_PARAMS)
    if unknown:
        raise NotImplementedError(f"#exec TEXTURE IMPORT: parameter(s) {unknown} not supported yet "
                                  f"({directive!r})")
    if "NAME" not in params or "FILE" not in params:
        raise NotImplementedError(f"#exec TEXTURE IMPORT: NAME= and FILE= are required ({directive!r})")
    return TextureImportDirective(name=params["NAME"], file=params["FILE"],
                                  lodset=int(params.get("LODSET", "0")))
