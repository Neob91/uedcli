import struct

import pytest

from pathlib import Path

from uedcli import tool_assets
from uedcli.dxpkg import (PackageHeader, SchemaError, direct_packages, parse_header,
                          transitive_closure)
from uedcli.tests.conftest import install_content_dirs, install_root

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


def test_it_rejects_a_truncated_package_with_a_named_error(tmp_path):
    # A truncated `.u` used to escape as a bare struct.error/IndexError traceback from the raw
    # byte readers — breaking "no Python exception ever reaches the user". It must now be a
    # SchemaError (a ValueError subclass, so every existing handler catches it) naming the FILE.
    # Header claims 400 names at offset 36; the file holds nothing after the header, so the FIRST
    # compact-index read runs off the end (the generic IndexError path).
    bad = tmp_path / "truncated.u"
    bad.write_bytes(struct.pack("<9I", 0x9E2A83C1, 69, 0, 400, 36, 0, 36, 0, 36))
    with pytest.raises(SchemaError, match="truncated.u"):
        parse_header(str(bad))
    with pytest.raises(SchemaError, match="truncated.u"):
        direct_packages(str(bad))


def test_a_name_entry_running_past_eof_names_the_file(tmp_path):
    """Exercises `_read_name`'s OWN overrun guard — the branch the test above never reaches,
    because that fixture dies in the compact-index read first.

    Here the compact index parses fine and declares a 100-byte name with only 3 bytes behind it.
    The guard must fire AND the message must carry the path: `parse_header` re-raises an
    already-typed SchemaError unchanged, so an unprefixed one would reach the user with no
    filename — and `stub_closure`'s dependency walk parses files the user never named, so the
    filename is the only way to learn WHICH package is corrupt."""
    # compact index for 100: low 6 bits (36) with the continuation bit, then 100 >> 6 == 1.
    body = bytes([0x40 | 36, 0x01]) + b"abc"
    bad = tmp_path / "cutname.u"
    bad.write_bytes(struct.pack("<9I", 0x9E2A83C1, 69, 0, 1, 36, 0, 36, 0, 36) + body)
    with pytest.raises(SchemaError) as ei:
        parse_header(str(bad))
    msg = str(ei.value)
    assert "cutname.u" in msg, msg                 # the one thing item 3 required
    assert "overruns buffer" in msg and "len=100" in msg, msg


def test_a_v61_name_truncated_inside_its_flag_bytes_is_rejected(tmp_path):
    """The version-61 name layout is `<NUL-terminated string><u32 ObjectFlags>`, and nothing ever
    READS those 4 flag bytes — the string stops at the NUL and `pos` steps over them. So a file cut
    off inside them used to parse as COMPLETE: this exact 39-byte fixture returned
    `PackageHeader(version=61, names=['AB'], imports=[])` with no error, a silent wrong answer on
    the very input class the SchemaError contract exists to catch. Every OTHER v61 truncation is
    caught by `buf.index` raising; this was the one hole."""
    bad = tmp_path / "v61trunc.u"
    bad.write_bytes(struct.pack("<9I", 0x9E2A83C1, 61, 0, 1, 36, 0, 36, 0, 36) + b"AB\x00")
    assert bad.stat().st_size == 39
    with pytest.raises(SchemaError) as ei:
        parse_header(str(bad))
    assert "v61trunc.u" in str(ei.value), str(ei.value)


def test_a_v61_name_with_its_flag_bytes_intact_still_parses(tmp_path):
    """The guard is a strict LOWER bound from the format, so a complete v61 entry — the same
    fixture plus its 4 ObjectFlags bytes — must still parse. Pins that the fix cannot reject a
    real package (the install's five v61 content packages are the live case)."""
    ok = tmp_path / "v61ok.u"
    ok.write_bytes(struct.pack("<9I", 0x9E2A83C1, 61, 0, 1, 36, 0, 36, 0, 36)
                   + b"AB\x00" + b"\x00\x00\x00\x00")
    h = parse_header(str(ok))
    assert h.version == 61 and h.names == ["AB"] and h.imports == []


def test_a_utf16_name_running_past_eof_also_names_the_file(tmp_path):
    """The NEGATIVE-length (UTF-16LE) branch of the same guard — its byte count is `-length * 2`,
    so a short buffer overruns twice as fast."""
    # compact index for -40: sign bit | low 6 bits (40 & 0x3F == 40 → needs continuation).
    body = bytes([0x80 | 0x40 | (40 & 0x3F), 40 >> 6]) + b"ab"
    bad = tmp_path / "cutwide.u"
    bad.write_bytes(struct.pack("<9I", 0x9E2A83C1, 69, 0, 1, 36, 0, 36, 0, 36) + body)
    with pytest.raises(SchemaError, match="cutwide.u"):
        parse_header(str(bad))


def test_it_rejects_a_package_cut_off_mid_import_table(tmp_path):
    # Names parse; the IMPORT table's compact indices run off the end of the buffer.
    bad = tmp_path / "cut.u"
    bad.write_bytes(struct.pack("<9I", 0x9E2A83C1, 69, 0, 0, 36, 0, 36, 8, 36))
    with pytest.raises(SchemaError, match="cut.u"):
        parse_header(str(bad))


def test_it_rejects_a_file_too_small_to_hold_a_header(tmp_path):
    bad = tmp_path / "stub.u"
    bad.write_bytes(b"\xc1\x83\x2a\x9e")
    with pytest.raises(SchemaError, match="too small"):
        parse_header(str(bad))


def test_it_reports_an_unreadable_package_rather_than_raising_oserror(tmp_path):
    with pytest.raises(SchemaError, match="cannot read package"):
        parse_header(str(tmp_path / "nope.u"))


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
# (Tools/uedcli/uned/DeusExAssets/Textures/, gitignored;
# dev/docs/spikes/2026-06-18-deusex-content-install.md +
# dev/docs/specs/2026-06-20-uedcli-deusex-assets-layout-design.md).
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
