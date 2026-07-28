"""The INTEGRATION corpus sweep — the same bar over the two game installs, plus the two
engine-fact dumps that are not git-tracked.

Everything here is `-m integration` and therefore DESELECTED by default, because it needs
material a fresh checkout does not have: `pytest.ini` carries `addopts = -m "not integration"`.
Deselected is not skipped — a skip would mean "this test could not decide", and these tests
decide perfectly well when the install is there.

WHY THE ASSERTIONS ARE INVARIANTS, NOT TOTALS. A game install is live: it is patched, modded,
and different on every machine. An exact export count over one would fail for the wrong reason
and get edited until it stopped complaining. So the bar here is *shape*: zero parse failures,
zero unrecognised layouts, zero ambiguous chains, zero exceptions, every texture either decodes
or names a case. The offline tier next door is where exact counts are legitimate.

Two exceptions are exact and deliberately so — the `LUM_CoreTex.utx` and `System`+`Textures`
figures. Those are the MOTIVATING BUG, and its whole point is that a specific number of
textures went from unreadable to readable.

`UEDCLI_TEST_UNREAL_INSTALL` points at the Unreal Gold install; unlike the Deus Ex one it has
no in-tree pointer at all. Tests needing it skip cleanly when it is unset.
"""
from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

from uedcli import utexture
from uedcli.tests.conftest import install_root
from uedcli.tests.test_utexture_corpus import _arrays_of, _sweep, _texture_like

pytestmark = pytest.mark.integration

PACKAGE_SUFFIXES = (".u", ".utx", ".uax", ".umx", ".unr", ".dx")


def unreal_root() -> Path | None:
    env = os.environ.get("UEDCLI_TEST_UNREAL_INSTALL")
    return Path(env) if env else None


def _packages(root: Path, *subs: str) -> list[Path]:
    out = []
    for sub in subs:
        d = root / sub
        if d.is_dir():
            out += [p for p in sorted(d.rglob("*"))
                    if p.is_file() and p.suffix.lower() in PACKAGE_SUFFIXES]
    return out


def _readable(paths):
    """Drop files that are not packages we read at all — a broken or unrelated file in a game
    directory is not this sweep's subject."""
    out = []
    for p in paths:
        try:
            utexture.load_package(str(p))
        except (OSError, ValueError, struct.error, IndexError):
            continue
        out.append(p)
    return out


def _require(root: Path | None, what: str) -> Path:
    if root is None or not root.exists():
        pytest.skip(f"no {what} install (looked at {root})")
    return root


# --- the Deus Ex install -----------------------------------------------------------------

def test_the_motivating_bug_is_fixed_over_the_projects_own_texture_package():
    """**The live confirmation.** `LUM/Textures/LUM_CoreTex.utx` holds 253 `Texture` exports,
    **30** of which the one-array parser rejected with "texture body not at EOF" — every one a
    `bHasComp` texture whose second mip array made the body overrun. They were invisible to
    uedcli and rendered as a checkerboard.

    Exact by design: the number going to zero IS the fix. The offline criterion for the same
    defect class is the committed `UccCompMips.utx`.
    """
    root = _require(install_root(), "Deus Ex")
    path = root / "LUM" / "Textures" / "LUM_CoreTex.utx"
    if not path.exists():
        pytest.skip(f"no {path}")
    got = _sweep([path])
    assert got["textures"] == 253
    assert got["parse_failures"] == [] and got["exceptions"] == []
    assert got["comp_arrays"] == 30                 # the 30 that used to fail, now read
    assert got["cases"] == {}


def test_the_install_system_and_textures_sweep_clean():
    """39 `bHasComp` textures across `System` + `Textures`, zero failures, and every texture
    either decodes or names a case."""
    root = _require(install_root(), "Deus Ex")
    got = _sweep(_readable(_packages(root, "System", "Textures")))
    assert got["parse_failures"] == [] and got["exceptions"] == []
    assert got["comp_arrays"] == 39
    assert got["cases"] == {}


def test_the_whole_deus_ex_tree_never_produces_a_silent_miss_or_an_exception():
    """The widest bar available: every texture-classed export in the whole install either
    decodes or comes back with a NAMED case, and none of the three "we will not guess" cases
    fires on real content. Invariants, not totals — the tree is live."""
    root = _require(install_root(), "Deus Ex")
    got = _sweep(_readable(_packages(root, "System", "Textures", "Maps", "LUM")))
    assert got["textures"] > 0
    assert got["parse_failures"] == [] and got["exceptions"] == []
    for case in ("unrecognised-layout", "ambiguous-layout", "ambiguous-alpha", "size-mismatch"):
        assert got["cases"].get(case, 0) == 0, (case, got["cases"])


