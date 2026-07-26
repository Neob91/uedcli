"""Persistent package-schema cache (`uedcli.schema_cache`) — spec
`dev/docs/specs/2026-07-18-package-schema-cache.md` §11. Engine-facts-adjacent: pins the stat-tuple
key, the marshal serialization + hand-bumped `SCHEMA_CACHE_VERSION`, the discovery/props blob split,
realpath keying, corrupt=miss, parallel-writer safety, and the accepted `os.utime` staleness caveat,
so a decoder/format change trips a red test instead of drifting.

The whole offline suite runs with the cache OFF (`conftest._schema_cache_off`); these tests opt back
IN via `cache_on`. Each uses the autouse per-test `$UEDCLI_HOME` tmp dir, so entries land in a tmp
`cache/schema/` and never touch the developer's real `~/.uedcli`.
"""
from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

import pytest

from uedcli import config, schema_cache, uprops

# A small, RICH, FROZEN committed package: 9 classes / 72 own props / 5 enum-typed props / a super
# chain — decoder coverage across class-list, cmap, import-super resolution, abstract-from-ScriptText,
# and property + local-enum decode. UED22 is baked + committed, so this runs in the OFFLINE suite.
_FIRE = Path(__file__).resolve().parents[2] / "uned" / "UED22" / "fire.u"
_GOLDEN = Path(__file__).parent / "fixtures" / "schema_golden_fire_v1.marshal"

pytestmark = pytest.mark.skipif(not _FIRE.is_file(), reason="committed UED22/fire.u not present")


@pytest.fixture
def cache_on(monkeypatch):
    """Opt this test back into the cache (the suite default is OFF) and isolate the in-process memos."""
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE", "on")
    _clear_memos()
    yield
    _clear_memos()


@pytest.fixture
def fire_copy(tmp_path):
    """A writable copy of the golden package (the mutable-file tests rewrite/utime it)."""
    dst = tmp_path / "fire.u"
    shutil.copy2(_FIRE, dst)
    return dst


def _clear_memos():
    schema_cache._DISC_MEMO.clear()
    schema_cache._PROP_MEMO.clear()


def _spy_load_package(monkeypatch):
    """Wrap `uprops.load_package` with a call counter (schema_cache calls it via `uprops.load_package`).
    Returns a 1-element list holding the count."""
    calls = [0]
    real = uprops.load_package

    def spy(*a, **k):
        calls[0] += 1
        return real(*a, **k)

    monkeypatch.setattr(uprops, "load_package", spy)
    return calls


def _blobs(home_env: str, ext: str = "*") -> list[Path]:
    root = Path(home_env) / "cache" / "schema"
    return sorted(root.rglob(f"*.{ext}")) if ext != "*" else sorted(
        p for p in root.rglob("*") if p.is_file())


# --------------------------------------------------------------------------- frozen-golden version guard

def test_frozen_golden_bundle_matches_fresh_decode():
    """HIGH-2: the committed serialized bundle (discovery + props) for the golden `.u` is byte-equal
    to a fresh decode-and-serialize. A decoder/format/version change makes them differ and trips THIS
    test red, forcing a golden refresh OR a `SCHEMA_CACHE_VERSION` bump — a reviewed choice, not silent
    drift. (A round-trip decode→serialize→deserialize would run the current decoder on BOTH sides and
    could never catch a forgotten bump; this compares against a FROZEN artifact.)"""
    assert _GOLDEN.is_file(), (
        f"missing frozen golden {_GOLDEN}; regenerate with load_package_schema('{_FIRE}', "
        "name='fire', need_props=True).golden_bytes() under UEDCLI_SCHEMA_CACHE=off")
    monkey_off = os.environ.get("UEDCLI_SCHEMA_CACHE")
    os.environ["UEDCLI_SCHEMA_CACHE"] = "off"
    try:
        _clear_memos()
        fresh = schema_cache.load_package_schema(str(_FIRE), name="fire", need_props=True).golden_bytes()
    finally:
        if monkey_off is None:
            os.environ.pop("UEDCLI_SCHEMA_CACHE", None)
        else:
            os.environ["UEDCLI_SCHEMA_CACHE"] = monkey_off
    assert fresh == _GOLDEN.read_bytes(), (
        "decoded bundle diverged from the committed golden — a decoder/serialization/Prop-layout "
        "change. Either bump SCHEMA_CACHE_VERSION and refresh the golden, or fix the regression.")


