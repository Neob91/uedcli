"""Persistent per-package decoded-schema cache — decode a `.u`'s v1 primitives once and reuse them
across cold `uedcli` runs (`dev/docs/architecture.md` "Package schema cache").

Every `uedcli` command is a fresh host-native process, so all schema decoding otherwise starts from
zero every invocation — and the dominant cost is `load_package`'s name/import/export TABLE parse
(38-211 ms per big package), NOT the property decode. This module persists each package's decoded
primitives to `~/.uedcli/cache/schema/v<N>/<key>.{disc,prop}`, so a warm hit skips `load_package`
entirely (never even touches the raw bytes `buf`).

The one load-bearing idea: **cache PER-PACKAGE primitives, recompute cross-package compositions
in-process** (ancestry, the class tree, the resolved property union are cheap dict-merges once the
per-package decode is done). v1 caches only the discovery-path primitives — no tables, no defaults,
no struct layouts (that is v2). See the spec §4.

**Two blobs, so `class list` never pays for what only `class show` needs.** The bundle splits into:
  - a DISCOVERY blob (`.disc`): class list, casefold→export-index map, per-class super-ref FQCN
    strings, abstract flags — everything `ClassIndex` (the `class list` tree) reads;
  - a PROPS blob (`.prop`): the own-property schema (with LOCAL enum value-names) that
    `resolve_class_properties`' schema union reads.
`class list` decodes and caches only discovery; the own-property decode of EVERY class (measured
~8 s across the whole DX path, and unused by `class list`) is deferred to `need_props=True` callers.
Without the split, a `class list` cold-miss would eagerly decode all own-props and run ~4× slower
than the pre-cache path — the split keeps the cold miss cheap and the warm hit at ~0.4 s.

Key = a `(SCHEMA_CACHE_VERSION, realpath, size, st_mtime_ns)` **stat tuple**, NOT a content hash:
for ship-once game packages an `os.stat` (~5 µs) is a safe change detector, while re-hashing the
bytes every run would cost about as much as the parse it saves (§4.3). The narrow staleness caveat
(a same-size, same-mtime content spoof) is accepted; `UEDCLI_SCHEMA_CACHE=off` and `cache clear`
cover the paranoid case.

Storage mirrors `stub_cache.py`: immutable per-key files, `_atomic_write` (tmp + `os.replace`), a
corrupt/version-mismatched entry is a MISS (re-decode), never an error. A write that FAILS, though
(an unwritable cache dir — e.g. a root-owned `~/.uedcli/cache`), is SURFACED as `CacheWriteError`,
never swallowed: a silently-dead cache re-decodes every package every run with no hint why (the
`class list` slowdown, 2026-07-18). Serialization is `marshal`
(the §9 spike: JSON 16.69 ms vs marshal 5.71 ms on DeusEx.u; marshal has no pickle RCE, and a format
drift degrades to a miss). `SCHEMA_CACHE_VERSION` is folded into BOTH the hashed key AND the `v<N>/`
path, and hand-bumped on ANY change to a bundle shape, a feeding decoder, the `Prop` layout, or the
serialization (§4.5). A committed frozen-golden blob guards the hand step (test_schema_cache).

**Footprint GC (automatic, best-effort).** Beyond the manual `uedcli cache clear` (nuke all), the
cache self-bounds: after a successful blob write each process runs, at most once, a `sweep()` that
(1) reclaims orphaned `v<older>/` dirs a `SCHEMA_CACHE_VERSION` bump left unreachable, and
(2) LRU-evicts current-version blobs by atime until under a byte/count cap (`SCHEMA_CACHE_MAX_BYTES`,
env-overridable). Immutability means eviction has NO correctness pressure — an evicted blob is just a
future re-decode — so the sweep never touches live-entry correctness and swallows every error. The
same sweep is exposed on demand as **`uedcli cache gc [--max-bytes N] [--max-entries N]`** (the flags
override the env-or-constant caps for that one run).
"""
from __future__ import annotations

import hashlib
import marshal
import os
import re
import stat as _stat
from dataclasses import dataclass, replace
from pathlib import Path

from . import config
from .stub_cache import _atomic_write
from . import uprops
from .uprops import Package, Prop, SchemaError

