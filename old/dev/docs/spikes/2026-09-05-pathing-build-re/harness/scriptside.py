#!/usr/bin/env python3
"""Script-side facts for the pathing spike (findings/30-script-side.md), read offline from the `.u`
and `.dx` bytes via `uedcli.uprops` / `uedcli.upackage`.

  scriptside.py tree <ued|dx>                 NavigationPoint family: class tree, own props+flags, defaults
  scriptside.py defaults <ued|dx> <Pkg.Class> [regex]   effective (inherited) defaults of one class
  scriptside.py disk <map.dx> [--class C] [--limit N] [--hex NAME]   on-disk NavPt tags + ReachSpec cross-check
  scriptside.py calls <ued|dx> <Package> [regex]        functions whose bytecode calls the pathing natives
  scriptside.py census [maps…]                          per-map bAutoBuilt / InventorySpot / WarpZoneMarker counts
"""
from __future__ import annotations

import glob
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import GAME as _GAME, UED22 as _UED22  # noqa: E402
from uedcli.upackage import (load_package, read_compact_index, read_fstring, read_property_tags,  # noqa: E402
                             PT_BOOL, PT_INT, PT_FLOAT, PT_OBJECT, PT_NAME, PT_BYTE, PT_STRUCT)
from uedcli.uprops import ufield                                                                 # noqa: E402
from uedcli.uprops.uclass import (class_children_ref, class_default_tags, class_export_index,   # noqa: E402
                                  iter_classes, _super_fqcn)
from uedcli.uprops.ufield import _decode_property, _field_next, _skip_script                     # noqa: E402
from uedcli.uprops.base import PROPERTY_TYPES                                                    # noqa: E402
from uedcli.uprops.values import resolve_class_defaults, T3D_STYLE                               # noqa: E402

SYSDIRS = {"ued": _UED22, "dx": _GAME / "System"}
MAPS = _GAME / "Maps"
RF_HasStack = 0x02000000

CPF = [(0x1, "Edit"), (0x2, "Const"), (0x4, "Input"), (0x8, "ExportObject"), (0x10, "OptionalParm"),
       (0x20, "Net"), (0x40, "ConstRef"), (0x80, "Parm"), (0x100, "OutParm"), (0x200, "SkipParm"),
       (0x400, "ReturnParm"), (0x800, "CoerceParm"), (0x1000, "Native"), (0x2000, "Transient"),
       (0x4000, "Config"), (0x8000, "Localized"), (0x10000, "Travel"), (0x20000, "EditConst"),
       (0x40000, "GlobalConfig"), (0x100000, "OnDemand"), (0x200000, "New"), (0x400000, "NeedCtorLink")]
FUNC = [(0x1, "Final"), (0x2, "Defined"), (0x4, "Iterator"), (0x8, "Latent"), (0x10, "PreOperator"),
        (0x20, "Singular"), (0x40, "Net"), (0x80, "NetReliable"), (0x100, "Simulated"), (0x200, "Exec"),
        (0x400, "Native"), (0x800, "Event"), (0x1000, "Operator"), (0x2000, "Static"), (0x4000, "NoExport"),
        (0x8000, "Const"), (0x10000, "Invariant")]

_pkgs: dict[tuple[str, str], object] = {}


def pkg_path(which: str, name: str) -> str | None:
    hits = [p for p in SYSDIRS[which].iterdir() if p.name.casefold() == f"{name.casefold()}.u"]
    return str(hits[0]) if hits else None


def pkg_for(which: str, name: str):
    key = (which, name.casefold())
    if key not in _pkgs:
        path = pkg_path(which, name)
        if path is None:
            sys.exit(f"package {name} not found in {SYSDIRS[which]}")
        _pkgs[key] = load_package(path, name=name)
    return _pkgs[key]


def flag_names(v: int, table) -> str:
    return "|".join(n for m, n in table if v & m) or "-"


