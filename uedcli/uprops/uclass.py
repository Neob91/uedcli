"""Everything UClass-level: locating a class export, its OWN properties, the Super chain walked
across packages (`resolve_class_properties`), whether the class is declared `abstract`, and its raw
defaults block."""
from __future__ import annotations

import re
import struct

from ..upackage import (Package, PropertyTag, SchemaError, load_package,
                        read_compact_index as _read_compact_index, read_property_tags)
from .base import PROPERTY_TYPES, Prop, _safe_name, _schema_guard
from .ufield import _decode_property, _skip_script


def class_export_index(pkg: Package, class_name: str) -> int | None:
    """1-based export index of a UClass by name (case-insensitive — FName)."""
    want = class_name.casefold()
    for i, e in enumerate(pkg.exports):
        if pkg.names[e["nm"]].casefold() == want and pkg.name_of_ref(e["cls"]) in (None, "Class"):
            return i + 1
    return None


def own_class_properties(pkg: Package, class_name: str, *, owner_fqcn: str) -> list[Prop]:
    """A class's OWN (not inherited) properties — export records whose Outer is the class and whose
    kind is a *Property."""
    ci = class_export_index(pkg, class_name)
    if ci is None:
        raise SchemaError(f"class not found in {pkg.name}: {class_name}")
    out = []
    for i, e in enumerate(pkg.exports):
        if e["outer"] == ci and pkg.name_of_ref(e["cls"]) in PROPERTY_TYPES:
            out.append(_decode_property(pkg, i + 1, owner_fqcn))
    return out


def class_index_map(pkg: Package) -> dict[str, int]:
    """`casefold(class name) -> 1-based export index` for every UClass in `pkg` — the O(1)
    replacement for repeated `class_export_index` linear scans (the ancestry walk hammers this)."""
    out: dict[str, int] = {}
    for i, e in enumerate(pkg.exports):
        if pkg.name_of_ref(e["cls"]) in (None, "Class"):
            nm = _safe_name(pkg, e["nm"])
            if nm is not None:
                out.setdefault(nm.casefold(), i + 1)
    return out


def super_fqcn_by_index(pkg: Package, ci: int) -> str | None:
    """`_super_fqcn` given a class's 1-based export index directly (skips the name→index scan). Any
    out-of-range ref (a malformed-but-loadable package — `load_package` only checks consume-to-EOF, not
    ref bounds) raises `SchemaError`, so a caller's `except SchemaError` covers it and it never
    tracebacks as a bare `IndexError`."""
    if not (1 <= ci <= len(pkg.exports)):
        raise SchemaError(f"class export index {ci} out of range in {pkg.name}")
    sup = pkg.exports[ci - 1]["sup"]
    if sup == 0:
        return None
    try:
        if sup > 0:                                 # local super
            return f"{pkg.name}.{pkg.names[pkg.exports[sup - 1]['nm']]}"
        j = -sup - 1                                # imported super
        super_name = pkg.names[pkg.imports[j][3]]
        super_pkg = pkg.import_package_of(j)
    except IndexError as e:
        raise SchemaError(f"out-of-range super ref {sup} in {pkg.name} class #{ci}: {e}") from e
    if super_pkg is None:
        raise SchemaError(f"cannot resolve the package of super {super_name} of "
                          f"{pkg.name}.{pkg.names[pkg.exports[ci - 1]['nm']]}")
    return f"{super_pkg}.{super_name}"


def _super_fqcn(pkg: Package, class_name: str) -> str | None:
    """The fully-qualified name of `class_name`'s direct super, or None if it has none (root).
    Resolves a local super (same package) or a cross-package import super."""
    ci = class_export_index(pkg, class_name)
    if ci is None:
        raise SchemaError(f"class not found in {pkg.name}: {class_name}")
    sup = pkg.exports[ci - 1]["sup"]
    if sup == 0:
        return None
    if sup > 0:                                     # local super
        return f"{pkg.name}.{pkg.names[pkg.exports[sup - 1]['nm']]}"
    j = -sup - 1                                    # imported super
    super_name = pkg.names[pkg.imports[j][3]]
    super_pkg = pkg.import_package_of(j)
    if super_pkg is None:
        raise SchemaError(f"cannot resolve the package of super {super_name} of "
                          f"{pkg.name}.{class_name}")
    return f"{super_pkg}.{super_name}"


def super_fqcn(pkg: Package, class_name: str) -> str | None:
    """Public wrapper over `_super_fqcn`: the FQCN of `class_name`'s direct super (None at the root)."""
    return _super_fqcn(pkg, class_name)


