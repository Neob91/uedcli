"""Offline class-property extraction from a UE1 `.u` package's bytes — the schema source for
`actor prop` validation (decisions 2026-06-26 12:41/14:10 UTC: no fallbacks; parse the REAL game
`.u`, never a v69 stub). Productionizes the `2026-06-26-uproperty-typed-decode` spike
(`uproperty_decode.py`), adding the **Super-chain inheritance union across packages** the spike's
own-props-only `class_properties` lacked.

For each `*Property` export whose `Outer` is a class it recovers `name`, `kind`, `array_dim`
(static-array bound, 1 for a scalar), the low-16 `CPF_*` flags, and the type tail (the body's final
compact): a `ByteProperty`'s Enum (→ its value names), an `Object`/`Class`/`Struct`Property's
referenced object. `resolve_class_properties` then unions a class's own props with every ancestor's,
crossing package boundaries via the import table and a caller-supplied `resolver` (package name →
`.u` path on the schema search path). Child props override parents on a case-folded name collision.

Pure: parses bytes, never runs the editor. The low-level container parsing (header, tables,
compact index, tagged-property lists) lives in the unified core `upackage.py` (decisions.md
2026-07-18 10:02 §5) — `Package`/`load_package`/`SchemaError` are re-exported from there, so
every existing `uprops.Package`/`uprops.SchemaError` caller keeps working unchanged. The
cursor-to-EOF integrity check on every record is the no-fallback contract — a layout error
desyncs and is caught.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, replace

from .upackage import (                              # noqa: F401  (re-exported public API)
    Package,
    PropertyTag,
    SchemaError,
    load_package,
    read_compact_index as _read_compact_index,
    read_fstring as _read_fstring,
    read_property_tags,
    PT_BYTE, PT_INT, PT_BOOL, PT_FLOAT, PT_OBJECT, PT_NAME, PT_STR_LEGACY, PT_STR, PT_STRUCT,
)

# The closed set of UProperty subclasses (proven finite = 11 by the name-only spike).
PROPERTY_TYPES = frozenset({
    "ArrayProperty", "BoolProperty", "ByteProperty", "ClassProperty", "FloatProperty",
    "IntProperty", "NameProperty", "ObjectProperty", "PointerProperty", "StrProperty",
    "StructProperty",
})
_KINDS_WITH_TYPE_REF = frozenset({
    "ByteProperty", "ObjectProperty", "StructProperty", "ClassProperty", "ArrayProperty",
})


CPF_NET = 0x20                      # PropertyFlags bit: a 2-byte RepOffset follows Category on disk


import functools


def _schema_guard(fn):
    """Convert ANY parse-layer escape (IndexError/struct.error/ValueError/RecursionError/
    OverflowError from a corrupt-but-loadable package body — review finding: `load_package`'s
    wrapper covers only the header/tables, and byte-flip fuzzing reached bare tracebacks in the
    body decoders) into a named `SchemaError`, honoring the module's "every parse error raises
    SchemaError" contract. A real SchemaError passes through unchanged."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SchemaError:
            raise
        except RecursionError:
            raise SchemaError(f"{fn.__name__}: runaway recursion decoding a corrupt "
                              "package body") from None
        except (IndexError, ValueError, OverflowError, KeyError) as e:
            raise SchemaError(f"{fn.__name__}: corrupt package body "
                              f"({type(e).__name__}: {e})") from e
        except struct.error as e:
            raise SchemaError(f"{fn.__name__}: truncated package body ({e})") from e
    return wrapper




@dataclass(frozen=True, kw_only=True)
class Prop:
    name: str
    kind: str                       # e.g. "ByteProperty"
    array_dim: int                  # static-array size; 1 for a scalar
    property_flags: int             # full 32-bit CPF_* flags
    type_ref: int                   # signed object ref of the type tail (0 == None)
    type_name: str | None           # resolved name of type_ref (enum/struct/object class)
    owner: str                      # the class that declares it (FQCN), for diagnostics
    enum_value_names: tuple[str, ...] = ()   # a ByteProperty's LOCAL enum values; () if none/imported
    category: str | None = None     # editor group (`var(Category)`); the declaring class name for a
                                     # bare `var()`; None for a non-editable `var` (name index 0)
    # An `ArrayProperty`'s ELEMENT property (`UArrayProperty::Inner`), decoded as a Prop of its own —
    # so a caller can see the element KIND (`IntProperty`/`ObjectProperty`/`StructProperty`/…) and,
    # through the element's own `type_ref`/`type_name`, the element's enum/struct/object type. This
    # is the only place that information exists: an ArrayProperty's own `type_ref`/`type_name` point
    # at the Inner UProperty OBJECT (so `type_name` is the inner's *name*, e.g. "Ammo", never its
    # kind). None for every non-array Prop, and for an array whose Inner ref is 0 or a cross-package
    # import (the UnrealScript compiler always emits Inner as a child export of the ArrayProperty in
    # the SAME package, so an import there means a corrupt/foreign package). Consumed by
    # `mapimport`'s dynamic-array value decode (`dev/docs/specs/2026-07-24-level-import.md` §5.2d).
    array_inner: "Prop | None" = None


def _last_compact(buf: bytes, start: int, end: int) -> int:
    pos, last = start, 0
    while pos < end:
        last, pos = _read_compact_index(buf, pos)
    return last


