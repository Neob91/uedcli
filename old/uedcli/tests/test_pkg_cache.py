"""Tests for the on-disk decoded-package cache (`pkg_cache.py`) — the second tier below
`upackage.load_package`'s in-process memoization, surviving across separate CLI invocations.
Mirrors `test_schema_cache.py`'s isolation pattern: each test sets `UEDCLI_HOME` to a tmp dir so
entries never touch the developer's real `~/.uedcli`."""
from __future__ import annotations

import os
import sys

import pytest

from uedcli import config, pkg_cache
from uedcli.upackage import NameEntry, Package, parse_package_bytes
from uedcli.tests.test_upackage import _synthetic_v69_empty


def _synthetic_pkg():
    return parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Test")


def test_write_then_read_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", "Test", 123, 456, pkg)
    back = pkg_cache.read("/fake/Test.u", "Test", 123, 456)
    assert back is not None
    assert back == pkg  # every Package field, via the dataclass's own __eq__


def test_different_name_same_file_does_not_share_an_entry(tmp_path, monkeypatch):
    """Reproduces the reported bug (v3): `upackage.load_package`/`pkg_cache` cached the SAME file
    across DIFFERENT `name=` requests as one entry, so `resolve_class_properties` loading `fire.u`
    as `name="Fire"` (from the FQCN `Fire.Flame`) poisoned a later `name="fire"` request for the
    SAME file — a real, reproduced failure (`test_schema_cache.py`'s golden test only when
    `test_proceduraltex.py` ran first). `name` must be part of the cache key."""
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    pkg_capital = parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Fire")
    pkg_cache.write("/fake/fire.u", "Fire", 123, 456, pkg_capital)
    assert pkg_cache.read("/fake/fire.u", "fire", 123, 456) is None  # different name -> miss, not the "Fire" entry
    pkg_lower = parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="fire")
    pkg_cache.write("/fake/fire.u", "fire", 123, 456, pkg_lower)
    back_capital = pkg_cache.read("/fake/fire.u", "Fire", 123, 456)
    back_lower = pkg_cache.read("/fake/fire.u", "fire", 123, 456)
    assert back_capital is not None and back_capital.name == "Fire"
    assert back_lower is not None and back_lower.name == "fire"


def test_read_reinterns_pre_interning_blobs(tmp_path, monkeypatch):
    """Reproduces the reported bug: a blob written from a `Package` built the OLD (pre-`e1a03472`)
    way — no `sys.intern()` on its strings — must come back re-interned on read, not served as-is,
    or `golden_bytes()`'s marshal encoding is unstable again (same divergence class the interning
    fix on the direct-decode path was meant to eliminate).

    `marshal` doesn't auto-intern plain string values (verified separately), so identity against a
    canonical reference interned BEFORE the round trip is a real proof of `_from_blob`'s own
    `sys.intern()` call — unlike `x is sys.intern(x)`, which trivially self-interns on first use."""
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    canonical_name = sys.intern("".join(["Pk", "gX"]))
    canonical_n0 = sys.intern("".join(["N", "one"]))   # not the interned "None" singleton
    canonical_n1 = sys.intern("".join(["Cl", "assY"]))

    # OLD (pre-`e1a03472`) construction: plain concatenation, no `sys.intern()` — equal in value to
    # the canonical references above but a distinct object each.
    name = "".join(["Pk", "gX"])
    n0 = "".join(["N", "one"])
    n1 = "".join(["Cl", "assY"])
    assert name is not canonical_name and n0 is not canonical_n0 and n1 is not canonical_n1

    pkg = Package(
        name=name, version=69, names=[n0, n1], imports=[], exports=[], buf=b"",
        name_entries=[NameEntry(text=n0, flags=0), NameEntry(text=n1, flags=0)],
    )
    pkg_cache.write("/fake/Old.u", "PkgX", 1, 1, pkg)
    back = pkg_cache.read("/fake/Old.u", "PkgX", 1, 1)
    assert back is not None
    assert back.name is canonical_name
    assert back.names[0] is canonical_n0
    assert back.names[1] is canonical_n1
    assert back.name_entries[0].text is canonical_n0
    assert back.name_entries[1].text is canonical_n1


