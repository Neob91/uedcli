import struct

import pytest

from pathlib import Path

from uedctl import tool_assets
from uedctl.dxpkg import (PackageHeader, direct_packages, parse_header,
                          transitive_closure)
from uedctl.tests.conftest import install_content_dirs, install_root

# Repo fixtures (retail maps under the dx_lum repo's Maps/), anchored on the tool dir's parent
# tree — test-only; production paths are project/config-derived.
MAPS = tool_assets.tool_root().parent.parent / "Maps"
INSTALL_TEXTURES = install_root() / "Textures"


def _map(name):
    p = MAPS / name
    if not p.exists():
        pytest.skip(f"map fixture {name} not present")
    return str(p)


def _install_texture(name):
    # The gitignored Deus Ex install content (dev/docs/spikes/2026-06-18-deusex-content-install.md)
    # — present on a box that's run the install spike, absent (e.g. a fresh klonr worktree) on
    # one that hasn't. Skip rather than fail; this is a real-content probe, not a fixture we ship.
    p = INSTALL_TEXTURES / name
    if not p.exists():
        pytest.skip(f"Deus Ex install content not present: {p}")
    return str(p)


def test_it_parses_a_real_dx_header_at_version_69():
    h = parse_header(_map("dx.dx"))
    assert isinstance(h, PackageHeader)
    assert h.version == 69
    assert len(h.names) > 0 and len(h.imports) > 0


def test_it_extracts_dx_dx_direct_packages_including_actor_class_packages():
    # dx.dx's import table names exactly these three (spike EVIDENCE.md). The actor-class
    # packages (Engine, Core) come from the import table, NOT from any dotted T3D ref.
    assert direct_packages(_map("dx.dx")) == {"Core", "DeusExDeco", "Engine"}


def test_it_handles_unicode_fname_lengths_without_crashing():
    # 20_AireGardens.dx carries UTF-16LE Group-name FNames; a naive ANSI parse crashes here.
    pkgs = direct_packages(_map("20_AireGardens.dx"))
    assert "Engine" in pkgs and all(p and p.isprintable() for p in pkgs)


def test_it_rejects_an_unsupported_version(tmp_path):
    # Supported: 61 (old null-term name table), 68 (install content), 69 (levels/substrate).
    # An unrecognised version must fail loudly and name the offending value — `match="version"`
    # alone would pass even if the actual version number were omitted from the message.
    bad = tmp_path / "bad.dx"
    bad.write_bytes(struct.pack("<9I", 0x9E2A83C1, 70, 0, 0, 64, 0, 64, 0, 64) + b"\x00" * 64)
    with pytest.raises(ValueError, match=r"version 70 not in \(61, 68, 69\)"):
        parse_header(str(bad))


def test_it_rejects_bad_magic(tmp_path):
    bad = tmp_path / "notpkg.dx"
    bad.write_bytes(struct.pack("<9I", 0xDEADBEEF, 69, 0, 0, 64, 0, 64, 0, 64) + b"\x00" * 64)
    with pytest.raises(ValueError, match="magic"):
        parse_header(str(bad))


def test_transitive_closure_includes_indirect_code_deps():
    # dx.dx's DIRECT set is {Core, DeusExDeco, Engine}; the closure reaches further (DeusExItems,
    # Effects via DeusExDeco.u). Effects is exactly what UCC demands at load — predicted offline.
    search = [str(tool_assets.uned_dir() / "UED22"), str(MAPS)]
    found, missing = transitive_closure(_map("dx.dx"), search_dirs=search)
    assert {"Core", "DeusExDeco", "Engine"} <= (found | missing)
    assert "Effects" in (found | missing)        # reachable only transitively


def test_transitive_closure_reports_missing_when_no_search_dirs():
    found, missing = transitive_closure(_map("dx.dx"), search_dirs=[])
    assert missing and found == set()            # no search dirs → everything is missing


def test_transitive_closure_propagates_a_root_parse_failure_instead_of_returning_empty(tmp_path):
    # Review-found 2026-06-20 (Opus 4.8 + GPT-5.4): a DEPENDENCY node that fails to parse is a
    # closure-growth dead end (it was already resolved as a real file, so the swallow is safe);
    # the ROOT was never resolved through that same check, so swallowing ITS failure would
    # silently produce an empty (found, missing) with NO signal anything went wrong — exactly
    # the under-count this function exists to prevent. A corrupt/unsupported-version root must
    # raise, not vanish.
    bad = tmp_path / "bad.dx"
    bad.write_bytes(struct.pack("<9I", 0x9E2A83C1, 70, 0, 0, 64, 0, 64, 0, 64) + b"\x00" * 64)
    with pytest.raises(ValueError, match="version"):
        transitive_closure(str(bad), search_dirs=[])