def _decode_property(pkg: Package, export_index1: int, owner_fqcn: str, *, _inner: bool = False) -> Prop:
    """Decode one *Property export (1-based index) into typed info. The v68/v69 UProperty body layout
    is (RE'd byte-exact 2026-07-18 — empirical decode + `Core.dll UProperty::Serialize` @ 0x10164fd0,
    see `unrealed/class-schema.md`):

        [UObject None terminator: compact] [UField.SuperField: compact] [UField.Next: compact]
        [ArrayDim: u32] [PropertyFlags: u32] [Category: FName compact]
        [RepOffset: u16 — ONLY if PropertyFlags & CPF_NET] [subclass type tail: compact ref(s)]

    (The OLD decode read the leading None-terminator AS "category" and mis-offset the header, so
    `property_flags` was garbage for every prop and `array_dim` was wrong for any static array whose
    size didn't fit the `>>16 & 0xFF` hack — see the doc. This reads the true fields.)"""
    e = pkg.exports[export_index1 - 1]
    kind = pkg.name_of_ref(e["cls"])
    so, sz = e["soff"], e["ssize"]
    if sz <= 0:
        raise SchemaError(f"property {pkg.names[e['nm']]} has empty serial body (ssize={sz})")
    buf = pkg.buf
    _none, p = _read_compact_index(buf, so)         # UObject empty tagged-prop-list terminator (==0)
    _super, p = _read_compact_index(buf, p)         # UField.SuperField
    _next, p = _read_compact_index(buf, p)          # UField.Next
    array_dim = struct.unpack_from("<I", buf, p)[0] or 1; p += 4
    property_flags = struct.unpack_from("<I", buf, p)[0]; p += 4
    cat_idx, p = _read_compact_index(buf, p)        # UProperty.Category (FName)
    category = pkg.names[cat_idx] if 0 < cat_idx < len(pkg.names) else None
    if property_flags & CPF_NET:                     # a 2-byte RepOffset sits before the type tail
        p += 2
    type_ref = _last_compact(buf, p, so + sz) if kind in _KINDS_WITH_TYPE_REF else 0
    # A ByteProperty's LOCAL enum values, decoded eagerly so a Prop carries everything actor-prop
    # validation needs (resolve_class_properties discards the loaded Package). An imported enum
    # (type_ref < 0) or a plain byte (0) yields () — validation then can't enumerate, so accepts.
    enum_names = tuple(enum_values(pkg, type_ref)) if kind == "ByteProperty" else ()
    # An ArrayProperty's type tail is its `Inner` UProperty ref — decode that property too, so the
    # ELEMENT kind is available (see `Prop.array_inner`). `_inner` stops the recursion at one level:
    # UnrealScript cannot declare `array<array<T>>`, so a nested array ref is corruption, and an
    # Inner that (corruptly) points back at itself would otherwise recurse forever.
    inner = None
    if kind == "ArrayProperty" and not _inner and 0 < type_ref <= len(pkg.exports):
        if pkg.name_of_ref(pkg.exports[type_ref - 1]["cls"]) in PROPERTY_TYPES:
            inner = _decode_property(pkg, type_ref, owner_fqcn, _inner=True)
    return Prop(name=pkg.names[e["nm"]], kind=kind, array_dim=array_dim,
                property_flags=property_flags, type_ref=type_ref,
                type_name=pkg.name_of_ref(type_ref), owner=owner_fqcn,
                enum_value_names=enum_names, category=category, array_inner=inner)


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


def _safe_name(pkg: Package, nm: int) -> str | None:
    """The name-table entry `nm`, or None if out of range (a malformed-but-loadable package —
    `load_package` checks consume-to-EOF, not that every `nm` indexes a real name)."""
    return pkg.names[nm] if 0 <= nm < len(pkg.names) else None


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
    from . import schema_cache                      # lazy: schema_cache imports uprops (cycle-break)

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
def enum_values(pkg: Package, type_ref: int) -> list[str]:
    """The ordered value names of a ByteProperty's enum `type_ref`. A positive ref is a LOCAL Enum
    export (decoded byte-exact); a 0 ref is a plain byte (→ []). A negative (cross-package import)
    ref needs the owning package loaded — callers that want its values resolve that package and
    decode the enum there; here it returns [] with the owner discoverable via `import_package_of`."""
    if type_ref <= 0:
        return []
    e = pkg.exports[type_ref - 1]
    if pkg.name_of_ref(e["cls"]) != "Enum":
        return []
    buf, p = pkg.buf, e["soff"]
    _none, p = _read_compact_index(buf, p)
    _next, p = _read_compact_index(buf, p)
    _skip, p = _read_compact_index(buf, p)
    count, p = _read_compact_index(buf, p)
    vals = []
    for _ in range(count):
        v, p = _read_compact_index(buf, p)
        vals.append(pkg.names[v])
    if p != e["soff"] + e["ssize"]:
        raise SchemaError(f"enum {pkg.names[e['nm']]} body did not consume to EOF")
    return vals


# ══ Class DEFAULT VALUES — the SerializeExpr walker + UClass-tail defaults decoder ═══════════
# (spec `specs/2026-07-18-actor-prop-subcommands.md` §5.2; decisions.md 2026-07-18 10:02 §5.)
#
# A UClass export body is:
#   [UField.SuperField][UField.Next]                       (compacts; NO leading None terminator —
#                                                           UE1 skips the UObject tagged list for
#                                                           UClass objects and serializes the class
#                                                           DEFAULTS at the tail instead)
#   [UStruct: ScriptText][Children][FriendlyName][Line:u32][TextPos:u32][ScriptSize:u32][script…]
#   [UState: ProbeMask:u64][IgnoreMask:u64][LabelTableOffset:u16][StateFlags:u32]
#   [UClass: ClassFlags:u32][ClassGuid:16B][Dependencies:TArray{Class compact,Deep u32,CRC u32}]
#   [PackageImports:TArray{name compact}][ClassWithin: compact][ClassConfigName: name compact]
#   [DEFAULTS: tagged-property list, "None"-terminated]  → must land EXACTLY at soff+ssize.
#
# The script bytecode has NO on-disk byte length — `ScriptSize` counts the IN-MEMORY size, and
# names/object refs are compact on disk but 4 bytes in memory, so the walker tracks both cursors
# and replays `UStruct::SerializeExpr` token by token. Unknown opcode / any desync raises
# `SchemaError` (no-fallback). Validated by the corpus-integrity test: every class in every game
# `.u` must walk clean and land the defaults list exactly at EOF.

_EX_END_FUNCTION_PARMS = 0x16