def test_decode_is_deterministic():
    """Two fresh decodes serialize byte-identically (the golden-equality guard rests on this)."""
    a = schema_cache.load_package_schema(str(_FIRE), name="fire", need_props=True).golden_bytes()
    _clear_memos()
    b = schema_cache.load_package_schema(str(_FIRE), name="fire", need_props=True).golden_bytes()
    assert a == b


# --------------------------------------------------------------------------- the discovery/props split

def test_class_list_path_does_not_decode_own_props(cache_on, fire_copy, monkeypatch):
    """The split's whole point: a discovery load (`need_props=False`, what `class list`/`ClassIndex`
    does) NEVER runs the expensive own-property decode — it writes only the `.disc` blob."""
    calls = [0]
    real = uprops.own_class_properties
    monkeypatch.setattr(uprops, "own_class_properties",
                        lambda *a, **k: (calls.__setitem__(0, calls[0] + 1), real(*a, **k))[1])
    schema_cache.load_package_schema(str(fire_copy))            # need_props defaults False
    assert calls[0] == 0                                        # own props never decoded
    files = _blobs(os.environ["UEDCLI_HOME"])
    assert [f.suffix for f in files] == [".disc"]              # only the discovery blob written


def test_need_props_writes_both_blobs_and_loads_own_props(cache_on, fire_copy):
    s = schema_cache.load_package_schema(str(fire_copy), need_props=True)
    exts = sorted(f.suffix for f in _blobs(os.environ["UEDCLI_HOME"]))
    assert exts == [".disc", ".prop"]
    assert s.own_props is not None
    assert len(s.own_props_for("WaveTexture", owner_fqcn="fire.WaveTexture")) == 4


# --------------------------------------------------------------------------- hit / miss on the stat key

def test_same_stat_is_a_hit_and_skips_load_package(cache_on, fire_copy, monkeypatch):
    calls = _spy_load_package(monkeypatch)
    s1 = schema_cache.load_package_schema(str(fire_copy), need_props=True)
    assert calls[0] == 1                                   # miss: parsed ONCE, both blobs from one load
    _clear_memos()                                         # force the ON-DISK path (not the memo)
    s2 = schema_cache.load_package_schema(str(fire_copy), need_props=True)
    assert calls[0] == 1                                   # HIT: no second load_package
    assert s1.class_list == s2.class_list and s1.super_refs == s2.super_refs
    assert s1.own_props_for("WaveTexture", owner_fqcn="fire.WaveTexture") == \
        s2.own_props_for("WaveTexture", owner_fqcn="fire.WaveTexture")


def test_props_hit_after_a_discovery_only_miss_reparses_once(cache_on, fire_copy, monkeypatch):
    """A discovery-only load writes `.disc`; a later `need_props` load reparses ONCE to add `.prop`,
    then a subsequent `need_props` load is a full hit."""
    calls = _spy_load_package(monkeypatch)
    schema_cache.load_package_schema(str(fire_copy))           # disc miss (1)
    _clear_memos()
    schema_cache.load_package_schema(str(fire_copy), need_props=True)   # disc hit, prop miss (2)
    assert calls[0] == 2
    _clear_memos()
    schema_cache.load_package_schema(str(fire_copy), need_props=True)   # both hit (still 2)
    assert calls[0] == 2


def test_stat_change_is_a_miss(cache_on, fire_copy, monkeypatch):
    calls = _spy_load_package(monkeypatch)
    schema_cache.load_package_schema(str(fire_copy))
    assert calls[0] == 1
    with open(fire_copy, "ab") as f:                       # append → new size AND new mtime_ns
        f.write(b"\x00" * 16)
    _clear_memos()
    schema_cache.load_package_schema(str(fire_copy))
    assert calls[0] == 2                                   # different stat tuple → new key → re-decode
    assert len(_blobs(os.environ["UEDCLI_HOME"], "disc")) == 2   # both entries, no stale serve


