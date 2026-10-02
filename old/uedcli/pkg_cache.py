"""On-disk cache for decoded package primitives (name/import/export tables + the raw bytes) — the
SECOND tier below `upackage.load_package`'s in-process memoization, surviving across separate cold
`uedcli` CLI invocations. Mirrors `schema_cache.py`'s exact proven scheme: the same stat-tuple hash
key, `marshal` serialization, `_atomic_write`, loud write-failure error, env-var off-switch, and
footprint GC (`sweep()`/`uedcli cache gc`) — see that module's docstring for the rationale (§4 of
`dev/docs/direction/packages.md`: "decoded package primitives are cached per-package on disk... A
cache that cannot be written is a loud, actionable error naming the directory.").

Unlike `schema_cache.py` (which derives a smaller class-schema bundle from a `Package`), this tier
caches the `Package` itself — the whole point is skipping `load_package`'s table parse entirely on
a warm hit, before any use-case decoder runs.
"""
from __future__ import annotations

import hashlib
import marshal
import os
import re
import shutil
import stat as _stat
import sys
from pathlib import Path

from . import config
from .stub_cache import _atomic_write
from .upackage import NameEntry, Package

# Bump on ANY change to `Package`'s fields, this module's blob shape, or the cache-key derivation.
# A bump makes every old entry unreachable (new key + new v<N>/ dir) — a corrupt/wrong-version entry
# is a miss, never an error. v2: `_from_blob` now re-interns decoded strings (see below) — old v1
# blobs predate that and must not be read back as-is. v3: the key now includes the requested `name`
# — a real, reproduced bug found `Package.name` alone (not size/mtime) could differ per caller for
# the SAME file (e.g. `resolve_class_properties` requests `name="Fire"` for `Fire.Flame` while
# another caller requests `name="fire"` for the same `fire.u`); caching by `(realpath, size,
# mtime_ns)` alone served one caller's name to the other. See `upackage.load_package`'s docstring.
CACHE_VERSION = 3

# Footprint cap for the on-disk package cache, mirroring SCHEMA_CACHE_MAX_BYTES. Entries are
# immutable/content-keyed, so eviction has no correctness pressure. Overridable per-process (mainly
# for tests): UEDCLI_PKG_CACHE_MAX_BYTES / UEDCLI_PKG_CACHE_MAX_ENTRIES.
PKG_CACHE_MAX_BYTES = 256 * 1024 * 1024
PKG_CACHE_MAX_ENTRIES: int | None = None

_VERSION_DIR_RE = re.compile(r"^v(\d+)$")

# The automatic best-effort footprint sweep runs at most once per process (see schema_cache.py).
_SWEPT = False


class CacheWriteError(Exception):
    """The on-disk package cache directory could not be written. Never swallowed — a silently
    dead cache re-decodes every package on every run, invisibly."""


def _enabled() -> bool:
    """The cache is ON unless `UEDCLI_PKG_CACHE=off` (any other value/unset = on)."""
    return os.environ.get("UEDCLI_PKG_CACHE", "").strip().lower() != "off"


def _cache_key(realpath: str, name: str, size: int, mtime_ns: int) -> str:
    key = f"{CACHE_VERSION}\0{realpath}\0{name}\0{size}\0{mtime_ns}"
    return hashlib.sha1(key.encode("utf-8", "surrogatepass")).hexdigest()


def _blob_path(realpath: str, name: str, size: int, mtime_ns: int) -> Path:
    key = _cache_key(realpath, name, size, mtime_ns)
    return config.pkg_cache_root() / f"v{CACHE_VERSION}" / f"{key}.pkg"


def _to_blob(pkg: Package) -> dict:
    return dict(
        v=CACHE_VERSION, name=pkg.name, version=pkg.version, names=pkg.names,
        imports=pkg.imports, exports=pkg.exports, buf=pkg.buf,
        name_entries=[(e.text, e.flags) for e in pkg.name_entries],
        licensee=pkg.licensee, name_offset=pkg.name_offset, name_count=pkg.name_count,
        import_offset=pkg.import_offset, import_count=pkg.import_count,
        export_offset=pkg.export_offset, export_count=pkg.export_count,
        guid_range=pkg.guid_range,
    )


def _from_blob(d: dict) -> Package:
    # Re-intern strings on the read path (defense in depth beyond the CACHE_VERSION bump above): a
    # blob written by pre-interning code, or by any future decoder that forgets to intern, must not
    # reintroduce the marshal-encoding instability `e1a03472` fixed on the direct-decode path.
    return Package(
        name=sys.intern(d["name"]), version=d["version"],
        names=[sys.intern(n) for n in d["names"]], imports=d["imports"],
        exports=d["exports"], buf=d["buf"],
        name_entries=[NameEntry(text=sys.intern(t), flags=f) for t, f in d["name_entries"]],
        licensee=d["licensee"], name_offset=d["name_offset"], name_count=d["name_count"],
        import_offset=d["import_offset"], import_count=d["import_count"],
        export_offset=d["export_offset"], export_count=d["export_count"],
        guid_range=d["guid_range"],
    )


def _pkg_loads(data: bytes) -> Package | None:
    """Deserialize a package blob, or None if corrupt / wrong version / malformed (⇒ miss). Broad
    except: marshal can raise a variety of types on malformed input, and a shape-valid-but-wrong-arity
    blob (e.g. a `name_entries` entry with the wrong tuple arity) can raise inside `_from_blob`'s own
    unpacking — both must be a silent miss, never a crash (mirrors `schema_cache._disc_loads`)."""
    try:
        blob = marshal.loads(data)
        if not isinstance(blob, dict) or blob.get("v") != CACHE_VERSION:
            return None
        return _from_blob(blob)
    except Exception:
        return None


