#!/usr/bin/env python3
"""Replay the builder's list bookkeeping + Prune on a built map and compare with what is on disk.

Input: the map's `ReachSpecs` (in array order = creation order) and its actor roster. Replays
`insertReachSpec` (descending-Distance insert, 16-slot cap, evict-longest / refuse-longest) into
every node's `Paths`/`upstreamPaths`, then `Prune` over the NavigationPointList (reverse roster
order, as `definePaths` prepends) with the decoded criterion, then checks the resulting `Paths`,
`upstreamPaths`, `PrunedPaths` and `bPruned` against the file. A 100 % match on retail maps
verifies the DX 1112fm reading (`findings/20-dx-pathbuilder.md` §3.28–3.32); `--engine ued`
uses the UED22 constants (`findings/10-ued-pathbuilder.md` §4.5, §4.9) for UED22-built maps.

Usage: simulate_bookkeeping.py [--engine dx|ued] [--verbose] <map.dx> [...]
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from retail_stats import export_fqcn, is_nav_class, load_package, parse_level, parse_nav  # noqa: E402

R_FLY = 2
import os
DEBUG_SPECS = os.environ.get("DEBUG_SPECS", "").split(",")
STRICT = os.environ.get("STRICT", "") == "1"


def insert(paths: list[int], specs, spec_idx: int) -> int:
    d = specs[spec_idx][0]
    n = 0
    while n < 16 and paths[n] != -1 and specs[paths[n]][0] > d:
        n += 1
    if paths[15] == -1:
        e = paths.index(-1)                      # first free slot, >= n
        for k in range(e, n, -1):
            paths[k] = paths[k - 1]
        paths[n] = spec_idx
        return n
    if n == 0:
        return -1
    for k in range(0, n - 1):
        paths[k] = paths[k + 1]
    paths[n - 1] = spec_idx
    return n - 1


def remove(paths: list[int], spec_idx: int) -> None:
    if spec_idx not in paths:
        return
    i = paths.index(spec_idx)
    for k in range(i, 15):
        paths[k] = paths[k + 1]
    paths[15] = -1


def run(path: str, engine: str, verbose: bool) -> tuple[int, int, str]:
    pkg = load_package(path)
    refs, specs = parse_level(pkg)
    navs = {}
    for i in range(len(pkg.exports)):
        fq = export_fqcn(pkg, i)
        if not fq.startswith("MyLevel.") and is_nav_class(fq):
            navs[i + 1] = parse_nav(pkg, i)
    roster = [r for r in refs if r in navs]
    if engine == "dx":
        bot_only = lambda s: s[3] < 12                                   # noqa: E731
        monster = lambda s: s[3] >= 22 and s[4] >= 51 and not (s[5] & R_FLY)   # noqa: E731
    else:
        bot_only = lambda s: s[3] < 24                                   # noqa: E731
        monster = lambda s: s[3] >= 52 and s[4] >= 40 and not (s[5] & R_FLY)   # noqa: E731
    P = {n: [-1] * 16 for n in navs}
    U = {n: [-1] * 16 for n in navs}
    PR = {n: [-1] * 16 for n in navs}
    pruned = [0] * len(specs)
    # creation order = array order; the builder appends only when the Start insert succeeded
    for k, (d, s, t, r, h, f, pr) in enumerate(specs):
        if s not in navs or t not in navs:
            continue
        if insert(P[s], specs, k) == -1:
            pass                                                         # cannot happen for a spec that is in the array
        insert(U[t], specs, k)
    if verbose:
        name = {n: nav.name for n, nav in navs.items()}
        print("roster:", [name[r] for r in roster][:6], "... n =", len(roster))
        for n in list(navs)[:3]:
            print(f"  {name[n]}: simP={P[n]} diskP={navs[n].paths} diskPR={navs[n].pruned}")
            print(f"  {name[n]}: simU={U[n]} diskU={navs[n].upstream}")
    # Prune over NavigationPointList = reverse roster
    for node in reversed(roster):
        for i in range(16):
            ui = U[node][i]
            if ui == -1:
                break
            a = specs[ui]
            for j in range(16):
                di = P[node][j]
                if di == -1:
                    break
                b = specs[di]
                A, B = a[1], b[2]
                k = -1
                for idx in P[A]:
                    if idx == -1:
                        break
                    if specs[idx][2] == B:
                        k = idx
                        break
                if k == -1:
                    continue
                g = specs[k]
                comb = (a[0] + b[0], A, B, min(a[3], b[3]), min(a[4], b[4]), a[5] | b[5], 0)
                if not ((float(comb[0]) < 1.2 * float(g[0])) if STRICT else (float(comb[0]) <= 1.2 * float(g[0]))):
                    continue
                le = comb[3] >= g[3] and comb[4] >= g[4] and (comb[5] | g[5]) == g[5]
                if not (le or bot_only(g) or monster(comb)):
                    continue
                if verbose and str(k) in DEBUG_SPECS:
                    print(f"  DEBUG prune spec {k} {g} via node {navs[node].name}: alpha {ui} {a} beta {di} {b} comb {comb} le={le} bot={bot_only(g)} monster={monster(comb)}")
                remove(P[A], k)
                slot = PR[A].index(-1) if -1 in PR[A] else 15
                PR[A][slot] = k
                pruned[k] = 1
                remove(U[B], k)
    # compare
    ok = bad = 0
    msgs = []
    for k, sp in enumerate(specs):
        if pruned[k] == sp[6]:
            ok += 1
        else:
            bad += 1
            if verbose:
                msgs.append(f"spec {k} {sp} sim_pruned={pruned[k]}")
    arr_ok = arr_bad = 0
    for n, nav in navs.items():
        for name, sim, disk in (("Paths", P[n], nav.paths), ("upstreamPaths", U[n], nav.upstream), ("PrunedPaths", PR[n], nav.pruned)):
            d = [disk.get(i, -1) for i in range(16)]
            if sim == d:
                arr_ok += 1
            else:
                arr_bad += 1
                if verbose and len(msgs) < 40:
                    msgs.append(f"{nav.name}.{name} sim={sim} disk={d}")
    return ok, bad, f"{path.split('/')[-1]:36s} specs {ok}/{ok + bad} bPruned match; arrays {arr_ok}/{arr_ok + arr_bad} match" + ("\n  " + "\n  ".join(msgs) if msgs else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="dx", choices=("dx", "ued"))
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("maps", nargs="+")
    a = ap.parse_args()
    tot_ok = tot_bad = 0
    for m in a.maps:
        try:
            ok, bad, msg = run(m, a.engine, a.verbose)
        except Exception as ex:
            print(m, "ERR", ex)
            continue
        tot_ok += ok; tot_bad += bad
        print(msg)
    print(f"TOTAL bPruned match {tot_ok}/{tot_ok + tot_bad}")


if __name__ == "__main__":
    main()