# Bump on ANY change to: a bundle shape/fields (disc OR prop), a feeding decoder in uprops/upackage,
# the Prop layout, or the serialization format. A bump makes every old entry unreachable (new key +
# new v<N>/ dir). The committed frozen-golden test trips red to force this human step (spec §4.5/§11).
SCHEMA_CACHE_VERSION = 2

# Footprint cap for the persistent schema cache (spec follow-up: automatic GC for cache/schema/).
# Entries are IMMUTABLE / content-keyed, so eviction carries NO correctness pressure — evicting a
# blob just turns a future load into a re-decode; this is pure disk-footprint control. The cap
# bounds the CURRENT version's total blob bytes (v1 discovery bundles are tens of KB each; v2's
# larger defaults bundles are what make a cap worth having). Overridable PER-PROCESS via the env
# (mainly for tests): UEDCLI_SCHEMA_CACHE_MAX_BYTES (size cap) and UEDCLI_SCHEMA_CACHE_MAX_ENTRIES
# (blob-count cap; default off — size alone bounds footprint).
SCHEMA_CACHE_MAX_BYTES = 256 * 1024 * 1024
SCHEMA_CACHE_MAX_ENTRIES: int | None = None

# A cache-dir subdir named exactly `v<digits>` is a decoder-version bucket; anything else under the
# root is left alone by the version-dir reclaim.
_VERSION_DIR_RE = re.compile(r"^v(\d+)$")

# The automatic best-effort footprint sweep runs at most ONCE per process (a full-dir scan is not
# worth repeating on every blob write within the same command). Reset by tests that exercise the
# auto-trigger across cases (see conftest / the cache_on fixture). A plain module global: a benign
# data race between threads only risks a redundant (idempotent, best-effort) sweep.
_SWEPT = False

# The Prop fields, in the fixed order used by the on-disk tuple form. A change here is a bundle-shape
# change ⇒ bump SCHEMA_CACHE_VERSION (and refresh the golden).
#
# `array_inner` is a nested `Prop | None` (an ArrayProperty's ELEMENT property), so it cannot ride
# `getattr` straight into a marshal tuple like the flat fields — `_prop_row`/`_prop_from_row` encode
# it as a nested row (or None). It MUST be persisted rather than dropped: a warm cache that silently
# handed back `array_inner=None` would make `mapimport`'s dynamic-array decode fail (or, worse,
# quietly skip an array) only on machines whose cache happened to be warm.
_PROP_FIELDS = ("name", "kind", "array_dim", "property_flags", "type_ref", "type_name", "owner",
                "enum_value_names", "category", "array_inner")


def _prop_row(p: Prop) -> tuple:
    """One `Prop` → its on-disk tuple, with the nested `array_inner` encoded recursively."""
    return tuple(_prop_row(v) if isinstance(v := getattr(p, f), Prop) else v for f in _PROP_FIELDS)


def _prop_from_row(row) -> Prop:
    """The inverse of `_prop_row`."""
    kw = dict(zip(_PROP_FIELDS, row))
    if kw.get("array_inner") is not None:
        kw["array_inner"] = _prop_from_row(kw["array_inner"])
    return Prop(**kw)


def _rebind_owner(p: Prop, owner_fqcn: str) -> Prop:
    """`p` with its `owner` (and its `array_inner`'s, which must agree — the element property is
    declared by the same class) rebound to `owner_fqcn`."""
    inner = None if p.array_inner is None else replace(p.array_inner, owner=owner_fqcn)
    return replace(p, owner=owner_fqcn, array_inner=inner)

# In-process memos (realpath -> decoded parts), so repeated loads within one command are free and the
# disk is touched at most once per package per process. Split by blob so a discovery-only load never
# forces the (expensive) own-prop decode. Exposed for tests that exercise the ON-DISK hit path (clear
# to force a disk read). Die with the process.
_DISC_MEMO: dict[str, "_Disc"] = {}
_PROP_MEMO: dict[str, dict] = {}


class CacheWriteError(Exception):
    """A schema-cache blob could not be persisted (the cache dir is unwritable — classically a
    root-owned `~/.uedcli/cache` left behind by a container run). Raised instead of silently swallowed
    so a dead cache can't invisibly force every command to re-decode from scratch; dispatch renders the
    (actionable) message at exit 2."""


