"""Dependency symbol environment — resolve names a package's sources reference (superclasses,
property/type classes, native functions) against the already-compiled `.u` packages on the compile
search path. Reuses the byte-exact reader (`upackage`, `uprops`).

Rung-0/1 needs only: which package exports a given class, and that class's stored `ScriptText`
self-dependency CRC (imported deps carry the CRC read from their home package, per
`compile-model.md`). Deeper resolution (inherited members, property offsets, native indices) is added
as later rungs reach it.
"""
from __future__ import annotations

import glob
import os
import struct
from dataclasses import dataclass
from functools import cached_property

from ..upackage import Package, load_package, read_compact_index as _rci
from ..uprops.ufield import _skip_script


@dataclass(frozen=True, kw_only=True)
class ClassInfo:
    name: str                 # as spelled in its home package
    package: str              # home package stem (e.g. "Core", "Engine")
    self_crc: int             # its own ScriptText CRC (from its self-dependency)
    class_flags: int          # its ClassFlags (a subset propagates to subclasses)
    package_imports: tuple[str, ...]  # its PackageImports (own pkg + transitive deps + Core)
    probe_mask: int           # its default-state EProbe bits (subclasses OR in their own overrides)
    config_name: str          # its ClassConfigName — a subclass's bare `config` (no name) inherits it


def class_home_from_imports(pkg: Package, class_name: str) -> str | None:
    """The home package of `class_name`, found among `pkg`'s own IMPORT table (not its exports) — a
    `Core.Class`-typed import row named `class_name`, resolved to a package name via
    `Package.import_package_of`'s existing outer-chain walk. Fallback for a class that has NO
    exported script body anywhere on the search path: some engine classes are fully native with no
    `.uc` source at all, so no `.u` ever serializes a UClass export for them, yet they are still real,
    resolvable class references — live-probed (`dev/docs/spikes/2026-09-14-utserveradmin-class-ref-
    gaps/probe_netconnection_import_only.py`): UT99's
    `Engine.NetConnection` compiles fine as a cast target (`NetConnection(x) != None`) with only
    Core+Engine `EditPackages` loaded, even though no fetched UT99 `.u` exports it; the fresh golden's
    own import table names its home package `Engine`, matching this scan of `Engine.u`'s own imports
    exactly (`Engine.u` itself imports `NetConnection` from itself — for some OTHER class's property
    type — even though it never exports it)."""
    cf = class_name.casefold()
    for i, imp in enumerate(pkg.imports):
        cls_pkg_idx, cls_name_idx, _outer, obj_name_idx = imp
        if pkg.names[obj_name_idx].casefold() != cf:
            continue
        if 0 <= cls_name_idx < len(pkg.names) and pkg.names[cls_name_idx] == "Class":
            home = pkg.import_package_of(i)
            if home:
                return home
    return None


def _class_export_index(pkg: Package, class_name: str) -> int | None:
    cf = class_name.casefold()
    for i, e in enumerate(pkg.exports):
        # a UClass export has Class-ref 0 (the metaclass quirk); match by casefolded name
        if e["cls"] == 0 and pkg.names[e["nm"]].casefold() == cf:
            return i + 1
    return None


def _self_crc(pkg: Package, class_index1: int) -> int:
    """Walk a UClass body to its Dependencies and return the self-dependency's ScriptTextCRC (the
    first dep whose Class ref is this export)."""
    e = pkg.exports[class_index1 - 1]
    buf, pos = pkg.buf, e["soff"]
    for _ in range(5):                       # Super, Next, ScriptText, Children, FriendlyName
        _, pos = _rci(buf, pos)
    pos += 8                                 # Line + TextPos
    ssz = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    pos = _skip_script(pkg, pos, ssz)
    pos += 8 + 8 + 2 + 4 + 4 + 16            # UState fields + ClassFlags + ClassGuid
    depcnt, pos = _rci(buf, pos)
    self_ref = class_index1
    for _ in range(depcnt):
        cls, pos = _rci(buf, pos)
        _deep, crc = struct.unpack_from("<II", buf, pos); pos += 8
        if cls == self_ref:
            return crc
    raise ValueError(f"{pkg.name}.{pkg.names[e['nm']]}: no self-dependency CRC found")