# --- content-package recursion (2026-06-20: extended past code-only) -------------------------
# parse_header/direct_packages are generic UPackage-format readers, not .dx-specific, so they
# work identically on a .utx — confirmed live against the real Deus Ex install content
# (Tools/uedctl/uned/DeusExAssets/Textures/, gitignored;
# dev/docs/spikes/2026-06-18-deusex-content-install.md +
# dev/docs/specs/2026-06-20-uedctl-deusex-assets-layout-design.md).
# These probe the EXACT live gap quirks.md "Containers / package resolution" documents:
# CoreTexMetal.utx itself depends on CoreTexDetail, a dependency no level's OWN .dx manifest
# would ever name.


def test_it_parses_a_real_content_package_at_version_68():
    # The install's content packages are overwhelmingly version 68 (levels are 69) — confirmed
    # live 2026-06-20 (89/94 sampled .utx/.uax/.umx files). Same name-table layout as 69.
    h = parse_header(_install_texture("CoreTexMetal.utx"))
    assert h.version == 68
    assert len(h.names) > 0 and len(h.imports) > 0
    assert all(n.isprintable() for n in h.names if n)        # no garbage from a layout mismatch


def test_it_extracts_coretexmetals_direct_deps_including_coretexdetail():
    # The live-confirmed gap: CoreTexMetal.utx depends on CoreTexDetail, a package no level's
    # OWN .dx import table would ever name (quirks.md "Containers / package resolution").
    pkgs = direct_packages(_install_texture("CoreTexMetal.utx"))
    assert "CoreTexDetail" in pkgs


def test_transitive_closure_recurses_into_content_packages():
    # A real map's closure now reaches CoreTexMetal's OWN dependency (CoreTexDetail) — a
    # content-to-content dependency a code-only closure could never see, since CoreTexMetal
    # itself is only reachable by recursing INTO a content package in the first place.
    _install_texture("CoreTexMetal.utx")     # skip if the install content isn't present
    search = [str(d) for d in install_content_dirs()]
    found, missing = transitive_closure(_map("19_FMA.dx"), search_dirs=search)
    assert "CoreTexMetal" in (found | missing)
    assert "CoreTexDetail" in (found | missing)


def test_transitive_closure_over_content_does_not_balloon_to_the_whole_install():
    # Measured 2026-06-20 over the real install: closures land at 6-65 packages per map, not
    # "the whole install" (~190 files) — install content isn't a circular/all-to-all graph.
    _install_texture("CoreTexMetal.utx")
    search = [str(d) for d in install_content_dirs()]
    found, missing = transitive_closure(_map("20_AireGardens.dx"), search_dirs=search)
    assert len(found | missing) < 100


def test_transitive_closure_includes_v61_content_package_in_found():
    # CoreTexDetail.utx is version 61 — parseable as of 2026-06-23 (null-terminated name table).
    # It lands in `found` whether or not its own deps (Core/Engine, substrate) are on search_dirs.
    detail = INSTALL_TEXTURES / "CoreTexDetail.utx"
    if not detail.exists():
        pytest.skip(f"Deus Ex install content not present: {detail}")
    search = [str(d) for d in install_content_dirs()]
    found, missing = transitive_closure(_map("19_FMA.dx"), search_dirs=search)
    assert "CoreTexDetail" in found      # resolved and parseable, not silently dropped


# --- version-61 content packages (2026-06-23) -------------------------------------------------
# Five Deus Ex install packages use a pre-64 name-table format: null-terminated string + 4-byte
# ObjectFlags with NO compact-index length prefix. The import table is the same compact-index
# format as 68/69.  Their own deps are just Core/Engine (substrate), so the closure terminates
# cleanly.  Confirmed live 2026-06-23; see spikes/2026-06-23-capability-gaps-round2.md.


def test_it_parses_a_real_v61_content_package():
    h = parse_header(_install_texture("CoreTexDetail.utx"))
    assert h.version == 61
    assert len(h.names) > 0 and len(h.imports) > 0
    assert all(n.isprintable() for n in h.names if n)   # no garbage from a layout mismatch


def test_it_extracts_v61_package_direct_deps():
    # All five v61 packages depend only on Core and/or Engine — no further unique deps.
    for name in ("CoreTexDetail.utx", "CoreTexWater.utx", "Palettes.utx",
                 "Render.utx", "TITAN.utx"):
        pkgs = direct_packages(_install_texture(name))
        assert pkgs <= {"Core", "Engine"}, f"{name}: unexpected deps {pkgs}"


def test_it_parses_a_forged_v61_header_with_null_terminated_names(tmp_path):
    # A minimal synthetic v61 package: 2 names ("None" + "Engine") and 0 imports.
    import struct
    names_bytes = b"None\x00" + struct.pack("<I", 0x04070410)
    names_bytes += b"Engine\x00" + struct.pack("<I", 0x00070010)
    namecnt = 2
    nameoff = 9 * 4          # immediately after the 9-int header (36 bytes)
    data = struct.pack("<9I", 0x9E2A83C1, 61, 0, namecnt, nameoff, 0, nameoff, 0, nameoff)
    data += names_bytes
    p = tmp_path / "synth.utx"
    p.write_bytes(data)
    h = parse_header(str(p))
    assert h.version == 61
    assert h.names == ["None", "Engine"]
    assert h.imports == []