def _walk_expr(pkg: Package, pos: int, mem: int) -> tuple[int, int, int]:
    """Replay one SerializeExpr: returns (pos, mem, token). Token semantics per the UE1 v68
    opcode set; disk/memory sizes differ only for compacts (name/object refs: compact on disk,
    4 in memory)."""
    buf = pkg.buf
    tok = buf[pos]; pos += 1; mem += 1

    def obj() -> None:                              # object ref: compact disk / 4 mem
        nonlocal pos, mem
        _v, pos = _read_compact_index(buf, pos)
        mem += 4

    def name() -> None:                             # FName: compact disk / 4 mem
        nonlocal pos, mem
        _v, pos = _read_compact_index(buf, pos)
        mem += 4

    def fixed(n: int) -> None:                      # n bytes, same on disk and in memory
        nonlocal pos, mem
        pos += n; mem += n

    def expr() -> int:
        nonlocal pos, mem
        pos, mem, t = _walk_expr(pkg, pos, mem)
        return t

    def parms() -> None:                            # function args until EX_EndFunctionParms
        while expr() != _EX_END_FUNCTION_PARMS:
            pass

    if tok >= 0x70:                                 # single-byte native call index
        parms()
    elif tok >= 0x60:                               # extended native: high nibble + 1 byte
        fixed(1)
        parms()
    elif 0x39 <= tok <= 0x5F:                       # conversion tokens: 1 operand each
        expr()
    elif tok in (0x00, 0x01, 0x02):                 # Local/Instance/DefaultVariable
        obj()
    elif tok == 0x04:                               # Return
        expr()
    elif tok == 0x05:                               # Switch: size byte + expr
        fixed(1); expr()
    elif tok == 0x06:                               # Jump: u16
        fixed(2)
    elif tok == 0x07:                               # JumpIfNot: u16 + expr
        fixed(2); expr()
    elif tok == 0x08:                               # Stop
        pass
    elif tok == 0x09:                               # Assert: u16 line + expr
        fixed(2); expr()
    elif tok == 0x0A:                               # Case: u16 next; 0xFFFF == default (no expr)
        w = struct.unpack_from("<H", buf, pos)[0]
        fixed(2)
        if w != 0xFFFF:
            expr()
    elif tok == 0x0B:                               # Nothing
        pass
    elif tok == 0x0C:                               # LabelTable: {name,u32} until "None"
        while True:
            v, pos2 = _read_compact_index(buf, pos)
            pos = pos2; mem += 4
            nm = pkg.names[v] if 0 <= v < len(pkg.names) else None
            fixed(4)
            if nm == "None":
                break
    elif tok == 0x0D:                               # GotoLabel
        expr()
    elif tok == 0x0E:                               # EatString
        expr()
    elif tok in (0x0F, 0x14):                       # Let / LetBool
        expr(); expr()
    elif tok == 0x11:                               # New: 4 exprs
        expr(); expr(); expr(); expr()
    elif tok == 0x12:                               # ClassContext: expr + u16 + byte + expr
        expr(); fixed(3); expr()
    elif tok == 0x13:                               # MetaCast: class + expr
        obj(); expr()
    elif tok == 0x16:                               # EndFunctionParms
        pass
    elif tok == 0x17:                               # Self
        pass
    elif tok == 0x18:                               # Skip: u16 + expr
        fixed(2); expr()
    elif tok == 0x19:                               # Context: expr + u16 + byte + expr
        expr(); fixed(3); expr()
    elif tok == 0x1A:                               # ArrayElement: index expr + base expr
        expr(); expr()
    elif tok == 0x1B:                               # VirtualFunction: name + parms
        name(); parms()
    elif tok == 0x1C:                               # FinalFunction: func + parms
        obj(); parms()
    elif tok == 0x1D:                               # IntConst
        fixed(4)
    elif tok == 0x1E:                               # FloatConst
        fixed(4)
    elif tok == 0x1F:                               # StringConst: NUL-terminated
        end = buf.index(b"\x00", pos)
        n = end - pos + 1
        fixed(n)
    elif tok == 0x20:                               # ObjectConst
        obj()
    elif tok == 0x21:                               # NameConst
        name()
    elif tok in (0x22, 0x23):                       # RotationConst / VectorConst: 12 bytes
        fixed(12)
    elif tok == 0x24:                               # ByteConst
        fixed(1)
    elif tok in (0x25, 0x26, 0x27, 0x28):           # IntZero/IntOne/True/False
        pass
    elif tok == 0x29:                               # NativeParm
        obj()
    elif tok == 0x2A:                               # NoObject
        pass
    elif tok == 0x2C:                               # IntConstByte
        fixed(1)
    elif tok == 0x2D:                               # BoolVariable
        expr()
    elif tok == 0x2E:                               # DynamicCast: class + expr
        obj(); expr()
    elif tok == 0x2F:                               # Iterator: expr + u16
        expr(); fixed(2)
    elif tok in (0x30, 0x31):                       # IteratorPop / IteratorNext
        pass
    elif tok in (0x32, 0x33):                       # StructCmpEq/Ne: struct + expr + expr
        obj(); expr(); expr()
    elif tok == 0x34:                               # UnicodeStringConst: u16 units until 0
        while struct.unpack_from("<H", buf, pos)[0] != 0:
            fixed(2)
        fixed(2)
    elif tok == 0x36:                               # StructMember: property + expr
        obj(); expr()
    elif tok == 0x38:                               # GlobalFunction: name + parms
        name(); parms()
    else:
        raise SchemaError(f"unknown script opcode {tok:#04x} at {pos - 1} in {pkg.name}")
    return pos, mem, tok


def _skip_script(pkg: Package, pos: int, script_size: int) -> int:
    """Walk the whole script blob (in-memory size `script_size`), returning the disk position
    after it. A desync (memory cursor overshoots) raises `SchemaError`."""
    mem = 0
    while mem < script_size:
        pos, mem, _t = _walk_expr(pkg, pos, mem)
    if mem != script_size:
        raise SchemaError(f"script walk desync in {pkg.name}: memory cursor {mem} != "
                          f"ScriptSize {script_size}")
    return pos


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


# ── struct member schemas, value rendering, and the super-chain defaults merge ───────────────

def _field_next(pkg: Package, export_index1: int) -> int:
    """A UProperty export's `UField.Next` ref (the Children linked-list pointer): the 3rd compact
    of its body ([None][SuperField][Next]…)."""
    e = pkg.exports[export_index1 - 1]
    buf, p = pkg.buf, e["soff"]
    _none, p = _read_compact_index(buf, p)
    _sup, p = _read_compact_index(buf, p)
    nxt, _p = _read_compact_index(buf, p)
    return nxt

