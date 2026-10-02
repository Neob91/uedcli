#!/usr/bin/env python3
"""Inspect and compare path graphs of built `.dx` files (uses `retail_stats.analyze` internals).

  graph_tool.py nodes <dx> <name-regex>       nodes + every spec touching them
  graph_tool.py steps <dx>                    edges between nodes at DIFFERENT z (step/jump probe)
  graph_tool.py diff <dx-a> <dx-b>            edge sets by (Start,End) name; field diffs on common edges
  graph_tool.py templates <log> [from] [to]   unique log-line templates (numbers/names masked) with counts
"""
from __future__ import annotations

import re
import sys
from collections import Counter

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from retail_stats import Nav, export_fqcn, flagstr, is_nav_class, load_package, parse_level, parse_nav  # noqa: E402


def graph(path: str):
    pkg = load_package(path)
    _, specs = parse_level(pkg)
    navs: dict[int, Nav] = {}
    for i in range(len(pkg.exports)):
        fq = export_fqcn(pkg, i)
        if not fq.startswith("MyLevel.") and is_nav_class(fq):
            navs[i + 1] = parse_nav(pkg, i)
    return navs, specs


def edge_rows(navs, specs):
    for k, (d, s, t, r, h, f, pr) in enumerate(specs):
        a, b = navs.get(s), navs.get(t)
        yield k, d, r, h, f, pr, (a.name if a else f"#{s}"), (b.name if b else f"#{t}"), a, b


def cmd_nodes(path, pat):
    navs, specs = graph(path)
    rx = re.compile(pat)
    for n in navs.values():
        if rx.search(n.name):
            print(n.name, n.cls, n.loc, "P", n.paths, "U", n.upstream, "PR", n.pruned, {k: v for k, v in n.props.items() if k not in ("visitedWeight",)})
    for k, d, r, h, f, pr, an, bn, a, b in edge_rows(navs, specs):
        if rx.search(an) or rx.search(bn):
            print(f"  spec {k:4d} {an:>12} -> {bn:<12} dist={d:5d} R/H={r}/{h} {flagstr(f):<10} pruned={pr}")


def cmd_steps(path):
    navs, specs = graph(path)
    rows = []
    for k, d, r, h, f, pr, an, bn, a, b in edge_rows(navs, specs):
        if a and b and a.loc[2] != b.loc[2]:
            rows.append((b.loc[2] - a.loc[2], an, bn, d, r, h, f, pr))
    for dz, an, bn, d, r, h, f, pr in sorted(rows):
        print(f"dz={dz:+6.0f} {an:>10} -> {bn:<10} dist={d:4d} R/H={r}/{h} {flagstr(f):<10} pruned={pr}")


def cmd_diff(pa, pb):
    na, sa = graph(pa)
    nb, sb = graph(pb)
    ea = {(an, bn): (d, r, h, f, pr) for k, d, r, h, f, pr, an, bn, a, b in edge_rows(na, sa)}
    eb = {(an, bn): (d, r, h, f, pr) for k, d, r, h, f, pr, an, bn, a, b in edge_rows(nb, sb)}
    common = set(ea) & set(eb)
    print(f"A={len(ea)} B={len(eb)} common={len(common)} onlyA={len(set(ea) - set(eb))} onlyB={len(set(eb) - set(ea))}")
    diffs = Counter()
    ex = {}
    for e in common:
        for i, fld in enumerate(("dist", "R", "H", "flags", "pruned")):
            if ea[e][i] != eb[e][i]:
                diffs[fld] += 1
                ex.setdefault(fld, []).append((e, ea[e], eb[e]))
    print("field diffs on common edges:", dict(diffs))
    for fld, lst in ex.items():
        print(f"  {fld} sample:", lst[:6])
    print("onlyA sample:", sorted(set(ea) - set(eb))[:15])
    print("onlyB sample:", sorted(set(eb) - set(ea))[:15])
    da = Counter(v[0] - (v[0]) for v in ea.values())
    print("A pruned:", sum(1 for v in ea.values() if v[4]), "B pruned:", sum(1 for v in eb.values() if v[4]))
    print("A flags:", Counter(flagstr(v[3]) for v in ea.values()), "B flags:", Counter(flagstr(v[3]) for v in eb.values()))
    print("A R/H top:", Counter((v[1], v[2]) for v in ea.values()).most_common(8))
    print("B R/H top:", Counter((v[1], v[2]) for v in eb.values()).most_common(8))


def cmd_census(path):
    pkg = load_package(path)
    c = Counter(export_fqcn(pkg, i).split(".")[-1] for i in range(len(pkg.exports)))
    print(path.split("/")[-1], len(pkg.exports), "exports;", c.most_common(40))
    navs, specs = graph(path)
    print("navs", len(navs), "specs", len(specs), "bAutoBuilt", sum(1 for n in navs.values() if n.props.get("bAutoBuilt")),
          "nav classes", Counter(n.cls for n in navs.values()))


def cmd_templates(log, a=None, b=None):
    lines = open(log, errors="replace").read().splitlines()
    if a:
        lines = lines[int(a) - 1:int(b)]
    c = Counter()
    first = {}
    for l in lines:
        t = re.sub(r"-?\d+\.\d+", "<f>", l)
        t = re.sub(r"-?\b\d+\b", "<n>", t)
        t = re.sub(r"\b[A-Z]\w*\d+\b|\b[A-D]_\w+\b", "<name>", t)
        c[t] += 1
        first.setdefault(t, l)
    for t, n in c.most_common():
        print(f"{n:6d}  {t}    e.g. {first[t][:120]}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"nodes": cmd_nodes, "steps": cmd_steps, "diff": cmd_diff, "templates": cmd_templates, "census": cmd_census}[cmd](*sys.argv[2:])