def _probe_mask(pkg: Package, class_index1: int) -> int:
    """The default-state ProbeMask u64 in a UClass body (first of the UState fields)."""
    e = pkg.exports[class_index1 - 1]
    buf, pos = pkg.buf, e["soff"]
    for _ in range(5):                       # Super, Next, ScriptText, Children, FriendlyName
        _, pos = _rci(buf, pos)
    pos += 8                                 # Line + TextPos
    ssz = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    pos = _skip_script(pkg, pos, ssz)
    return struct.unpack_from("<Q", buf, pos)[0]


def _class_flags(pkg: Package, class_index1: int) -> int:
    """The ClassFlags u32 in a UClass body (right after the UState fields, before ClassGuid)."""
    e = pkg.exports[class_index1 - 1]
    buf, pos = pkg.buf, e["soff"]
    for _ in range(5):                       # Super, Next, ScriptText, Children, FriendlyName
        _, pos = _rci(buf, pos)
    pos += 8                                 # Line + TextPos
    ssz = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    pos = _skip_script(pkg, pos, ssz)
    pos += 8 + 8 + 2 + 4                      # ProbeMask, IgnoreMask, LabelTableOffset, StateFlags
    return struct.unpack_from("<I", buf, pos)[0]


def _package_imports(pkg: Package, class_index1: int) -> tuple[str, ...]:
    """The PackageImports name list in a UClass body (after Dependencies, before ClassWithin)."""
    e = pkg.exports[class_index1 - 1]
    buf, pos = pkg.buf, e["soff"]
    for _ in range(5):                       # Super, Next, ScriptText, Children, FriendlyName
        _, pos = _rci(buf, pos)
    pos += 8
    ssz = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    pos = _skip_script(pkg, pos, ssz)
    pos += 8 + 8 + 2 + 4 + 4 + 16            # UState fields + ClassFlags + ClassGuid
    depcnt, pos = _rci(buf, pos)
    for _ in range(depcnt):
        _, pos = _rci(buf, pos); pos += 8
    picnt, pos = _rci(buf, pos)
    out = []
    for _ in range(picnt):
        n, pos = _rci(buf, pos)
        out.append(pkg.names[n])
    return tuple(out)


def _config_name(pkg: Package, class_index1: int) -> str:
    """The ClassConfigName in a UClass body (after PackageImports, ClassWithin) — 'System' if this
    class never set an explicit one anywhere in its chain. Live-probed: UT99 `Engine.Spectator`/
    `Engine.MessagingSpectator` are both `'User'` (real UT99 stores spectator/messaging prefs in
    `User.ini`), `Engine.PlayerPawn` is `'System'` — see `compile._class_header`'s bare-`config`
    inheritance rule, `dev/docs/spikes/2026-09-14-utserveradmin-class-ref-gaps/
    probe_config_name_inheritance.py`."""
    e = pkg.exports[class_index1 - 1]
    buf, pos = pkg.buf, e["soff"]
    for _ in range(5):                       # Super, Next, ScriptText, Children, FriendlyName
        _, pos = _rci(buf, pos)
    pos += 8
    ssz = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    pos = _skip_script(pkg, pos, ssz)
    pos += 8 + 8 + 2 + 4 + 4 + 16            # UState fields + ClassFlags + ClassGuid
    depcnt, pos = _rci(buf, pos)
    for _ in range(depcnt):
        _, pos = _rci(buf, pos); pos += 8
    picnt, pos = _rci(buf, pos)
    for _ in range(picnt):
        _, pos = _rci(buf, pos)
    _within, pos = _rci(buf, pos)
    cfgname, _pos = _rci(buf, pos)
    return pkg.names[cfgname] if 0 < cfgname < len(pkg.names) else "System"


_SUBSTRATES = ("ued22", "ut99")