def struct_children_ref(pkg: Package, struct_index1: int) -> int:
    """A Struct export's `UStruct.Children` head ref. Struct body (class `Struct` ≠ `Class`, so
    the leading UObject None terminator IS present): [None][SuperField][Next][ScriptText]
    [Children]…"""
    e = pkg.exports[struct_index1 - 1]
    buf, p = pkg.buf, e["soff"]
    _none, p = _read_compact_index(buf, p)
    _sup, p = _read_compact_index(buf, p)
    _next, p = _read_compact_index(buf, p)
    _st, p = _read_compact_index(buf, p)
    children, _p = _read_compact_index(buf, p)
    return children

def find_struct_export(pkg: Package, struct_name: str) -> int | None:
    """1-based export index of a `Struct` export by name (case-insensitive)."""
    want = struct_name.casefold()
    for i, e in enumerate(pkg.exports):
        if pkg.name_of_ref(e["cls"]) == "Struct":
            nm = _safe_name(pkg, e["nm"])
            if nm is not None and nm.casefold() == want:
                return i + 1
    return None

@_schema_guard
def struct_members(pkg: Package, struct_index1: int, *, owner: str,
                   _seen: set | None = None) -> list[Prop]:
    """The ORDERED member properties of a Struct export — the `Children` linked list walked via
    each member's `UField.Next` (declaration order; the export-table order is NOT reliable, and
    the in-struct binary layout depends on this order). A struct with a super-struct contributes
    its super's members FIRST (UE1 in-memory layout), recursively."""
    if not (1 <= struct_index1 <= len(pkg.exports)):
        raise SchemaError(f"struct export index {struct_index1} out of range in {pkg.name} "
                          f"(wrong resolving package?)")
    seen = _seen if _seen is not None else set()
    if struct_index1 in seen:                        # corrupt self/cyclic super ref (fuzz finding)
        raise SchemaError(f"cyclic super-struct chain in {pkg.name} ({owner})")
    seen.add(struct_index1)
    e = pkg.exports[struct_index1 - 1]
    out: list[Prop] = []
    sup_ref = e["sup"]
    if sup_ref > 0:                                  # super-struct members lead (local supers only
        out.extend(struct_members(pkg, sup_ref, owner=owner, _seen=seen))  # DX: Plane ext. Vector
    elif sup_ref < 0:
        raise SchemaError(f"imported super-struct not supported for {owner}")
    cur = struct_children_ref(pkg, struct_index1)
    for _ in range(256):
        if cur == 0:
            return out
        if cur < 0:
            raise SchemaError(f"struct child is an import in {owner}")
        ee = pkg.exports[cur - 1]
        if pkg.name_of_ref(ee["cls"]) in PROPERTY_TYPES:
            out.append(_decode_property(pkg, cur, owner))
        cur = _field_next(pkg, cur)
    raise SchemaError(f"struct member chain did not terminate in {owner}")

@_schema_guard
def resolve_type_export(pkg: Package, type_ref: int, want_class: str, *, resolver, _pkgs: dict):
    """Resolve a Prop's `type_ref` (enum/struct) to (owning_package, 1-based export index). A
    local ref resolves in `pkg`; an import resolves via its owning package + a name lookup
    there. `want_class` is "Enum" or "Struct". PUBLIC because `classdefaults` compiles struct
    member layouts through it for the typed compare, and `dispatch` renders struct defaults —
    which is also why it carries `@_schema_guard`: an out-of-range import ref in a corrupt package
    used to escape as a bare `IndexError`, and the compare now walks the member layout of EVERY
    struct property of every class in a level, so callers that catch only `SchemaError` would have
    surfaced a traceback."""
    if type_ref > 0:
        if type_ref > len(pkg.exports):          # bounds-check AT THE SOURCE: a corrupt local ref
            raise SchemaError(f"{want_class} type ref {type_ref} out of range in {pkg.name}")
        return pkg, type_ref
    if type_ref == 0:
        raise SchemaError(f"no {want_class} type ref to resolve")
    j = -type_ref - 1
    type_name = pkg.names[pkg.imports[j][3]]
    owner_pkg_name = pkg.import_package_of(j)
    if owner_pkg_name is None:
        raise SchemaError(f"cannot resolve the owning package of imported {want_class} "
                          f"{type_name}")
    if owner_pkg_name not in _pkgs:
        path = resolver(owner_pkg_name)
        if path is None:
            raise SchemaError(f"package {owner_pkg_name!r} not found on the schema search path "
                              f"(needed for {want_class} {type_name})")
        _pkgs[owner_pkg_name] = load_package(path, name=owner_pkg_name)
    tp = _pkgs[owner_pkg_name]
    if want_class == "Struct":
        ti = find_struct_export(tp, type_name)
    else:
        want = type_name.casefold()
        ti = None
        for i, e in enumerate(tp.exports):
            if tp.name_of_ref(e["cls"]) == want_class:
                nm = _safe_name(tp, e["nm"])
                if nm is not None and nm.casefold() == want:
                    ti = i + 1
                    break
    if ti is None:
        raise SchemaError(f"{want_class} {type_name} not found in package {owner_pkg_name}")
    return tp, ti

@_schema_guard
def resolve_enum_names(prop: Prop, declaring_pkg: Package, *, resolver,
                       _pkgs: dict | None = None) -> tuple[str, ...]:
    """A ByteProperty's enum value names, CROSS-PACKAGE (spec §4): a local enum comes from the
    eager `enum_value_names`; an imported enum resolves its owning package via the import table
    and decodes the enum there. A plain byte (no enum) yields ()."""
    if prop.enum_value_names:
        return prop.enum_value_names
    if prop.kind != "ByteProperty" or prop.type_ref == 0:
        return ()
    pkgs = _pkgs if _pkgs is not None else {}
    tp, ti = resolve_type_export(declaring_pkg, prop.type_ref, "Enum",
                                  resolver=resolver, _pkgs=pkgs)
    return tuple(enum_values(tp, ti))