def test_utime_restored_stale_bytes_ARE_served_the_old_entry(cache_on, fire_copy, monkeypatch):
    """The accepted staleness caveat (§4.3): a content change that PRESERVES both size and mtime_ns
    (a deliberate spoof / timestamp-restoring copy over a same-size file) DOES serve the old entry.
    Documents the known limitation — and that `UEDCLI_SCHEMA_CACHE=off` bypasses it."""
    st = os.stat(fire_copy)
    s_old = schema_cache.load_package_schema(str(fire_copy))
    original = fire_copy.read_bytes()
    spoof = bytearray(original)
    spoof[len(spoof) // 2] ^= 0xFF                         # flip a byte, SAME length
    fire_copy.write_bytes(bytes(spoof))
    os.utime(fire_copy, ns=(st.st_atime_ns, st.st_mtime_ns))   # restore mtime; size already equal
    _clear_memos()
    calls = _spy_load_package(monkeypatch)
    s_stale = schema_cache.load_package_schema(str(fire_copy))
    assert calls[0] == 0                                   # served the OLD entry (the caveat)
    assert s_stale.class_list == s_old.class_list
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE", "off")       # escape hatch re-decodes the ACTUAL bytes
    _clear_memos()
    schema_cache.load_package_schema(str(fire_copy))
    assert calls[0] == 1                                   # off ⇒ always cold-decode


def test_version_bump_is_a_miss(cache_on, fire_copy, monkeypatch):
    calls = _spy_load_package(monkeypatch)
    schema_cache.load_package_schema(str(fire_copy))
    assert calls[0] == 1
    v1_key = schema_cache.cache_key(os.path.realpath(fire_copy))
    monkeypatch.setattr(schema_cache, "SCHEMA_CACHE_VERSION", schema_cache.SCHEMA_CACHE_VERSION + 1)
    _clear_memos()
    schema_cache.load_package_schema(str(fire_copy))
    assert calls[0] == 2                                   # old v<N> entry unreachable → re-decode
    v2_key = schema_cache.cache_key(os.path.realpath(fire_copy))
    assert v1_key != v2_key                                # the HASHED key string changed too
    dirs = {p.parent.name for p in _blobs(os.environ["UEDCLI_HOME"], "disc")}
    assert dirs == {f"v{schema_cache.SCHEMA_CACHE_VERSION - 1}", f"v{schema_cache.SCHEMA_CACHE_VERSION}"}


# --------------------------------------------------------------------------- realpath keying

def test_realpath_keying_shares_one_entry(cache_on, fire_copy, tmp_path, monkeypatch):
    link_a = tmp_path / "a.u"
    link_b = tmp_path / "b.u"
    link_a.symlink_to(fire_copy)
    link_b.symlink_to(fire_copy)
    calls = _spy_load_package(monkeypatch)
    schema_cache.load_package_schema(str(link_a))
    _clear_memos()
    schema_cache.load_package_schema(str(link_b))          # same realpath → same key → HIT
    assert calls[0] == 1
    assert len(_blobs(os.environ["UEDCLI_HOME"], "disc")) == 1


# --------------------------------------------------------------------------- corrupt / robustness

def test_corrupt_entry_is_a_miss_not_an_error(cache_on, fire_copy, monkeypatch):
    schema_cache.load_package_schema(str(fire_copy))       # miss → writes the .disc entry
    entry = _blobs(os.environ["UEDCLI_HOME"], "disc")[0]
    entry.write_bytes(b"not a valid marshal blob \x00\xff")
    _clear_memos()
    calls = _spy_load_package(monkeypatch)
    s = schema_cache.load_package_schema(str(fire_copy))   # corrupt ⇒ miss ⇒ re-decode, no exception
    assert calls[0] == 1
    assert "wavetexture" in s.cmap
    assert schema_cache._disc_loads(entry.read_bytes()) is not None   # rewritten valid


def test_loaders_reject_wrong_version():
    disc = schema_cache._disc_dumps(
        schema_cache._decode_discovery(uprops.load_package(str(_FIRE), name="fire")))
    assert schema_cache._disc_loads(disc) is not None
    import marshal
    d = marshal.loads(disc)
    d["v"] = 999
    assert schema_cache._disc_loads(marshal.dumps(d)) is None


def test_super_ref_for_preserves_the_no_fallback_contract():
    """A corrupt/out-of-range super ref is stored as the `""` sentinel and `super_ref_for` RE-RAISES
    it (matching the live `_super_fqcn` the cache path replaced), so the unseeded
    `resolve_class_properties` path errors on a malformed chain instead of silently truncating the
    union (spec §6). A genuine root stays `None`; a real super passes through."""
    s = schema_cache.PackageSchema(
        package_name="P", class_list=("Corrupt", "Root", "Kid"),
        cmap={"corrupt": 1, "root": 2, "kid": 3},
        super_refs={"corrupt": "", "root": None, "kid": "P.Root"},
        abstract={}, own_props=None)
    with pytest.raises(uprops.SchemaError):
        s.super_ref_for("Corrupt")
    assert s.super_ref_for("Root") is None
    assert s.super_ref_for("Kid") == "P.Root"


def test_missing_file_raises_clean_schema_error(cache_on, tmp_path):
    with pytest.raises(uprops.SchemaError):
        schema_cache.load_package_schema(str(tmp_path / "nope.u"))


def test_parallel_writers_produce_a_valid_entry(cache_on, fire_copy):
    results: list = []
    errors: list = []
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait()
            results.append(schema_cache.load_package_schema(str(fire_copy), need_props=True))
        except Exception as e:                             # noqa: BLE001
            errors.append(e)

    _clear_memos()
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len({r.golden_bytes() for r in results}) == 1   # every writer produced identical bytes
    disc = _blobs(os.environ["UEDCLI_HOME"], "disc")
    prop = _blobs(os.environ["UEDCLI_HOME"], "prop")
    assert len(disc) == 1 and len(prop) == 1
    assert schema_cache._disc_loads(disc[0].read_bytes()) is not None   # no torn read
    assert schema_cache._props_loads(prop[0].read_bytes()) is not None


def test_unwritable_cache_surfaces_as_error_not_swallowed(cache_on, fire_copy, monkeypatch):
    """A cache-write failure (classically a root-owned `~/.uedcli/cache`) MUST surface as a clean,
    actionable `CacheWriteError`, never be silently swallowed — a dead cache otherwise re-decodes every
    package every run with no hint why (the `class list` slowdown, 2026-07-18). The message names the
    two fixes: chown the dir, or `UEDCLI_SCHEMA_CACHE=off`."""
    def boom(path, data):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(schema_cache, "_atomic_write", boom)
    _clear_memos()
    with pytest.raises(schema_cache.CacheWriteError) as ei:
        schema_cache.load_package_schema(str(fire_copy))
    msg = str(ei.value)
    assert "chown" in msg and "UEDCLI_SCHEMA_CACHE=off" in msg   # actionable, not a bare OSError


def test_unwritable_cache_is_bypassed_by_the_off_escape_hatch(fire_copy, monkeypatch):
    """With the cache OFF, a would-be-failing write is never attempted, so an unwritable cache dir does
    NOT break the command — the documented escape hatch."""
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE", "off")
    def boom(path, data):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(schema_cache, "_atomic_write", boom)
    _clear_memos()
    schema_cache.load_package_schema(str(fire_copy))            # no write attempted → no error


# --------------------------------------------------------------------------- escape hatch + clear

def test_off_never_reads_or_writes(fire_copy, monkeypatch):
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE", "off")
    _clear_memos()
    calls = _spy_load_package(monkeypatch)
    schema_cache.load_package_schema(str(fire_copy))
    schema_cache.load_package_schema(str(fire_copy))
    assert calls[0] == 2                                   # every call cold-decodes
    assert _blobs(os.environ["UEDCLI_HOME"]) == []         # nothing written


def test_clear_removes_the_dir_and_is_a_noop_when_absent(cache_on, fire_copy):
    schema_cache.load_package_schema(str(fire_copy))
    root = config.schema_cache_root()
    assert root.is_dir() and _blobs(os.environ["UEDCLI_HOME"])
    assert schema_cache.clear() is True
    assert not root.exists()
    assert schema_cache.clear() is False                   # already-absent → no-op


def test_cache_clear_verb(cache_on, fire_copy, capsys):
    from uedcli import cli
    from uedcli.dispatch import dispatch
    schema_cache.load_package_schema(str(fire_copy))
    assert config.schema_cache_root().is_dir()
    rc = dispatch(cli.build_parser().parse_args(["cache", "clear"]))
    assert rc == 0
    assert not config.schema_cache_root().exists()
    assert "cleared" in capsys.readouterr().out
    assert dispatch(cli.build_parser().parse_args(["cache", "clear"])) == 0   # a 2nd clear is a no-op


# --------------------------------------------------------------------------- footprint GC (auto sweep)
# The cache self-bounds via an automatic best-effort sweep (once per process, after a blob write):
# reclaim orphaned v<older>/ dirs a version bump left unreachable + LRU-evict current-version blobs by
# atime to a byte/count cap. Immutable entries ⇒ eviction has no correctness pressure. These pin the
# reclaim, the atime LRU order, the caps, the env overrides, best-effort race tolerance, and that the
# on-write auto-trigger actually fires.

def _cur_version_dir() -> Path:
    return config.schema_cache_root() / f"v{schema_cache.SCHEMA_CACHE_VERSION}"


def _make_blob(name: str, size: int, atime_ns: int) -> Path:
    """Drop a fake blob of `size` bytes into the CURRENT version dir with an explicit atime (so LRU
    order is deterministic regardless of the mount's atime policy)."""
    d = _cur_version_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(b"x" * size)
    os.utime(p, ns=(atime_ns, atime_ns))
    return p


def test_reclaim_old_version_dirs_removes_only_orphan_version_buckets(cache_on):
    """A `SCHEMA_CACHE_VERSION` bump orphans every `v<other>/` dir; reclaim deletes exactly those,
    leaving the current bucket AND any non-version-named sibling untouched."""
    ver = schema_cache.SCHEMA_CACHE_VERSION
    root = config.schema_cache_root()
    cur = root / f"v{ver}"
    orphan_lo = root / f"v{ver - 1}"
    orphan_hi = root / f"v{ver + 1}"
    not_a_version = root / "notes"
    for d in (cur, orphan_lo, orphan_hi, not_a_version):
        d.mkdir(parents=True)
        (d / "blob.disc").write_bytes(b"x")
    removed = schema_cache.reclaim_old_version_dirs()
    assert removed == 2
    assert cur.is_dir() and not_a_version.is_dir()          # current + non-version left alone
    assert not orphan_lo.exists() and not orphan_hi.exists()


def test_reclaim_tolerates_missing_root(cache_on):
    """No cache dir yet ⇒ a clean no-op, never an error."""
    assert not config.schema_cache_root().exists()
    assert schema_cache.reclaim_old_version_dirs() == 0


def test_evict_lru_removes_oldest_atime_until_under_byte_cap(cache_on):
    a = _make_blob("a.disc", 100, atime_ns=1 * 10**18)      # oldest
    b = _make_blob("b.disc", 100, atime_ns=2 * 10**18)
    c = _make_blob("c.disc", 100, atime_ns=3 * 10**18)      # newest
    stats = schema_cache.evict_lru(max_bytes=150, max_entries=None)
    assert not a.exists() and not b.exists()               # 300B > 150B ⇒ drop the two oldest
    assert c.exists()                                       # newest-atime survives
    assert stats["evicted"] == 2 and stats["kept_bytes"] == 100 and stats["kept_entries"] == 1
    assert stats["freed_bytes"] == 200


def test_evict_lru_honors_entry_count_cap(cache_on):
    for i, at in enumerate((10, 20, 30, 40)):
        _make_blob(f"{i}.disc", 10, atime_ns=at * 10**16)
    stats = schema_cache.evict_lru(max_bytes=None, max_entries=2)
    assert stats["kept_entries"] == 2
    assert {p.name for p in _cur_version_dir().iterdir()} == {"2.disc", "3.disc"}   # the two newest


def test_evict_lru_noop_when_under_cap(cache_on):
    a = _make_blob("a.disc", 50, atime_ns=1 * 10**18)
    stats = schema_cache.evict_lru(max_bytes=10_000)
    assert a.exists() and stats["evicted"] == 0 and stats["kept_entries"] == 1


def test_evict_lru_tolerates_unlink_race(cache_on, monkeypatch):
    """A blob that vanishes / can't be unlinked mid-sweep (a racing writer, a perms glitch) is skipped,
    never raised — best-effort footprint control."""
    a = _make_blob("a.disc", 100, atime_ns=1 * 10**18)      # oldest → first eviction candidate
    b = _make_blob("b.disc", 100, atime_ns=2 * 10**18)
    real_unlink = os.unlink

    def flaky(path, *args, **kw):
        if str(path).endswith("a.disc"):
            raise OSError("racing writer already removed it")
        return real_unlink(path, *args, **kw)

    monkeypatch.setattr(os, "unlink", flaky)
    schema_cache.evict_lru(max_bytes=50)                    # both over cap; a fails, b succeeds
    assert a.exists() and not b.exists()                   # no exception; the removable one went


def test_sweep_combines_reclaim_and_eviction(cache_on):
    ver = schema_cache.SCHEMA_CACHE_VERSION
    orphan = config.schema_cache_root() / f"v{ver + 1}"
    orphan.mkdir(parents=True)
    (orphan / "stale.disc").write_bytes(b"x")
    _make_blob("old.disc", 200, atime_ns=1 * 10**18)
    keep = _make_blob("new.disc", 200, atime_ns=9 * 10**18)
    stats = schema_cache.sweep(max_bytes=200, max_entries=None)
    assert stats["removed_version_dirs"] == 1 and not orphan.exists()
    assert stats["evicted"] == 1 and keep.exists()


def test_sweep_defaults_to_env_or_constant_caps(cache_on, monkeypatch):
    """The `-1` sentinel means 'use the env-or-constant default'; a tiny env cap makes the sweep evict."""
    _make_blob("a.disc", 4096, atime_ns=1 * 10**18)
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE_MAX_BYTES", "1024")
    stats = schema_cache.sweep()                            # no explicit caps ⇒ reads the env override
    assert stats["evicted"] == 1 and stats["kept_bytes"] == 0


def test_default_cap_env_parsing_and_fallback(monkeypatch):
    monkeypatch.delenv("UEDCLI_SCHEMA_CACHE_MAX_BYTES", raising=False)
    assert schema_cache._default_max_bytes() == schema_cache.SCHEMA_CACHE_MAX_BYTES
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE_MAX_BYTES", "4096")
    assert schema_cache._default_max_bytes() == 4096
    for bad in ("garbage", "-5", ""):                       # garbage / negative / blank ⇒ fall back
        monkeypatch.setenv("UEDCLI_SCHEMA_CACHE_MAX_BYTES", bad)
        assert schema_cache._default_max_bytes() == schema_cache.SCHEMA_CACHE_MAX_BYTES
    monkeypatch.delenv("UEDCLI_SCHEMA_CACHE_MAX_ENTRIES", raising=False)
    assert schema_cache._default_max_entries() is None      # count cap is off by default
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE_MAX_ENTRIES", "0")
    assert schema_cache._default_max_entries() == 0


def _run_cli(*argv) -> int:
    from uedcli import cli
    from uedcli.dispatch import dispatch
    return dispatch(cli.build_parser().parse_args(list(argv)))


def test_cache_gc_verb_reclaims_orphans_and_evicts_to_the_given_cap(cache_on, capsys):
    """`uedcli cache gc` is the on-demand surface over the same `sweep()` the on-write auto-GC runs:
    orphaned version dirs go, current-version blobs LRU-evict to `--max-bytes`, and the summary
    reports what happened."""
    ver = schema_cache.SCHEMA_CACHE_VERSION
    orphan = config.schema_cache_root() / f"v{ver + 1}"
    orphan.mkdir(parents=True)
    (orphan / "stale.disc").write_bytes(b"x")
    old = _make_blob("old.disc", 200, atime_ns=1 * 10**18)
    keep = _make_blob("new.disc", 200, atime_ns=9 * 10**18)
    assert _run_cli("cache", "gc", "--max-bytes", "200") == 0
    assert not orphan.exists() and not old.exists() and keep.exists()
    out = capsys.readouterr().out
    assert "removed 1 old version dir(s)" in out and "evicted 1 entries" in out
    assert "kept 1 entries (200 bytes)" in out


def test_cache_gc_max_entries_caps_the_blob_count(cache_on, capsys):
    for i, at in enumerate((10, 20, 30)):
        _make_blob(f"{i}.disc", 10, atime_ns=at * 10**16)
    assert _run_cli("cache", "gc", "--max-entries", "1") == 0
    assert {p.name for p in _cur_version_dir().iterdir()} == {"2.disc"}   # newest atime survives


def test_cache_gc_without_flags_uses_the_env_or_constant_caps(cache_on, monkeypatch, capsys):
    _make_blob("a.disc", 4096, atime_ns=1 * 10**18)
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE_MAX_BYTES", "1024")
    assert _run_cli("cache", "gc") == 0
    assert not (_cur_version_dir() / "a.disc").exists()


def test_cache_gc_on_an_absent_cache_is_a_clean_noop(cache_on, capsys):
    """No cache dir yet ⇒ exit 0 with a zeroed summary, never an error (a footprint GC must never be
    the thing that breaks a command)."""
    assert not config.schema_cache_root().exists()
    assert _run_cli("cache", "gc") == 0
    assert "evicted 0 entries" in capsys.readouterr().out


def test_cache_gc_rejects_a_negative_cap(cache_on, capsys):
    """A negative cap is meaningless (it is NOT a spelling of 'unbounded') — clean exit 2 naming the
    flag and the value, never a Python error."""
    for flag in ("--max-bytes", "--max-entries"):
        assert _run_cli("cache", "gc", flag, "-1") == 2
        assert f"cache gc {flag}: must be >= 0, got -1" in capsys.readouterr().err


def test_auto_sweep_fires_once_on_write_and_reclaims_orphan(cache_on, fire_copy):
    """The automatic trigger: a real cache write runs the sweep (once), reclaiming an orphaned version
    dir without any manual `cache clear`. The current bucket and the just-written entry survive."""
    ver = schema_cache.SCHEMA_CACHE_VERSION
    orphan = config.schema_cache_root() / f"v{ver + 1}"
    orphan.mkdir(parents=True)
    (orphan / "stale.disc").write_bytes(b"x")
    assert schema_cache._SWEPT is False                     # reset per-test by conftest
    schema_cache.load_package_schema(str(fire_copy))        # a write → _maybe_auto_sweep()
    assert schema_cache._SWEPT is True
    assert not orphan.exists()                              # orphan reclaimed automatically
    assert _cur_version_dir().is_dir() and list(_cur_version_dir().glob("*.disc"))  # live entry kept


def test_auto_sweep_evicts_lru_under_env_byte_cap(cache_on, fire_copy, monkeypatch):
    """With a small env byte cap, the on-write auto-sweep evicts an old LRU filler while keeping the
    freshly-written (newest-atime) live blob — the cap set well above any single real blob."""
    filler = _make_blob("filler.disc", 1_000_000, atime_ns=1)   # huge + oldest
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE_MAX_BYTES", "512000")
    schema_cache.load_package_schema(str(fire_copy))            # write real .disc (newest) + auto-sweep
    assert not filler.exists()                                  # LRU filler evicted under the cap
    remaining = [p.name for p in _cur_version_dir().iterdir()]
    assert remaining and "filler.disc" not in remaining        # the live blob survived


def test_auto_sweep_runs_at_most_once_per_process(cache_on, fire_copy, monkeypatch):
    """The gate: once `_SWEPT` is set, later writes in the same process do NOT re-sweep (a full-dir
    scan per blob would be wasteful) — so an orphan created AFTER the first sweep is not reclaimed
    until the next process."""
    calls = [0]
    real = schema_cache.sweep
    monkeypatch.setattr(schema_cache, "sweep", lambda *a, **k: (calls.__setitem__(0, calls[0] + 1), real(*a, **k))[1])
    schema_cache.load_package_schema(str(fire_copy), need_props=True)   # writes .disc + .prop
    assert calls[0] == 1                                        # swept once despite two writes
    _clear_memos()
    schema_cache.load_package_schema(str(fire_copy), need_props=True)   # all hits, no write
    assert calls[0] == 1


# --------------------------------------------------------------------------- v1 consumer equivalence

def _ued22_files(*stems):
    base = _FIRE.parent
    return [(s, str(base / f"{s}.u")) for s in stems if (base / f"{s}.u").is_file()]


def test_classindex_results_identical_warm_vs_cold(monkeypatch):
    """The rewired ClassIndex consumers (`_cmap`/`_all_fqcns`/`is_abstract`/`children_map`) produce
    byte-identical results whether decoding cold or reading a warm cache entry — the v1 equivalence
    guarantee for the `class list` path (spec §11)."""
    from uedcli.classindex import ClassIndex
    files = _ued22_files("fire", "core", "Engine")

    def snapshot():
        idx = ClassIndex.from_files(files)
        return (sorted(idx._all_fqcns()),
                {k: sorted(v) for k, v in idx.children_map().items()},
                {f: idx.is_abstract(f) for f in idx._all_fqcns()},
                {s: idx._cmap(s) for s, _ in files})

    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE", "off")
    _clear_memos()
    cold = snapshot()
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE", "on")
    _clear_memos()
    warm_miss = snapshot()                                 # populates the cache
    _clear_memos()
    warm_hit = snapshot()                                  # reads the cache
    assert cold == warm_miss == warm_hit


def test_resolve_class_properties_schema_path_equals_seeded(cache_on):
    """`resolve_class_properties` yields identical Props via the schema-cache path and via a
    pre-seeded live `Package` (the still-supported seed capability, though `class show` no longer uses
    it as of 2026-07-20) — so rewiring the union onto the cache changes nothing observable."""
    files = {s.casefold(): p for s, p in _ued22_files("fire", "core", "Engine")}
    resolver = lambda name: files.get(name.casefold())    # noqa: E731  (real resolvers are FName-cased)

    fqcn = "fire.WaveTexture"
    via_cache = uprops.resolve_class_properties(fqcn, resolver=resolver)
    seed = {"fire": uprops.load_package(files["fire"], name="fire")}
    via_seed = uprops.resolve_class_properties(fqcn, resolver=resolver, _cache=seed)
    assert via_cache == via_seed
    assert [p.name for p in via_cache] == [p.name for p in via_seed]


def test_resolve_class_properties_identical_cache_on_vs_off(monkeypatch):
    """The escape hatch changes nothing observable: the union is identical whether decoded via the
    schema cache (ON) or the live per-package path (OFF)."""
    files = {s.casefold(): p for s, p in _ued22_files("fire", "core", "Engine")}
    resolver = lambda name: files.get(name.casefold())    # noqa: E731
    fqcn = "fire.WaveTexture"
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE", "off")
    _clear_memos()
    off = uprops.resolve_class_properties(fqcn, resolver=resolver)
    monkeypatch.setenv("UEDCLI_SCHEMA_CACHE", "on")
    _clear_memos()
    on = uprops.resolve_class_properties(fqcn, resolver=resolver)
    assert off == on and [p.name for p in off] == [p.name for p in on]
