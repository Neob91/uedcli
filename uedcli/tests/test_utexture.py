"""Offline tests for `uedcli.utexture` — the promoted native texture decoder + the
`Package[.Group].Name` ref resolver.

The pixel expectations are FROZEN sha256 digests of the decoded RGB buffers, banked from
the spike-validated decoder (spike `2026-06-27-decontainerize-uedcli/01-native-texture-
decode.md` proved the decode byte-identical to `UCC batchexport` across the whole Deus Ex
corpus; these fixtures pin that behavior as a regression). Three committed fixture packages
cover both FMipmap layout branches and the two-array body:
  - `LUM_InfoPortraits.utx` — file-version 69 (>= 63: mips carry the lazy-array skip
    offset), one ungrouped 64×64 texture.
  - `CoreTexWater.utx` — file-version 61 (< 63: NO skip offset), two textures in group
    `water` (also exercises group-qualified refs).
  - `UccCompMips.utx` — v69, one texture carrying BOTH mip arrays (a P8 `Mips` chain and a
    DXT1 `CompMips` copy). Our own artwork, assembled by `build_uccfixture.py`; see its
    docstring for the provenance that makes it a usable cross-check.

Shapes no committed package can supply — an empty mip, a dangling palette ref, a stored
`Format` byte, a lying mip count — are synthesized in-test with `pkgfixture`.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest

from uedcli import utexture
from uedcli.tests import pkgfixture
from uedcli.utexture import (DecodedTexture, TextureError, TextureResolver, decode_palette,
                             decode_texture, export_index_of_ref, load_package, mip0_to_rgb,
                             textures)

FIXTURES = Path(__file__).parent / "fixtures"
PORTRAITS = str(FIXTURES / "LUM_InfoPortraits.utx")
WATER = str(FIXTURES / "CoreTexWater.utx")
COMPMIPS = str(FIXTURES / "UccCompMips.utx")


@pytest.fixture(autouse=True)
def _tmp_pkg_dir(tmp_path):
    """Every synthesized package is written under the test's own tmp dir."""
    global _TMP
    _TMP = tmp_path


_TMP: Path | None = None


def _write(buf: bytes, filename: str) -> str:
    """Write synthesized package bytes to the test's tmp dir; return the path.

    The file NAME is load-bearing: `TextureResolver` keys packages by file stem, so a ref
    `Foo.Bar` only finds a package written as `Foo.utx`.
    """
    p = _TMP / filename
    p.write_bytes(buf)
    return str(p)


def _synth(**kw):
    """A loaded `Package` from `pkgfixture.texture_package(**kw)`. Export 0 is the palette,
    export 1 the texture."""
    return load_package(_write(pkgfixture.texture_package(**kw), "Synth.utx"))


def _decode_named(path: str, name: str):
    pkg = load_package(path)
    for i in textures(pkg):
        t = decode_texture(pkg, i)
        if t.name == name:
            pal = decode_palette(pkg, export_index_of_ref(pkg, t.palette_ref))
            return t, mip0_to_rgb(t.mips[0], pal)
    raise AssertionError(f"texture {name} not in {path}")


def test_decode_v69_pixel_exact():
    """v69 fixture (mips WITH skip-offset): frozen size + RGB digest + probe pixels."""
    t, rgb = _decode_named(PORTRAITS, "ArthurCallaway")
    assert (t.mips[0].width, t.mips[0].height) == (64, 64)
    assert len(rgb) == 64 * 64 * 3
    assert hashlib.sha256(rgb).hexdigest() == (
        "6d42e496e6636b838775b6ee9373e7357f1ebd84057baf8b0eae856c1f0a8e16")


def test_decode_v61_pixel_exact():
    """v61 fixture (mips WITHOUT skip-offset — the WidthOffset-era layout branch)."""
    t, rgb = _decode_named(WATER, "dirtywater")
    assert (t.mips[0].width, t.mips[0].height) == (256, 256)
    assert rgb[:3] == bytes.fromhex("2f2a27")            # probe: first pixel
    assert hashlib.sha256(rgb).hexdigest() == (
        "10a7519cd5fd4f7fdca54771defdd364eac01d758cdd268701fcc271bac83a42")


def test_decode_all_mips_reach_eof():
    """Every texture in all three fixtures parses to exactly the declared body end, and the
    single-array ones consume ZERO bytes after `Mips`.

    `trailing_bytes == 0` is the guarantee the old body-to-EOF `raise` used to give, now stated
    positively: the parser reports the overrun instead of raising, so a test has to assert the
    clean case or nothing would notice it going non-zero. `CoreTexWater.utx` is file-version 61,
    where there are no per-mip skip offsets and this is the ONLY integrity signal the format has.
    """
    for path in (PORTRAITS, WATER):
        pkg = load_package(path)
        assert textures(pkg), path
        for i in textures(pkg):
            t = decode_texture(pkg, i)
            assert t.mips, t.name
            assert t.trailing_bytes == 0, (path, t.name, t.trailing_bytes)
            assert t.comp_mips == [], (path, t.name)      # bHasComp absent => nothing after Mips
            assert t.no_mip_data is False, (path, t.name)