def own_props_in_order(pkg, class_name: str, owner: str):
    ci = class_export_index(pkg, class_name)
    node = class_children_ref(pkg, ci)
    out = []
    while node > 0:
        e = pkg.exports[node - 1]
        if pkg.name_of_ref(e["cls"]) in PROPERTY_TYPES:
            out.append(_decode_property(pkg, node, owner))
        node = _field_next(pkg, node)
    return out


def chain(which: str, fqcn: str) -> list[str]:
    out = []
    cur = fqcn
    while cur is not None:
        out.append(cur)
        p, c = cur.split(".", 1)
        cur = _super_fqcn(pkg_for(which, p), c)
    return out


# ── tree ────────────────────────────────────────────────────────────────────────────────────────

def nav_family(which: str) -> list[str]:
    fam = []
    for path in sorted(SYSDIRS[which].glob("*.u"), key=lambda p: p.name.casefold()):
        pkg = pkg_for(which, path.stem)
        for cls in iter_classes(pkg):
            fq = f"{pkg.name}.{cls}"
            try:
                ch = chain(which, fq)
            except SystemExit:
                continue
            if "Engine.NavigationPoint" in ch[1:] or fq == "Engine.NavigationPoint":
                fam.append(fq)
    return fam


def render_defaults(which: str, fqcn: str, keys: list[str] | None = None, pat=None) -> list[str]:
    d = resolve_class_defaults(fqcn, resolver=lambda n: pkg_path(which, n), style=T3D_STYLE)
    rows = []
    for (k, idx), v in sorted(d.items()):
        if keys is not None and k not in keys:
            continue
        if pat is not None and not pat.search(k):
            continue
        rows.append(f"{k}{'(' + str(idx) + ')' if idx else ''}={v}")
    return rows


KEY_DEFAULTS = ["bcollidewhenplacing", "collisionradius", "collisionheight", "bhiddened", "bstatic",
                "bnodelete", "drawtype", "extracost", "bautobuilt", "bendpoint", "bendpointonly",
                "bspecialcost", "bplayeronly", "bonewaypath", "bneverusestrafing", "btwoway", "cost",
                "bcollideactors", "bcollideworld", "bblockactors", "bblockplayers", "bdirectional",
                "texture", "sprite", "physics", "bmovable", "bhidden", "bstasis", "bignore"]


def cmd_tree(which: str):
    fam = nav_family(which)
    print(f"; {which}: {len(fam)} classes in the NavigationPoint family")
    for fq in fam:
        ch = chain(which, fq)
        pkg_name, cls = fq.split(".", 1)
        pkg = pkg_for(which, pkg_name)
        print(f"\n== {fq}  super={ch[1] if len(ch) > 1 else None}")
        for p in own_props_in_order(pkg, cls, fq):
            dim = f"[{p.array_dim}]" if p.array_dim > 1 else ""
            t = p.kind.replace("Property", "") + (f"<{p.type_name}>" if p.type_name else "")
            cat = f" cat={p.category}" if p.category else ""
            print(f"   var {p.name}{dim:<5} {t:<28} flags={p.property_flags:#x} {flag_names(p.property_flags, CPF)}{cat}")
        own = class_default_tags(pkg, cls)
        print("   own defaults:", ", ".join(
            f"{t.name}{'(' + str(t.array_index) + ')' if t.array_index else ''}="
            f"{t.bool_value if t.ptype == PT_BOOL else t.raw.hex()}" for t in own) or "(none)")
        print("   effective:", " ".join(render_defaults(which, fq, KEY_DEFAULTS)))


def cmd_defaults(which: str, fqcn: str, rx: str | None):
    pat = re.compile(rx, re.I) if rx else None
    for r in render_defaults(which, fqcn, None, pat):
        print(r)


# ── disk ────────────────────────────────────────────────────────────────────────────────────────

