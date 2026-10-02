#!/usr/bin/env python3
"""Predict a MAP SAVE's name-table and import-table ORDER generatively.

Model (disasm RVAs in count_refs.py):
  initial name map  = tagged names in global FName-index order
                    = [session-startup names, fixed order] ++ [map names, creation order]
  initial import map = tagged import objects in GObjObjects order
  final order        = MSVC-CRT qsort, DESCENDING by the save's reference counters.

Startup orders come from the toysmall live trace (saveorder_oracle.py dump); map-name
creation order is derived from the level's own structure (Level.Actors spawn order,
per-brush Model -> Polys -> item names, then the re-spawned viewport cameras).

Usage: predict_tables.py <dump> <golden.dx> [more goldens...]
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from uedcli.upackage import Package, load_package, read_compact_index, read_fstring  # noqa: E402
from count_refs import collect, import_totals, RF_HasStack                            # noqa: E402
from msvc_qsort import msvc_qsort                                                     # noqa: E402

STARTUP_NAME_END = 7852        # first map-created name in the toysmall trace


def startup_names(dump: Path) -> list[str]:
    out = []
    for line in dump.read_text().splitlines():
        p = line.split(maxsplit=3)
        if p[0] != "NAME":
            continue
        if int(p[1]) >= STARTUP_NAME_END:
            break
        if p[2] != "-":
            out.append(p[3])
    return out


def startup_object_order(dump: Path) -> dict[str, int]:
    """name -> GObjObjects index for every live startup object (map objects included;
    callers only use pre-import identities)."""
    out = {}
    for line in dump.read_text().splitlines():
        p = line.split()
        if p[0] == "OBJ" and p[2] != "-":
            out.setdefault(p[3], int(p[1]))
    return out


def level_actor_refs(pkg: Package) -> list[int]:
    """The Level export's Actors array (spawn order)."""
    li = next(i for i in range(len(pkg.exports))
              if pkg.object_class_name(i + 1) == "Level")
    ex = pkg.exports[li]
    buf, pos = pkg.buf, ex["soff"]
    nidx, pos = read_compact_index(buf, pos)          # None terminator
    num = struct.unpack_from("<i", buf, pos)[0]
    pos += 8
    refs = []
    for _ in range(num):
        r, pos = read_compact_index(buf, pos)
        refs.append(r)
    return refs


def model_polys_items(pkg: Package, model_ref: int) -> tuple[str, list[str]]:
    """(polys export name, item names in FPoly order) for a Model export ref."""
    mex = pkg.exports[model_ref - 1]
    buf, pos = pkg.buf, mex["soff"]
    # skip UObject None + FBox + FSphere
    _, pos = read_compact_index(buf, pos)
    pos += 41
    for _ in range(2):
        n, pos = read_compact_index(buf, pos)
        pos += 12 * n
    n, pos = read_compact_index(buf, pos)             # Nodes
    for _ in range(n):
        pos += 25
        for _ in range(10):
            _, pos = read_compact_index(buf, pos)
        pos += 8
    n, pos = read_compact_index(buf, pos)             # Surfs
    for _ in range(n):
        _, pos = read_compact_index(buf, pos)
        pos += 4
        for _ in range(6):
            _, pos = read_compact_index(buf, pos)
        pos += 4
        _, pos = read_compact_index(buf, pos)
    n, pos = read_compact_index(buf, pos)             # Verts
    for _ in range(n):
        _, pos = read_compact_index(buf, pos)
        _, pos = read_compact_index(buf, pos)
    pos += 4                                          # NumSharedSides
    nz = struct.unpack_from("<i", buf, pos)[0]
    pos += 4
    for _ in range(nz):
        _, pos = read_compact_index(buf, pos)
        pos += 16
    polys_ref, pos = read_compact_index(buf, pos)
    if polys_ref == 0:
        return "", []
    pex = pkg.exports[polys_ref - 1]
    buf, pos = pkg.buf, pex["soff"]
    _, pos = read_compact_index(buf, pos)
    num = struct.unpack_from("<i", buf, pos)[0]
    pos += 8
    items = []
    for _ in range(num):
        nv, pos = read_compact_index(buf, pos)
        pos += 48 + 12 * nv + 4
        _, pos = read_compact_index(buf, pos)         # actor
        _, pos = read_compact_index(buf, pos)         # texture
        item, pos = read_compact_index(buf, pos)
        items.append(pkg.names[item])
        _, pos = read_compact_index(buf, pos)
        _, pos = read_compact_index(buf, pos)
        pos += 4
    return pkg.names[pex["nm"]], items


