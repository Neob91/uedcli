"""Block-compressed decode (BC1 today) against an INDEPENDENT oracle, plus array selection.

WHY AN ORACLE AT ALL. A synthesized fixture only ever proves that our decoder agrees with our
own encoder — it passes just as happily when both are wrong the same way. Two independent
oracles are used instead:

* **Pillow's DDS decoder** (12.3.0, already the repo's only runtime dependency) for
  byte-exactness over blocks we construct. Its conventions are pinned below because
  byte-exactness only means something once they are: RGB565 → 888 by BIT REPLICATION
  (`(v<<3)|(v>>2)`), and the plain integer `(2a+b)//3` for the 1/3 and 2/3 interpolants.
* **the `CompMips` pair** in `UccCompMips.utx` — the same picture stored twice, as a P8 chain
  built by the game's own `ucc make` and as DXT1 blocks written by Pillow. Comparing our BC1
  decode against the P8 copy tests our decoder against someone else's compressor.

READ THIS BEFORE TRUSTING THE TOLERANCE CHECK. The ≤ 8/255 mean-absolute-error bound catches
LAYOUT and ENDPOINT errors only. Measured on this fixture: a colour-endianness swap scores 98.0
(34.6x) and a c0/c1 endpoint swap 40.7 (14.4x) — but **an index bit-offset off by one scores
4.801 and PASSES**, because shifted index bits still select from the same four per-block
colours, so the error stays bounded by intra-block variation. The load-bearing check for index
decoding is therefore the BYTE-EXACT comparison against Pillow, not the tolerance. And the
tolerance is valid at MIP 0 ONLY: per-level agreement degrades to 53–60 by 8x8, because a
downsampled image carries detail at or below the 4x4 block size.
(`dev/docs/spikes/2026-07-26-ucc-texture-fixture/findings.md` §5–6.)
"""
from __future__ import annotations

import io
import struct
from pathlib import Path

import pytest
from PIL import Image

from uedcli import utexture
from uedcli.tests import pkgfixture
from uedcli.utexture import (DecodedTexture, Mip, TextureError, TextureResolver,
                             decode_palette, decode_texture, export_index_of_ref,
                             load_package, mip0_to_rgb, textures)

FIXTURES = Path(__file__).parent / "fixtures"
COMPMIPS = str(FIXTURES / "UccCompMips.utx")


# --- the Pillow oracle ----------------------------------------------------------------

def _dds(w: int, h: int, blocks: bytes) -> bytes:
    """Wrap raw DXT1 blocks in the minimal 128-byte DDS header Pillow needs for one surface."""
    hdr = bytearray(128)
    hdr[0:4] = b"DDS "
    struct.pack_into("<IIIIII", hdr, 4, 124,
                     0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, h, w, len(blocks), 0)
    struct.pack_into("<I", hdr, 28, 1)                     # dwMipMapCount
    struct.pack_into("<II", hdr, 76, 32, 0x4)              # pixelformat size, DDPF_FOURCC
    hdr[84:88] = b"DXT1"
    struct.pack_into("<I", hdr, 108, 0x1000)               # DDSCAPS_TEXTURE
    return bytes(hdr) + blocks


def _pillow_bc1(w: int, h: int, blocks: bytes) -> tuple[bytes, bytes]:
    """Pillow's own decode of the same blocks → `(rgb, mask)` in our conventions."""
    raw = Image.open(io.BytesIO(_dds(w, h, blocks))).convert("RGBA").tobytes()
    return (bytes(b for i in range(0, len(raw), 4) for b in raw[i:i + 3]),
            bytes(1 if raw[i + 3] else 0 for i in range(0, len(raw), 4)))


def _block(c0: int, c1: int, bits: int) -> bytes:
    return struct.pack("<HHI", c0, c1, bits)


def test_pillow_expands_rgb565_by_bit_replication_not_rounding():
    """PINS THE ORACLE'S CONVENTION, because byte-exactness against it is meaningless
    otherwise. 5- and 6-bit channels are widened by copying the high bits down into the low
    ones, NOT by `round(v * 255 / max)` — the two differ on many values, and if Pillow ever
    changed this the block tests below would fail for a reason that is not our bug."""
    for v in range(32):                                    # every 5-bit red value
        rgb, _ = _pillow_bc1(4, 4, _block(v << 11, v << 11, 0))
        assert rgb[0] == (v << 3) | (v >> 2), v
    for v in range(64):                                    # every 6-bit green value
        rgb, _ = _pillow_bc1(4, 4, _block(v << 5, v << 5, 0))
        assert rgb[1] == (v << 2) | (v >> 4), v