def parse_level(p):
    li = next(i for i, e in enumerate(p.exports) if p.name_of_ref(e["cls"]) == "Level")
    e = p.exports[li]
    buf, pos, end = p.buf, e["soff"], e["soff"] + e["ssize"]
    _t, pos = read_property_tags(p, pos, end)
    num, _mx = struct.unpack_from("<ii", buf, pos); pos += 8
    refs = []
    for _ in range(num):
        r, pos = read_compact_index(buf, pos); refs.append(r)
    for _ in range(4):
        _s, pos = read_fstring(buf, pos)
    opc, pos = read_compact_index(buf, pos)
    for _ in range(opc):
        _s, pos = read_fstring(buf, pos)
    pos += 8
    _model, pos = read_compact_index(buf, pos)
    n, pos = read_compact_index(buf, pos)
    specs = []
    for _ in range(n):
        dist = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        s, pos = read_compact_index(buf, pos)
        d, pos = read_compact_index(buf, pos)
        R, H, fl = struct.unpack_from("<iii", buf, pos); pos += 12
        pr = buf[pos]; pos += 1
        specs.append((dist, s, d, R, H, fl, pr))
    return refs, specs


def is_navpt(p, cls_ref: int, cache: dict) -> bool:
    """Class ref (an import in a map) → is it in the NavigationPoint family, per the GAME's .u."""
    if cls_ref in cache:
        return cache[cls_ref]
    path = p.object_path(cls_ref)
    ok = False
    if path and "." in path:
        try:
            ok = "Engine.NavigationPoint" in chain("dx", path)
        except (SystemExit, Exception):
            ok = False
    cache[cls_ref] = ok
    return ok


def actor_tags(p, ex_idx1: int):
    e = p.exports[ex_idx1 - 1]
    buf, pos, end = p.buf, e["soff"], e["soff"] + e["ssize"]
    if e["flags"] & RF_HasStack:
        node, pos = read_compact_index(buf, pos)
        _sn, pos = read_compact_index(buf, pos)
        pos += 12
        if node != 0:
            _off, pos = read_compact_index(buf, pos)
    start = pos
    tags, pos = read_property_tags(p, pos, end)
    return tags, start, pos, end


def tag_value(p, t):
    if t.ptype == PT_BOOL:
        return str(t.bool_value)
    if t.ptype == PT_INT:
        return str(struct.unpack("<i", t.raw)[0])
    if t.ptype == PT_FLOAT:
        return repr(struct.unpack("<f", t.raw)[0])
    if t.ptype == PT_BYTE:
        return str(t.raw[0])
    if t.ptype in (PT_OBJECT,):
        r, _ = read_compact_index(t.raw, 0)
        return f"{p.name_of_ref(r)}({r})"
    if t.ptype == PT_NAME:
        r, _ = read_compact_index(t.raw, 0)
        return f"'{p.names[r]}'"
    if t.ptype == PT_STRUCT and t.struct_name == "Vector":
        return "(%g,%g,%g)" % struct.unpack("<fff", t.raw)
    return t.raw.hex()


