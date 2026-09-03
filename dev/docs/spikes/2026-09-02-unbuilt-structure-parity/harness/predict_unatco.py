#!/usr/bin/env python3
"""Generative table-order prediction for the UNATCO import golden.

Extends predict_tables.py's model with the ensure_load phase: each `OBJ LOAD`ed
package registers its FULL name table (file order) and creates its objects
(package root, then exports in table order, outers first) BEFORE `MAP IMPORT`;
map names then follow the T3D two-pass creation model.

Usage: predict_unatco.py <dump> <golden.dx> <trunk-dir>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli.upackage import load_package, read_property_tags, read_compact_index  # noqa: E402
from count_refs import collect, import_totals, RF_HasStack                        # noqa: E402
from msvc_qsort import msvc_qsort                                                 # noqa: E402
import predict_tables as PT                                                       # noqa: E402


def load_order_files(trunk_dir: str) -> list[tuple[str, str]]:
    from uedcli import config, trunk as trunk_mod
    from uedcli.apply import _level_referenced_packages
    from uedcli.packages import obj_load_entries, editor_search_dirs
    from uedcli.materialize import levelinfo_first_order
    lvl, _ = trunk_mod.read_level(Path(trunk_dir))
    classes = {n: lvl.actors[n].cls for n in lvl.order}
    hb = {n: lvl.actors[n].brush is not None for n in lvl.order}
    order = levelinfo_first_order(lvl.order, classes, hb)
    ref = _level_referenced_packages(
        type("L", (), {"actors": {n: lvl.actors[n] for n in order}})())
    proj = config.load_project(str(Path(trunk_dir).parents[1]))
    sd = config.composed_search_dirs(proj, config.load_user_config())
    return obj_load_entries(ref, editor_search_dirs(sd))


def package_name_seq(files: list[tuple[str, str]]) -> list[str]:
    seq = []
    for _pkg, f in files:
        seq += list(load_package(f).names)
    return seq


def package_object_seq(files: list[tuple[str, str]]) -> list[str]:
    """Full object paths (Pkg.Group.Name, lowercased) in creation order."""
    seq: list[str] = []
    for pkg, f in files:
        p = load_package(f, name=pkg)
        seq.append(pkg.lower())
        made = {0}
        def make(ref: int) -> None:
            if ref in made or ref <= 0:
                return
            ex = p.exports[ref - 1]
            make(ex["outer"])
            made.add(ref)
            seq.append(p.object_path(ref).lower())    # object_path already includes the package
        for i in range(1, len(p.exports) + 1):
            make(i)
    return seq


def golden_import_paths(pkg) -> list[tuple[str, str]]:
    """(full path lowercased, top-level name) per import entry, golden order."""
    out = []
    for j, imp in enumerate(pkg.imports):
        parts = []
        k = j
        while True:
            parts.append(pkg.names[pkg.imports[k][3]])
            outer = pkg.imports[k][2]
            if outer >= 0:
                break
            k = -outer - 1
        out.append((".".join(reversed(parts)).lower(), parts[0]))
    return out


_ACTOR_RE = re.compile(r"^Begin Actor Class=(\S+) Name=(\S+)")
_BRUSH_RE = re.compile(r"^\s*Begin Brush Name=(\S+)")
_ITEM_RE = re.compile(r"^\s*Begin Polygon.*?\bItem=(\S+)")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def t3d_name_events(t3d: str, name_values: set[str], pkg) -> list[str]:
    """Map-time FName creation order from the T3D text: pass 1 actor names, then per
    actor (T3D order) its property-value names, brush model name, polys auto-name,
    poly item names."""
    exp_name = [pkg.names[e["nm"]] for e in pkg.exports]
    model_polys = {}
    for i in range(len(pkg.exports)):
        if pkg.object_class_name(i + 1) == "Model":
            pname, _items = PT.model_polys_items(pkg, i + 1)
            model_polys[exp_name[i]] = pname
    lines = t3d.splitlines()
    # the fresh level's model + polys exist before any T3D actor
    lvl_refs = PT.level_actor_refs(pkg)   # noqa: F841  (forces Level export parse below)
    import struct as _s
    li = next(i for i in range(len(pkg.exports))
              if pkg.object_class_name(i + 1) == "Level")
    buf, pos = pkg.buf, pkg.exports[li]["soff"]
    _, pos = read_compact_index(buf, pos)
    num = _s.unpack_from("<i", buf, pos)[0]
    pos += 8
    for _ in range(num):
        _, pos = read_compact_index(buf, pos)
    from uedcli.upackage import read_fstring
    for _ in range(4):
        _, pos = read_fstring(buf, pos)
    nops, pos = read_compact_index(buf, pos)
    for _ in range(nops):
        _, pos = read_fstring(buf, pos)
    pos += 8
    lvl_model, pos = read_compact_index(buf, pos)
    prefix = []
    if lvl_model > 0:
        prefix.append(exp_name[lvl_model - 1])
        if exp_name[lvl_model - 1] in model_polys:
            prefix.append(model_polys[exp_name[lvl_model - 1]])
    # the fresh builder brush's name, interned unconditionally at MAP-IMPORT init
    # (UNATCO trace: between the level Model/Polys names and the T3D walk); survives
    # into the saved table only when the level references it (the tagged filter)
    prefix.append("Brush1")
    actors: list[tuple[str, int, int]] = []
    depth_start = None
    for idx, ln in enumerate(lines):
        m = _ACTOR_RE.match(ln)
        if m:
            depth_start = idx
            aname = m.group(2)
        elif ln.startswith("End Actor") and depth_start is not None:
            actors.append((aname, depth_start, idx))
            depth_start = None
    seq: list[str] = prefix + [a for a, _, _ in actors]             # pass 1
    for aname, s, e in actors:                                      # pass 2
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
            if in_brush:
                continue
            if "=" not in ln:
                continue
            val = ln.split("=", 1)[1]
            # quoted values: a name property's T3D form (Group="boo", possibly comma-multi);
            # only whole quoted words count, so prose strings don't fire
            def _quoted(m):
                for part in m.group(1).split(","):
                    if part in name_values:
                        seq.append(part)
                return ""
            val = re.sub(r'"([^"]*)"', _quoted, val)
            for tok in _WORD_RE.findall(val):
                if tok in name_values:
                    seq.append(tok)
    # post-import viewport cameras
    cams = sorted((n for n, c in ((exp_name[i], pkg.object_class_name(i + 1))
                                  for i in range(len(pkg.exports))) if c == "Camera"),
                  key=lambda n: int(re.sub(r"\D", "", n) or 0))
    seq += cams
    out, seen = [], set()
    for n in seq:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def name_value_set(pkg) -> set[str]:
    """Every FName TEXT that occurs as a VALUE in export bodies (candidates for
    map-time creation via property import)."""
    vals = set()
    for i, ex in enumerate(pkg.exports):
        cls = pkg.object_class_name(i + 1)
        if cls in ("Model", "Polys", "Level"):
            continue
        pos, end = ex["soff"], ex["soff"] + ex["ssize"]
        if ex["flags"] & RF_HasStack:
            node, pos = read_compact_index(pkg.buf, pos)
            _, pos = read_compact_index(pkg.buf, pos)
            pos += 12
            if node != 0:
                _, pos = read_compact_index(pkg.buf, pos)
        tags, _ = read_property_tags(pkg, pos, end)
        for t in tags:
            if t.ptype == 6:
                n, _ = read_compact_index(t.raw, 0)
                vals.add(pkg.names[n])
            elif t.struct_name == "InitialAllianceInfo":
                n, _ = read_compact_index(t.raw, 0)
                vals.add(pkg.names[n])
            elif t.struct_name == "SNanoKeyInitStruct":
                n, p = read_compact_index(t.raw, 0)
                vals.add(pkg.names[n])
                n, _ = read_compact_index(t.raw, p)
                vals.add(pkg.names[n])
    return vals


def main() -> int:
    dump, golden_path, trunk_dir = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    pkg = load_package(golden_path)
    ev = collect(pkg)
    files = load_order_files(trunk_dir)
    print("load order:", [p for p, _ in files])
    ok = True

    from creation_order import (boot_object_paths, import_creation_order,
                                 package_name_order)

    # --- imports (creation-order model, UNATCO-trace-confirmed) ---
    totals = import_totals(pkg, ev)
    idents = golden_import_paths(pkg)
    referenced = {p for p, _ in idents}
    boot = boot_object_paths(str(dump), referenced)
    pred_imp = import_creation_order(files, referenced, boot)
    imp_pos = {p: i for i, p in enumerate(pred_imp)}
    pairs = sorted(range(len(idents)), key=lambda j: imp_pos.get(idents[j][0], 10**6 + j))
    arr = [(idents[j][0], totals[j]) for j in pairs]
    msvc_qsort(arr, lambda a, b: b[1] - a[1])
    d = [(i, arr[i][0], idents[i][0]) for i in range(len(arr)) if arr[i][0] != idents[i][0]]
    print(f"IMPORT order: {'EXACT' if not d else f'{len(d)} mismatches'} of {len(arr)}")
    if d:
        print("  first:", d[:10])
    ok &= not d

    # --- names (boot ++ per-package [root, FName table] ++ map-time names) ---
    counts = {pkg.names[i]: ev.names.get(i, 0) for i in range(len(pkg.names))}
    tagged = set(pkg.names)
    startup = PT.startup_names(dump)
    seen = set(startup)
    pkg_names = [n for n in package_name_order(files) if not (n in seen or seen.add(n))]

    from uedcli import trunk as trunk_mod
    from uedcli.emit import emit_map
    from uedcli.materialize import levelinfo_first_order
    lvl, _ = trunk_mod.read_level(Path(trunk_dir))
    classes = {n: lvl.actors[n].cls for n in lvl.order}
    hb = {n: lvl.actors[n].brush is not None for n in lvl.order}
    order = levelinfo_first_order(lvl.order, classes, hb)
    t3d = emit_map([lvl.actors[n] for n in order])
    events = [n for n in t3d_name_events(t3d, name_value_set(pkg), pkg) if n not in seen]

    initial = ([n for n in startup if n in tagged]
               + [n for n in pkg_names if n in tagged]
               + [n for n in events if n in tagged])
    miss = tagged - set(initial)
    if miss:
        print(f"NAME model misses: {len(miss)} e.g. {sorted(miss)[:15]}")
        ok = False
    else:
        arr = initial[:]
        msvc_qsort(arr, lambda a, b: counts[b] - counts[a])
        d = [(i, arr[i], pkg.names[i]) for i in range(len(arr)) if arr[i] != pkg.names[i]]
        allties = all(counts[a] == counts[b] for _, a, b in d)
        print(f"NAME order: {'EXACT' if not d else f'{len(d)} mismatches (all-ties={allties})'} "
              f"of {len(arr)}")
        # names are owner-excluded from the parity bar; report but don't fail on ties
    print("IMPORT EXACT" if ok else "IMPORT MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
