"""Pixel decode for UE1 textures: the per-layout decoders and the layout DETECTION that
picks one. Split out of `utexture.py` (which keeps package loading, the mip/palette readers,
`DecodedTexture`/`TextureError` and `TextureResolver`) so each file has one job.

Nothing here touches a `Package`: a decoder takes a `Mip` plus a palette and returns
`(rgb, mask)` bytes, and detection takes the mip list plus the optional format code. That is why
this is the half that separates cleanly.

THE GOVERNING IDEA of detection — the layout is read off the DATA, not a format table — and the
evidence for the four format codes are documented at `detect_layout` below.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:                                    # `Mip` appears only in annotations, and
    from .utexture import Mip                        # `from __future__ import annotations` is on


def mip0_to_rgb(mip: Mip, palette: list[tuple[int, int, int]]) -> bytes:
    """P8 mip bytes + palette → packed RGB (width*height*3 bytes, row-major)."""
    out = bytearray(mip.width * mip.height * 3)
    for i, idx in enumerate(mip.data):
        r, g, b = palette[idx]
        out[i * 3] = r; out[i * 3 + 1] = g; out[i * 3 + 2] = b
    return bytes(out)


def _decode_linear1(mip: Mip, palette) -> tuple[bytes, bytes]:
    """P8 → `(rgb, mask)`. P8 carries no alpha channel, so the palette-index-0 convention IS
    its transparency mask: 1 = opaque, 0 = transparent."""
    return (mip0_to_rgb(mip, palette),
            bytes(1 if idx != 0 else 0 for idx in mip.data))


def _rgb565(v: int) -> tuple[int, int, int]:
    """A 16-bit RGB565 endpoint → 8 bits per channel by BIT REPLICATION, not by rounding.

    `(v << 3) | (v >> 2)` for the 5-bit channels and `(v << 2) | (v >> 4)` for the 6-bit one:
    the low bits are filled with copies of the high bits, so 31 → 255 exactly. Checked against
    Pillow's DDS decoder over all 32 and all 64 possible values with zero mismatches — it is
    NOT `round(v * 255 / 31)`, which differs by one on many values. Byte-exactness against a
    third-party decoder is therefore achievable, and is what the tests assert.
    """
    return (((v >> 11) & 0x1F) << 3 | ((v >> 11) & 0x1F) >> 2,
            ((v >> 5) & 0x3F) << 2 | ((v >> 5) & 0x3F) >> 4,
            (v & 0x1F) << 3 | (v & 0x1F) >> 2)


def _bc_colours(c0: int, c1: int, *, punch_through: bool) -> tuple[list, bool]:
    """The four colours a block's two RGB565 endpoints imply, and whether index 3 is
    transparent. Shared by BC1, BC2 and BC3 — all three carry the SAME colour block, BC2/BC3
    simply at offset 8 behind an alpha half.

    The four-colour mode's middle entries are the 1/3 and 2/3 interpolants, computed as the
    plain integer `(2a + b) // 3` (white/black endpoints give 170 and 85).

    `punch_through` is the one difference, and it is BC1's alone. In BC1, `c0 <= c1` selects a
    three-colour mode — one interpolant, the integer midpoint — where index 3 is transparent
    black. **BC2 and BC3 have no such mode**: they carry real alpha, so their colour block is
    always four opaque colours regardless of how the endpoints compare. Verified against
    Pillow: the same `c0 <= c1` block gives 127 + transparent under DXT1 and 85/170 opaque
    under DXT3/DXT5.
    """
    a, b = _rgb565(c0), _rgb565(c1)
    if not punch_through or c0 > c1:
        return ([a, b,
                 tuple((2 * a[k] + b[k]) // 3 for k in range(3)),
                 tuple((a[k] + 2 * b[k]) // 3 for k in range(3))], False)
    return ([a, b, tuple((a[k] + b[k]) // 2 for k in range(3)), (0, 0, 0)], True)


def _bc2_alpha(half: bytes) -> list[int]:
    """BC2 (DXT3) alpha: sixteen EXPLICIT 4-bit values, two per byte, low nibble first.
    Widened to 8 bits by replication (`v * 17`), so 15 → 255."""
    return [((half[i >> 1] >> (4 * (i & 1))) & 0xF) * 17 for i in range(16)]


def _bc3_alpha(half: bytes) -> list[int]:
    """BC3 (DXT5) alpha: two 8-bit endpoints then sixteen 3-bit indices packed into a 48-bit
    little-endian word.

    `a0 > a1` selects the EIGHT-value mode — six interpolants at sevenths. `a0 <= a1` selects
    the SIX-interpolant mode: four interpolants at fifths, plus a hard 0 at index 6 and a hard
    255 at index 7. That second mode is what makes the textbook opaque block `0005ffffffffffff`
    read as uniformly opaque under BC3 while the same eight bytes are alpha noise under BC2 —
    the asymmetry that identifies which of the two a real file is.
    """
    a0, a1 = half[0], half[1]
    if a0 > a1:
        table = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
    else:
        table = [a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]
    bits = int.from_bytes(half[2:8], "little")
    return [table[(bits >> (3 * i)) & 7] for i in range(16)]


def _decode_block(mip: Mip, *, block_bytes: int, alpha) -> tuple[bytes, bytes]:
    """The shared block walk for BC1/BC2/BC3 → `(rgb, mask)`.

    Each 4x4 block is `block_bytes` long and ends with BC1's colour block: two RGB565 endpoints
    then sixteen 2-bit indices, `(x, y)`'s index at bit `2 * (4 * y + x)`. `alpha` is `None` for
    BC1 (whose transparency is the punch-through mode inside the colour block) or a function
    from the leading 8-byte alpha half to sixteen 0..255 values for BC2/BC3.

    **Row writes are clipped to the mip's real width and height.** A block chain is stored as
    `ceil(w/4) x ceil(h/4)` WHOLE blocks, so the last block of a 4x1 or 8x2 mip carries texels
    that do not exist. Writing `bw * 4` pixels per row instead of `w` produces a buffer of the
    wrong length and shears the image; the case is live in real content, at 8x2, 4x1 and 2x1 in
    every block chain that reaches 1x1.

    **`mask` is BINARY — 1 = opaque, 0 = transparent** — because that is the contract every
    caller reads. BC2/BC3 can carry GRADED alpha, and it is flattened here at zero; board item
    `bc2-bc3-graded-alpha-is-flattened-to-a-binary` records that and why. Transparency comes
    only from the data, never from the texture's `bMasked` flag.
    """
    w, h = mip.width, mip.height
    bw, bh = (w + 3) // 4, (h + 3) // 4
    rgb = bytearray(w * h * 3)
    mask = bytearray(b"\x01" * (w * h))
    data = mip.data
    coff = block_bytes - 8                             # the colour block sits at the END
    for by in range(bh):
        for bx in range(bw):
            off = (by * bw + bx) * block_bytes
            c0, c1, bits = struct.unpack_from("<HHI", data, off + coff)
            colours, punch = _bc_colours(c0, c1, punch_through=alpha is None)
            alphas = None if alpha is None else alpha(data[off:off + 8])
            for py in range(4):
                y = by * 4 + py
                if y >= h:
                    break
                for px in range(4):
                    x = bx * 4 + px
                    if x >= w:
                        break
                    t = py * 4 + px
                    idx = (bits >> (2 * t)) & 3
                    r, g, b = colours[idx]
                    p = (y * w + x) * 3
                    rgb[p] = r; rgb[p + 1] = g; rgb[p + 2] = b
                    if alphas is not None:
                        if not alphas[t]:
                            mask[y * w + x] = 0
                    elif punch and idx == 3:
                        mask[y * w + x] = 0
    return bytes(rgb), bytes(mask)


def _decode_bc1(mip: Mip, _palette=None) -> tuple[bytes, bytes]:
    """BC1 (DXT1): 8-byte blocks, colour only, transparency from the punch-through mode."""
    return _decode_block(mip, block_bytes=8, alpha=None)


def _decode_bc2(mip: Mip, _palette=None) -> tuple[bytes, bytes]:
    """BC2 (DXT3): 16-byte blocks — explicit 4-bit alpha, then BC1's colour block."""
    return _decode_block(mip, block_bytes=16, alpha=_bc2_alpha)