def cmd_disk(argv):
    mp = argv[0]
    want_cls = None; limit = 6; hexname = None
    i = 1
    while i < len(argv):
        if argv[i] == "--class": want_cls = argv[i + 1]; i += 2
        elif argv[i] == "--limit": limit = int(argv[i + 1]); i += 2
        elif argv[i] == "--hex": hexname = argv[i + 1]; i += 2
        else: sys.exit(f"bad arg {argv[i]}")
    p = load_package(mp)
    refs, specs = parse_level(p)
    print(f"; {mp}: Actors={len(refs)} ReachSpecs={len(specs)}")
    cache = {}
    navs = [r for r in refs if r > 0 and is_navpt(p, p.exports[r - 1]["cls"], cache)]
    print(f"; NavigationPoint-family actors on the roster: {len(navs)}")
    shown = 0
    for r in navs:
        e = p.exports[r - 1]
        name = p.names[e["nm"]]; cls = p.name_of_ref(e["cls"])
        if want_cls and cls != want_cls and name != want_cls:
            continue
        if shown >= limit:
            break
        shown += 1
        tags, start, pos, end = actor_tags(p, r)
        print(f"\n== {name} class={cls} export#{r - 1} soff={e['soff']:#x} ssize={e['ssize']} props@{start:#x}..{pos:#x}")
        for t in tags:
            ai = f"({t.array_index})" if t.array_index else ""
            print(f"   {t.name}{ai} = {tag_value(p, t)}")
        # cross-check Paths / upstreamPaths / PrunedPaths → ReachSpecs
        for arr, side in (("Paths", 1), ("upstreamPaths", 2), ("PrunedPaths", None)):
            for t in tags:
                if t.name == arr:
                    idx = struct.unpack("<i", t.raw)[0]
                    if 0 <= idx < len(specs):
                        sp = specs[idx]
                        okS = sp[1] == r; okE = sp[2] == r
                        ok = okS if side == 1 else okE if side == 2 else (okS or okE)
                        print(f"   check {arr}({t.array_index})={idx}: spec Start={p.name_of_ref(sp[1])} End={p.name_of_ref(sp[2])} "
                              f"dist={sp[0]} R={sp[3]} H={sp[4]} flags={sp[5]:#x} pruned={sp[6]} -> {'OK' if ok else 'MISMATCH'}")
                    else:
                        print(f"   check {arr}({t.array_index})={idx}: OUT OF RANGE")
        # reverse: specs naming this actor not in its arrays
        out_idx = {struct.unpack('<i', t.raw)[0] for t in tags if t.name == 'Paths'}
        in_idx = {struct.unpack('<i', t.raw)[0] for t in tags if t.name == 'upstreamPaths'}
        pr_idx = {struct.unpack('<i', t.raw)[0] for t in tags if t.name == 'PrunedPaths'}
        miss_out = [i for i, s in enumerate(specs) if s[1] == r and i not in out_idx | pr_idx]
        miss_in = [i for i, s in enumerate(specs) if s[2] == r and i not in in_idx]
        print(f"   reverse: specs with Start=this not in Paths∪PrunedPaths: {miss_out}; specs with End=this not in upstreamPaths: {miss_in}")
        if hexname and name == hexname:
            print(f"   hex[{start:#x}:{pos:#x}]:")
            b = p.buf[start:pos]
            for o in range(0, len(b), 32):
                print(f"   {start + o:#08x}: {b[o:o + 32].hex(' ')}")
            print("   names:", {n: i for i, n in enumerate(p.names) if n in {t.name for t in tags} | {'None'}})


# ── calls ───────────────────────────────────────────────────────────────────────────────────────

def function_meta(pkg, ex1: int):
    """(iNative, FunctionFlags, script_start, script_size) of a Function export."""
    e = pkg.exports[ex1 - 1]
    buf, p = pkg.buf, e["soff"]
    _t, p = read_property_tags(pkg, p, e["soff"] + e["ssize"])
    for _ in range(5):                                 # Super, Next, ScriptText, Children, FriendlyName
        _v, p = read_compact_index(buf, p)
    p += 8
    ssz = struct.unpack_from("<I", buf, p)[0]; p += 4
    script_start = p
    p = _skip_script(pkg, p, ssz)
    # v>=64 UFunction trailer: iNative u16, OperPrecedence u8, FunctionFlags u32 (+ u16 RepOffset if FUNC_Net)
    inative, _prec, fflags = struct.unpack_from("<HBI", buf, p)
    return inative, fflags, script_start, ssz


def outer_path(pkg, ex1: int) -> str:
    parts = []
    cur = ex1
    while cur > 0:
        e = pkg.exports[cur - 1]
        parts.append(pkg.names[e["nm"]])
        cur = e["outer"]
    return ".".join(reversed(parts))