def _enabled() -> bool:
    """The cache is ON unless `UEDCLI_SCHEMA_CACHE=off` (any other value / unset = on) — read at call
    time so tests and CI can toggle it per-process (spec §7)."""
    return os.environ.get("UEDCLI_SCHEMA_CACHE", "").strip().lower() != "off"


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


@dataclass(frozen=True)
class _Disc:
    """The discovery-blob payload for one package."""
    package_name: str
    class_list: tuple[str, ...]
    cmap: dict[str, int]
    super_refs: dict[str, str | None]
    abstract: dict[str, bool | None]


@dataclass(frozen=True)
class PackageSchema:
    """The v1 primitive bundle for ONE package — a pure function of that package's bytes (spec §4.1a).
    `own_props` is `None` when the schema was loaded discovery-only (`need_props=False`), so
    `class list` never triggers the own-property decode. All name keys are casefolded (FName)."""

    package_name: str                              # pkg.name (the stem spelling used at decode)
    class_list: tuple[str, ...]                    # iter_classes order (deterministic, may repeat)
    cmap: dict[str, int]                           # casefold(class) -> 1-based export index
    super_refs: dict[str, str | None]              # casefold(class) -> direct-super FQCN, or None (root)
    abstract: dict[str, bool | None]               # casefold(class) -> abstract flag (None=undeterminable)
    own_props: dict[str, tuple[Prop, ...] | None] | None  # casefold(class) -> own Props; None=not loaded

    # -- typed reads ----------------------------------------------------------
    def super_ref_for(self, class_name: str) -> str | None:
        """The class's direct-super FQCN, or None if it is a genuine root. RAISES `SchemaError` if the
        super ref failed to decode (a malformed-but-loadable package) — preserving the no-fallback
        contract of the live `_super_fqcn` it replaces (spec §6), so the unseeded `resolve_class_
        properties` path errors on a corrupt chain instead of silently truncating the union. The
        corrupt case is the `""` sentinel (a real FQCN is never empty); genuine roots stay `None`, so
        `children_map`'s `if sup:` still skips both (empty and None are falsy)."""
        v = self.super_refs.get(class_name.casefold())
        if v == "":
            raise SchemaError(
                f"cannot resolve the super of {self.package_name}.{class_name} "
                "(corrupt/out-of-range super ref in a malformed package)")
        return v

    def own_props_for(self, class_name: str, *, owner_fqcn: str) -> list[Prop]:
        """The class's own (not inherited) Props, with `owner` rebound to `owner_fqcn` — byte-for-byte
        what `uprops.own_class_properties(pkg, class_name, owner_fqcn=owner_fqcn)` produced at decode
        time. Requires the schema to have been loaded `need_props=True`. Raises `SchemaError` for an
        unknown class or a class whose body failed to decode (both of which the live path also raises)."""
        if self.own_props is None:
            raise SchemaError(f"own props not loaded for {self.package_name} "
                              "(load_package_schema needs need_props=True)")
        cf = class_name.casefold()
        if cf not in self.own_props:
            raise SchemaError(f"class not found in {self.package_name}: {class_name}")
        val = self.own_props[cf]
        if val is None:
            raise SchemaError(f"cannot decode properties of {owner_fqcn} (corrupt package body)")
        return [_rebind_owner(p, owner_fqcn) for p in val]

    # -- serialization (marshal; see module docstring / §9 spike) -------------
    def golden_bytes(self) -> bytes:
        """The FULL bundle (discovery + props) serialized — the artifact the frozen-golden version
        guard freezes, so a change to EITHER decoder or serialization trips the test (§11)."""
        return _disc_dumps(_Disc(self.package_name, self.class_list, self.cmap,
                                 self.super_refs, self.abstract)) + b"\x1e" + _props_dumps(self.own_props)


def _disc_dumps(d: _Disc) -> bytes:
    return marshal.dumps({"v": SCHEMA_CACHE_VERSION, "package_name": d.package_name,
                          "class_list": list(d.class_list), "cmap": d.cmap,
                          "super_refs": d.super_refs, "abstract": d.abstract})


def _disc_loads(data: bytes) -> "_Disc | None":
    """Deserialize a discovery blob, or None if corrupt / wrong version (⇒ miss). Broad except:
    `marshal` can raise a variety of types on malformed input."""
    try:
        d = marshal.loads(data)
        if not isinstance(d, dict) or d.get("v") != SCHEMA_CACHE_VERSION:
            return None
        return _Disc(d["package_name"], tuple(d["class_list"]), d["cmap"], d["super_refs"], d["abstract"])
    except Exception:
        return None