def test_real_procedural_textures_report_no_mip_data_and_production_never_lists_them():
    """The procedural classes exist only in a game install — there are none in any tracked
    material, which is why this cannot be an offline test.

    Two halves: through the sweep's own wider matcher every `FireTexture`/`WetTexture`/… export
    reports `no-mip-data` (their mips serialize with `DataCount == 0`), AND the shipped
    `utexture.textures()` returns none of them, so the widening cannot leak into production.
    """
    root = _require(install_root(), "Deus Ex")
    seen = 0
    for path in _readable(_packages(root, "System", "Textures")):
        pkg = utexture.load_package(str(path))
        exact = set(utexture.textures(pkg))
        for i in _texture_like(pkg):
            cls = pkg.class_of_export(i) or ""
            if cls == "Texture":
                continue
            assert i not in exact, f"{path.name}: production listed a {cls}"
            try:
                t = utexture.decode_texture(pkg, i)
            except (ValueError, struct.error, IndexError):
                continue                             # FireTexture trails FSpark bytes; fine
            for mips, code in _arrays_of(t):
                got = utexture.detect_layout(mips, code=code)
                assert isinstance(got, utexture.DetectionFailure) and got.case == "no-mip-data", \
                    (path.name, cls, got)
                seen += 1
    assert seen > 0, "no procedural-class exports found; this install cannot exercise the rule"


# --- the Unreal Gold install: the only real stored codes anywhere ------------------------

def test_the_unreal_install_sweeps_clean_and_carries_the_eleven_stored_codes():
    """Unreal Gold holds the ONLY texture exports in any corpus that physically store a
    `Format` property — eleven of them, ten `Format = 7` (BC3) and one `Format = 3` (BC1).
    Every one names a layout its own chain fits, which is the measurement behind "the code
    never contradicts the data on real content"."""
    root = _require(unreal_root(), "Unreal Gold (set UEDCLI_TEST_UNREAL_INSTALL)")
    stored = {}
    for path in _readable(_packages(root, "System", "Maps", "Textures")):
        pkg = utexture.load_package(str(path))
        for i in utexture.textures(pkg):
            try:
                t = utexture.decode_texture(pkg, i)
            except (ValueError, struct.error, IndexError):
                continue
            if "Format" in t.props:
                stored[f"{path.name}:{t.name}"] = t.fmt
                # It names a FITTED candidate — the code corroborates, never contradicts.
                assert isinstance(utexture.detect_layout(t.mips, code=t.fmt), utexture.Layout), \
                    (path.name, t.name, t.fmt)
    assert len(stored) == 11, stored
    assert sorted(stored.values()) == [3] + [7] * 10, stored


def test_the_unreal_and_deus_ex_enums_agree_with_the_slot_map():
    """The other two `ETextureFormat` dumps. Unreal Gold has 8 slots and names 0/3/6/7 under
    the DXT vendor spelling; Deus Ex has only **5** and therefore DOES NOT DEFINE 6 or 7.

    Pinning Deus Ex's silence AS SILENCE matters: it is not true that "all three agree on 6 and
    7" — one of them says nothing, which is why it cannot contradict. Together with the tracked
    227 dump next door, these three are the whole justification for the four-slot map.
    """
    from uedcli import uprops
    from uedcli.tests.test_utexture_corpus import _enum

    unreal = _require(unreal_root(), "Unreal Gold (set UEDCLI_TEST_UNREAL_INSTALL)")
    pkg = uprops.load_package(str(unreal / "System" / "Engine.u"), name="Engine")
    slots = _enum(pkg, "ETextureFormat")
    assert len(slots) == 8
    assert {i: slots[i] for i in (0, 3, 6, 7)} == \
        {0: "TEXF_P8", 3: "TEXF_DXT1", 6: "TEXF_DXT3", 7: "TEXF_DXT5"}

    dx = _require(install_root(), "Deus Ex")
    pkg = uprops.load_package(str(dx / "System" / "Engine.u"), name="Engine")
    slots = _enum(pkg, "ETextureFormat")
    assert len(slots) == 5, slots
    assert {i: slots[i] for i in (0, 3)} == {0: "TEXF_P8", 3: "TEXF_DXT1"}