# --- CompMips: the second mip array ------------------------------------------------

def test_comp_mips_fixture_parses_both_arrays_to_eof():
    """`UccCompMips.utx` — the two-array shape — parses EOF-clean with BOTH arrays read.

    This is the offline criterion for the bug that motivates the decoder's `CompMips` support:
    a `UTexture` whose `bHasComp` property is true serializes a SECOND mip array right after
    `Mips`, and a parser that stops after the first overruns the body and rejects the texture.
    Before this support the same file raised "texture body not at EOF".

    The fixture is our own artwork, committed: its P8 chain was built by the game's own
    `ucc make` and its DXT1 blocks by Pillow (`dev/docs/spikes/2026-07-26-ucc-texture-fixture/`),
    assembled by `uedcli/tests/build_uccfixture.py`. No game content, so this runs on a bare
    checkout — the live confirmation over `LUM_CoreTex.utx` is integration-tier.
    """
    pkg = load_package(COMPMIPS)
    idx = textures(pkg)
    assert len(idx) == 1
    t = decode_texture(pkg, idx[0])
    assert t.name == "SpikeFixture"
    assert t.trailing_bytes == 0
    assert [(m.width, m.height) for m in t.mips] == \
        [(64, 64), (32, 32), (16, 16), (8, 8), (4, 4), (2, 2), (1, 1)]
    assert [(m.width, m.height) for m in t.comp_mips] == \
        [(64, 64), (32, 32), (16, 16), (8, 8), (4, 4), (2, 2), (1, 1)]
    # DXT1 = 8-byte blocks over ceil(w/4) x ceil(h/4), so the chain FLOORS at one block.
    assert [len(m.data) for m in t.comp_mips] == [2048, 512, 128, 32, 8, 8, 8]
    assert t.fmt == 0 and t.comp_format == 3          # P8 original, DXT1 copy
    assert t.no_mip_data is False


def test_comp_mips_absent_consumes_nothing_after_mips():
    """`CompMips` is gated on the `bHasComp` PROPERTY, not read unconditionally: with the flag
    absent the body ends exactly after `Mips`."""
    pkg = _synth(mips=pkgfixture.linear_chain(8, 8))
    t = decode_texture(pkg, 1)
    assert t.comp_mips == [] and t.trailing_bytes == 0
    assert [m.width for m in t.mips] == [8, 4, 2, 1]


def test_resolve_prefers_the_p8_mips_over_the_compressed_copy():
    """`Mips` is the original and `CompMips` a lossy copy, so the original wins whenever it
    carries data."""
    r = TextureResolver([COMPMIPS])
    got = r.resolve("UccCompMips.SpikeFixture")
    assert isinstance(got, DecodedTexture)
    assert (got.width, got.height) == (64, 64) and len(got.rgb) == 64 * 64 * 3
    assert got.array == "mips"
    # The P8 chain, decoded through the palette — NOT the DXT1 blocks read as palette indices.
    pkg = load_package(COMPMIPS)
    t = decode_texture(pkg, 1)
    pal = decode_palette(pkg, export_index_of_ref(pkg, t.palette_ref))
    assert got.rgb == mip0_to_rgb(t.mips[0], pal)


def test_a_compressed_only_texture_decodes_through_the_fallback():
    """A texture whose `Mips` are all EMPTY while `CompMips` carries DXT1 decodes from the
    compressed copy, and SAYS SO — `array == "comp-mips"`, so a caller can see it was handed
    the lossy image rather than the original.

    This is the shape that made the fallback dangerous before a block decoder existed: the
    selection rule picks `CompMips`, but `t.fmt` is the *Mips* array's code (`0`, P8 implied)
    and `CompFormat` is a different field. Judging the compressed array by the original's code
    would index the palette with DXT1 block bytes and render a confident wrong picture. Each
    array is now judged against its OWN code, which is why this decodes correctly instead.
    """
    empty = [(w, h, b"") for (w, h, _) in pkgfixture.linear_chain(64, 64)]
    pkg_bytes = pkgfixture.texture_package(mips=empty,
                                           comp_mips=pkgfixture.bc_chain(64, 64))
    path = _write(pkg_bytes, "CompOnly.utx")
    t = decode_texture(load_package(path), 1)
    assert t.no_mip_data is False                    # CompMips DOES carry data
    got = TextureResolver([path]).resolve("CompOnly.Fixture")
    assert isinstance(got, DecodedTexture)
    assert got.array == "comp-mips" and got.layout == "bc1"
    assert got.format_code == 3                      # CompFormat, NOT the Mips array's 0
    assert len(got.rgb) == 64 * 64 * 3


# --- the body-integrity report (was a raise) ---------------------------------------

