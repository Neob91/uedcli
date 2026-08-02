"""Offline class index over the composed package search path — the single structure that powers
`class list`/`class show` discovery, bare→FQCN qualification on ingest, and class-existence
validation (spec in board item `offline-class-discovery-qualify-and-validate`; rationale/MIGRATION.md
2026-07-17 19:37 UTC).

Header-only: it reuses `uprops.load_package`, which parses a `.u` package's name/import/export
TABLES and decodes NO property bodies — so enumeration, existence, and qualification never pay the
per-property decode cost (only `class show`'s `resolve_class_properties` and abstract detection touch
bodies). Only `.u` files carry classes, so the index scans just those on the composed path.

The index is built once per CLI invocation (each invocation is a fresh process) and caches every
package it loads. A single unparseable `.u` is SKIPPED with a stderr note rather than aborting the
whole verb (a foreign/quirky package on the path must not crash discovery/validation).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from . import config, schema_cache, uprops

ENGINE_ACTOR = "Engine.Actor"
CORE_OBJECT = "Core.Object"      # the ultimate UE1 root — the `--all` class-tree root


class ClassRefError(ValueError):
    """A class reference could not be resolved/validated at author time (unknown class, unknown
    `--subclass-of`/package). Dispatch converts it to a clean exit-2 message, never a traceback."""


@dataclass
class ClassIndex:
    """Query layer over the composed `.u` set. Construct via `from_project` (production) or the
    `__init__` with a `{stem: path}` map (tests). All name lookups are case-insensitive (FName)."""

    _paths: dict[str, str]                    # casefold(stem) -> .u path (project shadows base)
    _stems: dict[str, str]                    # casefold(stem) -> canonical stem spelling
    _schemas: dict[str, "schema_cache.PackageSchema | None"] = field(default_factory=dict)
    _bare: dict[str, set[str]] | None = None
    _all: list[str] | None = None
    _ancestry: dict[str, list[str]] = field(default_factory=dict)   # casefold(fqcn) -> chain
    _abstract: dict[str, bool | None] = field(default_factory=dict)  # casefold(fqcn) -> abstract
    _cmaps: dict[str, dict[str, int]] = field(default_factory=dict)  # casefold(stem) -> {name:idx1}
    _children: dict[str, list[str]] | None = None   # casefold(parent fqcn) -> [child fqcn], name-sorted

    # -- construction ----------------------------------------------------------
    @classmethod
    def from_files(cls, u_files: list[tuple[str, str]]) -> "ClassIndex":
        """`u_files`: `(stem, path)` for each `.u` on the composed path, project-before-base so a
        project overlay shadows a same-named base package (keep-first)."""
        paths: dict[str, str] = {}
        stems: dict[str, str] = {}
        for stem, path in u_files:
            k = stem.casefold()
            paths.setdefault(k, path)
            stems.setdefault(k, stem)
        return cls(_paths=paths, _stems=stems)

    @classmethod
    def from_project(cls, project, user_config) -> "ClassIndex":
        """Build from the composed config search path (`.u` files only). An empty path (no project /
        no games config) yields an index that resolves nothing — the caller turns a miss into a clean
        'no package search path' error before validating."""
        u_files: list[tuple[str, str]] = []
        for host_path, _prov in config.composed_search_files(project, user_config):
            if host_path.lower().endswith(".u"):
                stem = os.path.splitext(os.path.basename(host_path))[0]
                u_files.append((stem, host_path))
        return cls.from_files(u_files)

    @property
    def empty(self) -> bool:
        return not self._paths

    def resolver(self):
        """A `(package_name) -> path | None` resolver over the index's `.u` files, for
        `uprops.resolve_class_properties`' cross-package Super walk."""
        return lambda pkg_name: self._paths.get(pkg_name.casefold())

    def package_paths(self) -> list[str]:
        """Every indexed `.u` file path — the composed package set the class arm operates over.
        `class preview` builds a `utexture.TextureResolver` over these to decode a mesh's skins from
        the SAME path the mesh itself decoded from (DX deco skins live in the deco `.u`)."""
        return list(self._paths.values())

    def packages(self) -> list[tuple[str, str]]:
        """`(canonical stem, .u path)` for every indexed package — what `class prewarm` iterates to
        warm each package's persistent schema cache."""
        return [(self._stems[k], p) for k, p in self._paths.items()]

    def package_stem(self, stem: str) -> str | None:
        """The canonical spelling of `stem` if it is on the path (case-insensitive), else None — the
        `--package` validator for `class prewarm`/`list`."""
        return self._stems.get(stem.casefold())

    # -- package loading -------------------------------------------------------
    # There is NO live full-`Package` load here any more. `_package` (a memoized `uprops.load_package`)
    # existed only for `class show`'s own-props degrade fallback; that fallback was deleted 2026-07-25
    # (an unreadable ancestor is now a hard exit 2), leaving it with zero callers — so it went with it,
    # per the no-back-compat-cruft rule. EVERY class fact now comes off `_schema` (the persistent
    # per-package schema cache).
    def _schema(self, stem: str) -> "schema_cache.PackageSchema | None":
        """The package's persistent decoded-schema bundle (class list / cmap / super refs / abstract
        flags / own-prop schema), sourced through `schema_cache.load_package_schema` so a warm cold
        run skips `load_package` entirely (spec 2026-07-18-package-schema-cache §4.6). Mirrors
        `_package`'s skip-with-note: an unparseable package is a stderr note + None, never an abort.
        Cached per invocation like every other per-package input here."""
        k = stem.casefold()
        if k not in self._schemas:
            path = self._paths.get(k)
            if path is None:
                self._schemas[k] = None
            else:
                try:
                    self._schemas[k] = schema_cache.load_package_schema(
                        path, name=self._stems.get(k, stem))
                except uprops.SchemaError as e:
                    print(f"class index: skipping unparseable package "
                          f"{self._stems.get(k, stem)!r}: {e}", file=sys.stderr)
                    self._schemas[k] = None
        return self._schemas[k]

    def _cmap(self, stem: str) -> dict[str, int]:
        """The package's `casefold(class name) -> 1-based export index` map (cached); {} if the
        package isn't resolvable/parseable. Sourced from the persistent schema cache (`_schema`)."""
        k = stem.casefold()
        if k not in self._cmaps:
            sch = self._schema(stem)
            self._cmaps[k] = {} if sch is None else sch.cmap
        return self._cmaps[k]

    # -- enumeration -----------------------------------------------------------
    def _all_fqcns(self) -> list[str]:
        if self._all is None:
            out: list[str] = []
            for k in self._paths:
                sch = self._schema(k)
                if sch is None:
                    continue
                out.extend(f"{sch.package_name}.{c}" for c in sch.class_list)
            self._all = out
        return self._all

    def all_classes(self) -> list[str]:
        """Every class (FQCN) defined on the composed path, in package/table order. The
        denominator `class classify status` reports classified progress against."""
        return list(self._all_fqcns())

    def bare_to_fqcn(self) -> dict[str, set[str]]:
        """`casefold(bare class name) -> {Package.Class}` over the whole path. A 2+ set is a
        cross-package name collision. Built once (loads every `.u`) — the acknowledged per-ingest tax
        for bare-name qualification."""
        if self._bare is None:
            m: dict[str, set[str]] = {}
            for fqcn in self._all_fqcns():
                bare = fqcn.split(".", 1)[1]
                m.setdefault(bare.casefold(), set()).add(fqcn)
            self._bare = m
        return self._bare

    # -- class facts -----------------------------------------------------------
    def class_exists(self, fqcn: str) -> bool:
        """True if `Package.Class` names a real class in that package on the path."""
        if "." not in fqcn:
            return False
        pkg_name, cname = fqcn.split(".", 1)
        return cname.casefold() in self._cmap(pkg_name)

    def ancestry(self, fqcn: str, _seen: frozenset = frozenset()) -> list[str]:
        """`[fqcn, super, super.super, …]` up to the root, TRUNCATING at a missing/unparseable
        ancestor package (skip-with-note applies at load) — never raises for an absent ancestor.
        Memoized, and reuses a super's already-computed chain (the shared upper chains — every Actor
        subclass shares `…→Engine.Actor→Core.Object` — are walked once). `_seen` guards against a
        pathological super-chain CYCLE in a corrupt `.u` (a real hierarchy never cycles) so the
        recursion can't run away — a cycle just truncates the chain."""
        key = fqcn.casefold()
        cached = self._ancestry.get(key)
        if cached is not None:
            return cached
        if "." not in fqcn:
            self._ancestry[key] = [fqcn]
            return self._ancestry[key]
        pkg_name, cname = fqcn.split(".", 1)
        sch = self._schema(pkg_name)
        sup: str | None = None
        if sch is not None:
            try:
                sup = sch.super_ref_for(cname)          # cached super ref (disc blob); no live decode
            except uprops.SchemaError as e:
                # A genuine root returns None silently; the corrupt `""` sentinel (that super_ref_for
                # re-raises) truncating the chain is corruption (or a torn concurrent read) — surface
                # it, so a silently-dropped super chain leaves a diagnosable trace instead of a bare
                # missing line (2026-07-18). super_ref_for's `.get` miss (class absent) returns None
                # too, matching the old `ci is None` no-super case — chain stops at [fqcn].
                print(f"class index: super chain of {fqcn} truncated — {e}", file=sys.stderr)
                sup = None
        if sup is None or sup.casefold() in (_seen | {key}):
            chain = [fqcn]                               # root, self-loop, or a cycle back to an ancestor
        else:
            chain = [fqcn] + self.ancestry(sup, _seen | {key})
        # Cache every level (the shared upper chains are reused across classes). `_seen` only STOPS a
        # runaway recursion; a real class hierarchy never cycles, so in the normal (acyclic) case
        # `_seen` never fires and this cache is always the complete chain. A corrupt cyclic `.u` would
        # cache a truncated chain — bounded and non-crashing, acceptable for corrupt input.
        self._ancestry[key] = chain
        return chain

    def descends_from(self, fqcn: str, base_fqcn: str) -> bool:
        """True if `fqcn` IS `base_fqcn` or has it as an ancestor (case-insensitive)."""
        b = base_fqcn.casefold()
        return any(a.casefold() == b for a in self.ancestry(fqcn))

    def is_abstract(self, fqcn: str) -> bool | None:
        """True/False, or None if undeterminable (no shipped source). Memoized."""
        key = fqcn.casefold()
        if key not in self._abstract:
            pkg_name, cname = fqcn.split(".", 1)
            sch = self._schema(pkg_name)
            self._abstract[key] = None if sch is None else sch.abstract.get(cname.casefold())
        return self._abstract[key]

    def is_placeable(self, fqcn: str) -> bool:
        """The offline PROXY for editor-placeability (UE1 has no `CLASS_Placeable`): a non-abstract
        `Engine.Actor` descendant. `abstract=None` (undeterminable) counts as placeable — fail-open,
        so a class is listed rather than hidden."""
        return self.descends_from(fqcn, ENGINE_ACTOR) and self.is_abstract(fqcn) is not True

    # -- hierarchy (the `class list` tree) ------------------------------------
    def children_map(self) -> dict[str, list[str]]:
        """`casefold(parent fqcn) -> [child fqcn]` (name-sorted) over every class on the path — the
        inverse of the Super chain. Built once (loads every `.u`, like `bare_to_fqcn`)."""
        if self._children is None:
            m: dict[str, list[str]] = {}
            for fqcn in self._all_fqcns():
                pkg_name, cname = fqcn.split(".", 1)
                sch = self._schema(pkg_name)
                sup = None if sch is None else sch.super_refs.get(cname.casefold())
                if sup:
                    m.setdefault(sup.casefold(), []).append(fqcn)
            for k in m:
                m[k].sort(key=lambda c: (c.split(".", 1)[0].casefold(), c.split(".", 1)[1].casefold()))
            self._children = m
        return self._children

    def subclasses(self, fqcn: str) -> list[str]:
        """The DIRECT subclasses of `fqcn` (name-sorted)."""
        return self.children_map().get(fqcn.casefold(), [])

    # -- discovery (`class list`) ---------------------------------------------
    def _sorted(self, cands) -> list[str]:
        return sorted(set(cands),
                      key=lambda c: (c.split(".", 1)[0].casefold(), c.split(".", 1)[1].casefold()))

    def _distance_below(self, fqcn: str, root_cf: str) -> int | None:
        """The ancestry distance of `fqcn` below `root_cf` (0 if it IS the root, 1 for a direct
        child, …), or None if `fqcn` is not `root_cf`/a descendant."""
        for i, a in enumerate(self.ancestry(fqcn)):
            if a.casefold() == root_cf:
                return i
        return None

    def list_classes(self, *, package: str | None = None, subclass_of: str | None = None,
                     include_non_actor: bool = False, include_abstract: bool = False,
                     depth: "int | float | None" = None) -> list[str]:
        """Rooted, depth-limited class listing (decisions 2026-07-17 — a flat dump of ~1200 placeable
        classes is unusable — and 2026-07-18, the `--all` split into orthogonal flags):
        - **default** (no `--subclass-of`/`--depth`/`--include-*`): the direct children of
          `Engine.Actor` — the ~40 browsable CATEGORIES (`Engine.Light`, `Engine.Decoration`, …),
          abstract branch-points INCLUDED (they're what you drill into). Depth 1, NOT placeable-filtered.
        - **`--subclass-of X`** (no `--depth`): the PLACEABLE classes that are `X` or descend from it —
          the drill that yields the real leaves. Unlimited depth, placeable-filtered.
        - **`--depth N`** (root = `--subclass-of` or `Engine.Actor`): a structural browse — every class
          within N levels below the root, NOT placeable-filtered. `depth == math.inf` = unlimited.
        - **`--package P`** (no `--subclass-of`/`--depth`): the PLACEABLE classes defined in P (any depth).
        - **`include_non_actor`**: reroot the default from `Engine.Actor` to `Core.Object` so non-Actor
          classes are in scope (no-op when `subclass_of` sets the root explicitly). The `d==0` root-skip
          still fires, so the flat list excludes the root class itself.
        - **`include_abstract`**: drop the placeable filter in the `--subclass-of` drill and `--package`
          views (a no-op in the default/`--depth` views, which are already unfiltered).
        `--package P` narrows any of these. There is no unrooted "every class" path — the faithful full
        dump is `subclass_of=Core.Object, include_abstract=True`."""
        if subclass_of is not None and not self.class_exists(subclass_of):
            raise ClassRefError(f"unknown --subclass-of class: {subclass_of}")
        cands = list(self._all_fqcns())
        if package is not None:
            if package.casefold() not in self._paths:
                raise ClassRefError(f"package not found on the path: {package}")
            cands = [c for c in cands if c.split(".", 1)[0].casefold() == package.casefold()]
        default_root = CORE_OBJECT if include_non_actor else ENGINE_ACTOR
        root_cf = (subclass_of or default_root).casefold()
        if depth is not None:                           # structural browse, N deep, unfiltered
            eff, placeable_only = (None if depth == float("inf") else depth), False
        elif subclass_of is not None:                   # drill: placeable descendants (abstract unless include_abstract)
            eff, placeable_only = None, (not include_abstract)
        elif package is not None:                       # placeable in the package (abstract unless include_abstract)
            eff, placeable_only = None, (not include_abstract)
        else:                                           # the default category view (depth 1)
            eff, placeable_only = 1, False
        out = []
        for c in cands:
            d = self._distance_below(c, root_cf)
            if d is None:
                continue
            if subclass_of is None and d == 0:          # never list the Engine.Actor root itself
                continue
            if eff is not None and d > eff:
                continue
            if placeable_only and not self.is_placeable(c):
                continue
            out.append(c)
        return self._sorted(out)

    # -- ingest qualify + validate --------------------------------------------
    def _qualify_bare(self, bare: str) -> str | None:
        """Resolve a BARE class name to its FQCN, or None to LEAVE IT BARE (defer to live
        qualification at materialize). Raises `ClassRefError` only for a genuine 0-candidate miss.

        The offline index sees ALL on-disk classes; the live editor sees only LOADED ones, so a bare
        name in 2+ on-disk packages is offline-ambiguous even when materialize would bind it cleanly.
        So we do NOT hard-reject an ambiguity: unique → qualify; else prefer a single Engine/Core
        candidate (the overwhelming real case — bare `Class=Light` from a `MAP EXPORT` is
        `Engine.Light`); a genuine game-package collision with no engine/core winner is left BARE for
        live qualification (the trunk holds a bare class for that one actor — the legacy-bare case
        `verify.py` already handles). Ingest is thus never STRICTER than the build."""
        candidates = self.bare_to_fqcn().get(bare.casefold(), set())
        if not candidates:
            raise ClassRefError(f"unknown class: {bare} (not found in any package on the path)")
        if len(candidates) == 1:
            return next(iter(candidates))
        by_pkg = {c.split(".", 1)[0].casefold(): c for c in candidates}
        if "engine" in by_pkg:
            return by_pkg["engine"]
        if "core" in by_pkg:
            return by_pkg["core"]
        return None                                       # genuine collision → defer to live

    def qualify_and_validate(self, actors) -> None:
        """MUTATE each actor's `cls` in place: qualify a bare name to its FQCN and existence-validate
        a qualified one. All-or-nothing at the call site (the caller validates before its first
        write). Raises `ClassRefError` (→ exit 2) on an unknown class; never a traceback.

        NB call this AFTER builder-brush filtering — `is_builder_brush` keys on the exact bare
        string `"Brush"`, so qualifying `Brush`→`Engine.Brush` first would let the transient red
        builder brush escape the filter."""
        for actor in actors:
            cls = actor.cls or ""
            if "." in cls:
                if not self.class_exists(cls):
                    raise ClassRefError(f"unknown class: {cls} (package not on the path, or the "
                                        f"package does not define that class)")
            else:
                fqcn = self._qualify_bare(cls)
                if fqcn is not None:
                    actor.cls = fqcn