def format_float(v: float) -> str:
    """Canonical CLI float rendering: integral values bare (`24`), fractions trimmed to ≤6dp
    (`0.5`, `-10.25`) — the spec §4 display form (set stores text verbatim, so any float text
    round-trips; numeric comparison in `find` is format-independent)."""
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return f"{v:.6f}".rstrip("0").rstrip(".")


def format_float_t3d(v: float) -> str:
    """T3D float rendering: ALWAYS six decimal places (`24.000000`, `-2240.000000`) — the C `%f`
    form UnrealEd's own `MAP EXPORT` writes for every float, scalar or struct member. Distinct from
    `format_float`, which trims an integral value to `24` for CLI display; a natively decoded map
    must match the editor's text exactly, so it renders through this instead."""
    return f"{v:.6f}"


@dataclass(frozen=True)
class ValueStyle:
    """How a decoded property VALUE is rendered to text. Two styles exist and they are NOT
    interchangeable:

    - **`CLI_STYLE`** (the default for every caller that displays a value — `actor prop get`, the
      class-defaults table): floats trimmed (`24`, `0.5`), and a BYTE member inside a struct shown
      as its plain number.
    - **`T3D_STYLE`**: exactly what UnrealEd's `MAP EXPORT` writes — every float at six decimals
      (`24.000000`), and a byte struct member spelled as its ENUM NAME (`MainScale=(SheerAxis=
      SHEER_ZX)`, never `(SheerAxis=5)`). `mapimport` uses this so a natively decoded `.dx` is
      textually identical to the editor's export of the same map.
    """
    float_fmt: "object" = format_float       # (float) -> str
    enum_bytes: bool = False                 # render a byte STRUCT MEMBER as its enum value name


CLI_STYLE = ValueStyle()
T3D_STYLE = ValueStyle(float_fmt=format_float_t3d, enum_bytes=True)


_STRUCT_BIN_SIZES = {"ByteProperty": 1, "IntProperty": 4, "FloatProperty": 4}


def _pkg_for_owner(owner: str, fallback: Package, *, resolver, _pkgs: dict) -> Package:
    """The package a Prop was DECLARED in (its `owner` fqcn's package) — the package its
    `type_ref` is relative to. Falls back to `fallback` when the owner isn't dotted (struct
    members decoded in-place)."""
    if "." not in owner:
        return fallback
    pkg_name = owner.split(".", 1)[0]
    if pkg_name == fallback.name:
        return fallback
    if pkg_name not in _pkgs:
        path = resolver(pkg_name)
        if path is None:
            raise SchemaError(f"package {pkg_name!r} not found on the schema search path "
                              f"(needed to resolve {owner})")
        _pkgs[pkg_name] = load_package(path, name=pkg_name)
    return _pkgs[pkg_name]


def _decode_struct_bin_at(value_pkg: Package, members_pkg: Package, members: list[Prop],
                          raw: bytes, start: int, *, resolver,
                          _pkgs: dict, style: ValueStyle = CLI_STYLE
                          ) -> tuple[list[tuple[str, str]], int]:
    """Decode an in-struct binary value block (`UStructProperty::SerializeItem` →
    member-wise `SerializeBin`) into ordered (member_name, rendered_text) pairs from cursor
    `start`. Object/name COMPACTS in the VALUE resolve against `value_pkg` (the package the
    defaults tag was serialized in); a member's own `type_ref` (nested struct types) resolves
    against `members_pkg` (the package the member schema was decoded from). Returns
    (pairs, cursor_after).

    `style` picks the text form of floats and byte members — see `ValueStyle`.

    NB the SAME per-member wire forms are how UE1 serializes a DYNAMIC ARRAY's elements
    (`UArrayProperty::SerializeItem` calls the Inner property's `SerializeItem` per element), so
    `mapimport` decodes an array by passing `[inner] * count` as `members`."""
    out: list[tuple[str, str]] = []
    p = start
    for m in members:
        for i in range(m.array_dim):
            suffix = f"({i})" if m.array_dim > 1 else ""
            if m.kind in _STRUCT_BIN_SIZES:
                n = _STRUCT_BIN_SIZES[m.kind]
                chunk = raw[p:p + n]
                if len(chunk) < n:
                    raise SchemaError(f"struct value truncated at member {m.name}")
                if m.kind == "ByteProperty":
                    out.append((m.name + suffix, _byte_member_text(m, chunk[0], members_pkg,
                                                                  resolver=resolver, _pkgs=_pkgs,
                                                                  style=style)))
                elif m.kind == "IntProperty":
                    out.append((m.name + suffix,
                                str(int.from_bytes(chunk, "little", signed=True))))
                else:
                    out.append((m.name + suffix,
                                style.float_fmt(struct.unpack("<f", chunk)[0])))
                p += n
            elif m.kind in ("ObjectProperty", "ClassProperty"):
                ref, p = _read_compact_index(raw, p)
                out.append((m.name + suffix, render_object_ref(value_pkg, ref)))
            elif m.kind == "NameProperty":
                ni, p = _read_compact_index(raw, p)
                out.append((m.name + suffix,
                            value_pkg.names[ni] if 0 <= ni < len(value_pkg.names) else "None"))
            elif m.kind == "StrProperty":            # in-struct FString (compact len + bytes)
                s, p = _read_fstring(raw, p)
                out.append((m.name + suffix, s))
            elif m.kind == "BoolProperty":           # in-struct bool: one byte (0/1)
                if p >= len(raw):
                    raise SchemaError(f"struct value truncated at member {m.name}")
                out.append((m.name + suffix, "True" if raw[p] else "False"))
                p += 1
            elif m.kind == "StructProperty":
                tp, inner = struct_member_schema(members_pkg, m, resolver=resolver, _pkgs=_pkgs)
                sub, p = _decode_struct_bin_at(value_pkg, tp, inner, raw, p,
                                               resolver=resolver, _pkgs=_pkgs, style=style)
                out.append((m.name + suffix,
                            "(" + ",".join(f"{k}={v}" for k, v in sub) + ")"))
            else:
                raise SchemaError(f"unsupported struct member kind {m.kind} ({m.name}) "
                                  "in a defaults value")
    return out, p