def test_empty_mips_with_trailing_bytes_reports_instead_of_raising():
    """The `FireTexture` shape — zero-length mip data AND trailing bytes past the mip array —
    parses without raising and reports both facts.

    Procedural textures serialize mips whose `DataCount` is 0, and `FireTexture` also trails a
    `TArray<FSpark>`. The old parser raised on the trailing bytes before anything could see the
    empty mips, so the two conditions could not be told apart. They are now separate fields on
    the result and the classification belongs to the caller.
    """
    pkg = _synth(mips=[(64, 64, b"")], trailing=b"\x01" * 24)
    t = decode_texture(pkg, 1)
    assert t.no_mip_data is True
    assert t.trailing_bytes == 24


def test_real_pixel_data_with_trailing_bytes_also_reports_instead_of_raising():
    """The other half: a body with REAL pixel data and the same 24 trailing bytes also parses,
    reporting `no_mip_data is False` — the two shapes are distinguishable, which is the point."""
    pkg = _synth(mips=pkgfixture.linear_chain(8, 8), trailing=b"\x01" * 24)
    t = decode_texture(pkg, 1)
    assert t.no_mip_data is False
    assert t.trailing_bytes == 24


def test_a_texture_with_no_mip_data_is_a_miss_not_a_black_image():
    """THE regression this slice can introduce. Once the parser stops raising, a texture whose
    mips are all empty reaches the `not t.mips` gate — which PASSES, because a list of *empty*
    mips is truthy — and `mip0_to_rgb` returns `w*h*3` zero bytes: a silent, plausible,
    completely black picture rather than a miss.

    So assert both halves: the resolve is a miss, AND specifically not a zero-filled buffer.
    """
    path = _write(pkgfixture.texture_package(mips=[(64, 64, b"")]), "NoData.utx")
    got = TextureResolver([path]).resolve("NoData.Fixture")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"
    assert not isinstance(got, DecodedTexture)       # never the zero buffer, which is truthy


def test_a_texture_with_trailing_bytes_is_a_miss():
    """The integrity guard's EFFECT survives the change from raise to field: a body with real
    pixel data that does not end where the export table says still resolves to a miss."""
    path = _write(pkgfixture.texture_package(mips=pkgfixture.linear_chain(8, 8),
                                             trailing=b"\x01" * 24), "Trailing.utx")
    got = TextureResolver([path]).resolve("Trailing.Fixture")
    assert isinstance(got, TextureError) and got.case == "corrupt-body"


def test_a_skip_offset_mismatch_still_raises():
    """Reporting the body end does NOT weaken the per-mip check. A `WidthOffset` — the absolute
    file offset a mip's data is supposed to end at — that disagrees with where the data actually
    ended is a parse the decoder cannot continue from, so it still raises."""
    path = _write(pkgfixture.texture_package(mips=pkgfixture.linear_chain(8, 8)), "Ok.utx")
    pkg = load_package(path)
    e = pkg.exports[1]
    # The first FMipmap's skip offset is the u32 immediately after the mip COUNT, which itself
    # follows the property list's "None" terminator.
    _props, pos = utexture._read_props(pkg.buf, e["soff"], e["soff"] + e["ssize"], pkg.names)
    _count, pos = utexture._ci(pkg.buf, pos)
    buf = bytearray(pkg.buf)
    buf[pos:pos + 4] = struct.pack("<I", struct.unpack_from("<I", buf, pos)[0] + 1)
    bad = load_package(_write(bytes(buf), "BadSkip.utx"))
    with pytest.raises(ValueError, match="skip-offset mismatch"):
        decode_texture(bad, 1)


def test_load_package_rejects_non_package(tmp_path):
    bad = tmp_path / "NotAPackage.utx"
    bad.write_bytes(b"\x00" * 64)
    with pytest.raises(ValueError, match="bad magic"):
        load_package(str(bad))


# --- TextureResolver -----------------------------------------------------------


def _resolver():
    # Accepts either plain paths or (path, provenance) tuples — exercise both forms.
    return TextureResolver([(PORTRAITS, "project"), WATER])


def test_resolve_two_part_hit():
    got = _resolver().resolve("LUM_InfoPortraits.ArthurCallaway")
    assert isinstance(got, DecodedTexture)
    assert (got.width, got.height) == (64, 64) and len(got.rgb) == 64 * 64 * 3
    assert got.layout == "linear1" and got.format_code == 0 and got.array == "mips"
    assert len(got.mask) == 64 * 64


def test_resolve_group_qualified_hit():
    got = _resolver().resolve("CoreTexWater.water.dirtywater")
    assert isinstance(got, DecodedTexture)
    assert (got.width, got.height) == (256, 256)


def test_resolve_group_mismatch_names_the_group_asked_for():
    """A group mismatch is `unknown-texture`, not a fourth case: from the caller's side the
    package has no texture of that name IN THAT GROUP, and the fix is the same — write a
    different ref. The message names the group so the user can see which one was searched."""
    got = _resolver().resolve("CoreTexWater.wood.dirtywater")
    assert isinstance(got, TextureError) and got.case == "unknown-texture"
    assert "wood" in got.detail


