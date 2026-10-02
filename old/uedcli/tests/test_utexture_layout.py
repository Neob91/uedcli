"""Layout detection — reading a texture's pixel layout off its own mip chain.

THE IDEA. A mip chain is self-describing. Block-compressed formats store
`ceil(w/4) x ceil(h/4)` blocks, so their chains FLOOR at one block (an 8- or 16-byte tail);
linear formats keep scaling as `w*h*N` all the way to 1x1. The numeric `Format` code breaks
ties and vetoes layouts we have not verified — it never contradicts the data and it never
sizes a chain. There is no per-game format table, because requiring one would mean a lone
`.utx` from an unknown engine could not be decoded at all, which is the point of the exercise.

TWO SEPARATE QUESTIONS, and conflating them is the trap. `detect_layout` names the layout;
whether a DECODER exists for it is asked afterwards. A chain can detect successfully as
`linear4` and still fail to decode — and the error then says what the file actually is.

`code` is the array's EFFECTIVE format byte (the stored value if the property is present, else
`0`) or `None`, meaning *no code is available at all*. Production always passes an int; `None`
is for a caller judging a bare mip array, and it is what makes "detect without consulting
`Format`" checkable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from uedcli import utexture
from uedcli.tests import pkgfixture
from uedcli.tests.conftest import install_root, ued22_root
from uedcli.utexture import (DecodedTexture, DetectionFailure, Layout, TextureError,
                             TextureResolver, decode_texture, detect_layout, load_package,
                             textures)


def _mips(chain):
    return [utexture.Mip(w, h, data) for (w, h, data) in chain]


def _tracked(package: str, name: str):
    """One named texture out of the git-tracked `uned/UED22` corpus, as a `TextureObj`."""
    pkg = load_package(str(ued22_root() / package))
    for i in textures(pkg):
        if pkg.names[pkg.exports[i]["nm"]].casefold() == name.casefold():
            return decode_texture(pkg, i)
    raise AssertionError(f"{package} no longer carries a texture named {name}")


def _write(tmp_path, stem, **kw) -> str:
    p = Path(tmp_path) / f"{stem}.utx"
    p.write_bytes(pkgfixture.texture_package(**kw))
    return str(p)


# --- the tiebreak, over real tracked content ----------------------------------------

def test_a_truncated_chain_is_ambiguous_and_the_code_breaks_the_tie():
    """`uwindow.u:WhiteTexture` is 32x32 → 16x16 → 8x8 → **4x4 and stops**. Every level is
    byte-identically explained by P8 (`w*h`) and by a 16-byte block layout
    (`(w/4)*(h/4)*16 == w*h` whenever both dimensions are multiples of 4), so the data alone
    cannot decide — the chain never descends below one block, which is where a block layout
    would give itself away.

    Its effective code is 0 (no `Format` property is written, and UE1 omits any property equal
    to its class default, so an absent one IS the byte 0 = P8). That names a FITTED candidate,
    so it resolves — `layout_source == "format-code"`. This is not an edge case: 1,137 of the
    1,998 tracked textures fit two or more layouts.
    """
    t = _tracked("uwindow.u", "WhiteTexture")
    assert [(m.width, m.height) for m in t.mips] == [(32, 32), (16, 16), (8, 8), (4, 4)]
    assert detect_layout(t.mips, code=None) == DetectionFailure(
        "ambiguous-layout",
        "the chain fits ['bc16', 'linear1'] and code None names none of them")
    assert detect_layout(t.mips, code=0) == Layout("linear1", "format-code")


def test_a_single_mip_is_ambiguous_between_p8_and_the_8_byte_block_layout():
    """`DeusExUI.u:HUDItemsBorder_Center` is one 64x2 mip of 128 bytes. P8 says `64*2 = 128`;
    BC1 says `ceil(64/4)*ceil(2/4)*8 = 16*1*8 = 128`. The collision happens for any
    non-4-aligned dimension, and the code resolves it the same way."""
    t = _tracked("DeusExUI.u", "HUDItemsBorder_Center")
    assert [(m.width, m.height, len(m.data)) for m in t.mips] == [(64, 2, 128)]
    assert detect_layout(t.mips, code=None).case == "ambiguous-layout"
    assert "bc8" in detect_layout(t.mips, code=None).detail
    assert detect_layout(t.mips, code=0) == Layout("linear1", "format-code")


def test_a_chain_reaching_one_by_one_is_settled_by_the_data_alone():
    """A P8 chain that descends to 1x1 has a 1-byte tail, which no block layout can produce
    (the smallest block is 8 bytes). So the data settles it, `layout_source == "data"`, and
    **`code=None` gives the same answer as `code=0`** — that identity IS the "detect without
    consulting `Format`" criterion, and it is checkable because `None` is a real value of the
    parameter."""
    t = _tracked("DeusExCharacters.u", "GrayTex1")           # 9 mips, 256x256 down to 1x1
    assert (t.mips[-1].width, t.mips[-1].height) == (1, 1) and len(t.mips[-1].data) == 1
    assert detect_layout(t.mips, code=0) == Layout("linear1", "data")
    assert detect_layout(t.mips, code=None) == detect_layout(t.mips, code=0)


# --- the block classes ---------------------------------------------------------------

def test_a_chain_flooring_at_eight_bytes_is_the_eight_byte_block_layout():
    """Settled by the data with the code UNCONSULTED — which is what lets a foreign, code-less
    BC1 file decode at all."""
    got = detect_layout(_mips(pkgfixture.bc_chain(64, 64, 8)), code=None)
    assert got == Layout("bc1", "data")


def test_a_chain_flooring_at_sixteen_bytes_with_no_usable_code_is_ambiguous_alpha():
    """**THE STATED LIMIT ON UNIVERSALITY.** BC2 and BC3 have byte-identical sizes and mip
    chains and differ only in how each block's alpha half is encoded, so nothing in the data
    separates them and only a `Format` code of 6 or 7 can. A 16-byte-block file that stores no
    code returns a named error and NO PIXELS — never a coin flip, never "BC3 is commoner".

    This is not a corner the implementation has not reached: there is no future measurement
    that fixes it. The other half of the claim, which is what keeps it honest: a code-less BC1
    file whose chain fits the 8-byte class UNIQUELY does decode (the test above).
    """
    chain = _mips(pkgfixture.bc_chain(64, 64, 16))
    assert detect_layout(chain, code=None).case == "ambiguous-alpha"
    assert detect_layout(chain, code=0).case == "ambiguous-alpha"   # the implied P8 names no
    assert detect_layout(chain, code=6) == Layout("bc2", "format-code")
    assert detect_layout(chain, code=7) == Layout("bc3", "format-code")


# --- the veto ------------------------------------------------------------------------

def test_the_veto_pair_one_keyword_two_answers(tmp_path):
    """THE reason detection is shaped this way. The SAME chain, differing only in whether a
    `Format` byte is stored:

    * no code — a foreign, code-less BC1 file — DETECTS as `bc1` from the data.
    * `Format = 8` — 227's `TEXF_BC4`, a single-channel 8-byte-block format whose mip chain is
      byte-for-byte the size of BC1's — is VETOED, with no pixels, **even though the data fits
      exactly one layout**. Without the veto a BC4 texture is drawn as BC1: a confident wrong
      image on a file whose own code says it is not BC1.

    Without this pair the veto could be deleted and no test would go red.
    """
    chain = _mips(pkgfixture.bc_chain(64, 64, 8))
    assert detect_layout(chain, code=None) == Layout("bc1", "data")
    vetoed = detect_layout(chain, code=8)
    assert isinstance(vetoed, DetectionFailure) and vetoed.case == "unverified-format"
    assert "8" in vetoed.detail

    # And end to end through the resolver, where the stored byte comes off the file.
    coded = _write(tmp_path, "Bc4", mips=pkgfixture.bc_chain(64, 64, 8), fmt=8)
    got = TextureResolver([coded]).resolve("Bc4.Fixture")
    assert isinstance(got, TextureError) and got.case == "unverified-format"


def test_the_veto_beats_a_unique_fit_even_before_the_data_is_looked_at():
    """Ordering matters: the veto is checked ahead of every fit row, so nothing can reach
    around it by fitting well. A chain that fits `linear4` uniquely and stores code 5 (a real
    slot in some engine, unsampled by us) is vetoed rather than detected."""
    chain = _mips(pkgfixture.linear_chain(16, 16, 4))
    assert detect_layout(chain, code=None) == Layout("linear4", "data")
    assert detect_layout(chain, code=5).case == "unverified-format"


# --- detection vs decodability -------------------------------------------------------

def test_detection_succeeds_and_decoding_fails_for_a_layout_with_no_decoder(tmp_path):
    """The distinction that resolves the design's oldest self-contradiction. A chain fitting
    `linear4` uniquely with no stored code:

    * DETECTION succeeds — `linear4`, from the data.
    * DECODING fails — `unverified-format`, because no verified decoder exists for it.

    Both halves are asserted: a test that only checked the error would not notice detection
    silently failing, and the whole value of separating them is that the message can say
    "this is a 4 bytes/pixel linear texture we cannot decode" instead of "unknown".
    """
    chain = _mips(pkgfixture.linear_chain(16, 16, 4))
    assert detect_layout(chain, code=0) == Layout("linear4", "data")

    path = _write(tmp_path, "Lin4", mips=pkgfixture.linear_chain(16, 16, 4))
    got = TextureResolver([path]).resolve("Lin4.Fixture")
    assert isinstance(got, TextureError) and got.case == "unverified-format"
    assert "linear4" in got.detail and "4 bytes/px" in got.detail


def test_a_stored_zero_and_an_absent_format_property_behave_identically(tmp_path):
    """**No stored-vs-defaulted distinction, anywhere.** UE1 omits any property equal to its
    class default, so an absent `Format` is not a missing code — it IS the byte 0, `TEXF_P8`,
    a real claim. A design that treated a written 0 as stronger than an implied one would be
    the deleted `format-disagreement` creeping back; asserting the identity is what stops it.

    Checked on an AMBIGUOUS chain, where the code is actually load-bearing — on a chain the
    data settles the code is never consulted and the identity would hold vacuously.
    """
    ambiguous = pkgfixture.linear_chain(16, 16, 1)[:1]        # a single 4-aligned mip
    stored = TextureResolver([_write(tmp_path, "Stored", mips=ambiguous, fmt=0)])
    implied = TextureResolver([_write(tmp_path, "Implied", mips=ambiguous)])
    a = stored.resolve("Stored.Fixture")
    b = implied.resolve("Implied.Fixture")
    assert isinstance(a, DecodedTexture) and isinstance(b, DecodedTexture)
    assert (a.layout, a.layout_source, a.format_code) == \
           (b.layout, b.layout_source, b.format_code) == ("linear1", "format-code", 0)
    assert a.rgb == b.rgb


# --- the failure cases, distinguished -------------------------------------------------

def test_an_empty_chain_is_no_mip_data_and_detection_never_indexes_it():
    """A procedural texture (`FireTexture` and friends) serializes mips whose `DataCount` is 0.
    Detection holds this line itself rather than leaving it to the caller, so it is callable on
    any array — an empty chain would otherwise index mip 0 of an empty list and raise."""
    assert detect_layout([], code=0).case == "no-mip-data"
    assert detect_layout(_mips([(64, 64, b"")]), code=0).case == "no-mip-data"


def test_the_firetexture_shape_is_no_mip_data_not_corrupt_body(tmp_path):
    """Zero-length mip data AND trailing bytes past the mip array — `FireTexture` trails a
    `TArray<FSpark>`. The empty pixels are decided first, so the two conditions do not race,
    and this reads the parser's already-recorded fields rather than re-opening it."""
    path = _write(tmp_path, "Fire", mips=[(64, 64, b"")], trailing=b"\x01" * 24)
    got = TextureResolver([path]).resolve("Fire.Fixture")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"