TARGETS = ["FindPathToward", "FindPathTo", "actorReachable", "pointReachable", "ReachablePathnodes",
           "ComputePathnodeDistances", "AIDirectionReachable", "ClearPaths", "MoveTo", "MoveToward",
           "PickWallAdjust", "WaitForLanding", "SpecialCost", "Accept", "Generate", "ForceGenerate",
           "FindRandomDest", "FindBestInventoryPath", "AIPickRandomDestination", "AIDirectionalReachable",
           "EAdjustJump", "CanSee", "LineOfSightTo", "PathNode", "PatrolPoint", "NextPatrolPoint", "Nextpatrol"]


def cmd_calls(which: str, pkg_name: str, rx: str | None):
    pat = re.compile(rx, re.I) if rx else re.compile("|".join(TARGETS), re.I)
    # native index → name across Engine + this package
    natives: dict[int, str] = {}
    for pn in ("Core", "Engine", pkg_name):
        pk = pkg_for(which, pn)
        for i, e in enumerate(pk.exports):
            if pk.name_of_ref(e["cls"]) == "Function":
                try:
                    inat, ffl, _s, _z = function_meta(pk, i + 1)
                except Exception:
                    continue
                if inat:
                    natives[inat] = f"{outer_path(pk, i + 1)}"
    pkg = pkg_for(which, pkg_name)
    hits: list[tuple[str, str]] = []
    orig = ufield._walk_expr

    def spy(pk, pos, mem):
        buf = pk.buf
        tok = buf[pos]
        if tok >= 0x70:
            hits.append(("native", natives.get(tok, f"native#{tok}")))
        elif tok >= 0x60:
            idx = ((tok - 0x60) << 8) | buf[pos + 1]
            hits.append(("native", natives.get(idx, f"native#{idx}")))
        elif tok in (0x1B, 0x38):
            v, _ = read_compact_index(buf, pos + 1)
            hits.append(("virtual" if tok == 0x1B else "global", pk.names[v]))
        elif tok == 0x1C:
            v, _ = read_compact_index(buf, pos + 1)
            hits.append(("final", pk.object_path(v) or str(v)))
        return orig(pk, pos, mem)

    ufield._walk_expr = spy
    try:
        for i, e in enumerate(pkg.exports):
            if pkg.name_of_ref(e["cls"]) != "Function":
                continue
            hits.clear()
            try:
                inat, ffl, _s, _z = function_meta(pkg, i + 1)
            except Exception as ex:
                print(f"!! {outer_path(pkg, i + 1)}: {ex}")
                continue
            calls = sorted({f"{k}:{n}" for k, n in hits if pat.search(n.rsplit('.', 1)[-1])})
            if calls:
                print(f"{outer_path(pkg, i + 1)} [{flag_names(ffl, FUNC)}{', native#' + str(inat) if inat else ''}] -> {' '.join(calls)}")
    finally:
        ufield._walk_expr = orig


def cmd_decls(which: str, pkg_name: str, rx: str):
    """Declarations (flags + native index) of functions matching rx, with their owning class."""
    pat = re.compile(rx, re.I)
    pkg = pkg_for(which, pkg_name)
    for i, e in enumerate(pkg.exports):
        if pkg.name_of_ref(e["cls"]) != "Function":
            continue
        nm = pkg.names[e["nm"]]
        if not pat.search(nm):
            continue
        inat, ffl, _s, ssz = function_meta(pkg, i + 1)
        print(f"{outer_path(pkg, i + 1)}  flags={ffl:#x} {flag_names(ffl, FUNC)}  iNative={inat} scriptsize={ssz}")


# ── census ──────────────────────────────────────────────────────────────────────────────────────