def _byte_member_text(m: Prop, value: int, members_pkg: Package, *, resolver, _pkgs: dict,
                      style: ValueStyle) -> str:
    """A ByteProperty struct member's rendered text: its plain number under `CLI_STYLE`, its ENUM
    VALUE NAME under a style with `enum_bytes` (what `MAP EXPORT` writes — `SheerAxis=SHEER_ZX`).
    Falls back to the number when the member has no enum or the value is out of the enum's range
    (a real, if odd, possibility: a byte holds 0-255 regardless of how many names the enum has)."""
    if not style.enum_bytes or m.type_ref == 0:
        return str(value)
    dp = _pkg_for_owner(m.owner, members_pkg, resolver=resolver, _pkgs=_pkgs)
    names = resolve_enum_names(m, dp, resolver=resolver, _pkgs=_pkgs)
    return names[value] if value < len(names) else str(value)


@_schema_guard
def struct_member_schema(pkg: Package, prop: Prop, *, resolver,
                         _pkgs: dict) -> tuple[Package, list[Prop]]:
    """A `StructProperty`'s struct type resolved to `(package_it_was_decoded_from, ordered members)`.
    `pkg` is the fallback package for a member whose `owner` is not dotted (a nested struct decoded
    in place); a dotted `owner` resolves to that class's declaring package, which is what the
    prop's `type_ref` indexes."""
    if prop.kind != "StructProperty" or prop.type_ref == 0:
        raise SchemaError(f"cannot resolve the struct type of {prop.name} "
                          f"(kind={prop.kind}, type_ref={prop.type_ref})")
    dp = _pkg_for_owner(prop.owner, pkg, resolver=resolver, _pkgs=_pkgs)
    tp, ti = resolve_type_export(dp, prop.type_ref, "Struct", resolver=resolver, _pkgs=_pkgs)
    return tp, struct_members(tp, ti, owner=prop.type_name or prop.name)


def _decode_struct_bin(value_pkg: Package, members_pkg: Package, members: list[Prop],
                       raw: bytes, *, resolver, _pkgs: dict,
                       style: ValueStyle = CLI_STYLE) -> list[tuple[str, str]]:
    """`_decode_struct_bin_at` from 0 with the exact-consume integrity check (no-fallback:
    leftover bytes mean the member layout is wrong)."""
    out, p = _decode_struct_bin_at(value_pkg, members_pkg, members, raw, 0,
                                   resolver=resolver, _pkgs=_pkgs, style=style)
    if p != len(raw):
        raise SchemaError(f"struct value did not consume exactly ({p} != {len(raw)})")
    return out


def render_object_ref(pkg: Package, ref: int) -> str:
    """A signed object ref (in `pkg`'s tables) → the T3D object-ref form
    `Class'Package[.Group].Name'`, or `None` for a 0 ref."""
    if ref == 0:
        return "None"
    cls = pkg.object_class_name(ref) or "Object"
    path = pkg.object_path(ref)
    if path is None:
        raise SchemaError(f"unresolvable object ref {ref} in {pkg.name}")
    return f"{cls}'{path}'"


@_schema_guard
def struct_tag_member_tree(pkg: Package, tag: PropertyTag, prop: Prop, *, resolver, _pkgs: dict,
                           style: ValueStyle = CLI_STYLE) -> dict:
    """A `StructProperty` tag's value decoded to a NESTED tree of its members.

    The tree maps each member's rendered key → either the member's rendered TEXT, or, for a member
    that is itself a struct, a sub-tree of the same shape. It is the same decode
    `render_default_tag` joins into `(A=…,B=…)`, kept structured instead.

    **Why a tree rather than flat pairs.** UnrealEd's `MAP EXPORT` writes only the struct members
    that DIFFER from the class default's corresponding member, and it does so **recursively** — a
    mirrored brush exports `MainScale=(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)`, where the nested
    `Scale` states only the one axis that changed and drops the two that match the default. Real
    editor output committed at `uedcli/tests/fixtures/level_small.t3d` shows exactly that. Flat
    pairs cannot express it: the nested struct would already be joined into one string, so a
    comparison could only keep or drop the whole of it, producing
    `Scale=(X=-1.000000,Y=1.000000,Z=1.000000)`. Pair this with `zero_struct_tree` (for a class that
    declares no default) and `strip_member_tree` (the comparison), then `render_member_tree`.
    """
    tp, members = struct_member_schema(pkg, prop, resolver=resolver, _pkgs=_pkgs)
    tree, pos = _struct_tree_at(pkg, tp, members, tag.raw, 0, resolver=resolver, _pkgs=_pkgs,
                                style=style)
    if pos != len(tag.raw):
        raise SchemaError(f"struct value did not consume exactly ({pos} != {len(tag.raw)})")
    return tree


def _struct_tree_at(value_pkg: Package, members_pkg: Package, members: list[Prop], raw: bytes,
                    start: int, *, resolver, _pkgs: dict, style: ValueStyle) -> tuple[dict, int]:
    """`struct_tag_member_tree`'s walk. Non-struct members are decoded one at a time by the shared
    `_decode_struct_bin_at` (so there is exactly ONE definition of each member kind's wire form);
    a struct member recurses. A member that is a STATIC ARRAY contributes one entry per element,
    decoded in sequence — hence the per-key loop rather than one decode per member."""
    out: dict = {}
    p = start
    for m in members:
        if m.kind == "StructProperty":
            tp, inner = struct_member_schema(members_pkg, m, resolver=resolver, _pkgs=_pkgs)
            for k in member_keys(m):
                sub, p = _struct_tree_at(value_pkg, tp, inner, raw, p, resolver=resolver,
                                         _pkgs=_pkgs, style=style)
                out[k] = sub
        else:
            one = m if m.array_dim == 1 else replace(m, array_dim=1)
            for k in member_keys(m):
                pairs, p = _decode_struct_bin_at(value_pkg, members_pkg, [one], raw, p,
                                                 resolver=resolver, _pkgs=_pkgs, style=style)
                out[k] = pairs[0][1]
    return out, p