def test_unrecognised_layout_and_size_mismatch_are_different_answers():
    """One file is in a layout we have no size rule for; the other is internally inconsistent.
    Splitting them is the whole reason the rule is written down: the fixes differ."""
    nothing_fits = detect_layout(_mips([(8, 8, bytes(63))]), code=0)
    assert nothing_fits.case == "unrecognised-layout"
    inconsistent = detect_layout(_mips([(8, 8, bytes(64)), (4, 4, bytes(63))]), code=0)
    assert inconsistent.case == "size-mismatch" and "mip 1" in inconsistent.detail


def test_ambiguous_layout_is_reachable_from_a_real_package(tmp_path):
    """Not just from `detect_layout(code=None)` — a package on disk can produce it.

    A single 2x2 mip of 8 bytes fits `linear2` (2·2·2) and `bc8` (1 block × 8) and nothing
    else; the effective code is the implied `0`, which names P8, and P8 is not a candidate. So
    nothing legitimate breaks the tie and the answer is a named error rather than a guess.

    Measured frequency on real content: **zero** — P8 is a fitted candidate in every ambiguous
    chain that stores no code, which is why the implied 0 always resolves them. Reachable is
    not the same as occurring, and this pins the branch that would otherwise never run.
    """
    path = _write(tmp_path, "Amb", mips=[(2, 2, bytes(8))])
    got = TextureResolver([path]).resolve("Amb.Fixture")
    assert isinstance(got, TextureError) and got.case == "ambiguous-layout"
    assert "bc8" in got.detail and "linear2" in got.detail


