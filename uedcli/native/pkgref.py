"""Import / name resolver (§30.6).

Maps every referenced class -> its defining package + a synthesized import entry, and
every content object (texture/sound/music) -> its `(ClassPackage, ClassName,
PackageIndex-chain, ObjectName)` import.  Import fields ClassPackage/ClassName/ObjectName
are NAME indices (FName compact-index); PackageIndex is an object-ref of the outer
package import.

A class's package is resolved from an explicit `Package.Class` qualification (the trunk may
store a qualified class) or, for a BARE class name, from a **class->package index** built by
scanning the game's real `.u` code packages on the search path (`build_class_package_index`):
that index maps `DeusExMover`->`DeusEx`, `ATM`->`DeusEx`, `PlayerStart`/`ZoneInfo`/`Level`->
`Engine`, etc., exactly as the engine's own object namespace does.  A bare class the index does
not know (a native pseudo-class like `Level`, or a package genuinely absent from the search
path) falls back to the caller's `default_package` ("Engine") — the correct answer for the
engine pseudo-classes and a non-fatal best guess otherwise (the build surfaces the latter as a
warning from `materialize.run_materialize_native`).  Historically this fell back to a NON-EXISTENT
`uprops.package_of_class`, so EVERY class defaulted to `Engine` — fatal on any real level, which
imports `DeusEx`/`Extension`/... classes (spike section 88).
"""
from __future__ import annotations

from pathlib import Path

from .codec import ref_import
from .pkg_write import NameTable, ImportRec, parse_package


# Package-set (frozenset of dir paths) -> {classname.casefold(): package_stem}.  Built once per
# distinct search-dir set per process (the scan parses ~45 `.u` headers, ~2 s) and reused across
# every actor and every build in the same run.
_CLASS_PKG_CACHE: dict = {}


def build_class_package_index(pkg_dirs) -> dict:
    """Scan the `*.u` CODE packages in `pkg_dirs` and map `classname.casefold()` -> the bare stem
    of the package that DEFINES that UClass (`"DeusExMover"` -> `"DeusEx"`).

    A UClass export is detected by its own class-ref: in the v68 game `.u`, a UClass export's class
    field is NULL (ref 0 -> `class_of_export` returns None), so `None` is the load-bearing signal
    (the `"Class"` alternative covers other package versions where the ref names the `Class`
    object).  The export name is the class name; the package file stem is the owning package.  A
    class name is UNIQUE across the loaded package set (UE1's single global object namespace —
    verified: 0 cross-package collisions across the 45 shipped DeusEx `.u`), so which package a
    given name maps to is unambiguous regardless of scan order; `pkg_dirs` is still walked in the
    caller's order (overlay first) and `setdefault` keeps the first occurrence.  A bad/locked/
    non-code package is skipped, never fatal.  Result is memoized per dir-set for the process (the
    returned dict is shared — callers MUST treat it read-only)."""
    key = tuple(str(d) for d in (pkg_dirs or ()))
    cached = _CLASS_PKG_CACHE.get(key)
    if cached is not None:
        return cached
    index: dict = {}
    for d in key:
        dp = Path(d)
        if not dp.is_dir():
            continue
        for u in sorted(dp.glob("*.u")):
            try:
                p = parse_package(u.read_bytes())
            except Exception:
                continue                      # a bad/locked package never breaks the build
            stem = u.stem
            for i, e in enumerate(p.exports):
                if p.class_of_export(i) in (None, "Class"):
                    nm = p.names[e["nm"]]
                    index.setdefault(nm.casefold(), stem)
    _CLASS_PKG_CACHE[key] = index
    return index


def build_texture_group_index(pkg_dirs, kinds=("Texture",)) -> dict:
    """Scan `*.utx` in `pkg_dirs` and map `(package_stem.lower(), objname.lower())` -> the object's
    GROUP chain (e.g. "Concrete", or "" for a top-level object).

    UE1 content packages nest objects in groups; a texture's true path is `Package.Group.Name` and
    an import MUST carry that group in its outer chain (the editor emits it) or the game raises
    "Can't find Texture in file".  Our trunk stores only the 2-part `Package.Name` a poly's
    `Texture=` uses, so `object_ref` needs this index to re-attach the group.  `pkg_dirs` is
    searched in order (project overlay first, then game base — first hit wins, mirroring the
    composed search path)."""
    index: dict = {}
    for d in pkg_dirs or ():
        dp = Path(d)
        if not dp.is_dir():
            continue
        for utx in sorted(dp.glob("*.utx")):
            try:
                p = parse_package(utx.read_bytes())
            except Exception:
                continue                      # a bad/locked package never breaks the build
            stem = utx.stem.lower()
            for i, e in enumerate(p.exports):
                if p.class_of_export(i) not in kinds:
                    continue
                parts, outer = [], e["outer"]
                while outer > 0:              # walk the outer chain up to the package root
                    oe = p.exports[outer - 1]
                    parts.append(p.names[oe["nm"]])
                    outer = oe["outer"]
                index.setdefault((stem, p.names[e["nm"]].lower()), ".".join(reversed(parts)))
    return index