def test_resolve_bare_ref_is_unqualified_ref():
    """A bare (unqualified) ref is REFUSED rather than scanned for across packages — a
    cross-package stem scan is ambiguous, and `assemble._patch_surf_refs` requires the
    qualifier too. The case is distinct from a miss so a caller can tell the user to qualify
    the ref rather than to go looking for the texture."""
    for ref in ("dirtywater", "a.b.c.d"):
        got = _resolver().resolve(ref)
        assert isinstance(got, TextureError) and got.case == "unqualified-ref", ref


def test_resolve_unknown_package_and_unknown_texture_are_different_cases():
    r = _resolver()
    miss_pkg = r.resolve("NoSuchPackage.foo")
    assert isinstance(miss_pkg, TextureError) and miss_pkg.case == "unknown-package"
    assert "NoSuchPackage" in miss_pkg.detail
    miss_tex = r.resolve("CoreTexWater.nosuchtexture")
    assert isinstance(miss_tex, TextureError) and miss_tex.case == "unknown-texture"
    assert "nosuchtexture" in miss_tex.detail


def test_resolve_case_insensitive():
    assert isinstance(_resolver().resolve("coretexwater.WATER.DirtyWater"), DecodedTexture)


def test_resolve_caches_per_instance():
    """Cached BY IDENTITY — the same object, not an equal rebuild. Callers hold on to the
    result and compare it; a rebuilt-but-equal object would also re-decode every mip."""
    r = _resolver()
    first = r.resolve("CoreTexWater.dirtywater")
    assert r.resolve("CoreTexWater.dirtywater") is first
    err = r.resolve("CoreTexWater.nosuchtexture")
    assert r.resolve("CoreTexWater.nosuchtexture") is err    # errors are cached too


def test_resolve_project_shadows_base(tmp_path):
    """First entry per stem wins (the composed list is stem-deduped project-first; the
    resolver must keep that order even when handed duplicate stems)."""
    r = TextureResolver([PORTRAITS, str(tmp_path / "LUM_InfoPortraits.utx")])
    assert isinstance(r.resolve("LUM_InfoPortraits.ArthurCallaway"), DecodedTexture)


def test_an_unreadable_package_is_not_an_absent_one(tmp_path):
    """`package-unreadable` and `unknown-package` were one value until now, and they need
    different fixes: one is a broken file on the path, the other is a file that is not there."""
    bad = tmp_path / "Corrupt.utx"
    bad.write_bytes(b"\x12\x34" * 40)
    r = TextureResolver([str(bad)])
    got = r.resolve("Corrupt.anything")
    assert isinstance(got, TextureError) and got.case == "package-unreadable"
    absent = r.resolve("NotOnThePath.anything")
    assert isinstance(absent, TextureError) and absent.case == "unknown-package"


# --- the decode-layer cases --------------------------------------------------------

def test_missing_palette_is_its_own_case():
    """A `Palette` object ref pointing past the export table is `missing-palette` — the pixels
    are fine, the colours are not, and saying so tells the user the package is incomplete."""
    path = _write(pkgfixture.texture_package(mips=pkgfixture.linear_chain(4, 4), palette_ref=99),
                  "NoPal.utx")
    got = TextureResolver([path]).resolve("NoPal.Fixture")
    assert isinstance(got, TextureError) and got.case == "missing-palette"
    assert "99" in got.detail


def test_no_mip_data_is_the_typed_case_and_not_a_black_buffer():
    """The empty-mip shape reports `no-mip-data`. Asserted on the CASE, so it cannot be
    satisfied by a zero-filled RGB buffer — the silent-black-image trap."""
    path = _write(pkgfixture.texture_package(mips=[(64, 64, b"")]), "NoData.utx")
    got = TextureResolver([path]).resolve("NoData.Fixture")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"


def test_trailing_bytes_is_corrupt_body():
    path = _write(pkgfixture.texture_package(mips=pkgfixture.linear_chain(8, 8),
                                             trailing=b"\x01" * 24), "Trail.utx")
    got = TextureResolver([path]).resolve("Trail.Fixture")
    assert isinstance(got, TextureError) and got.case == "corrupt-body"
    assert "24" in got.detail


def test_a_chain_that_contradicts_itself_is_a_size_mismatch():
    """A chain whose mip 0 fits a layout and whose mip 1 fits a DIFFERENT one is
    `size-mismatch` — the file is internally inconsistent, and the message names the mip that
    breaks it. The container is intact and the body ends where it should, so calling this
    corruption would send the reader looking for the wrong problem."""
    path = _write(pkgfixture.texture_package(mips=[(8, 8, bytes(64)), (4, 4, bytes(63))]),
                  "Contra.utx")
    got = TextureResolver([path]).resolve("Contra.Fixture")
    assert isinstance(got, TextureError) and got.case == "size-mismatch"
    assert "mip 1" in got.detail


def test_a_mip_zero_that_fits_nothing_is_an_unrecognised_layout():
    """Distinct from the above: nothing explains mip 0 AT ALL, so there is no candidate set to
    contradict. The two are separate cases because they mean different things — one file is
    internally inconsistent, the other is in a layout we have no size rule for."""
    path = _write(pkgfixture.texture_package(mips=[(8, 8, bytes(63))]), "Odd.utx")
    got = TextureResolver([path]).resolve("Odd.Fixture")
    assert isinstance(got, TextureError) and got.case == "unrecognised-layout"
    assert "63" in got.detail


