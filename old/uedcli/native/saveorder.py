"""UED22 `MAP SAVE` name-table and import-table ORDER — the generative model.

Reverse-engineered from `core.dll UObject::SavePackage` (RVA 0x277c0; UT-era build) and
confirmed against four editor `MAP IMPORT` goldens + two live gdb traces (toysmall,
UNATCO) by the 2026-09-02 spike. Both tables are built the same way:

  1. COLLECT every entry in first-encounter creation order — names in `FName::Names`
     index order, imports in `GObjObjects` index order (= object creation order).
  2. COUNT references while serializing the export bodies (a per-entry INT counter):
       `FArchiveSaveTagImports::operator<<(FName&)`   -> NameCounts[name]++   (RVA 0x162e0)
       `FArchiveSaveTagImports::operator<<(UObject*&)`-> ObjCounts[obj]++ and recurse
                                                         into Obj->Outer     (RVA 0x161c0)
  3. SORT `appQsort` (0x315c0 -> MSVC CRT qsort 0x77cb0; median-of-3, CUTOFF 8, UNSTABLE)
     DESCENDING by that counter (comparators 0x230c0 names / 0x23080 imports).

The creation order (step 1) is reconstructed from level data with no oracle: a fixed
editor-boot prefix (`_saveorder_boot`), then the OBJ-LOADed packages, then the map-time
objects/names. `compute_tables` is the entry the writer calls.

Import order is byte-exact on all four goldens (toys + UNATCO). Name order is exact for
the boot + package regions and the toy levels; the UNATCO map-time region has a residual
placed-actor spawn sub-order (owner-excluded from the parity bar; see the spike report).
"""
from __future__ import annotations

import struct
from collections import defaultdict
from dataclasses import dataclass, field

from uedcli.upackage import (Package, load_package, read_compact_index,
                             read_fstring, read_property_tags)

from ._saveorder_boot import BOOT_NAMES, BOOT_OBJECT_PATHS

RF_HasStack = 0x02000000
PT_BYTE, PT_INT, PT_BOOL, PT_FLOAT, PT_OBJECT, PT_NAME, PT_ARRAY, PT_STRUCT, PT_STR = \
    1, 2, 3, 4, 5, 6, 9, 10, 13


# --------------------------------------------------------------------------- MSVC qsort

_CUTOFF = 8
_STKSIZ = 30


def _shortsort(a: list, lo: int, hi: int, comp) -> None:
    while hi > lo:
        maxi = lo
        p = lo + 1
        while p <= hi:
            if comp(a[p], a[maxi]) > 0:
                maxi = p
            p += 1
        a[maxi], a[hi] = a[hi], a[maxi]
        hi -= 1


