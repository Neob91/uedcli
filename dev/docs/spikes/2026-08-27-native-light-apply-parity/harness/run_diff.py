#!/usr/bin/env python3
"""Where the per-surface light RUNS diverge: which lights native adds that the editor does not, and
which it misses — aggregated per light actor, and split by whether the run's ORDER alone differs.

Runs are compared as export NAMES (renumbering is not a difference) at the same `LightMap` record
index, which only means the same surface when the two trees agree — build the oracle with
`build_ued_lit_golden.py`, whose paste-built tree native reproduces exactly.

Usage: run_diff.py NATIVE.dx EDITOR.dx [--top N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lightparity import _load, level_model, light_names, runs  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("native")
    ap.add_argument("editor")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    repo = str(Path(__file__).resolve().parents[5])
    upackage, umodel = _load(repo)
    npkg, nm = level_model(upackage, umodel, args.native)
    epkg, em = level_model(upackage, umodel, args.editor)
    nruns = runs(nm, light_names(npkg, nm))
    eruns = runs(em, light_names(epkg, em))

    common = min(len(nm.light_map), len(em.light_map))
    extra_by_light: dict[str, int] = {}
    missing_by_light: dict[str, int] = {}
    same_set = order_only = 0
    for k in range(common):
        a, b = nruns[k], eruns[k]
        if a == b:
            same_set += 1
            continue
        if sorted(a) == sorted(b):
            order_only += 1
            continue
        for n in set(a) - set(b):
            extra_by_light[n] = extra_by_light.get(n, 0) + 1
        for n in set(b) - set(a):
            missing_by_light[n] = missing_by_light.get(n, 0) + 1

    print(f"records compared: {common}")
    print(f"  run identical (same set, same order): {same_set}")
    print(f"  same SET, different ORDER only:       {order_only}")
    print(f"  set differs:                          {common - same_set - order_only}")
    print(f"  total extra (surf, light) pairs native adds:   "
          f"{sum(extra_by_light.values())}")
    print(f"  total (surf, light) pairs native misses:       "
          f"{sum(missing_by_light.values())}")

    for label, d in (("EXTRA in native", extra_by_light), ("MISSING from native", missing_by_light)):
        print(f"\n{label} — top {args.top} light actors by surfaces affected "
              f"({len(d)} distinct):")
        for n, c in sorted(d.items(), key=lambda kv: -kv[1])[:args.top]:
            print(f"    {n:22} {c:6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