def iter_classes(pkg: Package) -> list[str]:
    """Every UClass name defined in `pkg` (an export whose own class-type is `Class`, or the root
    `Object` whose class-ref is 0/None). Header-only — reads the export table, decodes no property
    bodies. The order is the export-table order (deterministic). An export with an out-of-range name
    index is skipped (foreign/corrupt package robustness)."""
    out = []
    for e in pkg.exports:
        if pkg.name_of_ref(e["cls"]) in (None, "Class"):
            nm = _safe_name(pkg, e["nm"])
            if nm is not None:
                out.append(nm)
    return out


def _class_script_source(pkg: Package, class_name: str, *, max_bytes: int | None = None,
                         ci: int | None = None) -> str | None:
    """The class's shipped UnrealScript source (`.uc` text) from its `ScriptText` TextBuffer, or
    None if the class has no ScriptText (a source-stripped package) or the TextBuffer body doesn't
    decode cleanly. TextBuffer body layout (verified live 2026-07-17 on Engine/DeusEx/DeusExDeco):
    `[UObject empty property-list `None` terminator: 1 compact] + Pos:u32 + Top:u32 + Text:FString`
    — the FString length lands EXACTLY at `soff+ssize`, which is asserted as a free integrity check
    (a mismatch ⇒ our layout read is wrong ⇒ return None rather than hand back garbage).

    `max_bytes` decodes only the leading N bytes of the text (the full length is still read + integrity
    -checked) — for callers that only need the class declaration at the top, this avoids decoding +
    scanning a multi-KB body.

    `ci` is the class's precomputed 1-based export index (from a `class_index_map`) — pass it to skip
    the O(n) `class_export_index` scan, which turns a per-class caller (decoding EVERY class's abstract
    flag) from O(n²) into O(n). When None it is looked up as before."""
    if ci is None:
        ci = class_export_index(pkg, class_name)
        if ci is None:
            raise SchemaError(f"class not found in {pkg.name}: {class_name}")
    buf, p = pkg.buf, pkg.exports[ci - 1]["soff"]
    try:
        _sup, p = _read_compact_index(buf, p)          # UField.SuperField
        _next, p = _read_compact_index(buf, p)         # UField.Next
        st, p = _read_compact_index(buf, p)            # UStruct.ScriptText -> TextBuffer ref
    except (IndexError, struct.error):
        return None
    if st <= 0 or st > len(pkg.exports):               # bounds: a garbage script-text ref → no source
        return None
    tb = pkg.exports[st - 1]
    if pkg.name_of_ref(tb["cls"]) != "TextBuffer":
        return None
    so, sz = tb["soff"], tb["ssize"]
    if sz <= 0:
        return None
    try:
        _none, q = _read_compact_index(buf, so)        # UObject empty prop-list `None` terminator
        q += 8                                          # Pos:u32 + Top:u32
        length, q = _read_compact_index(buf, q)         # FString length
    except (IndexError, struct.error):
        return None
    if length < 0 or q + length != so + sz:            # integrity: text must fill the body exactly
        return None
    take = length if max_bytes is None else min(length, max_bytes)
    return buf[q:q + take].split(b"\x00", 1)[0].decode("latin-1", "replace")


_ABSTRACT_DECL = re.compile(r"\bclass\b(.*?);", re.DOTALL | re.IGNORECASE)


_ABSTRACT_KW = re.compile(r"\babstract\b", re.IGNORECASE)


_LINE_COMMENT = re.compile(r"//[^\n]*")


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def class_is_abstract(pkg: Package, class_name: str, *, ci: int | None = None) -> bool | None:
    """True/False if `class_name` is declared `abstract`, or None if it can't be determined offline
    (no shipped source). Reads the `.uc` class declaration: strip `//` and `/* */` comments FIRST
    (so a `;` inside a comment can't truncate the declaration early), then test `\\babstract\\b`
    inside the first `class ... ;` statement (DOTALL — declarations are routinely multi-line;
    word-boundary — a class/parent whose NAME contains "abstract" must not match). `CLASS_Abstract`
    is per-class-declared, NOT inherited, so this reads the class's OWN declaration only.

    A None result is fail-open at the call site (a maybe-unplaceable class is listed rather than
    hidden). DX ships source for every class, so None is a forward-compat concession only.

    `ci` (the class's precomputed export index) is threaded straight to `_class_script_source` to skip
    its O(n) name→index scan — see there."""
    # The class declaration is at the very top (after the header comment); decode only the head — a
    # generous 16 KB covers any real header + the multi-line declaration. If the `class ... ;` isn't
    # found in the head (a pathologically long header), fall back to the full source once.
    src = _class_script_source(pkg, class_name, max_bytes=16384, ci=ci)
    result = abstract_from_source(src)
    if result is None and src is not None and len(src) >= 16384:   # head had no decl → full source
        result = abstract_from_source(_class_script_source(pkg, class_name, ci=ci))
    return result