def map_name_creation_seq(pkg: Package) -> list[str]:
    """New-name creation order during MAP IMPORT (+ post-import cameras)."""
    exp_name = [pkg.names[e["nm"]] for e in pkg.exports]
    exp_cls = [pkg.object_class_name(i + 1) for i in range(len(pkg.exports))]
    actors = [r for r in level_actor_refs(pkg) if r > 0]
    seq: list[str] = []

    # the fresh level's model (+ its polys) exists before any T3D actor
    li = next(i for i in range(len(pkg.exports)) if exp_cls[i] == "Level")
    buf, pos = pkg.buf, pkg.exports[li]["soff"]
    _, pos = read_compact_index(buf, pos)
    num = struct.unpack_from("<i", buf, pos)[0]
    pos += 8
    for _ in range(num):
        _, pos = read_compact_index(buf, pos)
    for _ in range(4):
        _, pos = read_fstring(buf, pos)
    nops, pos = read_compact_index(buf, pos)
    for _ in range(nops):
        _, pos = read_fstring(buf, pos)
    pos += 8
    lvl_model, pos = read_compact_index(buf, pos)
    if lvl_model > 0:
        seq.append(exp_name[lvl_model - 1])
        pname, _ = model_polys_items(pkg, lvl_model)
        if pname:
            seq.append(pname)

    cams = [r for r in actors if exp_cls[r - 1] == "Camera"]
    t3d_actors = [r for r in actors if exp_cls[r - 1] != "Camera"]
    if TRUNK_ORDER:
        # spawn order = T3D order (the Actors ARRAY hoists brushes; names follow spawn)
        byname = {exp_name[r - 1]: r for r in t3d_actors}
        t3d_actors = [byname[n] for n in TRUNK_ORDER if n in byname] + \
                     [r for r in t3d_actors if exp_name[r - 1] not in set(TRUNK_ORDER)]
    # pass 1: all T3D actor names
    seq += [exp_name[r - 1] for r in t3d_actors]
    # pass 2: per brush actor, its model + polys + item names
    for r in t3d_actors:
        ex = pkg.exports[r - 1]
        buf, pos = pkg.buf, ex["soff"]
        if ex["flags"] & RF_HasStack:
            node, pos = read_compact_index(buf, pos)
            _, pos = read_compact_index(buf, pos)
            pos += 12
            if node != 0:
                _, pos = read_compact_index(buf, pos)
        from uedcli.upackage import read_property_tags
        tags, _ = read_property_tags(pkg, pos, ex["soff"] + ex["ssize"])
        for t in tags:
            if t.name == "Brush" and t.ptype == 5:
                mref, _ = read_compact_index(t.raw, 0)
                if mref > 0:
                    seq.append(exp_name[mref - 1])
                    pname, items = model_polys_items(pkg, mref)
                    if pname:
                        seq.append(pname)
                    seq += items
    # post-import viewport cameras (spawn order)
    seq += [exp_name[r - 1] for r in cams]

    out, seen = [], set()
    for n in seq:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def predict(dump: Path | str, golden_path: str) -> bool:
    dump = Path(dump)
    pkg = load_package(golden_path)
    ev = collect(pkg)
    ok = True

    # --- names ---
    counts = {pkg.names[i]: ev.names.get(i, 0) for i in range(len(pkg.names))}
    tagged = set(pkg.names)
    sn = startup_names(dump)
    sset = set(sn)
    creation = [n for n in map_name_creation_seq(pkg) if n not in sset]
    initial = [n for n in sn if n in tagged] + [n for n in creation if n in tagged]
    miss = tagged - set(initial)
    if miss:
        print(f"  NAME model misses tagged names: {sorted(miss)[:10]}")
        ok = False
    else:
        arr = initial[:]
        msvc_qsort(arr, lambda a, b: counts[b] - counts[a])
        good = arr == list(pkg.names)
        if not good:
            d = [(i, arr[i], pkg.names[i]) for i in range(len(arr)) if arr[i] != pkg.names[i]]
            print(f"  NAME order: {len(d)} mismatches of {len(arr)}: {d[:8]}")
        else:
            print(f"  NAME order: EXACT ({len(arr)} names)")
        ok &= good

    # --- imports ---
    totals = import_totals(pkg, ev)
    obj_order = startup_object_order(dump)
    idents = [pkg.names[imp[3]] for imp in pkg.imports]
    missing = [t for t in idents if t not in obj_order]
    if missing:
        print(f"  IMPORT model misses objects: {missing[:10]}")
        ok = False
    else:
        pairs = sorted(range(len(idents)), key=lambda j: obj_order[idents[j]])
        arr = [(idents[j], totals[j]) for j in pairs]
        msvc_qsort(arr, lambda a, b: b[1] - a[1])
        good = [t for t, _ in arr] == idents
        if not good:
            d = [(i, arr[i][0], idents[i]) for i in range(len(arr)) if arr[i][0] != idents[i]]
            print(f"  IMPORT order: {len(d)} mismatches of {len(arr)}: {d[:8]}")
        else:
            print(f"  IMPORT order: EXACT ({len(arr)} imports)")
        ok &= good
    return ok


TRUNK_ORDER: list[str] = []      # T3D actor import order (levelinfo_first_order), per level


def _trunk_order(trunk_dir: str) -> list[str]:
    sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
    from uedcli import trunk as trunk_mod
    from uedcli.materialize import levelinfo_first_order
    lvl, _ = trunk_mod.read_level(Path(trunk_dir))
    classes = {n: lvl.actors[n].cls for n in lvl.order}
    hb = {n: lvl.actors[n].brush is not None for n in lvl.order}
    return levelinfo_first_order(lvl.order, classes, hb)


def main() -> int:
    global TRUNK_ORDER
    dump = Path(sys.argv[1])
    allok = True
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        g = args[i]
        TRUNK_ORDER = []
        if i + 1 < len(args) and args[i + 1].startswith("--trunk="):
            TRUNK_ORDER = _trunk_order(args[i + 1].split("=", 1)[1])
            i += 1
        print(f"=== {g}")
        allok &= predict(dump, g)
        i += 1
    print("ALL EXACT" if allok else "MISMATCHES")
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