def _decode_bc3(mip: Mip, _palette=None) -> tuple[bytes, bytes]:
    """BC3 (DXT5): 16-byte blocks — interpolated alpha, then BC1's colour block."""
    return _decode_block(mip, block_bytes=16, alpha=_bc3_alpha)

# --- layout detection ----------------------------------------------------------
#
# THE GOVERNING IDEA: the layout is read off the DATA. A mip chain is self-describing, because
# block-compressed formats store ceil(w/4) x ceil(h/4) blocks and therefore FLOOR at one block
# (an 8-byte or 16-byte tail), while linear formats keep scaling as w*h*N all the way to 1x1.
# The numeric `Format` code breaks ties and vetoes layouts we cannot verify — it never
# contradicts the data and it never sizes a chain. There is deliberately NO per-game format
# table: requiring one would mean a lone `.utx` from an unknown engine could not be decoded,
# which is the whole point of reading the data instead.
#
# Slot numbers are NOT portable, which is why a table would be wrong rather than merely
# inconvenient. Dumped from three installs: Unreal Gold v69 has 8 slots, UED22/227 v69 has 122,
# Deus Ex v68 has 5 — and slot 2 is 8 bytes/px in Unreal Gold (`RGB64`) but 2 bytes/px in 227
# (`R5G6B5`). A hardcoded table would mis-slice real data and then report a bogus size mismatch.

