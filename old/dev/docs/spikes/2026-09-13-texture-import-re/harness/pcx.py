"""Minimal 8bpp RLE PCX encoder, built for probing UCC's `#exec TEXTURE IMPORT`. Not a general
PCX writer — just enough to build controlled fixtures (see `rebuild_probes.py`)."""
from __future__ import annotations

import struct


def _rle_encode_row(row: list[int], bytes_per_line: int) -> bytes:
    padded = row + [0] * (bytes_per_line - len(row))
    out = bytearray()
    i, n = 0, len(padded)
    while i < n:
        j = i
        while j + 1 < n and padded[j + 1] == padded[i] and (j - i) < 62:
            j += 1
        run, val = j - i + 1, padded[i]
        if run > 1 or val >= 0xC0:
            out += bytes([0xC0 | run, val])
        else:
            out.append(val)
        i = j + 1
    return bytes(out)


def make_pcx(pixels: list[list[int]], palette: list[tuple[int, int, int]]) -> bytes:
    """`pixels[y][x]` is a palette index 0-255; `palette` is exactly 256 (r, g, b) tuples."""
    height = len(pixels)
    width = len(pixels[0])
    assert all(len(r) == width for r in pixels)
    assert len(palette) == 256
    bytes_per_line = width + (width % 2)
    header = struct.pack(
        "<BBBBHHHHHH48sBBHHHH54x",
        0x0A, 5, 1, 8,                        # Manufacturer, Version, Encoding=RLE, 8bpp
        0, 0, width - 1, height - 1,          # Xmin,Ymin,Xmax,Ymax
        72, 72,                               # HDpi, VDpi
        b"\x00" * 48,                         # 16-color EGA colormap, unused at 8bpp
        0, 1, bytes_per_line, 1, 0, 0,        # Reserved, NPlanes, BytesPerLine, PaletteInfo, HScreen, VScreen
    )
    assert len(header) == 128
    body = bytearray()
    for row in pixels:
        body += _rle_encode_row(row, bytes_per_line)
    pal_block = bytearray([0x0C])
    for r, g, b in palette:
        pal_block += bytes([r, g, b])
    return bytes(header) + bytes(body) + bytes(pal_block)


def default_palette() -> list[tuple[int, int, int]]:
    """A smooth, fully-ordered palette (`color(i) = (3i, 5i, 7i) mod 256`) — every entry lies on
    one line through the origin in RGB space, so any reasonable "nearest point on this palette"
    algorithm degenerates to plain index averaging. Good for exercising the STRUCTURAL format;
    useless for pinning the mip quantization algorithm (see `grey_ramp_with_overrides`)."""
    return [((i * 3) % 256, (i * 5) % 256, (i * 7) % 256) for i in range(256)]


def grey_ramp_with_overrides(overrides: dict[int, tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """An identity grey ramp (`palette[i] = (i, i, i)`) with a few indices overridden to specific
    colors. Used to place saturated colors OFF the grey ramp's line, so a nearest-palette search
    can be told apart from naive index averaging."""
    pal = [(i, i, i) for i in range(256)]
    for i, rgb in overrides.items():
        pal[i] = rgb
    return pal
