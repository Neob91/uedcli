"""Reproduce UED22 `UCC.exe`'s `SavePackage` table ordering (name / import / export tables).

Reverse-engineered from `uned/UED22/core.dll` (ImageBase `0x10000000`). Full write-up and the
verification harness live in `dev/docs/board/to-build/uedcli-unrealscript-compiler` /
`dev/docs/unrealed/unrealscript/`. The mechanism:

`UObject::SavePackage` (@`0x277c0`) gathers each table then sorts it with `appQsort` (@`0x315c0`,
a thunk to the MSVC CRT `qsort` @`0x77cb0`) **descending by an integer key**; ties fall to that
qsort's own (unstable) order, seeded from the gather order:

  * exports : key = per-object reference count ; gather = object CREATION order (= parse order of
              the package's own objects). Fully reproducible from source — see `order_exports`.
  * imports : key = per-object reference count ; gather = engine GObjObjects (global) index.
  * names   : key = per-name reference count   ; gather = engine FName registration (global) index.

The keys are counts accumulated by the import-tagging pass (`FArchiveSaveTagImports`):
`operator<<(FName)` (@`0x162e0`) does `NameIndices[name]++`; `operator<<(UObject)` (@`0x161c0`)
does `ObjectIndices[obj]++` and, for an import, recurses into its outer chain. Both index arrays are
`AddZeroed` in the linker ctor (@`0x4a6f0`), so the key is a pure reference count.

STATUS. Export order is verified byte-exact vs UCC (see `test_uscript_ordering`). The name/import
COUNT keys are verified (they reproduce the count *tiers* of every sampled package exactly), but the
within-tier order needs the engine's global FName / GObjObjects index — a UED22 boot+load artifact
not derivable from the source under compilation. Supply it via `GlobalIndex` (extract once from the
booted editor); without it the tiers are correct but tied entries may be mis-permuted.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ── MSVC CRT qsort (core.dll @0x77cb0, reached via the appQsort thunk @0x315c0) ──
# Ported exactly from the MODERN MSVC `qsort.c` UED22 was built with (RE'd 2026-09-05 from the
# `.text` disassembly — NOT the classic K&R median-of-3): __shortsort (selection, max→hi) for
# runs ≤ 8, else median-of-3 with the median kept in place and a Hoare-style partition that skips
# the equal-key run on both sides. It is UNSTABLE — equal-key runs are permuted deterministically,
# and that permutation is part of the byte output — so the exact algorithm matters.
_CUTOFF = 8


def _shortsort(a: list, lo: int, hi: int, comp) -> None:
    while hi > lo:
        mx = lo
        for p in range(lo + 1, hi + 1):
            if comp(a[p], a[mx]) > 0:
                mx = p
        a[mx], a[hi] = a[hi], a[mx]
        hi -= 1


def msvc_qsort(seq, comp) -> list:
    """A faithful port of the modern MSVC CRT `qsort` UED22 sorts every package table with."""
    a = list(seq)
    n = len(a)
    if n < 2:
        return a
    stack: list[tuple[int, int]] = []
    lo, hi = 0, n - 1
    while True:
        size = hi - lo + 1
        if size <= _CUTOFF:
            _shortsort(a, lo, hi, comp)
        else:
            mid = lo + size // 2
            if comp(a[lo], a[mid]) > 0: a[lo], a[mid] = a[mid], a[lo]
            if comp(a[lo], a[hi]) > 0: a[lo], a[hi] = a[hi], a[lo]
            if comp(a[mid], a[hi]) > 0: a[mid], a[hi] = a[hi], a[mid]
            loguy, higuy = lo, hi
            while True:
                if mid > loguy:
                    while True:
                        loguy += 1
                        if not (loguy < mid and comp(a[loguy], a[mid]) <= 0): break
                if mid <= loguy:
                    while True:
                        loguy += 1
                        if not (loguy <= hi and comp(a[loguy], a[mid]) <= 0): break
                while True:
                    higuy -= 1
                    if not (higuy > mid and comp(a[higuy], a[mid]) > 0): break
                if higuy < loguy:
                    break
                a[loguy], a[higuy] = a[higuy], a[loguy]
                if mid == higuy:
                    mid = loguy
            higuy += 1
            if mid < higuy:
                while True:
                    higuy -= 1
                    if not (higuy > mid and comp(a[higuy], a[mid]) == 0): break
            if mid >= higuy:
                while True:
                    higuy -= 1
                    if not (higuy > lo and comp(a[higuy], a[mid]) == 0): break
            if higuy - lo >= hi - loguy:            # recurse the smaller half, stack the larger
                if lo < higuy: stack.append((lo, higuy))
                if loguy < hi:
                    lo = loguy; continue
            else:
                if loguy < hi: stack.append((loguy, hi))
                if lo < higuy:
                    hi = higuy; continue
        if not stack:
            break
        lo, hi = stack.pop()
    return a


# ── input model ────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, kw_only=True)
class ObjInput:
    """One object bound for the package — an export if `in_package`, else an import.

    `name` is a package-unique KEY (drives export ordering + `obj_refs`/`class_name`/`outer`
    resolution). `display` is the object's FName spelling for the NAME table (defaults to `name`);
    exports whose display name repeats across the package — a param `A` of two functions — need
    distinct keys but share a display. `name_refs` / `obj_refs` are the body's ordered `<<FName`
    (display names) and `<<UObject` (object KEYS or import display names) emission streams, which set
    the sort keys. `late_name_refs` are `<<FName` refs that register at a LATER compile point than the
    rest of the body — currently just a class's defaultproperties tag stream, compiled after every
    member/function in the source (RE'd from `RahnemBrushBuilders`'s `GroupName="Landscape"`); counted
    the same as `name_refs` but gathered in a separate trailing pass. `class_name`/`outer` are object
    display names (for name gather) or None."""
    name: str
    class_name: str
    outer: str | None
    in_package: bool
    display: str | None = None
    name_refs: tuple[str, ...] = ()
    obj_refs: tuple[str, ...] = ()
    late_name_refs: tuple[str, ...] = ()

    @property
    def disp(self) -> str:
        return self.display if self.display is not None else self.name


@dataclass(frozen=True, kw_only=True)
class GlobalIndex:
    """Tie-break gather order for count-equal entries. Maps a CASEFOLDED name to the engine's global
    registration index (lower = earlier); only relative order matters. Dumped once from the booted
    UED22 editor (`global_index.default_global_index`). A name absent from a map sorts after all
    present ones (a safe default for the package's own parse-order names, which register last)."""
    names: dict[str, int] = field(default_factory=dict)
    objects: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class Ordered:
    names: list[str]
    imports: list[str]
    exports: list[str]
    name_key: dict[str, int]
    obj_key: dict[str, int]


# ── the algorithm ────────────────────────────────────────────────────────────────────────────────
def order_package(objs: list[ObjInput], creation_order: list[str],
                  global_index: GlobalIndex | None = None,
                  name_creation: list[str] | None = None) -> Ordered:
    """Order a package's three tables. `creation_order` is the OBJECT creation order (drives the export
    gather). `name_creation` is the NAME-registration encounter order for own-new names (UCC's two-pass
    compile registers declarations before function-body locals, so it differs from object creation);
    it defaults to `creation_order`. `global_index` supplies the engine gather order for the
    import/name tie-break; omit it to get correct tiers with a best-effort tie order."""
    gi = global_index or GlobalIndex()
    by = {o.name: o for o in objs}
    tagexp = {o.name for o in objs if o.in_package}
    name_key, obj_key = _reference_counts(objs, creation_order, by, tagexp)

    def by_name_index(n: str) -> int:
        return gi.names.get(n.casefold(), 10**9)

    def by_obj_index(n: str) -> int:
        return gi.objects.get(n.casefold(), 10**9)

    # None is FName index 0 and stays IN the gather+sort (not special-cased out): its presence in the
    # array changes the unstable qsort's permutation of the count-tied names (RE'd from the name
    # gather @0x27ea0, which iterates GObjNames from index 0). Excluding it mis-permutes ties.
    gathered = _gather_names(objs, name_creation or creation_order, by)
    names = msvc_qsort(sorted(gathered, key=by_name_index),
                       lambda x, y: name_key.get(y, 0) - name_key.get(x, 0))

    exp_gather = [n for n in creation_order if n in tagexp]
    imp_gather = sorted((o.name for o in objs if not o.in_package), key=by_obj_index)
    exports = msvc_qsort(exp_gather, lambda x, y: obj_key.get(y, 0) - obj_key.get(x, 0))
    imports = msvc_qsort(imp_gather, lambda x, y: obj_key.get(y, 0) - obj_key.get(x, 0))
    return Ordered(names=names, imports=imports, exports=exports,
                   name_key=name_key, obj_key=obj_key)


def order_exports(objs: list[ObjInput], creation_order: list[str]) -> list[str]:
    """The export table order — reproducible from source with no global-index table."""
    return order_package(objs, creation_order).exports


def _reference_counts(objs, creation_order, by, tagexp):
    """Simulate the import-tag pass: per body, count each `<<FName` and each `<<UObject`
    (`operator<<(UObject)` recurses into an import's outer chain), then the explicit `<<Class`."""
    name_key: dict[str, int] = {}
    obj_key: dict[str, int] = {}

    def ser_obj(nm: str | None) -> None:
        if nm is None or nm == "None" or nm not in by:
            return
        obj_key[nm] = obj_key.get(nm, 0) + 1        # inc precedes the export/import test (0x161c0)
        o = by[nm]
        if o.name in tagexp:
            return                                   # export: no outer recursion
        if o.outer is not None:
            ser_obj(o.outer)

    for nm in creation_order:
        o = by.get(nm)
        if o is None or not o.in_package:
            continue
        for r in o.name_refs:
            name_key[r] = name_key.get(r, 0) + 1
        for r in o.late_name_refs:
            name_key[r] = name_key.get(r, 0) + 1
        for r in o.obj_refs:
            ser_obj(r)
        ser_obj(o.class_name)
    return name_key, obj_key


def _gather_names(objs, creation_order, by):
    """Names entering the table (name-flag pass @0x27bdb): each tagged object's Name and Outer.Name,
    plus every `<<FName`-referenced name in its body — gathered AT the point its referencing object is
    processed, not deferred to a trailing pass. A value-only name (never an object's own name in this
    package — a package self-ref stashed in `PackageImports`, a `Category` string, …) registers when
    the declaration that emits it is processed, same as UCC's compiler interning it inline; RE'd from
    `RahnemBrushBuilders` (package self-name sorts immediately before the first `var()` it precedes in
    golden, not after the whole class body). `late_name_refs` (the defaultproperties tag stream) is a
    SECOND, later registration point — the whole block compiles after every member/function in the
    source, so it gathers in its own trailing pass, after the main walk (also RE'd from
    `RahnemBrushBuilders`: `GroupName="Landscape"` sorts after a function param declared later in
    source than the property it defaults). Only relative order among names absent from `global_index`
    matters — anything with a real global index is re-sorted by that below regardless of gather
    position."""
    seen: list[str] = []

    def add(n: str | None) -> None:
        if n is not None and n not in seen:
            seen.append(n)

    add("None")
    for nm in creation_order:
        o = by.get(nm)
        if o is None:
            continue
        add(o.disp)
        add(o.outer)
        for r in o.name_refs:
            add(r)
    # Imports are not in creation_order but their Name/Outer and Class.Name/Class.Outer are gathered
    # too (the flag pass walks the whole object array). Stock names re-sort by global index below, so
    # the order they enter here is irrelevant; only their presence is.
    for o in objs:
        if o.in_package:
            continue
        add(o.disp)
        add(o.outer)
        add(o.class_name)
        co = by.get(o.class_name)
        if co is not None:
            add(co.outer)
    for nm in creation_order:
        o = by.get(nm)
        if o is None:
            continue
        for r in o.late_name_refs:
            add(r)
    return seen