def test_a_layout_with_no_decoder_is_unverified_format_naming_what_it_is():
    """A chain the detector CAN name but the build cannot decode says what the file actually
    is — "detected linear4 … no verified decoder" — rather than "unknown". Detection and
    decodability are separate questions, and answering them separately is what makes the
    message useful. It is NOT `corrupt-body`: nothing is wrong with the file."""
    path = _write(pkgfixture.texture_package(mips=pkgfixture.linear_chain(16, 16, 4)),
                  "Lin4.utx")
    got = TextureResolver([path]).resolve("Lin4.Fixture")
    assert isinstance(got, TextureError) and got.case == "unverified-format"
    assert "linear4" in got.detail


def test_a_hostile_mip_count_is_corrupt_body_in_bounded_time():
    """A package is untrusted input. A declared mip count of 2**20 must come back as a named
    case, not as an `IndexError`, a `MemoryError`, or minutes of work — the caps in
    `_read_mip_array` refuse it before a single mip is read."""
    path = _write(pkgfixture.texture_package(mips=pkgfixture.linear_chain(4, 4),
                                             declared_mip_count=1 << 20), "Hostile.utx")
    got = TextureResolver([path]).resolve("Hostile.Fixture")
    assert isinstance(got, TextureError) and got.case == "corrupt-body"


def test_the_five_reachable_decode_cases_are_distinct():
    """Each case has its own input and none is reachable by accident from another's. Without
    this a fix that collapsed two cases into one would pass every test above."""
    inputs = {
        "corrupt-body": dict(mips=pkgfixture.linear_chain(8, 8), trailing=b"\x01" * 24),
        "missing-palette": dict(mips=pkgfixture.linear_chain(4, 4), palette_ref=99),
        "size-mismatch": dict(mips=[(8, 8, bytes(64)), (4, 4, bytes(63))]),
        "no-mip-data": dict(mips=[(64, 64, b"")]),
        # a layout the detector names and no decoder handles — NOT a block chain, which now
        # decodes
        "unverified-format": dict(mips=pkgfixture.linear_chain(8, 8, 4)),
    }
    seen = {}
    for case, kw in inputs.items():
        path = _write(pkgfixture.texture_package(**kw), f"Case{len(seen)}.utx")
        got = TextureResolver([path]).resolve(f"Case{len(seen)}.Fixture")
        assert isinstance(got, TextureError), (case, got)
        seen[case] = got.case
    assert seen == {c: c for c in inputs}, seen


def test_the_flags_are_reported_not_applied():
    """`bMasked`/`bAlphaTexture` are engine RENDER POLICY, owned by whoever is drawing. The
    decoder reports them and derives its mask only from the pixel data — for P8, the
    palette-index-0 convention. Neither committed fixture carries either tag, so both read
    `None` ("no tag; the class default decides"), never `False`."""
    got = _resolver().resolve("LUM_InfoPortraits.ArthurCallaway")
    assert isinstance(got, DecodedTexture)
    assert got.b_masked is None and got.b_alpha_texture is None
    pkg = load_package(PORTRAITS)
    t = decode_texture(pkg, textures(pkg)[0])
    assert got.mask == bytes(1 if i != 0 else 0 for i in t.mips[0].data)


def test_resolve_masked_is_gone():
    """The two seams merged. `resolve_masked` is not kept as an alias — uedcli is unreleased,
    so the new spelling is the only spelling."""
    assert not hasattr(TextureResolver, "resolve_masked")


# --- corpus criteria ----------------------------------------------------------------

def test_no_texture_in_the_tracked_ued22_corpus_fails_to_parse():
    """Every `Texture`-classed export in the one GIT-TRACKED package corpus parses.

    Exact totals are legitimate here and nowhere else offline: `uned/UED22/` is fully tracked,
    so a fresh checkout has byte-identical content and the numbers cannot drift under a
    developer's local files. They are counted under the enumeration rule stated on
    `conftest.ued22_root()` — recursive, extension-exact `{.u,.utx,.uax,.umx}` — without which
    the same tree answers 32/1,934 or 35/2,002 instead.

    This tree carries NO `CompMips` arrays at all, so it is a control for the two-array support
    rather than a test of it: the count must not move when `CompMips` parsing lands.
    """
    from uedcli.tests.conftest import ued22_packages

    packages = ued22_packages()
    assert len(packages) == 34, [p.name for p in packages]

    exports, failures, comp_arrays = 0, [], 0
    for path in packages:
        pkg = load_package(str(path))
        for i in textures(pkg):
            exports += 1
            try:
                t = decode_texture(pkg, i)
            except (ValueError, struct.error, IndexError) as exc:
                failures.append(f"{path.name}:{pkg.names[pkg.exports[i]['nm']]}: {exc}")
                continue
            if t.trailing_bytes:
                failures.append(f"{path.name}:{t.name}: {t.trailing_bytes} trailing bytes")
            if t.comp_mips:
                comp_arrays += 1
    assert exports == 1998, exports
    assert failures == []
    assert comp_arrays == 0, comp_arrays