def test_ambiguous_layout_is_not_ambiguous_alpha():
    """Two different shapes of "we will not guess". `ambiguous-layout` is several candidate
    layouts and no code naming one of them; `ambiguous-alpha` is ONE candidate with two
    possible decoders. Measured frequency of the first on real content: zero, because P8 is a
    fitted candidate in every ambiguous chain that stores no code."""
    two_candidates = detect_layout(_mips([(32, 32, bytes(1024))]), code=None)
    assert two_candidates.case == "ambiguous-layout"
    one_candidate = detect_layout(_mips(pkgfixture.bc_chain(64, 64, 16)), code=None)
    assert one_candidate.case == "ambiguous-alpha"


# --- integration: the only real stored-code samples on this machine --------------------

@pytest.mark.integration
def test_the_three_real_single_mip_block_textures_resolve_via_their_code():
    """The corpus's ONLY textures whose ambiguity is broken by a genuinely STORED code. All
    three live in the Unreal Gold install, which is gitignored, so every stored-code assertion
    that runs by default is synthesized instead."""
    root = install_root().parent / "Unreal"
    import os
    env = os.environ.get("UEDCLI_TEST_UNREAL_INSTALL")
    if env:
        root = Path(env)
    if not root.exists():
        pytest.skip(f"no Unreal install at {root} (set UEDCLI_TEST_UNREAL_INSTALL)")
    cases = [("Maps/DmRiot.unr", "SolModifié"), ("Maps/DmRiot.unr", "Flotte"),
             ("Maps/DMBeyondTheSun.unr", "Uebergang3")]
    for rel, name in cases:
        pkg = load_package(str(root / rel))
        idx = next(i for i in textures(pkg)
                   if pkg.names[pkg.exports[i]["nm"]] == name)
        t = decode_texture(pkg, idx)
        assert t.fmt == 7, (rel, name, t.fmt)
        assert len(t.mips) == 1, (rel, name)
        assert detect_layout(t.mips, code=t.fmt) == Layout("bc3", "format-code")