# The SIZE CLASSES a mip chain can fit. `linear{N}` is N bytes per pixel; `bc{B}` is B bytes per
# 4x4 block, so it floors at one block.
_LINEAR_BPP = (1, 2, 3, 4, 8)
_BLOCK_BYTES = (8, 16)

# THE ONE PLACE SLOT SEMANTICS ARE ASSUMED — four slots, and this is not the format table the
# design rejects. It is never used to SIZE a chain; it only (a) breaks a tie among candidates
# the data already fitted and (b) names the codes we cannot decode so they fail honestly. A
# chain the data settles on its own decodes with this map unconsulted.
#
# Justified by all three dumped `ETextureFormat` enums agreeing on exactly these four: Unreal
# Gold `0 P8, 3 DXT1, 6 DXT3, 7 DXT5`; UED22/227 `0 P8, 3 BC1, 6 BC2, 7 BC3`; Deus Ex `0 P8,
# 3 DXT1` and SILENT on 6/7 (five slots), so it cannot contradict. DXT1 = BC1, DXT3 = BC2,
# DXT5 = BC3 — the same four layouts under two vendors' names.
_CODE_TO_CLASS = {0: "linear1", 3: "bc8", 6: "bc16", 7: "bc16"}
_CODE_TO_LAYOUT = {0: "linear1", 3: "bc1", 6: "bc2", 7: "bc3"}

# A size class the data alone can name a concrete layout for. `bc16` is absent on purpose: BC2
# and BC3 have byte-identical sizes and mip chains and differ only in how each block's alpha
# half is encoded, so nothing in the data separates them and only a code can.
_CLASS_TO_LAYOUT = {"linear1": "linear1", "linear2": "linear2", "linear3": "linear3",
                    "linear4": "linear4", "linear8": "linear8", "bc8": "bc1"}


@dataclass(frozen=True)
class Layout:
    """A successful detection. `name` is the concrete pixel layout — `linear1` (P8) …
    `linear8`, `bc1`, `bc2`, `bc3`. `source` is `"data"` when the mip sizes settled it with the
    code unconsulted, or `"format-code"` when the code broke a tie between candidates the data
    had already fitted. There are only those two."""
    name: str
    source: str


@dataclass(frozen=True)
class DetectionFailure:
    """Detection could not name a layout. `case` is one of `no-mip-data`, `unverified-format`,
    `unrecognised-layout`, `size-mismatch`, `ambiguous-alpha`, `ambiguous-layout`."""
    case: str
    detail: str