@pytest.mark.integration
def test_lum_coretex_texture_failures_drop_to_zero():
    """The LIVE confirmation of the motivating bug, over the project's own texture package.

    `LUM/Textures/LUM_CoreTex.utx` holds 253 `Texture` exports, **30** of which the one-array
    parser rejected with "texture body not at EOF" — every one of them a `bHasComp` texture
    carrying a second mip array. They are invisible to uedcli and render as a checkerboard.

    Integration-tier because that file is reachable only through the gitignored game install;
    the offline criterion for the same defect class is the committed `UccCompMips.utx` above.
    """
    from uedcli.tests.conftest import install_root

    path = install_root() / "LUM" / "Textures" / "LUM_CoreTex.utx"
    if not path.exists():
        pytest.skip(f"no install at {path}")
    pkg = load_package(str(path))
    exports, failures, comp = 0, [], 0
    for i in textures(pkg):
        exports += 1
        try:
            t = decode_texture(pkg, i)
        except (ValueError, struct.error, IndexError) as exc:
            failures.append(f"{pkg.names[pkg.exports[i]['nm']]}: {exc}")
            continue
        if t.trailing_bytes:
            failures.append(f"{t.name}: {t.trailing_bytes} trailing bytes")
        if t.comp_mips:
            comp += 1
    assert exports == 253, exports
    assert failures == []
    assert comp == 30, comp                      # the 30 that used to fail, now read


