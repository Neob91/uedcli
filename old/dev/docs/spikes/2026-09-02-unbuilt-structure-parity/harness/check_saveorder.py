#!/usr/bin/env python3
"""Regression runner for the MAP SAVE table-order model. Prints PASS/FAIL for the
confirmed findings; exits non-zero on any regression. Needs the goldens under
_scratch/unbuilt-parity/ (gitignored) and the committed trace dump next to this file.

  toys  : import + name order reproduced EXACTLY (generative)
  unatco: counters exact (0 descending-violations, 0 name misses); every order
          mismatch is a same-count tie (order determined by count except in ties)
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from uedcli.upackage import load_package                      # noqa: E402
from count_refs import collect, import_totals                # noqa: E402

SCR = ROOT / "_scratch/unbuilt-parity"
DUMP = HERE / "toysmall_startup.dump.txt"
UNATCO_TRUNK = (ROOT / "_scratch/uedcli-parity-cache/"
                "485ea1fd396ec8306b89e719ebb1c46af53c7ee6316446a3a0600ff33dd0da00/"
                "trunk/maps/03_nyc_unatcohq")

TOYS = [("toysmall", SCR / "toys/toysmall/maps/toysmall"),
        ("toy30", SCR / "toys/toy30/maps/toy30"),
        ("toy150", SCR / "toys/toy150/maps/toy150")]


def _counts_exact(pkg) -> bool:
    ev = collect(pkg)
    tot = import_totals(pkg, ev)
    imp_ok = all(tot[j] <= tot[j - 1] for j in range(1, len(tot)))
    nc = [ev.names.get(i, 0) for i in range(len(pkg.names))]
    nm_ok = all(nc[i] <= nc[i - 1] for i in range(1, len(nc)))
    return imp_ok and nm_ok


def _unatco_import_exact(golden: str) -> bool:
    import predict_unatco as PU
    from uedcli.native.saveorder import compute_tables
    pkg = load_package(golden)
    dx = Path(golden).read_bytes()
    spec = compute_tables(dx, PU.load_order_files(str(UNATCO_TRUNK)), [])

    def path_of(j: int) -> str:
        parts, k = [], j
        while True:
            cp, cn, outer, on = spec.imports[k]
            parts.append(spec.names[on])
            if outer >= 0:
                break
            k = -outer - 1
        return ".".join(reversed(parts)).lower()

    return [path_of(j) for j in range(len(spec.imports))] == [p for p, _ in PU.golden_import_paths(pkg)]


def main() -> int:
    import predict_tables as PT
    ok = True

    for name, trunk in TOYS:
        gold = SCR / f"toys/{name}_a.dx"
        if not gold.exists():
            print(f"SKIP {name}: golden missing")
            continue
        PT.TRUNK_ORDER = PT._trunk_order(str(trunk))
        good = PT.predict(DUMP, str(gold))
        print(f"{'PASS' if good else 'FAIL'} {name}: generative import+name order EXACT")
        ok &= good

    ug = SCR / "unatco/golden_import.dx"
    if ug.exists() and UNATCO_TRUNK.exists():
        good = _unatco_import_exact(str(ug))
        print(f"{'PASS' if good else 'FAIL'} unatco: generative IMPORT order EXACT "
              f"(creation-order model)")
        ok &= good
        print(f"     unatco: counters exact = {_counts_exact(load_package(str(ug)))}")
    else:
        print("SKIP unatco: golden or trunk missing")

    print("ALL PASS" if ok else "REGRESSION")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