def abstract_from_source(src: str | None) -> bool | None:
    """Pure helper: is `src` (a class's `.uc` text) an `abstract` class declaration? None if `src` is
    None or has no `class … ;` declaration; True/False otherwise. Strips `//` + `/* */` comments
    FIRST (a `;` inside a comment can't truncate the decl), matches `class … ;` DOTALL (multi-line
    decls), and tests `\\babstract\\b` (word-boundary — a `*Abstract*` class/parent NAME must not
    match)."""
    if src is None:
        return None
    stripped = _LINE_COMMENT.sub(" ", _BLOCK_COMMENT.sub(" ", src))
    m = _ABSTRACT_DECL.search(stripped)
    if m is None:
        return None
    return _ABSTRACT_KW.search(m.group(1)) is not None


def resolve_class_properties(fqcn: str, *, resolver, _seen=None, _cache=None) -> list[Prop]:
    """ALL properties of a class — own + every ancestor's — walking the Super chain across packages.

    `fqcn` is `Package.Class`. `resolver(package_name) -> path | None` maps a package name to its
    `.u` path on the schema search path; a None result is a hard SchemaError (no fallback). Child
    props override an ancestor's on a case-folded name collision (most-derived kept). Returns the
    union ordered child-first.
    """
    from .. import schema_cache                      # lazy: schema_cache imports uprops (cycle-break)

    seen = _seen if _seen is not None else set()
    cache = _cache if _cache is not None else {}
    if "." not in fqcn:
        raise SchemaError(f"class must be fully qualified (Package.Class): {fqcn!r}")
    if fqcn.casefold() in seen:
        return []                                   # cycle guard (shouldn't happen in a class graph)
    seen.add(fqcn.casefold())
    pkg_name, class_name = fqcn.split(".", 1)
    # Three sources for a package's own-prop schema + super link, giving IDENTICAL results:
    #  - a full `Package` a caller pre-seeded into `_cache` (e.g. `class show` seeds the packages its
    #    ClassIndex already loaded, so the super chain and prop set read the SAME bytes) → live decode;
    #  - else, cache ON: the persistent per-package SCHEMA CACHE (spec 2026-07-18-package-schema-cache
    #    §4.6) — a warm hit skips `load_package` entirely; the cached own-props are rebound to this
    #    `fqcn`'s owner, matching `own_class_properties(pkg, class_name, owner_fqcn=fqcn)` byte-for-byte;
    #  - else, cache OFF (debug/CI/paranoid): the OLD live per-package decode, memoized in `_cache`, so
    #    we decode only the CHAIN's classes (not the whole package — the bundle decode is amortized only
    #    when the cache persists it) and raise on a corrupt super, exactly as before this cache existed.
    # All three raise `SchemaError` on an unknown class / corrupt super (no fallback, §6).
    seeded = cache.get(pkg_name)
    if isinstance(seeded, Package):
        props = list(own_class_properties(seeded, class_name, owner_fqcn=fqcn))
        sup = _super_fqcn(seeded, class_name)
    else:
        path = resolver(pkg_name)
        if path is None:
            # Neutral wording on purpose: this walk serves BOTH ingest validation and `class show`,
            # and each caller prefixes its own context — "cannot validate …" here read as nonsense
            # under `class show`, which validates nothing.
            raise SchemaError(f"package {pkg_name!r} (needed for {fqcn}) not found on the schema "
                              "search path — the real game .u must be present")
        if schema_cache._enabled():
            schema = schema_cache.load_package_schema(path, name=pkg_name, need_props=True)
            props = list(schema.own_props_for(class_name, owner_fqcn=fqcn))
            sup = schema.super_ref_for(class_name)
        else:
            pkg = cache[pkg_name] = load_package(path, name=pkg_name)
            props = list(own_class_properties(pkg, class_name, owner_fqcn=fqcn))
            sup = _super_fqcn(pkg, class_name)
    if sup is not None:
        inherited = resolve_class_properties(sup, resolver=resolver, _seen=seen, _cache=cache)
        have = {p.name.casefold() for p in props}
        props.extend(p for p in inherited if p.name.casefold() not in have)
    return props