@pytest.mark.integration
def test_install_system_and_textures_failures_drop_to_zero():
    """The same, over the install's `System` + `Textures`: 39 `bHasComp` textures, 0 failures."""
    from uedcli.tests.conftest import install_root

    root = install_root()
    if not root.exists():
        pytest.skip(f"no install at {root}")
    failures, comp = [], 0
    for sub in ("System", "Textures"):
        for path in sorted((root / sub).rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (".u", ".utx"):
                continue
            try:
                pkg = load_package(str(path))
            except (OSError, ValueError, struct.error, IndexError):
                continue                          # not a package we read; not this test's subject
            for i in textures(pkg):
                try:
                    t = decode_texture(pkg, i)
                except (ValueError, struct.error, IndexError) as exc:
                    failures.append(f"{path.name}:{pkg.names[pkg.exports[i]['nm']]}: {exc}")
                    continue
                if t.trailing_bytes:
                    failures.append(f"{path.name}:{t.name}: {t.trailing_bytes} trailing")
                if t.comp_mips:
                    comp += 1
    assert failures == []
    assert comp == 39, comp


# --- S2b: the mip pyramid and the bMasked read rule ---------------------------------

def test_the_result_carries_every_mip_of_the_selected_array():
    """`actor diagram --faces textured` picks a mip per face from screen density, so it needs
    the whole pyramid and not just level 0. The levels come from the array S1's selection rule
    chose, which `array` names, and level 0 is the same buffers the top-level fields carry."""
    got = TextureResolver([COMPMIPS]).resolve("UccCompMips.SpikeFixture")
    assert isinstance(got, DecodedTexture)
    assert got.array == "mips"                       # the P8 original, not the DXT1 copy
    assert [(w, h) for (w, h, _rgb, _m) in got.mips] == \
        [(64, 64), (32, 32), (16, 16), (8, 8), (4, 4), (2, 2), (1, 1)]
    for (w, h, rgb, mask) in got.mips:
        assert len(rgb) == w * h * 3 and len(mask) == w * h
    assert got.mips[0] == (got.width, got.height, got.rgb, got.mask)
    assert got.mips is got.mips                      # decoded once, cached on the instance


def test_the_pyramid_matches_a_direct_decode_of_every_level():
    """Not just plausible shapes — the actual pixels of every level."""
    got = TextureResolver([COMPMIPS]).resolve("UccCompMips.SpikeFixture")
    pkg = load_package(COMPMIPS)
    t = decode_texture(pkg, 1)
    pal = decode_palette(pkg, export_index_of_ref(pkg, t.palette_ref))
    assert [rgb for (_w, _h, rgb, _m) in got.mips] == [mip0_to_rgb(m, pal) for m in t.mips]


def test_an_unreadable_ref_is_a_typed_error_with_no_pyramid_to_mistake_for_one():
    """The pyramid never arrives as a truthy-but-empty result: an error is a `TextureError`,
    which has no `mips` at all, so a caller cannot iterate zero levels and render nothing."""
    got = _resolver().resolve("NoSuchPackage.foo")
    assert isinstance(got, TextureError)
    assert not hasattr(got, "mips")


def _pkg_path(tmp_dir, stem, **kw):
    """Write a synthesized package as `<stem>.utx` — the STEM is what a ref resolves against."""
    p = Path(tmp_dir) / f"{stem}.utx"
    p.write_bytes(pkgfixture.texture_package(**kw))
    return str(p)


def test_bmasked_reads_the_tag_when_it_is_present(tmp_path):
    """`bMasked` present ⇒ that value, both ways. The `False` arm cannot come from real
    content — UE1 omits any property equal to its class default, so a stored `bMasked=False`
    exists only in a package we build — which is why the fixture builder needs the parameter."""
    on = _pkg_path(tmp_path, "MaskOn", name="T", mips=pkgfixture.linear_chain(4, 4),
                      bmasked=True)
    off = _pkg_path(tmp_path, "MaskOff", name="T", mips=pkgfixture.linear_chain(4, 4),
                       bmasked=False)
    assert TextureResolver([on]).resolve("MaskOn.T").b_masked is True
    assert TextureResolver([off]).resolve("MaskOff.T").b_masked is False


def test_bmasked_with_no_tag_falls_to_the_resolved_class_default(tmp_path):
    """**The owner's read rule: the tag if present, ELSE the resolved class default** — never
    "absent means false".

    UE1 omits a tagged property equal to its class default, so an absent `bMasked` means
    "equal to the default", and only the default says what that is. Resolving it walks
    `Engine.Texture`'s ancestor chain through the CODE packages on the search path; a property
    the chain never states falls to its type's zero, `False` for a bool. Here that resolution
    runs for real against the tracked `uned/UED22` `Engine.u` + `Core.u`.
    """
    from uedcli.tests.conftest import ued22_root

    tagless = _pkg_path(tmp_path, "Tagless", name="T", mips=pkgfixture.linear_chain(4, 4))
    r = TextureResolver([tagless, str(ued22_root() / "Engine.u"),
                         str(ued22_root() / "Core.u")])
    got = r.resolve("Tagless.T")
    assert isinstance(got, DecodedTexture)
    assert got.b_masked is False                     # resolved, not assumed
    assert got.b_alpha_texture is False


def test_bmasked_is_none_when_no_code_package_can_supply_the_default(tmp_path):
    """On a search path with **no code package** there is no default to resolve, so neither
    branch of the rule applies and the answer is `None`, not `False`.

    That path is not hypothetical — it is the "read any texture from any engine" case the
    decoder exists to serve: a lone `.utx` handed to the tool. Reporting `False` would report
    a value nothing supplied. A provisional call, recorded on the board
    (`inbox/bmasked-with-no-reachable-class-default-source`) with its known cost: a caller that
    ORs the flag into a render decision treats `None` as falsy.
    """
    tagless = _pkg_path(tmp_path, "Lone", name="T", mips=pkgfixture.linear_chain(4, 4))
    got = TextureResolver([tagless]).resolve("Lone.T")
    assert isinstance(got, DecodedTexture)
    assert got.b_masked is None and got.b_alpha_texture is None


def test_a_real_masked_texture_reports_the_flag(tmp_path):
    """End to end over tracked content: `uned/UED22/DeusExDeco.u` carries both kinds, and the
    two must come out differently — `True` from a written tag, `False` from the resolved
    default. Pinning both here is what stops the rule collapsing back to "absent ⇒ false",
    which would be indistinguishable on the `False` arm alone."""
    from uedcli.tests.conftest import ued22_root

    deco = ued22_root() / "DeusExDeco.u"
    r = TextureResolver([str(deco), str(ued22_root() / "Engine.u"),
                         str(ued22_root() / "Core.u")])
    pkg = load_package(str(deco))
    tagged = untagged = None
    for i in textures(pkg):
        e = pkg.exports[i]
        props, _ = utexture._read_props(pkg.buf, e["soff"], e["soff"] + e["ssize"], pkg.names)
        name = pkg.names[e["nm"]]
        if props.get("bMasked") and tagged is None:
            tagged = name
        elif "bMasked" not in props and untagged is None:
            untagged = name
    assert tagged and untagged, "the fixture package no longer carries both kinds"
    assert r.resolve(f"DeusExDeco.{tagged}").b_masked is True
    assert r.resolve(f"DeusExDeco.{untagged}").b_masked is False


# --- a corrupt package must never reach the user as a traceback ----------------------

def test_no_single_byte_corruption_makes_the_resolver_raise():
    """A package's header tables are read at load and never range-checked, so a corrupt file
    can carry a name index, an object ref or an export index pointing nowhere — and the lookup
    walk reads several of them. Before the backstop in `resolve`, **12 distinct single-byte
    corruptions** of this 1,459-byte package raised `IndexError` straight out of
    `TextureResolver.resolve()`.

    That is a Python traceback out of `level photo --native` and out of author-time texture
    validation, on nothing worse than a damaged `.utx` sitting on the search path. Every byte is
    flipped here in turn; every result must be a `DecodedTexture` or a `TextureError`.
    """
    good = pkgfixture.texture_package(mips=pkgfixture.linear_chain(8, 8))
    for i in range(len(good)):
        for delta in (0x01, 0xFF):
            buf = bytearray(good)
            buf[i] = (buf[i] + delta) & 0xFF
            path = _write(bytes(buf), "Fuzz.utx")
            got = TextureResolver([path]).resolve("Fuzz.Fixture")
            assert isinstance(got, (DecodedTexture, TextureError)), (i, delta, got)


def test_no_single_byte_corruption_makes_the_existence_check_raise():
    """`exists()` walks the same tables, and its bare-name form scans EVERY package on the
    path — so one damaged file would otherwise poison every unqualified lookup. It answers a
    bool either way; the point is that it answers."""
    good = pkgfixture.texture_package(mips=pkgfixture.linear_chain(8, 8))
    for i in range(len(good)):
        buf = bytearray(good)
        buf[i] ^= 0xFF
        path = _write(bytes(buf), "FuzzE.utx")
        r = TextureResolver([path])
        assert isinstance(r.exists("FuzzE.Fixture"), bool), i
        assert isinstance(r.exists("Fixture"), bool), i        # the bare-name scan


def test_an_unreadable_package_structure_is_reported_as_package_unreadable():
    """The named case, not a generic miss: the package IS on the path, so telling the user it
    is 'unknown' would send them looking for a file that is right there."""
    buf = bytearray(pkgfixture.texture_package(mips=pkgfixture.linear_chain(8, 8)))
    hits = 0
    for i in range(len(buf)):
        mutated = bytearray(buf)
        mutated[i] ^= 0xFF
        path = _write(bytes(mutated), "Broken.utx")
        got = TextureResolver([path]).resolve("Broken.Fixture")
        if isinstance(got, TextureError) and got.case == "package-unreadable":
            hits += 1
    assert hits > 0, "no corruption reached the structural backstop; the test proves nothing"


def test_the_committed_fixture_is_exactly_what_its_build_script_produces():
    """A REPRODUCIBILITY pin, not a decode oracle.

    `UccCompMips.utx` is committed because rebuilding it needs artifacts from a spike, and
    because a test that regenerated it and then checked its pixels would be testing our writer
    against our reader — the circularity the fixture exists to avoid. But "committed" is only
    meaningful if the script still emits it: comparing the BYTES makes no claim about whether
    they are right, only that the recorded provenance still holds.

    It has drifted once already. Adding the name `bMasked` to the fixture builder's interned
    name list lengthened the encoded name table, which shifted the package's data offset, which
    shifted every absolute mip skip-offset — 13 bytes of difference in a file whose pixels were
    unchanged, and nothing noticed.
    """
    from uedcli.tests import build_uccfixture

    committed = (FIXTURES / "UccCompMips.utx").read_bytes()
    assert build_uccfixture.build() == committed, \
        ("build_uccfixture.build() no longer reproduces the committed fixture; re-run "
         "`.venv/bin/python -m uedcli.tests.build_uccfixture` and commit the result")


def test_a_hostile_header_count_is_refused_before_any_entry_is_read():
    """A header's name/import/export counts are raw `uint32`s out of an untrusted file, and
    nothing else bounds them. A header claiming four billion names sends the table walk into an
    allocation loop that runs until the process is killed.

    **It does not fail fast on its own.** A name's length is a SIGNED compact index, so a
    negative one moves the read cursor BACKWARDS — and negative indices into `bytes` are legal
    in Python, so the walk cycles inside the buffer rather than running off the end. Measured
    before the bound: a count of `0xFFFFFFFF` ran for over 200 s inside a 2.5 GB cap without
    returning.

    The bound is exact and needs no magic number: no table entry can occupy fewer than one
    byte, so an N-byte file cannot hold more than N of anything.

    Note what this asserts that the byte-flip sweeps above cannot: **that an answer arrives**.
    Those assert no exception escapes, which a hang satisfies perfectly.
    """
    import time

    good = pkgfixture.texture_package(mips=pkgfixture.linear_chain(8, 8))
    # header layout: tag, version, flags, namecnt, nameoff, expcnt, expoff, impcnt, impoff
    for label, offset in (("name", 12), ("export", 20), ("import", 28)):
        buf = bytearray(good)
        struct.pack_into("<I", buf, offset, 0xFFFFFFFF)
        path = _write(bytes(buf), "Huge.utx")
        started = time.monotonic()
        got = TextureResolver([path]).resolve("Huge.Fixture")
        elapsed = time.monotonic() - started
        assert isinstance(got, TextureError) and got.case == "package-unreadable", (label, got)
        assert elapsed < 1.0, f"{label} count took {elapsed:.1f}s — the bound is not holding"


def test_a_negative_name_length_cannot_walk_the_cursor_backwards():
    """The other half of the same defect: a name length is a signed compact index, so a
    negative one both slices nothing and moves the cursor back. Refused outright — a name
    cannot have negative length, and accepting one is what lets the walk cycle."""
    good = bytearray(pkgfixture.texture_package(mips=pkgfixture.linear_chain(8, 8)))
    nameoff = struct.unpack_from("<I", good, 16)[0]
    good[nameoff] = 0xFF          # compact index: sign | continue | low six bits set
    good[nameoff + 1] = 0x04      # continuation -> -319
    path = _write(bytes(good), "NegLen.utx")
    got = TextureResolver([path]).resolve("NegLen.Fixture")
    assert isinstance(got, TextureError) and got.case == "package-unreadable"