def zero_struct_tree(pkg: Package, prop: Prop, *, resolver, _pkgs: dict,
                     style: ValueStyle = CLI_STYLE) -> dict:
    """The ZERO value of struct property `prop`, in `struct_tag_member_tree`'s nested shape.

    A class that declares no default for a property inherits the class-default object's raw memory,
    which UE1 starts as zeros — so "no declared default" means the type's zero, member by member.
    See `_zero_member_text` for what zero SPELLS per kind; note it is not simply an all-zero byte
    buffer decoded, because a zero name/object reference spells `None` rather than name-table
    index 0 (which is an ordinary name — `unrealed/package-format.md` "`FPoly.ItemName` — name
    index 0 is a REAL name")."""
    tp, members = struct_member_schema(pkg, prop, resolver=resolver, _pkgs=_pkgs)
    out: dict = {}
    for m in members:
        if m.kind == "StructProperty":
            sub = zero_struct_tree(tp, m, resolver=resolver, _pkgs=_pkgs, style=style)
            for k in member_keys(m):
                out[k] = sub
        else:
            text = _zero_member_text(m, tp, resolver=resolver, _pkgs=_pkgs, style=style)
            for k in member_keys(m):
                out[k] = text
    return out


def strip_member_tree(value_tree: dict, default_tree: dict) -> dict:
    """`value_tree` with every member equal to `default_tree`'s corresponding member REMOVED,
    recursively — the editor's own export rule.

    A nested struct is kept only when something inside it differs, and then only the differing
    members are kept, which is what makes `MainScale=(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)`
    come out right. A member absent from `default_tree` (the schemas disagree) is KEPT: stating a
    value that might have been droppable is harmless, whereas dropping one that differs is data
    loss."""
    kept: dict = {}
    for k, v in value_tree.items():
        d = default_tree.get(k)
        if isinstance(v, dict):
            sub = strip_member_tree(v, d if isinstance(d, dict) else {})
            if sub:
                kept[k] = sub
        elif v != d:
            kept[k] = v
    return kept


def render_member_tree(tree: dict) -> str:
    """A member tree as the `(A=…,B=(X=…))` text a T3D property line carries."""
    return "(" + ",".join(
        f"{k}=" + (render_member_tree(v) if isinstance(v, dict) else v)
        for k, v in tree.items()) + ")"


def member_keys(m: Prop) -> list[str]:
    """The rendered key(s) one struct member (or one array element property) contributes: `Name`
    for a scalar, `Name(0)`/`Name(1)`/… when the member is itself a STATIC array. The single
    definition of that suffixing, so every producer and consumer of the `(member, text)` pairs
    keys identically."""
    if m.array_dim > 1:
        return [f"{m.name}({i})" for i in range(m.array_dim)]
    return [m.name]


@_schema_guard
def _zero_member_text(m: Prop, members_pkg: Package, *, resolver, _pkgs: dict,
                      style: ValueStyle) -> str:
    if m.kind == "FloatProperty":
        return style.float_fmt(0.0)
    if m.kind == "IntProperty":
        return "0"
    if m.kind == "ByteProperty":
        return _byte_member_text(m, 0, members_pkg, resolver=resolver, _pkgs=_pkgs, style=style)
    if m.kind in ("ObjectProperty", "ClassProperty", "NameProperty"):
        return "None"
    if m.kind == "StrProperty":
        return ""
    if m.kind == "BoolProperty":
        return "False"
    if m.kind == "StructProperty":
        return render_member_tree(
            zero_struct_tree(members_pkg, m, resolver=resolver, _pkgs=_pkgs, style=style))
    raise SchemaError(f"unsupported struct member kind {m.kind} ({m.name})")


@_schema_guard
def decode_array_tag(pkg: Package, tag: PropertyTag, prop: Prop, *, resolver, _pkgs: dict,
                     style: ValueStyle = CLI_STYLE) -> list[str]:
    """A DYNAMIC array (`array<T> Foo`) property tag's value → the rendered text of each element.

    UE1 serializes `UArrayProperty` as a compact element COUNT followed by that many elements, each
    written by the ELEMENT property's own `SerializeItem` — the very same per-kind wire forms a
    struct's members use (`_decode_struct_bin_at`). So the decode is that decoder handed the element
    property repeated `count` times, which also brings its exact-consume integrity check.

    The element property comes from `prop.array_inner`: an ArrayProperty's own `type_ref` points at
    the element property OBJECT, so its `type_name` is that object's NAME and never its kind — the
    element kind exists nowhere else.

    (Distinct from a STATIC array `var int Foo[4]`, which is not one tag at all: the engine writes a
    separate tag per element, each carrying its own `array_index`.)"""
    if prop.kind != "ArrayProperty":
        raise SchemaError(f"{tag.name} is not a dynamic array (kind={prop.kind})")
    if prop.array_inner is None:
        raise SchemaError(f"cannot decode dynamic array {tag.name}: its element property "
                          f"(the ArrayProperty's Inner) did not resolve in {prop.owner}")
    count, pos = _read_compact_index(tag.raw, 0)
    if not (0 <= count <= 1 << 22):
        raise SchemaError(f"implausible element count {count} for dynamic array {tag.name}")
    declaring = _pkg_for_owner(prop.owner, pkg, resolver=resolver, _pkgs=_pkgs)
    pairs, pos = _decode_struct_bin_at(pkg, declaring, [prop.array_inner] * count, tag.raw, pos,
                                       resolver=resolver, _pkgs=_pkgs, style=style)
    if pos != len(tag.raw):
        raise SchemaError(f"dynamic array {tag.name} did not consume exactly "
                          f"({pos} != {len(tag.raw)} bytes)")
    return [v for _k, v in pairs]