def test_stat_mismatch_is_a_miss(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", "Test", 123, 456, pkg)
    assert pkg_cache.read("/fake/Test.u", "Test", 123, 999) is None  # different mtime_ns
    assert pkg_cache.read("/fake/Test.u", "Test", 999, 456) is None  # different size
    assert pkg_cache.read("/other/Test.u", "Test", 123, 456) is None  # different path


def test_disabled_via_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    monkeypatch.setenv("UEDCLI_PKG_CACHE", "off")
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", "Test", 123, 456, pkg)
    assert pkg_cache.read("/fake/Test.u", "Test", 123, 456) is None
    root = config.pkg_cache_root()
    assert not root.exists() or not any(root.rglob("*.pkg"))  # nothing written


def test_write_failure_raises_loud_error(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path / "readonly"))
    (tmp_path / "readonly").mkdir()
    (tmp_path / "readonly").chmod(0o500)  # no write permission
    pkg = _synthetic_pkg()
    with pytest.raises(pkg_cache.CacheWriteError):
        pkg_cache.write("/fake/Test.u", "Test", 123, 456, pkg)
    (tmp_path / "readonly").chmod(0o700)  # restore so pytest can clean up tmp_path


def test_write_failure_is_bypassed_by_the_off_escape_hatch(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path / "readonly"))
    monkeypatch.setenv("UEDCLI_PKG_CACHE", "off")
    (tmp_path / "readonly").mkdir()
    (tmp_path / "readonly").chmod(0o500)
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", "Test", 123, 456, pkg)  # no write attempted -> no error
    (tmp_path / "readonly").chmod(0o700)


def test_corrupt_entry_is_a_miss_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", "Test", 123, 456, pkg)
    root = config.pkg_cache_root()
    blobs = list(root.rglob("*.pkg"))
    assert len(blobs) == 1
    blobs[0].write_bytes(b"not a valid marshal blob \x00\xff")
    assert pkg_cache.read("/fake/Test.u", "Test", 123, 456) is None


def test_clear_removes_the_dir_and_is_a_noop_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", "Test", 123, 456, pkg)
    assert config.pkg_cache_root().is_dir()
    assert pkg_cache.clear() is True
    assert not config.pkg_cache_root().exists()
    assert pkg_cache.clear() is False


def test_sweep_reclaims_orphan_version_dirs_and_evicts_lru(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    ver = pkg_cache.CACHE_VERSION
    root = config.pkg_cache_root()
    orphan = root / f"v{ver + 1}"
    orphan.mkdir(parents=True)
    (orphan / "stale.pkg").write_bytes(b"x")
    cur = root / f"v{ver}"
    cur.mkdir(parents=True)
    old = cur / "old.pkg"
    old.write_bytes(b"x" * 200)
    os.utime(old, ns=(1 * 10**18, 1 * 10**18))
    keep = cur / "new.pkg"
    keep.write_bytes(b"x" * 200)
    os.utime(keep, ns=(9 * 10**18, 9 * 10**18))
    stats = pkg_cache.sweep(max_bytes=200, max_entries=None)
    assert stats["removed_version_dirs"] == 1 and not orphan.exists()
    assert stats["evicted"] == 1 and not old.exists() and keep.exists()


def test_cache_gc_verb_covers_both_caches(tmp_path, monkeypatch, capsys):
    from uedcli import schema_cache
    from uedcli.cli import main as cli
    from uedcli.cli.dispatch import dispatch

    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE", "on")
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", "Test", 123, 456, pkg)
    assert config.pkg_cache_root().is_dir()

    rc = dispatch(cli.build_parser().parse_args(["cache", "gc"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert str(config.schema_cache_root()) in out
    assert str(config.pkg_cache_root()) in out


def test_cache_clear_verb_covers_both_caches(tmp_path, monkeypatch, capsys):
    from uedcli.cli import main as cli
    from uedcli.cli.dispatch import dispatch

    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", "Test", 123, 456, pkg)
    assert config.pkg_cache_root().is_dir()

    rc = dispatch(cli.build_parser().parse_args(["cache", "clear"]))
    assert rc == 0
    assert not config.pkg_cache_root().exists()
    out = capsys.readouterr().out
    assert str(config.pkg_cache_root()) in out