def cmd_census(maps: list[str]):
    paths = maps or sorted(glob.glob(str(MAPS / "*.dx")))
    print("map | actors | reachspecs | navpts | bAutoBuilt=True | InventorySpot | WarpZoneMarker | Inventory actors | WarpZoneInfo | on-disk path tags (Paths/upstream/Pruned/VisNoReach/cost/ExtraCost/bEndPoint/bSpecialCost/bPlayerOnly/bOneWayPath/bTwoWay)")
    for mp in paths:
        p = load_package(mp)
        try:
            refs, specs = parse_level(p)
        except Exception as ex:
            print(f"{Path(mp).name}: !! {ex}")
            continue
        cache = {}
        counts = dict(auto=0, inv=0, wzm=0, navs=0, invactors=0, wzi=0)
        tagnames: dict[str, int] = {}
        for r in refs:
            if r <= 0:
                continue
            e = p.exports[r - 1]
            cls = p.name_of_ref(e["cls"])
            path = p.object_path(e["cls"]) or ""
            try:
                ch = chain("dx", path) if "." in path else []
            except Exception:
                ch = []
            if "Engine.Inventory" in ch:
                counts["invactors"] += 1
            if cls == "WarpZoneInfo":
                counts["wzi"] += 1
            if not is_navpt(p, e["cls"], cache):
                continue
            counts["navs"] += 1
            if cls == "InventorySpot":
                counts["inv"] += 1
            if cls == "WarpZoneMarker":
                counts["wzm"] += 1
            tags, _s, _p, _e = actor_tags(p, r)
            for t in tags:
                if t.name == "bAutoBuilt" and t.bool_value:
                    counts["auto"] += 1
                if t.name in ("Paths", "upstreamPaths", "PrunedPaths", "VisNoReachPaths", "cost", "ExtraCost",
                              "bEndPoint", "bSpecialCost", "bPlayerOnly", "bOneWayPath", "bTwoWay", "bAutoBuilt",
                              "visitedWeight", "bestPathWeight", "nextNavigationPoint", "startPath", "previousPath",
                              "RouteCache", "taken", "ownerTeam", "nextOrdered", "prevOrdered", "bEndPointOnly",
                              "bNeverUseStrafing"):
                    tagnames[t.name] = tagnames.get(t.name, 0) + 1
        print(f"{Path(mp).name} | {len(refs)} | {len(specs)} | {counts['navs']} | {counts['auto']} | {counts['inv']} | "
              f"{counts['wzm']} | {counts['invactors']} | {counts['wzi']} | {tagnames}")


def cmd_xcheck(mp: str):
    """Every ReachSpec vs the per-node arrays: is spec i in Start.Paths / Start.PrunedPaths / End.upstreamPaths?"""
    from collections import Counter
    p = load_package(mp)
    refs, specs = parse_level(p)
    cache = {}
    navs = [r for r in refs if r > 0 and is_navpt(p, p.exports[r - 1]["cls"], cache)]
    arr = {}
    for r in navs:
        tags, _a, _b, _c = actor_tags(p, r)
        d = {"Paths": set(), "upstreamPaths": set(), "PrunedPaths": set()}
        for t in tags:
            if t.name in d:
                d[t.name].add(struct.unpack("<i", t.raw)[0])
        arr[r] = d
    c = Counter()
    for i, sp in enumerate(specs):
        a = arr.get(sp[1]); b = arr.get(sp[2])
        c[(bool(a and i in a["Paths"]), bool(a and i in a["PrunedPaths"]), bool(b and i in b["upstreamPaths"]), sp[6])] += 1
    print(f"; {Path(mp).name}: specs={len(specs)} navpts={len(navs)}")
    print("(in Start.Paths, in Start.PrunedPaths, in End.upstreamPaths, bPruned) -> count")
    for k, v in sorted(c.items()):
        print("  ", k, v)
    print("max Paths+Pruned per node:", max(len(d["Paths"]) + len(d["PrunedPaths"]) for d in arr.values()),
          "max Paths:", max(len(d["Paths"]) for d in arr.values()),
          "max Pruned:", max(len(d["PrunedPaths"]) for d in arr.values()),
          "max upstream:", max(len(d["upstreamPaths"]) for d in arr.values()))
    starts = [sp[1] for sp in specs]
    runs = sum(1 for i in range(1, len(starts)) if starts[i] != starts[i - 1]) + 1
    print(f"specs grouped by Start: {runs} runs for {len(set(starts))} distinct starts")
    # nodes whose arrays are full: how many specs start there
    full = [(p.name_of_ref(r), len(d['Paths']) + len(d['PrunedPaths']), sum(1 for sp in specs if sp[1] == r))
            for r, d in arr.items() if len(d["Paths"]) + len(d["PrunedPaths"]) >= 16]
    print("nodes with Paths+Pruned==16 (name, arr, specs starting there):", full[:8], "…", len(full), "total")
    # nextNavigationPoint on disk vs roster order (does each node point at the PREVIOUS nav actor on the roster?)
    prev = 0; ok = bad = 0
    for r in navs:
        tags, _a, _b, _c = actor_tags(p, r)
        nn = [read_compact_index(t.raw, 0)[0] for t in tags if t.name == "nextNavigationPoint"]
        if nn:
            ok += nn[0] == prev; bad += nn[0] != prev
        prev = r
    print(f"nextNavigationPoint == previous nav actor on the roster: {ok} yes / {bad} no; first nav actor {p.name_of_ref(navs[0])}")
    # LevelInfo tags
    li = refs[0]
    tags, _a, _b, _c = actor_tags(p, li)
    print("LevelInfo0 tags:", ", ".join(f"{t.name}={tag_value(p, t)}" for t in tags))


