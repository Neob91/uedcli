"""Offline tests for `uedcli.proceduraltex` — the one static frame the draft renderers paint for
UE1's bitmap-less texture classes — and for the `utexture` resolver path that feeds it.

Two layers, tested separately because they fail separately: the blob parsing that reads a body's
stored sparks and drops, and the whole INTEGRATION — a synthesized `.utx` resolved through
`TextureResolver`, which is what proves the sparks, drops, palette and `SourceTexture` are really
decoded and handed to a generator.

Fixtures are synthesized with `pkgfixture` (no game content — this runs on a bare checkout), over
a real `ClassIndex` from the committed `uned/UED22` corpus, because only a widened resolver sees
an `Engine.Texture` DESCENDANT like `fire.FireTexture` at all.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

from uedcli import proceduraltex, utexture
from uedcli.classindex import ClassIndex
from uedcli.tests import pkgfixture
from uedcli.utexture import DecodedTexture, TextureError, TextureResolver

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

# A flat black-to-white ramp: index N is (N, N, N), so a painted palette index reads straight off
# the pixel and a test can assert on brightness without decoding a real fire ramp.
RAMP = [(i, i, i, 255) for i in range(256)]


@pytest.fixture(scope="module")
def index() -> ClassIndex:
    """Only the code packages the `Engine.Texture` hierarchy needs — `fire.u` is where
    `FireTexture`/`WaveTexture`/`WetTexture`/`IceTexture` are declared."""
    files = [(os.path.splitext(os.path.basename(f))[0], f)
             for f in glob.glob(str(UED22 / "*.u"))]
    return ClassIndex.from_files(files)


def _spark(x: int, y: int, heat: int = 255, kind: int = 13) -> bytes:
    """One 8-byte `FSpark`: type, heat, X, Y, then four per-type bytes nothing here reads."""
    return bytes([kind, heat, x, y, 0, 0, 0, 0])


def _spark_array(*sparks: bytes) -> bytes:
    """The `TArray<FSpark>` a `FireTexture` body trails: compact count, then the elements."""
    return bytes([len(sparks)]) + b"".join(sparks)


def _drop(x: int, y: int, depth: int = 255, kind: int = 1) -> bytes:
    """One 8-byte `ADrop`: type, depth, X, Y (HALF-resolution grid), then four unread bytes."""
    return bytes([kind, depth, x, y, 0, 0, 0, 0])


def _fire_package(**kw) -> bytes:
    """A 16x16 `fire.FireTexture` whose body carries two sparks near the bottom."""
    return pkgfixture.texture_package(**{
        "name": "Flame", "class_package": "fire", "class_name": "FireTexture",
        "mips": [(16, 16, b"")], "palette": RAMP,
        "trailing": _spark_array(_spark(4, 13), _spark(11, 14)),
        "int_props": {"USize": 16, "VSize": 16, "NumSparks": 2},
        "byte_props": {"RenderHeat": 255, "FX_Size": 96}, **kw})


def _wave_package(**kw) -> bytes:
    """A 32x32 `fire.WaveTexture` with two drops on its 16x16 half-resolution grid."""
    return pkgfixture.texture_package(**{
        "name": "Pool", "class_package": "fire", "class_name": "WaveTexture",
        "mips": [(32, 32, b"")], "palette": RAMP,
        "int_props": {"USize": 32, "VSize": 32, "NumDrops": 2},
        "byte_props": {"WaveAmp": 128, "FX_Frequency": 8, "FX_Radius": 128,
                       "BumpMapLight": 0, "BumpMapAngle": 128, "PhongRange": 128,
                       "PhongSize": 32},
        "struct_array": ("Drops", "ADrop", [_drop(5, 5), _drop(11, 10)]), **kw})


def _source_chain(w: int, h: int):
    """A P8 mip pyramid whose pixels vary in BOTH axes, so a horizontal-only distortion shows up
    and a vertical one would too."""
    out = []
    while True:
        out.append((w, h, bytes(((i % w) * 9 + (i // w) * 5) & 0xFF for i in range(w * h))))
        if w == 1 and h == 1:
            return out
        w, h = max(1, w // 2), max(1, h // 2)


def _wet_package(*, class_name: str = "WetTexture", **kw) -> bytes:
    """A 32x32 `fire.WetTexture` (or `IceTexture`) pointed at the source export `pkgfixture`
    appends, which is object ref 3. An ice texture reads the same export as its glass."""
    refs = {"SourceTexture": 3}
    if class_name == "IceTexture":
        refs["GlassTexture"] = 3
    return pkgfixture.texture_package(**{
        "name": "Wet", "class_package": "fire", "class_name": class_name,
        "mips": [(32, 32, b"")], "palette": RAMP, "source_mips": _source_chain(32, 32),
        "int_props": {"USize": 32, "VSize": 32, "NumDrops": 2},
        "object_props": refs,
        "byte_props": {"WaveAmp": 200, "FX_Frequency": 8, "FX_Radius": 128,
                       "FX_Amplitude": 255, "Amplitude": 255},
        "struct_array": ("Drops", "ADrop", [_drop(5, 5), _drop(11, 10)]), **kw})


def _resolver(tmp_path, buf: bytes, stem: str, index) -> TextureResolver:
    p = tmp_path / f"{stem}.utx"
    p.write_bytes(buf)
    return TextureResolver([str(p)], class_index=index)


def _distinct(res: DecodedTexture) -> int:
    return len({res.rgb[i:i + 3] for i in range(0, len(res.rgb), 3)})


# --- the stored particles: what the body actually carries --------------------------

def test_a_fire_body_s_trailing_bytes_decode_as_its_spark_array():
    """The `TArray<FSpark>` after a `FireTexture`'s empty mips is where its live spark positions
    are — 8 bytes each, X and Y inside the texture. Measured over all 124 fire textures in the
    shipped Deus Ex + Unreal corpora: the array's own count equals the body's `NumSparks` every
    time, and no spark lands outside `USize`x`VSize`."""
    sparks = proceduraltex.parse_sparks(_spark_array(_spark(4, 13, heat=200),
                                                     _spark(11, 14, kind=7)), 2)
    assert [(s.x, s.y, s.heat, s.kind) for s in sparks] == [(4, 13, 200, 13), (11, 14, 255, 7)]


def test_a_truncated_spark_array_yields_the_sparks_that_are_there():
    """A package is untrusted input: a count that over-declares what the blob holds must give
    fewer sparks, never a read past the end."""
    assert len(proceduraltex.parse_sparks(b"\x09" + _spark(1, 1), 9)) == 1
    assert proceduraltex.parse_sparks(b"", 4) == ()


def test_drops_past_numdrops_are_stale_slots_and_are_dropped():
    """`Drops[]` keeps leftovers past the live count — `HubEffects.WaterRings2` stores 137
    elements behind a `NumDrops` of 6 — so only indices `0..NumDrops-1` are real sources."""
    raws = {0: _drop(1, 1), 1: _drop(2, 2), 2: _drop(3, 3)}
    assert [(d.x, d.y) for d in proceduraltex.parse_drops(raws, 2)] == [(1, 1), (2, 2)]


def test_a_missing_element_does_not_shift_the_drops_after_it():
    """UE1 omits a static-array element equal to its all-zero default, so the live indices can
    have holes. A hole is a drop that displaces nothing — never a reason to slide the next
    element into its slot."""
    raws = {0: _drop(1, 1), 2: _drop(3, 3)}
    assert [(d.x, d.y) for d in proceduraltex.parse_drops(raws, 3)] == [(1, 1), (3, 3)]


def test_a_static_array_property_is_read_element_by_element(tmp_path):
    """`TextureObj.prop_arrays` carries every element of a static array keyed by its index, where
    `props` keeps only the last — the decode `Drops[]` needs."""
    p = tmp_path / "Pool.utx"
    p.write_bytes(_wave_package())
    t = utexture.decode_texture(utexture.load_package(str(p)), 1)
    assert {k: raw for k, (_ptype, raw) in t.prop_arrays["Drops"].items()} == {
        0: _drop(5, 5), 1: _drop(11, 10)}
    assert t.props["Drops"][1] == _drop(11, 10)


def test_a_static_array_index_past_127_reads_back_at_its_own_index(tmp_path):
    """The packed array index takes two bytes above 0x7F, and real content goes there —
    `Effects.drtywater_a` stores `Drops` indices up to 178. Reading that index as one byte would
    desync every tag after it, so the whole body is asserted to parse as well."""
    drops = [_drop(k % 16, k % 16) for k in range(200)]
    p = tmp_path / "Big.utx"
    p.write_bytes(_wave_package(
        name="Big", int_props={"USize": 32, "VSize": 32, "NumDrops": 200},
        struct_array=("Drops", "ADrop", drops)))
    t = utexture.decode_texture(utexture.load_package(str(p)), 1)
    assert sorted(t.prop_arrays["Drops"]) == list(range(200))
    assert t.prop_arrays["Drops"][178][1] == drops[178]
    assert t.trailing_bytes == 0                      # nothing desynced behind the wide index


# --- the painted frames -----------------------------------------------------------

def test_fire_paints_a_pattern_not_a_flat_colour(tmp_path, index):
    """The regression that separates a real generated pattern from a re-skinned placeholder: the
    frame carries many distinct values, and the heat falls off going UP from the sparks — which
    is what makes it read as fire rather than as noise."""
    got = _resolver(tmp_path, _fire_package(), "Fire", index).resolve("Fire.Flame")
    assert isinstance(got, DecodedTexture), got
    assert (got.width, got.height, got.layout_source) == (16, 16, "procedural")
    assert _distinct(got) > 8
    column = [got.rgb[(y * 16 + 4) * 3] for y in range(16)]
    assert column[13] > column[9] > column[4]          # spark row, mid plume, tip


def test_wave_paints_a_pattern_not_a_flat_colour(tmp_path, index):
    got = _resolver(tmp_path, _wave_package(), "Pool", index).resolve("Pool.Pool")
    assert isinstance(got, DecodedTexture), got
    assert (got.width, got.height, got.layout_source) == (32, 32, "procedural")
    assert _distinct(got) > 8


def test_wet_distorts_its_source_horizontally_and_only_horizontally(tmp_path, index):
    """The manual's one hard statement about `WetTexture` — "the distortion is horizontal only".
    Each output row is therefore a sideways-shifted read of the source row at the same v, so
    every colour in an output row also occurs in that source row."""
    resolver = _resolver(tmp_path, _wet_package(), "Wet", index)
    got, src = resolver.resolve("Wet.Wet"), resolver.resolve("Wet.WetSrc")
    assert isinstance(got, DecodedTexture) and isinstance(src, DecodedTexture), (got, src)
    assert got.layout_source == "procedural" and _distinct(got) > 8
    for y in range(32):
        row = {got.rgb[(y * 32 + x) * 3:(y * 32 + x) * 3 + 3] for x in range(32)}
        source_row = {src.rgb[(y * 32 + x) * 3:(y * 32 + x) * 3 + 3] for x in range(32)}
        assert row <= source_row, y
    assert got.rgb != src.rgb                          # ... and it really is displaced


def test_ice_paints_its_source_through_the_glass_texture(tmp_path, index):
    got = _resolver(tmp_path, _wet_package(class_name="IceTexture"), "Ice",
                    index).resolve("Ice.Wet")
    assert isinstance(got, DecodedTexture), got
    assert (got.width, got.height, got.layout_source) == (32, 32, "procedural")
    assert _distinct(got) > 8


@pytest.mark.parametrize("build,stem,ref", [
    (_fire_package, "Fire", "Fire.Flame"),
    (_wave_package, "Pool", "Pool.Pool"),
    (_wet_package, "Wet", "Wet.Wet"),
    (lambda: _wet_package(class_name="IceTexture"), "Ice", "Ice.Wet"),
])
def test_the_same_package_always_paints_the_same_pixels(build, stem, ref, tmp_path, index):
    """Determinism, across two resolvers sharing nothing but the file. A frame seeded from a
    clock or an unseeded RNG fails here, and every caller (`class preview`, `level photo
    --native`, the texture catalog) depends on identical inputs giving identical pixels."""
    p = tmp_path / f"{stem}.utx"
    p.write_bytes(build())
    first = TextureResolver([str(p)], class_index=index).resolve(ref)
    second = TextureResolver([str(p)], class_index=index).resolve(ref)
    assert isinstance(first, DecodedTexture), first
    assert (first.rgb, first.mask) == (second.rgb, second.mask)


# --- what is NOT painted ----------------------------------------------------------

def test_a_procedural_class_with_no_generator_still_reports_no_mip_data(tmp_path, index):
    """`ScriptedTexture` is a draw-on canvas an actor paints at runtime, not one of this family,
    and nothing here renders it. It stays the `no-mip-data` case, so `resolve_or_procedural_red`
    keeps substituting the placeholder for it exactly as before."""
    resolver = _resolver(tmp_path, pkgfixture.texture_package(
        name="Canvas", class_package="Engine", class_name="ScriptedTexture",
        mips=[(16, 16, b"")], int_props={"USize": 16, "VSize": 16}), "Canvas", index)
    got = resolver.resolve("Canvas.Canvas")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"
    assert utexture.resolve_or_procedural_red(resolver, "Canvas.Canvas") is utexture.PROCEDURAL_RED


def test_a_fire_with_no_stored_sparks_falls_back_to_the_placeholder(tmp_path, index):
    """A fire texture whose spark array is empty says nothing about how it looks, and the heat a
    spark would carry is a native class default we cannot read offline. Painting one would be
    inventing, so it stays `no-mip-data` and the detail says why."""
    got = _resolver(tmp_path, _fire_package(
        trailing=b"\x00", int_props={"USize": 16, "VSize": 16, "NumSparks": 0}),
        "Fire", index).resolve("Fire.Flame")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"
    assert "stores none" in got.detail


def test_a_wet_texture_with_no_source_falls_back_to_the_placeholder(tmp_path, index):
    """`LavaFX.lava8` ships like this. There is nothing to distort, so it is the placeholder
    case — NOT a hard error, because a whole `level photo` must not fail over one shipped
    texture the user cannot fix."""
    got = _resolver(tmp_path, _wet_package(object_props={}, source_mips=None),
                    "Wet", index).resolve("Wet.Wet")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"
    assert "SourceTexture" in got.detail


def test_an_absurd_declared_size_is_not_painted(tmp_path, index):
    """A procedural body has no stored pixels to bound it — its size is whatever it claims — so
    the claim is checked before anything is allocated."""
    got = _resolver(tmp_path, _fire_package(
        int_props={"USize": 99999, "VSize": 99999, "NumSparks": 2}),
        "Fire", index).resolve("Fire.Flame")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"
    assert "99999" in got.detail


def test_a_palette_that_will_not_decode_falls_back_to_the_placeholder(tmp_path, index):
    """A corrupt palette must leave the fire UNPAINTED, not take `resolve` down as
    `package-unreadable`: every caller treats that as a hard failure, so a `level photo --native`
    of a map using this texture would abort where it used to render the placeholder."""
    resolver = _resolver(tmp_path, _fire_package(palette_count=3), "Fire", index)
    got = resolver.resolve("Fire.Flame")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"
    assert "palette" in got.detail
    assert utexture.resolve_or_procedural_red(resolver, "Fire.Flame") is utexture.PROCEDURAL_RED


def test_a_mistyped_object_ref_is_a_typed_result_not_a_traceback(tmp_path, index):
    """A package is untrusted: its tag says what TYPE each value is, so a body can label `Palette`
    a STRUCT and hand the resolver bytes where it expects a ref. `resolve`'s backstop does not
    catch `TypeError`, so an unguarded comparison would surface as a traceback out of the CLI."""
    got = _resolver(tmp_path, _fire_package(struct_array=("Palette", "Vector", [bytes(12)])),
                    "Fire", index).resolve("Fire.Flame")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"


def test_a_texture_that_sources_itself_does_not_recurse(tmp_path, index):
    """Object ref 2 is the `WetTexture` export itself. A package can say that; the resolver must
    answer rather than recurse until the stack runs out."""
    got = _resolver(tmp_path, _wet_package(object_props={"SourceTexture": 2}),
                    "Wet", index).resolve("Wet.Wet")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"


# --- what the rest of the codebase sees -------------------------------------------

def test_a_painted_frame_is_marked_as_painted_not_as_a_decoded_bitmap(tmp_path, index):
    """`is_procedural` is the seam the texture catalog uses to keep these NAME-keyed: the pixels
    are uedcli's, not the package's, so hashing them would key a classification shard to this
    renderer's output."""
    got = _resolver(tmp_path, _fire_package(), "Fire", index).resolve("Fire.Flame")
    assert utexture.is_procedural(got)
    assert not utexture.is_procedural(utexture.PROCEDURAL_RED)
    assert utexture.PROCEDURAL_RED.layout_source == "synthetic"


def test_mip_zero_is_the_only_level_a_painted_frame_offers(tmp_path, index):
    """Nothing decodes a second level for it — `.mips` must not walk off the end trying."""
    got = _resolver(tmp_path, _fire_package(), "Fire", index).resolve("Fire.Flame")
    assert len(got.mips) == 1
    assert got.mips[0] == (got.width, got.height, got.rgb, got.mask)


def test_dimensions_still_reports_no_stored_pixels(tmp_path, index):
    """`dimensions()` measures STORED pixels and a procedural texture has none — unchanged by the
    frame `resolve` now paints. The two answer different questions."""
    got = _resolver(tmp_path, _fire_package(), "Fire", index).dimensions("Fire.Flame")
    assert isinstance(got, TextureError) and got.case == "no-mip-data"
