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


class InstallEnv:
    """Index of the compiled `.u` packages on a search path. Lazily loads a package the first time a
    class in it is needed."""

    def __init__(self, search_dirs: list[str]) -> None:
        self._search_dirs = search_dirs
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
                         package_imports=_package_imports(pkg, ci))