def cmd_who(mp: str, tagname: str):
    """Actors (name, class) carrying tag `tagname` on disk, with its value."""
    p = load_package(mp)
    refs, _specs = parse_level(p)
    cache = {}
    for r in refs:
        if r <= 0 or not is_navpt(p, p.exports[r - 1]["cls"], cache):
            continue
        tags, _a, _b, _c = actor_tags(p, r)
        for t in tags:
            if t.name == tagname:
                e = p.exports[r - 1]
                print(f"{p.names[e['nm']]} ({p.name_of_ref(e['cls'])}) {tagname}({t.array_index})={tag_value(p, t)}")


def cmd_refs(which: str, pkg_name: str, rx: str):
    """Functions whose bytecode references a PROPERTY matching rx (instance/default variable reads or writes)."""
    pat = re.compile(rx, re.I)
    pkg = pkg_for(which, pkg_name)
    hits: list[str] = []
    orig = ufield._walk_expr

    def spy(pk, pos, mem):
        tok = pk.buf[pos]
        if tok in (0x00, 0x01, 0x02, 0x36):          # Local/Instance/DefaultVariable/StructMember: obj ref
            v, _ = read_compact_index(pk.buf, pos + 1)
            nm = pk.name_of_ref(v)
            if nm and pat.search(nm):
                hits.append(f"{pk.object_path(v)}")
        return orig(pk, pos, mem)

    ufield._walk_expr = spy
    try:
        for i, e in enumerate(pkg.exports):
            if pkg.name_of_ref(e["cls"]) != "Function":
                continue
            hits.clear()
            try:
                _inat, ffl, _s, _z = function_meta(pkg, i + 1)
            except Exception as ex:
                print(f"!! {outer_path(pkg, i + 1)}: {ex}")
                continue
            if hits:
                print(f"{outer_path(pkg, i + 1)} [{flag_names(ffl, FUNC)}] -> {' '.join(sorted(set(hits)))}")
    finally:
        ufield._walk_expr = orig


def main(argv):
    cmd = argv[0]
    if cmd == "xcheck":
        return cmd_xcheck(argv[1])
    if cmd == "who":
        return cmd_who(argv[1], argv[2])
    if cmd == "refs":
        return cmd_refs(argv[1], argv[2], argv[3])
    if cmd == "tree":
        cmd_tree(argv[1])
    elif cmd == "defaults":
        cmd_defaults(argv[1], argv[2], argv[3] if len(argv) > 3 else None)
    elif cmd == "disk":
        cmd_disk(argv[1:])
    elif cmd == "calls":
        cmd_calls(argv[1], argv[2], argv[3] if len(argv) > 3 else None)
    elif cmd == "decls":
        cmd_decls(argv[1], argv[2], argv[3])
    elif cmd == "census":
        cmd_census(argv[1:])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
