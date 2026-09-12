"""Unit tests for upackage.py's Rust-backed core. Broader coverage (real files, every existing
caller) lives in test_dxpkg.py/test_utexture_corpus.py/test_native_roundtrip.py/uscript's own
suites — this file covers upackage.py's own new surface directly."""
import struct

import pytest

import uedcli.upackage
from uedcli.upackage import (MAGIC, NameEntry, Package, SchemaError, load_package,
                             parse_package_bytes, read_compact_index, read_fstring)


def _synthetic_v69_empty() -> bytes:
    """The smallest valid v69 package: one name ("None"), no imports, no exports."""
    names_blob = bytes([0x04]) + b"None" + struct.pack("<I", 0)
    header_fixed = 36
    name_offset = header_fixed + 16  # header + GUID
    buf = bytearray(name_offset)
    struct.pack_into("<9I", buf, 0,
                      MAGIC, 69, 0, 1, name_offset, 0,
                      name_offset + len(names_blob), 0, name_offset + len(names_blob))
    buf += names_blob
    return bytes(buf)


def test_parses_synthetic_package_and_keeps_names_as_bare_strings():
    pkg = parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Test")
    assert pkg.names == ["None"]
    assert pkg.version == 69
    assert pkg.licensee == 0


def test_name_entries_carries_flags_alongside_names():
    pkg = parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Test")
    assert pkg.name_entries == [NameEntry(text="None", flags=0)]
    assert len(pkg.name_entries) == len(pkg.names)


def test_guid_range_present_for_v68_plus_absent_below():
    pkg = parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Test")
    assert pkg.guid_range == (36, 52)


def test_table_offsets_exposed():
    pkg = parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Test")
    assert pkg.name_offset == 52
    assert pkg.name_count == 1
    assert pkg.import_count == 0
    assert pkg.export_count == 0


def test_bad_magic_raises_schema_error():
    with pytest.raises(SchemaError):
        parse_package_bytes(b"not a package" + b"\x00" * 40, where="<test>")


def test_absurd_declared_count_raises_schema_error():
    buf = bytearray(_synthetic_v69_empty())
    struct.pack_into("<I", buf, 12, 0xFFFFFFFF)  # namecnt
    with pytest.raises(SchemaError):
        parse_package_bytes(bytes(buf), where="<test>")


def test_read_compact_index_still_works_standalone():
    assert read_compact_index(bytes([0x05]), 0) == (5, 1)
    assert read_compact_index(bytes([0x85]), 0) == (-5, 1)


def test_read_fstring_still_works_standalone():
    assert read_fstring(bytes([0x03]) + b"Foo", 0) == ("Foo", 4)


def test_dx_unicode_group_name_decodes(tmp_path):
    """The negative-length UTF-16LE branch upackage.py previously lacked (only dxpkg.py had it)."""
    import pathlib
    fixture = pathlib.Path("/workspace/dx_lum/Maps/20_AireGardens.dx")
    if not fixture.exists():
        pytest.skip("real DX Unicode-name fixture not present on this host")
    pkg = load_package(str(fixture))
    assert any("\x00" not in n for n in pkg.names)  # sanity: names decoded, not raw garbage


def test_load_package_memoizes_within_a_process(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_PKG_CACHE", "off")  # exercise only the in-process tier
    pkg_path = tmp_path / "Test.u"
    pkg_path.write_bytes(_synthetic_v69_empty())

    calls = []
    real_parse = uedcli.upackage.parse_package_bytes

    def counting_parse(buf, **kw):
        calls.append(1)
        return real_parse(buf, **kw)

    monkeypatch.setattr(uedcli.upackage, "parse_package_bytes", counting_parse)

    first = uedcli.upackage.load_package(str(pkg_path))
    second = uedcli.upackage.load_package(str(pkg_path))
    assert first is second  # same cached object, not just equal
    assert len(calls) == 1


def test_load_package_different_names_do_not_share_the_in_process_entry(tmp_path, monkeypatch):
    """The in-process `_LOAD_CACHE` tier's own version of the name-collision bug fixed for
    `pkg_cache.py` (see `test_pkg_cache.py::test_different_name_same_file_does_not_share_an_entry`):
    the SAME file loaded under two different `name=` requests must not share a cache entry, or the
    second caller gets a `Package` whose `.name` belongs to the first."""
    monkeypatch.setenv("UEDCLI_PKG_CACHE", "off")  # exercise only the in-process tier
    pkg_path = tmp_path / "fire.u"
    pkg_path.write_bytes(_synthetic_v69_empty())

    capital = uedcli.upackage.load_package(str(pkg_path), name="Fire")
    lower = uedcli.upackage.load_package(str(pkg_path), name="fire")
    assert capital is not lower
    assert capital.name == "Fire"
    assert lower.name == "fire"


def test_load_package_cache_invalidates_on_mtime_change(tmp_path, monkeypatch):
    import os

    monkeypatch.setenv("UEDCLI_PKG_CACHE", "off")  # exercise only the in-process tier
    pkg_path = tmp_path / "Test.u"
    pkg_path.write_bytes(_synthetic_v69_empty())
    first = uedcli.upackage.load_package(str(pkg_path))

    st = os.stat(pkg_path)
    # Bump mtime_ns deterministically (no sleep-and-hope) to a value the cache hasn't seen,
    # keeping size identical -- proves invalidation keys on mtime_ns, not just size.
    os.utime(pkg_path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    second = uedcli.upackage.load_package(str(pkg_path))
    assert first is not second