def _props_dumps(own_props: dict) -> bytes:
    own = {cf: (None if props is None else [_prop_row(p) for p in props])
           for cf, props in own_props.items()}
    return marshal.dumps({"v": SCHEMA_CACHE_VERSION, "own_props": own})


def _props_loads(data: bytes) -> "dict | None":
    try:
        d = marshal.loads(data)
        if not isinstance(d, dict) or d.get("v") != SCHEMA_CACHE_VERSION:
            return None
        return {cf: (None if rows is None else tuple(_prop_from_row(r) for r in rows))
                for cf, rows in d["own_props"].items()}
    except Exception:
        return None


def _decode_discovery(pkg: Package) -> _Disc:
    """The discovery primitives (class list, cmap, super refs, abstract) from a loaded Package — the
    cheap miss-path decode `class list` needs. Per-class super decode is guarded so one corrupt class
    can't drop the whole package's class list; a corrupt super stores the `""` sentinel (see
    `super_ref_for`). `iter_classes`/`class_index_map` are NOT guarded — if they fail the package is
    genuinely unparseable, which the caller (ClassIndex._schema) turns into skip-with-note, as today."""
    classes = uprops.iter_classes(pkg)
    cmap = uprops.class_index_map(pkg)
    super_refs: dict[str, str | None] = {}
    abstract: dict[str, bool | None] = {}
    for c in classes:
        cf = c.casefold()
        if cf in super_refs:                        # duplicate class name: keep first (cmap semantics)
            continue
        ci = cmap.get(cf)
        try:
            super_refs[cf] = uprops.super_fqcn_by_index(pkg, ci) if ci is not None else None
        except SchemaError:
            super_refs[cf] = ""                     # sentinel: super_ref_for re-raises, children_map skips
        # Pass the already-known export index so the abstract decode skips a per-class O(n) name→index
        # scan — otherwise decoding every class's abstract flag is O(n²) (the `class list` hot path).
        abstract[cf] = uprops.class_is_abstract(pkg, c, ci=ci)
    return _Disc(pkg.name, tuple(classes), cmap, super_refs, abstract)


def _decode_props(pkg: Package) -> dict[str, tuple[Prop, ...] | None]:
    """The own-property schema per class — the expensive miss-path decode only `need_props=True`
    callers pay. A per-class own-prop decode failure stores the `None` sentinel (own_props_for
    re-raises SchemaError), so one corrupt class doesn't drop the package's whole prop bundle."""
    own_props: dict[str, tuple[Prop, ...] | None] = {}
    for c in uprops.iter_classes(pkg):
        cf = c.casefold()
        if cf in own_props:                         # duplicate class name: keep first
            continue
        try:
            own_props[cf] = tuple(uprops.own_class_properties(pkg, c, owner_fqcn=f"{pkg.name}.{c}"))
        except SchemaError:
            own_props[cf] = None
    return own_props


def cache_key(realpath: str) -> str:
    """The on-disk entry stem: a short sha1 of the ~100-byte `(SCHEMA_CACHE_VERSION, realpath, size,
    st_mtime_ns)` key STRING — NOT a hash of the multi-MB file bytes (spec §4.3). `os.stat` (~5 µs)
    is the change detector; raises OSError if the file is gone (the caller falls through to a clean
    load_package error)."""
    st = os.stat(realpath)
    key = f"{SCHEMA_CACHE_VERSION}\0{realpath}\0{st.st_size}\0{st.st_mtime_ns}"
    return hashlib.sha1(key.encode("utf-8", "surrogatepass")).hexdigest()


def _blob_path(key: str, ext: str) -> str:
    return os.path.join(config.schema_cache_root(), f"v{SCHEMA_CACHE_VERSION}", f"{key}.{ext}")


def _read_blob(path: str, loader):
    try:
        with open(path, "rb") as f:
            return loader(f.read())
    except OSError:
        return None


