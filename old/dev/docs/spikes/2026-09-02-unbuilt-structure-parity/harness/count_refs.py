#!/usr/bin/env python3
"""Reference counters for UED22 MAP SAVE name/import table order.

The counting core (Events, body walkers, collect, import_totals) is single-sourced in
the production module `uedcli.native.saveorder`; this file re-exports it and keeps the
CLI that prints per-table descending-violation diagnostics for a saved `.dx`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli.native.saveorder import (  # noqa: E402,F401
    Events, RF_HasStack, collect, import_totals)
from uedcli.upackage import load_package  # noqa: E402


def main() -> int:
    for path in sys.argv[1:]:
        pkg = load_package(path)
        ev = collect(pkg)
        totals = import_totals(pkg, ev)
        print(f"=== {path}")
        print("structs seen:", sorted(ev.structs_seen))
        bad = [(j, totals[j - 1], totals[j]) for j in range(1, len(totals))
               if totals[j] > totals[j - 1]]
        print(f"imports: {len(totals)}; descending-violations: {len(bad)}")
        for j, a, b in bad[:10]:
            print(f"  imp[{j-1}] {pkg.names[pkg.imports[j-1][3]]}={a} < "
                  f"imp[{j}] {pkg.names[pkg.imports[j][3]]}={b}")
        ncounts = [ev.names.get(i, 0) for i in range(len(pkg.names))]
        nbad = [(i, ncounts[i - 1], ncounts[i]) for i in range(1, len(ncounts))
                if ncounts[i] > ncounts[i - 1]]
        print(f"names: {len(ncounts)}; descending-violations: {len(nbad)}")
        for i, a, b in nbad[:10]:
            print(f"  name[{i-1}] {pkg.names[i-1]}={a} < name[{i}] {pkg.names[i]}={b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