def test_pillow_uses_integer_thirds_for_the_interpolants():
    """White and black endpoints give 170 and 85, i.e. the plain integer `(2a+b)//3`."""
    rgb, _ = _pillow_bc1(4, 4, _block(0xFFFF, 0x0000, 0b11100100))
    assert rgb[0:12] == bytes([255, 255, 255, 0, 0, 0, 170, 170, 170, 85, 85, 85])


# --- our BC1 decode, byte-exact against it --------------------------------------------

@pytest.mark.parametrize("c0,c1,bits", [
    (0xFFFF, 0x0000, 0b11100100),                          # four-colour mode, all four indices
    (0x0000, 0xFFFF, 0b11100100),                          # PUNCH-THROUGH mode (c0 <= c1)
    (0xF800, 0x001F, 0x1B1B1B1B),                          # saturated red / blue endpoints
    (0x07E0, 0x07E0, 0xFFFFFFFF),                          # c0 == c1: punch-through, flat
    (0xABCD, 0x1234, 0x89ABCDEF),                          # arbitrary
])
def test_one_block_decodes_byte_exactly_against_pillow(c0, c1, bits):
    blocks = _block(c0, c1, bits)
    assert utexture._decode_bc1(Mip(4, 4, blocks)) == _pillow_bc1(4, 4, blocks)


def test_the_punch_through_mode_yields_a_transparent_texel():
    """When `c0 <= c1` a BC1 block carries only three colours and index 3 is transparent
    black. The mask comes from that, and from nothing else — never from the texture's
    `bMasked` flag, which is engine render policy the pixel layer does not own."""
    blocks = _block(0x0000, 0xFFFF, 0b11000000)            # texel 3 = index 3
    rgb, mask = utexture._decode_bc1(Mip(4, 4, blocks))
    assert mask[3] == 0 and mask[0] == 1
    assert rgb[9:12] == b"\x00\x00\x00"
    p_rgb, p_mask = _pillow_bc1(4, 4, blocks)
    assert (rgb, mask) == (p_rgb, p_mask)


def test_the_four_colour_mode_is_fully_opaque():
    blocks = _block(0xFFFF, 0x0000, 0xFFFFFFFF)            # every texel index 3
    _rgb, mask = utexture._decode_bc1(Mip(4, 4, blocks))
    assert set(mask) == {1}