def load_package_schema(path: str, *, name: str | None = None,
                        need_props: bool = False) -> PackageSchema:
    """The cache boundary (spec §4.6): the v1 bundle for the `.u` at `path`, WITHOUT a `load_package`
    on a warm hit. `need_props=False` (the default — `class list`) loads only the cheap DISCOVERY
    blob; `need_props=True` (`resolve_class_properties`) also loads/decodes the own-property blob.
    `name` sets `pkg.name` on a miss-decode (defaults to the file stem, what the composed search path
    uses); it only matters when THIS process writes the entry (the accepted casefolded writer-spelling
    caveat, §4.3). Misses/corrupt/version-mismatched entries re-decode; a genuinely unparseable
    package still raises `SchemaError` (no fallback)."""
    realpath = os.path.realpath(path)
    load_name = name if name is not None else _stem(realpath)

    if not _enabled():                              # escape hatch: never read, never write
        pkg = uprops.load_package(realpath, name=load_name)
        disc = _decode_discovery(pkg)
        own = _decode_props(pkg) if need_props else None
        return _assemble(disc, own)

    try:
        key = cache_key(realpath)
    except OSError:                                 # missing/unstatable file → clean load_package error
        pkg = uprops.load_package(realpath, name=load_name)
        disc = _decode_discovery(pkg)
        own = _decode_props(pkg) if need_props else None
        return _assemble(disc, own)

    pkg: Package | None = None                      # loaded at most ONCE, reused across both blobs

    disc = _DISC_MEMO.get(realpath)
    if disc is None:
        disc = _read_blob(_blob_path(key, "disc"), _disc_loads)
        if disc is None:                            # miss / corrupt / wrong version → decode + write
            pkg = uprops.load_package(realpath, name=load_name)
            disc = _decode_discovery(pkg)
            _write_blob(_blob_path(key, "disc"), _disc_dumps(disc))
        _DISC_MEMO[realpath] = disc

    own = None
    if need_props:
        own = _PROP_MEMO.get(realpath)
        if own is None:
            own = _read_blob(_blob_path(key, "prop"), _props_loads)
            if own is None:                         # miss → decode (reusing a package we already loaded)
                if pkg is None:
                    pkg = uprops.load_package(realpath, name=load_name)
                own = _decode_props(pkg)
                _write_blob(_blob_path(key, "prop"), _props_dumps(own))
            _PROP_MEMO[realpath] = own

    return _assemble(disc, own)


def _assemble(disc: _Disc, own_props) -> PackageSchema:
    return PackageSchema(package_name=disc.package_name, class_list=disc.class_list, cmap=disc.cmap,
                         super_refs=disc.super_refs, abstract=disc.abstract, own_props=own_props)


def _write_blob(path: str, data: bytes) -> None:
    """Persist a cache blob, SURFACING any write failure — never silently swallowed. A cache that
    can't be written (classically a root-owned `~/.uedcli/cache` left by a container run) otherwise
    dies invisibly and every command re-decodes from scratch, with no hint why (the `class list`
    slowdown, 2026-07-18). We raise a clean, actionable `CacheWriteError` instead; dispatch renders it
    at exit 2. The escape hatch for a genuinely read-only cache location is `UEDCLI_SCHEMA_CACHE=off`
    (named in the message)."""
    try:
        _atomic_write(Path(path), data)
    except OSError as e:
        raise CacheWriteError(
            f"cannot write the schema cache under {config.user_cache_home()}: {e}\n"
            f"The persistent class-schema cache is unwritable, so every command must re-decode all "
            f"packages (slow). Fix the directory's ownership/permissions, e.g.\n"
            f"    sudo chown -R $(id -u):$(id -g) {config.user_cache_home()}\n"
            f"or disable the cache with UEDCLI_SCHEMA_CACHE=off.") from e
    _maybe_auto_sweep()


# --------------------------------------------------------------------------- footprint GC
# The manual `uedcli cache clear` nukes everything; this GC is the best-effort footprint control that
# keeps a long-lived cache bounded WITHOUT clearing live entries. It has two independent
# parts, both safe because entries are immutable / content-keyed (a wrongly-evicted blob is merely a
# future re-decode, never a wrong answer):
#   1. reclaim ORPHANED version dirs — a `SCHEMA_CACHE_VERSION` bump makes every `v<older>/` bucket
#      permanently unreachable (new key + new `v<N>/` path); delete those whole dirs.
#   2. LRU-evict CURRENT-version blobs by atime until under the byte / count cap — oldest-accessed
#      first, so the just-written (newest-atime) live blobs are the LAST candidates and survive.
# It runs two ways, over the same `sweep()`: automatically (once per process, best-effort) after a
# blob write, and on demand via `uedcli cache gc [--max-bytes N] [--max-entries N]`, whose flags
# override the env-or-constant caps for that run (`dispatch._dispatch_cache`).


