"""Offline audio index over the composed package search path — the enumeration + identity seam for
the `sound` and `music` catalog nouns.

Header-only: it reuses `upackage.load_package`, which parses a package's name/import/export TABLES
and decodes no object bodies, so enumeration never pays a per-sample cost. It enumerates the exports
of class `Sound` (kind `sound`) or class `Music` (kind `music`) across every file on the composed
path; a single unparseable package is skipped with a stderr note, never aborting the verb.

Identity (the shard key) follows the texture arm's collision rule: a ref keys to **`Package.Name`**
when that bare name is unique within its package, else the full dotted **`Package.Group.Name`** (an
export carries an Outer group — one package can hold the same bare name in two groups). `list` prints
the full addressable dotted ref (`object_path`); `show`/`classify` accept either the dotted ref or
the 2-part identity and `resolve` reduces both to the one stored identity.

Promoted from the spike enumerator `dev/docs/spikes/sound-corpus-remeasure/measure.py:_sound_exports`,
generalised over the class name.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from . import upackage

# The export CLASS enumerated for each noun.
_CLASS_OF_KIND = {"sound": "Sound", "music": "Music"}


class AudioRefError(ValueError):
    """A sound/music ref could not be resolved to one stored identity: unknown on the path, or a
    2-part ref that is ambiguous because the bare name collides across groups. Carries a message
    naming the value; the CLI turns it into a clean exit 2, never a traceback."""


@dataclass(frozen=True, kw_only=True)
class AudioEntry:
    kind: str            # "sound" | "music"
    ref: str             # the full dotted object_path (Package[.Group…].Name) — printed by `list`
    identity: str        # Package.Name (bare name unique) or the full dotted ref (collision)
    package: str         # the package stem
    group: str | None    # the middle dotted segment(s), or None for a root object
    path: str            # host package file path (read live for the .umx title)


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _group_of(dotted: str) -> str | None:
    parts = dotted.split(".")
    return ".".join(parts[1:-1]) if len(parts) >= 3 else None


def _enumerate_package(path: str, stem: str, class_name: str) -> list[tuple[str, str]]:
    """`(bare_name, dotted_path)` for every export of class `class_name` in one package. A package
    that will not parse is skipped with a stderr note (a foreign/quirky file on the path must not
    crash enumeration), matching `classindex`."""
    try:
        pkg = upackage.load_package(path, name=stem)
    except upackage.SchemaError as e:
        print(f"audio index: skipping unreadable package {stem!r}: {e}", file=sys.stderr)
        return []
    out: list[tuple[str, str]] = []
    for i in range(1, len(pkg.exports) + 1):
        if pkg.object_class_name(i) != class_name:
            continue
        dotted = pkg.object_path(i)
        if dotted is None:                       # corrupt ref chain — can't address it, skip
            continue
        out.append((dotted.split(".")[-1], dotted))
    return out


@dataclass(frozen=True)
class AudioIndex:
    kind: str
    entries: tuple[AudioEntry, ...]

    @classmethod
    def from_files(cls, files: list[tuple[str, str]], kind: str) -> "AudioIndex":
        """`files`: `(host_path, provenance)` as `config.composed_search_files` returns. Enumerates
        the `kind`-class exports, applies the collision rule per package, and returns the index."""
        class_name = _CLASS_OF_KIND[kind]
        entries: list[AudioEntry] = []
        for path, _prov in files:
            stem = _stem(path)
            found = _enumerate_package(path, stem, class_name)
            bare_counts: dict[str, int] = {}
            for name, _dotted in found:
                bare_counts[name.casefold()] = bare_counts.get(name.casefold(), 0) + 1
            for name, dotted in found:
                unique = bare_counts[name.casefold()] == 1
                identity = f"{stem}.{name}" if unique else dotted
                entries.append(AudioEntry(kind=kind, ref=dotted, identity=identity,
                                          package=stem, group=_group_of(dotted), path=path))
        return cls(kind=kind, entries=tuple(entries))

    # -- lookups ---------------------------------------------------------------

    def packages(self) -> set[str]:
        """The casefolded package stems that own at least one object of this kind."""
        return {e.package.casefold() for e in self.entries}

    def entry_of_identity(self, identity: str) -> AudioEntry | None:
        key = identity.casefold()
        return next((e for e in self.entries if e.identity.casefold() == key), None)

    def resolve(self, ref: str) -> str:
        """A supplied 2- or 3-part ref → the one stored identity. An exact dotted `object_path`
        match wins first; else the 2-part `Package.Name` form resolves when it names exactly one
        object. Raises `AudioRefError` naming the value for an unknown ref, or for a 2-part ref whose
        bare name collides across groups (ambiguous — the dotted ref is required)."""
        key = ref.casefold()
        by_ref = {e.ref.casefold(): e.identity for e in self.entries}
        if key in by_ref:
            return by_ref[key]
        two_part: dict[str, list[str]] = {}
        for e in self.entries:
            two_part.setdefault(f"{e.package}.{e.ref.split('.')[-1]}".casefold(), []).append(e.identity)
        candidates = two_part.get(key)
        if candidates is None:
            raise AudioRefError(f"{self.kind} not found: {ref}")
        if len(candidates) > 1:
            raise AudioRefError(
                f"ambiguous {self.kind} ref {ref}: the bare name appears in several groups "
                f"({', '.join(sorted(candidates))}); use the full dotted ref")
        return candidates[0]