def read(realpath: str, name: str, size: int, mtime_ns: int) -> Package | None:
    """A warm hit for `(realpath, name, size, mtime_ns)`, or None on a miss/corrupt/wrong-version
    entry (never an error — the caller falls through to a cold decode). `name` is part of the key:
    see `CACHE_VERSION`'s v3 note — the same file loaded under two different names must not share
    an entry."""
    if not _enabled():
        return None
    path = _blob_path(realpath, name, size, mtime_ns)
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    return _pkg_loads(data)


def write(realpath: str, name: str, size: int, mtime_ns: int, pkg: Package) -> None:
    """Persist `pkg` under `(realpath, name, size, mtime_ns)`. Raises `CacheWriteError` (never a
    bare OSError/traceback) if the cache dir can't be written; escape hatch is
    `UEDCLI_PKG_CACHE=off`."""
    if not _enabled():
        return
    path = _blob_path(realpath, name, size, mtime_ns)
    try:
        _atomic_write(path, marshal.dumps(_to_blob(pkg)))
    except OSError as e:
        raise CacheWriteError(
            f"cannot write the package cache under {config.user_cache_home()}: {e}\n"
            f"The persistent on-disk package cache is unwritable, so every command must re-decode "
            f"all packages (slow). Fix the directory's ownership/permissions, e.g.\n"
            f"    sudo chown -R $(id -u):$(id -g) {config.user_cache_home()}\n"
            f"or disable the cache with UEDCLI_PKG_CACHE=off.") from e
    _maybe_auto_sweep()


# --------------------------------------------------------------------------- footprint GC
# Mirrors schema_cache.py's sweep exactly: reclaim orphaned v<older>/ dirs a CACHE_VERSION bump left
# unreachable, then LRU-evict current-version blobs by atime to a byte/count cap. Runs automatically
# (once per process, best-effort) after a write, and on demand via `uedcli cache gc`.


def _env_int(name: str, default: int | None) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        v = int(raw.strip())
    except ValueError:
        return default
    return v if v >= 0 else default


def _default_max_bytes() -> int | None:
    return _env_int("UEDCLI_PKG_CACHE_MAX_BYTES", PKG_CACHE_MAX_BYTES)


def _default_max_entries() -> int | None:
    return _env_int("UEDCLI_PKG_CACHE_MAX_ENTRIES", PKG_CACHE_MAX_ENTRIES)


def reclaim_old_version_dirs(*, keep_version: int | None = None) -> int:
    """Delete every `v<N>/` bucket under `cache/pkg/` whose N != the current (kept) version.
    Best-effort: a missing root or a dir that vanishes mid-race is skipped, never raised."""
    keep = CACHE_VERSION if keep_version is None else keep_version
    root = config.pkg_cache_root()
    try:
        with os.scandir(root) as it:
            children = list(it)
    except OSError:
        return 0

    removed = 0
    for child in children:
        try:
            if not child.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        m = _VERSION_DIR_RE.match(child.name)
        if m is None or int(m.group(1)) == keep:
            continue
        shutil.rmtree(child.path, ignore_errors=True)
        if not os.path.exists(child.path):
            removed += 1
    return removed


def evict_lru(*, max_bytes: int | None, max_entries: int | None = None) -> dict:
    """LRU-evict blobs from the current version dir until under the byte/count cap (either `None` =
    unbounded). Best-effort: unstatable/already-gone files are skipped, never raised."""
    curdir = config.pkg_cache_root() / f"v{CACHE_VERSION}"
    try:
        with os.scandir(curdir) as it:
            entries = list(it)
    except OSError:
        return {"evicted": 0, "freed_bytes": 0, "kept_bytes": 0, "kept_entries": 0}

    files: list[tuple[int, int, str]] = []          # (atime_ns, size, path)
    for e in entries:
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        if not _stat.S_ISREG(st.st_mode):
            continue
        files.append((st.st_atime_ns, st.st_size, e.path))

    total = sum(f[1] for f in files)
    count = len(files)

    def within() -> bool:
        return (max_bytes is None or total <= max_bytes) and \
               (max_entries is None or count <= max_entries)

    evicted = 0
    freed = 0
    if not within():
        files.sort(key=lambda f: f[0])              # oldest atime (LRU) first
        for _atime, size, path in files:
            if within():
                break
            try:
                os.unlink(path)
            except OSError:
                continue
            total -= size
            count -= 1
            evicted += 1
            freed += size
    return {"evicted": evicted, "freed_bytes": freed, "kept_bytes": total, "kept_entries": count}


def sweep(*, max_bytes: int | None = -1, max_entries: int | None = -1) -> dict:
    """The full footprint GC: reclaim orphaned `v<older>/` dirs, then LRU-evict current-version
    blobs to the cap. Caps default (sentinel `-1`) to the env-or-constant defaults. Never raises."""
    mb = _default_max_bytes() if max_bytes == -1 else max_bytes
    me = _default_max_entries() if max_entries == -1 else max_entries
    removed_dirs = reclaim_old_version_dirs()
    stats = evict_lru(max_bytes=mb, max_entries=me)
    return {"removed_version_dirs": removed_dirs, **stats}


def _maybe_auto_sweep() -> None:
    """Run `sweep()` at most once per process, best-effort — see schema_cache.py's version."""
    global _SWEPT
    if _SWEPT:
        return
    _SWEPT = True
    try:
        sweep()
    except Exception:                               # noqa: BLE001 — best-effort; never break a command
        pass


def clear() -> bool:
    """Delete `cache/pkg/` (backs `uedcli cache clear`). Returns True if a dir was removed, False
    if it was already absent (a no-op)."""
    root = config.pkg_cache_root()
    if root.is_dir():
        shutil.rmtree(root)
        return True
    return False