class Resolver:
    def __init__(self, names: NameTable, texture_groups: dict | None = None,
                 class_packages: dict | None = None):
        self.names = names
        # (package.lower(), objname.lower()) -> group chain ("" = top-level); see build_texture_group_index
        self.texture_groups = texture_groups or {}
        # classname.casefold() -> defining package stem; see build_class_package_index. Empty ⇒
        # every bare class falls back to `default_package` (the pre-fix behaviour).  A build-level
        # warning for a genuinely-unresolvable class is emitted in `materialize.run_materialize_native`
        # (which holds the actor list + the warnings channel), not here.
        self.class_packages = class_packages or {}
        self.imports: list[ImportRec] = []
        self._pkg: dict[str, int] = {}          # package chain key -> import-ref
        self._cls: dict[tuple, int] = {}         # (package, class) -> import-ref
        self._obj: dict[tuple, int] = {}         # (pkgchain, kind, name) -> import-ref
        self._core = names.index("Core")
        self._n_package = names.index("Package")
        self._n_class = names.index("Class")

    def _add(self, rec: ImportRec) -> int:
        idx0 = len(self.imports)
        self.imports.append(rec)
        return ref_import(idx0)

    def package_ref(self, chain: str) -> int:
        """Import-ref of a package.  `chain` is dot-joined outers, e.g. "Engine" or
        "DeusExItems.Skins" (a sub-package under a parent)."""
        key = chain
        r = self._pkg.get(key)
        if r is not None:
            return r
        parts = chain.split(".")
        parent = 0
        if len(parts) > 1:
            parent = self.package_ref(".".join(parts[:-1]))
        r = self._add(ImportRec(class_package=self._core, class_name=self._n_package,
                                package_index=parent,
                                object_name=self.names.index(parts[-1])))
        self._pkg[key] = r
        return r

    def class_ref(self, package: str, classname: str) -> int:
        key = (package, classname)
        r = self._cls.get(key)
        if r is not None:
            return r
        pkg_ref = self.package_ref(package)
        r = self._add(ImportRec(class_package=self._core, class_name=self._n_class,
                                package_index=pkg_ref,
                                object_name=self.names.index(classname)))
        self._cls[key] = r
        return r

    def qualified_class_ref(self, qualified: str, *, default_package: str = "Engine") -> int:
        """Resolve "Package.Class" or a bare "Class" (uses uprops, else default)."""
        if "." in qualified:
            package, classname = qualified.split(".", 1)
            # a class name itself never contains a further dot; guard against groups
            classname = classname.split(".")[-1]
            return self.class_ref(package, classname)
        package = self._package_of_class(qualified, default_package)
        return self.class_ref(package, qualified)

    def _package_of_class(self, classname: str, default_package: str) -> str:
        return self.class_packages.get(classname.casefold()) or default_package

    def content_ref(self, package: str, kind: str, name: str,
                     sub_package: str | None = None) -> int:
        """A texture/sound/music import.  `kind` is "Texture"/"Sound"/"Music".  The
        outer PackageIndex is the sub-package (if any) else the root package."""
        chain = f"{package}.{sub_package}" if sub_package else package
        key = (chain, kind, name)
        r = self._obj.get(key)
        if r is not None:
            return r
        outer = self.package_ref(chain)
        # ClassPackage names the package that DEFINES `kind` (the object's class), NOT the object's
        # own package. `Class`/`Package` are Core (a `Script=Class'DeusEx.Mission02'` ref imports
        # as Core.Class); a texture SUBCLASS (`WetTexture`, `FireTexture`) lives in its own code
        # package (`Fire`), found in the class->package index; the plain Engine content classes
        # (Texture/Sound/Music/Mesh) fall back to Engine. Getting it wrong makes the game refuse the
        # import ("Can't find <kind> in file" / "Can't find Class in file").
        owner = ("Core" if kind.casefold() in ("class", "package")
                 else self.class_packages.get(kind.casefold()) or "Engine")
        r = self._add(ImportRec(class_package=self.names.index(owner),
                                class_name=self.names.index(kind),
                                package_index=outer,
                                object_name=self.names.index(name)))
        self._obj[key] = r
        return r

    def texture_ref(self, qualified: str) -> int:
        """Resolve a poly `Texture=` of the form Package[.Group].Name to an import-ref."""
        return self.object_ref("Texture", qualified)

    def object_ref(self, object_class: str, qualified: str) -> int:
        """Resolve an object instance reference `object_class 'Package[.Group].Name'` (a texture,
        mesh, sound, music, ...) to an import-ref.  `object_class` is the referenced object's
        class name (the import's ClassName); the outer PackageIndex is the sub-package chain (if
        any) else the root package."""
        parts = qualified.split(".")
        if len(parts) == 1:
            raise ValueError(f"unqualified {object_class} reference (no package): {qualified!r}")
        package = parts[0]
        name = parts[-1]
        sub = ".".join(parts[1:-1]) if len(parts) > 2 else None
        if sub is None:
            # re-attach the group the trunk's 2-part `Package.Name` dropped (else the game can't
            # find the object — the editor always emits the full `Package.Group.Name`).
            g = self.texture_groups.get((package.lower(), name.lower()))
            if g:
                sub = g
        return self.content_ref(package, object_class, name, sub_package=sub)