def _fitting_classes(w: int, h: int, n: int) -> set[str]:
    """Every size class that exactly explains `n` bytes for a `w` x `h` mip."""
    out = set()
    for bpp in _LINEAR_BPP:
        if n == w * h * bpp:
            out.add(f"linear{bpp}")
    for b in _BLOCK_BYTES:
        if n == ((w + 3) // 4) * ((h + 3) // 4) * b:
            out.add(f"bc{b}")
    return out


def detect_layout(mips: list[Mip], *, code: int | None) -> Layout | DetectionFailure:
    """Name the pixel layout of one mip array, from its own sizes plus its own `Format` code.

    PURE, and it knows nothing about which layouts have decoders — that is a separate question
    the caller asks afterwards, and conflating the two is what makes a detector self-
    contradictory. A chain can detect successfully as `linear4` and still not decode.

    `code` is the array's EFFECTIVE format byte — the stored value if the property is present,
    else `0` — or **`None`**, meaning no code is available at all. Production always passes an
    int; `None` is for a caller judging a bare mip array, and it is what makes "detect without
    consulting `Format`" something a test can actually express.

    **The code must be the one belonging to THIS array**: `Format` for `Mips`, `CompFormat` for
    `CompMips`. The two arrays hold different layouts by construction — all 69 measured
    `CompMips` arrays are block-compressed while their `Mips` are P8 — so judging one against
    the other's code sends every one of them down an error branch.

    The rows below are ordered and mutually exclusive by construction.
    """
    # ROW 1 — an array whose every mip is empty. Held here rather than by the caller so that
    # `detect_layout` is callable on any array without a pre-check.
    if not mips or not any(m.data for m in mips):
        return DetectionFailure("no-mip-data", f"{len(mips)} mips, none carrying pixel data")

    # ROW 2 — THE VETO, and it is checked before anything looks at the data. A code naming a
    # slot outside the four-slot map stops the decode EVEN WHEN THE DATA FITS EXACTLY ONE
    # LAYOUT. That is not pedantry: 227's slot 8 is `TEXF_BC4`, a single-channel 8-byte-block
    # format whose mip chain is byte-for-byte the size of BC1's and fits `bc8` uniquely. A
    # "unique fit always wins" decoder would draw a BC4 texture as BC1 — a confident wrong
    # image on a file whose own code says it is not BC1. Slot 9 collides the same way, slots
    # 10/11 collide with `bc16`. Measured firing rate on real content: zero.
    if code is not None and code not in _CODE_TO_CLASS:
        return DetectionFailure(
            "unverified-format",
            f"Format code {code} names no layout this build has verified; refusing to guess "
            f"even though the data would fit "
            f"{sorted(_fitting_classes(mips[0].width, mips[0].height, len(mips[0].data)))}")

    first = mips[0]
    fits0 = _fitting_classes(first.width, first.height, len(first.data))
    # ROW 3 — nothing explains mip 0 at all.
    if not fits0:
        per_px = len(first.data) / max(1, first.width * first.height)
        return DetectionFailure(
            "unrecognised-layout",
            f"mip 0 is {first.width}x{first.height} with {len(first.data)} bytes "
            f"({per_px:g} bytes/px), which fits no layout (code {code})")

    # ROW 4 — mip 0 fits something but the chain is internally inconsistent. Distinct from row
    # 3 on purpose: this file is CORRUPT in a specific mip, and the message names which.
    candidates = set(fits0)
    for j, m in enumerate(mips[1:], start=1):
        got = _fitting_classes(m.width, m.height, len(m.data))
        if not candidates & got:
            return DetectionFailure(
                "size-mismatch",
                f"mip {j} ({m.width}x{m.height}, {len(m.data)} bytes) fits {sorted(got)}, "
                f"which contradicts mip 0's {sorted(candidates)}")
        candidates &= got

    if len(candidates) == 1:
        only = next(iter(candidates))
        # ROW 5 — one candidate, and it is the 16-byte block class. BC2 and BC3 are identical
        # in size and differ only in their alpha encoding, so ONLY the code can separate them.
        # This is the design's stated limit on universality: a BC2/BC3 file that stores no
        # Format code does not decode, and never gets a coin flip.
        if only == "bc16":
            if code in (6, 7):
                return Layout(_CODE_TO_LAYOUT[code], "format-code")
            return DetectionFailure(
                "ambiguous-alpha",
                f"a 16-byte-block chain, but code {code} does not say whether the alpha is "
                f"BC2's explicit 4-bit values or BC3's interpolated endpoints; these are "
                f"byte-identical in size and nothing in the data separates them")
        # ROW 6 — one candidate, and the data settles it with the CODE UNCONSULTED. This is
        # what lets a foreign code-less BC1 file decode. It is also where an uncoded `bc8`
        # chain is taken for BC1 BY ASSUMPTION: the data cannot tell BC1 from BC4, and what is
        # really assumed is that no writer emits a non-BC1 8-byte-block chain while omitting
        # `Format` (a genuine BC4 export has Format=8, which row 2 vetoes).
        return Layout(_CLASS_TO_LAYOUT[only], "data")

    # ROW 7 — two or more candidates, and the code names one of them. Not an edge case: 45.8 %
    # of the measured corpus fits two or more layouts, because a w x h mip with w*h bytes is
    # byte-identically explained by P8 and by BC2/BC3 whenever both dimensions are multiples of
    # 4. The tiebreaker is almost always the IMPLIED 0 rather than a stored byte — a `Format`
    # property is physically present on 11 of 18,176 texture exports.
    if code is not None and _CODE_TO_CLASS.get(code) in candidates:
        return Layout(_CODE_TO_LAYOUT[code], "format-code")

    # ROW 8 — a real choice the data left open and nothing legitimate breaks. Say so rather
    # than guess. Measured frequency on real content: zero, because P8 is a fitted candidate in
    # every ambiguous chain that stores no code, so the implied 0 always resolves it.
    return DetectionFailure(
        "ambiguous-layout",
        f"the chain fits {sorted(candidates)} and code {code} names none of them")