@pytest.mark.parametrize("w,h", [(8, 2), (4, 1), (2, 1), (1, 1), (2, 2), (12, 4), (5, 3)])
def test_partial_blocks_are_clipped_to_the_mips_real_size(w, h):
    """A block chain is stored as `ceil(w/4) x ceil(h/4)` WHOLE blocks, so the last block of a
    non-4-aligned mip carries texels that do not exist. Writing `bw * 4` pixels per row instead
    of `w` gives a buffer of the wrong length and shears the image — so the BUFFER LENGTH is
    asserted, not just the pixels. These shapes are live in real content: every DXT1 chain that
    reaches 1x1 passes through 8x2, 4x1 and 2x1."""
    nblocks = ((w + 3) // 4) * ((h + 3) // 4)
    blocks = b"".join(_block(0xF800 + i, 0x001F, 0x1B1B1B1B) for i in range(nblocks))
    rgb, mask = utexture._decode_bc1(Mip(w, h, blocks))
    assert len(rgb) == w * h * 3 and len(mask) == w * h
    assert (rgb, mask) == _pillow_bc1(w, h, blocks)


# --- the committed fixture: our decoder vs someone else's compressor -------------------

def _fixture_arrays():
    pkg = load_package(COMPMIPS)
    t = decode_texture(pkg, textures(pkg)[0])
    pal = decode_palette(pkg, export_index_of_ref(pkg, t.palette_ref))
    return t, pal


def test_the_two_arrays_of_one_texture_detect_as_different_layouts():
    """ONE texture, TWO arrays, TWO layouts, and neither array's code interfering with the
    other's. `Format` describes `Mips` and `CompFormat` describes `CompMips`; judging the
    compressed array against the original's code would send all 69 measured `bHasComp`
    textures — the ones this work exists to fix — down an error branch, because their `Mips`
    code names P8 and P8 is not a candidate for a block chain."""
    t, _pal = _fixture_arrays()
    assert utexture.detect_layout(t.mips, code=t.fmt) == utexture.Layout("linear1", "data")
    assert utexture.detect_layout(t.comp_mips, code=t.comp_format) == \
        utexture.Layout("bc1", "data")


def test_the_fixtures_dxt1_chain_decodes_byte_exactly_against_pillow_at_every_mip():
    """THE LOAD-BEARING CHECK for index decoding — the one the tolerance below cannot make.
    Every level, including the 2x2 and 1x1 partial blocks."""
    t, _pal = _fixture_arrays()
    for m in t.comp_mips:
        assert utexture._decode_bc1(m) == _pillow_bc1(m.width, m.height, m.data), \
            (m.width, m.height)


def test_our_bc1_decode_agrees_with_uccs_p8_copy_of_the_same_picture():
    """The independent-compressor cross-check: our BC1 decode of Pillow's blocks against UCC's
    own P8 build of the same artwork. Mean absolute channel error ≤ 8/255 — measured 2.831 on
    this fixture.

    MIP 0 ONLY. Agreement degrades to 53–60 by 8x8 because a downsampled image carries detail
    at or below the 4x4 block size, so a *correct* decode diverges there; a per-level bound
    would have to be per-level and below 16x16 no useful bound exists for this artwork.

    And this bound does NOT certify the decode. It separates layout and endpoint errors by
    14–35x, but an index bit-offset bug scores 4.801 and passes it. The byte-exact test above
    is what covers that class.
    """
    t, pal = _fixture_arrays()
    ours, _mask = utexture._decode_bc1(t.comp_mips[0])
    p8 = mip0_to_rgb(t.mips[0], pal)
    assert len(ours) == len(p8)
    err = sum(abs(a - b) for a, b in zip(ours, p8)) / len(p8)
    assert err <= 8.0, err
    assert 2.0 < err < 4.0, f"the fixture's measured 2.831 moved to {err}"


# --- array selection: a defined procedure, not a preference ----------------------------

def _pkg(tmp_path, stem, **kw) -> str:
    p = Path(tmp_path) / f"{stem}.utx"
    p.write_bytes(pkgfixture.texture_package(**kw))
    return str(p)


def test_selection_prefers_mips_when_it_carries_data(tmp_path):
    """`Mips` is the original and `CompMips` a lossy copy, so the original wins."""
    path = _pkg(tmp_path, "Both", mips=pkgfixture.linear_chain(8, 8),
                comp_mips=pkgfixture.bc_chain(8, 8))
    got = TextureResolver([path]).resolve("Both.Fixture")
    assert isinstance(got, DecodedTexture)
    assert got.array == "mips" and got.layout == "linear1"


@pytest.mark.parametrize("shape", ["empty-array", "empty-mips"])
def test_the_two_absent_mips_shapes_are_one_rule(tmp_path, shape):
    """An array CARRIES DATA iff it is non-empty AND at least one mip has bytes. A zero-length
    `Mips` array and a `Mips` array whose mips are all zero-length are therefore treated
    identically — "`Mips` is absent" is not a concept this decoder has, and both fall through
    to the compressed copy."""
    mips = [] if shape == "empty-array" else \
        [(w, h, b"") for (w, h, _) in pkgfixture.linear_chain(8, 8)]
    path = _pkg(tmp_path, f"Fall{shape.replace('-', '')}", mips=mips,
                comp_mips=pkgfixture.bc_chain(8, 8))
    got = TextureResolver([path]).resolve(f"Fall{shape.replace('-', '')}.Fixture")
    assert isinstance(got, DecodedTexture)
    assert got.array == "comp-mips" and got.layout == "bc1"


def test_neither_array_carrying_data_is_no_mip_data_with_no_exception(tmp_path):
    """Detection is never invoked over an empty chain — it would index mip 0 of an empty list
    and raise, and no Python exception may reach the user. Selection runs FIRST and answers
    with the named case."""
    path = _pkg(tmp_path, "Neither", mips=[(8, 8, b"")], comp_mips=[(8, 8, b"")])
    got = TextureResolver([path]).resolve("Neither.Fixture")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"


def test_the_fallback_never_fires_because_mips_FAILED_to_decode(tmp_path):
    """**The fallback fires only on the selection rule.** A `Mips` array that carries data and
    then errors reports ITS error — it does not silently hand back the compressed copy.

    Falling back on any failure would let a real corruption be papered over with a lossy image
    and make the result's provenance unpredictable: the caller could no longer tell whether
    `array == "comp-mips"` meant "there was no original" or "the original was broken". Measured
    cost of the strict rule: zero, since all 69 `bHasComp` textures have a decodable P8 `Mips`.
    """
    path = _pkg(tmp_path, "BadMips",
                mips=[(8, 8, bytes(64)), (4, 4, bytes(63))],       # self-contradicting chain
                comp_mips=pkgfixture.bc_chain(8, 8))
    got = TextureResolver([path]).resolve("BadMips.Fixture")
    assert isinstance(got, TextureError) and got.case == "size-mismatch"


def test_the_pyramid_of_a_block_texture_decodes_every_level(tmp_path):
    """The mip-pyramid accessor is layout-generic: it decodes each level through whatever
    decoder the detected layout named, not through the P8 path."""
    path = _pkg(tmp_path, "BcPyr", mips=[], comp_mips=pkgfixture.bc_chain(16, 16))
    got = TextureResolver([path]).resolve("BcPyr.Fixture")
    assert isinstance(got, DecodedTexture)
    assert [(w, h) for (w, h, _r, _m) in got.mips] == [(16, 16), (8, 8), (4, 4), (2, 2), (1, 1)]
    for (w, h, rgb, mask) in got.mips:
        assert len(rgb) == w * h * 3 and len(mask) == w * h


# --- integration ------------------------------------------------------------------------

@pytest.mark.integration
def test_every_bhascomp_texture_in_the_install_decodes_both_arrays():
    """Over the live install: each `bHasComp` texture's two arrays both decode, and the two
    agree within the same mip-0 bound."""
    from uedcli.tests.conftest import install_root

    root = install_root()
    if not root.exists():
        pytest.skip(f"no install at {root}")
    checked = 0
    for sub in ("System", "Textures", "LUM"):
        for path in sorted((root / sub).rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (".u", ".utx"):
                continue
            try:
                pkg = load_package(str(path))
            except (OSError, ValueError, struct.error, IndexError):
                continue
            for i in textures(pkg):
                try:
                    t = decode_texture(pkg, i)
                except (ValueError, struct.error, IndexError):
                    continue
                if not t.comp_mips or not any(m.data for m in t.mips):
                    continue
                pal_i = export_index_of_ref(pkg, t.palette_ref)
                if pal_i is None or not (0 <= pal_i < len(pkg.exports)):
                    continue
                pal = decode_palette(pkg, pal_i)
                ours, _m = utexture._decode_bc1(t.comp_mips[0])
                p8 = mip0_to_rgb(t.mips[0], pal)
                err = sum(abs(a - b) for a, b in zip(ours, p8)) / max(1, len(p8))
                assert err <= 8.0, (path.name, t.name, err)
                checked += 1
    assert checked == 69, checked


# --- BC2 / BC3: the same colour block, two different alpha halves ----------------------

def _pillow(w: int, h: int, blocks: bytes, fourcc: bytes) -> tuple[bytes, bytes]:
    raw = Image.open(io.BytesIO(_dds16(w, h, blocks, fourcc))).convert("RGBA").tobytes()
    return (bytes(b for i in range(0, len(raw), 4) for b in raw[i:i + 3]),
            bytes(1 if raw[i + 3] else 0 for i in range(0, len(raw), 4)))


def _dds16(w: int, h: int, blocks: bytes, fourcc: bytes) -> bytes:
    hdr = bytearray(_dds(w, h, b""))
    struct.pack_into("<I", hdr, 20, len(blocks))
    hdr[84:88] = fourcc
    return bytes(hdr) + blocks


OPAQUE_BC3_HALF = bytes.fromhex("0005ffffffffffff")
"""The textbook fully-opaque BC3 alpha block, and the one that IDENTIFIES a real file as BC3.

`a0 = 0`, `a1 = 5`, so `a0 <= a1` selects the six-interpolant mode where index 7 is a hard 255;
every one of the sixteen 3-bit indices is 7, so the whole block is opaque. Read as BC2 the same
eight bytes are sixteen explicit nibbles `0,0,0,5,15,15,…` — alpha 0/85/255 noise. That
asymmetry is the evidence: all 4,096 blocks of `DmRiot.unr:Poster01`'s mip 0 carry exactly these
bytes, which is nonsense as BC2 and correct as BC3.
"""

_COLOUR_HALVES = [
    struct.pack("<HHI", 0xFFFF, 0x0000, 0b11100100),
    struct.pack("<HHI", 0x0000, 0xFFFF, 0b11100100),      # c0 <= c1: NO punch-through here
    struct.pack("<HHI", 0xF800, 0x001F, 0x1B1B1B1B),
    struct.pack("<HHI", 0xABCD, 0x1234, 0x89ABCDEF),
]
_ALPHA_HALVES = [
    OPAQUE_BC3_HALF,
    bytes(8),                                             # all zero
    bytes([0xFF] * 8),
    struct.pack("<BB", 255, 0) + bytes([0b00100000, 0b10001100, 0, 0, 0, 0]),   # graded
    bytes.fromhex("0123456789abcdef"),
]


@pytest.mark.parametrize("colour", _COLOUR_HALVES)
@pytest.mark.parametrize("alpha", _ALPHA_HALVES)
@pytest.mark.parametrize("fourcc,decode", [(b"DXT3", utexture._decode_bc2),
                                           (b"DXT5", utexture._decode_bc3)])
def test_bc2_and_bc3_blocks_decode_byte_exactly_against_pillow(colour, alpha, fourcc, decode):
    """Both alpha modes of BC3, a fully-opaque block, a graded-alpha block, an all-zero one,
    and four colour halves — including `c0 <= c1`, which is BC1's punch-through trigger and
    must NOT be one here.

    This compares `(rgb, mask)`, and `mask` is binary — so it pins the colour half exactly and
    the alpha half only down to zero-ness. The alpha VALUES are pinned separately, above.
    """
    blocks = alpha + colour
    assert decode(Mip(4, 4, blocks)) == _pillow(4, 4, blocks, fourcc)


@pytest.mark.parametrize("w,h", [(8, 2), (4, 1), (2, 1), (1, 1), (2, 2), (5, 3)])
@pytest.mark.parametrize("fourcc,decode", [(b"DXT3", utexture._decode_bc2),
                                           (b"DXT5", utexture._decode_bc3)])
def test_bc2_and_bc3_partial_blocks_are_clipped(w, h, fourcc, decode):
    n = ((w + 3) // 4) * ((h + 3) // 4)
    blocks = b"".join(_ALPHA_HALVES[3] + struct.pack("<HHI", 0xF800 + i, 0x001F, 0x1B1B1B1B)
                      for i in range(n))
    rgb, mask = decode(Mip(w, h, blocks))
    assert len(rgb) == w * h * 3 and len(mask) == w * h
    assert (rgb, mask) == _pillow(w, h, blocks, fourcc)


def _pillow_alpha(blocks: bytes, fourcc: bytes) -> list[int]:
    """Pillow's RAW per-texel alpha for one 4x4 block — 0..255, before any reduction."""
    raw = Image.open(io.BytesIO(_dds16(4, 4, blocks, fourcc))).convert("RGBA").tobytes()
    return [raw[i * 4 + 3] for i in range(16)]


@pytest.mark.parametrize("alpha", _ALPHA_HALVES)
@pytest.mark.parametrize("fourcc,fn", [(b"DXT3", utexture._bc2_alpha),
                                       (b"DXT5", utexture._bc3_alpha)])
def test_the_alpha_VALUES_match_pillow_not_merely_their_zero_ness(alpha, fourcc, fn):
    """The alpha readers are checked against Pillow's raw 0..255 channel.

    **The block tests above cannot do this.** They compare `(rgb, mask)`, and `mask` is BINARY —
    one byte per texel, 1 or 0 — so every graded alpha value collapses to "not zero" on both
    sides of the comparison. Two real bugs survive that: BC2's 4-bit widening (`* 17` vs `* 16`,
    which never produces 0 either way) and BC3's eight-value interpolation table (endpoints
    swapped, likewise). Both were verified to leave the suite green before this test existed.

    Nothing is wrong in the shipped output today — the mask is binary by design, recorded in
    board item `bc2-bc3-graded-alpha-is-flattened-to-a-binary`. But whoever widens the mask
    inherits these two paths, and would otherwise inherit them believing they were byte-exact.
    """
    blocks = alpha + _COLOUR_HALVES[0]
    assert fn(blocks[:8]) == _pillow_alpha(blocks, fourcc)


def test_the_same_sixteen_bytes_give_identical_rgb_and_different_alpha():
    """**The shared-colour-block claim, asserted rather than assumed.** BC2 and BC3 differ ONLY
    in how the leading 8 bytes encode alpha; the trailing 8 are the same colour block in both.
    So decoding one block both ways must give identical RGB and different transparency — and if
    the RGB ever differed, the two decoders would have drifted apart in the half they share."""
    blocks = OPAQUE_BC3_HALF + _COLOUR_HALVES[0]
    rgb2, mask2 = utexture._decode_bc2(Mip(4, 4, blocks))
    rgb3, mask3 = utexture._decode_bc3(Mip(4, 4, blocks))
    assert rgb2 == rgb3
    assert mask2 != mask3
    assert set(mask3) == {1}                              # BC3: uniformly opaque
    assert 0 in mask2                                     # BC2: the same bytes are alpha noise


def test_a_sixteen_byte_block_chain_with_no_usable_code_yields_no_pixels(tmp_path):
    """**THE STATED LIMIT ON UNIVERSALITY, end to end.** A BC2 or BC3 texture that stores no
    `Format` code does not decode: it returns `ambiguous-alpha` and no pixels.

    This is not a corner the implementation has not reached. BC2 and BC3 have byte-identical
    sizes and mip chains; nothing in the data separates them, and no future measurement fixes
    that. Guessing BC3 because it is commoner would be right often and silently, unrecoverably
    wrong otherwise — a plausible image with the wrong alpha.

    The honest other half, in the same breath: a code-less BC1 file whose chain fits the 8-byte
    class UNIQUELY does decode, because 8-byte blocks are shared with no other layout we read.
    """
    p = Path(tmp_path) / "NoCode.utx"
    p.write_bytes(pkgfixture.texture_package(mips=pkgfixture.bc_chain(64, 64, 16)))
    got = TextureResolver([str(p)]).resolve("NoCode.Fixture")
    assert isinstance(got, TextureError) and got.case == "ambiguous-alpha"
    assert "BC2" in got.detail and "BC3" in got.detail    # it says WHICH pair it cannot choose


@pytest.mark.parametrize("code,layout", [(6, "bc2"), (7, "bc3")])
def test_a_stored_code_of_six_or_seven_selects_the_alpha_variant(tmp_path, code, layout):
    """The only thing that CAN separate them, doing so end to end through the resolver."""
    p = Path(tmp_path) / f"Alpha{code}.utx"
    p.write_bytes(pkgfixture.texture_package(mips=pkgfixture.bc_chain(16, 16, 16), fmt=code))
    got = TextureResolver([str(p)]).resolve(f"Alpha{code}.Fixture")
    assert isinstance(got, DecodedTexture)
    assert got.layout == layout and got.layout_source == "format-code"
    assert len(got.rgb) == 16 * 16 * 3


# --- the mesh-skin path ------------------------------------------------------------------

@pytest.mark.parametrize("kw,layout", [
    (dict(mips="linear"), "linear1"),
    (dict(mips="bc8"), "bc1"),
    (dict(mips="bc16", fmt=6), "bc2"),
    (dict(mips="bc16", fmt=7), "bc3"),
])
def test_a_mesh_skin_ref_resolves_for_every_format_this_build_adds(tmp_path, kw, layout):
    """A mesh skin reaches the decoder as a `Package.Name` ref with any Group segment dropped —
    that is the whole of the skin path's texture-facing contract, and both committed mesh
    harnesses build exactly that string before calling `resolve`.

    Covered here for EVERY format the build adds, which is the requirement; what is NOT covered
    is an end-to-end mesh render, because no production code resolves skins yet — the only two
    consumers are spike harnesses. Board item
    `no-production-consumer-resolves-mesh-skins-yet` records that gap.
    """
    chain = {"linear": pkgfixture.linear_chain(16, 16),
             "bc8": pkgfixture.bc_chain(16, 16, 8),
             "bc16": pkgfixture.bc_chain(16, 16, 16)}[kw["mips"]]
    p = Path(tmp_path) / "SkinPkg.utx"
    p.write_bytes(pkgfixture.texture_package(name="Skin", mips=chain,
                                             fmt=kw.get("fmt")))
    got = TextureResolver([str(p)]).resolve("SkinPkg.Skin")
    assert isinstance(got, DecodedTexture) and got.layout == layout


def test_an_undecodable_skin_names_the_offending_ref():
    """What the harnesses print. The typed error is deliberately TRUTHY, so a caller that still
    writes `if got:` renders the error object as a skin — which is why both harnesses had to be
    migrated to a type check, and why the error must carry the ref to name in its message."""
    got = TextureResolver([]).resolve("MeshPkg.MissingSkin")
    assert isinstance(got, TextureError)
    assert bool(got) is True                              # truthy: an unmigrated caller breaks
    assert got.ref == "MeshPkg.MissingSkin" and "MeshPkg" in got.detail


def test_neither_committed_mesh_harness_still_treats_a_truthy_error_as_a_skin():
    """A static guard on the two spike harnesses, which `rules/spikes.md` makes durable evidence
    rather than scratch. Both used to do `got = resolve(...)` / `if got:`; a future edit
    reintroducing that would silently rasterize an error object, and no runtime test would
    catch it because the harnesses need a mesh package the suite does not have."""
    harness = (Path(__file__).resolve().parents[2] / "dev" / "docs" / "spikes"
               / "2026-07-25-native-mesh-decode" / "harness")
    for name in ("render.py", "render_class.py"):
        code = [ln.strip() for ln in (harness / name).read_text().splitlines()
                if not ln.lstrip().startswith("#")]
        assert "if got:" not in code, f"{name} still treats a truthy TextureError as a skin"
        assert any("TextureError" in ln for ln in code), \
            f"{name} does not type-check the decode result"


@pytest.mark.integration
def test_the_real_bc3_poster_is_uniformly_opaque_and_carries_the_identifying_alpha_block():
    """The pinned identification, over the only real BC3 content on this machine.

    All 4,096 blocks of `DmRiot.unr:Poster01`'s mip 0 carry the alpha half
    `0005ffffffffffff`. Decoded as BC3 that is uniformly opaque; decoded as BC2 the same eight
    bytes are alpha 0/85/255 noise. One distinct value across a whole 256x256 mip is nonsense
    for explicit per-texel alpha and exactly what a fully-opaque BC3 export looks like — which
    is the evidence that slot 7 is BC3 and not BC2.
    """
    import os

    root = Path(os.environ.get("UEDCLI_TEST_UNREAL_INSTALL", "")) if \
        os.environ.get("UEDCLI_TEST_UNREAL_INSTALL") else None
    if root is None or not root.exists():
        pytest.skip("set UEDCLI_TEST_UNREAL_INSTALL to the Unreal install root")
    pkg = load_package(str(root / "Maps" / "DmRiot.unr"))
    i = next(j for j in textures(pkg) if pkg.names[pkg.exports[j]["nm"]] == "Poster01")
    t = decode_texture(pkg, i)
    assert t.fmt == 7
    halves = {t.mips[0].data[b * 16:b * 16 + 8] for b in range(len(t.mips[0].data) // 16)}
    assert halves == {OPAQUE_BC3_HALF}, len(halves)
    _rgb, mask = utexture._decode_bc3(t.mips[0])
    assert set(mask) == {1}


@pytest.mark.integration
def test_the_largest_real_block_texture_decodes_in_bounded_memory():
    """`UnrealShare.u:TranslatorHUDHD` is 2048x2048 with 12 mips — the stress case. It must
    decode end to end without an exception and without the caps refusing it."""
    import os

    root = Path(os.environ.get("UEDCLI_TEST_UNREAL_INSTALL", "")) if \
        os.environ.get("UEDCLI_TEST_UNREAL_INSTALL") else None
    if root is None or not root.exists():
        pytest.skip("set UEDCLI_TEST_UNREAL_INSTALL to the Unreal install root")
    r = TextureResolver([str(root / "System" / "UnrealShare.u")])
    got = r.resolve("UnrealShare.TranslatorHUDHD")
    assert isinstance(got, DecodedTexture)
    assert (got.width, got.height) == (2048, 2048) and got.layout == "bc3"
    assert len(got.mips) == 12