@_schema_guard
def class_default_tags(pkg: Package, class_name: str) -> list[PropertyTag]:
    """The class's OWN defaults block — the tagged-property list at the UClass body tail — as
    raw `PropertyTag`s (a sparse diff against the SUPER's defaults). Raises `SchemaError` on any
    layout desync (incl. not landing exactly at the body's end)."""
    ci = class_export_index(pkg, class_name)
    if ci is None:
        raise SchemaError(f"class not found in {pkg.name}: {class_name}")
    e = pkg.exports[ci - 1]
    so, sz = e["soff"], e["ssize"]
    if sz <= 0:                                      # an intrinsic class with no body: no defaults
        return []
    buf, end = pkg.buf, e["soff"] + e["ssize"]
    p = so
    _sup, p = _read_compact_index(buf, p)            # UField.SuperField
    _next, p = _read_compact_index(buf, p)           # UField.Next
    _st, p = _read_compact_index(buf, p)             # UStruct.ScriptText
    _children, p = _read_compact_index(buf, p)       # UStruct.Children
    _fname, p = _read_compact_index(buf, p)          # UStruct.FriendlyName
    p += 8                                           # Line:u32 + TextPos:u32
    script_size = struct.unpack_from("<I", buf, p)[0]; p += 4
    p = _skip_script(pkg, p, script_size)
    p += 8 + 8 + 2 + 4                               # UState: ProbeMask,IgnoreMask,LabelTableOffset,StateFlags
    p += 4 + 16                                      # UClass: ClassFlags + ClassGuid
    depcnt, p = _read_compact_index(buf, p)          # Dependencies TArray
    for _ in range(depcnt):
        _cls, p = _read_compact_index(buf, p)
        p += 8                                       # Deep:u32 + ScriptTextCRC:u32
    impcnt, p = _read_compact_index(buf, p)          # PackageImports TArray
    for _ in range(impcnt):
        _n, p = _read_compact_index(buf, p)
    _within, p = _read_compact_index(buf, p)         # ClassWithin (v>=62)
    _cfg, p = _read_compact_index(buf, p)            # ClassConfigName (v>=62)
    tags, p = read_property_tags(pkg, p, end)
    if p != end:
        raise SchemaError(f"{pkg.name}.{class_name}: defaults did not consume to body end "
                          f"(cursor {p} != {end}, {end - p} bytes left)")
    return tags


def class_children_ref(pkg: Package, class_index1: int) -> int:
    """A Class export's `UStruct.Children` head ref. Unlike `Struct`/field exports, a Class body
    has NO leading UObject tagged-prop header: [SuperField][Next][ScriptText][Children]…"""
    e = pkg.exports[class_index1 - 1]
    buf, p = pkg.buf, e["soff"]
    _sup, p = _read_compact_index(buf, p)
    _next, p = _read_compact_index(buf, p)
    _st, p = _read_compact_index(buf, p)
    children, _p = _read_compact_index(buf, p)
    return children


def class_serialization_order(fqcn: str, *, resolver, _pkgs: dict | None = None) -> dict[str, int]:
    """`casefold(prop name) -> rank` in the editor's tagged-property SERIALIZATION order for
    `fqcn`: each class's own `UStruct.Children` linked list in chain order, most-derived class
    first, first occurrence winning on a name collision. This is the order a `MAP SAVE` writes
    FPropertyTags in (validated on every 2026-09-02 unbuilt golden, 100% of actors) — NOT the
    export-scan order `own_class_properties` returns. Resolve against the EDITOR's packages
    (UED22 `Engine.u`/`DeusEx.u`): the game's differ in prop set and order."""
    from .ufield import _field_next
    pkgs = _pkgs if _pkgs is not None else {}
    order: list[str] = []
    seen: set[str] = set()
    cur = fqcn
    for _ in range(64):
        if "." not in cur:
            raise SchemaError(f"class must be fully qualified (Package.Class): {cur!r}")
        pkg_name, class_name = cur.split(".", 1)
        key = pkg_name.casefold()
        if key not in pkgs:
            path = resolver(pkg_name)
            if path is None:
                raise SchemaError(f"cannot resolve package {pkg_name!r} for {fqcn!r}")
            pkgs[key] = load_package(path, name=pkg_name)
        pkg = pkgs[key]
        ci = class_export_index(pkg, class_name)
        if ci is None:
            raise SchemaError(f"class not found in {pkg_name}: {class_name}")
        node = class_children_ref(pkg, ci)
        for _ in range(8192):
            if node <= 0:
                break
            e = pkg.exports[node - 1]
            if pkg.name_of_ref(e["cls"]) in PROPERTY_TYPES:
                nm = pkg.names[e["nm"]]
                if nm.casefold() not in seen:
                    seen.add(nm.casefold())
                    order.append(nm)
            node = _field_next(pkg, node)
        else:
            raise SchemaError(f"{cur}: Children chain did not terminate")
        sup = _super_fqcn(pkg, class_name)
        if sup is None:
            break
        cur = sup
    return {n.casefold(): i for i, n in enumerate(order)}
