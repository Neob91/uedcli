#!/usr/bin/env python3
"""Ground-truth statistics of the AI path graph in the retail Deus Ex maps.

Decodes every map's `ULevel.ReachSpecs` + each NavigationPoint's tagged `Paths`/`upstreamPaths`/
`PrunedPaths`/`VisNoReachPaths`/flags, then tests the builder hypotheses (Distance = straight
line? array ordering? the prune criterion? 16-slot overflow? flag/radius/height value sets).

Usage: retail_stats.py [--maps <glob>] [--md <out.md>] [--dump <map-name>]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import struct
import sys
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from uedcli.upackage import Package, load_package, read_compact_index, read_property_tags  # noqa: E402
from uedcli.uprops.uclass import _super_fqcn  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import GAME as _GAME  # noqa: E402
GAME = str(_GAME)
RF_HasStack = 0x02000000
R_WALK, R_FLY, R_SWIM, R_JUMP, R_DOOR, R_SPECIAL, R_PLAYERONLY = 1, 2, 4, 8, 16, 32, 64
FLAGNAMES = {1: "WALK", 2: "FLY", 4: "SWIM", 8: "JUMP", 16: "DOOR", 32: "SPECIAL", 64: "PLAYERONLY"}

_code_pkgs: dict[str, Package] = {}
_nav_cache: dict[str, bool] = {}


def code_pkg(name: str) -> Package | None:
    k = name.casefold()
    if k not in _code_pkgs:
        hits = glob.glob(f"{GAME}/System/*.u")
        p = next((h for h in hits if h.split("/")[-1].casefold() == f"{k}.u"), None)
        _code_pkgs[k] = load_package(p, name=name) if p else None
    return _code_pkgs[k]


def is_nav_class(fqcn: str) -> bool:
    if fqcn in _nav_cache:
        return _nav_cache[fqcn]
    cur = fqcn
    res = False
    for _ in range(40):
        pkg_name, cls = cur.split(".", 1)
        if cls == "NavigationPoint":
            res = True
            break
        pkg = code_pkg(pkg_name)
        if pkg is None:
            break
        try:
            cur = _super_fqcn(pkg, cls)
        except Exception:
            cur = None
        if cur is None:
            break
    _nav_cache[fqcn] = res
    return res


def export_fqcn(pkg: Package, i: int) -> str:
    e = pkg.exports[i]
    cls_ref = e["cls"]
    if cls_ref >= 0:
        return "MyLevel." + (pkg.name_of_ref(cls_ref) or "Class")
    imp = pkg.imports[-cls_ref - 1]
    return f"{pkg.import_package_of(-cls_ref - 1)}.{pkg.names[imp[3]]}"


def flagstr(f: int) -> str:
    return "|".join(n for b, n in FLAGNAMES.items() if f & b) or "0"


@dataclass
class Nav:
    idx1: int
    name: str
    cls: str
    loc: tuple[float, float, float] | None = None
    paths: dict | None = None
    upstream: dict | None = None
    pruned: dict | None = None
    visnoreach: dict | None = None
    props: dict | None = None
    radius: float = 0.0
    height: float = 0.0


def parse_level(pkg: Package):
    li = next(i for i, e in enumerate(pkg.exports) if pkg.object_class_name(i + 1) == "Level")
    e = pkg.exports[li]
    buf, pos, end = pkg.buf, e["soff"], e["soff"] + e["ssize"]
    _, pos = read_property_tags(pkg, pos, end)
    num = struct.unpack_from("<i", buf, pos)[0]; pos += 8
    refs = []
    for _ in range(num):
        r, pos = read_compact_index(buf, pos); refs.append(r)
    for _ in range(4):
        n, pos = read_compact_index(buf, pos); pos += (n if n >= 0 else -2 * n)
    opc, pos = read_compact_index(buf, pos)
    for _ in range(opc):
        n, pos = read_compact_index(buf, pos); pos += (n if n >= 0 else -2 * n)
    pos += 8
    _, pos = read_compact_index(buf, pos)
    cnt, pos = read_compact_index(buf, pos)
    specs = []
    for _ in range(cnt):
        d = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        s, pos = read_compact_index(buf, pos)
        t, pos = read_compact_index(buf, pos)
        r, h, f = struct.unpack_from("<iii", buf, pos); pos += 12
        pr = buf[pos]; pos += 1
        specs.append((d, s, t, r, h, f, pr))
    return refs, specs


def parse_nav(pkg: Package, i: int) -> Nav:
    e = pkg.exports[i]
    buf, pos, end = pkg.buf, e["soff"], e["soff"] + e["ssize"]
    if e["flags"] & RF_HasStack:
        node, pos = read_compact_index(buf, pos)
        _, pos = read_compact_index(buf, pos)
        pos += 12
        if node != 0:
            _, pos = read_compact_index(buf, pos)
    tags, _ = read_property_tags(pkg, pos, end)
    nav = Nav(idx1=i + 1, name=pkg.names[e["nm"]], cls=export_fqcn(pkg, i).split(".", 1)[1],
              paths={}, upstream={}, pruned={}, visnoreach={}, props={})
    for t in tags:
        if t.name == "Location":
            nav.loc = struct.unpack("<fff", t.raw)
        elif t.name == "Paths":
            nav.paths[t.array_index] = struct.unpack("<i", t.raw)[0]
        elif t.name == "upstreamPaths":
            nav.upstream[t.array_index] = struct.unpack("<i", t.raw)[0]
        elif t.name == "PrunedPaths":
            nav.pruned[t.array_index] = struct.unpack("<i", t.raw)[0]
        elif t.name == "VisNoReachPaths":
            nav.visnoreach[t.array_index] = read_compact_index(t.raw, 0)[0]
        elif t.name == "CollisionRadius":
            nav.radius = struct.unpack("<f", t.raw)[0]
        elif t.name == "CollisionHeight":
            nav.height = struct.unpack("<f", t.raw)[0]
        elif t.ptype == 3:
            nav.props[t.name] = t.bool_value
        elif t.ptype in (1, 2, 4):
            nav.props[t.name + (f"[{t.array_index}]" if t.array_index else "")] = (
                t.raw[0] if t.ptype == 1 else struct.unpack("<i" if t.ptype == 2 else "<f", t.raw)[0])
    return nav


def analyze(path: str, dump: bool = False) -> dict:
    pkg = load_package(path)
    refs, specs = parse_level(pkg)
    navs: dict[int, Nav] = {}
    for i in range(len(pkg.exports)):
        fq = export_fqcn(pkg, i)
        if fq.startswith("MyLevel."):
            continue
        if is_nav_class(fq):
            navs[i + 1] = parse_nav(pkg, i)
    R = {"map": path.split("/")[-1], "actors": len(refs), "navs": len(navs), "specs": len(specs),
         "pruned": sum(1 for s in specs if s[6]), "flags": Counter(), "rh": Counter(), "cls": Counter(),
         "dist_eq_trunc": 0, "dist_eq_round": 0, "dist_other": [], "maxdist": Counter(),
         "paths_ok": 0, "paths_bad": [], "up_ok": 0, "up_bad": [], "pr_ok": 0, "pr_bad": [],
         "order_by_dist": 0, "order_by_specidx": 0, "order_by_endidx": 0, "order_n": 0,
         "gaps": 0, "overflow": [], "recip": 0, "prune_ok": 0, "prune_bad": [], "unpruned_prunable": 0,
         "unpruned_checked": 0, "autobuilt": 0, "props": Counter(), "special": [], "nonpath_cls": Counter(),
         "spec_not_in_arrays": 0, "dup_pairs": 0, "order_by_dist_desc": 0, "uorder_n": 0, "uorder_by_dist_desc": 0,
         "p_plus_pr_16": 0, "p_plus_pr_gt16": 0, "dropped_are_longest": 0, "dropped_not_longest": 0, "orphans": 0, "orphans_pruned": 0, "prune_ok_1x": 0, "dist_swim_2x": 0, "dist_swim_2round": 0, "max_prune_ratio": 0.0, "heights": Counter(), "radii": Counter(), "self_loops": 0, "zero_dist": 0,
         "notnav_endpoint": 0, "visnoreach": 0}
    referenced = set()
    by_start = defaultdict(list)
    by_end = defaultdict(list)
    pairs = Counter()
    for k, (d, s, t, r, h, f, pr) in enumerate(specs):
        R["flags"][flagstr(f)] += 1
        R["rh"][(r, h)] += 1
        R["heights"][h] += 1; R["radii"][r] += 1
        by_start[s].append(k); by_end[t].append(k)
        pairs[(s, t)] += 1
        if s == t:
            R["self_loops"] += 1
        if d == 0:
            R["zero_dist"] += 1
        a, b = navs.get(s), navs.get(t)
        if a is None or b is None:
            R["notnav_endpoint"] += 1
            continue
        R["cls"][(a.cls, b.cls)] += 1
        if a.loc and b.loc:
            eu = math.dist(a.loc, b.loc)
            if d == int(eu):
                R["dist_eq_trunc"] += 1
            elif (f & R_SWIM) and d == 2 * int(eu):
                R["dist_swim_2x"] += 1                      # dx: 2 × truncated straight line
            elif (f & R_SWIM) and d == 2 * round(eu):
                R["dist_swim_2round"] += 1                  # ued: 2 × rounded straight line
            elif d == round(eu):
                R["dist_eq_round"] += 1
            else:
                R["dist_other"].append((k, d, round(eu, 2), flagstr(f), a.cls, b.cls))
            if not pr:
                R["maxdist"][flagstr(f)] = max(R["maxdist"][flagstr(f)], d)
        if f & R_SPECIAL:
            R["special"].append((d, r, h, flagstr(f), a.cls, b.cls, pr))
    R["dup_pairs"] = sum(1 for v in pairs.values() if v > 1)
    R["recip"] = sum(1 for (s, t) in pairs if (t, s) in pairs)
    for n in navs.values():
        R["props"].update(k for k, v in n.props.items() if v is not False)
        if n.props.get("bAutoBuilt"):
            R["autobuilt"] += 1
        if n.visnoreach:
            R["visnoreach"] += 1
        for arr, ok, bad, fn in ((n.paths, "paths_ok", "paths_bad", lambda s: s[1] == n.idx1 and not s[6]),
                                 (n.upstream, "up_ok", "up_bad", lambda s: s[2] == n.idx1 and not s[6]),
                                 (n.pruned, "pr_ok", "pr_bad", lambda s: s[1] == n.idx1 and s[6] == 1)):
            idxs = sorted(arr)
            if idxs and idxs != list(range(len(idxs))):
                R["gaps"] += 1
            for i in idxs:
                v = arr[i]
                if v < 0:
                    continue
                if v < len(specs) and fn(specs[v]):
                    R[ok] += 1
                else:
                    R[bad].append((n.name, i, v))
        vals = [n.paths[i] for i in sorted(n.paths) if n.paths[i] >= 0]
        if len(vals) >= 2:
            R["order_n"] += 1
            if vals == sorted(vals):
                R["order_by_specidx"] += 1
            if [specs[v][0] for v in vals] == sorted(specs[v][0] for v in vals):
                R["order_by_dist"] += 1
            if [specs[v][0] for v in vals] == sorted((specs[v][0] for v in vals), reverse=True):
                R["order_by_dist_desc"] += 1
        uvals = [n.upstream[i] for i in sorted(n.upstream) if n.upstream[i] >= 0]
        if len(uvals) >= 2:
            R["uorder_n"] += 1
            if [specs[v][0] for v in uvals] == sorted((specs[v][0] for v in uvals), reverse=True):
                R["uorder_by_dist_desc"] += 1
        pvals = [n.pruned[i] for i in sorted(n.pruned) if n.pruned[i] >= 0]
        if len(vals) + len(pvals) == 16:
            R["p_plus_pr_16"] += 1
        if len(vals) + len(pvals) > 16:
            R["p_plus_pr_gt16"] += 1
            if [specs[v][2] for v in vals] == sorted(specs[v][2] for v in vals):
                R["order_by_endidx"] += 1
        live_out = [k for k in by_start.get(n.idx1, []) if not specs[k][6]]
        if len(live_out) > len(vals):
            R["overflow"].append((n.name, len(live_out), len(vals), len(pvals)))
            R["spec_not_in_arrays"] += len(live_out) - len(vals)
            dropped = [specs[k][0] for k in live_out if k not in vals]
            if dropped and min(dropped) >= max(specs[v][0] for v in vals):
                R["dropped_are_longest"] += 1
            else:
                R["dropped_not_longest"] += 1
        referenced.update(vals); referenced.update(pvals); referenced.update(uvals)
    R["orphans"] = sum(1 for k in range(len(specs)) if k not in referenced)
    R["orphans_pruned"] = sum(1 for k in range(len(specs)) if k not in referenced and specs[k][6])
    # prune criterion: pruned A->B iff exists N with A->N, N->B (legs = any node-referenced spec) and d(AN)+d(NB) <= 1.2 d(AB)
    live = {(s[1], s[2]): s for k, s in enumerate(specs) if k in referenced}
    out_live = defaultdict(list)
    for (s, t), sp in live.items():
        out_live[s].append((t, sp))
    for k, (d, s, t, r, h, f, pr) in enumerate(specs):
        best = None
        for (n, sp1) in out_live.get(s, []):
            sp2 = live.get((n, t))
            if sp2 is None or n == t:
                continue
            tot = sp1[0] + sp2[0]
            if best is None or tot < best[0]:
                best = (tot, n, sp1, sp2)
        if pr:
            if best is not None and best[0] <= 1.2 * d:
                R["prune_ok"] += 1
                R["max_prune_ratio"] = max(R["max_prune_ratio"], best[0] / d if d else 0)
                if best[0] <= d:
                    R["prune_ok_1x"] += 1
            else:
                R["prune_bad"].append((k, d, best[0] if best else None, flagstr(f)))
        else:
            R["unpruned_checked"] += 1
            if best is not None and best[0] <= 1.2 * d and min(best[2][3], best[3][3]) >= r and min(best[2][4], best[3][4]) >= h and (best[2][5] | best[3][5]) == f:
                R["unpruned_prunable"] += 1
    if dump:
        for n in navs.values():
            print(n.name, n.cls, n.loc, "R/H", n.radius, n.height, "P", n.paths, "U", n.upstream, "PR", n.pruned, n.props)
        for k, s in enumerate(specs):
            a, b = navs.get(s[1]), navs.get(s[2])
            print(k, s, a.name if a else s[1], b.name if b else s[2])
    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", default=f"{GAME}/Maps/*.dx")
    ap.add_argument("--json")
    ap.add_argument("--dump")
    a = ap.parse_args()
    if a.dump:
        analyze(a.dump, dump=True)
        return
    out = []
    for p in sorted(glob.glob(a.maps)):
        try:
            out.append(analyze(p))
        except Exception as ex:
            print(p.split("/")[-1], "ERR", ex, file=sys.stderr)
    if a.json:
        json.dump([{k: ([[str(kk), vv] for kk, vv in v.items()] if isinstance(v, Counter) else v) for k, v in R.items()} for R in out], open(a.json, "w"))
    tot = Counter()
    for R in out:
        for k in ("actors", "navs", "specs", "pruned", "dist_eq_trunc", "dist_eq_round", "paths_ok", "up_ok", "pr_ok",
                  "order_by_dist", "order_by_specidx", "order_by_endidx", "order_n", "gaps", "recip", "prune_ok",
                  "unpruned_prunable", "unpruned_checked", "autobuilt", "spec_not_in_arrays", "dup_pairs", "self_loops",
                  "zero_dist", "notnav_endpoint", "visnoreach", "order_by_dist_desc", "uorder_n", "uorder_by_dist_desc",
                  "p_plus_pr_16", "p_plus_pr_gt16", "dropped_are_longest", "dropped_not_longest", "orphans", "orphans_pruned", "prune_ok_1x", "dist_swim_2x", "dist_swim_2round"):
            tot[k] += R[k]
        tot["dist_other"] += len(R["dist_other"]); tot["paths_bad"] += len(R["paths_bad"])
        tot["up_bad"] += len(R["up_bad"]); tot["pr_bad"] += len(R["pr_bad"]); tot["prune_bad"] += len(R["prune_bad"])
        tot["overflow_nodes"] += len(R["overflow"])
    flags, rh, cls, props, maxd = Counter(), Counter(), Counter(), Counter(), Counter()
    for R in out:
        flags.update(R["flags"]); rh.update(R["rh"]); cls.update(R["cls"]); props.update(R["props"])
        for k, v in R["maxdist"].items():
            maxd[k] = max(maxd[k], v)
    heights, radii = Counter(), Counter()
    for R in out:
        heights.update(R["heights"]); radii.update(R["radii"])
    print("maps", len(out), "with specs", sum(1 for R in out if R["specs"]))
    print("max_prune_ratio", max(R["max_prune_ratio"] for R in out))
    print("heights", sorted(heights.items()))
    print("radii", sorted(radii.items()))
    print("totals", dict(tot))
    print("flags", flags.most_common())
    print("maxdist(unpruned) by flags", dict(maxd))
    print("R/H", rh.most_common(40))
    print("class pairs", cls.most_common(30))
    print("props", props.most_common())
    print("dist_other sample", [x for R in out for x in R["dist_other"]][:20])
    print("paths_bad sample", [(R["map"], x) for R in out for x in R["paths_bad"]][:10])
    print("up_bad sample", [(R["map"], x) for R in out for x in R["up_bad"]][:10])
    print("pr_bad sample", [(R["map"], x) for R in out for x in R["pr_bad"]][:10])
    print("prune_bad sample", [(R["map"], x) for R in out for x in R["prune_bad"]][:20])
    print("overflow sample", [(R["map"], x) for R in out for x in R["overflow"]][:20])
    print("special sample", [(R["map"], x) for R in out for x in R["special"]][:30])
    print("per-map", [(R["map"], R["navs"], R["specs"], R["pruned"]) for R in out])


if __name__ == "__main__":
    main()