@_schema_guard
def render_default_tag(pkg: Package, tag: PropertyTag, prop: Prop | None, *, resolver,
                       _pkgs: dict, style: ValueStyle = CLI_STYLE) -> str:
    """One defaults `PropertyTag` → its canonical CLI text (spec §4 forms). `pkg` is the
    package the tag was serialized in (its VALUE compacts resolve there); `prop` (the schema
    entry, if known) supplies enum naming + the struct type, whose refs resolve against the
    prop's DECLARING package.

    `style` picks the text form (CLI display vs UnrealEd's T3D) — see `ValueStyle`."""
    if tag.ptype == PT_BOOL:
        return "True" if tag.bool_value else "False"
    if tag.ptype == PT_BYTE:
        v = tag.raw[0]
        if prop is not None and prop.kind == "ByteProperty" and prop.type_ref != 0:
            dp = _pkg_for_owner(prop.owner, pkg, resolver=resolver, _pkgs=_pkgs)
            names = resolve_enum_names(prop, dp, resolver=resolver, _pkgs=_pkgs)
            if v < len(names):
                return names[v]
        return str(v)
    if tag.ptype == PT_INT:
        return str(int.from_bytes(tag.raw, "little", signed=True))
    if tag.ptype == PT_FLOAT:
        return style.float_fmt(struct.unpack("<f", tag.raw)[0])
    if tag.ptype == PT_OBJECT:
        ref, _ = _read_compact_index(tag.raw, 0)
        return render_object_ref(pkg, ref)
    if tag.ptype == PT_NAME:
        ni, _ = _read_compact_index(tag.raw, 0)
        return pkg.names[ni] if 0 <= ni < len(pkg.names) else "None"
    if tag.ptype in (PT_STR, PT_STR_LEGACY):
        if tag.ptype == PT_STR:
            s, _ = _read_fstring(tag.raw, 0)
        else:
            s = tag.raw.split(b"\x00", 1)[0].decode("latin-1")
        return s
    if tag.ptype == PT_STRUCT:
        if prop is None:
            raise SchemaError(f"cannot render struct default {tag.name} without its schema")
        # The FULL struct, every member stated. `mapimport` is the only caller that drops members
        # equal to the class default, and it does that itself via `strip_member_tree` — a rendered
        # default must state everything, because it IS the thing others compare against.
        return render_member_tree(struct_tag_member_tree(pkg, tag, prop, resolver=resolver,
                                                         _pkgs=_pkgs, style=style))
    raise SchemaError(f"unsupported default value type {tag.ptype} for {tag.name}")


@_schema_guard
def resolve_class_default_tags(fqcn: str, *, resolver, _pkgs: dict | None = None
                               ) -> dict[tuple[str, int], tuple[Package, PropertyTag]]:
    """The EFFECTIVE class defaults of `fqcn` as RAW tags: every ancestor's defaults block read and
    overlaid root→leaf (each block is a sparse diff against its super), keyed
    `(casefold(prop_name), array_index)` and valued `(package_the_tag_was_serialized_in, tag)` —
    the package matters because the tag's object/name compacts index THAT package's tables.

    This is the primitive `resolve_class_defaults` renders; it is public because a caller that needs
    the default MEMBER-WISE (`mapimport`'s struct member-strip) must decode the raw tag itself
    rather than re-parse a joined `(A=…,B=…)` string."""
    pkgs: dict = _pkgs if _pkgs is not None else {}
    chain: list[tuple[Package, str]] = []
    cur = fqcn
    seen: set[str] = set()
    while cur is not None and cur.casefold() not in seen:
        seen.add(cur.casefold())
        if "." not in cur:
            raise SchemaError(f"class must be fully qualified (Package.Class): {cur!r}")
        pkg_name, cls_name = cur.split(".", 1)
        if pkg_name not in pkgs:
            path = resolver(pkg_name)
            if path is None:
                raise SchemaError(f"cannot resolve defaults of {fqcn}: package {pkg_name!r} "
                                  "not found on the schema search path")
            pkgs[pkg_name] = load_package(path, name=pkg_name)
        pkg = pkgs[pkg_name]
        chain.append((pkg, cls_name))
        cur = _super_fqcn(pkg, cls_name)
    out: dict[tuple[str, int], tuple[Package, PropertyTag]] = {}
    for pkg, cls_name in reversed(chain):                # root first; leaf overrides
        for tag in class_default_tags(pkg, cls_name):
            out[(tag.name.casefold(), tag.array_index)] = (pkg, tag)
    return out


@_schema_guard
def resolve_class_defaults(fqcn: str, *, resolver, schema: dict | None = None,
                           _pkgs: dict | None = None,
                           style: ValueStyle = CLI_STYLE) -> dict[tuple[str, int], str]:
    """The EFFECTIVE class defaults of `fqcn`: every ancestor's defaults block decoded and
    overlaid root→leaf (each block is a sparse diff against its super — verified: `Engine.Light`
    re-states only what it changes vs `Actor`), rendered to canonical CLI text. Keys are
    `(casefold(prop_name), array_index)`. A prop absent here defaults to its type's ZERO (the
    caller synthesizes it — spec §2.3).

    `schema` (casefold name → Prop, the resolved leaf schema) supplies enum naming + struct
    member layouts; when None it is resolved here via the same `resolver`."""
    pkgs: dict = _pkgs if _pkgs is not None else {}
    if schema is None:
        schema = {p.name.casefold(): p
                  for p in resolve_class_properties(fqcn, resolver=resolver)}
    # Build the chain leaf→root, loading each package once (shared with the render cache).
    chain: list[tuple[Package, str]] = []
    cur = fqcn
    seen: set[str] = set()
    while cur is not None and cur.casefold() not in seen:
        seen.add(cur.casefold())
        if "." not in cur:
            raise SchemaError(f"class must be fully qualified (Package.Class): {cur!r}")
        pkg_name, cls_name = cur.split(".", 1)
        if pkg_name not in pkgs:
            path = resolver(pkg_name)
            if path is None:
                raise SchemaError(f"cannot resolve defaults of {fqcn}: package {pkg_name!r} "
                                  "not found on the schema search path")
            pkgs[pkg_name] = load_package(path, name=pkg_name)
        pkg = pkgs[pkg_name]
        chain.append((pkg, cls_name))
        cur = _super_fqcn(pkg, cls_name)
    out: dict[tuple[str, int], str] = {}
    for pkg, cls_name in reversed(chain):            # root first; leaf overrides
        for tag in class_default_tags(pkg, cls_name):
            prop = schema.get(tag.name.casefold())
            out[(tag.name.casefold(), tag.array_index)] = \
                render_default_tag(pkg, tag, prop, resolver=resolver, _pkgs=pkgs,
                                   style=style)
    return out