class InstallEnv:
    """Index of the compiled `.u` packages on a search path. Lazily loads a package the first time a
    class in it is needed. `substrate` names which real `UCC.exe` build the search path's packages
    came from ("ued22" or "ut99") — the two are different binaries with measured behavior differences
    (see `compile._auto_emit_defaults`); defaults to "ued22", the original/only substrate this
    compiler targeted."""

    def __init__(self, search_dirs: list[str], *, substrate: str = "ued22") -> None:
        if substrate not in _SUBSTRATES:
            raise ValueError(f"unknown substrate: {substrate!r} (must be one of {_SUBSTRATES})")
        self._search_dirs = search_dirs
        self.substrate = substrate
        self._pkg_cache: dict[str, Package] = {}

    @cached_property
    def _class_to_package(self) -> dict[str, str]:
        """casefolded class name -> home package stem. First package wins on a collision; the search
        path should be ordered so the intended home comes first."""
        index: dict[str, str] = {}
        for path in self._package_paths():
            stem = os.path.splitext(os.path.basename(path))[0]
            try:
                pkg = load_package(path)
            except Exception:
                continue
            for i, e in enumerate(pkg.exports):
                if e["cls"] == 0:
                    index.setdefault(pkg.names[e["nm"]].casefold(), stem)
        return index

    @cached_property
    def _import_only_class_to_package(self) -> dict[str, str]:
        """Fallback for a class with NO export anywhere on the search path but reachable as an
        IMPORT somewhere (`class_home_from_imports`) — only consulted when `_class_to_package`
        (export-based, authoritative) doesn't know the name. Never used for anything needing the
        class's own body (self CRC, members, flags) — only `import_only_class_package`, backing a
        cast-target import's home package."""
        exported = self._class_to_package               # authoritative; never overridden here
        index: dict[str, str] = {}
        for path in self._package_paths():
            try:
                pkg = load_package(path)
            except Exception:
                continue
            for imp in pkg.imports:
                nm_cf = pkg.names[imp[3]].casefold()
                if nm_cf in exported or nm_cf in index:
                    continue
                home = class_home_from_imports(pkg, pkg.names[imp[3]])
                if home:
                    index[nm_cf] = home
        return index

    def import_only_class_package(self, class_name: str) -> str | None:
        """The home package of a class known ONLY via import (never exported anywhere on the search
        path) — see `_import_only_class_to_package`. Used by `compile._add_import`'s cast-target
        fallback, never for member/function resolution (no body exists to read)."""
        return self._import_only_class_to_package.get(class_name.casefold())

    def _package_paths(self) -> list[str]:
        seen, out = set(), []
        for d in self._search_dirs:
            for path in sorted(glob.glob(os.path.join(d, "*.u"))):
                key = os.path.basename(path).casefold()
                if key not in seen:
                    seen.add(key)
                    out.append(path)
        return out

    def _load(self, stem: str) -> Package:
        if stem not in self._pkg_cache:
            for path in self._package_paths():
                if os.path.splitext(os.path.basename(path))[0].casefold() == stem.casefold():
                    self._pkg_cache[stem] = load_package(path)
                    break
            else:
                raise ValueError(f"package not found on search path: {stem}")
        return self._pkg_cache[stem]

    def resolve_class(self, class_name: str) -> ClassInfo | None:
        """The home package + self CRC of a class, or None if not on the search path."""
        stem = self._class_to_package.get(class_name.casefold())
        if stem is None:
            return None
        pkg = self._load(stem)
        ci = _class_export_index(pkg, class_name)
        if ci is None:
            return None
        # Package NAME casing is an FName from the engine pool, not the filename stem (`editor.u` ->
        # `Editor`); take the canonical spelling from the dumped global name pool.
        from .global_index import pool_case
        return ClassInfo(name=pkg.names[pkg.exports[ci - 1]["nm"]], package=pool_case(stem),
                         self_crc=_self_crc(pkg, ci), class_flags=_class_flags(pkg, ci),
                         package_imports=_package_imports(pkg, ci),
                         probe_mask=_probe_mask(pkg, ci), config_name=_config_name(pkg, ci))