def _env_int(name: str, default: int | None) -> int | None:
    """A non-negative int from env var `name`, else `default`. A missing/blank/garbage/negative
    value falls back to `default` (best-effort config — a bad override must never raise)."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        v = int(raw.strip())
    except ValueError:
        return default
    return v if v >= 0 else default


def _default_max_bytes() -> int | None:
    return _env_int("UEDCLI_SCHEMA_CACHE_MAX_BYTES", SCHEMA_CACHE_MAX_BYTES)


def _default_max_entries() -> int | None:
    return _env_int("UEDCLI_SCHEMA_CACHE_MAX_ENTRIES", SCHEMA_CACHE_MAX_ENTRIES)


def reclaim_old_version_dirs(*, keep_version: int | None = None) -> int:
    """Delete every `v<N>/` bucket under `cache/schema/` whose N != the current (kept) version — the
    orphans a `SCHEMA_CACHE_VERSION` bump leaves permanently unreachable. Returns the count of dirs
    removed. Best-effort: a missing root, a non-version-named sibling, or a dir that vanishes / can't
    be removed mid-race is skipped, never raised."""
    import shutil

    keep = SCHEMA_CACHE_VERSION if keep_version is None else keep_version
    root = config.schema_cache_root()
    try:
        with os.scandir(root) as it:                 # materialize up front: we delete during the loop
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
    """LRU-evict blobs from the CURRENT version dir (`v<SCHEMA_CACHE_VERSION>/`) until the total blob
    bytes are <= `max_bytes` AND the blob count is <= `max_entries` (either cap `None` = unbounded).
    Eviction order is ascending atime — least-recently-used first — so a blob this process just wrote
    (newest atime) is evicted only if the cache is grossly over cap. File-level (not per-key): a lone
    surviving `.disc`/`.prop` is fine (the other half re-decodes on next load). Returns a stats dict.
    Best-effort: unstatable / already-gone files are skipped, never raised."""
    curdir = config.schema_cache_root() / f"v{SCHEMA_CACHE_VERSION}"
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
            except OSError:                         # already gone / racing writer → skip
                continue
            total -= size
            count -= 1
            evicted += 1
            freed += size
    return {"evicted": evicted, "freed_bytes": freed, "kept_bytes": total, "kept_entries": count}


def sweep(*, max_bytes: int | None = -1, max_entries: int | None = -1) -> dict:
    """The full footprint GC: reclaim orphaned `v<older>/` dirs, then LRU-evict current-version blobs
    to the cap. Caps default (sentinel `-1`) to the env-or-constant defaults; pass an explicit value
    (incl. `None` for unbounded) to override. Never raises — a footprint GC must never break a
    command; the on-write auto-sweep additionally swallows any unexpected error."""
    mb = _default_max_bytes() if max_bytes == -1 else max_bytes
    me = _default_max_entries() if max_entries == -1 else max_entries
    removed_dirs = reclaim_old_version_dirs()
    stats = evict_lru(max_bytes=mb, max_entries=me)
    return {"removed_version_dirs": removed_dirs, **stats}


def _maybe_auto_sweep() -> None:
    """Run `sweep()` at most ONCE per process, best-effort. Called after a successful blob write, so a
    growing cache is bounded without any explicit `cache gc` invocation. The gate flag flips BEFORE
    the sweep (so a raise can't cause a retry storm) and every error is swallowed — GC must never
    break the command that happened to trigger it."""
    global _SWEPT
    if _SWEPT:
        return
    _SWEPT = True
    try:
        sweep()
    except Exception:                               # noqa: BLE001 — best-effort; never break a command
        pass


def clear() -> bool:
    """Delete `cache/schema/` (backs `uedcli cache clear`). Returns True if a dir was removed, False
    if it was already absent (a no-op). Also clears the in-process memos."""
    import shutil

    _DISC_MEMO.clear()
    _PROP_MEMO.clear()
    root = config.schema_cache_root()
    if root.is_dir():
        shutil.rmtree(root)
        return True
    return False
