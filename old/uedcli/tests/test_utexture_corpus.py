"""The OFFLINE corpus sweep — every texture in every git-tracked package, and the engine-fact
pins that justify the format map.

WHAT A SWEEP IS FOR. Per-shape unit tests prove the decoder handles the shapes someone thought
of. A sweep proves it handles the ones nobody did: it walks a whole corpus and requires that
every texture either decodes or produces a NAMED case — never a silent miss, never an
exception. It is the test that would have caught both defects this work exists to fix.

WHY EXACT COUNTS, AND WHERE THEY ARE LEGITIMATE. A "no exceptions" sweep passes happily while
everything quietly degrades to an error case, so the totals are asserted too. But an exact
total is only honest over material a fresh checkout is GUARANTEED to have and that nothing else
writes. `uned/UED22/` qualifies — it is fully tracked — and so do the committed fixtures.
Nothing under a game install does, which is why every install-wide criterion lives in
`test_utexture_corpus_installs.py` behind the `integration` marker and asserts INVARIANTS
(zero failures of each kind) rather than totals.

STATE THE ENUMERATION RULE WHEREVER A COUNT IS ASSERTED, or the same tree gives three answers:
`conftest.ued22_root()` carries it (recursive, extension-exact `{.u,.utx,.uax,.umx}` → 34
packages / 1,998 `Texture` exports; a loose `*.u*` glob also catches the tracked `DeusEx.u.bak`
and gives 35 / 2,002; top-level-only gives 32 / 1,934).

AND STATE THE UNIT. "Textures" counts one `Mips` chain per `Texture`-classed export; "mip
arrays" counts `Mips` plus each `CompMips`. They differ the moment a `bHasComp` texture appears
— by exactly 69 across the four corpora measured — and a criterion that mixes them cannot be
met. This tree happens to have NO `CompMips` at all, so the two coincide here at 1,998; that
coincidence is asserted, not assumed, so it cannot quietly stop being true.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from uedcli import utexture
from uedcli.tests.conftest import ued22_packages, ued22_root

FIXTURES = Path(__file__).parent / "fixtures"

# Counted 2026-07-27 under the enumeration rule on `conftest.ued22_root()`.
UED22_PACKAGES = 34
UED22_TEXTURE_EXPORTS = 1998          # unit: TEXTURES (one Mips chain each)
UED22_MIP_ARRAYS = 1998               # unit: MIP ARRAYS (Mips + each CompMips); no CompMips here
UED22_FIT_ONE_LAYOUT = 861            # unit: mip arrays whose sizes name exactly one layout
UED22_AMBIGUOUS = 1137                # unit: mip arrays fitting two or more, needing the tiebreak


def _texture_like(pkg) -> list[int]:
    """TEST-ONLY, and deliberately NOT `utexture.textures()`.

    The shipped `textures()` matches `class == "Texture"` EXACTLY, so `FireTexture`,
    `WetTexture`, `ScriptedTexture` and friends are never enumerated through it. Widening it is
    out of scope here — that belongs to the asset catalog, which is what will need to list
    every texture-ish object. The sweep does its own widening so it can assert what the
    procedural classes do, and asserts separately that production stays exact-match.
    """
    return [i for i in range(len(pkg.exports))
            if (pkg.class_of_export(i) or "").endswith("Texture")]


def _arrays_of(t):
    """Every mip array of one texture, each paired with ITS OWN format code. `Format` describes
    `Mips`; `CompFormat` describes `CompMips`. Judging one against the other's code is a wrong
    image, not an error."""
    out = [(t.mips, t.fmt)]
    if t.comp_mips:
        out.append((t.comp_mips, t.comp_format))
    return out


def _sweep(paths):
    """Decode every `Texture`-classed export under `paths`. Returns a census dict; the caller
    asserts on it. Nothing here raises — an exception escaping is itself the finding."""
    out = {"packages": 0, "textures": 0, "arrays": 0, "comp_arrays": 0,
           "fit_one": 0, "ambiguous": 0, "parse_failures": [], "exceptions": [],
           "layouts": {}, "sources": {}, "cases": {}, "format_census": {}}
    for path in paths:
        out["packages"] += 1
        pkg = utexture.load_package(str(path))
        for i in utexture.textures(pkg):
            out["textures"] += 1
            name = pkg.names[pkg.exports[i]["nm"]]
            try:
                t = utexture.decode_texture(pkg, i)
            except (ValueError, struct.error, IndexError) as exc:
                out["parse_failures"].append(f"{path.name}:{name}: {exc}")
                continue
            if t.trailing_bytes:
                out["parse_failures"].append(
                    f"{path.name}:{name}: {t.trailing_bytes} trailing bytes")
            out["format_census"][(t.fmt, t.comp_format if t.comp_mips else None)] = \
                out["format_census"].get((t.fmt, t.comp_format if t.comp_mips else None), 0) + 1
            for mips, code in _arrays_of(t):
                out["arrays"] += 1
                if t.comp_mips and mips is t.comp_mips:
                    out["comp_arrays"] += 1
                if mips and any(m.data for m in mips):
                    cand = set(utexture._fitting_classes(
                        mips[0].width, mips[0].height, len(mips[0].data)))
                    for m in mips[1:]:
                        cand &= utexture._fitting_classes(m.width, m.height, len(m.data))
                    if len(cand) == 1:
                        out["fit_one"] += 1
                    elif len(cand) > 1:
                        out["ambiguous"] += 1
                try:
                    got = utexture.detect_layout(mips, code=code)
                except Exception as exc:                   # noqa: BLE001 — the finding IS "it raised"
                    out["exceptions"].append(f"{path.name}:{name}: {type(exc).__name__}: {exc}")
                    continue
                if isinstance(got, utexture.Layout):
                    out["layouts"][got.name] = out["layouts"].get(got.name, 0) + 1
                    out["sources"][got.source] = out["sources"].get(got.source, 0) + 1
                else:
                    out["cases"][got.case] = out["cases"].get(got.case, 0) + 1
    return out


def test_every_tracked_texture_decodes_or_names_its_case():
    """THE SWEEP. Exact totals, because this tree is fully tracked and byte-identical on any
    checkout. Every number states its unit."""
    got = _sweep(ued22_packages())

    assert got["packages"] == UED22_PACKAGES
    assert got["textures"] == UED22_TEXTURE_EXPORTS               # unit: textures
    assert got["arrays"] == UED22_MIP_ARRAYS                      # unit: mip arrays
    assert got["comp_arrays"] == 0, \
        "this tree gained a CompMips array; the two units above no longer coincide"

    assert got["parse_failures"] == []
    assert got["exceptions"] == []

    # unit: mip arrays. 43 % of them need the format code to break a tie — not an edge case.
    assert got["fit_one"] == UED22_FIT_ONE_LAYOUT
    assert got["ambiguous"] == UED22_AMBIGUOUS

    # Not one texture in the corpus fails to name a layout.
    assert got["cases"] == {}
    assert got["layouts"] == {"linear1": UED22_MIP_ARRAYS}
    assert got["sources"] == {"data": UED22_FIT_ONE_LAYOUT,
                              "format-code": UED22_AMBIGUOUS}


def test_the_tracked_corpus_is_entirely_implied_p8():
    """The `(Format, CompFormat)` census. Every one of the 1,998 textures leaves `Format`
    unwritten — so its effective code is the implied 0 — and none carries a compressed copy.
    A regression that started mis-reading the property list shows up here as a count change
    rather than as a subtly different picture."""
    got = _sweep(ued22_packages())
    assert got["format_census"] == {(0, None): UED22_TEXTURE_EXPORTS}


def test_the_committed_fixtures_sweep_clean():
    """The same bar over the three committed fixture packages, which unlike the corpus above DO
    include a two-array texture."""
    got = _sweep([FIXTURES / n for n in ("CoreTexWater.utx", "LUM_InfoPortraits.utx",
                                         "UccCompMips.utx")])
    assert got["textures"] == 4 and got["arrays"] == 5            # 4 textures, one with CompMips
    assert got["comp_arrays"] == 1
    assert got["parse_failures"] == [] and got["exceptions"] == []
    assert got["cases"] == {}
    assert got["layouts"] == {"linear1": 4, "bc1": 1}


def test_a_procedural_texture_reports_no_mip_data_and_production_never_lists_it():
    """Procedural textures (`FireTexture` and friends) serialize mips whose `DataCount` is 0.

    Asserted against a SYNTHESIZED zero-length-mip export, not a procedural-CLASSED one: the
    fixture builder hardcodes the export class to `Texture`, so a procedural class cannot be
    synthesized, and there are **no** `FireTexture`/`WetTexture`/`IceTexture`/`WaveTexture`
    exports in any tracked material — an earlier wording asserted over an empty set and passed
    vacuously. The real procedural corpus is integration-tier.

    What IS asserted offline: the empty-mip shape reports `no-mip-data`, and the shipped
    `textures()` stays exact-match while the sweep's own matcher is wider.
    """
    assert utexture.detect_layout([utexture.Mip(64, 64, b"")], code=0).case == "no-mip-data"

    # The widening is the SWEEP's, not production's. No tracked package has a Texture SUBCLASS,
    # so the difference cannot be shown on real material — it is shown by running both matchers
    # over a package doctored to hold one, which is the only way to make the claim falsifiable.
    pkg = utexture.load_package(str(FIXTURES / "UccCompMips.utx"))
    assert utexture.textures(pkg) == _texture_like(pkg), \
        "no tracked package has a Texture subclass, so the two matchers must agree here"

    cls_ref = pkg.exports[1]["cls"]            # negative == an import; this is the CLASS ref
    pkg.names[pkg.imports[-cls_ref - 1][3]] = "FireTexture"
    assert pkg.class_of_export(1) == "FireTexture"
    assert _texture_like(pkg) == [1], "the sweep's matcher must see a Texture subclass"
    assert utexture.textures(pkg) == [], "production's exact match must NOT see it"


# --- the engine-fact pins ----------------------------------------------------------------

def _enum(pkg, name: str) -> list[str]:
    from uedcli import uprops
    for i, e in enumerate(pkg.exports):
        if pkg.name_of_ref(e["cls"]) == "Enum" and pkg.names[e["nm"]] == name:
            return uprops.enum_values(pkg, i + 1)
    raise AssertionError(f"no Enum named {name}")


def test_the_227_texture_format_enum_pins_the_four_slot_map_and_the_veto():
    """**The evidence the four-slot format map rests on**, and it is OFFLINE because
    `uned/UED22/Engine.u` is git-tracked.

    Slots 0/3/6/7 are the four the map assumes, and all three dumped engines agree on them (the
    other two dumps are integration-tier, next door). Slot **8** is pinned in the same assertion
    for a different reason: it is the evidence for the VETO. `TEXF_BC4` is a single-channel
    8-byte-block format whose mip chain is byte-for-byte the size of BC1's, so without the veto
    a BC4 texture would be drawn as BC1 — a confident wrong image on a file whose own code says
    it is not BC1. If a future substrate renames slot 8 to something we CAN decode, this goes
    red and the veto's justification has to be re-examined.
    """
    from uedcli import uprops

    pkg = uprops.load_package(str(ued22_root() / "Engine.u"), name="Engine")
    slots = _enum(pkg, "ETextureFormat")
    assert len(slots) == 122
    assert {i: slots[i] for i in (0, 3, 6, 7)} == \
        {0: "TEXF_P8", 3: "TEXF_BC1", 6: "TEXF_BC2", 7: "TEXF_BC3"}
    assert slots[8] == "TEXF_BC4"


def test_the_slot_map_in_the_decoder_matches_the_dumped_enum():
    """The map is code; the enum is evidence. Assert they agree, or the map is just a comment."""
    assert utexture._CODE_TO_CLASS == {0: "linear1", 3: "bc8", 6: "bc16", 7: "bc16"}
    assert utexture._CODE_TO_LAYOUT == {0: "linear1", 3: "bc1", 6: "bc2", 7: "bc3"}


def test_no_shipped_module_reads_the_texture_format_enum():
    """`ETextureFormat` is EVIDENCE, never a runtime dependency. If a shipped module started
    reading it, decoding would need the game's code package — which is exactly the per-game
    format table this design exists to avoid, and a lone `.utx` from an unknown engine would
    stop decoding.

    Checked against EXECUTABLE code only. Comments are invisible to the parser and docstrings
    are skipped explicitly, so the decoder may (and does) explain in prose where its four-slot
    map came from without that counting as a read.
    """
    import ast

    root = Path(utexture.__file__).resolve().parent
    tests = root / "tests"
    offenders = []
    # RECURSIVE. A non-recursive glob would skip `uedcli/native/`, `uedcli/builders/` and any
    # future subpackage — and a module under one of those reading the enum would reintroduce
    # exactly the per-game format table this design exists to avoid, with this pin still green.
    for path in sorted(root.rglob("*.py")):
        if tests in path.parents:
            continue                                 # the evidence lives in the tests, by design
        tree = ast.parse(path.read_text())
        docstrings = {id(n.value) for n in ast.walk(tree)
                      if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings and "ETextureFormat" in node.value):
                offenders.append(path.name)
    assert offenders == [], offenders