def msvc_qsort(a: list, comp, lo: int = 0, hi: int | None = None) -> None:
    """Faithful port of the MSVC CRT `qsort` statically linked into UED22's core.dll
    (`appQsort` 0x315c0 -> 0x77cb0): median-of-3, CUTOFF=8 shortsort, explicit lo/hi
    stack. UNSTABLE — the exact tie order depends on the whole initial permutation."""
    if hi is None:
        hi = len(a) - 1
    if hi - lo + 1 < 2:
        return
    lostk = [0] * _STKSIZ
    histk = [0] * _STKSIZ
    stkptr = 0
    while True:
        size = hi - lo + 1
        if size <= _CUTOFF:
            _shortsort(a, lo, hi, comp)
        else:
            mid = lo + (size // 2)
            if comp(a[lo], a[mid]) > 0:
                a[lo], a[mid] = a[mid], a[lo]
            if comp(a[lo], a[hi]) > 0:
                a[lo], a[hi] = a[hi], a[lo]
            if comp(a[mid], a[hi]) > 0:
                a[mid], a[hi] = a[hi], a[mid]
            loguy = lo
            higuy = hi
            while True:
                if mid > loguy:
                    loguy += 1
                    while loguy < mid and comp(a[loguy], a[mid]) <= 0:
                        loguy += 1
                if mid <= loguy:
                    loguy += 1
                    while loguy <= hi and comp(a[loguy], a[mid]) <= 0:
                        loguy += 1
                higuy -= 1
                while higuy > mid and comp(a[higuy], a[mid]) > 0:
                    higuy -= 1
                if higuy < loguy:
                    break
                a[loguy], a[higuy] = a[higuy], a[loguy]
                if mid == higuy:
                    mid = loguy
            higuy += 1
            if mid < higuy:
                higuy -= 1
                while higuy > mid and comp(a[higuy], a[mid]) == 0:
                    higuy -= 1
            if mid >= higuy:
                higuy -= 1
                while higuy > lo and comp(a[higuy], a[mid]) == 0:
                    higuy -= 1
            if higuy - lo >= hi - loguy:
                if lo < higuy:
                    lostk[stkptr] = lo
                    histk[stkptr] = higuy
                    stkptr += 1
                if loguy < hi:
                    lo = loguy
                    continue
            else:
                if loguy < hi:
                    lostk[stkptr] = loguy
                    histk[stkptr] = hi
                    stkptr += 1
                if lo < higuy:
                    hi = higuy
                    continue
        stkptr -= 1
        if stkptr >= 0:
            lo = lostk[stkptr]
            hi = histk[stkptr]
            continue
        return


# --------------------------------------------------------------------------- ref counting

class Events:
    def __init__(self) -> None:
        self.names: defaultdict[int, int] = defaultdict(int)   # name idx -> count
        self.objs: defaultdict[int, int] = defaultdict(int)    # obj ref  -> direct count
        self.structs_seen: set[str] = set()

    def name(self, idx: int) -> None:
        self.names[idx] += 1

    def obj(self, ref: int) -> None:
        if ref != 0:
            self.objs[ref] += 1


def _ci(buf: bytes, pos: int) -> tuple[int, int]:
    return read_compact_index(buf, pos)


def _walk_props(pkg: Package, ev: Events, pos: int, end: int) -> int:
    name_idx = {n: i for i, n in enumerate(pkg.names)}
    tags, after = read_property_tags(pkg, pos, end)
    for t in tags:
        ev.name(name_idx[t.name])
        if t.ptype == PT_STRUCT:
            ev.name(name_idx[t.struct_name])
            ev.structs_seen.add(t.struct_name)
            if t.struct_name in ("PointRegion", "InventoryItem"):
                ref, _ = _ci(t.raw, 0)
                ev.obj(ref)
            elif t.struct_name == "InitialAllianceInfo":
                nidx, _ = _ci(t.raw, 0)
                ev.name(nidx)
            elif t.struct_name == "SNanoKeyInitStruct":
                nidx, p = _ci(t.raw, 0)
                ev.name(nidx)
                nidx, p = _ci(t.raw, p)
                ev.name(nidx)
        elif t.ptype == PT_OBJECT:
            ref, _ = _ci(t.raw, 0)
            ev.obj(ref)
        elif t.ptype == PT_NAME:
            nidx, _ = _ci(t.raw, 0)
            ev.name(nidx)
        elif t.ptype == PT_ARRAY:
            raise NotImplementedError(f"dynamic array property {t.name}")
    ev.name(name_idx["None"])
    return after


def _walk_stack(buf: bytes, ev: Events, pos: int) -> int:
    node, pos = _ci(buf, pos)
    ev.obj(node)
    statenode, pos = _ci(buf, pos)
    ev.obj(statenode)
    pos += 8 + 4
    if node != 0:
        _, pos = _ci(buf, pos)
    return pos


def _walk_model(pkg: Package, ev: Events, pos: int, end: int) -> int:
    buf = pkg.buf
    pos = _walk_props(pkg, ev, pos, end)
    pos += 25 + 16
    for _ in range(2):
        n, pos = _ci(buf, pos)
        pos += 12 * n
    n, pos = _ci(buf, pos)                              # Nodes
    for _ in range(n):
        pos += 16 + 8 + 1
        for _ in range(4):
            _, pos = _ci(buf, pos)
        for _ in range(5):
            _, pos = _ci(buf, pos)
        _, pos = _ci(buf, pos)
        pos += 8
    n, pos = _ci(buf, pos)                              # Surfs
    for _ in range(n):
        tex, pos = _ci(buf, pos)
        ev.obj(tex)
        pos += 4
        for _ in range(4):
            _, pos = _ci(buf, pos)
        _, pos = _ci(buf, pos)
        _, pos = _ci(buf, pos)
        pos += 4
        actor, pos = _ci(buf, pos)
        ev.obj(actor)
    n, pos = _ci(buf, pos)                              # Verts
    for _ in range(n):
        _, pos = _ci(buf, pos)
        _, pos = _ci(buf, pos)
    pos += 4
    nz = struct.unpack_from("<i", buf, pos)[0]; pos += 4
    for _ in range(nz):
        ref, pos = _ci(buf, pos)
        ev.obj(ref)
        pos += 16
    polys, pos = _ci(buf, pos)
    ev.obj(polys)
    n, pos = _ci(buf, pos)                              # LightMap
    for _ in range(n):
        pos += 4 + 12
        _, pos = _ci(buf, pos)
        _, pos = _ci(buf, pos)
        pos += 8 + 4
    n, pos = _ci(buf, pos); pos += n                    # LightBits
    n, pos = _ci(buf, pos); pos += 25 * n               # Bounds
    n, pos = _ci(buf, pos); pos += 4 * n                # LeafHulls
    n, pos = _ci(buf, pos)                              # Leaves
    for _ in range(n):
        _, pos = _ci(buf, pos)
        _, pos = _ci(buf, pos)
        _, pos = _ci(buf, pos)
        pos += 8
    n, pos = _ci(buf, pos)                              # Lights (e4)
    for _ in range(n):
        ref, pos = _ci(buf, pos)
        ev.obj(ref)
    pos += 8
    return pos


def _walk_polys(pkg: Package, ev: Events, pos: int, end: int) -> int:
    buf = pkg.buf
    pos = _walk_props(pkg, ev, pos, end)
    num = struct.unpack_from("<i", buf, pos)[0]; pos += 8
    for _ in range(num):
        nv, pos = _ci(buf, pos)
        pos += 48 + 12 * nv + 4
        actor, pos = _ci(buf, pos)
        ev.obj(actor)
        tex, pos = _ci(buf, pos)
        ev.obj(tex)
        item, pos = _ci(buf, pos)
        ev.name(item)
        _, pos = _ci(buf, pos)
        _, pos = _ci(buf, pos)
        pos += 4
    return pos


def _walk_level(pkg: Package, ev: Events, pos: int, end: int) -> int:
    buf = pkg.buf
    pos = _walk_props(pkg, ev, pos, end)
    num = struct.unpack_from("<i", buf, pos)[0]; pos += 8
    for _ in range(num):
        ref, pos = _ci(buf, pos)
        ev.obj(ref)
    for _ in range(4):
        _, pos = read_fstring(buf, pos)
    nops, pos = _ci(buf, pos)
    for _ in range(nops):
        _, pos = read_fstring(buf, pos)
    pos += 8
    model, pos = _ci(buf, pos)
    ev.obj(model)
    nrs, pos = _ci(buf, pos)
    for _ in range(nrs):
        pos += 4
        a, pos = _ci(buf, pos); ev.obj(a)
        b, pos = _ci(buf, pos); ev.obj(b)
        pos += 12 + 1
    pos += 4
    ref, pos = _ci(buf, pos); ev.obj(ref)
    for _ in range(16):
        ref, pos = _ci(buf, pos)
        ev.obj(ref)
    ntv, pos = _ci(buf, pos)
    for _ in range(ntv):
        _, pos = read_fstring(buf, pos)
        _, pos = read_fstring(buf, pos)
    return pos


def _class_name(pkg, i0: int) -> str | None:
    """Export class name; works for both `uedcli.upackage.Package` (object_class_name,
    1-based) and `pkg_write.ParsedPackage` (class_of_export, 0-based)."""
    fn = getattr(pkg, "object_class_name", None)
    return fn(i0 + 1) if fn is not None else pkg.class_of_export(i0)


def collect(pkg: Package) -> Events:
    """Recompute the tag-pass name/object counters from a saved package's export bodies
    (on-disk occurrences == tag-pass increments)."""
    ev = Events()
    for i, ex in enumerate(pkg.exports):
        cls = _class_name(pkg, i)
        ev.obj(ex["cls"])                              # Ar << It->Class
        pos, end = ex["soff"], ex["soff"] + ex["ssize"]
        if cls == "Model":
            pos = _walk_model(pkg, ev, pos, end)
        elif cls == "Polys":
            pos = _walk_polys(pkg, ev, pos, end)
        elif cls == "Level":
            pos = _walk_level(pkg, ev, pos, end)
        else:
            if ex["flags"] & RF_HasStack:
                pos = _walk_stack(pkg.buf, ev, pos)
            pos = _walk_props(pkg, ev, pos, end)
        if pos != end:
            raise ValueError(f"export {i+1} ({cls}) body not consumed: {pos} != {end}")
    return ev


def import_totals(pkg: Package, ev: Events) -> list[int]:
    """Per-import counter incl. outer-chain propagation (each import ref bumps every
    ancestor once)."""
    totals = [0] * len(pkg.imports)
    for ref, n in ev.objs.items():
        if ref >= 0:
            continue
        j = -ref - 1
        while True:
            totals[j] += n
            outer = pkg.imports[j][2]
            if outer >= 0:
                break
            j = -outer - 1
    return totals


# --------------------------------------------------------------------------- creation order

def package_creation_order(pkg_path: str, pkg_name: str) -> list[str]:
    """Full object creation order of one package load: LinkerRoot first, then every
    export in CreateExport order (index order, each export's outer chain created first).
    Lowercased `pkg.group.name` paths."""
    p = load_package(pkg_path, name=pkg_name)
    seq = [pkg_name.lower()]
    made = {0}

    def create(ref: int) -> None:
        if ref in made or ref <= 0:
            return
        create(p.exports[ref - 1]["outer"])
        made.add(ref)
        seq.append(p.object_path(ref).lower())
    for i in range(1, len(p.exports) + 1):
        create(i)
    return seq


def package_name_order(load_files: list[tuple[str, str]]) -> list[str]:
    """Name interning order across OBJ LOAD: per package (in load order), the LinkerRoot
    name then its FName table in file order."""
    out: list[str] = []
    for name, path in load_files:
        p = load_package(path, name=name)
        out.append(name)
        out.extend(p.names)
    return out


def boot_object_paths(referenced: set[str]) -> list[str]:
    """Editor-boot import objects (lowercased paths) in GObjObjects order, filtered to
    those the level references — the fixed boot artifact (`BOOT_OBJECT_PATHS`)."""
    out = [p for p in BOOT_OBJECT_PATHS if p in referenced]
    if "engine" in referenced and "engine" not in out:
        out.insert(0, "engine")
    return out


def import_creation_order(load_files: list[tuple[str, str]],
                          referenced: set[str],
                          boot_order: list[str]) -> list[str]:
    """Import-object creation order (lowercased paths), filtered to `referenced`:
    boot objects, then packages in load order with a ONE-STEP ROOT DELAY —
    root(P0); for i>=1 root(Pi) then contents(P(i-1)); finally contents(P(last))."""
    out = [b for b in boot_order if b in referenced]
    roots = [p.lower() for p, _ in load_files]
    contents = []
    for name, path in load_files:
        seq = package_creation_order(path, name)
        contents.append([x for x in seq[1:] if x in referenced])
    if roots:
        if roots[0] in referenced:
            out.append(roots[0])
        for i in range(1, len(roots)):
            if roots[i] in referenced:
                out.append(roots[i])
            out.extend(contents[i - 1])
        out.extend(contents[-1])
    return out


# --------------------------------------------------------------------------- table assembly

def _import_paths(pkg: Package) -> list[tuple[str, str, str, str, str]]:
    """Per import (in pkg order): (full path lower, class_package, class_name,
    object_name, outer path lower or "")."""
    out = []
    for j in range(len(pkg.imports)):
        cp, cn, outer, on = pkg.imports[j]
        chain = []
        k = j
        while True:
            chain.append(pkg.names[pkg.imports[k][3]])
            o = pkg.imports[k][2]
            if o >= 0:
                break
            k = -o - 1
        path = ".".join(reversed(chain)).lower()
        outer_path = ".".join(reversed(chain[1:])).lower() if len(chain) > 1 else ""
        out.append((path, pkg.names[cp], pkg.names[cn], pkg.names[on], outer_path))
    return out


import re as _re

_ACTOR_RE = _re.compile(r"^Begin Actor Class=(\S+) Name=(\S+)")
_BRUSH_RE = _re.compile(r"^\s*Begin Brush Name=(\S+)")
_ITEM_RE = _re.compile(r"^\s*Begin Polygon.*?\bItem=(\S+)")
_WORD_RE = _re.compile(r"[A-Za-z0-9_]+")


def _model_polys_map(pkg) -> dict[str, str]:
    """{Model export name -> its Polys export name} by reading each Model body's
    `field_0x54` (the Polys ref)."""
    out: dict[str, str] = {}
    buf = pkg.buf
    for i, ex in enumerate(pkg.exports):
        if _class_name(pkg, i) != "Model":
            continue
        pos = ex["soff"]
        _, pos = _ci(buf, pos)                          # UObject None
        pos += 41                                       # FBox + FSphere
        for _ in range(2):                              # Vectors, Points
            n, pos = _ci(buf, pos); pos += 12 * n
        n, pos = _ci(buf, pos)                          # Nodes
        for _ in range(n):
            pos += 25
            for _ in range(10):
                _, pos = _ci(buf, pos)
            pos += 8
        n, pos = _ci(buf, pos)                          # Surfs
        for _ in range(n):
            _, pos = _ci(buf, pos); pos += 4
            for _ in range(6):
                _, pos = _ci(buf, pos)
            pos += 4
            _, pos = _ci(buf, pos)
        n, pos = _ci(buf, pos)                          # Verts
        for _ in range(n):
            _, pos = _ci(buf, pos); _, pos = _ci(buf, pos)
        pos += 4                                        # NumSharedSides
        nz = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        for _ in range(nz):
            _, pos = _ci(buf, pos); pos += 16
        polys_ref, pos = _ci(buf, pos)                  # field_0x54
        pname = pkg.name_of_ref(polys_ref) if polys_ref else None
        if pname:
            out[pkg.names[ex["nm"]]] = pname
    return out


def _level_model_name(pkg) -> str | None:
    buf = pkg.buf
    li = next((i for i in range(len(pkg.exports)) if _class_name(pkg, i) == "Level"), None)
    if li is None:
        return None
    pos = pkg.exports[li]["soff"]
    _, pos = _ci(buf, pos)
    num = struct.unpack_from("<i", buf, pos)[0]; pos += 8
    for _ in range(num):
        _, pos = _ci(buf, pos)
    for _ in range(4):
        _, pos = read_fstring(buf, pos)
    nops, pos = _ci(buf, pos)
    for _ in range(nops):
        _, pos = read_fstring(buf, pos)
    pos += 8
    model_ref, pos = _ci(buf, pos)
    return pkg.name_of_ref(model_ref) if model_ref > 0 else None


def _name_value_set(pkg) -> set[str]:
    """FName TEXTs that occur as property VALUES (candidates for map-time interning)."""
    vals: set[str] = set()
    for i, ex in enumerate(pkg.exports):
        cls = _class_name(pkg, i)
        if cls in ("Model", "Polys", "Level"):
            continue
        pos, end = ex["soff"], ex["soff"] + ex["ssize"]
        if ex["flags"] & RF_HasStack:
            node, pos = _ci(pkg.buf, pos)
            _, pos = _ci(pkg.buf, pos)
            pos += 12
            if node != 0:
                _, pos = _ci(pkg.buf, pos)
        tags, _ = read_property_tags(pkg, pos, end)
        for t in tags:
            if t.ptype == PT_NAME:
                n, _ = _ci(t.raw, 0); vals.add(pkg.names[n])
            elif t.struct_name == "InitialAllianceInfo":
                n, _ = _ci(t.raw, 0); vals.add(pkg.names[n])
            elif t.struct_name == "SNanoKeyInitStruct":
                n, p = _ci(t.raw, 0); vals.add(pkg.names[n])
                n, _ = _ci(t.raw, p); vals.add(pkg.names[n])
    return vals


def map_name_sequence(dx_bytes: bytes, t3d_text: str) -> list[str]:
    """The map-time FName creation order for `compute_tables`'s `level_map_names`:
    level Model + Polys, the fresh builder brush `Brush1` (interned unconditionally at
    MAP-IMPORT init; kept only if referenced), then the T3D walk — actor names, then per
    actor its FName-valued props + brush model/Polys/`Item=` labels — then the viewport
    Cameras. Exact for the toy levels; the UNATCO placed-actor sub-order has a residual
    (owner-excluded from the parity bar)."""
    from .pkg_write import parse_package
    pkg = parse_package(dx_bytes)
    model_polys = _model_polys_map(pkg)
    name_values = _name_value_set(pkg)
    lvl_model = _level_model_name(pkg)

    seq: list[str] = []
    if lvl_model:
        seq.append(lvl_model)
        if lvl_model in model_polys:
            seq.append(model_polys[lvl_model])
    seq.append("Brush1")

    lines = t3d_text.splitlines()
    actors = []
    depth_start = aname = None
    for idx, ln in enumerate(lines):
        m = _ACTOR_RE.match(ln)
        if m:
            depth_start, aname = idx, m.group(2)
        elif ln.startswith("End Actor") and depth_start is not None:
            actors.append((aname, depth_start, idx))
            depth_start = None
    seq += [a for a, _, _ in actors]                     # pass 1: actor names
    for aname, s, e in actors:                           # pass 2: props + brush detail
        in_brush = False
        for ln in lines[s + 1:e]:
            mb = _BRUSH_RE.match(ln)
            if mb:
                in_brush = True
                seq.append(mb.group(1))
                if mb.group(1) in model_polys:
                    seq.append(model_polys[mb.group(1)])
                continue
            if ln.strip().startswith("End Brush"):
                in_brush = False
                continue
            mi = _ITEM_RE.match(ln)
            if mi:
                seq.append(mi.group(1))
                continue
            if in_brush or "=" not in ln:
                continue
            val = ln.split("=", 1)[1]

            def _quoted(m):
                for part in m.group(1).split(","):
                    if part in name_values:
                        seq.append(part)
                return ""
            val = _re.sub(r'"([^"]*)"', _quoted, val)
            for tok in _WORD_RE.findall(val):
                if tok in name_values:
                    seq.append(tok)
    cams = sorted((pkg.names[e["nm"]] for i, e in enumerate(pkg.exports)
                   if _class_name(pkg, i) == "Camera"),
                  key=lambda n: int(_re.sub(r"\D", "", n) or 0))
    seq += cams
    out, seen = [], set()
    for n in seq:
        if n not in seen:
            seen.add(n); out.append(n)
    return out


@dataclass
class TableSpec:
    """Computed name + import tables in final on-disk order, shaped so `_seed_tables`
    consumes it exactly like a parsed golden `Package`: `.names` is the name list in
    index order; `.imports` is (class_pkg_idx, class_name_idx, outer_ref, obj_name_idx)
    tuples whose name indices point into `.names` and whose `outer_ref` is the signed
    compact-index ref into this same import list."""
    names: list[str] = field(default_factory=list)
    imports: list[tuple[int, int, int, int]] = field(default_factory=list)


def compute_tables(dx_bytes: bytes, load_files: list[tuple[str, str]],
                   level_map_names: list[str]) -> TableSpec:
    """Compute the final name + import table order for a MAP SAVE, from a content-correct
    (insertion-order) package `dx_bytes`, the OBJ-LOAD manifest `load_files`
    [(pkg_name, file_path)], and the map-time name creation sequence `level_map_names`
    (level Model/Polys/builder-Brush + the T3D walk)."""
    from .pkg_write import parse_package
    pkg = parse_package(dx_bytes)
    ev = collect(pkg)

    # --- names: boot ++ per-package [root, FName table] ++ map-time, dedup, tagged, qsort ---
    tagged = set(pkg.names)
    seen: set[str] = set()
    initial_names: list[str] = []
    for n in BOOT_NAMES:
        if n in tagged and n not in seen:
            seen.add(n); initial_names.append(n)
    for n in package_name_order(load_files):
        if n in tagged and n not in seen:
            seen.add(n); initial_names.append(n)
    for n in level_map_names:
        if n in tagged and n not in seen:
            seen.add(n); initial_names.append(n)
    # any tagged name the model missed (keeps the set complete; benign for order)
    for n in pkg.names:
        if n not in seen:
            seen.add(n); initial_names.append(n)
    name_counts = {pkg.names[i]: ev.names.get(i, 0) for i in range(len(pkg.names))}
    names = initial_names[:]
    msvc_qsort(names, lambda a, b: name_counts[b] - name_counts[a])
    name_index = {n: i for i, n in enumerate(names)}

    # --- imports: creation order -> qsort desc by count; rebuild records into `names` ---
    info = _import_paths(pkg)
    referenced = {rec[0] for rec in info}
    boot = boot_object_paths(referenced)
    creation = import_creation_order(load_files, referenced, boot)
    cpos = {p: i for i, p in enumerate(creation)}
    totals = import_totals(pkg, ev)
    path_count = {info[j][0]: totals[j] for j in range(len(info))}
    by_path = {rec[0]: rec for rec in info}
    ordered_paths = sorted(referenced, key=lambda p: cpos.get(p, 10**9))
    msvc_qsort(ordered_paths, lambda a, b: path_count[b] - path_count[a])

    new_pos = {p: i for i, p in enumerate(ordered_paths)}
    imports: list[tuple[int, int, int, int]] = []
    for path in ordered_paths:
        _p, class_pkg, class_name, obj_name, outer_path = by_path[path]
        outer_ref = -(new_pos[outer_path] + 1) if outer_path else 0
        imports.append((name_index[class_pkg], name_index[class_name],
                        outer_ref, name_index[obj_name]))
    return TableSpec(names=names, imports=imports)
